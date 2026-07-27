"""Evaluator interface.

An evaluator takes a parsed ModelOutput and returns an EvaluatorResult. It must
not mutate the output, and it is allowed to raise: the gate treats an evaluator
that raises as a refusal, never as a pass (see gate.py).
"""

from __future__ import annotations

import abc
import dataclasses
from typing import List, Tuple

from ..model import EvaluatorResult, ModelOutput


class Evaluator(abc.ABC):
    name: str = "evaluator"

    @abc.abstractmethod
    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        raise NotImplementedError


def scan_targets(output: ModelOutput) -> List[Tuple[str, str, str]]:
    """Every piece of text a content evaluator has to read.

    Returns (location, field, text) triples: the response, then every string
    field of every retrieved source.

    The fields are read off the dataclass rather than listed here, and that is
    the whole point of the function. This scope has now been wrong twice in the
    same direction. First both evaluators appended only `source.snippet`, so a
    payload in the title or an API key in a query string was never scanned: a
    source titled "Record for 123-45-6789 card 4111 1111 1111 1111" was
    released with no finding. That was fixed by listing title, url and snippet
    here, which looked like the fix and was not: `Citation.published` was still
    unread, so the identical payload that produced six findings in `snippet`
    produced zero in `published`. A hand-written list of fields is a whitelist,
    and this file already knows what a whitelist is worth.

    So the list is gone. Adding a field to `Citation` now adds it to the scan,
    and forgetting to update this function is no longer a thing that can
    happen. Non-string fields are skipped because there is nothing to match.

    Field is returned separately from location so that a caller can key its
    deduplication on it. Two fields of the same source can produce a match of
    the same kind at the same offset, and collapsing those into one hides the
    second.
    """
    targets: List[Tuple[str, str, str]] = [("response", "response", output.response)]
    for source in output.sources:
        location = "source:{0}".format(source.id)
        for field in dataclasses.fields(source):
            value = getattr(source, field.name)
            if isinstance(value, str):
                targets.append((location, field.name, value))
    return targets
