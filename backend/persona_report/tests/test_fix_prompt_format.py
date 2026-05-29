"""Structural validation of fix_prompt format: check_fix_prompt + retry behaviour."""
from __future__ import annotations

import pytest

from persona_simulation.schema import CategorizedIssue

from persona_report.errors import FixPromptFormatError
from persona_report.fixes import (
    FixCache,
    check_fix_prompt,
    draft_fix,
    draft_fixes_for_test_type,
)

from persona_report.tests.conftest import ByToolDummyProvider


# ────────────── helpers ──────────────

def _make_issue(**kw) -> CategorizedIssue:
    base = dict(
        summary="No privacy policy link before consent.",
        category="compliance",
        severity="high",
        evidence=["Consent flow is confusing"],
        affected_screens=["s2"],
    )
    base.update(kw)
    return CategorizedIssue(**base)


# ────────────── tests ──────────────

def test_valid_fix_prompt_passes(mock_fix_dict):
    """A well-formed fix_prompt from the fixture contains all 4 required sections."""
    missing = check_fix_prompt(mock_fix_dict["fix_prompt"])
    assert missing == [], f"Expected no missing sections, got: {missing}"


def test_missing_change_required_triggers_retry(
    sample_simulation, mock_fix_dict, mock_fix_bad_dict
):
    """When the first LLM response fails the format check, draft_fix retries once
    and returns the well-formed fix from the second call."""
    provider = ByToolDummyProvider({
        "emit_fix": [mock_fix_bad_dict, mock_fix_dict],
    })
    issue = _make_issue()
    fix, _tokens = draft_fix(
        issue, "medium", sample_simulation, provider=provider, test_type="compliance",
    )
    assert fix.title == mock_fix_dict["title"]
    assert provider.calls_by_tool["emit_fix"] == 2


def test_missing_evidence_numbers_detected_by_check():
    """A prompt with 'Evidence:' but no N/M ratio is flagged as missing section_2."""
    bad_prompt = (
        "On the s2 screen (s2-signup.png), the consent checkbox lacks a privacy link.\n\n"
        "Evidence: agents in the Small-Team PMs cluster flagged this as a compliance concern.\n\n"
        "Change required: Add an inline privacy policy link above the consent checkbox.\n\n"
        "Visual/interaction direction: 13px terracotta link with external-link icon."
    )
    missing = check_fix_prompt(bad_prompt)
    assert "section_2_evidence" in missing


def test_second_failure_drops_fix_and_records_warning(
    sample_simulation, mock_fix_bad_dict
):
    """When both LLM attempts return a bad-format fix_prompt, draft_fixes_for_test_type
    drops the fix and records a warning — it does not raise."""
    provider = ByToolDummyProvider({
        "emit_fix": [mock_fix_bad_dict],   # cycling: always returns bad fixture
    })
    issue = _make_issue()
    fixes, _tokens, warnings = draft_fixes_for_test_type(
        [(issue, "medium")],
        sample_simulation,
        test_type="compliance",
        provider=provider,
    )
    assert fixes == []
    assert len(warnings) == 1
    assert issue.summary in warnings[0] or "compliance" in warnings[0]
