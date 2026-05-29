"""Shared helpers for LLM-calling modules.

Each tool-use call in this package follows the same pattern:
  1. Call the provider with a forced tool (tool_choice)
  2. Validate the returned `input` against a pydantic model
  3. On ValidationError: one retry with a stricter "previous output failed" suffix
  4. On second failure: raise SchemaValidationError

This helper factors that out so every module doesn't re-implement it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from persona_simulation.errors import SchemaValidationError
from persona_synthesis.llm.base import LLMProvider, ToolCallResult


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def tool_def(name: str, description: str, model: Type[BaseModel]) -> dict:
    """Build an Anthropic tool definition from a pydantic model."""
    return {
        "name": name,
        "description": description,
        "input_schema": model.model_json_schema(),
    }


def tool_choice(name: str) -> dict:
    return {"type": "tool", "name": name}


def _tokens_from_raw(raw) -> int:
    """Best-effort extraction of total token usage from a provider response.

    Anthropic raw response has `usage.input_tokens` and `usage.output_tokens`.
    DummyProvider stores a dict in `raw` with keys `input_tokens`/`output_tokens`.
    Return 0 if we can't tell.
    """
    if raw is None:
        return 0
    if isinstance(raw, dict):
        return int(raw.get("input_tokens", 0)) + int(raw.get("output_tokens", 0))
    usage = getattr(raw, "usage", None)
    if usage is None:
        return 0
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    return int(in_tok) + int(out_tok)


T = TypeVar("T", bound=BaseModel)


def call_with_retry(
    provider: LLMProvider,
    *,
    system: str,
    user_content: list[dict],
    tool_name: str,
    tool_description: str,
    output_model: Type[T],
) -> tuple[T, int]:
    """Call provider with forced tool-use, validate, retry once on ValidationError.

    Returns (validated_model, tokens_used). Raises SchemaValidationError after
    two failed attempts.
    """
    tools = [tool_def(tool_name, tool_description, output_model)]
    choice = tool_choice(tool_name)
    messages = [{"role": "user", "content": user_content}]

    first = provider.complete(
        system=system, messages=messages, tools=tools, tool_choice=choice,
    )
    tokens = _tokens_from_raw(first.raw)
    try:
        return output_model.model_validate(first.input), tokens
    except ValidationError as e1:
        retry_system = (
            system
            + "\n\n---\nRETRY ADDENDUM\nYour previous output failed schema validation:\n"
            f"{e1.errors()}\n"
            "Re-read the required schema. Emit the tool call again, correcting every error."
        )
        second = provider.complete(
            system=retry_system, messages=messages, tools=tools, tool_choice=choice,
        )
        tokens += _tokens_from_raw(second.raw)
        try:
            return output_model.model_validate(second.input), tokens
        except ValidationError as e2:
            raise SchemaValidationError(
                attempts=2, last_errors=e2.errors(), raw_output=second.input
            ) from e2
