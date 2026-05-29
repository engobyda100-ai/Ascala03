"""Per-test-type filter predicates.

Each function takes a `SimulationResult` and returns a `FilteredSlice`:
the issues, agent paths, and screens that are relevant to the test type.
Pure code — no LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from persona_simulation.schema import (
    AgentPath,
    SimulationResult,
)
from persona_synthesis.schema import PersonaGroup

# Categorized issues come from persona_simulation.schema
from persona_simulation.schema import CategorizedIssue


# ──────────────────────────── Slice type ────────────────────────────

@dataclass
class FilteredSlice:
    test_type: str
    issues: list[CategorizedIssue]
    paths: list[AgentPath]
    screen_ids: list[str]                 # affected screens
    cluster_counts: dict[str, int]        # cluster_id -> n_agents in slice
    touchpoint_count: int                 # for data_confidence

    def all_clusters(self) -> list[str]:
        """All cluster_ids represented in the slice (in encounter order)."""
        seen: dict[str, None] = {}
        for p in self.paths:
            seen.setdefault(p.agent.cluster_id, None)
        return list(seen.keys())


# ──────────────────────────── Helpers ────────────────────────────

A11Y_KEYWORDS = re.compile(
    r"\b(focus|contrast|screen[\s-]?reader|keyboard|alt[\s-]?text|a11y|accessibility|legibl|readable)\b",
    re.IGNORECASE,
)

COMPLIANCE_PURPOSE_KEYWORDS = re.compile(
    r"\b(privacy|consent|cookie|terms|data|payment|billing|signup|account)\b",
    re.IGNORECASE,
)

ONBOARDING_PURPOSE_KEYWORDS = re.compile(
    r"\b(signup|sign[\s-]?up|welcome|verify|workspace|invite|setup|onboard|get[\s-]?started)\b",
    re.IGNORECASE,
)

CORE_SCREEN_KEYWORDS = re.compile(
    r"\b(dashboard|home|main|core|workspace|feed|results|gallery|inbox)\b",
    re.IGNORECASE,
)

RETENTION_ISSUE_KEYWORDS = re.compile(
    r"\b(return|come[\s-]?back|churn|repeat|habit|sticky)\b",
    re.IGNORECASE,
)

ENGAGEMENT_EXCLUSION_KEYWORDS = re.compile(
    r"\b(return|come[\s-]?back|churn|day[-\s]?\d+)\b",
    re.IGNORECASE,
)

ONBOARDING_WINDOW_STEPS = 5


def _agent_observed_a11y(path: AgentPath) -> bool:
    for step in path.steps:
        for issue in step.decision.observed_issues:
            if A11Y_KEYWORDS.search(issue):
                return True
    return False


def _has_a11y_posture(group: PersonaGroup) -> bool:
    pos = group.testing_postures.accessibility
    if pos.vision != "full" or pos.motor != "full" or pos.hearing != "full":
        return True
    if pos.screen_reader_likelihood >= 30:
        return True
    return False


def _has_compliance_exposure(group: PersonaGroup) -> bool:
    pos = group.testing_postures.compliance
    if pos.regulations != ["none"] and pos.regulations:
        return True
    if pos.data_sensitivity in {"medium", "high"}:
        return True
    if pos.enterprise_procurement:
        return True
    return False


def _purpose_match(sim: SimulationResult, screen_id: str, regex: re.Pattern) -> bool:
    for s in sim.screen_graph.screens:
        if s.id == screen_id and regex.search(s.inferred_purpose):
            return True
    return False


def _screens_matching_purpose(sim: SimulationResult, regex: re.Pattern) -> list[str]:
    return [s.id for s in sim.screen_graph.screens if regex.search(s.inferred_purpose)]


def _cluster_counts(paths: Iterable[AgentPath]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in paths:
        out[p.agent.cluster_id] = out.get(p.agent.cluster_id, 0) + 1
    return out


# ──────────────────────────── Per-test-type selectors ────────────────────────────

def select_accessibility(sim: SimulationResult) -> FilteredSlice:
    issues = [i for i in sim.report.categorized_issues.issues if i.category == "accessibility"]
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    paths = [
        p for p in sim.paths
        if _has_a11y_posture(p.agent.group) or _agent_observed_a11y(p)
    ]
    return FilteredSlice(
        test_type="accessibility",
        issues=issues,
        paths=paths,
        screen_ids=sorted(issue_screens),
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=sum(len(p.steps) for p in paths),
    )


def select_compliance(sim: SimulationResult) -> FilteredSlice:
    issues = [i for i in sim.report.categorized_issues.issues if i.category == "compliance"]
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    purpose_screens = set(_screens_matching_purpose(sim, COMPLIANCE_PURPOSE_KEYWORDS))
    screen_ids = sorted(issue_screens | purpose_screens)
    paths = [p for p in sim.paths if _has_compliance_exposure(p.agent.group)]
    # Touchpoints: agent steps that arrived at a compliance touchpoint screen
    touch = 0
    for p in paths:
        for step in p.steps:
            if step.screen_id in purpose_screens:
                touch += 1
    return FilteredSlice(
        test_type="compliance",
        issues=issues,
        paths=paths,
        screen_ids=screen_ids,
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=touch + len(issues),
    )


def select_onboarding(sim: SimulationResult) -> FilteredSlice:
    issues = [i for i in sim.report.categorized_issues.issues if i.category == "onboarding"]
    purpose_screens = set(_screens_matching_purpose(sim, ONBOARDING_PURPOSE_KEYWORDS))
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    screen_ids = sorted(issue_screens | purpose_screens)
    paths = list(sim.paths)  # all agents have onboarding signal
    # Touchpoints: steps within first ONBOARDING_WINDOW_STEPS for each agent
    touch = sum(min(len(p.steps), ONBOARDING_WINDOW_STEPS) for p in paths)
    return FilteredSlice(
        test_type="onboarding",
        issues=issues,
        paths=paths,
        screen_ids=screen_ids,
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=touch,
    )


def select_activation(sim: SimulationResult) -> FilteredSlice:
    issues = [i for i in sim.report.categorized_issues.issues if i.category == "activation"]
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    core_screens = set(_screens_matching_purpose(sim, CORE_SCREEN_KEYWORDS))
    paths = list(sim.paths)
    # Touchpoints: every agent contributes 1 (activation rate is sample-wide)
    return FilteredSlice(
        test_type="activation",
        issues=issues,
        paths=paths,
        screen_ids=sorted(issue_screens | core_screens),
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=len(paths),
    )


def select_engagement(sim: SimulationResult) -> FilteredSlice:
    # category=engagement_retention but exclude retention-only issues (return/come-back/etc.)
    issues = [
        i for i in sim.report.categorized_issues.issues
        if i.category == "engagement_retention"
        and not ENGAGEMENT_EXCLUSION_KEYWORDS.search(i.summary)
    ]
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    paths = [p for p in sim.paths if len(p.steps) >= 3]
    return FilteredSlice(
        test_type="engagement",
        issues=issues,
        paths=paths,
        screen_ids=sorted(issue_screens),
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=sum(len(p.steps) for p in paths),
    )


# ──────────────────────────── Retention scoring ────────────────────────────

RETURN_LIKELIHOOD_PATTERNS: list[tuple[int, re.Pattern]] = [
    (5, re.compile(r"\b(definitely|can'?t wait|bookmark(?:ing)?|adding to)\b", re.IGNORECASE)),
    (4, re.compile(r"\b(will come back|looking forward|plan to|i'll be back)\b", re.IGNORECASE)),
    (3, re.compile(r"\b(might|maybe|could see myself|consider(?:ing)?)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(unlikely|probably not|not sure if i)\b", re.IGNORECASE)),
    (1, re.compile(r"\b(won'?t|never|done with this|moving on)\b", re.IGNORECASE)),
]

HABIT_MARKER_PATTERNS = re.compile(
    r"\b(save|bookmark|subscribe|notify|alerts|updates|download|follow|watchlist|favorite|favourite)\b",
    re.IGNORECASE,
)

SWITCHING_COST_PATTERNS = re.compile(
    r"\b(migrat|switch|move from|current tool|already using|other app|leaving)\b",
    re.IGNORECASE,
)


def score_return_likelihood(path: AgentPath) -> int:
    """Highest-tier match across all step reasonings. 0 if none matched."""
    best = 0
    for step in path.steps:
        text = step.decision.reasoning
        for score, pat in RETURN_LIKELIHOOD_PATTERNS:
            if pat.search(text):
                if score > best:
                    best = score
                break
    return best


def agent_touched_habit_marker(path: AgentPath) -> bool:
    for step in path.steps:
        elem_id = step.decision.target_element_id or ""
        if HABIT_MARKER_PATTERNS.search(elem_id):
            return True
        # Also check observed_issues / reasoning for marker mentions
        if HABIT_MARKER_PATTERNS.search(step.decision.reasoning):
            return True
    return False


def agent_expressed_switching_cost(path: AgentPath) -> bool:
    for step in path.steps:
        if SWITCHING_COST_PATTERNS.search(step.decision.reasoning):
            return True
    return False


def select_retention(sim: SimulationResult) -> FilteredSlice:
    issues = [
        i for i in sim.report.categorized_issues.issues
        if i.category == "engagement_retention"
        and RETENTION_ISSUE_KEYWORDS.search(i.summary)
    ]
    paths = list(sim.paths)
    # Touchpoint: agents with non-zero return likelihood OR a habit-marker touch
    touch = sum(
        1 for p in paths
        if score_return_likelihood(p) > 0 or agent_touched_habit_marker(p)
    )
    issue_screens = {sid for i in issues for sid in i.affected_screens}
    return FilteredSlice(
        test_type="retention",
        issues=issues,
        paths=paths,
        screen_ids=sorted(issue_screens),
        cluster_counts=_cluster_counts(paths),
        touchpoint_count=touch,
    )


# ──────────────────────────── Dispatch ────────────────────────────

SELECTOR_BY_TEST_TYPE = {
    "accessibility": select_accessibility,
    "compliance": select_compliance,
    "onboarding": select_onboarding,
    "activation": select_activation,
    "engagement": select_engagement,
    "retention": select_retention,
}


def select_for(test_type: str, sim: SimulationResult) -> FilteredSlice:
    if test_type not in SELECTOR_BY_TEST_TYPE:
        raise ValueError(f"Unknown test_type: {test_type!r}")
    return SELECTOR_BY_TEST_TYPE[test_type](sim)


def confidence_from_touchpoints(touchpoint_count: int) -> str:
    if touchpoint_count >= 30:
        return "high"
    if touchpoint_count >= 10:
        return "medium"
    return "low"
