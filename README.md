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
.venv/bin/python -m evalharness --json
.venv/bin/python -m evalharness --fixture adv_one_citation_covers_all
.venv/bin/python mutations/run.py   # break the code on purpose, prove a test notices
```

`mutations/run.py` takes about thirty seconds and never touches the working
tree. It runs the suite once per mutant, so it needs the interpreter that has
pytest installed, which is why it is written `.venv/bin/python` here. See
[what a green suite proves](#a-note-on-what-a-green-suite-proves).

## What this is

One layer of a system I built at my own company, rewritten from scratch and
small enough to read in a sitting: the evaluation and refusal layer that sat in
front of model output. The fixtures are synthetic and written for this
repository.

It exists because "I built an evaluator harness that runs on every LLM call" is
a sentence, and a sentence is not evidence. This is the same idea in a form you
can clone and run in under a second, and then try to break.

The interesting content is not the gate. It is the record of the gate being
wrong: `naive_gate.py`, the two adversarial passes that got past it seven and
then eleven ways, the twenty-one mutants, and the paragraph below admitting the
deliberately wrong implementation once beat the real one.

## What this is not

- Not production code. It is about 1,700 lines of library and about the same
  again of tests, with no persistence, no concurrency, no queue, no
  observability, and no deployment story.
- Not extracted from any employer, customer or company codebase. No customer
  data and no proprietary logic. Every company, person, address, key and number
  in the fixtures is invented. The card number is the public test value.
- Not a benchmark. It is 26 fixtures that I wrote and labelled myself, so it
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

Both of them got that scope wrong, in different ways, and the sequence is the
point. `pii` scanned only the model's own words until 2026-07-27, while
`prompt_injection` had been reading source snippets since the first commit: the
same principle, in the same repository, applied in one file and not the next
one. Then the fix to `pii` copied the shape of `prompt_injection` exactly, which
meant it inherited that file's remaining bug, and both evaluators went on
reading `source.snippet` and ignoring the title and the url. A hostile document
names itself, and an API key in a query string is a leak wherever it sits.

Both now call `evaluators/base.py::scan_targets`, which is one function
returning every field of every source, so the scope is a single decision in a
single place rather than a convention two files are each expected to remember.
Getting the principle right once does not propagate it, and copying the fix
propagates whatever else was wrong with it.

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

Two false refusals are shipped as labelled fixtures rather than quietly patched.
`limitation_speech_act_over_refusal` refuses "Either way I will send the summary
tomorrow", which asserts nothing about the world. `benign_sourced_brief` refuses
on a trailing characterisation in an otherwise well sourced brief. Both are the
direct cost of defaulting to "this needs a source", both carry the reason in the
fixture file, and tuning them away would improve the numbers and mean less.

Two more fixtures carry the `known_limitation` label without being false
refusals, and the distinction matters. Fixtures 03 and 04 were labelled `benign`
until 2026-07-27 and the label was simply wrong: each contains a genuine uncited
factual claim that the old classifier had been releasing, so the refusal is
correct and it was the fixture that needed fixing. They keep their original
filenames so the relabel is visible in `git log` rather than tidied out of it.
The scorecard therefore shows four `known_limitation` rows and only two of them
are things this gate gets wrong.

Two further false refusals live in `tests/test_adversarial_pass_two.py` rather
than in the fixture set, under
`test_two_deliberate_false_refusals_left_in_rather_than_tuned_away`. "Note that
the figures are rounded" is refused because "note" carries a negative lookahead
on "that", and there is no length at which "Note that X" stops asserting X.
"The table below sets this out" is refused because the self-reference exemption
is anchored at the end of the sentence. Unanchoring it is one character of
regex and reopens a bypass. Both are the price of the bound described below.

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
   second. Two adversarial passes on 2026-07-27 found six of them. Three were
   structural (fixtures 18 to 20). Three more turned up only when the second
   reviewer stopped assuming the model writes ASCII English: a full stop with no
   space after it was not a boundary, `\r`, `\v`, `\f`, `\x1c` and U+2028 were
   not hard breaks (fixture 26 pins the first of those and U+2028), and `。` was
   not a terminator (`test_an_ideographic_full_stop_ends_a_claim`). There is no
   reason to think that is all of them. If you are looking for the next one,
   this is still the file.
2. The factual claim classifier defaults to "this needs a citation" and exempts
   an explicit list of non-assertions. It has errors in **both** directions and
   the false negative direction is the dangerous one:
   - **False refusals**, the disclosed and cheap direction. It asks for a source
     on sentences that assert nothing, for example "That surprised nobody".
     `14_limitation_speech_act_over_refusal` and
     `test_known_false_refusals_are_asserted_rather_than_hidden` pin them.
   - **False releases**, the direction that matters. Anything the exemption list
     wrongly matches goes out unsourced. An earlier version of this classifier
     inverted the logic (a whitelist of 41 reporting verbs, plus digits) and
     released "Northwind Bank is under investigation by the FCA for money
     laundering failures" with no citation, because that sentence contains
     neither. See fixture 21. **A whitelist cannot be a safety default.**
   That last line was the headline of this README for one pass, and it was
   incomplete. An exemption list is a whitelist one level down. The attack is
   not "write a sentence the classifier has never heard of", it is "wrap an
   allegation in something the exemption list has heard of", and on 2026-07-27
   that worked in both directions: `Note that <eleven words of allegation>` was
   exempt because of its first word, and `<thirteen words of allegation>, as set
   out below` was exempt because of its last. Fixtures 23 and 24. The fix is not
   a longer list, it is a **bound**: an exemption now applies only to a sentence
   short enough to be the courtesy line the exemption describes
   (`_EXEMPTION_WORD_LIMIT = 12`). An exemption that recognises a sentence by a
   fragment is a wildcard until something limits how much can hide behind the
   fragment.
3. **Hedges are exempt at any length, and that is the largest hole still open.**
   A sentence reporting the speaker's own state of mind is not checkable against
   a source, so `_HEDGE` is deliberately not bounded by the limit in point 2.
   The consequence is that `We believe Northwind Bank laundered two billion
   dollars through its Cyprus branch` is released with no citation and no
   finding. A model that learns to prefix everything with "we believe" defeats
   this gate. Bounding hedges the way the other exemptions are bounded is not
   the fix it looks like, and the numbers say so in both directions: the
   sentence above is exactly twelve words, so the twelve word bound leaves it
   exempt, and "I cannot answer that" is four words, so no bound of that kind
   ever reaches it. The only thing that closes this is dropping the hedge
   exemption outright, which refuses every hedged sentence including the
   refusal itself, and that is the sentence a refusing model most needs to be
   able to say. So the hole is documented rather than papered over.
   `segment.py` carries the same reasoning at `_HEDGE`.
4. The claim weight floor releases very short sentences. A fragment needs three
   word tokens, or twelve letters, or four characters when the sentence contains
   CJK, before it counts as a claim at all. Letters is the operative word:
   `_WORD` matches no digits and no punctuation, so the floor does not see them.
   `Bankrupt.` goes out unsourced, and so does `$2,000,000,000 laundered.`,
   which is twenty-five characters and nine letters.
   `test_the_claim_weight_floor_is_a_hole_and_is_asserted_as_one` asserts that
   as current behaviour. The CJK arm of that condition exists because a Latin
   letter is a fraction of a morpheme and a Chinese character is a whole one, so
   a twelve letter floor is the wrong unit for a language written without
   spaces: `首席执行官因欺诈被起诉` is eleven characters, one word token, and an
   allegation. That hole was found by `mutations/run.py`, not by a reviewer, and
   the story is under [what a green suite proves](#a-note-on-what-a-green-suite-proves).
5. Injection detection is a phrase list. A paraphrase, a translation or an
   encoded payload walks past it. `tests/test_injection.py` contains a passing
   test that demonstrates a paraphrase defeating it.
6. PII detection is regex over a fixed, short list of formats: email addresses,
   Luhn checked card numbers, US social security numbers, US and Canadian phone
   numbers, `+country code` phone numbers, and a list of vendor API key
   prefixes. Only two of those are tied to a jurisdiction: the US social
   security number, and the North American phone format the US shares with
   Canada. There is no UK pattern at all, so a National Insurance number, a sort
   code and a UK domestic mobile all pass through untouched. Names alone are not
   detected either.
7. Sourcing is not entailment, as above.
8. The fixtures are synthetic and I wrote both the fixtures and the code, so the
   agreement number is not independent evidence.
9. There is no throughput, latency or cost story here. In a real pipeline those
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
reintroduces twenty-one bugs, one at a time, into a throwaway copy of the tree,
and requires that a test *named for that property* goes red. A mutant nothing
catches means the property is not actually tested, and the run exits non zero.

```
$ python3 mutations/run.py
baseline: 312 passed in 1.09s

