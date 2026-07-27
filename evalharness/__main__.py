"""Command line entry point.

    python3 -m evalharness              print the scorecard over the shipped fixtures
    python3 -m evalharness --json       same thing, machine readable
    python3 -m evalharness --fixture X  inspect one fixture in detail

Exit code is 1 if any gate decision disagrees with the fixture label.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence

from .fixtures import FIXTURE_DIR, FixtureError
from .gate import RefuseOrCiteGate
from .scorecard import exit_code, render_reasons, report, run, to_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalharness",
        description=(
            "Run the refuse-or-cite gate and the evaluator set over a directory of "
            "fixture LLM outputs. No network access, no API keys."
        ),
    )
    parser.add_argument("--fixtures", default=FIXTURE_DIR, help="directory of fixture JSON files")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--fixture", default=None, help="inspect a single fixture by id")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rows = run(args.fixtures, RefuseOrCiteGate())
    except FixtureError as exc:
        print("fixture error: {0}".format(exc), file=sys.stderr)
        return 2

    if args.fixture:
        selected = [row for row in rows if row.fixture.id == args.fixture]
        if not selected:
            print("no fixture with id {0!r}".format(args.fixture), file=sys.stderr)
            return 2
        row = selected[0]
        print("fixture:     {0}".format(row.fixture.id))
        print("category:    {0}".format(row.fixture.category))
        print("description: {0}".format(row.fixture.description))
        print("decision:    {0} (label says {1})".format(row.decision, row.fixture.expected_gate))
        print("")
        print("response:")
        for line in row.fixture.output.response.splitlines() or [""]:
            print("    {0}".format(line))
        print("")
        print("findings:")
        print(render_reasons([row]) or "    none")
        if row.fixture.notes:
            print("")
            print("notes: {0}".format(row.fixture.notes))
        return 0 if row.agrees else 1

    print(to_json(rows) if args.json else report(rows))
    return exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
