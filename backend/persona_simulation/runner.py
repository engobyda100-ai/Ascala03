"""Public entrypoint: simulate()."""
from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Callable, Optional

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.schema import StreamEvent

from persona_simulation.categorize import categorize_issues
from persona_simulation.decisions import agent_decision
from persona_simulation.forking import should_fork
from persona_simulation.metrics import MetricsAccumulator
from persona_simulation.report import build_report, curate_traces
from persona_simulation.sampling import sample_seed_agents
from persona_simulation.schema import (
    AgentDecision,
    AgentPath,
    AgentStep,
    ForkSpec,
    SampledAgent,
    Screen,
    ScreenGraph,
    SimulationConfig,
    SimulationInputs,
    SimulationResult,
    TerminalState,
)
from persona_simulation.screen_graph import build_screen_graph


def _find_screen(graph: ScreenGraph, screen_id: str) -> Screen:
    for s in graph.screens:
        if s.id == screen_id:
            return s
    raise KeyError(f"screen_id {screen_id!r} not in graph")


def _resolve_transition(
    graph: ScreenGraph,
    current_screen_id: str,
    element_id: str,
) -> tuple[str | None, bool]:
    """Follow a click. Returns (next_screen_id_or_None, is_dead_end).

    - resolved transition → (to_screen, False)
    - unresolved action → (None, True)
    - element not on current screen → (None, True)  # treated as dead end
    """
    for t in graph.transitions:
        if t.from_screen == current_screen_id and t.via_element_id == element_id:
            return t.to_screen, False
    for u in graph.unresolved:
        if u.from_screen == current_screen_id and u.via_element_id == element_id:
            return None, True
    return None, True


class _LiveAgent:
    """Mutable walker state. Kept out of the pydantic schema."""

    def __init__(self, agent: SampledAgent, current_screen_id: str):
        self.agent = agent
        self.current_screen_id = current_screen_id
        self.history: list[AgentStep] = []
        self.terminal_state: TerminalState | None = None
        self.screens_visited: list[str] = [current_screen_id]
        self.fork_points: list[int] = []
        self.cumulative_seconds: int = 0
        self.tokens_used: int = 0
        self.consecutive_high_frustration: int = 0

    def to_path(self) -> AgentPath:
        return AgentPath(
            agent=self.agent,
            steps=list(self.history),
            terminal_state=self.terminal_state or "max_steps_reached",
            screens_visited=list(self.screens_visited),
            fork_points=list(self.fork_points),
            cumulative_seconds=self.cumulative_seconds,
            tokens_used=self.tokens_used,
        )


def _spawn_fork(
    parent: _LiveAgent,
    alt_index: int,
    agent_counter: "itertools.count",
    graph: ScreenGraph,
) -> _LiveAgent | None:
    """Create a sibling agent that takes the parent's alternative_action[alt_index].

    Returns None if the alternative isn't executable (e.g. a non-click alt with
    nowhere to go doesn't create a meaningfully different path).
    """
    if not parent.history:
        return None
    last_decision = parent.history[-1].decision
    if alt_index >= len(last_decision.alternative_actions):
        return None
    alt = last_decision.alternative_actions[alt_index]

    # Derive where the sibling would be after taking the alt.
    parent_screen_before_last = (
        parent.history[-2].screen_id if len(parent.history) >= 2 else parent.screens_visited[0]
    )
    # The parent was on `parent_screen_before_last` when it made the last decision;
    # by the time we spawn, parent has already advanced. Sibling takes the alt FROM
    # that same screen.
    sibling_origin = parent_screen_before_last

    if alt.action == "click_element" and alt.target_element_id:
        next_screen, dead = _resolve_transition(graph, sibling_origin, alt.target_element_id)
        if dead or next_screen is None:
            sibling_screen = sibling_origin  # will hit dead_end on its first step
        else:
            sibling_screen = next_screen
    elif alt.action == "go_back":
        # Go back one further than the parent; unknown destination → stay on origin
        sibling_screen = sibling_origin
    else:
        # scroll / give_up / complete — siblings start on origin and step next turn
        sibling_screen = sibling_origin

    seq = next(agent_counter)
    sibling = SampledAgent(
        agent_id=f"{parent.agent.agent_id}.f{seq:03d}",
        parent_agent_id=parent.agent.agent_id,
        cluster_id=parent.agent.cluster_id,
        cluster_name=parent.agent.cluster_name,
        age=parent.agent.age,
        tech_savviness=parent.agent.tech_savviness,
        patience_threshold=parent.agent.patience_threshold,
        pricing_sensitivity=parent.agent.pricing_sensitivity,
        primary_device=parent.agent.primary_device,
        group=parent.agent.group,
        personalized_backstory=parent.agent.personalized_backstory,
        rng_seed=parent.agent.rng_seed,
    )
    walker = _LiveAgent(sibling, current_screen_id=sibling_screen)
    # Inherit parent's history so the sibling has context
    walker.history = list(parent.history[:-1])  # all but the parent's last decision
    walker.cumulative_seconds = parent.cumulative_seconds
    walker.screens_visited = list(parent.screens_visited[:-1]) + [sibling_screen]
    return walker


