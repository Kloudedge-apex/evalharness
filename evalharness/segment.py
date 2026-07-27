"""Turning a response string into claims.

This is the least glamorous file in the repo and the one that decides whether
the gate is any good, because the gate can only demand a citation for a
sentence it managed to identify as a factual assertion.

Three deliberate choices, all of them arguable:

1. Sentence splitting is regex based, with a small abbreviation guard. It is
   not a parser. See README limitations.

2. A sentence is treated as factual if it contains a digit or a reporting verb.
   That is a wide net on purpose: the cheap error is asking for a citation on a
   sentence that did not need one, the expensive error is letting an unsourced
   assertion through.

3. The reporting verb check is a set membership test over tokenised words, not
   a substring scan of the raw text. That difference is the whole point of
   tests/test_naive_vs_real.py: "led" is a reporting verb, "ledger" is not, and
   a substring scan cannot tell them apart.
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

# Verbs that report an event in the world. If a sentence uses one, a reader can
# in principle go and check whether the event happened, so it needs a source.
_REPORTING_VERBS = frozenset(
    {
        "acquired",
        "acquires",
        "announced",
        "announces",
        "appointed",
        "appoints",
        "closed",
        "closes",
        "expanded",
        "expands",
        "fell",
        "filed",
        "files",
        "grew",
        "grows",
        "hired",
        "hires",
        "invested",
        "invests",
        "launched",
        "launches",
        "led",
        "leads",
        "merged",
        "merges",
        "named",
        "opened",
        "opens",
        "partnered",
        "partners",
        "raised",
        "raises",
        "reported",
        "reports",
        "rose",
        "secured",
        "secures",
        "shipped",
        "ships",
        "signed",
        "signs",
    }
)

_CITATION_MARKER = re.compile(r"\[(\w+)\]")
_TERMINATOR = re.compile(r"[.!?]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def split_sentences(text: str) -> List[str]:
    """Split on terminal punctuation followed by whitespace.

    Skips a candidate boundary when the punctuation is not followed by
    whitespace (decimals such as 12.5, and dotted URLs) or when the preceding
    token is a known abbreviation.
    """
    text = text.strip()
    if not text:
        return []

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
        if last_token in _ABBREVIATIONS:
            continue
        sentences.append(candidate)
        start = end

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
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

    Citation markers are stripped first, otherwise the digit inside `[1]` would
    make every cited sentence look factual for the wrong reason.
    """
    body = strip_citations(sentence)
    if any(char.isdigit() for char in body):
        return True
    words = {word.lower() for word in _WORD.findall(body)}
    return bool(words & _REPORTING_VERBS)


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
