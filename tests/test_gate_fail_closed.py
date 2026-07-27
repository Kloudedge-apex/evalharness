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
    # allow_partial because this gate deliberately omits the blocking
    # evaluators: the point of the test is what happens when one raises, not
    # what the full stack decides. The constructor refuses a partial gate by
    # default so that a production caller cannot build one by accident.
    gate = RefuseOrCiteGate(
        evaluators=[ExplodingEvaluator(), SilentlyPassingEvaluator()], allow_partial=True
    )
    result = gate.decide(clean_output())

    assert result.decision is Decision.REFUSE
    assert "evaluator_error" in result.reasons
    assert "evaluator backend is down" in result.blocking_findings[0].message


def test_a_gate_with_no_evaluators_cannot_be_built():
    """`RefuseOrCiteGate(evaluators=[])` used to be a gate that allowed anything.

    It ran zero checks, collected zero blocking findings, and returned ALLOW,
    which is the exact opposite of the one property this class claims. An
    adversarial reviewer built one and released a response containing a live
    looking API key through it. An object whose whole promise is "fails closed"
    must not be constructible in a configuration that fails open.
    """
    with pytest.raises(ValueError) as excinfo:
        RefuseOrCiteGate(evaluators=[])

    message = str(excinfo.value)
    for required in ("citation_coverage", "pii", "prompt_injection"):
        assert required in message


def test_dropping_one_blocking_evaluator_is_also_refused():
    """The dangerous version is subtler than an empty list.

    Passing three of the four evaluators looks like a working gate and silently
    stops checking one class of failure, so the constructor names what is
    missing rather than counting.
    """
    from evalharness.evaluators import default_evaluators

    kept = [e for e in default_evaluators() if e.name != "pii"]
    with pytest.raises(ValueError, match="pii"):
        RefuseOrCiteGate(evaluators=kept)


def test_a_partial_gate_is_still_available_when_it_is_asked_for_by_name():
    """The escape hatch exists, and it is opt in at the call site.

    A test that needs two fake evaluators should not have to fake the other
    four. What it must not be able to do is get that gate by accident.
    """
    gate = RefuseOrCiteGate(evaluators=[SilentlyPassingEvaluator()], allow_partial=True)
    assert gate.decide(clean_output()).decision is Decision.ALLOW


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
