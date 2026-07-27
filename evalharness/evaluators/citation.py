"""Citation coverage: does every factual claim carry a resolvable source.

This evaluator is the one the refuse-or-cite gate leans on. It answers exactly
one question per claim, and it answers it per claim rather than per document.
That per claim binding is the difference between this and the naive version in
naive_gate.py.

Three blocking failure modes:

  unsourced_claim      a factual sentence with no citation marker at all
  dangling_citation    a marker such as [3] that no source in the set matches
  unresolvable_source  a marker that resolves to a source stub with no locator
                       or no retrieved content, which a reader cannot check

What it does NOT do: it does not check that the cited source supports the
claim. It checks that a claim is sourced, not that it is true. Support is a
separate, advisory evaluator (support.py) and it is deliberately not wired into
the gate. See README, "Sourcing is not entailment".
"""

from __future__ import annotations

from typing import List

from ..model import EvaluatorResult, Finding, ModelOutput, Severity
from .base import Evaluator

NAME = "citation_coverage"


class CitationCoverageEvaluator(Evaluator):
    name = NAME

    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        findings: List[Finding] = []
        factual = output.factual_claims
        covered = 0

        for claim in factual:
            claim_ok = True

            if not claim.citation_ids:
                claim_ok = False
                findings.append(
                    Finding(
                        evaluator=self.name,
                        code="unsourced_claim",
                        message="Factual claim carries no citation marker.",
                        severity=Severity.BLOCK,
                        claim_index=claim.index,
                    )
                )

            for citation_id in claim.citation_ids:
                source = output.source_by_id(citation_id)
                if source is None:
                    claim_ok = False
                    findings.append(
                        Finding(
                            evaluator=self.name,
                            code="dangling_citation",
                            message=(
                                "Claim cites [{0}] but no such source was supplied.".format(
                                    citation_id
                                )
                            ),
                            severity=Severity.BLOCK,
                            claim_index=claim.index,
                        )
                    )
                elif not source.is_resolvable:
                    claim_ok = False
                    findings.append(
                        Finding(
                            evaluator=self.name,
                            code="unresolvable_source",
                            message=(
                                "Source [{0}] has no locator or no retrieved content, "
                                "so a reader cannot check it.".format(citation_id)
                            ),
                            severity=Severity.BLOCK,
                            claim_index=claim.index,
                        )
                    )

            if claim_ok:
                covered += 1

        # Coverage ratio, not a confidence. An output with no factual claims
        # scores 1.0 because there was nothing to source.
        score = 1.0 if not factual else covered / len(factual)
        return EvaluatorResult(name=self.name, score=score, findings=tuple(findings))
