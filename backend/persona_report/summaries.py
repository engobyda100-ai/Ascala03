"""One LLM call per test type to produce its short_summary."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from persona_synthesis.llm.base import LLMProvider

from persona_report._llm_helpers import call_with_retry, load_prompt
from persona_report.filters import FilteredSlice
from persona_report.schema import Stat


TOOL_NAME = "emit_short_summary"
TOOL_DESCRIPTION = "Emit a 2–4 sentence short_summary for one test type."


class _SummaryOutput(BaseModel):
    short_summary: str = Field(min_length=1)


def generate_short_summary(
    slice_: FilteredSlice,
    stats: list[Stat],
    *,
    data_confidence: str,
    provider: LLMProvider,
) -> tuple[str, int]:
    """Returns (short_summary, tokens_used)."""
    user_text = (
        f"Test type: {slice_.test_type}\n"
        f"Data confidence: {data_confidence}\n\n"
        "Computed key stats (use these numbers, do not invent others):\n"
        f"```json\n{json.dumps([s.model_dump() for s in stats], indent=2)}\n```\n\n"
        f"Affected screens: {slice_.screen_ids or '(none)'}\n"
        f"Cluster counts in this slice: {slice_.cluster_counts or '(none)'}\n"
        f"Number of categorized issues in this section: {len(slice_.issues)}\n"
        f"Touchpoint count (used for confidence): {slice_.touchpoint_count}\n\n"
        "Emit the short_summary tool call now. 2–4 sentences. Plain English. "
        "If test_type is 'retention', INCLUDE the predictive disclaimer. "
        "If data_confidence is 'low', acknowledge it."
    )
    system = load_prompt("test_type_summary.md")
    out, tokens = call_with_retry(
        provider,
        system=system,
        user_content=[{"type": "text", "text": user_text}],
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=_SummaryOutput,
    )
    return out.short_summary, tokens
