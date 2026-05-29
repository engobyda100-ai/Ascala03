"""Outcome context (per test) and executive summary (cross-test).

Pure code: derives business framing from observed completion rates and
existing TestTypeReports. No LLM.
"""
from __future__ import annotations

from typing import Optional

from persona_simulation.schema import SimulationResult

from persona_report.filters import FilteredSlice
from persona_report.schema import (
    ExecutiveSummary,
    OutcomeContext,
    TestTypeReport,
)


TEST_TYPE_METRIC: dict[str, str] = {
    "accessibility": "completion rate among agents with accessibility needs",
    "compliance": "compliance touchpoint pass-through rate",
    "onboarding": "onboarding completion rate",
    "activation": "activation rate (reached aha moment)",
    "engagement": "session-depth completion rate",
    "retention": "predictive return likelihood",
}


def _slice_completion_rate(slice_: FilteredSlice) -> float:
    if not slice_.paths:
        return 0.0
    completed = sum(1 for p in slice_.paths if p.terminal_state == "complete")
    return completed / len(slice_.paths)


def _per_cluster_completion_rate(slice_: FilteredSlice) -> dict[str, float]:
    totals: dict[str, int] = {}
    completes: dict[str, int] = {}
    for p in slice_.paths:
        cid = p.agent.cluster_id
        totals[cid] = totals.get(cid, 0) + 1
        if p.terminal_state == "complete":
            completes[cid] = completes.get(cid, 0) + 1
    return {cid: completes.get(cid, 0) / total for cid, total in totals.items()}


def compute_outcome_context(
    test_type: str, slice_: FilteredSlice, sim: SimulationResult
) -> OutcomeContext:
    overall = _slice_completion_rate(slice_)
    by_cluster = _per_cluster_completion_rate(slice_)
    metric = TEST_TYPE_METRIC.get(test_type, f"{test_type} completion rate")
    baseline_str = f"{round(overall * 100)}% complete ({test_type})"

    if not by_cluster:
        return OutcomeContext(
            test_type_metric=metric,
            baseline_outcome=baseline_str,
            overall_completion_rate=round(overall, 3),
            completion_rate_by_cluster={},
            business_implication=(
                f"No cluster-level data available for {test_type}."
            ),
        )

    worst_cid = min(by_cluster, key=lambda c: by_cluster[c])
    best_cid = max(by_cluster, key=lambda c: by_cluster[c])
    worst_rate = by_cluster[worst_cid]
    best_rate = by_cluster[best_cid]
    gap = best_rate - worst_rate

    if gap < 0.05:
        implication = (
            f"{metric.capitalize()} is consistent across clusters "
            f"(~{round(overall * 100)}%). No single segment is disproportionately blocked."
        )
    else:
        implication = (
            f"{worst_cid} ({round(worst_rate * 100)}%) trails {best_cid} "
            f"({round(best_rate * 100)}%) by {round(gap * 100)} points on {metric}. "
            f"Closing this gap is the highest-impact lever for {test_type}."
        )

    return OutcomeContext(
        test_type_metric=metric,
        baseline_outcome=baseline_str,
        overall_completion_rate=round(overall, 3),
        completion_rate_by_cluster={k: round(v, 3) for k, v in by_cluster.items()},
        worst_affected_cluster=worst_cid,
        worst_affected_cluster_rate=round(worst_rate, 3),
        best_performing_cluster=best_cid,
        best_performing_cluster_rate=round(best_rate, 3),
        gap_pct=round(gap, 3),
        business_implication=implication,
    )


def compute_executive_summary(
    test_type_reports: list[TestTypeReport],
    sim: SimulationResult,
    *,
    business_summary: Optional[str] = None,
) -> ExecutiveSummary:
    """Cross-test executive framing — overall + worst-hit cluster + top blockers."""
    paths = list(sim.paths)
    overall = (
        sum(1 for p in paths if p.terminal_state == "complete") / len(paths)
        if paths else 0.0
    )

    totals: dict[str, int] = {}
    completes: dict[str, int] = {}
    for p in paths:
        cid = p.agent.cluster_id
        totals[cid] = totals.get(cid, 0) + 1
        if p.terminal_state == "complete":
            completes[cid] = completes.get(cid, 0) + 1
    by_cluster = {
        cid: completes.get(cid, 0) / total
        for cid, total in totals.items()
    }

    worst_cid = min(by_cluster, key=lambda c: by_cluster[c]) if by_cluster else None
    best_cid = max(by_cluster, key=lambda c: by_cluster[c]) if by_cluster else None
    worst_rate = by_cluster[worst_cid] if worst_cid else None
    best_rate = by_cluster[best_cid] if best_cid else None
    gap = (best_rate - worst_rate) if (worst_rate is not None and best_rate is not None) else None

    severity_rank = {"urgent": 3, "important": 2, "medium": 1}
    blocker_candidates: list[tuple[int, int, str]] = []
    for ttr in test_type_reports:
        for f in ttr.recommended_fixes:
            sev_score = severity_rank.get(f.severity, 0)
            cluster_impact = (
                len(f.counterfactual_impact.affected_personas)
                if f.counterfactual_impact else len(f.evidence.affected_clusters)
            )
            blocker_candidates.append((sev_score, cluster_impact, f.title))
    blocker_candidates.sort(reverse=True)
    top_blockers = [t for _, _, t in blocker_candidates[:5]]

    return ExecutiveSummary(
        overall_completion_rate=round(overall, 3),
        completion_rate_by_cluster={k: round(v, 3) for k, v in by_cluster.items()},
        worst_affected_cluster=worst_cid,
        worst_affected_cluster_rate=round(worst_rate, 3) if worst_rate is not None else None,
        best_performing_cluster=best_cid,
        best_performing_cluster_rate=round(best_rate, 3) if best_rate is not None else None,
        cluster_gap_pct=round(gap, 3) if gap is not None else None,
        top_blockers_across_tests=top_blockers,
        business_summary=business_summary,
    )
