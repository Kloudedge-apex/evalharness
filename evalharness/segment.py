"""Turning a response string into claims.

This is the least glamorous file in the repo and the one that decides whether
the gate is any good, because the gate can only demand a citation for a
sentence it managed to identify as a factual assertion.

Three deliberate choices, all of them arguable:

1. Splitting happens on hard breaks (newlines, bullets, numbered items) before
   terminal punctuation, and on coordinated clauses after it. The model
   controls where sentences end, so anything it can use as a boundary has to
   be treated as one here. It is still a regex, not a parser. See README
   limitations.

2. A sentence needs a citation unless it matches an explicit exemption. The
   default is "checkable", not "not checkable". This is the second version of
   this function: the first asked whether the sentence contained a digit or one
   of 39 reporting verbs, which sounds like a wide net and is not, because
   "Northwind Bank is under investigation by the FCA for money laundering
   failures" contains neither and was released with no source at all. A verb
   whitelist cannot be a safety default. It fails open on everything it has not
   heard of, and what it has not heard of includes the copula.

3. The cost of (2) is false refusals on sentences that assert nothing, and that
   cost is asserted in tests/test_segment.py rather than described here, so
   that removing it is a deliberate act with a visible diff.
"""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from .model import Citation, Claim, ModelOutput

# Abbreviations that end in a period without ending a sentence. Short list on
# purpose: every entry is one I hit in the fixture set.
_ABBREVIATIONS = frozenset(
    {
        "inc.",
        "corp.",
        "co.",
        "ltd.",
        "llc.",
        "plc.",
        "u.s.",
        "u.k.",
        "e.g.",
        "i.e.",
        "vs.",
        "approx.",
        "est.",
        "no.",
        "dr.",
        "mr.",
        "mrs.",
        "ms.",
        "jan.",
        "feb.",
        "q1.",
        "q2.",
        "q3.",
        "q4.",
    }
)

_CITATION_MARKER = re.compile(r"\[(\w+)\]")
_TERMINATOR = re.compile(r"[.!?]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# A line break, a bullet, or a numbered list marker ends a claim just as surely
# as a full stop does. Without this, a response written as a markdown bullet
# list is one claim, and a single citation on the first bullet covers all of
# them. That is a total bypass of claim-scope binding, and bullet lists are the
# most common shape of model output there is. See tests/test_segment_adversarial.py.
_HARD_BREAK = re.compile(r"\n+")
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*+•‣◦]|\(?\d+[.)])[ \t]+")

# Coordinated clauses. "X is true [1], and Y is false" is two assertions sharing
# one citation, so the citation must not launder the second one. Splitting here
# costs an occasional spurious boundary, which produces a false refusal, and a
# false refusal is the error this gate is built to prefer.
_CLAUSE_BREAK = re.compile(
    r";\s+|,\s+(?=(?:and|but|while|whereas|although|though|yet)\s+\S+(?:\s+\S+){2,})",
    re.IGNORECASE,
)

_QUESTION = re.compile(r"\?\s*$")

# Sentences that assert nothing about the world and therefore cannot be
# sourced. Every entry is an explicit exemption from the "needs a citation"
# default. Adding to this list widens the hole, so each addition should be
# defensible on its own.
_NON_ASSERTION = re.compile(
    r"""^(?:
          (?:i|we)\s+(?:think|believe|suspect|guess|feel|assume|recommend|suggest|would|could|cannot|can't|do\s+not\s+know|don't\s+know)\b
        | (?:in\s+(?:my|our)\s+(?:view|opinion|experience))\b
        | (?:it\s+(?:seems|appears|may|might|could)\b)
        | (?:this\s+(?:is\s+)?(?:a\s+)?(?:draft|summary|note|template|example)\b)
        | (?:please|see|note|contact|consider|review|let\s+me|let\s+us|feel\s+free|reach\s+out|here\s+is|here\s+are)\b
        | (?:i\s+(?:cannot|will\s+not)\s+)
        | (?:refused\b|refusing\b)
        # Speech acts: offers, thanks, and statements about the message itself
        # rather than about the world. Nothing here can be sourced because
        # nothing here is a claim.
        | (?:happy\s+to|glad\s+to|delighted\s+to|thanks\b|thank\s+you\b)
        | (?:nothing\s+(?:here|in\s+this|further)\b)
        | (?:no\s+(?:action|decision)\s+(?:is\s+)?(?:needed|required)\b)
      )""",
    re.IGNORECASE | re.VERBOSE,
)

