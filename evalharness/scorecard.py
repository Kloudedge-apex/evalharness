"""Scorecard: run the gate over the whole fixture set and print the table.

The runner compares each gate decision against the label on the fixture and
exits non zero on any disagreement, so this is a check rather than a report.
A table that cannot fail is a screenshot.

Nothing here prints a matched PII value: findings carry redacted messages by
construction (see evaluators/pii.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .evaluators.citation import NAME as CITATION
from .evaluators.injection import NAME as INJECTION
from .evaluators.pii import NAME as PII
from .evaluators.support import NAME as SUPPORT
from .fixtures import FIXTURE_DIR, load_fixtures
from .gate import Decision, GateResult, RefuseOrCiteGate
from .model import Fixture

BLOCKING_EVALUATORS = (CITATION, PII, INJECTION)
ALL_EVALUATORS = (CITATION, PII, INJECTION, SUPPORT)


@dataclass(frozen=True)
class Row:
    fixture: Fixture
    result: GateResult

    @property
    def decision(self) -> str:
        return self.result.decision.value

    @property
    def matches_label(self) -> bool:
        return self.decision == self.fixture.expected_gate

    @property
    def codes_match_label(self) -> bool:
        return set(self.result.reasons) == set(self.fixture.expected_codes)

    @property
    def advisory_codes_match_label(self) -> bool:
        actual = {f.code for f in self.result.advisory_findings}
        return actual == set(self.fixture.expected_advisory_codes)

    @property
    def agrees(self) -> bool:
        return self.matches_label and self.codes_match_label and self.advisory_codes_match_label

    def score(self, evaluator: str) -> Optional[float]:
        result = self.result.result_for(evaluator)
        return None if result is None else result.score


def run(fixture_dir: str = FIXTURE_DIR, gate: Optional[RefuseOrCiteGate] = None) -> Tuple[Row, ...]:
    gate = gate or RefuseOrCiteGate()
    return tuple(Row(f, gate.decide(f.output)) for f in load_fixtures(fixture_dir))


def _fmt_score(value: Optional[float]) -> str:
    return " n/a " if value is None else "{0:.2f} ".format(value)


def render_table(rows: Sequence[Row]) -> str:
    id_width = max([len(r.fixture.id) for r in rows] + [7])
    cat_width = max([len(r.fixture.category) for r in rows] + [8])

    header = "{0}  {1}  {2}  {3}  {4}  {5}  {6}  {7}".format(
        "FIXTURE".ljust(id_width),
        "CATEGORY".ljust(cat_width),
        "CITE ",
        " PII ",
        "INJCT",
        "SUPRT",
        "GATE   ",
        "VS LABEL",
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            "{0}  {1}  {2}  {3}  {4}  {5}  {6}  {7}".format(
                row.fixture.id.ljust(id_width),
                row.fixture.category.ljust(cat_width),
                _fmt_score(row.score(CITATION)),
                _fmt_score(row.score(PII)),
                _fmt_score(row.score(INJECTION)),
                _fmt_score(row.score(SUPPORT)),
                row.decision.upper().ljust(7),
                "ok" if row.agrees else "MISMATCH",
            )
        )
    return "\n".join(lines)


def render_reasons(rows: Sequence[Row]) -> str:
    lines: List[str] = []
    for row in rows:
        if not row.result.reasons and not row.result.advisory_findings:
            continue
        lines.append("{0}:".format(row.fixture.id))
        for finding in row.result.blocking_findings:
            where = "" if finding.claim_index is None else " (claim {0})".format(finding.claim_index)
            lines.append("    BLOCK     {0}{1}: {2}".format(finding.code, where, finding.message))
        for reason in row.result.reasons:
            if not any(f.code == reason for f in row.result.blocking_findings):
                lines.append("    BLOCK     {0}".format(reason))
        for finding in row.result.advisory_findings:
            where = "" if finding.claim_index is None else " (claim {0})".format(finding.claim_index)
            lines.append("    advisory  {0}{1}: {2}".format(finding.code, where, finding.message))
    return "\n".join(lines)


def render_summary(rows: Sequence[Row]) -> str:
    total = len(rows)
    refused = sum(1 for r in rows if r.result.decision is Decision.REFUSE)
    agreed = sum(1 for r in rows if r.agrees)

    lines = ["fixtures: {0}    refused: {1}    allowed: {2}".format(total, refused, total - refused)]
    for name in ALL_EVALUATORS:
        results = [r.result.result_for(name) for r in rows]
        ran = [result for result in results if result is not None]
        if not ran:
            lines.append("  {0:<18} did not run".format(name))
            continue
        mean = sum(result.score for result in ran) / len(ran)
        clean = sum(1 for result in ran if result.passed)
        blocking = "blocking" if name in BLOCKING_EVALUATORS else "advisory"
        lines.append(
            "  {0:<18} {1:<9} mean score {2:.2f} over {3} run(s), {4} with no blocking finding".format(
                name, blocking, mean, len(ran), clean
            )
        )
    lines.append("gate agrees with fixture labels: {0}/{1}".format(agreed, total))
    return "\n".join(lines)


def to_json(rows: Sequence[Row]) -> str:
    payload: List[Dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "fixture": row.fixture.id,
                "category": row.fixture.category,
                "decision": row.decision,
                "expected_gate": row.fixture.expected_gate,
                "reasons": list(row.result.reasons),
                "expected_codes": list(row.fixture.expected_codes),
                "advisory": [f.code for f in row.result.advisory_findings],
                "scores": {
                    name: row.score(name) for name in ALL_EVALUATORS if row.score(name) is not None
                },
                "agrees_with_label": row.agrees,
            }
        )
    return json.dumps({"results": payload, "agrees": all(r.agrees for r in rows)}, indent=2)


def report(rows: Sequence[Row]) -> str:
    parts = [render_table(rows), "", render_summary(rows), "", "findings:", render_reasons(rows)]
    return "\n".join(parts)


def exit_code(rows: Sequence[Row]) -> int:
    return 0 if all(row.agrees for row in rows) else 1
