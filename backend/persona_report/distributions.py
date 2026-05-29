"""Pure builders for each chart_type.

Each `build_*` returns a PersonaDistribution with axes + dots + annotations.
No LLM. Empty distributions still render (with `empty_state` annotation),
per PLAN.md §10(a)/(b).
"""
from __future__ import annotations

from collections import defaultdict

from persona_simulation.schema import AgentPath, SimulationResult

from persona_report.filters import (
    A11Y_KEYWORDS,
    CORE_SCREEN_KEYWORDS,
    COMPLIANCE_PURPOSE_KEYWORDS,
    FilteredSlice,
    HABIT_MARKER_PATTERNS,
    SWITCHING_COST_PATTERNS,
    _has_compliance_exposure,
    _screens_matching_purpose,
    agent_expressed_switching_cost,
    agent_touched_habit_marker,
    score_return_likelihood,
)
from persona_report.schema import (
    AxisDef,
    Dot,
    DotAnnotation,
    EmotionalAverage,
    PersonaDistribution,
    Trajectory,
    TrajectoryCell,
)


# ──────────────────────────── helpers ────────────────────────────

ONBOARDING_WINDOW = 5


def _empty_state_annotation(text: str = "No agents matched this distribution.") -> DotAnnotation:
    return DotAnnotation(type="empty_state", text=text)


def _accessibility_need_level(group) -> int:
    """0–5 score derived from a11y posture."""
    pos = group.testing_postures.accessibility
    score = 0
    if pos.vision != "full":
        score += 1
    if pos.motor != "full":
        score += 1
    if pos.hearing != "full":
        score += 1
    score += round(pos.screen_reader_likelihood / 25)  # 0..4
    return min(score, 5)


def _agent_friction_score(path: AgentPath) -> float:
    """0–10: average of (confusion + frustration) across all steps."""
    if not path.steps:
        return 0.0
    total = 0.0
    for step in path.steps:
        e = step.decision.emotional_state
        total += e.confusion + e.frustration
    return total / len(path.steps)


def _n_a11y_issues_for_agent(path: AgentPath) -> int:
    n = 0
    for step in path.steps:
        for issue in step.decision.observed_issues:
            if A11Y_KEYWORDS.search(issue):
                n += 1
    return n


def _activation_outcome(path: AgentPath, core_screens: set[str]) -> str:
    if path.terminal_state == "complete":
        return "activated"
    if any(s.screen_id in core_screens for s in path.steps):
        return "partial"
    return "bounced"


def _has_invite_action(path: AgentPath) -> int:
    for step in path.steps:
        elem = step.decision.target_element_id or ""
        if any(token in elem.lower() for token in ("invite", "team", "add_member")):
            return 1
    return 0


def _has_settings_action(path: AgentPath) -> int:
    for step in path.steps:
        elem = step.decision.target_element_id or ""
        if any(token in elem.lower() for token in ("settings", "profile", "preferences", "config")):
            return 1
    return 0


def _used_core_feature(path: AgentPath, core_screens: set[str]) -> int:
    if not core_screens:
        return 0
    count = sum(1 for s in path.steps if s.screen_id in core_screens)
    return 1 if count > 1 else 0


# ──────────────────────────── Accessibility distributions ────────────────────────────

def build_a11y_scatter(slice_: FilteredSlice, sim: SimulationResult) -> PersonaDistribution:
    dots: list[Dot] = []
    for p in sim.paths:
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=_accessibility_need_level(p.agent.group),
                y=round(_agent_friction_score(p), 2),
                meta={"terminal_state": p.terminal_state},
            )
        )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="a11y-scatter",
        title="Accessibility need vs. friction",
        description="Each dot is one agent. X = inferred accessibility need level (0–5); Y = average confusion + frustration across their walk.",
        chart_type="scatter",
        scope="all_clusters",
        axes={
            "x": AxisDef(label="Accessibility need", min=0, max=5),
            "y": AxisDef(label="Friction score", min=0, max=10),
        },
        dots=dots,
        annotations=annotations,
    )


