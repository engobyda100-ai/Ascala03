"""End-to-end tests for generate_report() with mock LLM — all 6 test types produced."""
from __future__ import annotations

import pytest

from persona_report.generator import generate_report
from persona_report.schema import Report


# ────────────── helpers ──────────────

def _get_report(test_type: str, report: Report):
    return next(r for r in report.test_type_reports if r.test_type == test_type)


# ────────────── tests ──────────────

def test_full_report_schema_validates(sample_simulation, default_provider):
    """generate_report produces a fully valid Report that survives a schema round-trip."""
    report = generate_report(sample_simulation, provider=default_provider)
    Report.model_validate(report.model_dump())
    assert len(report.test_type_reports) == 6
    assert {r.test_type for r in report.test_type_reports} == {
        "accessibility", "compliance", "onboarding",
        "activation", "engagement", "retention",
    }
    for r in report.test_type_reports:
        assert len(r.key_stats) == 3
        assert 1 <= len(r.persona_distributions) <= 3
        assert r.data_confidence in {"high", "medium", "low"}


def test_retention_no_signals_has_empty_fixes_and_disclaimer(
    sample_simulation, make_provider, mock_fix_dict
):
    """Retention section with no return-intent signals yields empty fixes and a
    predictive disclaimer in the short_summary."""
    # Strip all return-intent reasoning from every agent step
    sim = sample_simulation.model_copy(deep=True)
    for path in sim.paths:
        for step in path.steps:
            step.decision.reasoning = "Neutral observation with no intent expressed."
            step.decision.observed_issues = []

    provider = make_provider()
    report = generate_report(sim, provider=provider)
    retention = _get_report("retention", report)

    assert retention.recommended_fixes == []
    # The mock summary contains the word "predictive" — check it is there
    assert "predictive" in retention.short_summary.lower()


def test_compliance_no_exposure_has_low_confidence(
    sample_simulation, make_provider
):
    """When all agents have no regulatory exposure, compliance data_confidence is 'low'."""
    sim = sample_simulation.model_copy(deep=True)
    for path in sim.paths:
        cp = path.agent.group.testing_postures.compliance
        object.__setattr__(cp, "regulations", ["none"])
        object.__setattr__(cp, "data_sensitivity", "low")
        object.__setattr__(cp, "enterprise_procurement", False)

    provider = make_provider()
    report = generate_report(sim, provider=provider)
    compliance = _get_report("compliance", report)
    assert compliance.data_confidence == "low"


def test_exec_summary_present_when_requested(sample_simulation, default_provider):
    """include_executive_summary=True produces a non-empty executive_summary."""
    report = generate_report(
        sample_simulation, provider=default_provider, include_executive_summary=True
    )
    assert report.executive_summary is not None
    assert len(report.executive_summary) > 20


def test_exec_summary_absent_by_default(sample_simulation, default_provider):
    """executive_summary is None when include_executive_summary is not set."""
    report = generate_report(sample_simulation, provider=default_provider)
    assert report.executive_summary is None


def test_fix_severity_matches_deterministic_rules(sample_simulation, default_provider):
    """The compliance TestTypeReport contains at least one urgent fix, matching the
    deterministic severity truth table (compliance issue + regulatory exposure + bailed)."""
    report = generate_report(sample_simulation, provider=default_provider)
    compliance = _get_report("compliance", report)
    severities = {f.severity for f in compliance.recommended_fixes}
    assert "urgent" in severities, (
        f"Expected at least one urgent compliance fix; got severities: {severities}"
    )
