"""Metrics accumulators.

Pure: the Runner feeds in events (arrival, decision, terminal) and this
module aggregates into the ScreenMetrics/GlobalMetrics pydantic models at
the end. No LLM calls.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Iterable

from persona_simulation.schema import (
    ActionDistribution,
    AgentPath,
    DropOffPoint,
    EmotionalState,
    GlobalMetrics,
    ScreenMetrics,
    TerminalState,
)


def _avg_emotional(states: list[EmotionalState]) -> EmotionalState:
    if not states:
        return EmotionalState(confusion=1, frustration=1, interest=1, trust=1)
    return EmotionalState(
        confusion=round(mean(s.confusion for s in states)),
        frustration=round(mean(s.frustration for s in states)),
        interest=round(mean(s.interest for s in states)),
        trust=round(mean(s.trust for s in states)),
    )


class MetricsAccumulator:
    """Stateful collector invoked by the Runner.

    Usage:
        acc = MetricsAccumulator()
        acc.on_arrival(screen_id, emotional_state)
        acc.on_decision(screen_id, decision)        # after the turn
        acc.on_terminal(screen_id, terminal_state)  # where the agent ended
        ... later ...
        global_metrics = acc.finalize(paths, tokens_used_total)
    """

    def __init__(self) -> None:
        self._arrivals: dict[str, int] = defaultdict(int)
        self._emotion_at_arrival: dict[str, list[EmotionalState]] = defaultdict(list)
        self._seconds: dict[str, list[int]] = defaultdict(list)
        self._actions: dict[str, ActionDistribution] = defaultdict(ActionDistribution)
        self._issues: dict[str, list[str]] = defaultdict(list)
        # departures[screen_id]["continued" | TerminalState]
        self._departures: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def on_arrival(self, screen_id: str, emotional_state: EmotionalState) -> None:
        self._arrivals[screen_id] += 1
        self._emotion_at_arrival[screen_id].append(emotional_state)

    def on_decision(self, screen_id: str, decision) -> None:
        self._seconds[screen_id].append(decision.estimated_seconds_on_screen)
        dist = self._actions[screen_id]
        setattr(dist, decision.action, getattr(dist, decision.action) + 1)
        for issue in decision.observed_issues:
            if issue and issue not in self._issues[screen_id]:
                self._issues[screen_id].append(issue)

    def on_departure(self, screen_id: str, kind: str) -> None:
        """`kind` is either 'continued' or a TerminalState value."""
        self._departures[screen_id][kind] += 1

    # ──────────────────────────── finalize ────────────────────────────

    def finalize(
        self,
        paths: Iterable[AgentPath],
        *,
        tokens_used_total: int,
        top_n_friction: int = 5,
    ) -> GlobalMetrics:
        paths_list = list(paths)
        per_screen: list[ScreenMetrics] = []
        for sid, n_arr in sorted(self._arrivals.items()):
            per_screen.append(
                ScreenMetrics(
                    screen_id=sid,
                    arrivals=n_arr,
                    departures=dict(self._departures.get(sid, {})),
                    avg_emotional_state_on_arrival=_avg_emotional(self._emotion_at_arrival[sid]),
                    avg_seconds=(mean(self._seconds[sid]) if self._seconds[sid] else 0.0),
                    action_distribution=self._actions[sid],
                    issues=list(self._issues[sid]),
                )
            )

        total_agents = len(paths_list)
        completions = sum(1 for p in paths_list if p.terminal_state == "complete")
        overall = (completions / total_agents) if total_agents else 0.0

        per_cluster: dict[str, list[AgentPath]] = defaultdict(list)
        for p in paths_list:
            per_cluster[p.agent.cluster_id].append(p)
        by_cluster: dict[str, float] = {}
        for cid, paths_in in per_cluster.items():
            done = sum(1 for p in paths_in if p.terminal_state == "complete")
            by_cluster[cid] = done / len(paths_in) if paths_in else 0.0

        # Drop-off curve: % of agents still alive at each step index.
        max_steps = max((len(p.steps) for p in paths_list), default=0)
        curve: list[DropOffPoint] = []
        for i in range(max_steps + 1):
            alive_at_i = sum(1 for p in paths_list if len(p.steps) > i)
            pct = (alive_at_i / total_agents * 100) if total_agents else 0.0
            curve.append(DropOffPoint(step_index=i, remaining_pct=round(pct, 2)))

        # Friction rank: by (avg frustration + share of non-'continued' departures)
        def friction_score(m: ScreenMetrics) -> float:
            frus = m.avg_emotional_state_on_arrival.frustration
            total_dep = sum(m.departures.values()) or 1
            drop_share = 1.0 - (m.departures.get("continued", 0) / total_dep)
            return frus + 5 * drop_share

        ranked = sorted(per_screen, key=friction_score, reverse=True)
        top_friction = [m.screen_id for m in ranked[:top_n_friction]]

        return GlobalMetrics(
            total_agents=total_agents,
            completion_rate_overall=round(overall, 4),
            completion_rate_by_cluster={k: round(v, 4) for k, v in by_cluster.items()},
            drop_off_curve=curve,
            tokens_used_total=tokens_used_total,
            top_friction_screens=top_friction,
            per_screen=per_screen,
        )