def build_a11y_dot_grid(slice_: FilteredSlice, sim: SimulationResult) -> PersonaDistribution:
    issue_severity_by_screen: dict[str, str] = {}
    for issue in slice_.issues:
        for sid in issue.affected_screens:
            # Promote to most severe seen so far
            cur = issue_severity_by_screen.get(sid, "low")
            order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if order.get(issue.severity, 0) > order.get(cur, 0):
                issue_severity_by_screen[sid] = issue.severity

    dots: list[Dot] = []
    for p in sim.paths:
        for sid in p.screens_visited:
            severity = issue_severity_by_screen.get(sid, "none")
            agent_flagged = any(
                A11Y_KEYWORDS.search(issue)
                for step in p.steps if step.screen_id == sid
                for issue in step.decision.observed_issues
            )
            if severity == "none" and not agent_flagged:
                # don't fill the grid with empty cells; only emit dots where there's signal
                continue
            dots.append(
                Dot(
                    agent_id=p.agent.agent_id,
                    cluster_id=p.agent.cluster_id,
                    x=sid,
                    y=p.agent.agent_id,
                    meta={
                        "severity": severity,
                        "agent_flagged": agent_flagged,
                    },
                )
            )

    # Empty-state annotations per cluster with zero relevant agents
    annotations: list[DotAnnotation] = []
    cluster_dot_counts: dict[str, int] = defaultdict(int)
    for d in dots:
        cluster_dot_counts[d.cluster_id] += 1
    for cid in slice_.cluster_counts:
        if cluster_dot_counts.get(cid, 0) == 0:
            annotations.append(
                DotAnnotation(
                    type="empty_state",
                    text=f"No accessibility signals for cluster {cid}.",
                    position={"cluster_id": cid},
                )
            )
    if not dots and not annotations:
        annotations.append(_empty_state_annotation())

    return PersonaDistribution(
        id="a11y-dot-grid",
        title="Per-screen accessibility signals",
        description="Rows are agents, columns are screens. Each dot marks a screen where an agent flagged an accessibility issue or where a categorized accessibility issue exists.",
        chart_type="dot_grid",
        scope="per_cluster",
        axes={
            "x": AxisDef(label="Screen"),
            "y": AxisDef(label="Agent"),
        },
        dots=dots,
        annotations=annotations,
    )


def build_a11y_beeswarm(slice_: FilteredSlice, sim: SimulationResult) -> PersonaDistribution:
    dots = [
        Dot(
            agent_id=p.agent.agent_id,
            cluster_id=p.agent.cluster_id,
            x=_n_a11y_issues_for_agent(p),
            meta={"cluster_name": p.agent.cluster_name},
        )
        for p in sim.paths
    ]
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="a11y-beeswarm",
        title="Accessibility issues per agent",
        description="Distribution of accessibility issues flagged per agent, swarmed by cluster.",
        chart_type="beeswarm",
        scope="all_clusters",
        axes={"x": AxisDef(label="Issues flagged per agent", min=0)},
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Compliance distributions ────────────────────────────

REGULATIONS = ["GDPR", "CCPA", "HIPAA", "SOC2", "PCI", "none"]


def _agent_flagged_compliance(path: AgentPath) -> bool:
    keys = ("complian", "consent", "privacy", "gdpr", "ccpa", "hipaa", "soc2")
    for step in path.steps:
        for obs in step.decision.observed_issues:
            low = obs.lower()
            if any(k in low for k in keys):
                return True
    return False


