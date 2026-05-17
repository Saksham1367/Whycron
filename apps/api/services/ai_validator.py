"""Hallucination validator (CONTEXT.md §8.4 mitigation #1).

After Claude returns an explanation, we extract concrete-looking citations
(backtick spans, all-caps identifiers, file paths) and check whether each
appears in the input log context. The grade downgrades from ``high`` to
``low`` as the share of grounded citations drops.

This is a backstop — the primary defense is the prompt itself ("never
invent fixes you can't justify from the logs"). The validator catches
cases where Claude confidently cites a path or error code that wasn't in
the logs.
"""
from __future__ import annotations

import re

_BACKTICK_RE = re.compile(r"`([^`]+)`")
# All-caps identifiers like ERROR, FATAL, OOMKilled, EACCES — these are
# the kind of tokens an SRE would quote from a log line.
_CAPS_RE = re.compile(r"\b([A-Z]{3,}[A-Z0-9_]*)\b")
# Posix or Windows-style file paths.
_PATH_RE = re.compile(
    r"(?:/[A-Za-z0-9_./\-]+|[A-Za-z]:\\[A-Za-z0-9_\\.\-]+)"
)


def extract_citations(text: str) -> list[str]:
    """Return concrete-looking spans from ``text`` that should be verifiable
    against the input logs. Order-preserving, deduplicated.
    """
    citations: list[str] = []
    citations.extend(_BACKTICK_RE.findall(text))
    citations.extend(_CAPS_RE.findall(text))
    citations.extend(_PATH_RE.findall(text))
    seen: set[str] = set()
    out: list[str] = []
    for c in citations:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def grade_confidence(claude_output: str, input_context: str) -> str:
    """Return ``'high' | 'medium' | 'low'`` for the explanation.

    - **high**  — every cited token appears literally in the input.
    - **medium** — no specific citations to verify, or 70 %+ are grounded.
    - **low**   — fewer than 70 % of citations are grounded; the model is
      probably hallucinating and the row should be flagged for review.
    """
    citations = extract_citations(claude_output)
    if not citations:
        return "medium"
    grounded = sum(1 for c in citations if c in input_context)
    ratio = grounded / len(citations)
    if ratio == 1.0:
        return "high"
    if ratio >= 0.7:
        return "medium"
    return "low"
