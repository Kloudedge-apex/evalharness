"""Evaluator interface.

An evaluator takes a parsed ModelOutput and returns an EvaluatorResult. It must
not mutate the output, and it is allowed to raise: the gate treats an evaluator
that raises as a refusal, never as a pass (see gate.py).
"""

from __future__ import annotations

import abc
from typing import List, Tuple

from ..model import EvaluatorResult, ModelOutput


class Evaluator(abc.ABC):
    name: str = "evaluator"

    @abc.abstractmethod
    def evaluate(self, output: ModelOutput) -> EvaluatorResult:
        raise NotImplementedError


def scan_targets(output: ModelOutput) -> List[Tuple[str, str, str]]:
    """Every piece of text a content evaluator has to read.

    Returns (location, field, text) triples: the response, then the title, url
    and snippet of each retrieved source.

    The title and the url are here because leaving them out was a bypass, and a
    quiet one. Both the PII and the injection evaluator used to append only
    `source.snippet`, while the README described their scope as "the response,
    or any retrieved source". A hostile document that carries its payload in
    the title, or an API key sitting in a query string, was therefore not
    scanned at all: a source titled "Record for 123-45-6789 card 4111 1111 1111
    1111" was released without a finding.

    Field is returned separately from location so that a caller can key its
    deduplication on it. Two fields of the same source can produce a match of
    the same kind at the same offset, and collapsing those into one hides the
    second.
    """
    targets: List[Tuple[str, str, str]] = [("response", "response", output.response)]
    for source in output.sources:
        location = "source:{0}".format(source.id)
        targets.append((location, "title", source.title))
        targets.append((location, "url", source.url))
        targets.append((location, "snippet", source.snippet))
    return targets
