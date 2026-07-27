"""The refuse-or-cite gate. Fails closed.

The rule the gate enforces:

    An output may be released only if every factual claim in it carries a
    citation that resolves to a source a reader can check, and no blocking
    evaluator objected. Otherwise the output is refused and withheld.

Refused means withheld. There is no third outcome. `Decision` has exactly two
members and there is a test asserting that, because the usual way a gate like
this dies is that someone adds a "soften and send anyway" path for the case
where refusing is inconvenient, and after that the gate is decoration.

Failing closed, concretely:

  * an evaluator that raises produces a blocking finding, not a skipped check
  * an unexpected error anywhere in `decide` produces a refusal
  * a response that produced no parseable claims but is not empty is refused,
    because "I could not check it" is not "it is fine"
  * an empty or whitespace only response is refused

The last one is arguable. An empty string is harmless to release. It is refused
because in the system this is distilled from, an empty response at that point in
the pipeline meant something upstream had failed, and shipping it silently is
how you find out three days later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from .evaluators import Evaluator, default_evaluators
from .model import EvaluatorResult, Finding, ModelOutput, Severity

REFUSAL_TEMPLATE = (
    "I cannot provide this answer. The draft did not pass the citation gate "
    "({reasons}). Nothing has been released."
)


class Decision(str, Enum):
    """Exactly two outcomes. Do not add a third."""

    ALLOW = "allow"
    REFUSE = "refuse"


@dataclass(frozen=True)
class GateResult:
    output_id: str
    decision: Decision
    reasons: Tuple[str, ...]
    results: Tuple[EvaluatorResult, ...]

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def blocking_findings(self) -> Tuple[Finding, ...]:
        return tuple(f for result in self.results for f in result.blocking_findings)

    @property
    def advisory_findings(self) -> Tuple[Finding, ...]:
        return tuple(
            f
            for result in self.results
            for f in result.findings
            if f.severity is Severity.ADVISORY
        )

    def result_for(self, name: str) -> Optional[EvaluatorResult]:
        for result in self.results:
            if result.name == name:
                return result
        return None

    @property
    def refusal_text(self) -> str:
        return REFUSAL_TEMPLATE.format(reasons=", ".join(self.reasons) or "unspecified")


def _error_result(name: str, exc: BaseException) -> EvaluatorResult:
    return EvaluatorResult(
        name=name,
        score=0.0,
        findings=(
            Finding(
                evaluator=name,
                code="evaluator_error",
                message="Evaluator raised {0}: {1}".format(type(exc).__name__, exc),
                severity=Severity.BLOCK,
            ),
        ),
    )


class RefuseOrCiteGate:
    def __init__(self, evaluators: Optional[Sequence[Evaluator]] = None) -> None:
        self.evaluators: Tuple[Evaluator, ...] = tuple(
            default_evaluators() if evaluators is None else evaluators
        )

    def decide(self, output: Optional[ModelOutput]) -> GateResult:
        try:
            return self._decide(output)
        except BaseException as exc:  # noqa: BLE001 - deliberate catch all
            # If the gate itself is broken we refuse. The alternative is an
            # exception propagating into a caller that treats it as "no
            # objection raised".
            output_id = getattr(output, "id", "unknown")
            return GateResult(
                output_id=output_id,
                decision=Decision.REFUSE,
                reasons=("gate_error",),
                results=(_error_result("gate", exc),),
            )

    def _decide(self, output: Optional[ModelOutput]) -> GateResult:
        if output is None:
            return GateResult("unknown", Decision.REFUSE, ("no_output",), ())

        if not output.response.strip():
            return GateResult(output.id, Decision.REFUSE, ("empty_response",), ())

        if not output.claims:
            return GateResult(output.id, Decision.REFUSE, ("unparseable_response",), ())

        results = []
        for evaluator in self.evaluators:
            try:
                result = evaluator.evaluate(output)
            except BaseException as exc:  # noqa: BLE001 - deliberate catch all
                result = _error_result(getattr(evaluator, "name", "unknown"), exc)
            results.append(result)

        reasons = []
        for result in results:
            for finding in result.blocking_findings:
                if finding.code not in reasons:
                    reasons.append(finding.code)

        decision = Decision.REFUSE if reasons else Decision.ALLOW
        return GateResult(output.id, decision, tuple(reasons), tuple(results))

    def release(self, output: Optional[ModelOutput]) -> Tuple[GateResult, str]:
        """Run the gate and return what the caller is allowed to show a user.

        This is the boundary that makes "fails closed" real rather than
        advisory: on a refusal the caller gets the refusal string, and the
        model's text is not returned at all.
        """
        result = self.decide(output)
        if result.allowed and output is not None:
            return result, output.response
        return result, result.refusal_text
