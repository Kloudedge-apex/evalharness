"""Mutation check: break the code on purpose, prove a named test notices.

A green test suite written by the author of the code proves the code does what
the author told it to check. It does not prove the checks are worth anything. A
test that asserts nothing, or asserts the wrong thing, is green forever.

So this script does the only cheap thing that distinguishes the two. It takes
each safety property this repository claims, reintroduces the bug that would
break it, and requires that a specific named test goes red. A mutant nothing
catches is a property nobody is actually testing, and the run exits non zero.

Every mutant below is a bug that was really in this code at some point. Seven of
them were the shipped behaviour until 2026-07-27.

    python3 mutations/run.py            # run them all
    python3 mutations/run.py -v         # print the failing test names

Takes about fifteen seconds: one full suite run per mutant, in a throwaway copy
of the tree. The working tree is never modified.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, NamedTuple, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
IGNORED = shutil.ignore_patterns("__pycache__", ".git", ".venv", ".pytest_cache", "mutations")


class Mutant(NamedTuple):
    id: str
    property_broken: str
    path: str
    old: str
    new: str
    caught_by: Tuple[str, ...]


MUTANTS: Tuple[Mutant, ...] = (
    Mutant(
        id="citation_document_scope",
        property_broken="Citations are bound to the claim they sit in, not to the document.",
        path="evalharness/evaluators/citation.py",
        old="            if not claim.citation_ids:",
        new="            if not any(c.citation_ids for c in factual):",
        caught_by=("test_one_citation_does_not_cover_the_claims_beside_it",),
    ),
    Mutant(
        id="evaluator_error_skipped",
        property_broken="An evaluator that raises blocks. It does not get skipped.",
        path="evalharness/gate.py",
        old='                result = _error_result(getattr(evaluator, "name", "unknown"), exc)',
        new="                continue",
        caught_by=("test_an_evaluator_that_raises_causes_a_refusal_not_a_skip",),
    ),
    Mutant(
        id="partial_gate_constructible",
        property_broken="A gate missing a blocking evaluator cannot be built by accident.",
        path="evalharness/gate.py",
        old="        if not allow_partial:",
        new="        if False:",
        caught_by=(
            "test_a_gate_with_no_evaluators_cannot_be_built",
            "test_dropping_one_blocking_evaluator_is_also_refused",
        ),
    ),
    Mutant(
        id="no_hard_break_split",
        property_broken="A newline or a bullet ends a claim.",
        path="evalharness/segment.py",
        old="    for block in _HARD_BREAK.split(text):",
        new="    for block in [text]:",
        caught_by=(
            "test_a_bullet_list_does_not_launder_three_uncited_claims",
            "test_every_list_marker_style_is_a_claim_boundary",
        ),
    ),
    Mutant(
        id="no_clause_split",
        property_broken="A citation does not extend across 'and' into a second assertion.",
        path="evalharness/segment.py",
        old="            for clause in _CLAUSE_BREAK.split(sentence):",
        new="            for clause in [sentence]:",
        caught_by=("test_a_comma_and_a_conjunction_do_not_extend_a_citation",),
    ),
    Mutant(
        id="abbreviation_swallows_next_sentence",
        property_broken="An abbreviation does not merge the sentence after it into itself.",
        path="evalharness/segment.py",
        old="            if not _starts_new_sentence(text, end, allow_digit=allow_digit):\n"
        "                continue",
        new="            continue",
        caught_by=("test_an_abbreviation_does_not_swallow_the_sentence_after_it",),
    ),
    Mutant(
        id="classifier_needs_a_digit",
        property_broken="A claim with no digit in it still needs a source.",
        path="evalharness/segment.py",
        old="    return _has_claim_weight(words)",
        new='    return bool(re.search(r"\\d", body)) and _has_claim_weight(words)',
        caught_by=(
            "test_serious_allegations_without_digits_or_reporting_verbs_still_need_a_source",
        ),
    ),
    Mutant(
        id="classifier_exempts_everything",
        property_broken="The exemption list is anchored. An exempt word mid-sentence is not exempt.",
        path="evalharness/segment.py",
        old="        if _NON_ASSERTION.match(body):\n            return False",
        new="        if re.search(\n"
        '            _NON_ASSERTION.pattern.replace("^", "", 1), body, _NON_ASSERTION.flags\n'
        "        ):\n            return False",
        caught_by=("test_the_exemption_list_only_matches_at_the_start_of_a_sentence",),
    ),
    Mutant(
        id="luhn_check_removed",
        property_broken="A long digit run is not reported as a card unless it checksums.",
        path="evalharness/evaluators/pii.py",
        old="                    if needs_luhn and not luhn_valid(match.group(0)):",
        new="                    if False and not luhn_valid(match.group(0)):",
        caught_by=(
            "test_card_candidates_are_luhn_checked_before_being_reported",
            "test_does_not_fire_on_ordinary_numbers",
        ),
    ),
    Mutant(
        id="pii_ascii_separators_only",
        property_broken="A card number with typographic or invisible separators is still a card number.",
        path="evalharness/evaluators/pii.py",
        old='_SEP = r"[\\s.\\u2010-\\u2015\\u200b-\\u200d\\u2060\\ufeff-]"',
        new='_SEP = r"[ .-]"',
        caught_by=(
            "test_typographic_separators_do_not_hide_a_card_number",
            "test_an_invisible_separator_does_not_hide_a_card_number",
        ),
    ),
    Mutant(
        id="pii_scans_response_only",
        property_broken="Retrieved sources are scanned for leaks, not just the response.",
        path="evalharness/evaluators/base.py",
        old='    for source in output.sources:\n'
        '        location = "source:{0}".format(source.id)\n'
        '        targets.append((location, "title", source.title))\n'
        '        targets.append((location, "url", source.url))\n'
        '        targets.append((location, "snippet", source.snippet))',
        new="    return targets",
        caught_by=("test_a_leak_inside_a_retrieved_source_is_found_too",),
    ),
    Mutant(
        id="evaluators_read_the_snippet_only",
        property_broken="A source is its title and its url too, not only its snippet.",
        path="evalharness/evaluators/base.py",
        old='        targets.append((location, "title", source.title))\n'
        '        targets.append((location, "url", source.url))\n',
        new="",
        caught_by=(
            "test_pii_in_a_source_title_and_url_is_found",
            "test_an_injection_in_a_source_title_is_found",
        ),
    ),
    Mutant(
        id="finding_dedup_ignores_the_field",
        property_broken="Two fields of one source that leak at the same offset are two findings.",
        path="evalharness/evaluators/pii.py",
        old="                    key = (location, field, code, match.start())",
        new="                    key = (location, code, match.start())",
        caught_by=("test_two_fields_of_one_source_do_not_collapse_into_one_finding",),
    ),
    Mutant(
        id="injection_bare_keyword_scan",
        property_broken="Injection detection requires the imperative shape, not a word.",
        path="evalharness/evaluators/injection.py",
        old='            r"\\b(?:ignore|disregard|forget|discard|override)\\s+" + _DETERMINER + r"(?:"\n            # With a pointer back at the conversation, any object will do.\n            r"(?:previous|prior|above|earlier|preceding|foregoing|system|original|initial)\\s+"\n            r"(?:instructions?|prompts?|rules?|directions?|directives?|guidance|guidelines?)"\n            # Without one, the object has to be unambiguously conversational.\n            # "Ignore the rules" is a sentence about a card game or a building\n            # site; "ignore the instructions" is borderline and included,\n            # because on a retrieved source the fail-closed direction is to\n            # block. That trade is stated in the README limitations.\n            r"|(?:instructions?|prompts?|directives?)"\n            r")\\b",',
        new='            r"\\b(?:ignore|disregard|forget|discard|override)\\b",',
        caught_by=("test_does_not_fire_on_ordinary_prose",),
    ),
    Mutant(
        id="injection_determiner_is_a_fixed_list",
        property_broken="One word of paraphrase does not defeat the injection list.",
        path="evalharness/evaluators/injection.py",
        old='_DETERMINER = r"(?:all\\s+of\\s+the\\s+|all\\s+of\\s+|all\\s+|any\\s+|the\\s+|your\\s+|my\\s+|our\\s+|these\\s+|those\\s+|every\\s+)*"',
        new='_DETERMINER = r"(?:all\\s+|any\\s+|the\\s+)*"',
        caught_by=("test_one_word_of_paraphrase_does_not_defeat_the_injection_list",),
    ),
    Mutant(
        id="secret_check_knows_stripe_only",
        property_broken="The secret check knows more than one vendor prefix.",
        path="evalharness/evaluators/pii.py",
        old='API_KEY = re.compile(\n    r"\\b(?:"\n    r"(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}"      # Stripe and lookalikes\n    r"|sk-(?:proj-|ant-|or-)?[A-Za-z0-9_-]{16,}"        # OpenAI, Anthropic, OpenRouter\n    r"|gh[pousr]_[A-Za-z0-9]{16,}"                      # GitHub personal/OAuth/app tokens\n    r"|github_pat_[A-Za-z0-9_]{20,}"\n    r"|AIza[0-9A-Za-z_-]{16,}"                          # Google API key\n    r"|xox[baprs]-[A-Za-z0-9-]{10,}"                    # Slack\n    r"|glpat-[A-Za-z0-9_-]{16,}"                        # GitLab\n    r"|(?:ey[A-Za-z0-9_-]{8,}\\.){2}[A-Za-z0-9_-]{8,}"   # JWT\n    r")\\b"\n)\n',
        new='API_KEY = re.compile(r"\\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\\b")\n',
        caught_by=("test_the_secret_check_knows_more_than_one_vendor",),
    ),
    Mutant(
        id="exemptions_are_unbounded",
        property_broken="An exemption applies only to a sentence short enough to be the line it describes.",
        path="evalharness/segment.py",
        old="    if len(words) <= _EXEMPTION_WORD_LIMIT:",
        new="    if True:",
        caught_by=(
            "test_an_opener_cannot_launder_the_allegation_behind_it",
            "test_a_tail_cannot_launder_the_allegation_in_front_of_it",
        ),
    ),
    Mutant(
        id="ascii_hard_breaks_only",
        property_broken="Every character str.splitlines() calls a line break ends a claim.",
        path="evalharness/segment.py",
        old='_HARD_BREAK = re.compile(r"[\\n\\r\\v\\f\\x1c\\x1d\\x1e\\x85\\u2028\\u2029]+")',
        new='_HARD_BREAK = re.compile(r"[\\n]+")',
        caught_by=("test_every_character_python_calls_a_line_break_is_a_claim_boundary",),
    ),
    Mutant(
        id="ascii_terminators_only",
        property_broken="An ideographic full stop ends a claim, same as a period.",
        path="evalharness/segment.py",
        old='_TERMINATOR = re.compile(r"[.!?。！？؟۔।॥…]+")',
        new='_TERMINATOR = re.compile(r"[.!?]+")',
        caught_by=("test_an_ideographic_full_stop_ends_a_claim",),
    ),
    Mutant(
        id="cjk_claim_weight_floor",
        property_broken="A claim-weight floor counted in Latin letters is the wrong unit for CJK.",
        path="evalharness/segment.py",
        old='    return characters >= 4 and bool(_CJK.search("".join(words)))',
        new="    return False",
        caught_by=("test_an_ideographic_full_stop_ends_a_claim",),
    ),
    Mutant(
        id="boundary_requires_whitespace",
        property_broken="A full stop with no space after it still ends the sentence.",
        path="evalharness/segment.py",
        old="    return following.isdigit() or following.islower()",
        new="    return True",
        caught_by=("test_a_missing_space_after_a_full_stop_still_ends_the_sentence",),
    ),
)

_FAILED = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)


def run_suite(directory: Path) -> Tuple[int, List[str], str]:
    """Run the whole suite in `directory` and return (exit code, failed ids, tail)."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=no",
            "-rf",
            "-p",
            "no:cacheprovider",
        ],
        cwd=str(directory),
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    failed = [match.group(1) for match in _FAILED.finditer(output)]
    tail = output.strip().splitlines()[-1] if output.strip() else ""
    return completed.returncode, failed, tail


