"""Prompt injection detection over the response and over retrieved sources.

Scope: this scans the model response AND every retrieved source snippet. The
source side matters more. Direct injection is a user typing "ignore your
instructions" into a chat box, which is mostly a nuisance. Indirect injection
is a hostile instruction sitting inside a document your retriever pulled in,
which the model then reads as if it were your own prompt. That is the one that
reaches tools and data.

Method: a list of phrase level regexes. Each pattern requires the imperative
shape, not just the presence of a suspicious word. "Ignore all previous
instructions" matches. "We cannot ignore the previous quarter's results" does
not, and there is a fixture and a test for exactly that sentence, because a
detector that fires on the word "ignore" gets muted within a week and then
protects nothing.

Honest limit: a phrase list catches phrasings on the list. A paraphrase, a
translation, or a base64 blob walks straight past it. Treat this as the cheap
deterministic layer that runs on every call, not as the whole defence.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from ..model import EvaluatorResult, Finding, ModelOutput, Severity
from .base import Evaluator, scan_targets

NAME = "prompt_injection"

# Determiners an injection puts between the verb and its object. The first
# version of the override pattern allowed "all", "any" and "the" and nothing
# else, so "Ignore your previous instructions" and "Ignore these instructions",
# which are closer to the canonical payload than the phrasing that did match,
# both walked past a detector written to catch exactly them. One word of
# paraphrase should not be enough.
_DETERMINER = r"(?:all\s+of\s+the\s+|all\s+of\s+|all\s+|any\s+|the\s+|your\s+|my\s+|our\s+|these\s+|those\s+|every\s+)*"

_PATTERNS: Tuple[Tuple[str, str, "re.Pattern[str]"], ...] = (
    (
        "injection_instruction_override",
        "instruction override",
        re.compile(
            r"\b(?:ignore|disregard|forget|discard|override)\s+" + _DETERMINER + r"(?:"
            # With a pointer back at the conversation, any object will do.
            r"(?:previous|prior|above|earlier|preceding|foregoing|system|original|initial)\s+"
            r"(?:instructions?|prompts?|rules?|directions?|directives?|guidance|guidelines?)"
            # Without one, the object has to be unambiguously conversational.
            # "Ignore the rules" is a sentence about a card game or a building
            # site; "ignore the instructions" is borderline and included,
            # because on a retrieved source the fail-closed direction is to
            # block. That trade is stated in the README limitations.
            r"|(?:instructions?|prompts?|directives?)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "injection_prompt_exfiltration",
        "system prompt exfiltration",
        re.compile(
            r"\b(?:reveal|print|repeat|show|output|dump)\s+(?:me\s+)?(?:your\s+|the\s+)?"
            r"(?:system\s+prompt|initial\s+instructions|hidden\s+instructions|"
            r"internal\s+instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "injection_role_override",
        "role override",
        # Two shapes after "you are now", and the second one is why this is not
        # simply `\w+`. Requiring an article meant "You are now DAN", the most
        # quoted jailbreak string there is, did not match, because a persona
        # name arrives without one. Accepting any word instead makes "You are
        # now able to export the report yourself" an injection, which is how a
        # detector gets muted. So the article-less branch requires an ALL-CAPS
        # token, which is what persona names look like and what ordinary
        # sentence continuations do not. `(?-i:...)` keeps that branch
        # case-sensitive inside an otherwise case-insensitive pattern.
        re.compile(
            r"\byou(?:\s+are|'re|\s+will\s+be)\s+now\s+"
            r"(?:(?:an?|the)\s+\w+|(?-i:[A-Z]{2,})\b)"
            r"|\bfrom\s+now\s+on,?\s+you(?:\s+are|'re)\s+"
            r"(?:(?:an?|the)\s+\w+|(?-i:[A-Z]{2,})\b)"
            r"|\b(?:act|behave|respond|speak)\s+as\s+(?:a\s+|an\s+)?"
            r"(?:unrestricted|jailbroken|uncensored|developer\s+mode|dan)\b"
            r"|\bpretend\s+(?:that\s+)?you(?:\s+are|'re)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "injection_guardrail_bypass",
        "guardrail bypass",
        # The object has to be a named control, not just the word "safety".
        # "Do not skip the safety briefing on site" is a sentence people write,
        # and a detector that flags it is a detector that gets muted.
        re.compile(
            r"\b(?:disable|bypass|turn\s+off|switch\s+off|skip|ignore)\s+"
            r"(?:your\s+|the\s+|all\s+|any\s+)?"
            r"(?:safety\s+(?:checks?|filters?|rules?)|guardrails?|content\s+polic(?:y|ies)|"
            r"content\s+filters?|citation\s+(?:checks?|requirements?|rules?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "injection_tool_hijack",
        "tool or data exfiltration instruction",
        re.compile(
            r"\b(?:send|email|forward|post|upload|transmit)\s+(?:the\s+|all\s+|our\s+)*"
            r"(?:contents?|data|records?|files?|list|database|customers?)\b[^.\n]{0,40}?\bto\b",
            re.IGNORECASE,
        ),
    ),
)


class PromptInjectionEvaluator(Evaluator):
    name = NAME

    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        findings: List[Finding] = []

        # Title and url as well as snippet. A hostile document names itself,
        # and "ignore your previous instructions" in a document title reaches
        # the model exactly the way it does in the body.
        for location, _field, text in scan_targets(output):
            if not text:
                continue
            for code, label, pattern in _PATTERNS:
                match = pattern.search(text)
                if match is None:
                    continue
                findings.append(
                    Finding(
                        evaluator=self.name,
                        code=code,
                        message="Detected {0} in {1}: {2!r}".format(
                            label, location, match.group(0).strip()[:80]
                        ),
                        severity=Severity.BLOCK,
                        location=location,
                    )
                )

        score = 1.0 if not findings else 0.0
        return EvaluatorResult(name=self.name, score=score, findings=tuple(findings))
