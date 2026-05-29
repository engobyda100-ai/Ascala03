"""Tests for counterfactuals, trajectories, scenarios, outcome context, and exec summary."""
from __future__ import annotations

from persona_report import distributions, filters
from persona_report.counterfactuals import compute_counterfactual_impact
from persona_report.outcomes import compute_executive_summary, compute_outcome_context
from persona_report.predictions import build_scenarios
from persona_report.schema import (
    CounterfactualImpact,
    Fix,
    FixEvidence,
)


def _make_siblings(parent_path, terminals):
    """Clone `parent_path` once per terminal state, marking each as a sibling fork."""
    siblings = []
    for i, term in enumerate(terminals):
        sib = parent_path.model_copy(deep=True)
        sib_agent = parent_path.agent.model_copy(update={
            "agent_id": f"{parent_path.agent.agent_id}-fork{i}",
            "parent_agent_id": parent_path.agent.agent_id,
        })
        sib_path = sib.model_copy(update={
            "agent": sib_agent,
            "terminal_state": term,
        })
        siblings.append(sib_path)
    return siblings


# ──────────────────────────── Counterfactuals ────────────────────────────

def test_counterfactual_lift_from_siblings(sample_simulation):
    parent = sample_simulation.paths[0]
    siblings = _make_siblings(parent, ["complete", "complete", "complete", "give_up"])
    new_sim = sample_simulation.model_copy(update={"paths": [parent] + siblings})

    impact = compute_counterfactual_impact([parent], new_sim)

    assert impact.method == "sibling-path"
    assert impact.sample_size == 4
    assert impact.confidence == "medium"
    assert impact.sibling_completion_rate == 0.75
    baseline = 1.0 if parent.terminal_state == "complete" else 0.0
    assert impact.baseline_completion_rate == baseline
    assert impact.predicted_lift_pct == round(0.75 - baseline, 3)
    assert impact.predicted_lift_range is not None
    lo, hi = impact.predicted_lift_range
    assert lo < impact.predicted_lift_pct < hi or lo == hi == impact.predicted_lift_pct


def test_counterfactual_high_confidence_with_5_plus_siblings(sample_simulation):
    parent = sample_simulation.paths[0]
    siblings = _make_siblings(
        parent, ["complete", "complete", "complete", "complete", "complete"]
    )
    new_sim = sample_simulation.model_copy(update={"paths": [parent] + siblings})

    impact = compute_counterfactual_impact([parent], new_sim)
    assert impact.sample_size == 5
    assert impact.confidence == "high"
    assert impact.sibling_completion_rate == 1.0


def test_counterfactual_insufficient_data(sample_simulation):
    parent = sample_simulation.paths[0]
    # Only 1 sibling → below MEDIUM_SAMPLE threshold
    siblings = _make_siblings(parent, ["complete"])
    new_sim = sample_simulation.model_copy(update={"paths": [parent] + siblings})

    impact = compute_counterfactual_impact([parent], new_sim)
    assert impact.method == "insufficient-data"
    assert impact.confidence == "low"
    assert impact.predicted_lift_pct is None
    assert impact.sample_size == 1


def test_counterfactual_no_affected_agents(sample_simulation):
    impact = compute_counterfactual_impact([], sample_simulation)
    assert impact.method == "insufficient-data"
    assert impact.confidence == "low"
    assert impact.predicted_lift_pct is None


# ──────────────────────────── Trajectories ────────────────────────────

def test_trajectory_aggregation_screens_and_cells(sample_simulation):
    slice_ = filters.select_for("onboarding", sample_simulation)
    traj = distributions.compute_trajectory(slice_, sample_simulation)

    assert len(traj.screens) > 0
    assert len(traj.clusters) > 0
    assert len(traj.cells) > 0
    # Each cell's screen_id must be in the screens list at the recorded index
    for cell in traj.cells:
        assert traj.screens[cell.screen_index] == cell.screen_id
        assert cell.cluster_id in traj.clusters
        # All averages bounded [1, 5]
        for emo in (cell.emotions.confusion, cell.emotions.frustration,
                    cell.emotions.interest, cell.emotions.trust):
            assert 1.0 <= emo <= 5.0
        assert cell.sample_size >= 1


def test_trajectory_average_matches_hand_compute(sample_simulation):
    slice_ = filters.select_for("onboarding", sample_simulation)
    traj = distributions.compute_trajectory(slice_, sample_simulation)
    if not traj.cells:
        return
    target = traj.cells[0]
    # Hand-compute average frustration for (cluster, screen)
    samples = []
    for p in slice_.paths:
        if p.agent.cluster_id != target.cluster_id:
            continue
        for step in p.steps:
            if step.screen_id == target.screen_id:
                samples.append(step.decision.emotional_state.frustration)
    expected = round(sum(samples) / len(samples), 3)
    assert target.emotions.frustration == expected
    assert target.sample_size == len(samples)


