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
    """Otherwise the digit inside [1] decides the question for the wrong reason."""
    assert "1" not in strip_citations("An opinion sentence [1].")
    # Under the safe default this sentence IS treated as factual: the classifier
    # exempts only explicit non-assertions, and "this reads like a good fit"
    # is not on that list. Stripping still matters, because it is what stops
    # the marker's own digit from being the reason.
    assert is_factual("This reads like a good fit for us [1].") is True


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
        "The ledger reconciliation notes are attached.",
        "Thanks for the introduction.",
        "Nothing here needs a decision from your side yet.",
        "I think this one is worth a look.",
    ],
)
def test_uncheckable_sentences_are_not_factual(sentence):
    assert is_factual(sentence) is False


@pytest.mark.parametrize(
    "sentence",
    [
        "This is the kind of account that buys tooling late.",
        "That surprised nobody.",
    ],
)
def test_known_false_refusals_are_asserted_rather_than_hidden(sentence):
    """The measured cost of the safe default, written down as a test.

    These sentences assert nothing a reader could check, and the classifier
    demands a citation for them anyway. That is a false refusal and it is the
    price of defaulting to "needs a source" instead of matching a verb list.

    It is asserted here rather than described in the README so that anyone who
    later teaches the classifier to exempt hedged characterisations has to
    delete a passing test to do it, and has to think about what else that
    exemption would let through.
    """
    assert is_factual(sentence) is True


@pytest.mark.parametrize(
    "sentence",
    [
        "The auditors note a shortfall in the reconciliation account.",
        "The board will please the regulator by settling early.",
        "The committee asked us to review the ledger before the audit.",
        "The regulator did not see the omission until the audit closed.",
    ],
)
def test_the_exemption_list_only_matches_at_the_start_of_a_sentence(sentence):
    """The same substring-versus-position bug as naive_gate, one level down.

    Every sentence here contains an exemption word ("note", "please", "review",
    "see") somewhere in the middle, and every one of them asserts something a
    reader could check. `_NON_ASSERTION` is anchored, so "Please review the
    ledger" is exempt and "The auditors note a shortfall" is not.

    De-anchoring it is a one character edit that reads like a harmless
    loosening and silently releases all four. The mutation harness
    (`mutations/run.py`, mutant `classifier_exempts_everything`) makes exactly
    that edit, and this is the test that has to notice.
    """
    assert is_factual(sentence) is True


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
    # "That surprised nobody" is not checkable, and the classifier asks for a
    # citation anyway. See test_known_false_refusals_are_asserted_rather_than_hidden.
    assert claims[1].is_factual is True
    assert [c.index for c in claims] == [0, 1]
