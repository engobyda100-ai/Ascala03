"""Tests for agent_decision()."""
from __future__ import annotations

import pytest

from persona_synthesis.schema import PersonaGroup

from persona_simulation.decisions import agent_decision
from persona_simulation.schema import (
    AgentDecision,
    AgentStep,
    EmotionalState,
    SampledAgent,
)


def _agent(sample_personas) -> SampledAgent:
    group = PersonaGroup.model_validate(sample_personas[0])
    return SampledAgent(
        agent_id="a_test_001",
        cluster_id=group.id,
        cluster_name=group.name,
        age=30,
        tech_savviness=4,
        patience_threshold="medium",
        pricing_sensitivity=3,
        primary_device="desktop",
        group=group,
        personalized_backstory="A test agent.",
        rng_seed=0,
    )


def _graph_and_screen(mock_screen_graph_dict):
    from persona_simulation.schema import ScreenGraph
    g = ScreenGraph.model_validate(mock_screen_graph_dict)
    return g, g.screens[0]


def test_click_element_parses(make_dummy, mock_decision_dict, mock_screen_graph_dict, sample_personas):
    provider = make_dummy(mock_decision_dict)
    graph, screen = _graph_and_screen(mock_screen_graph_dict)
    decision, tokens = agent_decision(
        _agent(sample_personas), screen, history=[],
        goal="complete signup", graph=graph, provider=provider,
    )
    assert isinstance(decision, AgentDecision)
    assert decision.action == "click_element"
    assert decision.target_element_id == "s1.btn_signup"
    assert tokens > 0


def test_click_missing_target_triggers_retry(make_dummy, mock_decision_dict, mock_screen_graph_dict, sample_personas):
    bad = {**mock_decision_dict, "target_element_id": None}
    provider = make_dummy(bad, mock_decision_dict)
    graph, screen = _graph_and_screen(mock_screen_graph_dict)
    decision, _ = agent_decision(
        _agent(sample_personas), screen, history=[],
        goal=None, graph=graph, provider=provider,
    )
    assert decision.target_element_id == "s1.btn_signup"
    assert len(provider.calls) == 2


def test_history_window_only_shows_last_k(make_dummy, mock_decision_dict, mock_screen_graph_dict, sample_personas):
    provider = make_dummy(mock_decision_dict)
    graph, screen = _graph_and_screen(mock_screen_graph_dict)
    # Build a fake 10-step history
    history = []
    for i in range(1, 11):
        history.append(AgentStep(
            order=i, screen_id=f"s{((i-1) % 2) + 1}",
            decision=AgentDecision(
                action="click_element", target_element_id="s1.btn_signup",
                reasoning=f"turn {i}", confidence=3,
                emotional_state=EmotionalState(confusion=1, frustration=1, interest=3, trust=3),
                estimated_seconds_on_screen=5,
            ),
            elapsed_seconds_total=5 * i,
        ))
    agent_decision(
        _agent(sample_personas), screen, history,
        goal=None, graph=graph, provider=provider, history_window=5,
    )
    # The composite text should mention last 5 turns only
    content_text = next(
        c["text"] for c in provider.calls[0]["messages"][0]["content"] if c.get("type") == "text"
    )
    assert "step 6" in content_text and "step 10" in content_text
    assert "step 1:" not in content_text
    assert "step 5:" not in content_text


def test_tokens_surfaced_from_provider(make_dummy, mock_decision_dict, mock_screen_graph_dict, sample_personas):
    provider = make_dummy(mock_decision_dict)
    graph, screen = _graph_and_screen(mock_screen_graph_dict)
    _, tokens = agent_decision(
        _agent(sample_personas), screen, history=[],
        goal=None, graph=graph, provider=provider,
    )
    # Our DummyProvider stores input+output = 5500 by default
    assert tokens == 5500


def test_observed_issues_forwarded(make_dummy, mock_decision_low_conf_dict, mock_screen_graph_dict, sample_personas):
    provider = make_dummy(mock_decision_low_conf_dict)
    graph, screen = _graph_and_screen(mock_screen_graph_dict)
    decision, _ = agent_decision(
        _agent(sample_personas), screen, history=[],
        goal=None, graph=graph, provider=provider,
    )
    assert decision.observed_issues
    assert "Two CTAs compete" in decision.observed_issues[0]