def _apply_decision(
    walker: _LiveAgent,
    decision: AgentDecision,
    graph: ScreenGraph,
    *,
    give_up_frustration_streak: int,
    max_depth: int,
) -> str:
    """Mutate walker state; return a departure-kind string for metrics.

    Returns one of: "continued", "complete", "give_up", "dead_end",
    "max_steps_reached".
    """
    step = AgentStep(
        order=len(walker.history) + 1,
        screen_id=walker.current_screen_id,
        decision=decision,
        was_fork_point=False,  # Runner sets this true when actually forking
        elapsed_seconds_total=walker.cumulative_seconds + decision.estimated_seconds_on_screen,
    )
    walker.history.append(step)
    walker.cumulative_seconds = step.elapsed_seconds_total

    # Track consecutive high-frustration for give_up detection
    if decision.emotional_state.frustration >= 5:
        walker.consecutive_high_frustration += 1
    else:
        walker.consecutive_high_frustration = 0

    # Terminal from explicit action
    if decision.action == "complete":
        walker.terminal_state = "complete"
        return "complete"
    if decision.action == "give_up":
        walker.terminal_state = "give_up"
        return "give_up"

    # Implicit give_up: frustration=5 twice in a row
    if walker.consecutive_high_frustration >= give_up_frustration_streak:
        walker.terminal_state = "give_up"
        return "give_up"

    # Click resolution
    if decision.action == "click_element":
        assert decision.target_element_id is not None
        next_screen, dead = _resolve_transition(
            graph, walker.current_screen_id, decision.target_element_id,
        )
        if dead:
            walker.terminal_state = "dead_end"
            return "dead_end"
        walker.current_screen_id = next_screen  # type: ignore[assignment]
        walker.screens_visited.append(next_screen)  # type: ignore[arg-type]
    elif decision.action == "go_back":
        if len(walker.screens_visited) >= 2:
            walker.current_screen_id = walker.screens_visited[-2]
            walker.screens_visited.append(walker.current_screen_id)
        # else: nowhere to go back; agent stays put (will likely escalate frustration)

    # scroll stays on the current screen — nothing to do

    # Depth ceiling
    if len(walker.history) >= max_depth:
        walker.terminal_state = "max_steps_reached"
        return "max_steps_reached"

    return "continued"