def build_compliance_grouped_dot_plot(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    dots: list[Dot] = []
    for p in sim.paths:
        regs = p.agent.group.testing_postures.compliance.regulations or ["none"]
        flagged = _agent_flagged_compliance(p)
        for r in regs:
            dots.append(
                Dot(
                    agent_id=p.agent.agent_id,
                    cluster_id=p.agent.cluster_id,
                    x=r if r in REGULATIONS else "none",
                    meta={"flagged_compliance_issue": flagged},
                )
            )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="compliance-grouped",
        title="Compliance flags by regulatory exposure",
        description="Agents grouped by the regulations that apply to them. Color shows whether they flagged a compliance concern.",
        chart_type="grouped_dot_plot",
        scope="all_clusters",
        axes={"x": AxisDef(label="Regulatory exposure", categorical=REGULATIONS)},
        dots=dots,
        annotations=annotations,
    )


def build_compliance_funnel(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    touchpoints = _screens_matching_purpose(sim, COMPLIANCE_PURPOSE_KEYWORDS)
    dots: list[Dot] = []
    for p in sim.paths:
        for sid in touchpoints:
            visited = sid in p.screens_visited
            if not visited:
                continue
            # Did they bail HERE? (terminal_state in drop AND last screen is sid)
            bailed_here = (
                p.terminal_state in {"give_up", "dead_end"}
                and (
                    (p.screens_visited and p.screens_visited[-1] == sid)
                    or (p.steps and p.steps[-1].screen_id == sid)
                )
            )
            dots.append(
                Dot(
                    agent_id=p.agent.agent_id,
                    cluster_id=p.agent.cluster_id,
                    x=sid,
                    y="bailed" if bailed_here else "proceeded",
                    meta={
                        "regulations": p.agent.group.testing_postures.compliance.regulations,
                    },
                )
            )

    annotations: list[DotAnnotation] = []
    if not touchpoints:
        annotations.append(
            DotAnnotation(
                type="empty_state",
                text="No screens matched compliance touchpoint keywords.",
            )
        )
    elif not dots:
        annotations.append(_empty_state_annotation("No agents reached any compliance touchpoint."))

    return PersonaDistribution(
        id="compliance-funnel",
        title="Trust funnel through compliance touchpoints",
        description="Agents flow forward (proceeded) or drop down (bailed) at each compliance-related screen.",
        chart_type="funnel_dot_flow",
        scope="all_clusters",
        axes={
            "x": AxisDef(label="Touchpoint", categorical=touchpoints or []),
            "y": AxisDef(label="Outcome", categorical=["proceeded", "bailed"]),
        },
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Onboarding distributions ────────────────────────────

def build_onboarding_funnel(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    """One funnel per cluster (scope=per_cluster)."""
    dots: list[Dot] = []
    step_labels = [f"step_{i + 1}" for i in range(ONBOARDING_WINDOW)]
    for p in sim.paths:
        for i in range(min(len(p.steps), ONBOARDING_WINDOW)):
            step = p.steps[i]
            # Did they drop after this step? terminal in drop and this is the last step.
            is_last_step = (i == len(p.steps) - 1)
            dropped_here = is_last_step and p.terminal_state in {"give_up", "dead_end", "max_steps_reached"}
            dots.append(
                Dot(
                    agent_id=p.agent.agent_id,
                    cluster_id=p.agent.cluster_id,
                    x=step_labels[i],
                    y="dropped" if dropped_here else "proceeded",
                    meta={"terminal_state": p.terminal_state if is_last_step else None},
                )
            )
    annotations: list[DotAnnotation] = []
    cluster_with_dots = {d.cluster_id for d in dots}
    for cid in slice_.cluster_counts:
        if cid not in cluster_with_dots:
            annotations.append(
                DotAnnotation(
                    type="empty_state",
                    text=f"No onboarding steps captured for cluster {cid}.",
                    position={"cluster_id": cid},
                )
            )
    if not dots and not annotations:
        annotations.append(_empty_state_annotation())
    return PersonaDistribution(
        id="onboarding-funnel",
        title="Onboarding step funnel per cluster",
        description="Agents through the first 5 onboarding steps, with a row for proceeded vs dropped.",
        chart_type="funnel_dot_flow",
        scope="per_cluster",
        axes={
            "x": AxisDef(label="Step", categorical=step_labels),
            "y": AxisDef(label="Outcome", categorical=["proceeded", "dropped"]),
        },
        dots=dots,
        annotations=annotations,
    )


def build_onboarding_scatter(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))
    dots: list[Dot] = []
    for p in sim.paths:
        ttfv = None
        if core_screens:
            for step in p.steps:
                if step.screen_id in core_screens:
                    ttfv = step.elapsed_seconds_total
                    break
        elif p.terminal_state == "complete":
            ttfv = p.cumulative_seconds
        if ttfv is None:
            ttfv = min(p.cumulative_seconds, 600)
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=p.agent.tech_savviness,
                y=min(ttfv, 600),
                meta={"terminal_state": p.terminal_state},
            )
        )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="onboarding-scatter",
        title="Tech-savviness vs. time-to-first-value",
        description="Where each agent landed first-value as a function of their tech savviness.",
        chart_type="scatter",
        scope="all_clusters",
        axes={
            "x": AxisDef(label="Tech savviness (1–5)", min=1, max=5),
            "y": AxisDef(label="Time to first value", unit="s", min=0, max=600),
        },
        dots=dots,
        annotations=annotations,
    )


