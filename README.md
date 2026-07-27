# evalharness

A small refuse-or-cite evaluation harness for LLM output. Standard library and
pytest, no API keys, no network calls, runs in under a second.

The rule it enforces:

> An output may be released only if every factual claim in it carries a citation
> that resolves to a source a reader can check, and no blocking evaluator
> objected. Otherwise the output is refused and withheld. There is no third
> outcome.

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
```

## What this is

A distilled, self contained reimplementation of one layer of a system I built at
my own company: the evaluation and refusal layer that sat in front of model
output. It was written from scratch for this repository, against synthetic
fixtures I wrote for this repository.

It exists because "I built an evaluator harness that runs on every LLM call" is
a sentence, and a sentence is not evidence. This is the same idea in a form you
can clone and run.

## What this is not

- Not production code. It is a few hundred lines with no persistence, no
  concurrency, no queue, no observability, and no deployment story.
- Not extracted from any employer, customer or company codebase. No customer
  data and no proprietary logic. Every company, person, address, key and number
  in the fixtures is invented. The card number is the public test value.
- Not a benchmark. It is 16 fixtures that I wrote and labelled myself, so it
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

The same lesson appears one level down, inside the claim classifier: "led" is a
reporting verb and "ledger" is not, so `is_factual()` tokenises before it
compares. There is a test for that too.

And it runs in the other direction. A detector that fires on the word "ignore"
would flag "we cannot ignore the previous quarter's results", a support engineer
would see nonsense in the queue, and the detector would be muted within a week.
`benign_ignore_word_in_prose` is that sentence, shipped as a fixture.

## Evaluators

| evaluator | tier | what it answers |
| --- | --- | --- |
| `citation_coverage` | blocking | Does every factual claim carry a marker that resolves to a source with a locator and retrieved content? |
| `pii` | blocking | Does the response contain an email, phone number, SSN, Luhn valid card number or API key? |
| `prompt_injection` | blocking | Does the response, or any retrieved source, contain a known injection phrasing? |
| `support_overlap` | advisory | How much vocabulary does a claim share with the source it cites? |

The blocking set is small on purpose. Every evaluator you make blocking is an
evaluator that can take the product down when it misfires.

`prompt_injection` scans retrieved sources as well as the response, because
indirect injection (a hostile instruction inside a document the retriever pulled
in) is the case that reaches tools and data. A harness that only scans what the
model said scores `adv_injection_in_retrieved_source` as clean.

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

`limitation_option_number_over_refusal` is shipped as a labelled fixture rather
than quietly patched: "option 2" contains a digit, the classifier calls it a
factual claim, and the gate refuses a harmless sentence. That is a real false
positive produced by a deliberate tuning choice, and hiding it would make the
scorecard look better and mean less.

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

1. Sentence splitting is a regex with a small abbreviation list. It is not a
   parser and it will mis-split unusual text.
2. The factual claim classifier is a heuristic: a digit or a reporting verb. It
   is biased towards demanding a citation, which produces false refusals like
   `limitation_option_number_over_refusal`. Real deployment would need a numeral
   filter, and would then need to prove the filter cannot be used to smuggle a
   claim through.
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

Two things partly compensate here, and both are weaker than an independent
reviewer would be:

- fixture labels live in JSON, separate from the implementation, and the runner
  fails on disagreement
- I mutation checked the suite by reintroducing bugs and confirming that named
  tests caught them. Reverting the citation check to document scope and making
  evaluator errors skip instead of block failed 12 tests, including
  `test_one_citation_does_not_cover_the_claims_beside_it` and
  `test_an_evaluator_that_raises_causes_a_refusal_not_a_skip`. Removing the Luhn
  guard and replacing injection patterns with a bare keyword scan failed 31,
  including the false positive tests. The mutations were reverted, and the suite
  is green as shipped.

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
fixtures/              16 labelled fixture outputs, synthetic
tests/                 163 tests
```

Read `tests/` as the spec. Every test name is a sentence about behaviour, and
the ones that matter carry a comment explaining why the behaviour is worth
holding onto.
