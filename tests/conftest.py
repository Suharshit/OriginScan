"""Shared test configuration for OriginScan.

Sets ORIGINSCAN_TOKENIZER=whitespace by default so tests run offline
without tiktoken needing to download cl100k_base.

Tests that specifically test tiktoken should use the
``requires_tiktoken`` marker, which skips when the encoding is
unavailable.
"""

from __future__ import annotations

import os

import pytest


def _tiktoken_available() -> bool:
    """Check if tiktoken cl100k_base encoding is available."""
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base")
        return True
    except Exception:
        return False


# Register the custom marker
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_tiktoken: skip when tiktoken cl100k_base is unavailable",
    )


@pytest.fixture(autouse=True)
def _use_whitespace_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all tests to the whitespace tokenizer for offline use.

    Tests marked with ``@pytest.mark.requires_tiktoken`` will clear
    this override so they use real tiktoken.
    """
    # Only set if not already set by the test itself
    if "ORIGINSCAN_TOKENIZER" not in os.environ:
        monkeypatch.setenv("ORIGINSCAN_TOKENIZER", "whitespace")


@pytest.fixture()
def use_tiktoken(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture that enables real tiktoken for a specific test.

    Usage::

        @pytest.mark.requires_tiktoken
        def test_something(self, use_tiktoken):
            ...
    """
    monkeypatch.delenv("ORIGINSCAN_TOKENIZER", raising=False)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip tests marked requires_tiktoken when unavailable."""
    if _tiktoken_available():
        return

    skip_marker = pytest.mark.skip(
        reason="tiktoken cl100k_base not available (offline)"
    )
    for item in items:
        if "requires_tiktoken" in item.keywords:
            item.add_marker(skip_marker)
