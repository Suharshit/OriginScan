"""Pluggable token counting.

Default uses tiktoken (cl100k_base) as an approximation of the target
model's tokenizer. The tokenizer name is recorded in each run for
reproducibility.

See design.md §5 (Common section).

Public API:
    TokenCounter (Protocol)
    TiktokenCounter
    WhitespaceCounter
    create_counter(name) -> TokenCounter
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenCounter(Protocol):
    """Protocol for token counting implementations.

    Every context builder uses this to enforce token caps.
    The tokenizer name is recorded per run for reproducibility.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this counter (for run metadata)."""
        ...

    def count(self, text: str) -> int:
        """Count the number of tokens in *text*."""
        ...


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class TiktokenCounter:
    """Token counter using tiktoken (default: cl100k_base).

    This is an approximation — different models tokenize differently.
    The encoding name is recorded in each run for reproducibility.
    """

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding_name = encoding_name
        self._encoder = tiktoken.get_encoding(encoding_name)

    @property
    def name(self) -> str:
        return f"tiktoken:{self._encoding_name}"

    def count(self, text: str) -> int:
        return len(self._encoder.encode(text))


class WhitespaceCounter:
    """Fallback token counter: splits on whitespace.

    Useful when tiktoken is unavailable or for fast approximations
    in tests.
    """

    @property
    def name(self) -> str:
        return "whitespace"

    def count(self, text: str) -> int:
        return len(text.split())


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_counter(name: str = "cl100k_base") -> TokenCounter:
    """Create a token counter by name.

    Args:
        name: ``"whitespace"`` for the fallback counter, or a tiktoken
              encoding name (e.g. ``"cl100k_base"``, ``"o200k_base"``).

    Returns:
        A TokenCounter instance.
    """
    if name == "whitespace":
        return WhitespaceCounter()
    return TiktokenCounter(name)
