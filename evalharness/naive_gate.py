"""The wrong implementation. Kept on purpose. Do not use it for anything.

This is a keyword-anywhere check: it scans the whole response for anything that
looks like a citation and, if it finds one, passes the entire output.

It is in the repo because I shipped this shape of bug in a real gate, and the
review that caught it caught it by reproducing the bypass rather than by reading
the diff. Keeping the broken version next to the real one means the difference
is executable: tests/test_naive_vs_real.py asserts that this function says yes
and RefuseOrCiteGate says refuse, on the same inputs.

Two ways it is wrong, and both show up in the fixtures:

  1. Document scope. One genuine citation anywhere satisfies the check for
     every claim in the output, including the four unsourced ones next to it.

  2. Substring scope. It matches "source" and "http" as raw substrings, so
     ordinary prose ("we source components locally", "the http endpoint") reads
     as evidence of a citation.

The fix for both is the same idea: bind the check to the unit you actually care
about (a claim), and match tokens rather than substrings.
"""

from __future__ import annotations

from typing import Tuple

CITATION_HINTS: Tuple[str, ...] = ("[1]", "http", "source", "according to", "reference")


def naive_allows(response: str) -> bool:
    """Return True if the response 'has a citation' by keyword-anywhere scan."""
    lowered = (response or "").lower()
    return any(hint in lowered for hint in CITATION_HINTS)
