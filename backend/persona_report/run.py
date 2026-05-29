"""CLI for persona_report.

Usage:
    python -m persona_report.run \
        --simulation path/to/sim.json \
        --output path/to/report.json \
        [--exec-summary] [--mock] [--mock-fixtures DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from persona_simulation.schema import SimulationResult
from persona_synthesis.llm.base import StreamChunk, ToolCallResult

from persona_report.generator import generate_report


# ──────────────────────────── mock provider ────────────────────────────

class _CLIDummyProvider:
    """Replays canned ToolCallResults by tool name (cycles forever)."""

    def __init__(self, by_tool: dict[str, list[dict]]):
        self._by_tool = {k: list(v) for k, v in by_tool.items()}
        self._idx: dict[str, int] = {k: 0 for k in self._by_tool}
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        self.calls.append({
            "system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice,
        })
        name = tool_choice.get("name") if isinstance(tool_choice, dict) else None
        if name is None or name not in self._by_tool:
            raise RuntimeError(f"mock provider has no responses for tool {name!r}")
        queue = self._by_tool[name]
        if not queue:
            raise RuntimeError(f"mock provider out of responses for tool {name!r}")
        i = self._idx[name] % len(queue)
        self._idx[name] += 1
        payload = queue[i]
        return ToolCallResult(
            name=name, input=payload,
            raw={"input_tokens": 2000, "output_tokens": 400},
        )

    def stream(self, *, system, messages, tools, tool_choice) -> Iterable[StreamChunk]:
        result = self.complete(system=system, messages=messages, tools=tools, tool_choice=tool_choice)
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


def _build_mock_provider(fixtures_dir: Path) -> _CLIDummyProvider:
    def load(name: str) -> dict:
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))
    summary = load("mock_test_type_summary.json")
    fix = load("mock_fix.json")
    exec_s = load("mock_exec_summary.json")
    return _CLIDummyProvider({
        "emit_short_summary": [summary],
        "emit_fix": [fix],
        "emit_executive_summary": [exec_s],
    })


# ──────────────────────────── CLI main ────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m persona_report.run",
        description="Turn a SimulationResult into a structured Report.",
    )
    parser.add_argument("--simulation", required=True, type=Path,
                        help="JSON file holding a SimulationResult")
    parser.add_argument("--output", type=Path, default=None,
                        help="Where to write the Report JSON (default: stdout)")
    parser.add_argument("--exec-summary", action="store_true",
                        help="Include the optional cross-test-type executive summary")
    parser.add_argument("--mock", action="store_true",
                        help="Use bundled fixture responses; no network")
    parser.add_argument("--mock-fixtures", type=Path, default=None,
                        help="Override fixture dir (default: persona_report/tests/fixtures)")
    parser.add_argument("--simulation-run-id", type=str, default=None,
                        help="Opaque id to stamp into report.meta")

    args = parser.parse_args(argv)

    try:
        sim_data = json.loads(args.simulation.read_text(encoding="utf-8"))
        sim = SimulationResult.model_validate(sim_data)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"error loading simulation: {e}", file=sys.stderr)
        return 2

    provider = None
    if args.mock:
        default_fixtures = Path(__file__).resolve().parent / "tests" / "fixtures"
        fixtures_dir = args.mock_fixtures or default_fixtures
        if not fixtures_dir.is_dir():
            print(f"error: --mock fixtures dir not found: {fixtures_dir}", file=sys.stderr)
            return 2
        provider = _build_mock_provider(fixtures_dir)

    try:
        report = generate_report(
            sim,
            provider=provider,
            include_executive_summary=args.exec_summary,
            simulation_run_id=args.simulation_run_id,
        )
    except Exception as e:
        print(f"error generating report: {e}", file=sys.stderr)
        return 4

    out_json = json.dumps(report.model_dump(), indent=2, default=str)
    if args.output is not None:
        args.output.write_text(out_json + "\n", encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
