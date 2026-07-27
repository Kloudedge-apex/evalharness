"""Citation coverage evaluator."""

from __future__ import annotations

from evalharness.evaluators.citation import CitationCoverageEvaluator
from evalharness.model import Citation
from evalharness.segment import parse_output

GOOD_SOURCE = Citation(
    id="1",
    title="Northwind migration",
    url="https://example.invalid/n",
    published="2026-02-11",
    snippet="Northwind announced a core banking migration on 2026-02-11.",
)


def evaluate(response, sources=(GOOD_SOURCE,)):
    return CitationCoverageEvaluator().evaluate(parse_output("t", response, sources))


def test_a_sourced_claim_passes_with_full_coverage():
    result = evaluate("Northwind announced a migration on 2026-02-11 [1].")
    assert result.passed is True
    assert result.score == 1.0


def test_an_unsourced_factual_claim_blocks():
    result = evaluate("Northwind announced a migration on 2026-02-11.")
    assert result.passed is False
    assert [f.code for f in result.findings] == ["unsourced_claim"]
    assert result.score == 0.0


def test_coverage_is_a_ratio_over_factual_claims():
    result = evaluate(
        "Northwind announced a migration on 2026-02-11 [1]. The budget is 40 million dollars."
    )
    assert result.score == 0.5


def test_an_output_with_nothing_checkable_scores_one():
    """No factual claims means nothing to source, not a coverage failure."""
    result = evaluate("Happy to talk this through whenever suits you.", sources=())
    assert result.passed is True
    assert result.score == 1.0


def test_a_dangling_marker_is_not_a_citation():
    result = evaluate("Northwind announced a migration on 2026-02-11 [4].")
    assert [f.code for f in result.findings] == ["dangling_citation"]


def test_a_source_with_no_locator_or_content_is_not_a_citation():
    stub = Citation(id="1", title="", url="", snippet="")
    result = evaluate("Northwind announced a migration on 2026-02-11 [1].", sources=(stub,))
    assert [f.code for f in result.findings] == ["unresolvable_source"]


def test_a_source_needs_both_a_locator_and_retrieved_content():
    locator_only = Citation(id="1", url="https://example.invalid/n", snippet="")
    content_only = Citation(id="1", url="", title="", snippet="Some retrieved text.")
    for source in (locator_only, content_only):
        result = evaluate("Northwind announced a migration on 2026-02-11 [1].", sources=(source,))
        assert [f.code for f in result.findings] == ["unresolvable_source"]


def test_findings_point_at_the_claim_that_failed():
    """A reviewer needs to know which sentence to fix, not just that one failed."""
    result = evaluate(
        "Northwind announced a migration on 2026-02-11 [1]. The budget is 40 million dollars."
    )
    assert result.findings[0].claim_index == 1


def test_coverage_says_nothing_about_whether_the_source_supports_the_claim():
    """The stated limit of this evaluator, asserted so it cannot be forgotten."""
    unrelated = Citation(
        id="1",
        title="Weather report",
        url="https://example.invalid/weather",
        snippet="Rain is expected across the north west on Thursday.",
    )
    result = evaluate("Northwind raised 12 million dollars [1].", sources=(unrelated,))
    assert result.passed is True