def build_onboarding_beeswarm(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    onboarding_screens = set(slice_.screen_ids)
    total_onboarding_screens = max(len(onboarding_screens), 1)
    dots: list[Dot] = []
    for p in sim.paths:
        visited_onboarding = sum(1 for s in set(p.screens_visited) if s in onboarding_screens)
        score = round(100 * visited_onboarding / total_onboarding_screens)
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=min(score, 100),
                meta={"visited": visited_onboarding},
            )
        )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="onboarding-beeswarm",
        title="Onboarding completion score per agent",
        description="Per-cluster distribution of how much of the onboarding window each agent covered.",
        chart_type="beeswarm",
        scope="per_cluster",
        axes={"x": AxisDef(label="Onboarding score", unit="%", min=0, max=100)},
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Activation distributions ────────────────────────────

def build_activation_dot_plot(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))
    dots: list[Dot] = []
    for p in sim.paths:
        outcome = _activation_outcome(p, core_screens)
        motiv = p.agent.group.testing_postures.activation.motivation_level
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=motiv,
                meta={"activation_outcome": outcome},
            )
        )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="activation-dot-plot",
        title="Activation by motivation level",
        description="Agents arranged by stated motivation, colored by activation outcome.",
        chart_type="dot_plot",
        scope="all_clusters",
        axes={"x": AxisDef(label="Motivation level", categorical=["low", "medium", "high"])},
        dots=dots,
        annotations=annotations,
    )


