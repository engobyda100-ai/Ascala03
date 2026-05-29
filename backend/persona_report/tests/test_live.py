"""Live integration test — hits the real Anthropic API.

Skipped by default. Run with:
    pytest -m live persona_report/tests/test_live.py -v

Costs approximately $0.10 per run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona_report.generator import generate_report
from persona_report.schema import Report
from persona_simulation.schema import SimulationResult


pytestmark = pytest.mark.live

FIXTURE = Path(__file__).parent / "fixtures" / "sample_simulation_result.json"


def test_live_generate_report():
    sim = SimulationResult.model_validate(json.loads(FIXTURE.read_text()))
    report = generate_report(sim, include_executive_summary=True)

    # Schema round-trip must not raise
    Report.model_validate(report.model_dump())

    assert len(report.test_type_reports) == 6
    for r in report.test_type_reports:
        assert r.short_summary, f"{r.test_type}: empty short_summary"
        assert len(r.key_stats) == 3
        assert 1 <= len(r.persona_distributions) <= 3

    assert report.executive_summary
    assert report.meta.total_llm_calls >= 6