def simulate(
    inputs: SimulationInputs,
    *,
    provider: Optional[LLMProvider] = None,
    config: Optional[SimulationConfig] = None,
    on_event: Optional[Callable[[StreamEvent], None]] = None,
) -> SimulationResult:
    """Run the full simulation pipeline.

    Data flow:
      1. Build the ScreenGraph from screenshots (or use the override).
      2. Sample seed agents (1 LLM call per seed × groups).
      3. Walk: per live agent, call agent_decision() each turn, apply the
         action, update metrics, decide whether to fork (pure code).
      4. Enforce budget caps: stop spawning new forks once any cap engages;
         let alive agents finish their current turn; then break.
      5. Categorize all observed_issues via one post-sim LLM call.
      6. Curate traces (heuristic) and call build_report for the narrative.

    Returns SynthesisResult with budget_stopped + budgets_engaged surfaced.
    """
    if provider is None:
        from persona_synthesis.llm.anthropic_client import AnthropicProvider
        provider = AnthropicProvider()

    cfg = config or SimulationConfig()
    emit = on_event or (lambda _ev: None)

    # Build screenshot lookup once (needed for per-turn image blocks)
    screenshots_by_name = {s.name: s for s in inputs.screenshots}

    # 1. Screen graph
    if inputs.screen_graph_override is not None:
        graph = inputs.screen_graph_override
    else:
        graph = build_screen_graph(
            inputs.screenshots, goal=inputs.goal, provider=provider,
        )
    emit(StreamEvent(kind="summary_done", data={"screens": len(graph.screens)}))

    # 2. Seed agents
    seeds = sample_seed_agents(
        inputs.groups,
        n_per_group=cfg.n_seed_per_group,
        provider=provider,
        rng_seed=cfg.rng_seed,
    )

    # 3+4. Walk with budget enforcement
    acc = MetricsAccumulator()
    completed_paths: list[AgentPath] = []
    live: list[_LiveAgent] = []
    for s in seeds:
        live.append(_LiveAgent(s, current_screen_id=graph.entry_screen_id))

    tokens_total = 0
    agents_in_cluster: dict[str, int] = defaultdict(int)
    for w in live:
        agents_in_cluster[w.agent.cluster_id] += 1
    total_agents = len(live)

    budgets_engaged: list[str] = []
    budget_stopped = False
    fork_counter = itertools.count(1)
    FORK_BUDGET_NAME = "hard_spend_cap_tokens"

    # For arrival metrics we need the FIRST emotional state at a screen for each
    # agent. We'll record arrival at the start of each walker's turn using the
    # decision's emotional_state (proxy — the emotional state the persona felt
    # on arriving at this screen).

    while live:
        next_live: list[_LiveAgent] = []
        for walker in live:
            current_screen = _find_screen(graph, walker.current_screen_id)

            # Per-turn LLM call
            decision, tokens = agent_decision(
                walker.agent,
                current_screen,
                walker.history,
                goal=inputs.goal,
                graph=graph,
                provider=provider,
                screenshots=screenshots_by_name,
                history_window=cfg.history_window_k,
            )
            walker.tokens_used += tokens
            tokens_total += tokens

            # Metrics: arrival + decision
            acc.on_arrival(walker.current_screen_id, decision.emotional_state)
            acc.on_decision(walker.current_screen_id, decision)

            # Apply; determine departure kind for metrics
            departure = _apply_decision(
                walker, decision, graph,
                give_up_frustration_streak=cfg.give_up_frustration_streak,
                max_depth=cfg.max_depth,
            )

            # Record the departure from the screen the agent was on WHEN they decided.
            # walker.history[-1].screen_id is correct (we appended the step above).
            acc.on_departure(walker.history[-1].screen_id, departure)

            if departure != "continued":
                completed_paths.append(walker.to_path())
                continue

            # Fork decision (pure, no LLM)
            if not budget_stopped:
                forks = should_fork(
                    decision,
                    total_agents=total_agents,
                    agents_in_cluster=agents_in_cluster[walker.agent.cluster_id],
                    current_depth=len(walker.history),
                    parent_agent_id=walker.agent.agent_id,
                    graph=graph,
                    current_screen_id=walker.history[-1].screen_id,
                    config=cfg,
                )
                for fs in forks:
                    sibling = _spawn_fork(walker, fs.take_alternative_index, fork_counter, graph)
                    if sibling is None:
                        continue
                    total_agents += 1
                    agents_in_cluster[sibling.agent.cluster_id] += 1
                    walker.fork_points.append(len(walker.history))
                    walker.history[-1].was_fork_point = True
                    next_live.append(sibling)

            # Token cap check — do this AFTER updating state so current turn counts.
            if tokens_total >= cfg.hard_spend_cap_tokens and not budget_stopped:
                budget_stopped = True
                if FORK_BUDGET_NAME not in budgets_engaged:
                    budgets_engaged.append(FORK_BUDGET_NAME)

            next_live.append(walker)

        # If budget stopped and we're past the current sweep, finalize remaining alive
        if budget_stopped and next_live:
            for w in next_live:
                w.terminal_state = "budget_stopped"
                acc.on_departure(w.current_screen_id, "budget_stopped")
                completed_paths.append(w.to_path())
            live = []
            break

        live = next_live

    # Detect other engaged caps for the report (informational)
    if total_agents >= cfg.max_agents_budget and "max_agents_budget" not in budgets_engaged:
        budgets_engaged.append("max_agents_budget")

    # 5. Categorize issues
    observed: list[str] = []
    for p in completed_paths:
        for step in p.steps:
            observed.extend(step.decision.observed_issues)
    issues = categorize_issues(observed, provider=provider)

    # Finalize metrics
    metrics = acc.finalize(completed_paths, tokens_used_total=tokens_total)

    # 6. Curate traces + build report
    curated = curate_traces(completed_paths)
    report = build_report(metrics, issues, curated, provider=provider)

    emit(StreamEvent(kind="done", data=None))

    return SimulationResult(
        screen_graph=graph,
        paths=completed_paths,
        report=report,
        budget_stopped=budget_stopped,
        budgets_engaged=budgets_engaged,
    )