def build_activation_parallel(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))
    dots: list[Dot] = []
    for p in sim.paths:
        reached_aha = 1 if (
            p.terminal_state == "complete"
            or any(s.screen_id in core_screens for s in p.steps)
        ) else 0
        used_core = _used_core_feature(p, core_screens)
        configured = _has_settings_action(p)
        invited = _has_invite_action(p)
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x="reached_aha",  # placeholder; the line is in meta
                meta={
                    "reached_aha": reached_aha,
                    "used_core_feature": used_core,
                    "configured_setting": configured,
                    "invited_teammate": invited,
                },
            )
        )
    annotations: list[DotAnnotation] = []
    cluster_with_dots = {d.cluster_id for d in dots}
    for cid in slice_.cluster_counts:
        if cid not in cluster_with_dots:
            annotations.append(
                DotAnnotation(
                    type="empty_state",
                    text=f"No activation lines for cluster {cid}.",
                    position={"cluster_id": cid},
                )
            )
    if not dots and not annotations:
        annotations.append(_empty_state_annotation())
    return PersonaDistribution(
        id="activation-parallel",
        title="Activation patterns per cluster",
        description="Each line is one agent across four binary axes; clusters are stacked.",
        chart_type="parallel_coordinates",
        scope="per_cluster",
        axes={
            "reached_aha": AxisDef(label="Reached aha", min=0, max=1),
            "used_core_feature": AxisDef(label="Used core feature", min=0, max=1),
            "configured_setting": AxisDef(label="Configured setting", min=0, max=1),
            "invited_teammate": AxisDef(label="Invited teammate", min=0, max=1),
        },
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Engagement distributions ────────────────────────────

def build_engagement_beeswarm(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    dots = [
        Dot(
            agent_id=p.agent.agent_id,
            cluster_id=p.agent.cluster_id,
            x=len(set(p.screens_visited)),
            meta={"steps": len(p.steps)},
        )
        for p in slice_.paths
    ]
    annotations: list[DotAnnotation] = []
    cluster_with_dots = {d.cluster_id for d in dots}
    for cid in slice_.cluster_counts:
        if cid not in cluster_with_dots:
            annotations.append(
                DotAnnotation(
                    type="empty_state",
                    text=f"No engagement signals for cluster {cid}.",
                    position={"cluster_id": cid},
                )
            )
    if not dots and not annotations:
        annotations.append(_empty_state_annotation())
    return PersonaDistribution(
        id="engagement-beeswarm",
        title="Unique screens visited per agent",
        description="Per-cluster distribution of how many distinct screens each agent visited.",
        chart_type="beeswarm",
        scope="per_cluster",
        axes={"x": AxisDef(label="Unique screens visited", min=0)},
        dots=dots,
        annotations=annotations,
    )


def build_engagement_scatter(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    dots: list[Dot] = []
    for p in slice_.paths:
        if not p.steps:
            continue
        avg_int = sum(s.decision.emotional_state.interest for s in p.steps) / len(p.steps)
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=len(p.steps),
                y=round(avg_int, 2),
                meta={"terminal_state": p.terminal_state},
            )
        )
    annotations = [] if dots else [_empty_state_annotation()]
    return PersonaDistribution(
        id="engagement-scatter",
        title="Session depth vs. interest",
        description="Each dot is one agent. X = number of steps taken; Y = average interest score.",
        chart_type="scatter",
        scope="all_clusters",
        axes={
            "x": AxisDef(label="Session depth (steps)", min=0),
            "y": AxisDef(label="Avg interest score", min=1, max=5),
        },
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Retention distributions ────────────────────────────

PREDICTIVE_NOTE = "Predictive signal — not measured retention."


def build_retention_dot_distribution(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    dots = [
        Dot(
            agent_id=p.agent.agent_id,
            cluster_id=p.agent.cluster_id,
            x=score_return_likelihood(p),
            meta={},
        )
        for p in sim.paths
    ]
    annotations: list[DotAnnotation] = [
        DotAnnotation(type="note", text=PREDICTIVE_NOTE),
    ]
    if not dots:
        annotations.append(_empty_state_annotation())
    cluster_with_dots = {d.cluster_id for d in dots}
    for cid in slice_.cluster_counts:
        if cid not in cluster_with_dots:
            annotations.append(
                DotAnnotation(
                    type="empty_state",
                    text=f"No return-intent signals for cluster {cid}.",
                    position={"cluster_id": cid},
                )
            )
    return PersonaDistribution(
        id="retention-dot-distribution",
        title="Expressed return likelihood (predictive)",
        description="Per-cluster spread of inferred return likelihood (0–5) from agent reasoning.",
        chart_type="dot_distribution",
        scope="per_cluster",
        axes={"x": AxisDef(label="Return likelihood (0–5)", min=0, max=5)},
        dots=dots,
        annotations=annotations,
    )


def build_retention_grouped_count(
    slice_: FilteredSlice, sim: SimulationResult
) -> PersonaDistribution:
    groups = ["habit_marker_touched", "switching_cost_expressed", "neither"]
    dots: list[Dot] = []
    for p in sim.paths:
        habit = agent_touched_habit_marker(p)
        switch = agent_expressed_switching_cost(p)
        if habit:
            group = "habit_marker_touched"
        elif switch:
            group = "switching_cost_expressed"
        else:
            group = "neither"
        dots.append(
            Dot(
                agent_id=p.agent.agent_id,
                cluster_id=p.agent.cluster_id,
                x=group,
                meta={"habit": habit, "switching_cost": switch},
            )
        )
    annotations: list[DotAnnotation] = [
        DotAnnotation(type="note", text=PREDICTIVE_NOTE),
    ]
    if not dots:
        annotations.append(_empty_state_annotation())
    return PersonaDistribution(
        id="retention-grouped",
        title="Retention markers (predictive)",
        description="Each agent placed into one of three groups based on the strongest signal observed.",
        chart_type="grouped_dot_count",
        scope="all_clusters",
        axes={"x": AxisDef(label="Marker", categorical=groups)},
        dots=dots,
        annotations=annotations,
    )


# ──────────────────────────── Dispatch ────────────────────────────

DISTRIBUTION_BUILDERS_BY_TEST_TYPE = {
    "accessibility": [build_a11y_scatter, build_a11y_dot_grid, build_a11y_beeswarm],
    "compliance": [build_compliance_grouped_dot_plot, build_compliance_funnel],
    "onboarding": [build_onboarding_funnel, build_onboarding_scatter, build_onboarding_beeswarm],
    "activation": [build_activation_dot_plot, build_activation_parallel],
    "engagement": [build_engagement_beeswarm, build_engagement_scatter],
    "retention": [build_retention_dot_distribution, build_retention_grouped_count],
}


def build(slice_: FilteredSlice, sim: SimulationResult) -> list[PersonaDistribution]:
    builders = DISTRIBUTION_BUILDERS_BY_TEST_TYPE.get(slice_.test_type)
    if builders is None:
        raise ValueError(f"Unknown test_type: {slice_.test_type!r}")
    return [b(slice_, sim) for b in builders]


# ──────────────────────────── Trajectory (per-cluster emotional arc) ────────────────────────────

def compute_trajectory(slice_: FilteredSlice, sim: SimulationResult) -> Trajectory:
    """Average emotional state by (cluster, screen) for the slice's paths.

    `screens` is in first-arrival order across all paths in the slice — this
    is the canonical X-axis for the trajectory chart. Cells with no samples
    are omitted (the renderer treats them as gaps).
    """
    paths = slice_.paths if slice_.paths else list(sim.paths)

    screen_order: list[str] = []
    screen_seen: set[str] = set()
    cluster_order: list[str] = []
    cluster_seen: set[str] = set()
    acc: dict[tuple[str, str], list] = defaultdict(list)

    for p in paths:
        cid = p.agent.cluster_id
        if cid not in cluster_seen:
            cluster_seen.add(cid)
            cluster_order.append(cid)
        for step in p.steps:
            sid = step.screen_id
            if sid not in screen_seen:
                screen_seen.add(sid)
                screen_order.append(sid)
            acc[(cid, sid)].append(step.decision.emotional_state)

    cells: list[TrajectoryCell] = []
    screen_index = {sid: i for i, sid in enumerate(screen_order)}
    for (cid, sid), states in acc.items():
        n = len(states)
        if n == 0:
            continue
        cells.append(
            TrajectoryCell(
                cluster_id=cid,
                screen_id=sid,
                screen_index=screen_index[sid],
                emotions=EmotionalAverage(
                    confusion=round(sum(s.confusion for s in states) / n, 3),
                    frustration=round(sum(s.frustration for s in states) / n, 3),
                    interest=round(sum(s.interest for s in states) / n, 3),
                    trust=round(sum(s.trust for s in states) / n, 3),
                ),
                sample_size=n,
            )
        )
    cells.sort(key=lambda c: (c.cluster_id, c.screen_index))
    return Trajectory(screens=screen_order, clusters=cluster_order, cells=cells)
