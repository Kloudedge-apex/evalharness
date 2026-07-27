"""The centrepiece.

This file exists to make one difference executable rather than asserted: the
naive keyword-anywhere check passes outputs that the real gate refuses.

I shipped the naive shape once in a real gate. It was not caught by reading the
diff, it was caught by someone reproducing the bypass. So the bypass lives in
the repository, next to the fix, with a test that fails the moment the fix
regresses to a document level or substring level check.
"""

from __future__ import annotations

import pytest

from evalharness.fixtures import load_fixtures
from evalharness.gate import Decision, RefuseOrCiteGate
from evalharness.naive_gate import naive_allows
from evalharness.segment import is_factual, parse_output

BYPASS_FIXTURES = ("adv_one_citation_covers_all", "adv_citation_keywords_in_prose")


@pytest.fixture(scope="module")
def fixtures_by_id():
    return {f.id: f for f in load_fixtures()}


@pytest.mark.parametrize("fixture_id", BYPASS_FIXTURES)
def test_naive_gate_is_fooled(fixtures_by_id, fixture_id):
    """The naive check says yes. This assertion is the bug, preserved."""
    fixture = fixtures_by_id[fixture_id]
    assert naive_allows(fixture.output.response) is True


@pytest.mark.parametrize("fixture_id", BYPASS_FIXTURES)
def test_real_gate_refuses_the_same_inputs(fixtures_by_id, fixture_id):
    fixture = fixtures_by_id[fixture_id]
    result = RefuseOrCiteGate().decide(fixture.output)
    assert result.decision is Decision.REFUSE
    assert "unsourced_claim" in result.reasons


def test_one_citation_does_not_cover_the_claims_beside_it(fixtures_by_id):
    """Document scope versus claim scope, stated as a count.

    The output has four factual claims and one citation. The naive check sees
    one citation and passes all four. The real gate sources them one at a time
    and objects three times.
    """
    fixture = fixtures_by_id["adv_one_citation_covers_all"]
    result = RefuseOrCiteGate().decide(fixture.output)

    assert len(fixture.output.factual_claims) == 4
    unsourced = [f for f in result.blocking_findings if f.code == "unsourced_claim"]
    assert len(unsourced) == 3
    assert {f.claim_index for f in unsourced} == {1, 2, 3}


def test_prose_words_are_not_evidence_of_a_citation(fixtures_by_id):
    """Substring scope versus token scope.

    'source' and 'http' appear in the text. Neither is a citation. The naive
    check cannot tell the difference because it asks 'is this string present',
    which is a question with no useful answer.
    """
    fixture = fixtures_by_id["adv_citation_keywords_in_prose"]
    response = fixture.output.response

    assert "source" in response.lower()
    assert "http" in response.lower()
    assert fixture.output.sources == ()
    assert naive_allows(response) is True
    assert RefuseOrCiteGate().decide(fixture.output).decision is Decision.REFUSE


def test_a_substring_scan_reads_outsourced_as_a_citation():
    """Substring scope, in the smallest possible example.

    naive_allows() looks for the string "source" anywhere in the response. The
    word "outsourced" contains it. So a sentence that cites nothing, about a
    topic that has nothing to do with sourcing, satisfies a citation check.

    There is no clever fix for this inside the naive design, which is the
    point: the bug is the question it asks, not the list it asks it against.
    """
    sentence = "The reconciliation work was outsourced to a vendor last quarter."

    assert "source" in sentence.lower()
    assert naive_allows(sentence) is True

    # The real gate treats it as a claim that needs a source, and it has none.
    output = parse_output("outsourced", sentence, ())
    assert RefuseOrCiteGate().decide(output).decision is Decision.REFUSE


def test_naive_gate_agrees_with_the_real_gate_on_a_clean_output(fixtures_by_id):
    """Sanity check: the naive version is not wrong about everything.

    It is wrong about the cases that matter, which is worse, because it looks
    like it is working every time you test it with a well formed example.
    """
    fixture = fixtures_by_id["benign_fully_sourced"]
    assert naive_allows(fixture.output.response) is True
    assert RefuseOrCiteGate().decide(fixture.output).decision is Decision.ALLOW
