"""CLI entrypoint for persona_simulation.

Usage:
    python -m persona_simulation.run \
        --personas path/to/personas.json \
        --screenshots path/to/dir \
        --goal "complete signup"

Flags:
    --mock                 Use a bundled DummyProvider with canned fixture outputs;
                           runs end-to-end without touching the network.
    --config-json PATH     Override SimulationConfig defaults.
    --graph-override PATH  Skip screen-graph build; use this JSON file instead.
    --out PATH             Write SimulationResult JSON to file instead of stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

from persona_synthesis.llm.base import LLMProvider, StreamChunk, ToolCallResult
from persona_synthesis.schema import PersonaGroup, UploadedFile

from persona_simulation.runner import simulate
from persona_simulation.schema import (
    ScreenGraph,
    SimulationConfig,
    SimulationInputs,
)


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


# ──────────────────────────── input loading ────────────────────────────

def _load_personas(path: Path) -> list[PersonaGroup]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "groups" in data:
        data = data["groups"]
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError(
            f"--personas must resolve to a list of 3 PersonaGroups (got {type(data).__name__})"
        )
    return [PersonaGroup.model_validate(d) for d in data]


def _load_screenshots(directory: Path) -> list[UploadedFile]:
    if not directory.is_dir():
        raise ValueError(f"--screenshots {directory} is not a directory")
    files: list[UploadedFile] = []
    for p in sorted(directory.iterdir()):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }[p.suffix.lower()]
            files.append(UploadedFile(name=p.name, mime=mime, data=p.read_bytes()))
    return files


def _load_config(path: Path | None) -> SimulationConfig:
    if path is None:
        return SimulationConfig()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SimulationConfig.model_validate(raw)


def _load_graph_override(path: Path | None) -> ScreenGraph | None:
    if path is None:
        return None
    return ScreenGraph.model_validate_json(path.read_text(encoding="utf-8"))


# ──────────────────────────── mock provider ────────────────────────────

class _CLIDummyProvider:
    """Replays canned ToolCallResults by tool name.

    Keeps a per-tool list of canned responses; each tool call pops the next
    matching entry. Used for --mock.
    """

    def __init__(self, by_tool: dict[str, list[dict]]):
        self._by_tool: dict[str, list[dict]] = {k: list(v) for k, v in by_tool.items()}
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools, tool_choice) -> ToolCallResult:
        self.calls.append({
            "system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice,
        })
        name = tool_choice.get("name") if isinstance(tool_choice, dict) else None
        if name is None:
            raise RuntimeError("mock provider requires a forced tool_choice name")
        queue = self._by_tool.get(name, [])
        if not queue:
            raise RuntimeError(
                f"mock provider out of canned responses for tool {name!r}; "
                f"available: {[k for k,v in self._by_tool.items() if v]}"
            )
        payload = queue.pop(0)
        return ToolCallResult(
            name=name, input=payload,
            raw={"input_tokens": 5000, "output_tokens": 500},
        )

    def stream(self, *, system, messages, tools, tool_choice) -> Iterable[StreamChunk]:
        result = self.complete(
            system=system, messages=messages, tools=tools, tool_choice=tool_choice,
        )
        yield StreamChunk(kind="tool_start", data={"name": result.name})
        yield StreamChunk(kind="tool_done", data=result.model_dump())
        yield StreamChunk(kind="done", data=None)


def _build_mock_provider(fixtures_dir: Path) -> _CLIDummyProvider:
    """Wire a mock provider from `tests/fixtures/`.

    Loads one screen-graph, one categorized-issues, one report, plus N
    backstory + decision responses so the run completes without running out.
    """
    def load(name: str) -> dict:
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    graph = load("mock_screen_graph.json")
    issues = load("mock_categorized_issues.json")
    report_narrative = load("mock_report.json")
    backstory = load("mock_backstory.json")
    decision = load("mock_decision.json")

    # Pre-stock generous queues so the mock doesn't run out during the walk.
    n_seeds = 32            # way more than enough for 3 groups at defaults
    n_decisions = 400       # covers 150-agent × 12-step runs and then some
    return _CLIDummyProvider({
        "emit_screen_graph": [graph],
        "emit_backstory": [backstory] * n_seeds,
        "emit_decision": [decision] * n_decisions,
        "emit_categorized_issues": [issues],
        "emit_report": [report_narrative],
    })


# ──────────────────────────── main ────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m persona_simulation.run",
        description="Run the Ascala persona simulation end-to-end.",
    )
    parser.add_argument("--personas", required=True, type=Path,
                        help="JSON file with 3 PersonaGroups (list or {groups:[...]})")
    parser.add_argument("--screenshots", required=True, type=Path,
                        help="Directory containing screenshot images")
    parser.add_argument("--goal", type=str, default=None,
                        help="Free-text goal the user should reach in the prototype")
    parser.add_argument("--mock", action="store_true",
                        help="Use bundled DummyProvider with canned fixture outputs; no network")
    parser.add_argument("--config-json", type=Path, default=None,
                        help="Override SimulationConfig defaults")
    parser.add_argument("--graph-override", type=Path, default=None,
                        help="Skip screen_graph build; load this JSON instead")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write SimulationResult JSON to this path (default: stdout)")
    parser.add_argument("--mock-fixtures", type=Path, default=None,
                        help="Directory of mock fixture JSONs (default: tests/fixtures)")

    args = parser.parse_args(argv)

    try:
        groups = _load_personas(args.personas)
        screenshots = _load_screenshots(args.screenshots)
        config = _load_config(args.config_json)
        graph_override = _load_graph_override(args.graph_override)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    provider = None
    if args.mock:
        default_fixtures = Path(__file__).resolve().parent / "tests" / "fixtures"
        fixtures_dir = args.mock_fixtures or default_fixtures
        if not fixtures_dir.is_dir():
            print(f"error: --mock fixtures dir not found: {fixtures_dir}", file=sys.stderr)
            return 2
        provider = _build_mock_provider(fixtures_dir)

    inputs = SimulationInputs(
        groups=groups,
        screenshots=screenshots,
        goal=args.goal,
        screen_graph_override=graph_override,
    )

    result = simulate(inputs, provider=provider, config=config)

    out_json = json.dumps(result.model_dump(), indent=2, default=str)
    if args.out is not None:
        args.out.write_text(out_json + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
