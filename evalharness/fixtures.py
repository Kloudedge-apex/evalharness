"""Loading the fixture set.

The loader validates rather than trusts. A fixture missing a required field is
an error, not a fixture that quietly evaluates to "allow". Same principle as the
gate: the failure mode of a permissive loader is a green scorecard that is
measuring nothing.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Sequence, Tuple

from .model import Citation, Fixture
from .segment import parse_output

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

_REQUIRED = ("id", "description", "category", "expected_gate", "response")
_VALID_GATES = ("allow", "refuse")


class FixtureError(ValueError):
    pass


def _citation_from_dict(raw: Any, path: str) -> Citation:
    if not isinstance(raw, dict):
        raise FixtureError("{0}: each source must be an object".format(path))
    if "id" not in raw:
        raise FixtureError("{0}: source is missing 'id'".format(path))
    return Citation(
        id=str(raw["id"]),
        title=str(raw.get("title", "")),
        url=str(raw.get("url", "")),
        published=str(raw.get("published", "")),
        snippet=str(raw.get("snippet", "")),
    )


def fixture_from_dict(raw: Dict[str, Any], path: str = "<memory>") -> Fixture:
    missing = [key for key in _REQUIRED if key not in raw]
    if missing:
        raise FixtureError("{0}: missing required field(s): {1}".format(path, ", ".join(missing)))
    if raw["expected_gate"] not in _VALID_GATES:
        raise FixtureError(
            "{0}: expected_gate must be one of {1}, got {2!r}".format(
                path, _VALID_GATES, raw["expected_gate"]
            )
        )

    sources = tuple(_citation_from_dict(s, path) for s in raw.get("sources", []))
    duplicate_ids = len({s.id for s in sources}) != len(sources)
    if duplicate_ids:
        raise FixtureError("{0}: duplicate source ids".format(path))

    output = parse_output(str(raw["id"]), str(raw["response"]), sources)
    return Fixture(
        id=str(raw["id"]),
        description=str(raw["description"]),
        category=str(raw["category"]),
        expected_gate=str(raw["expected_gate"]),
        output=output,
        expected_codes=tuple(raw.get("expected_codes", [])),
        expected_advisory_codes=tuple(raw.get("expected_advisory_codes", [])),
        notes=str(raw.get("notes", "")),
    )


def load_fixture_file(path: str) -> Fixture:
    with open(path, "r", encoding="utf-8") as handle:
        try:
            raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise FixtureError("{0}: invalid JSON: {1}".format(path, exc))
    if not isinstance(raw, dict):
        raise FixtureError("{0}: fixture must be a JSON object".format(path))
    return fixture_from_dict(raw, path)


def load_fixtures(directory: str = FIXTURE_DIR) -> Tuple[Fixture, ...]:
    if not os.path.isdir(directory):
        raise FixtureError("fixture directory not found: {0}".format(directory))
    fixtures: List[Fixture] = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        fixtures.append(load_fixture_file(os.path.join(directory, name)))
    if not fixtures:
        raise FixtureError("no fixtures found in {0}".format(directory))

    ids = [f.id for f in fixtures]
    if len(set(ids)) != len(ids):
        raise FixtureError("duplicate fixture ids in {0}".format(directory))
    return tuple(fixtures)
