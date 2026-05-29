"""Provider-agnostic interface for LLM calls with tool-use.

This is the only seam the synthesis pipeline depends on — swap to any
provider by implementing this Protocol.
"""
from __future__ import annotations

from typing import Any, Iterator, Protocol

from pydantic import BaseModel


class ToolCallResult(BaseModel):
    """The structured output from a tool-use-forced LLM call."""
    name: str          # tool name the model invoked
    input: dict        # raw dict (caller validates against pydantic)
    raw: Any = None    # provider-specific response for debugging


class StreamChunk(BaseModel):
    """One event in a streaming response."""
    kind: str          # "text", "tool_start", "tool_delta", "tool_done", "done"
    data: Any = None


class LLMProvider(Protocol):
    """Minimal surface: one non-streaming call, one streaming call.

    Both take a system prompt, a message list, a tools list, and a tool_choice
    dict (forcing a specific tool). Both return a single ToolCallResult by the
    end of the call; streaming just lets the caller observe progress.
    """

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
    ) -> ToolCallResult:
        ...

    def stream(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
    ) -> Iterator[StreamChunk]:
        ...


# StreamEvent is re-exported from schema for convenience
from persona_synthesis.schema import StreamEvent  # noqa: E402

__all__ = ["LLMProvider", "ToolCallResult", "StreamChunk", "StreamEvent"]
