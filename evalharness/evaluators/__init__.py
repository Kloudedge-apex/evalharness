"""Evaluators.

Blocking: citation_coverage, pii, prompt_injection.
Advisory: support_overlap.

The blocking set is small on purpose. Every evaluator you make blocking is an
evaluator that can take the product down when it misfires, so each one has to
earn it.
"""

from __future__ import annotations

from typing import Tuple

from .base import Evaluator
from .citation import CitationCoverageEvaluator
from .injection import PromptInjectionEvaluator
from .pii import PIIEvaluator
from .support import SupportOverlapEvaluator

__all__ = [
    "Evaluator",
    "CitationCoverageEvaluator",
    "PIIEvaluator",
    "PromptInjectionEvaluator",
    "SupportOverlapEvaluator",
    "default_evaluators",
]


def default_evaluators() -> Tuple[Evaluator, ...]:
    return (
        CitationCoverageEvaluator(),
        PIIEvaluator(),
        PromptInjectionEvaluator(),
        SupportOverlapEvaluator(),
    )
