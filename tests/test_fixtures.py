"""The fixture set is the spec for the gate, so it is checked as one.

Every shipped fixture carries a label. These tests assert the gate reproduces
each label exactly, including the finding codes, so a change in behaviour shows
up as a named failure rather than as a slightly different table.
"""

from __future__ import annotations

import json
import os

import pytest

from evalharness.fixtures import FIXTURE_DIR, FixtureError, fixture_from_dict, load_fixtures
from evalharness.gate import RefuseOrCiteGate

FIXTURES = load_fixtures()
IDS = [f.id for f in FIXTURES]


def test_the_fixture_set_covers_both_outcomes_and_all_three_categories():
    assert len(FIXTURES) >= 12
    assert {f.expected_gate for f in FIXTURES} == {"allow", "refuse"}
    assert {f.category for f in FIXTURES} == {"benign", "adversarial", "known_limitation"}


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_gate_reproduces_the_fixture_label(fixture):
    result = RefuseOrCiteGate().decide(fixture.output)
    assert result.decision.value == fixture.expected_gate


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_gate_reproduces_the_expected_finding_codes(fixture):
    result = RefuseOrCiteGate().decide(fixture.output)
    assert set(result.reasons) == set(fixture.expected_codes)


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_gate_reproduces_the_expected_advisory_codes(fixture):
    result = RefuseOrCiteGate().decide(fixture.output)
    actual = {f.code for f in result.advisory_findings}
    assert actual == set(fixture.expected_advisory_codes)


@pytest.mark.parametrize("fixture", FIXTURES, ids=IDS)
def test_every_fixture_explains_itself(fixture):
    """A fixture nobody can read is a fixture nobody will maintain."""
    assert fixture.description.strip()
    assert len(fixture.description) > 30


def test_fixture_files_are_valid_json_objects_on_disk():
    names = [n for n in os.listdir(FIXTURE_DIR) if n.endswith(".json")]
    assert len(names) == len(FIXTURES)
    for name in names:
        with open(os.path.join(FIXTURE_DIR, name), "r", encoding="utf-8") as handle:
            assert isinstance(json.load(handle), dict)


def test_loader_rejects_a_fixture_missing_required_fields():
    """The loader validates rather than trusts.

    A permissive loader gives you a green scorecard that is measuring a
    smaller fixture set than you think it is.
    """
    with pytest.raises(FixtureError):
        fixture_from_dict({"id": "x", "response": "hello"})


def test_loader_rejects_an_unknown_expected_gate():
    with pytest.raises(FixtureError):
        fixture_from_dict(
            {
                "id": "x",
                "description": "a description long enough to be useful to a reader",
                "category": "benign",
                "expected_gate": "maybe",
                "response": "hello",
            }
        )


def test_loader_rejects_duplicate_source_ids():
    with pytest.raises(FixtureError):
        fixture_from_dict(
            {
                "id": "x",
                "description": "a description long enough to be useful to a reader",
                "category": "benign",
                "expected_gate": "allow",
                "response": "hello",
                "sources": [{"id": "1"}, {"id": "1"}],
            }
        )


def test_loader_rejects_a_missing_directory():
    with pytest.raises(FixtureError):
        load_fixtures("/tmp/definitely-not-a-fixture-directory-38fa1")
