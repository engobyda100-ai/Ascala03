"""Final simulation-report synthesis.

Two parts:
  - `curate_traces()` — pure heuristic that picks up to 3 representative
    AgentPaths per cluster (highest-friction, most-successful, median).
  - `build_report()` — one LLM call that takes metrics + issues + curated
    traces and emits a narrative SimulationReport.
"""
from __future__ import annotations

import json
from collections import defaultdict
from statistics import median_low
from typing import Any

from pydantic import BaseModel, Field

from persona_synthesis.llm.base import LLMProvider

from persona_simulation._llm_helpers import call_with_retry, load_prompt
from persona_simulation.schema import (
    AgentPath,
    CategorizedIssues,
    ClusterFinding,
    GlobalMetrics,
    SimulationReport,
    TestCategory,
)


TOOL_NAME = "emit_report"
TOOL_DESCRIPTION = "Emit the narrative SimulationReport synthesizing metrics + issues + curated traces."


# ──────────────────────────── curate_traces ────────────────────────────

def _total_frustration(p: AgentPath) -> int:
    return sum(s.decision.emotional_state.frustration for s in p.steps)


def curate_traces(paths: list[AgentPath]) -> dict[str, list[AgentPath]]:
    """For each cluster, pick up to 3 representative paths.

    Selection, per cluster:
      1. highest-friction     — argmax(sum of frustration across steps)
      2. most-successful      — terminal_state=='complete' with fewest steps;
                                tiebreak on least total frustration
      3. median               — median step count among the rest
    """
    by_cluster: dict[str, list[AgentPath]] = defaultdict(list)
    for p in paths:
        by_cluster[p.agent.cluster_id].append(p)

    curated: dict[str, list[AgentPath]] = {}
    for cid, group in by_cluster.items():
        if not group:
            continue
        highest_friction = max(group, key=_total_frustration)

        completed = [p for p in group if p.terminal_state == "complete"]
        most_successful = None
        if completed:
            most_successful = min(
                completed,
                key=lambda p: (len(p.steps), _total_frustration(p)),
            )

        remainder = [p for p in group if p is not highest_friction and p is not most_successful]
        median_pick = None
        if remainder:
            median_step_count = median_low([len(p.steps) for p in remainder])
            # pick a path closest to that median length
            median_pick = min(remainder, key=lambda p: abs(len(p.steps) - median_step_count))

        picks: list[AgentPath] = [highest_friction]
        if most_successful is not None and most_successful not in picks:
            picks.append(most_successful)
        if median_pick is not None and median_pick not in picks:
            picks.append(median_pick)
        curated[cid] = picks
    return curated


# ──────────────────────────── build_report ────────────────────────────


def _trace_excerpt(p: AgentPath, max_steps: int = 12) -> dict[str, Any]:
    """Compact dict representation of an AgentPath for the report prompt."""
    shown = p.steps[:max_steps]
    return {
        "agent_id": p.agent.agent_id,
        "cluster_id": p.agent.cluster_id,
        "cluster_name": p.agent.cluster_name,
        "terminal_state": p.terminal_state,
        "screens_visited": p.screens_visited,
        "fork_points": p.fork_points,
        "cumulative_seconds": p.cumulative_seconds,
        "n_steps": len(p.steps),
        "steps": [
            {
                "order": s.order,
                "screen_id": s.screen_id,
                "action": s.decision.action,
                "target_element_id": s.decision.target_element_id,
                "confidence": s.decision.confidence,
                "emotional_state": s.decision.emotional_state.model_dump(),
                "reasoning": s.decision.reasoning,
                "observed_issues": s.decision.observed_issues,
            }
            for s in shown
        ],
        "truncated": len(p.steps) > max_steps,
    }


def _empty_cluster_findings(metrics: GlobalMetrics) -> list[ClusterFinding]:
    """Fallback used when the LLM emits fewer cluster_findings than clusters
    present in the metrics — we pad so the report still round-trips."""
    return [
        ClusterFinding(
            cluster_id=cid,
            cluster_name=cid,
            summary="(no narrative finding generated)",
            completion_rate=rate,
            key_friction=[],
        )
        for cid, rate in metrics.completion_rate_by_cluster.items()
    ]


def build_report(
    metrics: GlobalMetrics,
    issues: CategorizedIssues,
    curated_traces: dict[str, list[AgentPath]],
    *,
    provider: LLMProvider,
) -> SimulationReport:
    """One LLM call; returns the full SimulationReport with metrics + issues
    passed through unchanged."""
    trace_bundle = {
        cid: [_trace_excerpt(p) for p in paths]
        for cid, paths in curated_traces.items()
    }

    # The LLM will produce the narrative fields; we stitch metrics/issues back in.
    class _ReportNarrative(BaseModel):
        executive_summary: str = Field(min_length=1)
        cluster_findings: list[ClusterFinding] = Field(default_factory=list)
        top_friction_points: list[str] = Field(default_factory=list)
        findings_by_category: dict[str, list[str]] = Field(default_factory=dict)
        recommended_next_tests: list[str] = Field(default_factory=list)

    user_text = (
        "Global metrics from the simulation:\n"
        f"```json\n{json.dumps(metrics.model_dump(), indent=2)}\n```\n\n"
        "Categorized issues:\n"
        f"```json\n{json.dumps(issues.model_dump(), indent=2)}\n```\n\n"
        "Curated agent traces (highest-friction, most-successful, median per cluster):\n"
        f"```json\n{json.dumps(trace_bundle, indent=2)}\n```\n\n"
        "Emit the narrative report via the emit_report tool now. Produce "
        "executive_summary, cluster_findings (one entry per cluster present in "
        "metrics.completion_rate_by_cluster), top_friction_points, "
        "findings_by_category (keys from the 5 test categories), and "
        "recommended_next_tests. Do NOT include metrics or categorized_issues "
        "in your output — the caller stitches those back in."
    )

    system = load_prompt("simulation_report.md")
    narrative, _tokens = call_with_retry(
        provider,
        system=system,
        user_content=[{"type": "text", "text": user_text}],
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=_ReportNarrative,
    )

    findings = narrative.cluster_findings or _empty_cluster_findings(metrics)
    # Ensure every category key exists in findings_by_category even if empty.
    all_categories: list[TestCategory] = [
        "accessibility", "compliance", "onboarding", "activation", "engagement_retention",
    ]
    fbc = dict(narrative.findings_by_category)
    for cat in all_categories:
        fbc.setdefault(cat, [])

    return SimulationReport(
        executive_summary=narrative.executive_summary,
        cluster_findings=findings,
        top_friction_points=narrative.top_friction_points,
        findings_by_category=fbc,
        recommended_next_tests=narrative.recommended_next_tests,
        metrics=metrics,
        categorized_issues=issues,
    )
