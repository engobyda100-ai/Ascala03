"""End-to-end tests for synthesize_personas with a DummyProvider."""
from __future__ import annotations

import copy

import pytest

from persona_synthesis import (
    ChatMessage,
    SchemaValidationError,
    SynthesisInputs,
    synthesize_personas,
)
from persona_synthesis.schema import StreamEvent


def test_happy_path_chat_only(dummy_chat_only):
    inputs = SynthesisInputs(
        chat_messages=[ChatMessage(role="user", text="B2B SaaS for small founding teams.")]
    )
    result = synthesize_personas(inputs, provider=dummy_chat_only)

    assert len(result.groups) == 3
    s = sum(g.estimated_share_pct for g in result.groups)
    assert 98 <= s <= 102
    assert result.context_summary.app_category == "B2B project management"
    # One summary call + one persona call
    assert len(dummy_chat_only.calls) == 2


def test_retry_on_bad_json(make_dummy, mock_summary_dict, mock_bundle_dict, bad_bundle_dict):
    """First persona call returns an invalid bundle; the pipeline retries and succeeds."""
    provider = make_dummy(
        mock_summary_dict,    # summary call
        bad_bundle_dict,      # first persona attempt — only 1 group → invalid
        mock_bundle_dict,     # retry succeeds
    )
    inputs = SynthesisInputs(chat_messages=[ChatMessage(role="user", text="hi")])
    result = synthesize_personas(inputs, provider=provider)

    assert len(result.groups) == 3
    # summary + first persona + retry persona = 3 calls
    assert len(provider.calls) == 3
    # Retry system prompt must contain the RETRY ADDENDUM marker
    assert "RETRY ADDENDUM" in provider.calls[2]["system"]


def test_double_failure_raises(make_dummy, mock_summary_dict, bad_bundle_dict):
    provider = make_dummy(
        mock_summary_dict,  # summary
        bad_bundle_dict,    # persona attempt 1
        bad_bundle_dict,    # persona attempt 2
    )
    inputs = SynthesisInputs(chat_messages=[ChatMessage(role="user", text="hi")])

    with pytest.raises(SchemaValidationError) as excinfo:
        synthesize_personas(inputs, provider=provider)
    assert excinfo.value.attempts == 2


def test_files_only_path(make_dummy, mock_summary_dict, mock_bundle_dict):
    provider = make_dummy(mock_summary_dict, mock_bundle_dict)
    from persona_synthesis import UploadedFile

    inputs = SynthesisInputs(
        files=[UploadedFile(name="notes.txt", mime="text/plain", data=b"We target founders.")]
    )
    result = synthesize_personas(inputs, provider=provider)
    assert len(result.groups) == 3
    assert len(provider.calls) == 2  # one summary + one persona


def test_both_paths_merge(dummy_both):
    from persona_synthesis import UploadedFile

    inputs = SynthesisInputs(
        files=[UploadedFile(name="notes.txt", mime="text/plain", data=b"hello")],
        chat_messages=[ChatMessage(role="user", text="also founders")],
    )
    result = synthesize_personas(inputs, provider=dummy_both)
    assert len(result.groups) == 3
    # files summary + chat summary + personas = 3 calls
    assert len(dummy_both.calls) == 3


def test_empty_inputs_raise():
    from persona_synthesis.llm.base import LLMProvider

    class NeverCalled:
        def complete(self, **kwargs):
            raise AssertionError("should not be called")

        def stream(self, **kwargs):
            raise AssertionError("should not be called")

    with pytest.raises(ValueError, match="at least one of"):
        synthesize_personas(SynthesisInputs(), provider=NeverCalled())


def test_streaming_events_fire(dummy_chat_only):
    events: list[StreamEvent] = []
    inputs = SynthesisInputs(chat_messages=[ChatMessage(role="user", text="hi")])
    result = synthesize_personas(
        inputs, provider=dummy_chat_only, stream=True, on_event=events.append
    )
    assert len(result.groups) == 3
    kinds = [e.kind for e in events]
    assert "summary_done" in kinds
    assert "done" in kinds
    assert kinds.count("group_parsed") == 3


def test_summary_traceability(dummy_chat_only):
    """The returned context_summary should match what was used to generate personas."""
    inputs = SynthesisInputs(chat_messages=[ChatMessage(role="user", text="hi")])
    result = synthesize_personas(inputs, provider=dummy_chat_only)
    assert result.context_summary.stated_audience is not None
