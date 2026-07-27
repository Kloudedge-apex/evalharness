"""evalharness: a small refuse-or-cite evaluation harness over fixture LLM outputs.

Standard library only. No network calls, no API keys, no model inference.
See README.md for what this is and, more importantly, what it is not.
"""

from __future__ import annotations

from .gate import Decision, GateResult, RefuseOrCiteGate
from .model import Citation, Claim, EvaluatorResult, Finding, ModelOutput, Severity
from .segment import parse_output

__version__ = "0.1.0"

__all__ = [
    "Citation",
    "Claim",
    "Decision",
    "EvaluatorResult",
    "Finding",
    "GateResult",
    "ModelOutput",
    "RefuseOrCiteGate",
    "Severity",
    "parse_output",
    "__version__",
]
