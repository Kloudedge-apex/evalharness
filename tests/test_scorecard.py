"""The scorecard runner.

The runner has to be a check, not a report: it compares each decision against
the fixture label and exits non zero on disagreement. A table that cannot fail
is a screenshot.
"""

from __future__ import annotations

import json

from evalharness.__main__ import main
from evalharness.scorecard import exit_code, render_table, report, run, to_json


def test_the_runner_agrees_with_every_shipped_label():
    rows = run()
    disagreements = [r.fixture.id for r in rows if not r.agrees]
    assert disagreements == []
    assert exit_code(rows) == 0


def test_the_runner_can_fail():
    """Proof that agreement is measured and not assumed.

    Flip one label in memory, and the runner must notice.
    """
    rows = list(run())
    row = next(r for r in rows if r.fixture.expected_gate == "allow")
    flipped = type(row)(
        fixture=type(row.fixture)(
            id=row.fixture.id,
            description=row.fixture.description,
            category=row.fixture.category,
            expected_gate="refuse",
            output=row.fixture.output,
            expected_codes=("unsourced_claim",),
        ),
        result=row.result,
    )
    assert flipped.agrees is False
    assert exit_code([flipped]) == 1


def test_table_has_a_row_per_fixture_and_a_column_per_evaluator():
    rows = run()
    table = render_table(rows)
    lines = table.splitlines()

    assert lines[0].split()[:2] == ["FIXTURE", "CATEGORY"]
    for column in ("CITE", "PII", "INJCT", "SUPRT", "GATE"):
        assert column in lines[0]
    assert len(lines) == len(rows) + 2  # header plus rule
    for row in rows:
        assert any(line.startswith(row.fixture.id) for line in lines)


def test_report_lists_the_reason_for_every_refusal():
    rows = run()
    text = report(rows)
    for row in rows:
        for reason in row.result.reasons:
            assert reason in text


def test_the_report_never_prints_the_pii_it_found():
    """The detector must not become the leak."""
    text = report(run())
    assert "dana.whitfield@northwind-bank.example" not in text
    assert "4111 1111 1111 1111" not in text
    assert "sk_live_9f2Ab7Kq4Lm0Zx8T" not in text


def test_json_output_is_machine_readable():
    payload = json.loads(to_json(run()))
    assert payload["agrees"] is True
    assert len(payload["results"]) == len(run())
    first = payload["results"][0]
    for key in ("fixture", "decision", "expected_gate", "reasons", "scores"):
        assert key in first


def test_cli_exits_zero_on_the_shipped_fixtures(capsys):
    assert main([]) == 0
    assert "gate agrees with fixture labels" in capsys.readouterr().out


def test_cli_json_flag(capsys):
    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["agrees"] is True


def test_cli_can_inspect_a_single_fixture(capsys):
    assert main(["--fixture", "adv_one_citation_covers_all"]) == 0
    out = capsys.readouterr().out
    assert "unsourced_claim" in out
    assert "decision:    refuse" in out


def test_cli_reports_a_bad_fixture_directory(capsys):
    assert main(["--fixtures", "/tmp/definitely-not-a-fixture-directory-38fa1"]) == 2
    assert "fixture error" in capsys.readouterr().err
