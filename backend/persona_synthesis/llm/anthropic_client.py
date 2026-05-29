"""Anthropic Claude implementation of the LLMProvider Protocol.

Uses the Messages API with tool-use to force structured JSON output.
"""
from __future__ import annotations

import os
from typing import Any, Iterator

import anthropic

from persona_synthesis.errors import ProviderError
from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    """LLMProvider backed by Anthropic's Messages API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: anthropic.Anthropic | None = None,
    ):
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self._client = client or anthropic.Anthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
    ) -> ToolCallResult:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
        except anthropic.APIError as e:
            raise ProviderError(f"Anthropic API error: {e}") from e

        for block in resp.content:
            if block.type == "tool_use":
                return ToolCallResult(name=block.name, input=dict(block.input), raw=resp)

        raise ProviderError(
            f"Claude did not invoke the forced tool. Stop reason: {resp.stop_reason}"
        )

    def stream(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
    ) -> Iterator[StreamChunk]:
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            ) as stream:
                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block is not None and getattr(block, "type", "") == "tool_use":
                            yield StreamChunk(kind="tool_start", data={"name": block.name})
                    elif etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None:
                            dtype = getattr(delta, "type", "")
                            if dtype == "input_json_delta":
                                yield StreamChunk(
                                    kind="tool_delta",
                                    data={"partial_json": getattr(delta, "partial_json", "")},
                                )
                            elif dtype == "text_delta":
                                yield StreamChunk(
                                    kind="text",
                                    data={"text": getattr(delta, "text", "")},
                                )
                    elif etype == "message_stop":
                        yield StreamChunk(kind="done", data=None)

                final = stream.get_final_message()
                for block in final.content:
                    if block.type == "tool_use":
                        yield StreamChunk(
                            kind="tool_done",
                            data=ToolCallResult(
                                name=block.name, input=dict(block.input), raw=final
                            ).model_dump(),
                        )
                        return

                raise ProviderError(
                    f"Stream ended without a tool call. Stop reason: {final.stop_reason}"
                )
        except anthropic.APIError as e:
            raise ProviderError(f"Anthropic streaming error: {e}") from e
