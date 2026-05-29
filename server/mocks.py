"""Mock LLM providers for local-dev mode.

Synthesis: bypasses `synthesize_personas()` and returns a static fixture
(loaded from `server/mocks/mock_synthesis_result.json`). The synthesis
package has no built-in mock mode, and replicating its multi-call pipeline
with canned tool responses is more brittle than just returning the result.

Simulation/Report: lift the `_CLIDummyProvider` pattern from
`persona_simulation/run.py` and `persona_report/run.py` and point at the
existing fixture directories shipped with each package.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult
from persona_synthesis.schema import SynthesisResult


SERVER_DIR = Path(__file__).resolve().parent
MOCK_SYNTHESIS_RESULT_PATH = SERVER_DIR / "mocks" / "mock_synthesis_result.json"

# Fixture directories live alongside each backend package.
BACKEND_DIR = SERVER_DIR.parent / "backend"
SIMULATION_FIXTURES = BACKEND_DIR / "persona_simulation" / "tests" / "fixtures"
REPORT_FIXTURES = BACKEND_DIR / "persona_report" / "tests" / "fixtures"


def load_mock_synthesis_result() -> SynthesisResult:
    raw = MOCK_SYNTHESIS_RESULT_PATH.read_text(encoding="utf-8")
    return SynthesisResult.model_validate_json(raw)


# ──────────────────────────── shared dummy provider ────────────────────────────


class _DummyProvider:
    """Replays canned ToolCallResults by tool name.

    Modes:
    - "pop": consume entries (errors when exhausted) — matches simulation CLI.
    - "cycle": cycle through entries forever — matches report CLI.
    """

    def __init__(self, by_tool: dict[str, list[dict]], mode: str = "pop"):
        self._by_tool: dict[str, list[dict]] = {k: list(v) for k, v in by_tool.items()}
        self._idx: dict[str, int] = {k: 0 for k in self._by_tool}
        self._mode = mode

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        name = tool_choice.get("name") if isinstance(tool_choice, dict) else None
        if name is None or name not in self._by_tool:
            raise RuntimeError(
                f"mock provider has no responses for tool {name!r}; "
                f"available: {list(self._by_tool.keys())}"
            )
        queue = self._by_tool[name]
        if self._mode == "cycle":
            i = self._idx[name] % len(queue)
            self._idx[name] += 1
            payload = queue[i]
        else:  # pop
            if not queue:
                raise RuntimeError(f"mock provider out of canned responses for tool {name!r}")
            payload = queue.pop(0)
        return ToolCallResult(
            name=name,
            input=payload,
            raw={"input_tokens": 2000, "output_tokens": 400},
        )

    def stream(self, *, system, messages, tools, tool_choice) -> Iterable[StreamChunk]:
        result = self.complete(system=system, messages=messages, tools=tools, tool_choice=tool_choice)
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_simulation_mock_provider(fixtures_dir: Path = SIMULATION_FIXTURES) -> LLMProvider:
    """Mirrors persona_simulation.run._build_mock_provider."""
    graph = _load(fixtures_dir / "mock_screen_graph.json")
    issues = _load(fixtures_dir / "mock_categorized_issues.json")
    report_narrative = _load(fixtures_dir / "mock_report.json")
    backstory = _load(fixtures_dir / "mock_backstory.json")
    decision = _load(fixtures_dir / "mock_decision.json")

    n_seeds = 32        # generous; covers 3 groups × default seeds
    n_decisions = 400   # covers 150-agent × 12-step runs
    return _DummyProvider(
        {
            "emit_screen_graph": [graph],
            "emit_backstory": [backstory] * n_seeds,
            "emit_decision": [decision] * n_decisions,
            "emit_categorized_issues": [issues],
            "emit_report": [report_narrative],
        },
        mode="pop",
    )


def build_report_mock_provider(fixtures_dir: Path = REPORT_FIXTURES) -> LLMProvider:
    """Mirrors persona_report.run._build_mock_provider."""
    summary = _load(fixtures_dir / "mock_test_type_summary.json")
    fix = _load(fixtures_dir / "mock_fix.json")
    exec_s = _load(fixtures_dir / "mock_exec_summary.json")
    return _DummyProvider(
        {
            "emit_short_summary": [summary],
            "emit_fix": [fix],
            "emit_executive_summary": [exec_s],
        },
        mode="cycle",
    )
