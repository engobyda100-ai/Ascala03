"""Deterministic severity assignment for candidate fixes.

The LLM never picks severity — the truth table runs against the underlying
SimulationResult data. Rules are evaluated in order; first match wins.

Rule ordering (PLAN.md §6):
  1. compliance + regulatory exposure + agent bailed at affected screen → urgent
  2. accessibility + simulation issue.severity == "critical"            → urgent
  3. affected-cluster drop-off > 20% at affected screens                → urgent
  4. majority of any single cluster has avg(confusion+frustration) >= 4 → important
  5. >= 30% of all agents observed an overlapping issue                 → important
  6. default                                                            → medium
"""
from __future__ import annotations

from collections import defaultdict

from persona_simulation.schema import (
    AgentPath,
    CategorizedIssue,
    SimulationResult,
)


CLUSTER_DROP_OFF_THRESHOLD = 0.20    # rule #3
CONFUSION_FRUSTRATION_FLOOR = 4      # rule #4
GLOBAL_OVERLAP_THRESHOLD = 0.30      # rule #5
TERMINAL_DROP_STATES = {"give_up", "dead_end"}


def _cluster_paths(paths: list[AgentPath]) -> dict[str, list[AgentPath]]:
    out: dict[str, list[AgentPath]] = defaultdict(list)
    for p in paths:
        out[p.agent.cluster_id].append(p)
    return out


def _agent_dropped_at_screens(path: AgentPath, screen_ids: set[str]) -> bool:
    if path.terminal_state not in TERMINAL_DROP_STATES:
        return False
    last = path.screens_visited[-1] if path.screens_visited else None
    if last in screen_ids:
        return True
    # Also allow: if the agent's last step was on one of the screens
    if path.steps and path.steps[-1].screen_id in screen_ids:
        return True
    return False


def _agent_visited_affected_and_dropped(path: AgentPath, screen_ids: set[str]) -> bool:
    """True if agent visited any affected screen AND bailed anywhere downstream.

    Used for Rule 1 (compliance): a compliance concern on screen X can cause
    abandonment at screen X+1 — the strict "bailed at X" check misses that case.
    """
    if path.terminal_state not in TERMINAL_DROP_STATES:
        return False
    return any(s.screen_id in screen_ids for s in path.steps)


def _agent_avg_confusion_frustration(path: AgentPath, screen_ids: set[str]) -> float:
    """Average of (confusion + frustration) across this agent's steps that
    landed on one of the affected screens. 0 if the agent never touched them.
    """
    rel = [s for s in path.steps if s.screen_id in screen_ids]
    if not rel:
        return 0.0
    return sum(
        (s.decision.emotional_state.confusion + s.decision.emotional_state.frustration) / 2
        for s in rel
    ) / len(rel)


def _issue_evidence_overlap(issue: CategorizedIssue, path: AgentPath) -> bool:
    """True if any of this agent's observed_issues matches any evidence string."""
    if not issue.evidence:
        return False
    evidence_set = {e.strip().lower() for e in issue.evidence if e.strip()}
    for step in path.steps:
        for obs in step.decision.observed_issues:
            if obs.strip().lower() in evidence_set:
                return True
    return False


# ──────────────────────────── Public API ────────────────────────────

def classify(issue: CategorizedIssue, sim: SimulationResult) -> str:
    """Return one of 'urgent', 'important', 'medium' for the given issue."""
    affected = set(issue.affected_screens)
    paths = sim.paths

    # Rule 1: compliance + regulatory exposure + bailed (visited affected screen + dropped anywhere)
    if issue.category == "compliance":
        for p in paths:
            regs = p.agent.group.testing_postures.compliance.regulations
            has_exposure = (regs and regs != ["none"])
            if has_exposure and _agent_visited_affected_and_dropped(p, affected):
                return "urgent"

    # Rule 2: accessibility + critical severity
    if issue.category == "accessibility" and issue.severity == "critical":
        return "urgent"

    # Rule 3: affected-cluster drop-off > 20% at affected screens
    if affected:
        for cid, cpaths in _cluster_paths(paths).items():
            n_cluster = len(cpaths)
            if n_cluster == 0:
                continue
            dropped = sum(1 for p in cpaths if _agent_dropped_at_screens(p, affected))
            if dropped / n_cluster > CLUSTER_DROP_OFF_THRESHOLD:
                return "urgent"

    # Rule 4: majority of any single cluster with avg(confusion+frustration) >= 4
    if affected:
        for cid, cpaths in _cluster_paths(paths).items():
            n_cluster = len(cpaths)
            if n_cluster == 0:
                continue
            high = sum(
                1 for p in cpaths
                if _agent_avg_confusion_frustration(p, affected) >= CONFUSION_FRUSTRATION_FLOOR
            )
            if high / n_cluster > 0.5:
                return "important"

    # Rule 5: >= 30% of all agents have an observed_issue overlapping this issue's evidence
    if paths:
        overlapping = sum(1 for p in paths if _issue_evidence_overlap(issue, p))
        if overlapping / len(paths) >= GLOBAL_OVERLAP_THRESHOLD:
            return "important"

    return "medium"


def classify_many(
    issues: list[CategorizedIssue], sim: SimulationResult
) -> list[tuple[CategorizedIssue, str]]:
    return [(issue, classify(issue, sim)) for issue in issues]
