"""Deterministic key-stat computation per test type.

Each test type produces exactly 3 Stats. All formulas live here, all numbers
come from the SimulationResult — no LLM.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Iterable, Optional

from persona_simulation.schema import AgentPath, SimulationResult

from persona_report.filters import (
    A11Y_KEYWORDS,
    CORE_SCREEN_KEYWORDS,
    FilteredSlice,
    HABIT_MARKER_PATTERNS,
    SWITCHING_COST_PATTERNS,
    _has_compliance_exposure,
    _screens_matching_purpose,
    agent_expressed_switching_cost,
    agent_touched_habit_marker,
    score_return_likelihood,
)
from persona_report.schema import Sentiment, Stat


# ──────────────────────────── Helpers ────────────────────────────

def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "0%"
    return f"{round(100 * num / denom)}%"


def _pct_value(num: int, denom: int) -> float:
    if denom == 0:
        return 0.0
    return 100 * num / denom


def _agent_observed_a11y(path: AgentPath) -> bool:
    for step in path.steps:
        for issue in step.decision.observed_issues:
            if A11Y_KEYWORDS.search(issue):
                return True
    return False


def _agents_per_screen_a11y(slice_: FilteredSlice) -> dict[str, int]:
    """Count agents who flagged an a11y issue on each screen."""
    out: dict[str, int] = defaultdict(int)
    for path in slice_.paths:
        for step in path.steps:
            if any(A11Y_KEYWORDS.search(i) for i in step.decision.observed_issues):
                out[step.screen_id] += 1
    return out


def _sentiment_for_pct(value_pct: float, *, bad_above: float, good_below: Optional[float] = None) -> Sentiment:
    if value_pct > bad_above:
        return "negative"
    if good_below is not None and value_pct < good_below:
        return "positive"
    return "neutral"


# ──────────────────────────── Accessibility ────────────────────────────

def stats_accessibility(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    n_total = len(sim.paths)
    flaggers = sum(1 for p in sim.paths if _agent_observed_a11y(p))
    flagger_pct = _pct_value(flaggers, n_total)

    per_screen = _agents_per_screen_a11y(slice_)
    if per_screen:
        worst_screen = max(per_screen.items(), key=lambda kv: kv[1])
        worst_label = worst_screen[0]
        worst_count = worst_screen[1]
    else:
        worst_label, worst_count = "—", 0

    affected_clusters = {p.agent.cluster_id for p in sim.paths if _agent_observed_a11y(p)}
    total_clusters = {p.agent.cluster_id for p in sim.paths}

    return [
        Stat(
            value=_pct(flaggers, n_total),
            label="agents who flagged an accessibility issue",
            sentiment=_sentiment_for_pct(flagger_pct, bad_above=15.0, good_below=5.0),
        ),
        Stat(
            value=worst_label,
            label="most-flagged screen",
            sentiment="negative" if worst_count >= 3 else "neutral",
        ),
        Stat(
            value=f"{len(affected_clusters)}/{len(total_clusters)}",
            label="clusters affected",
            sentiment="negative" if len(affected_clusters) * 2 >= len(total_clusters) and len(affected_clusters) > 0 else "neutral",
        ),
    ]


# ──────────────────────────── Compliance ────────────────────────────

def stats_compliance(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    flaggers = sum(
        1 for p in sim.paths
        for step in p.steps
        for obs in step.decision.observed_issues
        if "complian" in obs.lower() or "consent" in obs.lower() or "privacy" in obs.lower()
    )
    # Dedupe per-agent (an agent counts once even if they flagged multiple times)
    flagger_agents = sum(
        1 for p in sim.paths
        if any(
            "complian" in obs.lower() or "consent" in obs.lower() or "privacy" in obs.lower()
            for step in p.steps for obs in step.decision.observed_issues
        )
    )
    n_total = len(sim.paths)

    high_exposure_bailed = sum(
        1 for p in slice_.paths
        if _has_compliance_exposure(p.agent.group)
        and p.terminal_state in {"give_up", "dead_end"}
    )

    n_touchpoints = len(slice_.screen_ids) or 0
    # touchpoints with drop-off: any agent terminated as drop on these screens
    drops_on_screens: set[str] = set()
    for sid in slice_.screen_ids:
        for p in sim.paths:
            if p.terminal_state in {"give_up", "dead_end"}:
                if (p.steps and p.steps[-1].screen_id == sid) or (
                    p.screens_visited and p.screens_visited[-1] == sid
                ):
                    drops_on_screens.add(sid)
    n_drops = len(drops_on_screens)

    return [
        Stat(
            value=_pct(flagger_agents, n_total),
            label="agents who flagged a compliance concern",
            sentiment=_sentiment_for_pct(_pct_value(flagger_agents, n_total), bad_above=10.0, good_below=2.0),
        ),
        Stat(
            value=str(high_exposure_bailed),
            label="high-exposure agents who bailed",
            sentiment="negative" if high_exposure_bailed >= 1 else "positive",
        ),
        Stat(
            value=f"{n_drops}/{n_touchpoints}" if n_touchpoints > 0 else "0/0",
            label="compliance touchpoints with drop-off",
            sentiment="negative" if n_drops > 0 else "positive",
        ),
    ]


# ──────────────────────────── Onboarding ────────────────────────────

ONBOARDING_WINDOW = 5


def _onboarding_completed(path: AgentPath) -> bool:
    if path.terminal_state == "complete":
        return len(path.steps) <= ONBOARDING_WINDOW
    return False


def _time_to_first_value(path: AgentPath, core_screens: set[str]) -> Optional[int]:
    """Cumulative seconds at the first arrival on any core screen, or None."""
    if not core_screens:
        # If no core screens detected, treat reaching `complete` as TTFV
        if path.terminal_state == "complete":
            return path.cumulative_seconds
        return None
    cumulative = 0
    for step in path.steps:
        cumulative = step.elapsed_seconds_total
        if step.screen_id in core_screens:
            return cumulative
    return None


def stats_onboarding(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    n_total = len(sim.paths)
    completed = sum(1 for p in sim.paths if _onboarding_completed(p))
    completed_pct = _pct_value(completed, n_total)
    completed_sentiment: Sentiment = (
        "positive" if completed_pct > 60 else
        "negative" if completed_pct < 30 else "neutral"
    )

    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))
    ttfv_values: list[int] = []
    for p in sim.paths:
        v = _time_to_first_value(p, core_screens)
        if v is not None:
            ttfv_values.append(v)
    median_ttfv = int(median(ttfv_values)) if ttfv_values else 0
    ttfv_sentiment: Sentiment = (
        "positive" if 0 < median_ttfv < 90 else
        "negative" if median_ttfv > 300 else
        "neutral" if median_ttfv > 0 else "neutral"
    )

    # Biggest drop-off step within the onboarding window
    arrivals_by_step: list[int] = [0] * (ONBOARDING_WINDOW + 1)
    for p in sim.paths:
        for i in range(min(len(p.steps), ONBOARDING_WINDOW + 1)):
            arrivals_by_step[i] += 1
    drops = []
    for i in range(len(arrivals_by_step) - 1):
        if arrivals_by_step[i] == 0:
            continue
        pct = 100 * (arrivals_by_step[i] - arrivals_by_step[i + 1]) / arrivals_by_step[i]
        drops.append((i, pct))
    if drops:
        biggest_step, biggest_pct = max(drops, key=lambda kv: kv[1])
        biggest_label = f"step {biggest_step + 1}"
        biggest_sentiment: Sentiment = "negative" if biggest_pct > 30 else "neutral"
    else:
        biggest_label, biggest_sentiment = "—", "neutral"

    return [
        Stat(
            value=_pct(completed, n_total),
            label="completed onboarding window",
            sentiment=completed_sentiment,
        ),
        Stat(
            value=f"{median_ttfv}s" if ttfv_values else "—",
            label="median time to first value",
            sentiment=ttfv_sentiment,
        ),
        Stat(
            value=biggest_label,
            label="biggest drop-off step",
            sentiment=biggest_sentiment,
        ),
    ]


# ──────────────────────────── Activation ────────────────────────────

def stats_activation(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    n_total = len(sim.paths)
    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))

    activated = sum(
        1 for p in sim.paths
        if p.terminal_state == "complete"
        or any(s.screen_id in core_screens for s in p.steps)
    )
    activated_pct = _pct_value(activated, n_total)
    activated_sentiment: Sentiment = (
        "positive" if activated_pct > 60 else
        "negative" if activated_pct < 30 else "neutral"
    )

    aha_times: list[int] = []
    for p in sim.paths:
        for step in p.steps:
            if step.screen_id in core_screens:
                aha_times.append(step.elapsed_seconds_total)
                break
    median_aha = int(median(aha_times)) if aha_times else 0
    aha_sentiment: Sentiment = (
        "positive" if 0 < median_aha < 60 else
        "negative" if median_aha > 240 else
        "neutral"
    )

    high_motiv_bounced = 0
    for p in sim.paths:
        if (
            p.agent.group.testing_postures.activation.motivation_level == "high"
            and p.terminal_state in {"give_up", "dead_end"}
        ):
            high_motiv_bounced += 1
    bounced_pct = _pct_value(high_motiv_bounced, n_total)
    bounced_sentiment: Sentiment = "negative" if bounced_pct > 10 else "neutral"

    return [
        Stat(
            value=_pct(activated, n_total),
            label="activation rate",
            sentiment=activated_sentiment,
        ),
        Stat(
            value=f"{median_aha}s" if aha_times else "—",
            label="median time to aha moment",
            sentiment=aha_sentiment,
        ),
        Stat(
            value=_pct(high_motiv_bounced, n_total),
            label="high-motivation agents who bounced",
            sentiment=bounced_sentiment,
        ),
    ]


# ──────────────────────────── Engagement ────────────────────────────

def stats_engagement(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    if not slice_.paths:
        return [
            Stat(value="0", label="average unique screens visited", sentiment="neutral"),
            Stat(value="—", label="average interest score", sentiment="neutral"),
            Stat(value="0%", label="deep explorers", sentiment="neutral"),
        ]
    total_screens = len(sim.screen_graph.screens)

    avg_unique = sum(len(set(p.screens_visited)) for p in slice_.paths) / len(slice_.paths)

    interest_values: list[int] = []
    for p in slice_.paths:
        for step in p.steps:
            interest_values.append(step.decision.emotional_state.interest)
    avg_interest = sum(interest_values) / len(interest_values) if interest_values else 0.0

    deep_explorers = 0
    if total_screens > 0:
        deep_explorers = sum(
            1 for p in slice_.paths
            if len(set(p.screens_visited)) >= total_screens / 2
        )
    deep_pct = _pct_value(deep_explorers, len(slice_.paths))

    interest_sentiment: Sentiment = (
        "positive" if avg_interest >= 4 else
        "negative" if avg_interest < 3 else "neutral"
    )
    unique_sentiment: Sentiment = (
        "positive"
        if total_screens > 0 and avg_unique > 0.6 * total_screens
        else "neutral"
    )

    return [
        Stat(
            value=f"{avg_unique:.1f}",
            label="average unique screens visited",
            sentiment=unique_sentiment,
        ),
        Stat(
            value=f"{avg_interest:.1f}/5" if interest_values else "—",
            label="average interest score",
            sentiment=interest_sentiment,
        ),
        Stat(
            value=_pct(deep_explorers, len(slice_.paths)),
            label="deep explorers",
            sentiment="positive" if deep_pct > 40 else "neutral",
        ),
    ]


# ──────────────────────────── Retention (signals only) ────────────────────────────

def stats_retention(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    n_total = len(sim.paths)
    with_signal = sum(1 for p in sim.paths if score_return_likelihood(p) > 0)
    sig_pct = _pct_value(with_signal, n_total)
    sig_sentiment: Sentiment = (
        "positive" if sig_pct > 50 else
        "negative" if sig_pct < 20 else "neutral"
    )

    habit_marker_clicks = 0
    for p in sim.paths:
        for step in p.steps:
            elem = step.decision.target_element_id or ""
            if HABIT_MARKER_PATTERNS.search(elem):
                habit_marker_clicks += 1

    switching_mentions = sum(1 for p in sim.paths if agent_expressed_switching_cost(p))

    return [
        Stat(
            value=_pct(with_signal, n_total),
            label="agents with return-intent signal",
            context="predictive — derived from agent reasoning",
            sentiment=sig_sentiment,
        ),
        Stat(
            value=str(habit_marker_clicks),
            label="habit-marker clicks",
            context="predictive — based on saved/subscribed/bookmarked actions",
            sentiment="positive" if habit_marker_clicks > 0 else "neutral",
        ),
        Stat(
            value=_pct(switching_mentions, n_total),
            label="switching-cost mentions",
            context="predictive — agents naming a current alternative",
            sentiment="neutral",
        ),
    ]


# ──────────────────────────── Dispatch ────────────────────────────

STATS_BY_TEST_TYPE = {
    "accessibility": stats_accessibility,
    "compliance": stats_compliance,
    "onboarding": stats_onboarding,
    "activation": stats_activation,
    "engagement": stats_engagement,
    "retention": stats_retention,
}


def compute(slice_: FilteredSlice, sim: SimulationResult) -> list[Stat]:
    fn = STATS_BY_TEST_TYPE.get(slice_.test_type)
    if fn is None:
        raise ValueError(f"Unknown test_type: {slice_.test_type!r}")
    out = fn(slice_, sim)
    if len(out) != 3:
        raise RuntimeError(
            f"stats.{slice_.test_type} returned {len(out)} stats, expected 3"
        )
    return out
