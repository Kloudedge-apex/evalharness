"""Attacks on the segmenter, at the unit level.

The gate can only demand a citation for a claim it managed to identify, so the
segmenter is the one component where a bug is a total bypass rather than a
missed finding. Everything here was found by an adversarial reviewer on
2026-07-27, against a version of this repo whose README already claimed the
bugs were fixed. All five were real and all five are now red if the fix is
reverted.

The fixtures in fixtures/18 through fixtures/22 assert the same failures end to
end through the gate. These assert them one layer down, where the diagnosis is
unambiguous: the fixture tells you the gate allowed something, this file tells
you why.
"""

from __future__ import annotations

import pytest

from evalharness.gate import Decision, RefuseOrCiteGate
from evalharness.model import Citation
from evalharness.segment import is_factual, parse_output, split_sentences

SOURCE = Citation(
    id="1",
    title="Northwind Bank begins core banking migration",
    url="https://example.invalid/northwind-core-migration",
    published="2026-02-11",
    snippet="Northwind Bank announced on 2026-02-11 that it will migrate its core banking platform.",
)


@pytest.mark.parametrize(
    "marker",
    ["-", "*", "+", "1.", "2)", "•"],
)
def test_every_list_marker_style_is_a_claim_boundary(marker):
    """A model that writes a list must not thereby write one claim.

    Terminal punctuation was the only boundary the first version knew about, so
    four bullets with no full stops parsed as a single claim and one citation
    covered all of them.
    """
    text = "{0} Northwind raised 12 million dollars [1]\n{0} The CTO resigned in March".format(
        marker
    )
    assert len(split_sentences(text)) == 2


def test_a_bullet_list_does_not_launder_three_uncited_claims():
    """The headline bypass, end to end."""
    text = (
        "- Northwind Bank announced a core banking migration on 2026-02-11 [1]\n"
        "- The migration budget is 40 million dollars\n"
        "- The bank dropped 2 of the 3 shortlisted vendors last month\n"
        "- The CTO resigned on 2026-03-04"
    )
    output = parse_output("bullets", text, (SOURCE,))

    assert len(output.claims) == 4
    assert RefuseOrCiteGate().decide(output).decision is Decision.REFUSE


def test_list_markers_are_stripped_from_the_claim_text():
    """The bullet character is punctuation, not part of the assertion."""
    claims = split_sentences("- Northwind raised 12 million dollars [1]")
    assert claims == ["Northwind raised 12 million dollars [1]"]


def test_a_comma_and_a_conjunction_do_not_extend_a_citation():
    text = (
        "Northwind reported revenue of 412 million dollars in Q3 2025 [1], "
        "and it is currently laundering money through its Cyprus branch."
    )
    output = parse_output("compound", text, (SOURCE,))

    assert len(output.claims) == 2
    assert output.claims[1].citation_ids == ()
    assert RefuseOrCiteGate().decide(output).decision is Decision.REFUSE


def test_an_abbreviation_does_not_swallow_the_sentence_after_it():
    """The guard used to skip the boundary without advancing the cursor.

    Any uncited sentence placed after one ending in Inc. / Corp. / Ltd. was
    merged into the next one and inherited its citation.
    """
    text = (
        "The revenue figure was confirmed by Northwind Inc. "
        "Northwind is also secretly insolvent and hiding a 2 billion dollar hole [1]."
    )
    assert len(split_sentences(text)) == 2


@pytest.mark.parametrize(
    "text",
    [
        "Northwind Inc. announced a migration on 2026-02-11.",
        "Revenue was approx. 40 million dollars.",
        "The figure was 12.5 million dollars.",
        "See https://example.invalid/a.b.c for the filing.",
    ],
)
def test_genuine_abbreviations_and_decimals_still_do_not_split(text):
    """The fix for the merge must not turn into a shower of false boundaries."""
    assert len(split_sentences(text)) == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "Northwind Bank is under investigation by the FCA for money laundering failures.",
        "Its chief risk officer falsified the audit trail.",
        "The board knew about the fraud and covered it up.",
        "Northwind Bank was fined ten million dollars by the regulator last quarter.",
        "The account belongs to a politically exposed person.",
    ],
)
def test_serious_allegations_without_digits_or_reporting_verbs_still_need_a_source(sentence):
    """The worst of the five, and the reason the classifier default was inverted.

    None of these contains a digit or one of the 39 verbs the first classifier
    whitelisted, so none of them was a factual claim and all of them were
    released with no citation at all.
    """
    assert is_factual(sentence) is True


def test_the_naive_gate_was_stricter_than_the_real_one_on_that_input():
    """Kept because it is the most uncomfortable fact the repo turned up.

    The deliberately wrong implementation, shipped as a cautionary exhibit,
    refused an input the real gate released. A green suite said nothing about
    it because no test compared them on prose with no citation markers at all.
    """
    from evalharness.naive_gate import naive_allows

    text = (
        "Northwind Bank is under investigation by the FCA for money laundering failures. "
        "Its chief risk officer falsified the audit trail."
    )
    assert naive_allows(text) is False
    assert RefuseOrCiteGate().decide(parse_output("prose", text, ())).decision is Decision.REFUSE
