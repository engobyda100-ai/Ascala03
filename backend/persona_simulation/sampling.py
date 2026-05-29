"""Sample concrete agents from PersonaGroups.

For each group, produce `n_per_group` seed agents by collapsing range/list
traits into specific values and calling Claude once per seed to personalize
the backstory. Forked agents are spawned by the Runner and inherit their
parent's backstory — no LLM call for forks.
"""
from __future__ import annotations

import json
import random
import re

from pydantic import BaseModel, Field

from persona_synthesis.llm.base import LLMProvider
from persona_synthesis.schema import PersonaGroup

from persona_simulation._llm_helpers import call_with_retry, load_prompt
from persona_simulation.schema import SampledAgent


TOOL_NAME = "emit_backstory"
TOOL_DESCRIPTION = "Emit a personalized backstory + goals + frustrations for this individual agent."


class _BackstoryOutput(BaseModel):
    backstory: str = Field(min_length=1)
    goals: list[str] = Field(min_length=1, max_length=6)
    frustrations: list[str] = Field(min_length=1, max_length=6)


def _parse_age_range(age_range: str) -> tuple[int, int]:
    """Best-effort parse of strings like '25-34', '25–34', '30+'. Returns (lo, hi)."""
    if not age_range:
        return 25, 45
    matches = re.findall(r"\d+", age_range)
    if len(matches) >= 2:
        lo, hi = int(matches[0]), int(matches[1])
        return (min(lo, hi), max(lo, hi))
    if len(matches) == 1:
        v = int(matches[0])
        return (v, v + 9)
    return 25, 45


def _sample_scalars(group: PersonaGroup, rng: random.Random) -> dict:
    """Collapse the group's ranges into concrete scalars."""
    age_lo, age_hi = _parse_age_range(group.demographics.age_range)
    return {
        "age": rng.randint(age_lo, age_hi),
        "tech_savviness": group.cognitive.tech_savviness,
        "patience_threshold": group.cognitive.patience_threshold,
        "pricing_sensitivity": group.economic.pricing_sensitivity,
        "primary_device": group.demographics.primary_device,
    }


def _personalize(
    group: PersonaGroup,
    scalars: dict,
    agent_id: str,
    provider: LLMProvider,
) -> tuple[str, list[str], list[str]]:
    """One Claude call returning (backstory, goals, frustrations)."""
    user_content = [{
        "type": "text",
        "text": (
            "Cluster (PersonaGroup) for this agent:\n"
            f"```json\n{json.dumps(group.model_dump(), indent=2)}\n```\n\n"
            "Sampled concrete traits for this individual:\n"
            f"```json\n{json.dumps(scalars, indent=2)}\n```\n\n"
            f"Agent id: {agent_id}\n\n"
            "Emit the backstory, goals, and frustrations via the emit_backstory tool. "
            "Stay within the cluster identity; the sampled scalars are this individual's "
            "specific colour."
        ),
    }]
    system = load_prompt("seed_backstory.md")
    out, _tokens = call_with_retry(
        provider,
        system=system,
        user_content=user_content,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        output_model=_BackstoryOutput,
    )
    return out.backstory, out.goals, out.frustrations


def sample_seed_agents(
    groups: list[PersonaGroup],
    *,
    n_per_group: int = 1,
    provider: LLMProvider,
    rng_seed: int = 0,
) -> list[SampledAgent]:
    """Return a fresh list of SampledAgents seeded from `groups`.

    Same `rng_seed` → identical sampled scalars across runs (tests depend on this).
    Note: LLM-generated backstories vary unless the provider is deterministic
    (DummyProvider in tests is, real Claude is not — that's fine for production).
    """
    rng = random.Random(rng_seed)
    agents: list[SampledAgent] = []
    seq = 0
    for group in groups:
        for _ in range(n_per_group):
            seq += 1
            agent_id = f"a_{group.id}_{seq:03d}"
            scalars = _sample_scalars(group, rng)
            backstory, goals, frustrations = _personalize(group, scalars, agent_id, provider)
            # Fold goals/frustrations into the backstory string so the downstream
            # decision prompt has one coherent narrative field.
            full_backstory = (
                backstory.rstrip()
                + "\n\nPersonal goals:\n"
                + "\n".join(f"  - {g}" for g in goals)
                + "\n\nPersonal frustrations:\n"
                + "\n".join(f"  - {fr}" for fr in frustrations)
            )
            agents.append(
                SampledAgent(
                    agent_id=agent_id,
                    parent_agent_id=None,
                    cluster_id=group.id,
                    cluster_name=group.name,
                    **scalars,
                    group=group,
                    personalized_backstory=full_backstory,
                    rng_seed=rng_seed,
                )
            )
    return agents
