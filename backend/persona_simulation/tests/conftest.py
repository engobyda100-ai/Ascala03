"""Test fixtures: DummyProvider variants + canned JSON outputs.

Cloned from `persona_synthesis/tests/conftest.py` but adapted for this
module's tool set (emit_screen_graph, emit_backstory, emit_decision,
emit_categorized_issues, emit_report).

The DummyProvider here supports two modes:
- Queue mode: pops canned ToolCallResults from a single queue (simple pattern)
- By-tool mode: looks up the next response by the requested tool name
  (more forgiving when the call order is hard to pin down, e.g. in the
  runner where decisions interleave with categorize/report)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ────────────── fixture loaders as pytest fixtures ──────────────

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def mock_screen_graph_dict() -> dict:
    return _load("mock_screen_graph.json")


@pytest.fixture
def bad_screen_graph_dict() -> dict:
    return _load("bad_screen_graph.json")


@pytest.fixture
def mock_backstory_dict() -> dict:
    return _load("mock_backstory.json")


@pytest.fixture
def mock_decision_dict() -> dict:
    return _load("mock_decision.json")


@pytest.fixture
def mock_decision_low_conf_dict() -> dict:
    return _load("mock_decision_low_conf.json")


@pytest.fixture
def mock_decision_complete_dict() -> dict:
    return _load("mock_decision_complete.json")


@pytest.fixture
def mock_decision_give_up_dict() -> dict:
    return _load("mock_decision_give_up.json")


@pytest.fixture
def mock_categorized_issues_dict() -> dict:
    return _load("mock_categorized_issues.json")


@pytest.fixture
def mock_report_dict() -> dict:
    return _load("mock_report.json")


@pytest.fixture
def sample_personas() -> list[dict]:
    return _load("sample_personas.json")["groups"]


# ────────────── DummyProvider: queue mode ──────────────

class DummyProvider:
    """Pops canned ToolCallResults from a queue in call order."""

    def __init__(self, responses: list[ToolCallResult]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        self.calls.append({
            "system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice,
        })
        if not self._responses:
            raise AssertionError("DummyProvider ran out of canned responses")
        return self._responses.pop(0)

    def stream(self, *, system, messages, tools, tool_choice) -> Iterator[StreamChunk]:
        result = self.complete(system=system, messages=messages, tools=tools, tool_choice=tool_choice)
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


# ────────────── DummyProvider: by-tool mode ──────────────

class ByToolDummyProvider:
    """Picks the next canned response for the requested tool name.

    Use this for runner tests where many decision calls interleave with
    a screen_graph / categorize / report call — order is predictable per
    tool but not globally.
    """

    def __init__(
        self,
        by_tool: dict[str, list[dict]],
        *,
        default_tokens: tuple[int, int] = (5_000, 500),
    ):
        self._by_tool: dict[str, list[dict]] = {k: list(v) for k, v in by_tool.items()}
        self._default_tokens = default_tokens
        self.calls: list[dict] = []
        self.calls_by_tool: dict[str, int] = {}

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        self.calls.append({
            "system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice,
        })
        name = tool_choice["name"] if isinstance(tool_choice, dict) else None
        if name is None:
            raise AssertionError("ByToolDummyProvider requires forced tool_choice name")
        self.calls_by_tool[name] = self.calls_by_tool.get(name, 0) + 1
        queue = self._by_tool.get(name)
        if not queue:
            raise AssertionError(
                f"ByToolDummyProvider out of canned responses for tool {name!r}"
            )
        payload = queue.pop(0)
        in_tok, out_tok = self._default_tokens
        return ToolCallResult(
            name=name, input=payload,
            raw={"input_tokens": in_tok, "output_tokens": out_tok},
        )

    def stream(self, *, system, messages, tools, tool_choice) -> Iterator[StreamChunk]:
        result = self.complete(system=system, messages=messages, tools=tools, tool_choice=tool_choice)
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


@pytest.fixture
def make_dummy():
    """Factory for queue-mode DummyProvider."""
    def _factory(*tool_outputs) -> DummyProvider:
        responses: list[ToolCallResult] = []
        for item in tool_outputs:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                name, input_ = item
                responses.append(ToolCallResult(
                    name=name, input=input_,
                    raw={"input_tokens": 5000, "output_tokens": 500},
                ))
            else:
                # Infer tool name by payload shape
                payload = item
                if "screens" in payload and "entry_screen_id" in payload:
                    name = "emit_screen_graph"
                elif "backstory" in payload:
                    name = "emit_backstory"
                elif "action" in payload and "confidence" in payload:
                    name = "emit_decision"
                elif "issues" in payload and (not payload["issues"] or "category" in payload["issues"][0]):
                    name = "emit_categorized_issues"
                elif "executive_summary" in payload:
                    name = "emit_report"
                else:
                    raise AssertionError(f"make_dummy cannot infer tool name for payload keys={list(payload.keys())}")
                responses.append(ToolCallResult(
                    name=name, input=payload,
                    raw={"input_tokens": 5000, "output_tokens": 500},
                ))
        return DummyProvider(responses)
    return _factory


@pytest.fixture
def make_by_tool_dummy():
    """Factory for by-tool-lookup DummyProvider."""
    def _factory(by_tool: dict[str, list[dict]], **kw) -> ByToolDummyProvider:
        return ByToolDummyProvider(by_tool, **kw)
    return _factory
