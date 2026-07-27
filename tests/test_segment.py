"""Claim segmentation and the factual claim classifier.

The gate can only demand a citation for a sentence it recognised as a claim, so
these are the assumptions everything else rests on. They are regex level
assumptions, and the tests say so.
"""

from __future__ import annotations

import pytest

from evalharness.segment import (
    extract_citation_ids,
    is_factual,
    parse_claims,
    split_sentences,
    strip_citations,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("One. Two. Three.", 3),
        ("Revenue grew 12.5 percent last year.", 1),
        ("Northwind Bank Inc. filed in March. The filing is public.", 2),
        ("See https://example.invalid/a.b for detail. It is public.", 2),
        ("No terminator here", 1),
        ("   ", 0),
        ("", 0),
    ],
)
def test_sentence_splitting(text, expected):
    assert len(split_sentences(text)) == expected


def test_decimal_does_not_end_a_sentence():
    assert split_sentences("Margin was 12.5 percent.") == ["Margin was 12.5 percent."]


def test_abbreviation_does_not_end_a_sentence():
    sentences = split_sentences("Northwind Corp. raised a round. Nobody expected it.")
    assert sentences[0] == "Northwind Corp. raised a round."


def test_citation_markers_are_extracted_in_order_without_duplicates():
    assert extract_citation_ids("A claim [2] with two markers [1] and a repeat [2].") == ("2", "1")


def test_citations_are_stripped_before_the_factual_check():
    """Otherwise the digit inside [1] makes every cited sentence look factual."""
    assert "1" not in strip_citations("An opinion sentence [1].")
    assert is_factual("This reads like a good fit for us [1].") is False


@pytest.mark.parametrize(
    "sentence",
    [
        "Revenue fell 12 percent.",
        "The migration starts in 2027.",
        "Northwind acquired a competitor.",
        "The round was led by Acme Partners.",
    ],
)
def test_checkable_sentences_are_factual(sentence):
    assert is_factual(sentence) is True


@pytest.mark.parametrize(
    "sentence",
    [
        "Happy to walk through the options whenever suits you.",
        "This is the kind of account that buys tooling late.",
        "The ledger reconciliation notes are attached.",
    ],
)
def test_uncheckable_sentences_are_not_factual(sentence):
    assert is_factual(sentence) is False


def test_the_classifier_errs_towards_demanding_a_citation():
    """Documented bias, asserted so that changing it is a deliberate act.

    A hedge does not exempt a sentence that still contains something checkable.
    Refusing a hedged claim is annoying. Publishing an unsourced one is not.
    """
    assert is_factual("Northwind might have raised 12 million dollars.") is True


def test_parse_claims_binds_citations_to_the_sentence_they_appear_in():
    claims = parse_claims("Northwind raised 12 million dollars [1]. That surprised nobody.")

    assert claims[0].citation_ids == ("1",)
    assert claims[0].is_factual is True
    assert claims[1].citation_ids == ()
    assert claims[1].is_factual is False
    assert [c.index for c in claims] == [0, 1]
