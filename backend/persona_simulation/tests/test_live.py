"""Live end-to-end test — skipped by default.

Run with:
    pytest -m live

Costs pennies. Requires ANTHROPIC_API_KEY in the env.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from persona_synthesis.schema import PersonaGroup, UploadedFile

from persona_simulation.runner import simulate
from persona_simulation.schema import SimulationConfig, SimulationInputs


pytestmark = pytest.mark.live


SHOTS_DIR = Path(__file__).parent / "fixtures" / "shots"


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
def test_live_simulation_minimal(sample_personas):
    groups = [PersonaGroup.model_validate(g) for g in sample_personas]
    shots = [
        UploadedFile(name=p.name, mime="image/png", data=p.read_bytes())
        for p in sorted(SHOTS_DIR.iterdir()) if p.suffix == ".png"
    ]
    cfg = SimulationConfig(
        n_seed_per_group=1,
        max_agents_budget=3,
        max_depth=5,
        hard_spend_cap_tokens=500_000,
    )
    result = simulate(
        SimulationInputs(groups=groups, screenshots=shots, goal="complete signup"),
        config=cfg,
    )
    assert result.report.executive_summary
    assert result.report.metrics.total_agents >= 3
