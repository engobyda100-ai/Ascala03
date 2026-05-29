"""Shared test fixtures: DummyProvider + canned outputs + sample SimulationResult."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from persona_simulation.schema import SimulationResult
from persona_synthesis.llm.base import StreamChunk, ToolCallResult


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ────────────── fixture loaders ──────────────

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def sample_simulation() -> SimulationResult:
    raw = _load("sample_simulation_result.json")
    return SimulationResult.model_validate(raw)


@pytest.fixture
def mock_summary_dict() -> dict:
    return _load("mock_test_type_summary.json")


@pytest.fixture
def mock_fix_dict() -> dict:
    return _load("mock_fix.json")


@pytest.fixture
def mock_fix_bad_dict() -> dict:
    return _load("mock_fix_bad_format.json")


@pytest.fixture
def mock_exec_summary_dict() -> dict:
    return _load("mock_exec_summary.json")


# ────────────── DummyProvider: by-tool, cycling ──────────────

class ByToolDummyProvider:
    """Round-robin returns canned responses keyed by tool_choice name."""

    def __init__(self, by_tool: dict[str, list[dict]],
                 *, default_tokens: tuple[int, int] = (2_000, 400)):
        self._by_tool = {k: list(v) for k, v in by_tool.items()}
        self._idx = {k: 0 for k in self._by_tool}
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
                f"ByToolDummyProvider has no canned responses for {name!r}"
            )
        i = self._idx[name] % len(queue)
        self._idx[name] += 1
        in_tok, out_tok = self._default_tokens
        return ToolCallResult(
            name=name, input=queue[i],
            raw={"input_tokens": in_tok, "output_tokens": out_tok},
        )

    def stream(self, *, system, messages, tools, tool_choice) -> Iterator[StreamChunk]:
        result = self.complete(system=system, messages=messages, tools=tools, tool_choice=tool_choice)
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


# ────────────── factory fixtures ──────────────

@pytest.fixture
def make_provider(mock_summary_dict, mock_fix_dict, mock_exec_summary_dict):
    """Default factory: stocks summary + fix + exec_summary so end-to-end runs."""
    def _factory(*,
                 fix_overrides: list[dict] | None = None,
                 summary_overrides: list[dict] | None = None,
                 exec_override: dict | None = None) -> ByToolDummyProvider:
        return ByToolDummyProvider({
            "emit_short_summary": summary_overrides or [mock_summary_dict],
            "emit_fix": fix_overrides or [mock_fix_dict],
            "emit_executive_summary": [exec_override or mock_exec_summary_dict],
        })
    return _factory


@pytest.fixture
def default_provider(make_provider) -> ByToolDummyProvider:
    return make_provider()
