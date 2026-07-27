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
   of 41 reporting verbs, which sounds like a wide net and is not, because
   "Northwind Bank is under investigation by the FCA for money laundering
   failures" contains neither and was released with no source at all. A verb
   whitelist cannot be a safety default. It fails open on everything it has not
   heard of, and what it has not heard of includes the copula.

   Every exemption below is also *bounded*. The second adversarial pass showed
   that an unbounded exemption is a wildcard: "Note that <any allegation>" was
   released because the sentence began with "note", and "<any allegation>, as
   set out below" was released because it ended with "below". An opener or a
   tail cannot neutralise nine words of assertion sitting between them, so an
   exemption now applies only to a sentence short enough to be the thing the
   exemption describes. See _EXEMPTION_WORD_LIMIT.

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

# The subset of the above that is normally followed by a number: "approx. 40
# million", "no. 7", "Jan. 14", "Q1. 2026". A digit after one of these
# continues the same sentence.
#
# The distinction earns its keep in _starts_new_sentence. A digit after a NAME
# abbreviation does start a new sentence ("confirmed by Northwind Inc. 4021
# accounts were frozen" is two claims, and treating it as one let the second
# inherit the first's citation), but a digit after a QUANTITY abbreviation is
# just the quantity.
_QUANTITY_ABBREVIATIONS = frozenset(
    {"approx.", "no.", "est.", "vs.", "e.g.", "i.e.", "jan.", "feb.", "q1.", "q2.", "q3.", "q4."}
)

_CITATION_MARKER = re.compile(r"\[(\w+)\]")

# Terminal punctuation in the scripts this is likely to meet. The ASCII-only
# version released a Chinese, Japanese or Hindi response as a single claim,
# because none of 。！？। is a full stop as far as `[.!?]` is concerned.
_TERMINATOR = re.compile(r"[.!?。！？؟۔।॥…]+")

# A word token in any script, not just Latin. The ASCII-only version of this
# pattern was the whole of the non-Latin bypass: `is_factual` counted zero
# words in "Северный банк находится под следствием", concluded it was a
# fragment rather than a claim, and released a serious allegation with no
# source at all. See _has_claim_weight.
_WORD = re.compile(r"[^\W\d_][^\W\d_'\-]*", re.UNICODE)

# Scripts written without spaces between words. A regex word token in these
# is a whole sentence, and a single character in them is a morpheme rather
# than a letter, so both of the thresholds in _has_claim_weight are counting
# the wrong unit. CJK unified ideographs and their extension A, the
# compatibility block, kana, and hangul syllables.
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")

# A line break, a bullet, or a numbered list marker ends a claim just as surely
# as a full stop does. Without this, a response written as a markdown bullet
# list is one claim, and a single citation on the first bullet covers all of
# them. That is a total bypass of claim-scope binding, and bullet lists are the
# most common shape of model output there is. See tests/test_segment_adversarial.py.
#
# The class is every character Python's own str.splitlines() treats as a line
# break, not just \n. Swapping \n for \r or U+2028 in a bullet list was enough
# to collapse three bullets back into one claim and re-open the bypass above.
_HARD_BREAK = re.compile(r"[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]+")
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*+•‣◦]|\(?\d+[.)])[ \t]+")

