"""Build what-if scenarios from fixes with counterfactual_impact.

Three scenarios per test type:
- status_quo:  no fixes; current observed completion rate
- quick_win:   top 1–2 high/medium-confidence fixes by predicted_lift
- redesign:    top 3–4 fixes (deeper change)

Combined-fix lift is given as a range (no LLM interaction reasoning):
- low  = max single-fix lift (best individual fix alone)
- high = additive sum of selected fixes' lifts (capped by remaining headroom)

Skip scenarios when there aren't enough fixes with grounded lift data.
"""
from __future__ import annotations

from typing import Optional

from persona_simulation.schema import SimulationResult

from persona_report.filters import FilteredSlice
from persona_report.schema import Fix, Scenario


QUICK_WIN_MAX = 2
REDESIGN_MAX = 4


def _baseline_completion_rate(slice_: FilteredSlice) -> float:
    if not slice_.paths:
        return 0.0
    completed = sum(1 for p in slice_.paths if p.terminal_state == "complete")
    return completed / len(slice_.paths)


def _primary_benefit_cluster(slice_: FilteredSlice) -> Optional[str]:
    """Cluster with the lowest completion rate within the slice (most to gain)."""
    by_cluster_total: dict[str, int] = {}
    by_cluster_complete: dict[str, int] = {}
    for p in slice_.paths:
        cid = p.agent.cluster_id
        by_cluster_total[cid] = by_cluster_total.get(cid, 0) + 1
        if p.terminal_state == "complete":
            by_cluster_complete[cid] = by_cluster_complete.get(cid, 0) + 1
    if not by_cluster_total:
        return None
    rates = {
        cid: by_cluster_complete.get(cid, 0) / total
        for cid, total in by_cluster_total.items()
    }
    return min(rates, key=lambda c: rates[c])


def _grounded_fixes(fixes: list[Fix]) -> list[Fix]:
    grounded = [
        f for f in fixes
        if f.counterfactual_impact is not None
        and f.counterfactual_impact.predicted_lift_pct is not None
    ]
    grounded.sort(
        key=lambda f: f.counterfactual_impact.predicted_lift_pct,  # type: ignore[union-attr]
        reverse=True,
    )
    return grounded


def _scenario_from_picks(
    name: str,
    label: str,
    description: str,
    picks: list[Fix],
    baseline: float,
    primary_cluster: Optional[str],
    effort: str,
) -> Scenario:
    lifts = [
        f.counterfactual_impact.predicted_lift_pct  # type: ignore[union-attr]
        for f in picks
    ]
    single_max = max(lifts) if lifts else 0.0
    additive = sum(lifts) if lifts else 0.0
    lift_low = max(single_max, 0.0)
    headroom = max(1.0 - baseline, 0.0)
    lift_high = max(min(additive, headroom), lift_low)
    return Scenario(
        name=name,  # type: ignore[arg-type]
        label=label,
        description=description,
        fixes_applied=[f.title for f in picks],
        baseline_completion_rate=round(baseline, 3),
        predicted_completion_rate_low=round(min(baseline + lift_low, 1.0), 3),
        predicted_completion_rate_high=round(min(baseline + lift_high, 1.0), 3),
        predicted_lift_low=round(lift_low, 3),
        predicted_lift_high=round(lift_high, 3),
        primary_benefit_cluster=primary_cluster,
        effort_estimate=effort,
    )


def _build_compliance_accessibility_scenarios(fixes: list[Fix]) -> list[Scenario]:
    """Build severity-tier scenarios for compliance/accessibility (residual issue counts, not lift)."""
    # Count total issues by severity
    total_counts = {"urgent": 0, "important": 0, "medium": 0}
    urgent_fixes = []
    important_fixes = []

    for f in fixes:
        if f.severity not in total_counts:
            continue
        total_counts[f.severity] += 1
        if f.severity == "urgent":
            urgent_fixes.append(f.title)
        elif f.severity == "important":
            important_fixes.append(f.title)

    scenarios: list[Scenario] = [
        Scenario(
            name="status_quo",
            label="Status quo",
            description="No fixes applied — current issue baseline.",
            fixes_applied=[],
            residual_issue_counts=dict(total_counts),
            baseline_completion_rate=None,
            predicted_completion_rate_low=None,
            predicted_completion_rate_high=None,
            predicted_lift_low=None,
            predicted_lift_high=None,
            primary_benefit_cluster=None,
            effort_estimate="none",
        ),
        Scenario(
            name="quick_win",
            label="Fix critical",
            description="Resolve all urgent issues.",
            fixes_applied=urgent_fixes,
            residual_issue_counts={
                "urgent": 0,
                "important": total_counts["important"],
                "medium": total_counts["medium"],
            },
            baseline_completion_rate=None,
            predicted_completion_rate_low=None,
            predicted_completion_rate_high=None,
            predicted_lift_low=None,
            predicted_lift_high=None,
            primary_benefit_cluster=None,
            effort_estimate="small",
        ),
        Scenario(
            name="redesign",
            label="Fix critical + important",
            description="Resolve all urgent and important issues.",
            fixes_applied=urgent_fixes + important_fixes,
            residual_issue_counts={
                "urgent": 0,
                "important": 0,
                "medium": total_counts["medium"],
            },
            baseline_completion_rate=None,
            predicted_completion_rate_low=None,
            predicted_completion_rate_high=None,
            predicted_lift_low=None,
            predicted_lift_high=None,
            primary_benefit_cluster=None,
            effort_estimate="medium-to-large",
        ),
    ]
    return scenarios


def build_scenarios(
    fixes: list[Fix],
    slice_: FilteredSlice,
    sim: SimulationResult,
    test_type: str = "onboarding",
) -> list[Scenario]:
    if test_type in ("compliance", "accessibility"):
        return _build_compliance_accessibility_scenarios(fixes)
    if test_type == "retention":
        return []

    baseline = _baseline_completion_rate(slice_)
    primary = _primary_benefit_cluster(slice_)

    scenarios: list[Scenario] = [
        Scenario(
            name="status_quo",
            label="Status quo",
            description="No fixes applied — current observed completion rate.",
            fixes_applied=[],
            baseline_completion_rate=round(baseline, 3),
            predicted_completion_rate_low=round(baseline, 3),
            predicted_completion_rate_high=round(baseline, 3),
            predicted_lift_low=0.0,
            predicted_lift_high=0.0,
            primary_benefit_cluster=None,
            effort_estimate="none",
        )
    ]

    grounded = _grounded_fixes(fixes)
    if not grounded:
        return scenarios

    quick_picks = [
        f for f in grounded
        if f.counterfactual_impact and f.counterfactual_impact.confidence in ("high", "medium")  # type: ignore[union-attr]
    ][:QUICK_WIN_MAX]
    if quick_picks:
        scenarios.append(
            _scenario_from_picks(
                name="quick_win",
                label="Quick win",
                description=(
                    f"Apply the top {len(quick_picks)} highest-confidence fix"
                    f"{'es' if len(quick_picks) > 1 else ''}."
                ),
                picks=quick_picks,
                baseline=baseline,
                primary_cluster=primary,
                effort="small",
            )
        )

    redesign_picks = grounded[:REDESIGN_MAX]
    if len(redesign_picks) >= 2 and len(redesign_picks) > len(quick_picks):
        scenarios.append(
            _scenario_from_picks(
                name="redesign",
                label="Redesign",
                description=(
                    f"Apply the top {len(redesign_picks)} fixes — implies a deeper redesign."
                ),
                picks=redesign_picks,
                baseline=baseline,
                primary_cluster=primary,
                effort="medium-to-large",
            )
        )

    return scenarios