killed   citation_document_scope              48 failing  Citations are bound to the claim they sit in, not to the document.
killed   evaluator_error_skipped               1 failing  An evaluator that raises blocks. It does not get skipped.
killed   partial_gate_constructible            2 failing  A gate missing a blocking evaluator cannot be built by accident.
killed   no_hard_break_split                  21 failing  A newline or a bullet ends a claim.
killed   no_clause_split                      15 failing  A citation does not extend across 'and' into a second assertion.
killed   abbreviation_swallows_next_sentence    8 failing  An abbreviation does not merge the sentence after it into itself.
killed   classifier_needs_a_digit             72 failing  A claim with no digit in it still needs a source.
killed   classifier_exempts_everything         4 failing  The exemption list is anchored. An exempt word mid-sentence is not exempt.
killed   luhn_check_removed                    7 failing  A long digit run is not reported as a card unless it checksums.
killed   pii_ascii_separators_only            10 failing  A card number with typographic or invisible separators is still a card number.
killed   pii_scans_response_only              21 failing  Retrieved sources are scanned for leaks, not just the response.
killed   evaluators_read_the_snippet_only      9 failing  A source is its title and its url too, not only its snippet.
killed   finding_dedup_ignores_the_field       1 failing  Two fields of one source that leak at the same offset are two findings.
killed   injection_bare_keyword_scan           7 failing  Injection detection requires the imperative shape, not a word.
killed   injection_determiner_is_a_fixed_list    3 failing  One word of paraphrase does not defeat the injection list.
killed   secret_check_knows_stripe_only        6 failing  The secret check knows more than one vendor prefix.
killed   exemptions_are_unbounded              8 failing  An exemption applies only to a sentence short enough to be the line it describes.
killed   ascii_hard_breaks_only                7 failing  Every character str.splitlines() calls a line break ends a claim.
killed   ascii_terminators_only                1 failing  An ideographic full stop ends a claim, same as a period.
killed   cjk_claim_weight_floor                1 failing  A claim-weight floor counted in Latin letters is the wrong unit for CJK.
killed   boundary_requires_whitespace          5 failing  A full stop with no space after it still ends the sentence.

