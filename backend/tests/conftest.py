"""Shared test fixtures: DummyProvider + canned responses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult


FIXTURES = Path(__file__).parent / "fixtures"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def mock_summary_dict() -> dict:
    return _load_json("mock_summary.json")


@pytest.fixture
def mock_bundle_dict() -> dict:
    return _load_json("mock_bundle.json")


@pytest.fixture
def bad_bundle_dict() -> dict:
    return _load_json("bad_bundle.json")


class DummyProvider:
    """Replays a queue of canned ToolCallResults. Records every call."""

    def __init__(self, responses: list[ToolCallResult]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        self.calls.append(
            {"system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice}
        )
        if not self._responses:
            raise AssertionError("DummyProvider ran out of canned responses")
        return self._responses.pop(0)

    def stream(self, *, system, messages, tools, tool_choice) -> Iterator[StreamChunk]:
        result = self.complete(
            system=system, messages=messages, tools=tools, tool_choice=tool_choice
        )
        # Emit a single tool_done chunk followed by done — enough to exercise the
        # stream path in synthesize_personas.
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


@pytest.fixture
def make_dummy(mock_summary_dict: dict, mock_bundle_dict: dict):
    """Factory: pass in the sequence of tool outputs you want."""
    def _factory(*tool_outputs: dict | tuple[str, dict]) -> DummyProvider:
        responses: list[ToolCallResult] = []
        for item in tool_outputs:
            if isinstance(item, tuple):
                name, input_ = item
            else:
                # Infer tool name from schema shape
                if "groups" in item:
                    name = "emit_personas"
                else:
                    name = "emit_summary"
                input_ = item
            responses.append(ToolCallResult(name=name, input=input_))
        return DummyProvider(responses)

    return _factory


@pytest.fixture
def dummy_chat_only(make_dummy, mock_summary_dict, mock_bundle_dict) -> DummyProvider:
    """Chat-only path: one summary call + one persona call."""
    return make_dummy(mock_summary_dict, mock_bundle_dict)


@pytest.fixture
def dummy_files_only(make_dummy, mock_summary_dict, mock_bundle_dict) -> DummyProvider:
    """Files-only path: one summary call + one persona call."""
    return make_dummy(mock_summary_dict, mock_bundle_dict)


@pytest.fixture
def dummy_both(make_dummy, mock_summary_dict, mock_bundle_dict) -> DummyProvider:
    """Both paths: two summary calls + one persona call."""
    return make_dummy(mock_summary_dict, mock_summary_dict, mock_bundle_dict)
