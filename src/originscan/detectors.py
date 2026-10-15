"""FakeDetector and DetectorAdapter implementations for testing.

Provides a deterministic FakeDetector that P5 can use before real LLM
detectors are wired up. Also provides the base for the escalation loop.

See design.md §8 and PRD task 6.6.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from originscan.interfaces import Context, DetectorAdapter, Finding


@dataclass
class FakeDetector:
    """Deterministic fake detector for testing.

    Returns a fixed verdict based on a hash of the input text, so that
    results are reproducible. Used for integration tests and pilot runs
    before real detectors are available.
    """

    name: str = "fake"
    base_confidence: float = 0.7

    def run(self, ctx: Context, run: int) -> Finding:
        """Produce a deterministic finding from the context text.

        The verdict flips based on a hash of (text, run) to exercise
        both True and False paths in tests.
        """
        text = ctx["text"]
        tokens = ctx["tokens"]

        # Deterministic hash → verdict
        h = hashlib.sha256(f"{text}:{run}".encode()).hexdigest()
        verdict = int(h[0], 16) >= 8  # ~50% chance

        # Deterministic confidence
        confidence = min(
            1.0, self.base_confidence + (int(h[1], 16) / 100)
        )

        return Finding(
            verdict=verdict,
            cwe="CWE-787" if verdict else None,
            line=10 if verdict else None,
            confidence=confidence,
            input_tokens=tokens,
            output_tokens=max(10, tokens // 10),
        )


# Verify FakeDetector satisfies the protocol at import time
_check: DetectorAdapter = FakeDetector()  # noqa: F841