# ──────────────────────────── Scenarios ────────────────────────────

def _fake_fix(title, lift, confidence="medium"):
    return Fix(
        severity="important",
        title=title,
        summary=f"summary for {title}",
        evidence=FixEvidence(),
        fix_prompt=(
            "On the s1 screen (s1.png), placeholder.\n"
            "Evidence: 1/1 agents in the X cluster did Y.\n"
            "Change required: add a thing.\n"
            "Visual/interaction direction: clearer."
        ),
        estimated_impact="-",
        related_issue_ids=[],
        counterfactual_impact=CounterfactualImpact(
            predicted_lift_pct=lift,
            predicted_lift_range=[lift - 0.05, lift + 0.05],
            sample_size=4,
            confidence=confidence,
            affected_personas=[],
            method="sibling-path",
            sibling_completion_rate=0.5 + lift,
            baseline_completion_rate=0.5,
        ),
    )


def test_scenario_combination_ranges(sample_simulation):
    slice_ = filters.select_for("onboarding", sample_simulation)
    fixes = [
        _fake_fix("Fix A", 0.10, "high"),
        _fake_fix("Fix B", 0.08, "medium"),
        _fake_fix("Fix C", 0.05, "medium"),
    ]
    scenarios = build_scenarios(fixes, slice_, sample_simulation)
    names = [s.name for s in scenarios]
    assert "status_quo" in names
    assert "quick_win" in names

    quick = next(s for s in scenarios if s.name == "quick_win")
    # Quick win = top 2 fixes (lifts 0.10, 0.08); low = max single = 0.10, high = additive
    assert quick.predicted_lift_low == 0.10
    headroom = max(1.0 - quick.baseline_completion_rate, 0.0)
    expected_high = round(min(0.10 + 0.08, headroom), 3)
    assert quick.predicted_lift_high == expected_high

    if "redesign" in names:
        redesign = next(s for s in scenarios if s.name == "redesign")
        assert redesign.predicted_lift_low == 0.10
        assert redesign.predicted_lift_high >= quick.predicted_lift_high


def test_scenarios_skips_when_no_grounded_fixes(sample_simulation):
    slice_ = filters.select_for("onboarding", sample_simulation)
    scenarios = build_scenarios([], slice_, sample_simulation)
    assert len(scenarios) == 1
    assert scenarios[0].name == "status_quo"


# ──────────────────────────── Outcome context ────────────────────────────

def test_outcome_context_identifies_worst_cluster(sample_simulation):
    slice_ = filters.select_for("onboarding", sample_simulation)
    ctx = compute_outcome_context("onboarding", slice_, sample_simulation)

    if ctx.completion_rate_by_cluster:
        rates = ctx.completion_rate_by_cluster
        assert ctx.worst_affected_cluster == min(rates, key=lambda c: rates[c])
        assert ctx.best_performing_cluster == max(rates, key=lambda c: rates[c])
        assert ctx.gap_pct == round(
            rates[ctx.best_performing_cluster] - rates[ctx.worst_affected_cluster], 3
        )
    assert "onboarding" in ctx.test_type_metric


# ──────────────────────────── Executive summary ────────────────────────────

def test_executive_summary_aggregates_completion_and_blockers(sample_simulation, default_provider):
    from persona_report.generator import generate_report
    report = generate_report(sample_simulation, provider=default_provider, include_executive_summary=False)

    summary = report.summary
    assert summary is not None
    assert 0.0 <= summary.overall_completion_rate <= 1.0
    if summary.completion_rate_by_cluster:
        rates = summary.completion_rate_by_cluster
        assert summary.worst_affected_cluster == min(rates, key=lambda c: rates[c])
        assert summary.best_performing_cluster == max(rates, key=lambda c: rates[c])
        assert summary.cluster_gap_pct == round(
            rates[summary.best_performing_cluster] - rates[summary.worst_affected_cluster], 3
        )
    # Top blockers ordered by severity (urgent > important > medium)
    assert len(summary.top_blockers_across_tests) <= 5


def test_report_attaches_trajectory_and_scenarios(sample_simulation, default_provider):
    from persona_report.generator import generate_report
    report = generate_report(sample_simulation, provider=default_provider, include_executive_summary=False)

    for ttr in report.test_type_reports:
        assert ttr.outcome_context is not None
        assert ttr.trajectory is not None
        assert any(s.name == "status_quo" for s in ttr.scenarios)
