"""Shared utilities for summarizers."""
from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from persona_synthesis.errors import SchemaValidationError
from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.schema import ContextSummary


PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
SUMMARY_TOOL_NAME = "emit_summary"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def summary_tool_def() -> dict:
    """Claude tool definition matching the ContextSummary schema."""
    return {
        "name": SUMMARY_TOOL_NAME,
        "description": "Emit a normalized ContextSummary for the input.",
        "input_schema": ContextSummary.model_json_schema(),
    }


def tool_choice() -> dict:
    return {"type": "tool", "name": SUMMARY_TOOL_NAME}


def call_and_validate(
    provider: LLMProvider,
    *,
    system: str,
    user_content: list[dict],
) -> ContextSummary:
    """One call with tool-use + pydantic validation (no retry at this layer).

    Summarizers don't retry on their own — orchestrator retries the whole chain
    if persona synthesis fails. Summarizer failure raises immediately.
    """
    result = provider.complete(
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=[summary_tool_def()],
        tool_choice=tool_choice(),
    )
    try:
        return ContextSummary.model_validate(result.input)
    except ValidationError as e:
        raise SchemaValidationError(
            attempts=1, last_errors=e.errors(), raw_output=result.input
        ) from e
