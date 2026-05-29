"""Tests for build_screen_graph()."""
from __future__ import annotations

from pathlib import Path

import pytest

from persona_synthesis.schema import UploadedFile

from persona_simulation.errors import GraphIncomplete, SchemaValidationError
from persona_simulation.screen_graph import build_screen_graph


SHOTS_DIR = Path(__file__).parent / "fixtures" / "shots"


def _load_shots() -> list[UploadedFile]:
    files = []
    for p in sorted(SHOTS_DIR.iterdir()):
        files.append(UploadedFile(name=p.name, mime="image/png", data=p.read_bytes()))
    return files


def test_happy_path(make_dummy, mock_screen_graph_dict):
    provider = make_dummy(mock_screen_graph_dict)
    graph = build_screen_graph(_load_shots(), goal="complete signup", provider=provider)
    assert graph.entry_screen_id == "s1"
    assert {s.id for s in graph.screens} == {"s1", "s2"}
    assert len(graph.transitions) == 1
    assert graph.unresolved[0].from_screen == "s1"
    # One call made with two image blocks
    assert len(provider.calls) == 1
    content = provider.calls[0]["messages"][0]["content"]
    images = [c for c in content if c.get("type") == "image"]
    assert len(images) == 2


def test_retry_on_invalid_graph(make_dummy, bad_screen_graph_dict, mock_screen_graph_dict):
    provider = make_dummy(bad_screen_graph_dict, mock_screen_graph_dict)
    graph = build_screen_graph(_load_shots(), provider=provider)
    assert graph.entry_screen_id == "s1"
    assert len(provider.calls) == 2
    assert "RETRY ADDENDUM" in provider.calls[1]["system"]


def test_double_failure_raises(make_dummy, bad_screen_graph_dict):
    provider = make_dummy(bad_screen_graph_dict, bad_screen_graph_dict)
    with pytest.raises(SchemaValidationError):
        build_screen_graph(_load_shots(), provider=provider)


def test_graph_incomplete_on_multiple_screens_no_transitions(make_dummy):
    minimal = {
        "screens": [
            {"id": "s1", "source_filename": "s1.png", "inferred_purpose": "a",
             "copy": [], "elements": [], "duplicate_of": None},
            {"id": "s2", "source_filename": "s2.png", "inferred_purpose": "b",
             "copy": [], "elements": [], "duplicate_of": None},
        ],
        "transitions": [],
        "unresolved": [],
        "entry_screen_id": "s1",
    }
    provider = make_dummy(minimal)
    with pytest.raises(GraphIncomplete):
        build_screen_graph(_load_shots(), provider=provider)


def test_single_screen_no_transitions_allowed(make_dummy):
    single = {
        "screens": [
            {"id": "s1", "source_filename": "s1.png", "inferred_purpose": "a",
             "copy": [], "elements": [], "duplicate_of": None},
        ],
        "transitions": [],
        "unresolved": [],
        "entry_screen_id": "s1",
    }
    provider = make_dummy(single)
    # Only load a single shot — the shape is legal
    shots = [UploadedFile(name="s1.png", mime="image/png",
                           data=(SHOTS_DIR / "s1.png").read_bytes())]
    graph = build_screen_graph(shots, provider=provider)
    assert len(graph.screens) == 1
    assert graph.transitions == []


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        # Provider would never get called
        class Never:
            def complete(self, **_): raise AssertionError
            def stream(self, **_): raise AssertionError
        build_screen_graph([], provider=Never())