# Statements about the document rather than about the world. Anchored at the
# end so that "the notes are attached" is exempt while "the fraud is attached
# to account 4021" is not.
_SELF_REFERENCE = re.compile(r"\b(?:attached|enclosed|below|above)\s*\.?\s*$", re.IGNORECASE)


def _split_on_terminators(text: str) -> List[str]:
    """Split one block on terminal punctuation followed by whitespace.

    Skips a candidate boundary when the punctuation is not followed by
    whitespace (decimals such as 12.5, and dotted URLs) or when the preceding
    token is a known abbreviation *and* the next sentence does not obviously
    start. An abbreviation used to swallow everything up to the following full
    stop, which let an uncited sentence inherit the next sentence's citation.
    """
    sentences: List[str] = []
    start = 0
    for match in _TERMINATOR.finditer(text):
        end = match.end()
        if end < len(text) and not text[end].isspace():
            continue
        candidate = text[start:end].strip()
        if not candidate:
            continue
        last_token = candidate.split()[-1].lower()
        if last_token in _ABBREVIATIONS and not _starts_new_sentence(text, end):
            continue
        sentences.append(candidate)
        start = end

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _starts_new_sentence(text: str, position: int) -> bool:
    """Does an uppercase word start at the next non-space character?

    "Northwind Inc. announced" is one sentence: lowercase continuation. "by
    Northwind Inc. Northwind is insolvent" is two, and treating it as one is
    how the second assertion stole the first one's citation.
    """
    rest = text[position:].lstrip()
    return bool(rest) and rest[0].isupper()


def split_sentences(text: str) -> List[str]:
    """Split a response into claim-sized units.

    Hard breaks first (newlines and list markers), then terminal punctuation,
    then coordinated clauses. Boundaries the model controls by pressing Enter
    are boundaries here too.
    """
    text = text.strip()
    if not text:
        return []

    sentences: List[str] = []
    for block in _HARD_BREAK.split(text):
        block = _LIST_MARKER.sub("", block.strip())
        if not block:
            continue
        for sentence in _split_on_terminators(block):
            for clause in _CLAUSE_BREAK.split(sentence):
                clause = clause.strip()
                if clause:
                    sentences.append(clause)
    return sentences


def extract_citation_ids(sentence: str) -> Tuple[str, ...]:
    """Pull the `[n]` markers out of a sentence, in order, without duplicates."""
    seen: List[str] = []
    for match in _CITATION_MARKER.finditer(sentence):
        marker = match.group(1)
        if marker not in seen:
            seen.append(marker)
    return tuple(seen)


def strip_citations(sentence: str) -> str:
    return _CITATION_MARKER.sub(" ", sentence)


def is_factual(sentence: str) -> bool:
    """Does this sentence assert something a reader could go and check?

    The default is yes. Everything is treated as a checkable assertion unless
    it matches an explicit exemption, because that is the only shape of this
    function that is actually biased towards refusing.

    The previous version answered yes only for a digit or one of 39 reporting
    verbs, which sounds wide and is not: "Northwind Bank is under investigation
    by the FCA for money laundering failures" contains neither, so it needed no
    citation and was released unsourced. The hole was the entire English
    copula. A whitelist of verbs cannot be a safety default; the exemption list
    below can, because every entry in it is a sentence that asserts nothing
    about the world.

    Citation markers are stripped first, otherwise the digit inside `[1]` would
    decide the question for the wrong reason.
    """
    body = strip_citations(sentence).strip()
    if not body:
        return False
    if _QUESTION.search(body):
        return False
    if _NON_ASSERTION.match(body):
        return False
    if _SELF_REFERENCE.search(body):
        return False
    # A fragment with no verb-like content is a heading or a label, not a claim.
    return len(_WORD.findall(body)) >= 3


def parse_claims(response: str) -> Tuple[Claim, ...]:
    claims = []
    for index, sentence in enumerate(split_sentences(response)):
        claims.append(
            Claim(
                index=index,
                text=sentence,
                citation_ids=extract_citation_ids(sentence),
                is_factual=is_factual(sentence),
            )
        )
    return tuple(claims)


def parse_output(output_id: str, response: str, sources: Sequence[Citation]) -> ModelOutput:
    return ModelOutput(
        id=output_id,
        response=response,
        sources=tuple(sources),
        claims=parse_claims(response),
    )
