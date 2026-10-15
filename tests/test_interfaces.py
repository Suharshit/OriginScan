"""Tests for originscan.interfaces — verify types and stub behaviour."""

from __future__ import annotations

import pytest

from originscan.interfaces import (
    Context,
    Finding,
    Level,
    Origin,
    build_context,
    choose_start,
    detect,
)


class TestContext:
    """Verify Context TypedDict structure."""

    def test_create_context(self) -> None:
        ctx: Context = {
            "text": "void foo() { return; }",
            "tokens": 8,
            "items": ["func:foo@src/a.c:10-12"],
        }
        assert ctx["text"] == "void foo() { return; }"
        assert ctx["tokens"] == 8
        assert ctx["items"] == ["func:foo@src/a.c:10-12"]

    def test_context_items_is_list(self) -> None:
        ctx: Context = {"text": "", "tokens": 0, "items": []}
        assert isinstance(ctx["items"], list)


class TestFinding:
    """Verify Finding TypedDict structure."""

    def test_create_finding(self) -> None:
        finding: Finding = {
            "verdict": True,
            "cwe": "CWE-787",
            "line": 31,
            "confidence": 0.67,
            "input_tokens": 5120,
            "output_tokens": 210,
        }
        assert finding["verdict"] is True
        assert finding["cwe"] == "CWE-787"

    def test_finding_with_none_fields(self) -> None:
        finding: Finding = {
            "verdict": False,
            "cwe": None,
            "line": None,
            "confidence": 0.1,
            "input_tokens": 100,
            "output_tokens": 50,
        }
        assert finding["cwe"] is None
        assert finding["line"] is None


class TestStubs:
    """Verify stub implementations behave as documented."""

    def test_build_context_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Phase 3"):
            build_context("test_slot", "L1")

    def test_detect_raises(self) -> None:
        ctx: Context = {"text": "", "tokens": 0, "items": []}
        with pytest.raises(NotImplementedError, match="P5"):
            detect(ctx, "fake", 1)

    def test_choose_start_defaults_to_l1(self) -> None:
        """Confidence-only fallback: always returns L1."""
        assert choose_start("ai", None) == "L1"
        assert choose_start("human", "CWE-787") == "L1"
        assert choose_start("unknown", None) == "L1"


class TestLiterals:
    """Verify Level and Origin type values."""

    def test_valid_levels(self) -> None:
        levels: list[Level] = ["L1", "L2", "L3"]
        assert len(levels) == 3

    def test_valid_origins(self) -> None:
        origins: list[Origin] = ["ai", "human", "unknown"]
        assert len(origins) == 3
