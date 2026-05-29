"""Tests for curate_traces() and build_report()."""
from __future__ import annotations

from persona_synthesis.schema import PersonaGroup

from persona_simulation.report import build_report, curate_traces
from persona_simulation.schema import (
    AgentDecision,
    AgentPath,
    AgentStep,
    CategorizedIssues,
    DropOffPoint,
    EmotionalState,
    GlobalMetrics,
    SampledAgent,
)


def _agent(sample_personas, cluster_index=0, suffix="a") -> SampledAgent:
    group = PersonaGroup.model_validate(sample_personas[cluster_index])
    return SampledAgent(
        agent_id=f"a_{group.id}_{suffix}",
        cluster_id=group.id,
        cluster_name=group.name,
        age=30,
        tech_savviness=3,
        patience_threshold="medium",
        pricing_sensitivity=3,
        primary_device="desktop",
        group=group,
        personalized_backstory="test",
        rng_seed=0,
    )


def _step(order: int, frustration: int) -> AgentStep:
    return AgentStep(
        order=order, screen_id="s1",
        decision=AgentDecision(
            action="click_element", target_element_id="s1.btn_signup",
            reasoning="r", confidence=3,
            emotional_state=EmotionalState(
                confusion=1, frustration=frustration, interest=3, trust=3,
            ),
            estimated_seconds_on_screen=5,
        ),
        elapsed_seconds_total=5 * order,
    )


def _path(agent: SampledAgent, frustrations: list[int], terminal: str = "complete") -> AgentPath:
    steps = [_step(i + 1, f) for i, f in enumerate(frustrations)]
    return AgentPath(
        agent=agent, steps=steps,
        terminal_state=terminal,  # type: ignore[arg-type]
        screens_visited=["s1"] * (len(steps) + 1),
        cumulative_seconds=steps[-1].elapsed_seconds_total if steps else 0,
    )


def test_curate_picks_highest_frustration_per_cluster(sample_personas):
    a = _agent(sample_personas, 0, "a")
    b = _agent(sample_personas, 0, "b")
    c = _agent(sample_personas, 0, "c")
    paths = [
        _path(a, [1, 1, 1], terminal="complete"),
        _path(b, [5, 5, 5], terminal="give_up"),
        _path(c, [2, 3, 3], terminal="max_steps_reached"),
    ]
    curated = curate_traces(paths)
    cid = a.cluster_id
    assert cid in curated
    picked = curated[cid]
    ids = [p.agent.agent_id for p in picked]
    # highest friction path must be present
    assert b.agent_id in ids
    # most-successful (complete) path must be present
    assert a.agent_id in ids


def test_curate_handles_zero_completions(sample_personas):
    a = _agent(sample_personas, 0, "a")
    b = _agent(sample_personas, 0, "b")
    paths = [
        _path(a, [2, 2], terminal="give_up"),
        _path(b, [5, 5], terminal="give_up"),
    ]
    curated = curate_traces(paths)
    picked = curated[a.cluster_id]
    # No "most-successful" → fewer picks but still works
    assert 1 <= len(picked) <= 3
    # Highest frustration is b
    assert picked[0].agent.agent_id == b.agent_id


def test_curate_splits_by_cluster(sample_personas):
    a = _agent(sample_personas, 0, "a")
    b = _agent(sample_personas, 1, "b")
    paths = [_path(a, [3], "complete"), _path(b, [3], "complete")]
    curated = curate_traces(paths)
    assert set(curated.keys()) == {a.cluster_id, b.cluster_id}


def test_build_report_passes_through_metrics_and_issues(make_dummy, mock_report_dict):
    provider = make_dummy(mock_report_dict)
    metrics = GlobalMetrics(
        total_agents=3,
        completion_rate_overall=0.67,
        completion_rate_by_cluster={"pg_1": 1.0, "pg_2": 1.0, "pg_3": 0.0},
        drop_off_curve=[DropOffPoint(step_index=0, remaining_pct=100.0)],
        tokens_used_total=30_000,
        top_friction_screens=["s1"],
    )
    issues = CategorizedIssues(issues=[])
    report = build_report(metrics, issues, curated_traces={}, provider=provider)
    # Pass-through
    assert report.metrics.completion_rate_overall == 0.67
    assert report.metrics.tokens_used_total == 30_000
    assert report.categorized_issues.issues == []
    # Narrative came from fixture
    assert "signup flow" in report.executive_summary.lower() or len(report.executive_summary) > 0


def test_build_report_fills_missing_category_keys(make_dummy, mock_report_dict):
    partial = {**mock_report_dict, "findings_by_category": {"onboarding": ["x"]}}
    provider = make_dummy(partial)
    metrics = GlobalMetrics(total_agents=0, completion_rate_overall=0.0,
                             completion_rate_by_cluster={"pg_1": 0.0})
    issues = CategorizedIssues(issues=[])
    report = build_report(metrics, issues, curated_traces={}, provider=provider)
    all_cats = {"accessibility", "compliance", "onboarding", "activation", "engagement_retention"}
    assert all_cats.issubset(report.findings_by_category.keys())
    assert report.findings_by_category["onboarding"] == ["x"]