# Coordinated clauses. "X is true [1], and Y is false" is two assertions sharing
# one citation, so the citation must not launder the second one. Splitting here
# costs an occasional spurious boundary, which produces a false refusal, and a
# false refusal is the error this gate is built to prefer.
#
# The first version of this pattern knew about semicolons and seven coordinating
# conjunctions, which meant a colon, a spaced dash, a markdown table cell and
# the words "so", "because" and "however" all still laundered a citation across
# a clause boundary. Anything the model can use to join two assertions has to be
# a boundary here.
_CLAUSE_BREAK = re.compile(
    r"""
      ;\s+
    | :\s+
    | \s*—\s*                       # em dash, a clause join in prose
    | \s+[–−]\s+               # spaced en dash / minus (unspaced is a range)
    | \s*\|\s*                           # markdown table cell boundary
    | ,\s+(?=(?:and|but|while|whereas|although|though|yet|so|because|however|
                therefore|which|whilst|since|as)\s+\S+(?:\s+\S+){2,})
    | \s+(?=(?:however|therefore|moreover|furthermore|nevertheless|nonetheless)\s*,)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_QUESTION = re.compile(r"\?\s*$")

# How long a sentence may be and still be waved through by a prefix or suffix
# exemption. The number is arbitrary and is stated here rather than buried,
# because the honest description of it is "a guess that bounds the damage".
#
# The reasoning: every exemption below recognises a sentence by a *fragment* of
# it, an opening ("please see", "I think") or a tail ("attached", "below").
# Without a bound, that fragment is a wildcard, and the second adversarial pass
# used it as one. "Note that Northwind Bank is under investigation by the FCA
# for money laundering failures" was released because it starts with "note".
# The sentences these exemptions are meant to cover are short: "Please see the
# attached brief" is five words. Allegations are not. Twelve words is wide
# enough for a real courtesy line and narrow enough that smuggling an
# allegation through requires writing an unnaturally terse one.
#
# This bound does NOT apply to the hedge openers ("I think", "in my view"),
# which are handled separately: see _HEDGE and is_factual.
_EXEMPTION_WORD_LIMIT = 12

# Hedges. A sentence that reports the speaker's own state of mind rather than
# the world is not checkable against a source, so it is exempt at any length.
# This is a real hole and it is documented in the README as one: a model that
# prefixes every allegation with "I believe" walks straight through this gate.
# It is kept because the alternative, refusing every hedged sentence, makes the
# gate unusable on the drafting workflows it exists for.
#
# Bounding it the way the directive openers are bounded is not the fix it looks
# like, and the arithmetic says so in both directions. "We believe Northwind
# Bank laundered two billion dollars through its Cyprus branch" is twelve words,
# so a twelve word bound leaves it exempt; and "I cannot answer that" is four,
# so no bound low enough to catch the first is high enough to spare the second,
# which is the one sentence a refusing model most needs to be able to say. The
# only thing that closes this hole is dropping the exemption outright. So it is
# documented instead, here and in the README limitations, which quotes this
# reasoning.
_HEDGE = re.compile(
    r"""^(?:
          (?:i|we)\s+(?:think|believe|suspect|guess|feel|assume|recommend|suggest|would|could|cannot|can't|do\s+not\s+know|don't\s+know)\b
        | (?:in\s+(?:my|our)\s+(?:view|opinion|experience))\b
        | (?:it\s+(?:seems|appears|may|might|could)\b)
        | (?:i\s+(?:cannot|will\s+not)\s+)
        | (?:refused\b|refusing\b)
      )""",
    re.IGNORECASE | re.VERBOSE,
)

# Sentences that assert nothing about the world and therefore cannot be
# sourced. Every entry is an explicit exemption from the "needs a citation"
# default. Adding to this list widens the hole, so each addition should be
# defensible on its own, and each is bounded by _EXEMPTION_WORD_LIMIT.
_NON_ASSERTION = re.compile(
    r"""^(?:
          (?:this\s+(?:is\s+)?(?:a\s+)?(?:draft|summary|note|template|example)\b)
        | (?:please|see|contact|consider|review|let\s+me|let\s+us|feel\s+free|reach\s+out|here\s+is|here\s+are)\b
        # "note" without a following "that". "Note the revised figures" points
        # at a document; "Note that the licence was revoked" is an assertion
        # wearing a directive as a hat, and a that-complement is always the
        # latter.
        | (?:note\b(?!\s+that\b))
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
# to account 4021" is not. End-anchoring alone was not enough: an arbitrarily
# long allegation followed by ", as set out below" inherited the exemption, so
# this is bounded by _EXEMPTION_WORD_LIMIT too.
_SELF_REFERENCE = re.compile(r"\b(?:attached|enclosed|below|above)\s*\.?\s*$", re.IGNORECASE)


def _is_inside_token(text: str, end: int) -> bool:
    """Is this terminator inside a token rather than at the end of a sentence?

    The rule used to be "not followed by whitespace means not a boundary",
    which is right for 12.5 and for example.invalid and wrong for everything
    else. Deleting the space after a full stop was therefore a one-character
    bypass: "...migration on 2026-02-11 [1].Northwind Bank is laundering money"
    parsed as a single claim, and the allegation inherited the citation that
    belonged to the migration. `."` and `.)` did the same.

    So the skip is now narrow. A terminator is inside a token only when the
    character after it continues the token: a digit (12.5, 1.0.3) or a
    lowercase letter (example.invalid). A quote, a bracket, a citation marker
    or a capital letter starts something new, whether or not the writer left a
    space.
    """
    if end >= len(text):
        return False
    following = text[end]
    if following.isspace():
        return False
    return following.isdigit() or following.islower()


def _split_on_terminators(text: str) -> List[str]:
    """Split one block on terminal punctuation.

    Skips a candidate boundary when the terminator is inside a token (see
    _is_inside_token) or when the preceding token is a known abbreviation *and*
    the next sentence does not obviously start. An abbreviation used to swallow
    everything up to the following full stop, which let an uncited sentence
    inherit the next sentence's citation.
    """
    sentences: List[str] = []
    start = 0
    for match in _TERMINATOR.finditer(text):
        end = match.end()
        if _is_inside_token(text, end):
            continue
        candidate = text[start:end].strip()
        if not candidate:
            continue
        last_token = candidate.split()[-1].lower()
        if last_token in _ABBREVIATIONS:
            allow_digit = last_token not in _QUANTITY_ABBREVIATIONS
            if not _starts_new_sentence(text, end, allow_digit=allow_digit):
                continue
        sentences.append(candidate)
        start = end

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


# Characters that open a sentence without being letters: quotation marks of
# several nationalities, brackets, and the `[` of a citation marker.
_SENTENCE_OPENERS = frozenset("\"'`([{«»‹›")


def _starts_new_sentence(text: str, position: int, allow_digit: bool = True) -> bool:
    """Does something that can begin a sentence start at the next non-space?

    "Northwind Inc. announced" is one sentence: lowercase continuation. "by
    Northwind Inc. Northwind is insolvent" is two, and treating it as one is
    how the second assertion stole the first one's citation.

    The first version of this asked only `rest[0].isupper()`, so the
    abbreviation guard still swallowed the next sentence whenever that sentence
    began with a digit ("Northwind Inc. 4021 accounts were frozen"), a citation
    marker, or an opening quote. Those are sentence starts too.

    `allow_digit` is False after a quantity abbreviation, where the digit is
    the quantity rather than a new sentence: "Revenue was approx. 40 million".
    """
    rest = text[position:].lstrip()
    if not rest:
        return False
    first = rest[0]
    if first.isdigit():
        return allow_digit
    return first.isupper() or first in _SENTENCE_OPENERS


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


def _has_claim_weight(words: List[str]) -> bool:
    """Is there enough here to be a sentence rather than a heading or a label?

    Two ways to qualify, because one of them does not survive contact with a
    writing system that has no spaces.

    Three word tokens is the space-delimited test. It is the whole test in the
    first version of this file, and combined with an ASCII-only word pattern it
    meant every non-Latin response scored zero words, counted as a fragment,
    and was released with no source at all: "北方银行因洗钱失败正在接受调查" is
    one token to a regex and a serious allegation to a reader.

    So a total of twelve letters also qualifies. Chinese, Japanese and Thai
    clear it in one token. It also promotes short English assertions that the
    word count used to miss, "Northwind collapsed" among them, which is the
    right answer for a different reason: two words can be an allegation.

    Twelve is still the wrong unit for CJK, and the mutation run is how that
    surfaced. A Latin letter is a fraction of a morpheme and a CJK character is
    a whole one, so twelve of each are not comparable amounts of meaning:
    "首席执行官因欺诈被起诉" is eleven characters, one token, an entire
    allegation, and it scored below both floors. Four characters is the floor
    for a sentence containing CJK, because four is already a complete clause in
    those scripts.

    The cost is on the other side, and it is real. "Executive summary" is
    seventeen letters and now needs a citation it can never have. That false
    refusal is asserted in the tests rather than argued about here.
    """
    if len(words) >= 3:
        return True
    characters = sum(len(word) for word in words)
    if characters >= 12:
        return True
    return characters >= 4 and bool(_CJK.search("".join(words)))


def is_factual(sentence: str) -> bool:
    """Does this sentence assert something a reader could go and check?

    The default is yes. Everything is treated as a checkable assertion unless
    it matches an explicit exemption, because that is the only shape of this
    function that is actually biased towards refusing.

    The previous version answered yes only for a digit or one of 41 reporting
    verbs, which sounds wide and is not: "Northwind Bank is under investigation
    by the FCA for money laundering failures" contains neither, so it needed no
    citation and was released unsourced. The hole was the entire English
    copula. A whitelist of verbs cannot be a safety default; the exemption list
    below can, because every entry in it is a sentence that asserts nothing
    about the world.

    The exemptions are bounded by length. That is the fix for the second class
    of bypass found against this file: an exemption that recognises a sentence
    by its opening or its tail will exempt anything you staple between them.

    Citation markers are stripped first, otherwise the digit inside `[1]` would
    decide the question for the wrong reason.
    """
    body = strip_citations(sentence).strip()
    if not body:
        return False

    words = _WORD.findall(body)

    # Hedges are exempt at any length. Documented hole, see _HEDGE.
    if _HEDGE.match(body):
        return False

    # A question mark, a prefix and a suffix are all the same kind of exemption:
    # a fragment of the sentence standing in for the whole. So all three carry
    # the same bound. A trailing "?" was unbounded until the third pass over
    # this file, which made a leading question the cheapest laundering route
    # left: "Did Northwind Bank launder two billion dollars through its Cyprus
    # branch and did the board then cover it up?" asserts the whole allegation
    # and was released with no citation and no finding.
    if len(words) <= _EXEMPTION_WORD_LIMIT:
        if _QUESTION.search(body):
            return False
        if _NON_ASSERTION.match(body):
            return False
        if _SELF_REFERENCE.search(body):
            return False

    return _has_claim_weight(words)


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
