"""Per-test-type filter predicate selection tests."""
from __future__ import annotations

from persona_report.filters import (
    SELECTOR_BY_TEST_TYPE,
    confidence_from_touchpoints,
    score_return_likelihood,
    select_for,
)


def test_all_six_test_types_have_selectors():
    expected = {"accessibility", "compliance", "onboarding",
                "activation", "engagement", "retention"}
    assert set(SELECTOR_BY_TEST_TYPE.keys()) == expected


def test_select_accessibility(sample_simulation):
    s = select_for("accessibility", sample_simulation)
    assert s.test_type == "accessibility"
    # The fixture has one critical a11y issue covering 3 screens, plus one
    # low-vision agent (a_pg_3_001).
    assert any(i.category == "accessibility" for i in s.issues)
    a11y_paths = [p for p in s.paths if p.agent.cluster_id == "pg_3"]
    assert any(p.agent.agent_id == "a_pg_3_001" for p in a11y_paths)


def test_select_compliance(sample_simulation):
    s = select_for("compliance", sample_simulation)
    assert s.test_type == "compliance"
    assert any(i.category == "compliance" for i in s.issues)
    # Compliance touchpoint screens include s2 (consent)
    assert "s2" in s.screen_ids


def test_select_onboarding(sample_simulation):
    s = select_for("onboarding", sample_simulation)
    assert s.test_type == "onboarding"
    # All 9 agents go through onboarding
    assert len(s.paths) == 9
    # touchpoint = sum of first 5 steps per agent (capped)
    assert s.touchpoint_count > 0


def test_select_activation(sample_simulation):
    s = select_for("activation", sample_simulation)
    assert s.test_type == "activation"
    assert len(s.paths) == 9
    # Should pick up the activation issue from the fixture
    assert any(i.category == "activation" for i in s.issues)


def test_select_engagement_excludes_retention_keywords(sample_simulation):
    s = select_for("engagement", sample_simulation)
    assert s.test_type == "engagement"
    # The fixture has a "Template gallery" issue under engagement_retention
    # (no "return"/"come back" keyword) → engagement keeps it.
    summaries = [i.summary for i in s.issues]
    assert any("Template gallery" in summ for summ in summaries)


def test_select_retention_uses_signal_touchpoints(sample_simulation):
    s = select_for("retention", sample_simulation)
    assert s.test_type == "retention"
    # touchpoint counts agents with non-zero return-likelihood OR a habit-marker touch
    # Solo Bootstrappers all have habit-marker / return-intent reasoning in the fixture.
    assert s.touchpoint_count >= 3


def test_unknown_test_type_raises(sample_simulation):
    import pytest
    with pytest.raises(ValueError):
        select_for("nonexistent", sample_simulation)


def test_confidence_thresholds():
    assert confidence_from_touchpoints(50) == "high"
    assert confidence_from_touchpoints(30) == "high"
    assert confidence_from_touchpoints(29) == "medium"
    assert confidence_from_touchpoints(10) == "medium"
    assert confidence_from_touchpoints(9) == "low"
    assert confidence_from_touchpoints(0) == "low"


def test_return_likelihood_scoring(sample_simulation):
    # The "bookmarking this" agent should score 5
    a1 = next(p for p in sample_simulation.paths if p.agent.agent_id == "a_pg_1_001")
    assert score_return_likelihood(a1) == 5
    # The "done with this" agent (give_up cluster 2 #2) should score 1
    a_done = next(p for p in sample_simulation.paths if p.agent.agent_id == "a_pg_2_002")
    assert score_return_likelihood(a_done) == 1
    # An agent with no return-related reasoning scores 0
    a_neutral = next(p for p in sample_simulation.paths if p.agent.agent_id == "a_pg_2_003")
    assert score_return_likelihood(a_neutral) == 0
