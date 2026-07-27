"""Evaluator interface.

An evaluator takes a parsed ModelOutput and returns an EvaluatorResult. It must
not mutate the output, and it is allowed to raise: the gate treats an evaluator
that raises as a refusal, never as a pass (see gate.py).
"""

from __future__ import annotations

import abc

from ..model import EvaluatorResult, ModelOutput


class Evaluator(abc.ABC):
    name: str = "evaluator"

    @abc.abstractmethod
    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        raise NotImplementedError
