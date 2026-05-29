"""Deterministic fork-decision logic.

The fork rules are pure: given one agent's decision + current simulation state,
decide whether to spawn siblings. No LLM involved — the agent's LLM output
already contains the ambiguity signal (confidence + alternative_actions).
"""
from __future__ import annotations

from persona_simulation.schema import (
    AgentDecision,
    AlternativeAction,
    ForkSpec,
    ScreenGraph,
    SimulationConfig,
)


CONFIDENCE_FORK_THRESHOLD = 3   # confidence must be <= this to consider forking


def _alternative_target_screen(
    alt: AlternativeAction, graph: ScreenGraph, current_screen_id: str
) -> str | None:
    """Resolve what next-screen this alternative would land on, if any.

    `click_element` → follow the matching transition. Any other action stays
    on the current screen (for fork-diff purposes; that's what "meaningfully
    different path" means in the spec).
    """
    if alt.action != "click_element" or alt.target_element_id is None:
        return current_screen_id
    for t in graph.transitions:
        if t.from_screen == current_screen_id and t.via_element_id == alt.target_element_id:
            return t.to_screen
    return None  # unresolved element — effectively a different "path" (a dead end)


def _primary_target_screen(
    decision: AgentDecision, graph: ScreenGraph, current_screen_id: str
) -> str | None:
    if decision.action != "click_element" or decision.target_element_id is None:
        return current_screen_id
    for t in graph.transitions:
        if t.from_screen == current_screen_id and t.via_element_id == decision.target_element_id:
            return t.to_screen
    return None


def should_fork(
    decision: AgentDecision,
    *,
    total_agents: int,
    agents_in_cluster: int,
    current_depth: int,
    parent_agent_id: str,
    graph: ScreenGraph,
    current_screen_id: str,
    config: SimulationConfig,
) -> list[ForkSpec]:
    """Return up to `forks_per_decision` ForkSpecs to spawn, or [] to skip.

    Fork when ALL:
      - confidence <= 3
      - has >=1 alternative leading to a MEANINGFULLY DIFFERENT path
        (different target screen than the primary action)
      - total_agents < max_agents_budget
      - agents_in_cluster < max_agents_per_cluster
      - current_depth < max_depth
    """
    if decision.confidence > CONFIDENCE_FORK_THRESHOLD:
        return []
    if total_agents >= config.max_agents_budget:
        return []
    if agents_in_cluster >= config.max_agents_per_cluster:
        return []
    if current_depth >= config.max_depth:
        return []
    if config.forks_per_decision <= 0:
        return []
    if not decision.alternative_actions:
        return []

    primary_target = _primary_target_screen(decision, graph, current_screen_id)
    headroom_total = config.max_agents_budget - total_agents
    headroom_cluster = config.max_agents_per_cluster - agents_in_cluster
    cap = min(config.forks_per_decision, headroom_total, headroom_cluster)

    specs: list[ForkSpec] = []
    seen_targets: set[str | None] = {primary_target}
    for i, alt in enumerate(decision.alternative_actions[:2]):
        if len(specs) >= cap:
            break
        alt_target = _alternative_target_screen(alt, graph, current_screen_id)
        if alt_target in seen_targets:
            continue  # not meaningfully different
        seen_targets.add(alt_target)
        specs.append(ForkSpec(parent_agent_id=parent_agent_id, take_alternative_index=i))
    return specs
