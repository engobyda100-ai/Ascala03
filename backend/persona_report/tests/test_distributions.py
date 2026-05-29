"""Tests for each chart_type builder + empty-state handling."""
from __future__ import annotations

from persona_report import distributions, filters
from persona_report.schema import PersonaDistribution


def _build(test_type: str, sim) -> list[PersonaDistribution]:
    slice_ = filters.select_for(test_type, sim)
    return distributions.build(slice_, sim)


def test_a11y_scatter_axes_and_dots(sample_simulation):
    dists = _build("accessibility", sample_simulation)
    scatter = next(d for d in dists if d.chart_type == "scatter")
    assert "x" in scatter.axes and "y" in scatter.axes
    assert len(scatter.dots) == len(sample_simulation.paths)
    for d in scatter.dots:
        assert isinstance(d.x, (int, float))
        assert isinstance(d.y, (int, float))


def test_a11y_dot_grid_per_cluster_with_empty_clusters_annotated(sample_simulation):
    dists = _build("accessibility", sample_simulation)
    grid = next(d for d in dists if d.chart_type == "dot_grid")
    assert grid.scope == "per_cluster"
    # The fixture has a11y signal mainly in pg_3; pg_1 may have none → empty state annotation
    if not any(d.cluster_id == "pg_1" for d in grid.dots):
        assert any(
            ann.type == "empty_state" and ann.position and ann.position.get("cluster_id") == "pg_1"
            for ann in grid.annotations
        )


def test_a11y_beeswarm_is_1d(sample_simulation):
    dists = _build("accessibility", sample_simulation)
    swarm = next(d for d in dists if d.chart_type == "beeswarm")
    assert "x" in swarm.axes
    assert "y" not in swarm.axes
    assert len(swarm.dots) == len(sample_simulation.paths)


def test_compliance_grouped_dot_plot_uses_categorical_x(sample_simulation):
    dists = _build("compliance", sample_simulation)
    grouped = next(d for d in dists if d.chart_type == "grouped_dot_plot")
    assert grouped.axes["x"].categorical is not None
    assert "GDPR" in grouped.axes["x"].categorical or "none" in grouped.axes["x"].categorical


def test_compliance_funnel(sample_simulation):
    dists = _build("compliance", sample_simulation)
    funnel = next(d for d in dists if d.chart_type == "funnel_dot_flow")
    if funnel.dots:
        outcomes = {d.y for d in funnel.dots}
        assert outcomes.issubset({"proceeded", "bailed"})


def test_onboarding_funnel_per_cluster(sample_simulation):
    dists = _build("onboarding", sample_simulation)
    funnel = next(d for d in dists if d.chart_type == "funnel_dot_flow")
    assert funnel.scope == "per_cluster"
    assert all(d.x.startswith("step_") for d in funnel.dots)


def test_onboarding_scatter_axes(sample_simulation):
    dists = _build("onboarding", sample_simulation)
    scatter = next(d for d in dists if d.chart_type == "scatter")
    assert scatter.axes["x"].max == 5
    assert scatter.axes["y"].unit == "s"


def test_activation_dot_plot_outcomes(sample_simulation):
    dists = _build("activation", sample_simulation)
    dp = next(d for d in dists if d.chart_type == "dot_plot")
    outcomes = {d.meta.get("activation_outcome") for d in dp.dots}
    assert outcomes.issubset({"activated", "partial", "bounced"})


def test_activation_parallel_has_4_axes_and_meta(sample_simulation):
    dists = _build("activation", sample_simulation)
    pc = next(d for d in dists if d.chart_type == "parallel_coordinates")
    assert set(pc.axes.keys()) == {
        "reached_aha", "used_core_feature", "configured_setting", "invited_teammate",
    }
    for d in pc.dots:
        assert set(d.meta.keys()) >= set(pc.axes.keys())


def test_engagement_beeswarm_1d_per_cluster(sample_simulation):
    dists = _build("engagement", sample_simulation)
    swarm = next(d for d in dists if d.chart_type == "beeswarm")
    assert swarm.scope == "per_cluster"
    assert "y" not in swarm.axes


def test_engagement_scatter_x_y(sample_simulation):
    dists = _build("engagement", sample_simulation)
    scatter = next(d for d in dists if d.chart_type == "scatter")
    assert "y" in scatter.axes


def test_retention_carries_predictive_note(sample_simulation):
    dists = _build("retention", sample_simulation)
    for d in dists:
        notes = [a for a in d.annotations if a.type == "note"]
        assert any("predictive" in n.text.lower() for n in notes)


def test_retention_grouped_count_groups(sample_simulation):
    dists = _build("retention", sample_simulation)
    grouped = next(d for d in dists if d.chart_type == "grouped_dot_count")
    groups = {d.x for d in grouped.dots}
    assert groups.issubset(
        {"habit_marker_touched", "switching_cost_expressed", "neither"}
    )


def test_each_test_type_returns_2_or_3_distributions(sample_simulation):
    for tt in ("accessibility", "compliance", "onboarding",
               "activation", "engagement", "retention"):
        dists = _build(tt, sample_simulation)
        assert 2 <= len(dists) <= 3


def test_empty_input_distribution_emits_empty_state(sample_simulation):
    """If we pass a SimulationResult with no paths, the distributions still render."""
    sim = sample_simulation.model_copy(deep=True)
    sim.paths = []
    sim.report.categorized_issues.issues = []
    sim.report.metrics.completion_rate_by_cluster = {}
    for tt in ("accessibility", "compliance", "onboarding",
               "activation", "engagement", "retention"):
        slice_ = filters.select_for(tt, sim)
        dists = distributions.build(slice_, sim)
        for d in dists:
            if not d.dots:
                assert any(a.type == "empty_state" for a in d.annotations)
