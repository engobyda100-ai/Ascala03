"""Schema-only tests: pydantic round-trips and the 3-group/share-sum invariant."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from persona_synthesis.schema import (
    ContextSummary,
    PersonaBundle,
    PersonaGroup,
)


def test_bundle_round_trip(mock_bundle_dict):
    bundle = PersonaBundle.model_validate(mock_bundle_dict)
    assert len(bundle.groups) == 3
    assert {g.id for g in bundle.groups} == {"pg_1", "pg_2", "pg_3"}


def test_summary_round_trip(mock_summary_dict):
    summary = ContextSummary.model_validate(mock_summary_dict)
    assert summary.app_category == "B2B project management"
    assert summary.pricing_model == "freemium"


def test_bundle_rejects_two_groups(mock_bundle_dict):
    bad = copy.deepcopy(mock_bundle_dict)
    bad["groups"] = bad["groups"][:2]
    with pytest.raises(ValidationError):
        PersonaBundle.model_validate(bad)


def test_bundle_rejects_four_groups(mock_bundle_dict):
    bad = copy.deepcopy(mock_bundle_dict)
    bad["groups"].append(copy.deepcopy(bad["groups"][0]))
    with pytest.raises(ValidationError):
        PersonaBundle.model_validate(bad)


@pytest.mark.parametrize("shares,should_pass", [
    ([33, 33, 34], True),      # 100 → ok
    ([33, 33, 33], True),      # 99 → ok (98–102 range)
    ([33, 33, 32], True),      # 98 → exactly on the lower boundary
    ([34, 33, 31], True),      # 98 → ok
    ([50, 30, 17], False),     # 97 → rejected
    ([50, 30, 22], True),      # 102 → exactly on the upper boundary
    ([50, 30, 23], False),     # 103 → rejected
    ([0, 0, 0], False),        # 0 → rejected
])
def test_share_sum_invariant(mock_bundle_dict, shares, should_pass):
    data = copy.deepcopy(mock_bundle_dict)
    for g, s in zip(data["groups"], shares):
        g["estimated_share_pct"] = s
    if should_pass:
        PersonaBundle.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            PersonaBundle.model_validate(data)


def test_missing_posture_rejected(mock_bundle_dict):
    data = copy.deepcopy(mock_bundle_dict)
    del data["groups"][0]["testing_postures"]["compliance"]
    with pytest.raises(ValidationError):
        PersonaBundle.model_validate(data)


def test_share_out_of_range_rejected(mock_bundle_dict):
    data = copy.deepcopy(mock_bundle_dict)
    data["groups"][0]["estimated_share_pct"] = 150  # >100 field-level
    with pytest.raises(ValidationError):
        PersonaBundle.model_validate(data)


def test_persona_group_direct(mock_bundle_dict):
    """One group can round-trip on its own."""
    g = PersonaGroup.model_validate(mock_bundle_dict["groups"][0])
    assert g.name == "Solo Bootstrappers"
    assert g.demographics.primary_device == "desktop"
    assert g.testing_postures.accessibility.screen_reader_likelihood == 2
