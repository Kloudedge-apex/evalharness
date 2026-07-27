"""Lexical overlap between a claim and the source it cites. ADVISORY ONLY.

Read this docstring before reading the code, because the honest description of
this evaluator is more useful than the evaluator.

This is not entailment. It cannot tell you whether the source supports the
claim. All it computes is the share of the claim's content words that also
appear in the cited snippet. A claim can score 1.0 against a snippet that
contradicts it, and a correctly supported claim can score near 0.0 because it
paraphrases.

It exists for one reason: to surface the "cited something, but not this"
failure, where a model attaches a real marker to an unrelated retrieved
document. It flags that case as ADVISORY so a human can look. It never blocks,
because a lexical heuristic is nowhere near good enough to refuse an output on.

Doing this properly means an entailment model, which means an inference call,
which this repo does not have (no network in the default path).
"""

from __future__ import annotations

import re
from typing import List, Set

from ..model import EvaluatorResult, Finding, ModelOutput, Severity
from ..segment import strip_citations
from .base import Evaluator

NAME = "support_overlap"

# Overlap below this share of content words gets an advisory flag. The number
# is a judgement call tuned against the fixtures in this repo and nothing else.
OVERLAP_THRESHOLD = 0.34

_WORD = re.compile(r"[A-Za-z0-9$%.,'-]+")

_STOPWORDS = frozenset(
    """a an the and or but if then than that this these those of in on at to for from by with
    was were is are be been being it its as into about over under after before during more most
    very will would can could should may might have has had do does did not no so such own same
    """.split()
)


def _content_words(text: str) -> Set[str]:
    words = {w.strip(".,'-").lower() for w in _WORD.findall(text)}
    return {w for w in words if w and w not in _STOPWORDS and len(w) > 2}


class SupportOverlapEvaluator(Evaluator):
    name = NAME

    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        findings: List[Finding] = []
        scored: List[float] = []

        for claim in output.factual_claims:
            claim_words = _content_words(strip_citations(claim.text))
            if not claim_words:
                continue
            best = 0.0
            checked = False
            for citation_id in claim.citation_ids:
                source = output.source_by_id(citation_id)
                if source is None or not source.snippet.strip():
                    continue
                checked = True
                snippet_words = _content_words(source.snippet)
                overlap = len(claim_words & snippet_words) / len(claim_words)
                best = max(best, overlap)
            if not checked:
                continue
            scored.append(best)
            if best < OVERLAP_THRESHOLD:
                findings.append(
                    Finding(
                        evaluator=self.name,
                        code="low_lexical_overlap",
                        message=(
                            "Claim shares {0:.0%} of its content words with the source it "
                            "cites. This is a weak signal, not a support judgement.".format(best)
                        ),
                        severity=Severity.ADVISORY,
                        claim_index=claim.index,
                    )
                )

        score = 1.0 if not scored else sum(scored) / len(scored)
        return EvaluatorResult(name=self.name, score=score, findings=tuple(findings))
