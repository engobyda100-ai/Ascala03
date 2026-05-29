"""Live Anthropic API test — skipped by default.

Run with:
    pytest -m live

Costs pennies. Requires ANTHROPIC_API_KEY in the env.
"""
from __future__ import annotations

import os

import pytest

from persona_synthesis import ChatMessage, SynthesisInputs, synthesize_personas


pytestmark = pytest.mark.live


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
def test_live_chat_only():
    result = synthesize_personas(
        SynthesisInputs(
            chat_messages=[
                ChatMessage(
                    role="user",
                    text=(
                        "We're building a B2B SaaS tool for early-stage founders "
                        "running small engineering teams. Freemium pricing. "
                        "Mostly US + EU. Values fast onboarding and clean docs."
                    ),
                ),
            ]
        )
    )
    assert len(result.groups) == 3
    s = sum(g.estimated_share_pct for g in result.groups)
    assert 98 <= s <= 102
    assert {g.id for g in result.groups} == {"pg_1", "pg_2", "pg_3"} or len(
        {g.id for g in result.groups}
    ) == 3
