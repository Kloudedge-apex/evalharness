"""Support overlap evaluator: advisory, lexical, and honest about it."""

from __future__ import annotations

from evalharness.evaluators.support import SupportOverlapEvaluator
from evalharness.model import Citation, Severity
from evalharness.segment import parse_output


def evaluate(response, sources):
    return SupportOverlapEvaluator().evaluate(parse_output("t", response, sources))


RELATED = Citation(
    id="1",
    title="Northwind funding",
    url="https://example.invalid/funding",
    snippet="Northwind closed a 12 million dollar funding round on 2026-01-20.",
)

UNRELATED = Citation(
    id="1",
    title="Northwind opens an office in Leeds",
    url="https://example.invalid/leeds",
    snippet="Northwind has signed a lease on office space in Leeds.",
)


def test_a_claim_that_matches_its_source_raises_nothing():
    result = evaluate("Northwind closed a 12 million dollar funding round on 2026-01-20 [1].", (RELATED,))
    assert result.findings == ()
    assert result.score > 0.9


def test_a_claim_cited_to_an_unrelated_document_is_flagged():
    result = evaluate("Northwind closed a 12 million dollar funding round on 2026-01-20 [1].", (UNRELATED,))
    assert [f.code for f in result.findings] == ["low_lexical_overlap"]


def test_the_flag_is_advisory_and_never_blocking():
    """This is a lexical heuristic. It is nowhere near good enough to refuse on."""
    result = evaluate("Northwind closed a 12 million dollar funding round on 2026-01-20 [1].", (UNRELATED,))
    assert result.findings[0].severity is Severity.ADVISORY
    assert result.passed is True


def test_high_overlap_does_not_mean_the_source_supports_the_claim():
    """The limit of the method, written as a test so it cannot be soft pedalled.

    The snippet below contradicts the claim word for word and still scores as
    high overlap, because overlap is vocabulary sharing and nothing else.
    Entailment needs a model, and this repository makes no inference calls.
    """
    contradiction = Citation(
        id="1",
        title="Northwind funding",
        url="https://example.invalid/funding",
        snippet="Northwind did not close a 12 million dollar funding round on 2026-01-20.",
    )
    result = evaluate("Northwind closed a 12 million dollar funding round on 2026-01-20 [1].", (contradiction,))
    assert result.findings == ()


def test_claims_with_no_checkable_citation_are_skipped_rather_than_scored_zero():
    """An unsourced claim is citation coverage's problem, not this evaluator's.

    Scoring it zero here would double count the same failure in two places on
    the scorecard, which makes the numbers look worse and mean less.
    """
    result = evaluate("Northwind closed a 12 million dollar round.", ())
    assert result.findings == ()
    assert result.score == 1.0