def apply_mutation(directory: Path, mutant: Mutant) -> None:
    target = directory / mutant.path
    source = target.read_text(encoding="utf-8")
    occurrences = source.count(mutant.old)
    if occurrences != 1:
        raise SystemExit(
            "mutant {0}: expected exactly one occurrence of its target in {1}, found {2}. "
            "The code moved and this mutant is now testing nothing.".format(
                mutant.id, mutant.path, occurrences
            )
        )
    target.write_text(source.replace(mutant.old, mutant.new), encoding="utf-8")


def caught(failed: Sequence[str], names: Sequence[str]) -> List[str]:
    """Which of `names` appear among the failing node ids."""
    joined = "\n".join(failed)
    return [name for name in names if name in joined]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="list failing tests")
    parser.add_argument("--only", help="run a single mutant by id")
    args = parser.parse_args()

    mutants = MUTANTS
    if args.only:
        mutants = tuple(m for m in MUTANTS if m.id == args.only)
        if not mutants:
            raise SystemExit("no mutant with id {0!r}".format(args.only))

    with tempfile.TemporaryDirectory(prefix="evalharness-baseline-") as tmp:
        baseline_dir = Path(tmp) / "artifact"
        shutil.copytree(ROOT, baseline_dir, ignore=IGNORED)
        code, failed, tail = run_suite(baseline_dir)
    if code != 0:
        print("baseline is not green ({0}). Fix that before mutating.".format(tail))
        return 2
    print("baseline: {0}".format(tail))
    print("")

    survivors: List[Mutant] = []
    for mutant in mutants:
        with tempfile.TemporaryDirectory(prefix="evalharness-mutant-") as tmp:
            work = Path(tmp) / "artifact"
            shutil.copytree(ROOT, work, ignore=IGNORED)
            apply_mutation(work, mutant)
            _, failed, _ = run_suite(work)

        hits = caught(failed, mutant.caught_by)
        status = "killed " if hits else "SURVIVED"
        print("{0}  {1:<34}  {2:>3} failing  {3}".format(status, mutant.id, len(failed), mutant.property_broken))
        if args.verbose:
            for name in failed:
                print("             {0}".format(name))
        if not hits:
            survivors.append(mutant)

    print("")
    if survivors:
        print("{0} of {1} mutants survived:".format(len(survivors), len(mutants)))
        for mutant in survivors:
            print("  {0}: no test named {1} failed".format(mutant.id, " or ".join(mutant.caught_by)))
        print("A surviving mutant means the property above is not actually tested.")
        return 1

    print("all {0} mutants killed by the test named for them".format(len(mutants)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
