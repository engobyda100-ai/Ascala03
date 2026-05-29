"""Tests for sample_seed_agents()."""
from __future__ import annotations

from persona_synthesis.schema import PersonaGroup

from persona_simulation.sampling import _parse_age_range, sample_seed_agents


def _three_groups(sample_personas) -> list[PersonaGroup]:
    return [PersonaGroup.model_validate(g) for g in sample_personas]


def test_parse_age_range_basic():
    assert _parse_age_range("25-34") == (25, 34)
    assert _parse_age_range("25–34") == (25, 34)     # en-dash
    assert _parse_age_range("30+") == (30, 39)       # single value → +9 band
    assert _parse_age_range("") == (25, 45)          # fallback


def test_deterministic_with_same_seed(make_dummy, mock_backstory_dict, sample_personas):
    groups = _three_groups(sample_personas)
    p1 = make_dummy(*([mock_backstory_dict] * 3))
    p2 = make_dummy(*([mock_backstory_dict] * 3))
    a1 = sample_seed_agents(groups, provider=p1, rng_seed=42)
    a2 = sample_seed_agents(groups, provider=p2, rng_seed=42)
    assert [a.age for a in a1] == [a.age for a in a2]
    assert [a.tech_savviness for a in a1] == [a.tech_savviness for a in a2]


def test_one_call_per_seed(make_dummy, mock_backstory_dict, sample_personas):
    groups = _three_groups(sample_personas)
    provider = make_dummy(*([mock_backstory_dict] * 3))
    agents = sample_seed_agents(groups, provider=provider, rng_seed=0, n_per_group=1)
    assert len(agents) == 3
    assert len(provider.calls) == 3
    # Each agent has the fixture backstory embedded
    for a in agents:
        assert "small-team PM" in a.personalized_backstory.lower() or "evaluates tools" in a.personalized_backstory.lower()
        assert a.parent_agent_id is None


def test_age_within_range(make_dummy, mock_backstory_dict, sample_personas):
    groups = _three_groups(sample_personas)
    provider = make_dummy(*([mock_backstory_dict] * 3))
    agents = sample_seed_agents(groups, provider=provider, rng_seed=7)
    for a in agents:
        lo, hi = _parse_age_range(a.group.demographics.age_range)
        assert lo <= a.age <= hi


def test_scalars_respect_schema_ranges(make_dummy, mock_backstory_dict, sample_personas):
    groups = _three_groups(sample_personas)
    provider = make_dummy(*([mock_backstory_dict] * 3))
    agents = sample_seed_agents(groups, provider=provider, rng_seed=0)
    for a in agents:
        assert 1 <= a.tech_savviness <= 5
        assert 1 <= a.pricing_sensitivity <= 5
        assert a.patience_threshold in {"low", "medium", "high"}
        assert a.primary_device in {"mobile", "desktop", "mixed"}


def test_multiple_per_group(make_dummy, mock_backstory_dict, sample_personas):
    groups = _three_groups(sample_personas)
    provider = make_dummy(*([mock_backstory_dict] * 6))
    agents = sample_seed_agents(groups, provider=provider, rng_seed=0, n_per_group=2)
    assert len(agents) == 6
    assert len(provider.calls) == 6
    # unique ids
    assert len({a.agent_id for a in agents}) == 6