all 21 mutants killed by the test named for them
```

Sixteen of those twenty-one are not hypotheticals. Each restores a bypass this
repository actually shipped at some point on 2026-07-27:
`partial_gate_constructible`, `no_hard_break_split`, `no_clause_split`,
`abbreviation_swallows_next_sentence`, `classifier_needs_a_digit`,
`pii_ascii_separators_only` and `pii_scans_response_only` from the first
adversarial pass; `evaluators_read_the_snippet_only`,
`finding_dedup_ignores_the_field`, `injection_determiner_is_a_fixed_list`,
`secret_check_knows_stripe_only`, `exemptions_are_unbounded`,
`ascii_hard_breaks_only` and `boundary_requires_whitespace` from the second; and
`ascii_terminators_only` and `cjk_claim_weight_floor`, which no reviewer found
and the mutation run did. Two of the sixteen restore the bypass rather than the
old code: `classifier_needs_a_digit` is a narrower stand-in for the digits or
verbs whitelist, and `cjk_claim_weight_floor` reaches the same release by a
different route, because the shipped `_WORD` was ASCII only and scored that
sentence at zero tokens rather than one. The other five are bugs this code never
had and could plausibly acquire.

Writing the harness immediately earned its keep. The first version of
`classifier_exempts_everything` swapped `.match()` for `.search()`, which I
believed was a real loosening of the claim classifier. It survived: zero tests
failed. The reason is that the pattern carries its own `^`, so the two calls
are equivalent and the mutation was a no-op. I had been about to describe an
anchoring property that no test covered and that my own mutant could not
distinguish. The mutant now strips the anchor, and
`test_the_exemption_list_only_matches_at_the_start_of_a_sentence` exists
because of it.

**It then earned it again, and that run is the best evidence in this repository
that the check is worth the thirty seconds.** `ascii_terminators_only` reverts
`_TERMINATOR` to `[.!?]`, deleting `。！？؟۔।॥…`. It survived with **zero** tests
failing, even though a test named `test_a_claim_in_a_non_latin_script_is_still_a_claim`
was sitting right there, passing. That test asserts a refusal, and the refusal
comes from the classifier whether the segmenter found one sentence or none, so
it had never touched the terminator at all. It was testing the wrong layer and
looked green doing it.

The replacement, `test_an_ideographic_full_stop_ends_a_claim`, puts a *cited*
Chinese sentence in front of `。` and an *uncited* one after it, so only the
terminator can produce the refusal. It then returned ALLOW, which was a real
bypass rather than a bad test: `首席执行官因欺诈被起诉` is one word token and
eleven characters, under both floors in `_has_claim_weight`, because both floors
were counting Latin letters. Chinese is written without spaces and one character
carries roughly what an English word carries. The fix went into `segment.py`
(`_CJK`, and a four character floor when the token is CJK) rather than into the
test string, and `cjk_claim_weight_floor` pins it. A mutant survived, which
proved a test was measuring the wrong thing, and fixing that test uncovered a
hole in the product nothing else in the repository had found.

**3. The adversarial passes happened, and they are in the git history.** On
2026-07-27 a reviewer went at this repository with the specific goal of getting
something past the gate, and got in seven ways:

| what got through | why | pinned as |
| --- | --- | --- |
| four claims as markdown bullets, one citation | the segmenter split on terminal punctuation only, so a response with no full stops was one claim | `18_adv_bullet_list_bypass` |
| "X is true [1], and Y is a crime" | claim scope was the sentence, so a comma and a conjunction extended the citation | `19_adv_compound_clause_bypass` |
| an uncited sentence placed after one ending "Inc." | the abbreviation guard skipped the boundary without advancing the cursor | `20_adv_abbreviation_merge_bypass` |
| "Northwind Bank is under investigation by the FCA" | the classifier was a whitelist of digits and 41 reporting verbs, and this has neither | `21_adv_unsourced_copula_prose` |
| an SSN and a card number inside a retrieved source | the PII evaluator scanned the response only | `22_adv_pii_in_retrieved_source` |
| a card number with en dashes instead of hyphens | the separator class was ASCII | `test_typographic_separators_do_not_hide_a_card_number` |
| a leaked API key through `RefuseOrCiteGate(evaluators=[])` | zero evaluators, zero objections, ALLOW | `test_a_gate_with_no_evaluators_cannot_be_built` |

The suite was green for all seven, and the README of the day asserted the gate
held. What the exercise measured is not the fixes, it is that gap. Every row
above is now a fixture or a named test, and seven of the twenty-one mutants in
`mutations/run.py` restore one of these bugs to check that the pin holds.

Then a second reviewer read the fixed version, including the sentence above
about how well it now held, and got in eleven more ways. Two of them are the
interesting ones and they are at the top:

| what got through | why | pinned as |
| --- | --- | --- |
| "Note that `<eleven words of allegation>`" | `_NON_ASSERTION` was anchored at the start and unbounded at the end, so matching the single word "Note" exempted any quantity of allegation behind it | `23_adv_exemption_prefix_laundering` |
| "`<thirteen words of allegation>`, as set out below" | `_SELF_REFERENCE` is anchored at the end and was unbounded at the start, so the same trick ran backwards | `24_adv_exemption_suffix_laundering` |
| an SSN, a card number and an API key in a source's title and url | fixture 22 taught the PII evaluator to read sources; it read `source.snippet` and stopped | `25_adv_pii_in_source_title_and_url` |
| "…migration on 2026-02-11 [1].Northwind is laundering money" | the guard that protects decimals and abbreviations skipped every full stop not followed by a space | `26_adv_unicode_boundary_bypass` |
| bullets joined by U+2028, `\r`, `\v`, `\f` or `\x1c` | the hard break class was `\n` alone, while `str.splitlines()` treats ten characters as line breaks | `test_every_character_python_calls_a_line_break_is_a_claim_boundary` |
| a card number separated by non-breaking or zero-width spaces | the separator class had been widened for typographic dashes but not for invisible spaces | `test_an_invisible_separator_does_not_hide_a_card_number` |
| "Ignore **all of the** previous instructions" | the determiner between "ignore" and "instructions" was a fixed alternation of three words (`all`, `any`, `the`) | `test_one_word_of_paraphrase_does_not_defeat_the_injection_list` |
| an injection phrase in a source's title | same scope bug as the PII one, in the file the PII fix was copied from | `test_an_injection_in_a_source_title_is_found` |
| a GitHub, Slack, OpenAI or Google key | the secret check knew Stripe's `sk_live_` family and AWS access key ids, and stopped there | `test_the_secret_check_knows_more_than_one_vendor` |
| two leaks at the same offset in two fields of one source | the finding key was (source id, offset), so the second one deduplicated away | `test_two_fields_of_one_source_do_not_collapse_into_one_finding` |
| an allegation in Chinese | one word token, eleven characters, under both claim weight floors | `cjk_claim_weight_floor`, and see above |

The first pass attacked what the classifier had never heard of. The second
attacked what it had: an exemption list is a whitelist one level down, and the
README's own conclusion from pass one ("a whitelist cannot be a safety default")
applied to the fix that conclusion produced. Both passes are the same finding at
different depths, which is the argument for running the exercise more than once
and for writing down what got in rather than what was repaired.

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
fixtures/              26 labelled fixture outputs, synthetic
tests/                 312 tests
mutations/run.py       reintroduces 21 bugs, requires a named test to catch each
```

Read `tests/` as the spec. Every test name is a sentence about behaviour, and
the ones that matter carry a comment explaining why the behaviour is worth
holding onto.
