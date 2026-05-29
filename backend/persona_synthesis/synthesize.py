"""Public entrypoint: synthesize_personas()."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from pydantic import ValidationError

from persona_synthesis.errors import SchemaValidationError
from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult
from persona_synthesis.parsers.base import parse_file
from persona_synthesis.schema import (
    ContextSummary,
    PersonaBundle,
    StreamEvent,
    SynthesisInputs,
    SynthesisResult,
)
from persona_synthesis.summarizers import combine, summarize_chat, summarize_files


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PERSONA_TOOL_NAME = "emit_personas"


def _persona_tool_def() -> dict:
    return {
        "name": PERSONA_TOOL_NAME,
        "description": "Emit exactly 3 PersonaGroups as a PersonaBundle.",
        "input_schema": PersonaBundle.model_json_schema(),
    }


def _tool_choice() -> dict:
    return {"type": "tool", "name": PERSONA_TOOL_NAME}


def _load_system_prompt() -> str:
    return (PROMPTS_DIR / "persona_synthesis.md").read_text(encoding="utf-8")


def _build_user_content(summary: ContextSummary, image_blocks: list[dict]) -> list[dict]:
    """The user turn handed to Claude for the persona call."""
    summary_json = json.dumps(summary.model_dump(), indent=2)
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Normalized context summary (derived from the product owner's "
                "inputs — use this as the source of truth for differentiation "
                "axes that matter most for this app):\n\n"
                f"```json\n{summary_json}\n```\n\n"
                "Now emit 3 distinct PersonaGroups via the emit_personas tool."
            ),
        }
    ]
    # Attach any screenshot image blocks so Claude can see them while synthesizing.
    content.extend(image_blocks)
    return content


def _invoke_with_validation(
    provider: LLMProvider,
    *,
    system: str,
    user_content: list[dict],
) -> PersonaBundle:
    """One call → validate. On ValidationError, one retry with stricter system."""
    first = provider.complete(
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=[_persona_tool_def()],
        tool_choice=_tool_choice(),
    )
    try:
        return PersonaBundle.model_validate(first.input)
    except ValidationError as e1:
        retry_system = (
            system
            + "\n\n---\nRETRY ADDENDUM\nYour previous output failed schema validation "
            f"with errors:\n{e1.errors()}\n"
            "Re-read the required schema carefully. Emit the tool call again. "
            "Every field is required. The three estimated_share_pct values MUST sum "
            "to ~100 (between 98 and 102). Use exactly 3 groups."
        )
        second = provider.complete(
            system=retry_system,
            messages=[{"role": "user", "content": user_content}],
            tools=[_persona_tool_def()],
            tool_choice=_tool_choice(),
        )
        try:
            return PersonaBundle.model_validate(second.input)
        except ValidationError as e2:
            raise SchemaValidationError(
                attempts=2, last_errors=e2.errors(), raw_output=second.input
            ) from e2


def _collect_image_blocks(inputs: SynthesisInputs) -> tuple[list, list[dict]]:
    """Parse all files up-front; return (parsed_files, image_blocks)."""
    parsed = [parse_file(f) for f in inputs.files]
    image_blocks = [p.image_block for p in parsed if p.image_block is not None]
    return parsed, image_blocks


def _build_summary(
    inputs: SynthesisInputs,
    parsed: list,
    provider: LLMProvider,
) -> ContextSummary:
    """Route inputs through one, the other, or both summarizers."""
    has_files = bool(parsed) or bool(inputs.product_url)
    has_chat = bool(inputs.chat_messages)

    if not has_files and not has_chat:
        raise ValueError(
            "synthesize_personas requires at least one of: files, chat_messages, product_url"
        )

    if has_files and has_chat:
        f_sum = summarize_files(parsed, provider, product_url=inputs.product_url)
        c_sum = summarize_chat(inputs.chat_messages, provider)
        return combine(f_sum, c_sum)
    if has_files:
        return summarize_files(parsed, provider, product_url=inputs.product_url)
    return summarize_chat(inputs.chat_messages, provider)


def synthesize_personas(
    inputs: SynthesisInputs,
    *,
    provider: Optional[LLMProvider] = None,
    stream: bool = False,
    on_event: Optional[Callable[[StreamEvent], None]] = None,
) -> SynthesisResult:
    """Run the full pipeline: parse → summarize → synthesize → validate.

    Args:
        inputs: caller's files + chat + optional URL.
        provider: any LLMProvider. Defaults to AnthropicProvider() — lazily imported.
        stream: if True, emit StreamEvents to `on_event` during synthesis.
        on_event: callback for stream events (only meaningful when stream=True).

    Returns:
        SynthesisResult with `groups` (3 PersonaGroups) and the `context_summary`
        used to produce them.

    Raises:
        SchemaValidationError: LLM output failed schema validation twice.
        ValueError: inputs were empty.
        ProviderError: provider-level failure.
    """
    if provider is None:
        # Lazy import so offline tests don't pull anthropic SDK at import time.
        from persona_synthesis.llm.anthropic_client import AnthropicProvider
        provider = AnthropicProvider()

    emit = on_event or (lambda _ev: None)

    parsed, image_blocks = _collect_image_blocks(inputs)
    summary = _build_summary(inputs, parsed, provider)
    emit(StreamEvent(kind="summary_done", data=summary.model_dump()))

    system = _load_system_prompt()
    user_content = _build_user_content(summary, image_blocks)

    if stream:
        bundle = _stream_with_validation(
            provider, system=system, user_content=user_content, emit=emit
        )
    else:
        bundle = _invoke_with_validation(
            provider, system=system, user_content=user_content
        )

    emit(StreamEvent(kind="done", data=None))
    return SynthesisResult(groups=list(bundle.groups), context_summary=summary)


def _stream_with_validation(
    provider: LLMProvider,
    *,
    system: str,
    user_content: list[dict],
    emit: Callable[[StreamEvent], None],
) -> PersonaBundle:
    """Stream events; on completion, validate the tool call. Retry non-streamed."""
    tool_result: ToolCallResult | None = None
    for chunk in provider.stream(
        system=system,
        messages=[{"role": "user", "content": user_content}],
        tools=[_persona_tool_def()],
        tool_choice=_tool_choice(),
    ):
        if chunk.kind == "tool_delta":
            emit(StreamEvent(kind="token", data=chunk.data))
        elif chunk.kind == "tool_done":
            # chunk.data is a ToolCallResult.model_dump()
            tool_result = ToolCallResult.model_validate(chunk.data)
        # other kinds are informational; we drop them
    if tool_result is None:
        raise SchemaValidationError(
            attempts=1, last_errors="stream ended without a tool call", raw_output=None
        )
    try:
        bundle = PersonaBundle.model_validate(tool_result.input)
        for g in bundle.groups:
            emit(StreamEvent(kind="group_parsed", data=g.model_dump()))
        return bundle
    except ValidationError as e1:
        # Retry non-streamed for simplicity
        return _invoke_with_validation(
            provider,
            system=system
            + "\n\n---\nRETRY ADDENDUM\nPrevious output failed schema validation: "
            f"{e1.errors()}. Re-emit the tool call with valid schema.",
            user_content=user_content,
        )
