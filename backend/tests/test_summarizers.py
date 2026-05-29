"""Summarizer unit tests: chat, files, and merge."""
from __future__ import annotations

import pytest

from persona_synthesis.parsers.base import ParsedFile
from persona_synthesis.schema import ChatMessage, ContextSummary, ResearchRef
from persona_synthesis.summarizers import summarize_chat, summarize_files
from persona_synthesis.summarizers.merge import combine


def test_summarize_chat_invokes_provider(make_dummy, mock_summary_dict):
    provider = make_dummy(mock_summary_dict)
    summary = summarize_chat(
        [ChatMessage(role="user", text="We target small agencies.")],
        provider,
    )
    assert isinstance(summary, ContextSummary)
    assert summary.app_category == "B2B project management"
    assert len(provider.calls) == 1
    # Transcript should appear in the user content
    user_content = provider.calls[0]["messages"][0]["content"]
    assert "small agencies" in user_content[0]["text"]


def test_summarize_chat_empty_raises():
    class Never:
        def complete(self, **_): raise AssertionError("should not be called")
        def stream(self, **_): raise AssertionError("should not be called")
    with pytest.raises(ValueError):
        summarize_chat([], Never())


def test_summarize_files_text_only(make_dummy, mock_summary_dict):
    provider = make_dummy(mock_summary_dict)
    parsed = [
        ParsedFile(name="notes.txt", kind="text", text="We target EU founders.", excerpt="…"),
    ]
    summary = summarize_files(parsed, provider)
    assert isinstance(summary, ContextSummary)
    # Provider should have been called with one text block and no image blocks
    user_content = provider.calls[0]["messages"][0]["content"]
    assert len([c for c in user_content if c.get("type") == "image"]) == 0


def test_summarize_files_with_image_block(make_dummy, mock_summary_dict):
    provider = make_dummy(mock_summary_dict)
    img_block = {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "fake"},
    }
    parsed = [
        ParsedFile(
            name="shot.png",
            kind="image",
            text="",
            image_block=img_block,
            excerpt="100×100 PNG",
        ),
    ]
    summary = summarize_files(parsed, provider)
    assert isinstance(summary, ContextSummary)
    user_content = provider.calls[0]["messages"][0]["content"]
    img_blocks = [c for c in user_content if c.get("type") == "image"]
    assert len(img_blocks) == 1
    assert img_blocks[0]["source"]["data"] == "fake"


def test_summarize_files_falls_back_to_our_refs_when_llm_omits_them(
    make_dummy, mock_summary_dict
):
    """If the LLM returned an empty uploaded_research list, our tracked refs fill in."""
    modified = {**mock_summary_dict, "uploaded_research": []}
    provider = make_dummy(modified)
    parsed = [ParsedFile(name="notes.txt", kind="text", text="hi", excerpt="hi")]
    summary = summarize_files(parsed, provider)
    assert len(summary.uploaded_research) == 1
    assert summary.uploaded_research[0].name == "notes.txt"


def test_summarize_files_requires_input():
    class Never:
        def complete(self, **_): raise AssertionError
        def stream(self, **_): raise AssertionError
    with pytest.raises(ValueError):
        summarize_files([], Never())


def test_merge_unions_lists_and_prefers_chat_for_audience():
    files_sum = ContextSummary(
        app_category="from files",
        stated_audience="from files",
        pricing_model="unknown",
        apparent_complexity="moderate",
        geography_signals=["US"],
        industry_signals=["SaaS"],
        uploaded_research=[ResearchRef(name="a.pdf", kind="pdf")],
        raw_notes="files notes",
    )
    chat_sum = ContextSummary(
        app_category="from chat",
        stated_audience="from chat",
        pricing_model="subscription",
        apparent_complexity="simple",
        geography_signals=["EU"],
        industry_signals=["SaaS", "consulting"],
        uploaded_research=[],
        raw_notes="chat notes",
    )
    merged = combine(files_sum, chat_sum)
    assert merged.stated_audience == "from chat"
    assert merged.pricing_model == "subscription"
    assert merged.geography_signals == ["US", "EU"]
    assert merged.industry_signals == ["SaaS", "consulting"]
    assert "files notes" in merged.raw_notes
    assert "chat notes" in merged.raw_notes
    assert merged.uploaded_research[0].name == "a.pdf"
