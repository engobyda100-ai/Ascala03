"""Pure tests for should_fork — no LLM, no DummyProvider."""
from __future__ import annotations

import pytest

from persona_simulation.forking import should_fork
from persona_simulation.schema import (
    AgentDecision,
    AlternativeAction,
    EmotionalState,
    InteractiveElement,
    Screen,
    ScreenGraph,
    SimulationConfig,
    Transition,
    UnresolvedAction,
)


# ────────────── helpers ──────────────

def _graph() -> ScreenGraph:
    return ScreenGraph(
        screens=[
            Screen(
                id="s1", source_filename="s1.png", inferred_purpose="landing",
                copy=[], elements=[
                    InteractiveElement(id="s1.btn_a", kind="button", label="A"),
                    InteractiveElement(id="s1.btn_b", kind="button", label="B"),
                    InteractiveElement(id="s1.btn_c", kind="button", label="C"),
                ],
            ),
            Screen(id="s2", source_filename="s2.png", inferred_purpose="a",
                   copy=[], elements=[]),
            Screen(id="s3", source_filename="s3.png", inferred_purpose="b",
                   copy=[], elements=[]),
        ],
        transitions=[
            Transition(from_screen="s1", via_element_id="s1.btn_a", to_screen="s2", confidence=5),
            Transition(from_screen="s1", via_element_id="s1.btn_b", to_screen="s3", confidence=5),
            Transition(from_screen="s1", via_element_id="s1.btn_c", to_screen="s2", confidence=3),
        ],
        unresolved=[],
        entry_screen_id="s1",
    )


def _decision(
    *,
    action="click_element", target="s1.btn_a", confidence=3,
    alts: list[AlternativeAction] | None = None,
) -> AgentDecision:
    return AgentDecision(
        action=action,
        target_element_id=target if action == "click_element" else None,
        reasoning="r",
        confidence=confidence,
        emotional_state=EmotionalState(confusion=1, frustration=1, interest=3, trust=3),
        estimated_seconds_on_screen=5,
        observed_issues=[],
        alternative_actions=alts or [],
    )


# ────────────── tests ──────────────

def test_confidence_low_with_distinct_alts_forks_twice():
    dec = _decision(
        target="s1.btn_a",
        alts=[
            AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b"),
            AlternativeAction(action="click_element", target_element_id="s1.btn_c", reasoning="c"),
        ],
    )
    # btn_a → s2, btn_b → s3 (distinct), btn_c → s2 (same as btn_a)
    # So only the btn_b alt is "meaningfully different" and should fork once.
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=SimulationConfig(),
    )
    assert len(forks) == 1
    assert forks[0].take_alternative_index == 0


def test_high_confidence_no_fork():
    dec = _decision(
        confidence=4,
        alts=[AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b")],
    )
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=SimulationConfig(),
    )
    assert forks == []


def test_alts_same_target_no_fork():
    dec = _decision(
        target="s1.btn_a",
        alts=[AlternativeAction(action="click_element", target_element_id="s1.btn_c", reasoning="c")],
    )
    # btn_a → s2, btn_c → s2 (same) → not meaningfully different
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=SimulationConfig(),
    )
    assert forks == []


def test_total_agents_at_cap_no_fork():
    dec = _decision(
        alts=[AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b")],
    )
    cfg = SimulationConfig(max_agents_budget=3)
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=cfg,
    )
    assert forks == []


def test_cluster_cap_no_fork():
    dec = _decision(
        alts=[AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b")],
    )
    cfg = SimulationConfig(max_agents_per_cluster=2)
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=2, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=cfg,
    )
    assert forks == []


def test_depth_at_max_no_fork():
    dec = _decision(
        alts=[AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b")],
    )
    cfg = SimulationConfig(max_depth=5)
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=5,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=cfg,
    )
    assert forks == []


def test_no_alternatives_no_fork():
    dec = _decision(alts=[])
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=_graph(), current_screen_id="s1",
        config=SimulationConfig(),
    )
    assert forks == []


def test_headroom_caps_number_of_forks():
    """When only 1 slot left in the total budget, fork at most 1 even if 2 alts differ."""
    g = _graph()
    dec = _decision(
        target="s1.btn_a",
        alts=[
            AlternativeAction(action="click_element", target_element_id="s1.btn_b", reasoning="b"),
            # This one goes to an unresolved element — counts as "different target" (None)
            AlternativeAction(action="click_element", target_element_id="s1.nonexistent", reasoning="x"),
        ],
    )
    cfg = SimulationConfig(max_agents_budget=4, forks_per_decision=2)
    forks = should_fork(
        dec, total_agents=3, agents_in_cluster=1, current_depth=1,
        parent_agent_id="a1", graph=g, current_screen_id="s1",
        config=cfg,
    )
    # 4 - 3 = 1 slot; and forks_per_decision=2 → capped to 1
    assert len(forks) == 1
