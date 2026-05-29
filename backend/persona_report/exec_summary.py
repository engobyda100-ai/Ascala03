"""Optional cross-test-type executive summary."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from persona_synthesis.llm.base import LLMProvider

from persona_report._llm_helpers import call_with_retry, load_prompt
from persona_report.schema import TestTypeReport


TOOL_NAME = "emit_executive_summary"
TOOL_DESCRIPTION = "Emit a single-paragraph executive summary across all six test-type sections."


class _ExecSummaryOutput(BaseModel):
    executive_summary: str = Field(min_length=1)


def generate(
    test_type_reports: list[TestTypeReport],
    *,
    provider: LLMProvider,
) -> tuple[str, int]:
    """Returns (executive_summary, tokens_used)."""
    digest = [
        {
            "test_type": tt.test_type,
            "data_confidence": tt.data_confidence,
            "short_summary": tt.short_summary,
            "key_stats": [s.model_dump() for s in tt.key_stats],
            "n_fixes": len(tt.recommended_fixes),
        }
        for tt in test_type_reports
    ]
    user_text = (
        "Per-test-type digest from the run:\n"
        f"```json\n{json.dumps(digest, indent=2)}\n```\n\n"
        "Emit the executive_summary now via the emit_executive_summary tool. "
        "One paragraph, 4–8 sentences, plain English. Use the actual numbers. "
        "Flag low-confidence findings explicitly. Retention is predictive only."
    )
    system = load_prompt("exec_summary.md")
    out, tokens = call_with_retry(
        provider,
        system=system,
        user_content=[{"type": "text", "text": user_text}],
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=_ExecSummaryOutput,
    )
    return out.executive_summary, tokens
