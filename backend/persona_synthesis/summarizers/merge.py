"""Combine a files-based and chat-based ContextSummary.

When both inputs are present, we have two independent passes. `combine` unions
list fields and prefers chat-sourced scalars when the user explicitly stated
them (the chat transcript is where the product owner tells us what they think).
"""
from __future__ import annotations

from persona_synthesis.schema import ContextSummary


def _merge_lists(a: list[str], b: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for x in [*a, *b]:
        if x and x not in seen:
            seen[x] = None
    return list(seen.keys())


def combine(files_summary: ContextSummary, chat_summary: ContextSummary) -> ContextSummary:
    return ContextSummary(
        app_category=chat_summary.app_category or files_summary.app_category,
        stated_audience=chat_summary.stated_audience or files_summary.stated_audience,
        pricing_model=chat_summary.pricing_model
        if chat_summary.pricing_model != "unknown"
        else files_summary.pricing_model,
        apparent_complexity=chat_summary.apparent_complexity or files_summary.apparent_complexity,
        geography_signals=_merge_lists(files_summary.geography_signals, chat_summary.geography_signals),
        industry_signals=_merge_lists(files_summary.industry_signals, chat_summary.industry_signals),
        uploaded_research=[*files_summary.uploaded_research, *chat_summary.uploaded_research],
        raw_notes="\n\n".join(x for x in [files_summary.raw_notes, chat_summary.raw_notes] if x),
    )
