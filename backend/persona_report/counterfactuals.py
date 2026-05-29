"""Estimate predicted completion-rate lift for a Fix.

Grounded in observed sibling paths only (no LLM): when an agent forked at a
low-confidence decision and a sibling took the alternative action, the sibling
becomes the counterfactual outcome. The lift estimate is the difference
between sibling completion rate and the baseline completion rate of the
affected agents.

When fewer than 2 siblings exist for the affected set, return method
"insufficient-data" with `predicted_lift_pct=None` — never fabricate.
"""
from __future__ import annotations

from typing import Iterable

from persona_simulation.schema import AgentPath, SimulationResult

from persona_report.schema import CounterfactualImpact


HIGH_SAMPLE = 5
MEDIUM_SAMPLE = 2

HIGH_MARGIN = 0.05
MEDIUM_MARGIN = 0.10


def _completion_rate(paths: Iterable[AgentPath]) -> float:
    paths = list(paths)
    if not paths:
        return 0.0
    completed = sum(1 for p in paths if p.terminal_state == "complete")
    return completed / len(paths)


def _gather_siblings(
    affected_agents: list[AgentPath], sim: SimulationResult
) -> list[AgentPath]:
    """Paths whose agent.parent_agent_id is in the affected set.

    These are the alternative-action descendants spawned by the simulator
    fork machinery — a direct counterfactual to the affected agents' walks.
    """
    affected_ids = {p.agent.agent_id for p in affected_agents}
    return [
        p for p in sim.paths
        if p.agent.parent_agent_id and p.agent.parent_agent_id in affected_ids
    ]


def compute_counterfactual_impact(
    affected_agents: list[AgentPath],
    sim: SimulationResult,
) -> CounterfactualImpact:
    """Return a CounterfactualImpact for a Fix's affected agent set.

    The method is "sibling-path" when sample_size ≥ MEDIUM_SAMPLE; otherwise
    "insufficient-data" and predicted_lift_pct is None.
    """
    affected_personas = sorted({p.agent.cluster_id for p in affected_agents})

    if not affected_agents:
        return CounterfactualImpact(
            confidence="low",
            method="insufficient-data",
            affected_personas=affected_personas,
        )

    baseline = _completion_rate(affected_agents)
    siblings = _gather_siblings(affected_agents, sim)
    n = len(siblings)

    if n < MEDIUM_SAMPLE:
        return CounterfactualImpact(
            sample_size=n,
            confidence="low",
            method="insufficient-data",
            baseline_completion_rate=round(baseline, 3),
            affected_personas=affected_personas,
        )

    sibling_rate = _completion_rate(siblings)
    lift = sibling_rate - baseline

    confidence = "high" if n >= HIGH_SAMPLE else "medium"
    margin = HIGH_MARGIN if confidence == "high" else MEDIUM_MARGIN
    range_lo = max(lift - margin, -1.0)
    range_hi = min(lift + margin, 1.0)

    return CounterfactualImpact(
        predicted_lift_pct=round(lift, 3),
        predicted_lift_range=[round(range_lo, 3), round(range_hi, 3)],
        sample_size=n,
        confidence=confidence,
        affected_personas=affected_personas,
        method="sibling-path",
        sibling_completion_rate=round(sibling_rate, 3),
        baseline_completion_rate=round(baseline, 3),
    )
