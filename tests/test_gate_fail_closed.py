"""The gate must fail closed.

Every test here is a way the gate could quietly turn into a pass through, which
is the failure mode that matters: a gate that is broken and refusing is a
visible outage, a gate that is broken and allowing is invisible until something
ships that should not have.
"""

from __future__ import annotations

import pytest

from evalharness.evaluators.base import Evaluator
from evalharness.gate import Decision, RefuseOrCiteGate
from evalharness.model import Citation, EvaluatorResult, ModelOutput
from evalharness.segment import parse_output


class ExplodingEvaluator(Evaluator):
    name = "exploding"

    def evaluate(self, output):
        raise RuntimeError("evaluator backend is down")


class SilentlyPassingEvaluator(Evaluator):
    name = "quiet"

    def evaluate(self, output):
        return EvaluatorResult(name=self.name, score=1.0)


def clean_output():
    return parse_output(
        "clean",
        "Northwind announced a migration on 2026-02-11 [1].",
        [
            Citation(
                id="1",
                title="Northwind migration",
                url="https://example.invalid/n",
                snippet="Northwind announced a migration on 2026-02-11.",
            )
        ],
    )


def test_clean_output_is_allowed():
    """The control. If this fails, every refusal below proves nothing."""
    result = RefuseOrCiteGate().decide(clean_output())
    assert result.decision is Decision.ALLOW
    assert result.reasons == ()


def test_an_evaluator_that_raises_causes_a_refusal_not_a_skip():
    gate = RefuseOrCiteGate(evaluators=[ExplodingEvaluator(), SilentlyPassingEvaluator()])
    result = gate.decide(clean_output())

    assert result.decision is Decision.REFUSE
    assert "evaluator_error" in result.reasons
    assert "evaluator backend is down" in result.blocking_findings[0].message


def test_a_broken_gate_refuses_rather_than_propagating():
    """Even a nonsense object gets a decision, and the decision is refuse."""

    class NotAnOutput:
        id = "broken"

        @property
        def response(self):
            raise ValueError("exploded while reading the response")

    result = RefuseOrCiteGate().decide(NotAnOutput())
    assert result.decision is Decision.REFUSE
    assert result.reasons == ("gate_error",)


def test_none_is_refused():
    result = RefuseOrCiteGate().decide(None)
    assert result.decision is Decision.REFUSE
    assert result.reasons == ("no_output",)


def test_whitespace_only_response_is_refused():
    output = parse_output("blank", "   \n  ", [])
    result = RefuseOrCiteGate().decide(output)
    assert result.decision is Decision.REFUSE
    assert result.reasons == ("empty_response",)


def test_response_that_produced_no_claims_is_refused():
    """'I could not parse it' is not 'there was nothing wrong with it'.

    Constructed directly rather than through the parser, because the parser
    always yields at least one claim for non empty text. This guards the branch
    against a future segmenter that can return nothing.
    """
    output = ModelOutput(id="unparsed", response="something was here", sources=(), claims=())
    result = RefuseOrCiteGate().decide(output)
    assert result.decision is Decision.REFUSE
    assert result.reasons == ("unparseable_response",)


def test_there_is_no_third_decision():
    """No SOFTEN, no WARN, no ALLOW_WITH_CAVEAT.

    This assertion looks petty and is not. The usual way a gate like this dies
    is that somebody adds a middle outcome for the case where refusing is
    inconvenient, and from then on nothing is ever refused.
    """
    assert [member.value for member in Decision] == ["allow", "refuse"]


def test_refusal_withholds_the_text_it_refused():
    """Fails closed at the boundary, not just in the log line."""
    output = parse_output("bad", "Northwind lost 3 clients in April.", [])
    result, released = RefuseOrCiteGate().release(output)

    assert result.decision is Decision.REFUSE
    assert "Northwind" not in released
    assert "3 clients" not in released
    assert "cannot provide this answer" in released.lower()
    assert "unsourced_claim" in released


def test_allowed_output_is_released_verbatim():
    output = clean_output()
    result, released = RefuseOrCiteGate().release(output)
    assert result.decision is Decision.ALLOW
    assert released == output.response


def test_advisory_findings_never_refuse():
    """The advisory tier has to stay non blocking or it is not an advisory tier."""
    output = parse_output(
        "advisory",
        "Northwind closed a 12 million dollar round on 2026-01-20 [1].",
        [
            Citation(
                id="1",
                title="Northwind opens an office in Leeds",
                url="https://example.invalid/leeds",
                snippet="Northwind has signed a lease on office space in Leeds.",
            )
        ],
    )
    result = RefuseOrCiteGate().decide(output)

    assert result.decision is Decision.ALLOW
    assert [f.code for f in result.advisory_findings] == ["low_lexical_overlap"]
