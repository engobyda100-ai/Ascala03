"""Deterministic severity truth-table tests."""
from __future__ import annotations

import copy

from persona_simulation.schema import (
    AgentDecision,
    AgentPath,
    AgentStep,
    CategorizedIssue,
    EmotionalState,
    SampledAgent,
    SimulationResult,
)

from persona_report.severity import classify, classify_many


def _make_issue(**kw) -> CategorizedIssue:
    base = dict(
        summary="x", category="onboarding", severity="medium",
        evidence=[], affected_screens=["s1"],
    )
    base.update(kw)
    return CategorizedIssue(**base)


def test_compliance_with_regulatory_exposure_and_drop_is_urgent(sample_simulation):
    issue = _make_issue(
        category="compliance", severity="high",
        affected_screens=["s2"],
        evidence=["Consent flow is confusing"],
    )
    assert classify(issue, sample_simulation) == "urgent"


def test_critical_accessibility_is_urgent(sample_simulation):
    issue = _make_issue(
        category="accessibility", severity="critical",
        affected_screens=["s1", "s2", "s3"],
    )
    assert classify(issue, sample_simulation) == "urgent"


def test_cluster_drop_off_above_20pct_is_urgent(sample_simulation):
    # Cluster pg_2 has 1/3 give_up at s2/s3 → 33% > 20%
    issue = _make_issue(
        category="onboarding", severity="medium",
        affected_screens=["s2", "s3"],
        evidence=[],
    )
    # Onboarding rule 1+2 don't apply (not compliance, not critical a11y).
    # Rule 3 (cluster drop > 20%) DOES apply since pg_2 has 1/3 give_up at s2.
    assert classify(issue, sample_simulation) == "urgent"


def test_majority_high_confusion_frustration_is_important(sample_simulation):
    # Construct a synthetic SimulationResult where 2/3 of one cluster has
    # avg(confusion+frustration) >= 4 at the affected screen, no drop-off.
    sim = sample_simulation.model_copy(deep=True)
    # Set ONLY pg_3 agents at s4 to high confusion/frustration; ensure no drop-offs
    # at s4 in the fixture (pg_3 has one complete at s4 already).
    target_screen = "s4"
    for p in sim.paths:
        if p.agent.cluster_id == "pg_3":
            for step in p.steps:
                if step.screen_id == target_screen:
                    step.decision.emotional_state = EmotionalState(
                        confusion=4, frustration=4, interest=3, trust=3,
                    )
    issue = _make_issue(
        category="engagement_retention", severity="medium",
        affected_screens=[target_screen],
        evidence=[],
    )
    # Rules 1/2 don't fire. Rule 3: no give_up/dead_end at s4 in pg_3 → no urgent.
    # Rule 4: pg_3 has 1 agent on s4 with avg=4 → 1/3 of cluster → not majority.
    # → important would only fire if majority. Build a stronger case:
    # make ALL pg_3 agents touch s4 with frustration 4
    extra_step = AgentStep(
        order=99, screen_id=target_screen,
        decision=AgentDecision(
            action="scroll", reasoning="r", confidence=3,
            emotional_state=EmotionalState(confusion=5, frustration=5, interest=2, trust=2),
            estimated_seconds_on_screen=8,
        ),
        elapsed_seconds_total=80,
    )
    pg3 = [p for p in sim.paths if p.agent.cluster_id == "pg_3"]
    for p in pg3:
        # Clear all drop-off states so Rule 3 never fires for this cluster.
        # (The test wants Rule 4 to trigger, not Rule 3.)
        if p.terminal_state in {"give_up", "dead_end"}:
            p.terminal_state = "complete"
        if not any(s.screen_id == target_screen for s in p.steps):
            p.steps.append(extra_step)
            p.screens_visited.append(target_screen)
    assert classify(issue, sim) == "important"


def test_evidence_overlap_30pct_is_important(sample_simulation):
    # ≥ 3 of 9 agents have observed_issue strings overlapping issue.evidence
    issue = _make_issue(
        category="onboarding", severity="medium",
        affected_screens=["s99"],   # no drop-off at this screen → rule 3 skipped
        evidence=["Two CTAs compete for attention"],
    )
    # The fixture has 3 agents (pg_2 #1, pg_2 #2, pg_3 #3) flagging this exact string → 3/9 = 33%
    assert classify(issue, sample_simulation) == "important"


def test_default_is_medium(sample_simulation):
    # An issue that doesn't match any rule above
    issue = _make_issue(
        category="onboarding", severity="low",
        affected_screens=[],   # no overlap with any drop / cluster
        evidence=["completely novel evidence text"],
    )
    assert classify(issue, sample_simulation) == "medium"


def test_classify_many_round_trip(sample_simulation):
    issues = sample_simulation.report.categorized_issues.issues
    out = classify_many(issues, sample_simulation)
    assert len(out) == len(issues)
    severities = {sev for _, sev in out}
    # We expect a mix
    assert severities.issubset({"urgent", "important", "medium"})
