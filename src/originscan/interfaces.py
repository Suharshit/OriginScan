"""Frozen interfaces for OriginScan — shared across P2, P4, P5.

DO NOT modify these types after Week 1 Day 5 without:
  1. Logging the change in docs/interface-changes.md
  2. Notifying P2 and P5

See design.md §2 for rationale.
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Level = Literal["L1", "L2", "L3"]
"""Context depth: L1 (function), L2 (file), L3 (repo slice)."""

Origin = Literal["ai", "human", "unknown"]
"""Code provenance label derived from git metadata."""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


class Context(TypedDict):
    """Detector-ready code context returned by build_context.

    Invariant: tokens <= configured cap for the requested level.
    """

    text: str
    """Prompt-ready code context with delimiters."""

    tokens: int
    """Token count of *text* (approximate; tokenizer recorded per run)."""

    items: list[str]
    """IDs of included elements, e.g. ``"func:foo@src/a.c:10-42"``."""


class Finding(TypedDict):
    """Detection result returned by a detector adapter (owned by P5)."""

    verdict: bool
    """True if a vulnerability was detected."""

    cwe: str | None
    """CWE identifier, e.g. ``"CWE-787"``, or None."""

    line: int | None
    """Line number of the finding within the target function, or None."""

    confidence: float
    """Detector confidence in [0.0, 1.0]."""

    input_tokens: int
    """Tokens sent to the detector."""

    output_tokens: int
    """Tokens received from the detector."""


# ---------------------------------------------------------------------------
# Function protocols / signatures
# ---------------------------------------------------------------------------


class BuildContextFn(Protocol):
    """Protocol for the build_context callable."""

    def __call__(self, slot_id: str, level: Level) -> Context: ...


class DetectFn(Protocol):
    """Protocol for the detect callable (P5-owned)."""

    def __call__(self, ctx: Context, detector: str, run: int) -> Finding: ...


class ChooseStartFn(Protocol):
    """Protocol for the choose_start callable (P5-owned)."""

    def __call__(self, origin: Origin, cwe_family: str | None) -> Level: ...


# ---------------------------------------------------------------------------
# Detector adapter protocol (design.md §8)
# ---------------------------------------------------------------------------


class DetectorAdapter(Protocol):
    """Interface for detector adapters (LLM, static, fake)."""

    def run(self, ctx: Context, run: int) -> Finding: ...


# ---------------------------------------------------------------------------
# Stub implementations — to be replaced by real code in later phases
# ---------------------------------------------------------------------------


def build_context(slot_id: str, level: Level) -> Context:
    """Build detector-ready context for a given slot and level.

    Stub — real implementation lives in context/builders.py (Phase 3+).
    """
    raise NotImplementedError("build_context not yet implemented (Phase 3)")


def detect(ctx: Context, detector: str, run: int) -> Finding:
    """Run a detector on a context (P5-owned).

    Stub — P4 provides FakeDetector for testing.
    """
    raise NotImplementedError("detect is owned by P5")


def choose_start(origin: Origin, cwe_family: str | None) -> Level:
    """Choose the starting context level based on provenance (P5-owned).

    Stub — falls back to confidence-only default (always L1).
    """
    return "L1"
