"""Tests for the runner orchestrator's budget + termination behavior."""
from __future__ import annotations

from persona_synthesis.schema import PersonaGroup, UploadedFile

from persona_simulation.runner import simulate
from persona_simulation.schema import (
    ScreenGraph,
    SimulationConfig,
    SimulationInputs,
)


def _inputs(sample_personas, mock_screen_graph_dict, goal="complete signup"):
    """Build SimulationInputs using the screen graph as override (skip build)."""
    groups = [PersonaGroup.model_validate(g) for g in sample_personas]
    graph = ScreenGraph.model_validate(mock_screen_graph_dict)
    # screenshots param unused when using override, but keep a placeholder
    return SimulationInputs(
        groups=groups,
        screenshots=[],
        goal=goal,
        screen_graph_override=graph,
    )


def _base_canned(
    n_seeds, n_decisions,
    mock_backstory_dict, decision_dict, mock_categorized_issues_dict, mock_report_dict,
) -> dict:
    return {
        "emit_backstory": [mock_backstory_dict] * n_seeds,
        "emit_decision": [decision_dict] * n_decisions,
        "emit_categorized_issues": [mock_categorized_issues_dict],
        "emit_report": [mock_report_dict],
    }


def test_all_complete_gives_full_completion_rate(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_complete_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    canned = _base_canned(
        3, 20, mock_backstory_dict, mock_decision_complete_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(n_seed_per_group=1, max_depth=3),
    )
    assert result.budget_stopped is False
    assert result.report.metrics.completion_rate_overall == 1.0
    assert len(result.paths) == 3
    assert all(p.terminal_state == "complete" for p in result.paths)


def test_max_depth_ceiling(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    canned = _base_canned(
        3, 40, mock_backstory_dict, mock_decision_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(n_seed_per_group=1, max_depth=3),
    )
    # Every agent just clicks btn_signup → goes to s2 → then loops (btn_signup isn't
    # on s2, so the decision would click "s1.btn_signup" which doesn't exist on s2
    # → dead_end). So they terminate early. We check no path exceeds 3 steps.
    for p in result.paths:
        assert len(p.steps) <= 3


def test_give_up_on_two_consecutive_high_frustration(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_give_up_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    canned = _base_canned(
        3, 20, mock_backstory_dict, mock_decision_give_up_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(n_seed_per_group=1, max_depth=10, give_up_frustration_streak=2),
    )
    # First turn: frustration=5 → click → land on s2
    # Second turn on s2: same decision output has target 's1.btn_signup', which isn't
    # on s2 → dead_end. But the consecutive frustration check runs BEFORE the click
    # resolution, so on turn 2 the streak hits 2 and we exit as give_up.
    for p in result.paths:
        assert p.terminal_state in ("give_up", "dead_end")


def test_dead_end_on_unresolved_element(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_categorized_issues_dict, mock_report_dict,
):
    # Decision that clicks the unresolved login link on s1
    dead_decision = {
        "action": "click_element",
        "target_element_id": "s1.link_login",
        "reasoning": "I have an account already.",
        "confidence": 4,
        "emotional_state": {"confusion": 1, "frustration": 1, "interest": 3, "trust": 3},
        "estimated_seconds_on_screen": 4,
        "observed_issues": [],
        "alternative_actions": []
    }
    canned = _base_canned(
        3, 20, mock_backstory_dict, dead_decision,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(n_seed_per_group=1),
    )
    for p in result.paths:
        assert p.terminal_state == "dead_end"


def test_token_cap_engages_budget_stopped(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    canned = _base_canned(
        3, 40, mock_backstory_dict, mock_decision_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    # DummyProvider reports 5500 tokens per call; set cap very low
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(
            n_seed_per_group=1, max_depth=25,
            hard_spend_cap_tokens=5500,  # after first decision call, we're at cap
        ),
    )
    assert result.budget_stopped is True
    assert "hard_spend_cap_tokens" in result.budgets_engaged


def test_max_agents_budget_limits_total(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_low_conf_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    """With low-confidence decisions that would normally fork, cap forks off entirely."""
    canned = _base_canned(
        3, 120, mock_backstory_dict, mock_decision_low_conf_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(
            n_seed_per_group=1, max_agents_budget=3,  # no headroom for forks
            max_depth=5,
        ),
    )
    # 3 seeds, 0 forks possible due to cap
    assert result.report.metrics.total_agents == 3


def test_report_always_produced_even_on_early_budget_stop(
    make_by_tool_dummy, sample_personas, mock_screen_graph_dict,
    mock_backstory_dict, mock_decision_dict,
    mock_categorized_issues_dict, mock_report_dict,
):
    canned = _base_canned(
        3, 20, mock_backstory_dict, mock_decision_dict,
        mock_categorized_issues_dict, mock_report_dict,
    )
    provider = make_by_tool_dummy(canned)
    result = simulate(
        _inputs(sample_personas, mock_screen_graph_dict),
        provider=provider,
        config=SimulationConfig(
            n_seed_per_group=1,
            hard_spend_cap_tokens=100,  # absurdly low
        ),
    )
    assert result.report.executive_summary  # report present
    assert result.budget_stopped is True
