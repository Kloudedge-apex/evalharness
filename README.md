# evalharness

A small refuse-or-cite evaluation harness for LLM output. Standard library and
pytest, no API keys, no network calls, runs in under a second.

The rule it enforces:

> An output may be released only if every sentence the segmenter identified as a
> factual claim carries a citation that resolves to a source a reader can check,
> and no blocking evaluator objected. Otherwise the output is refused and
> withheld. There is no third outcome.

That sentence is deliberately clumsy. "Every factual claim" is the sentence you
want to write and it is a claim about English, which this repository cannot
make. What it can enforce is a claim about its own segmenter, and the whole
gate is only as good as that qualifier. `segment.py` is therefore the file to
attack first, and the [Limitations](#limitations) say what happened when
somebody did.

## Run it

Needs Python 3 and pytest, nothing else.

```bash
python3 -m venv .venv && .venv/bin/pip install pytest   # or use your own pytest
.venv/bin/python -m pytest -q                            # the test suite
.venv/bin/python -m evalharness                          # the scorecard
```

If pytest is already on your machine, `python3 -m pytest -q` and
`python3 -m evalharness` from this directory are enough.

Developed and run on CPython 3.12. It uses only the standard library and should
work on 3.9 and later, but 3.12 is the only version I have run it on.

The scorecard prints a per evaluator table over the fixture set and exits non
zero if any gate decision disagrees with the label on its fixture, so it is a
check rather than a report. Other entry points:

```bash
python3 -m evalharness --json
python3 -m evalharness --fixture adv_one_citation_covers_all
python3 mutations/run.py     # break the code on purpose, prove a test notices
```

`mutations/run.py` takes about fifteen seconds and never touches the working
tree. See [what a green suite proves](#a-note-on-what-a-green-suite-proves).

## What this is

One layer of a system I built at my own company, rewritten from scratch and
small enough to read in a sitting: the evaluation and refusal layer that sat in
front of model output. The fixtures are synthetic and written for this
repository.

It exists because "I built an evaluator harness that runs on every LLM call" is
a sentence, and a sentence is not evidence. This is the same idea in a form you
can clone and run in under a second, and then try to break.

The interesting content is not the gate. It is the record of the gate being
wrong: `naive_gate.py`, the seven ways an adversarial reviewer got past it on
2026-07-27, the twelve mutants, and the paragraph below admitting the
deliberately wrong implementation once beat the real one.

## What this is not

- Not production code. It is a few hundred lines with no persistence, no
  concurrency, no queue, no observability, and no deployment story.
- Not extracted from any employer, customer or company codebase. No customer
  data and no proprietary logic. Every company, person, address, key and number
  in the fixtures is invented. The card number is the public test value.
- Not a benchmark. It is 22 fixtures that I wrote and labelled myself, so it
  measures agreement with my own judgement and nothing more.
- Not a quality evaluator. It makes no model calls, so it cannot assess whether
  an answer is good, only whether it is structurally allowed to be released.

## The part worth reading first

`evalharness/naive_gate.py` is a deliberately wrong implementation, kept in the
repository next to the real one. It is a keyword-anywhere scan: if anything that
looks like a citation appears anywhere in the response, the whole output passes.

I shipped that shape of bug in a real gate once. It was not caught by reading
the diff. It was caught by someone reproducing the bypass, which is why the
bypass lives here as executable code rather than as a lesson in a document.

Then it happened again, in this repository, to this paragraph. An adversarial
reviewer ran `naive_gate` and the real gate over prose containing no citation
markers at all: **the naive gate refused it and the real gate released it.** The
deliberately wrong implementation, shipped here as a cautionary exhibit, was
stricter than the fix on that input. The test suite was green throughout,
because no test had ever compared the two on an input where the real gate could
lose. It is pinned now, by name, in
`test_the_naive_gate_was_stricter_than_the_real_one_on_that_input`.

`tests/test_naive_vs_real.py` runs both implementations over the same inputs and
asserts that the naive one says yes and the real one refuses. Two failure modes
are separated there:

- **Document scope versus claim scope.** In `adv_one_citation_covers_all` there
  are four factual claims and one citation. The naive check sees a citation and
  passes all four. The real gate binds the check to each claim and objects three
  times.
- **Substring scope versus token scope.** In `adv_citation_keywords_in_prose`
  the words "source", "according to" and "http" appear in ordinary prose and
  there are no citations at all. The naive check reads those strings as
  evidence. This is the exact failure I hit in real life: one unrelated word
  satisfying a check it should not have.

The smallest version of the same bug: `naive_allows()` looks for the string
"source", and the word "outsourced" contains it. So "The reconciliation work was
outsourced to a vendor last quarter" satisfies a citation check while citing
nothing, on a topic with nothing to do with sourcing.
`test_a_substring_scan_reads_outsourced_as_a_citation` holds that. There is no
fix for it inside the naive design, which is the point: the bug is the question
it asks, not the list it asks it against.

And it runs in the other direction. A detector that fires on the word "ignore"
would flag "we cannot ignore the previous quarter's results", a support engineer
would see nonsense in the queue, and the detector would be muted within a week.
`benign_ignore_word_in_prose` is that sentence, shipped as a fixture. (It is
labelled `known_limitation` rather than `benign`, and refuses, for an unrelated
reason: a second sentence in it makes a checkable claim with no citation. The
injection evaluator stays quiet on it, which is what the fixture is for.)

## Evaluators

| evaluator | tier | what it answers |
| --- | --- | --- |
| `citation_coverage` | blocking | Does every factual claim carry a marker that resolves to a source with a locator and retrieved content? |
| `pii` | blocking | Does the response, or any retrieved source, contain an email, phone number, SSN, Luhn valid card number or API key? |
| `prompt_injection` | blocking | Does the response, or any retrieved source, contain a known injection phrasing? |
| `support_overlap` | advisory | How much vocabulary does a claim share with the source it cites? |

The blocking set is small on purpose. Every evaluator you make blocking is an
evaluator that can take the product down when it misfires.

`prompt_injection` and `pii` both scan retrieved sources as well as the
response, because indirect injection (a hostile instruction inside a document
the retriever pulled in) is the case that reaches tools and data, and a leak
that arrives through retrieval is still a leak. A harness that only scans what
the model said scores `adv_injection_in_retrieved_source` and
`adv_pii_in_retrieved_source` as clean.

`pii` only started scanning sources on 2026-07-27. It is worth noticing that
`prompt_injection` had the right scope from the first commit and `pii` did not,
in the same repository, written by the same person on the same day. Getting the
principle right once does not propagate it.

## Sourcing is not entailment

The gate checks that a claim is **sourced**. It does not check that the source
**supports** the claim. Those are different properties and only the first one is
enforced here.

`adv_unrelated_source_cited` is a funding claim cited to a document about an
office lease. The gate allows it. The advisory overlap check flags it for a
human, and the advisory tier never refuses. Doing this properly needs an
entailment model, which means an inference call, which this repository does not
make. `tests/test_support_overlap.py` includes a case where a snippet
contradicts the claim word for word and still scores as high overlap, so the
limit is asserted rather than described.

## Failing closed

Failing closed is the whole point, so it is tested as its own file
(`tests/test_gate_fail_closed.py`):

- an evaluator that raises produces a blocking finding, not a skipped check
- an unexpected error anywhere in the gate produces a refusal
- a response that produced no parseable claims is refused, because "I could not
  check it" is not "it is fine"
- an empty or whitespace only response is refused
- `Decision` has exactly two members, and a test asserts it. That assertion
  looks petty and is not. The usual way a gate like this dies is that somebody
  adds a middle outcome for the case where refusing is inconvenient.
- a refusal withholds the text. `gate.release()` returns the refusal string and
  not the model's words, so the failure is closed at the boundary rather than in
  a log line.
- a gate missing any blocking evaluator cannot be constructed. This one was
  added late and it is the most embarrassing entry on the list, because
  `RefuseOrCiteGate(evaluators=[])` used to build a gate that ran zero checks,
  collected zero objections and returned ALLOW for everything, including a
  response containing a live looking API key. An object whose entire claim is
  "fails closed" was one keyword argument away from failing open. Tests that
  genuinely need a partial gate now pass `allow_partial=True` and say why at the
  call site.

Four false refusals are shipped as labelled fixtures rather than quietly
patched. `limitation_speech_act_over_refusal` refuses "Either way I will send
the summary tomorrow". `benign_sourced_brief` refuses on a trailing
characterisation in an otherwise well sourced brief. Fixtures 03 and 04 were
labelled `benign` until 2026-07-27 and were not: each contains a genuine uncited
factual claim that the old classifier had been releasing, which is a more
useful thing to record than a clean scorecard. All four are the direct cost of
defaulting to "this needs a source", all four carry the reason in the fixture
file, and tuning them away would improve the numbers and mean less.

## What the numbers are

Every number the scorecard prints is a count or a ratio computed by ordinary
Python. `citation_coverage` reports covered claims over factual claims. `pii`
and `prompt_injection` are binary, because one leak is a failure. None of them
is a model graded score, a confidence, or a learned quantity.

My CV refers to a hallucination score moving from 0.5 to 0.95. That number came
from the production system at my own company, measured by LLM judged evaluators
against real traffic across several deploys. **This repository did not produce
that number and cannot produce it.** Nothing here calls a model. If you want to
interrogate that claim, the thing to interrogate is the production system, not
this repository. What this repository shows is the shape of the deterministic
layer and how I think about gating.

## Limitations

1. Sentence splitting is a regex. It splits on hard breaks (newlines, bullets,
   numbered items), then terminal punctuation, then coordinated clauses. It is
   not a parser. **A mis-split here is not cosmetic: it is a gate bypass**,
   because two claims merged into one means the citation on the first covers the
   second. Three such bypasses were found and fixed on 2026-07-27 (fixtures 18
   to 20) and there is no reason to think that is all of them. If you are
   looking for the next one, this is the file.
2. The factual claim classifier defaults to "this needs a citation" and exempts
   an explicit list of non-assertions. It has errors in **both** directions and
   the false negative direction is the dangerous one:
   - **False refusals**, the disclosed and cheap direction. It asks for a source
     on sentences that assert nothing, for example "That surprised nobody".
     `14_limitation_speech_act_over_refusal` and
     `test_known_false_refusals_are_asserted_rather_than_hidden` pin them.
   - **False releases**, the direction that matters. Anything the exemption list
     wrongly matches goes out unsourced. The exemption list is short for exactly
     that reason, and every addition to it widens the hole. An earlier version
     of this classifier inverted the logic (a whitelist of 39 reporting verbs,
     plus digits) and released "Northwind Bank is under investigation by the FCA
     for money laundering failures" with no citation, because that sentence
     contains neither. See fixture 21. **A whitelist cannot be a safety
     default.** That is the single most useful thing in this repository.
3. Injection detection is a phrase list. A paraphrase, a translation or an
   encoded payload walks past it. `tests/test_injection.py` contains a passing
   test that demonstrates a paraphrase defeating it.
4. PII detection is regex over mostly US and UK formats. Names alone are not
   detected at all.
5. Sourcing is not entailment, as above.
6. The fixtures are synthetic and I wrote both the fixtures and the code, so the
   agreement number is not independent evidence.
7. There is no throughput, latency or cost story here. In a real pipeline those
   decide whether a check runs on every call or on a sample.

## A note on what a green suite proves

A test suite the author wrote proves the code does what the author told it to
check. It does not prove the checks are the right ones. I have been burned by
exactly that: a fix of mine passed its own acceptance gate, and an adversarial
re-verification found the fix had recreated the bug it was meant to close.

Three things partly compensate. None of them is as good as a reviewer who wants
you to be wrong.

**1. The labels are separate from the code.** Fixture labels live in JSON, the
runner compares the gate's decision against them, and it exits non zero on
disagreement.

**2. The mutation check is a script, not a paragraph.** `mutations/run.py`
reintroduces twelve bugs, one at a time, into a throwaway copy of the tree, and
requires that a test *named for that property* goes red. A mutant nothing
catches means the property is not actually tested, and the run exits non zero.

```
$ python3 mutations/run.py
baseline: 225 passed in 0.69s

killed   citation_document_scope              23 failing  Citations are bound to the claim they sit in, not to the document.
killed   evaluator_error_skipped               1 failing  An evaluator that raises blocks. It does not get skipped.
killed   partial_gate_constructible            2 failing  A gate missing a blocking evaluator cannot be built by accident.
killed   no_hard_break_split                  13 failing  A newline or a bullet ends a claim.
killed   no_clause_split                       7 failing  A citation does not extend across 'and' into a second assertion.
killed   abbreviation_swallows_next_sentence   7 failing  An abbreviation does not merge the sentence after it into itself.
killed   classifier_needs_a_digit             36 failing  A claim with no digit in it still needs a source.
killed   classifier_exempts_everything         4 failing  The exemption list is anchored. An exempt word mid-sentence is not exempt.
killed   luhn_check_removed                    7 failing  A long digit run is not reported as a card unless it checksums.
killed   pii_ascii_separators_only             4 failing  A card number with typographic dashes is still a card number.
killed   pii_scans_response_only               8 failing  Retrieved sources are scanned for leaks, not just the response.
killed   injection_bare_keyword_scan           6 failing  Injection detection requires the imperative shape, not a word.

all 12 mutants killed by the test named for them
```

Seven of those twelve are not hypotheticals: `partial_gate_constructible`,
`no_hard_break_split`, `no_clause_split`, `abbreviation_swallows_next_sentence`,
`classifier_needs_a_digit`, `pii_ascii_separators_only` and
`pii_scans_response_only` restore the actual shipped behaviour of this
repository as of 2026-07-26. The other five are bugs this code never had and
could plausibly acquire.

Writing the harness immediately earned its keep. The first version of
`classifier_exempts_everything` swapped `.match()` for `.search()`, which I
believed was a real loosening of the claim classifier. It survived: zero tests
failed. The reason is that the pattern carries its own `^`, so the two calls
are equivalent and the mutation was a no-op. I had been about to describe an
anchoring property that no test covered and that my own mutant could not
distinguish. The mutant now strips the anchor, and
`test_the_exemption_list_only_matches_at_the_start_of_a_sentence` exists
because of it.

**3. The adversarial pass happened, and it is in the git history.** On
2026-07-27 a reviewer went at this repository with the specific goal of getting
something past the gate, and got in seven ways:

| what got through | why | pinned as |
| --- | --- | --- |
| four claims as markdown bullets, one citation | the segmenter split on terminal punctuation only, so a response with no full stops was one claim | `18_adv_bullet_list_bypass` |
| "X is true [1], and Y is a crime" | claim scope was the sentence, so a comma and a conjunction extended the citation | `19_adv_compound_clause_bypass` |
| an uncited sentence placed after one ending "Inc." | the abbreviation guard skipped the boundary without advancing the cursor | `20_adv_abbreviation_merge_bypass` |
| "Northwind Bank is under investigation by the FCA" | the classifier was a whitelist of digits and 39 reporting verbs, and this has neither | `21_adv_unsourced_copula_prose` |
| an SSN and a card number inside a retrieved source | the PII evaluator scanned the response only | `22_adv_pii_in_retrieved_source` |
| a card number with en dashes instead of hyphens | the separator class was ASCII | `test_typographic_separators_do_not_hide_a_card_number` |
| a leaked API key through `RefuseOrCiteGate(evaluators=[])` | zero evaluators, zero objections, ALLOW | `test_a_gate_with_no_evaluators_cannot_be_built` |

The suite was green for all seven, and the README of the day asserted the gate
held. What the exercise measured is not the fixes, it is that gap. Every row
above is now a fixture or a named test, and seven of the twelve mutants in
`mutations/run.py` restore one of these bugs to check that the pin holds.

## Layout

```
evalharness/
  model.py             Claim, Citation, Finding, EvaluatorResult, ModelOutput
  segment.py           sentence splitting, citation binding, claim classifier
  gate.py              the refuse-or-cite gate, fails closed
  naive_gate.py        the deliberately wrong version, kept for the test
  scorecard.py         runner, table, JSON, exit code
  __main__.py          CLI
  evaluators/
    citation.py        citation coverage (blocking)
    pii.py             PII and secrets, Luhn checked, redacted output (blocking)
    injection.py       prompt injection, response and sources (blocking)
    support.py         lexical overlap (advisory, not entailment)
fixtures/              22 labelled fixture outputs, synthetic
tests/                 225 tests
mutations/run.py       reintroduces 12 bugs, requires a named test to catch each
```

Read `tests/` as the spec. Every test name is a sentence about behaviour, and
the ones that matter carry a comment explaining why the behaviour is worth
holding onto.
