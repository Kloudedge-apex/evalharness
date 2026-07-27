"""Core data model for the harness.

Everything downstream (evaluators, gate, scorecard) operates on these types.
They are deliberately small and frozen so that an evaluator cannot mutate the
output it is judging.

Note on scores: every score in this repo is a deterministic count or ratio
computed by ordinary Python. None of them is a model graded or learned score.
See README.md, section "What the numbers are".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple


class Severity(str, Enum):
    """How a finding is treated by the gate.

    BLOCK findings cause a refusal. ADVISORY and INFO findings never do.
    The split is explicit because "advisory" checks that quietly become
    blocking checks are how a gate stops being predictable.
    """

    INFO = "info"
    ADVISORY = "advisory"
    BLOCK = "block"


@dataclass(frozen=True)
class Finding:
    """One thing an evaluator noticed.

    `code` is the stable machine identifier (tests and fixtures assert on it).
    `message` is for humans and may change.
    """

    evaluator: str
    code: str
    message: str
    severity: Severity
    claim_index: Optional[int] = None
    location: str = "response"

    @property
    def is_blocking(self) -> bool:
        return self.severity is Severity.BLOCK


@dataclass(frozen=True)
class EvaluatorResult:
    name: str
    score: float
    findings: Tuple[Finding, ...] = ()

    @property
    def blocking_findings(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.is_blocking)

    @property
    def passed(self) -> bool:
        """An evaluator passes when it produced no blocking finding."""
        return not self.blocking_findings


@dataclass(frozen=True)
class Citation:
    """A source the model claims to have used.

    `id` is the marker used in the response text, so `[1]` binds to id "1".
    """

    id: str
    title: str = ""
    url: str = ""
    published: str = ""
    snippet: str = ""

    @property
    def is_resolvable(self) -> bool:
        """A citation is only worth anything if a human can go and check it.

        That needs two things: somewhere to look (url or title) and something
        that was actually retrieved (snippet). A source stub with neither is
        treated as no source at all.
        """
        has_locator = bool(self.url.strip() or self.title.strip())
        has_content = bool(self.snippet.strip())
        return has_locator and has_content


@dataclass(frozen=True)
class Claim:
    """One sentence of a model response, plus what it cited.

    `is_factual` is a heuristic (see segment.py). It decides whether this
    sentence is required to carry a citation.
    """

    index: int
    text: str
    citation_ids: Tuple[str, ...] = ()
    is_factual: bool = False


@dataclass(frozen=True)
class ModelOutput:
    """A single LLM response, parsed into claims, plus its source set."""

    id: str
    response: str
    sources: Tuple[Citation, ...] = ()
    claims: Tuple[Claim, ...] = ()

    def source_by_id(self, citation_id: str) -> Optional[Citation]:
        for source in self.sources:
            if source.id == citation_id:
                return source
        return None

    @property
    def factual_claims(self) -> Tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.is_factual)


@dataclass(frozen=True)
class Fixture:
    """A fixture LLM output plus the label I expect the gate to produce.

    The labels are my own. They are what makes the scorecard checkable, and
    they are also the reason this is not an unbiased benchmark (README).
    """

    id: str
    description: str
    category: str
    expected_gate: str
    output: ModelOutput
    expected_codes: Tuple[str, ...] = ()
    expected_advisory_codes: Tuple[str, ...] = ()
    notes: str = ""
