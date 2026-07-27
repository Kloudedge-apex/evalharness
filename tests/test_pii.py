"""PII and secret detection, including the false positives it must not raise."""

from __future__ import annotations

import pytest

from evalharness.evaluators.pii import PIIEvaluator, luhn_valid, redact
from evalharness.segment import parse_output


def codes(response):
    result = PIIEvaluator().evaluate(parse_output("t", response, []))
    return sorted({f.code for f in result.findings})


@pytest.mark.parametrize(
    "response,expected",
    [
        ("Write to dana.whitfield@example.invalid for detail.", ["pii_email"]),
        ("Call +44 20 7946 0958 to confirm.", ["pii_phone"]),
        ("Call 415 555 0123 to confirm.", ["pii_phone"]),
        ("The reference is 123-45-6789 on file.", ["pii_ssn"]),
        ("Charged to 4111 1111 1111 1111 today.", ["pii_card"]),
        ("The key is sk_live_9f2Ab7Kq4Lm0Zx8T today.", ["secret_api_key"]),
        ("Uses AKIAIOSFODNN7EXAMPLE for access.", ["secret_api_key"]),
    ],
)
def test_detects_known_formats(response, expected):
    assert codes(response) == expected


@pytest.mark.parametrize(
    "response",
    [
        "The migration completed on 2026-02-11 as planned.",
        "The budget is 40 million dollars over three years.",
        "Order 1234567890123456 shipped yesterday.",
        "Version 1.2.3 was released in the first quarter.",
    ],
)
def test_does_not_fire_on_ordinary_numbers(response):
    assert codes(response) == []


def test_card_candidates_are_luhn_checked_before_being_reported():
    """A sixteen digit order reference is not a card number.

    An evaluator that reports every long digit run gets switched off by
    whoever is on call, and then it is not protecting anything.
    """
    assert luhn_valid("4111111111111111") is True
    assert luhn_valid("1234567890123456") is False
    assert codes("Order 1234567890123456 shipped.") == []
    assert codes("Card 4111111111111111 was charged.") == ["pii_card"]


def test_luhn_rejects_lengths_outside_the_card_range():
    assert luhn_valid("123") is False
    assert luhn_valid("41111111111111111111111") is False


def test_a_clean_response_scores_one_and_a_leak_scores_zero():
    """Binary by design. One leak is a failure, so there is no partial credit."""
    clean = PIIEvaluator().evaluate(parse_output("t", "Nothing sensitive here at all.", []))
    leaky = PIIEvaluator().evaluate(parse_output("t", "Mail dana@example.invalid now.", []))
    assert clean.score == 1.0
    assert leaky.score == 0.0


def test_findings_do_not_reproduce_the_value_they_found():
    """Otherwise the detector copies the leak into your terminal and your logs."""
    result = PIIEvaluator().evaluate(
        parse_output("t", "Mail dana.whitfield@example.invalid or call 415 555 0123.", [])
    )
    rendered = " ".join(f.message for f in result.findings)

    assert "dana.whitfield" not in rendered
    assert "415 555 0123" not in rendered
    assert "d***@example.invalid" in rendered


def test_redaction_of_a_secret_does_not_show_its_tail():
    """Card last four is a convention. Doing the same to a key would leak entropy."""
    assert redact("4111 1111 1111 1111") == "***1111"
    assert redact("sk_live_9f2Ab7Kq4Lm0Zx8T") == "sk_***"
    assert redact("dana@example.invalid") == "d***@example.invalid"
