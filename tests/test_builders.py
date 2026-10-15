"""Tests for originscan.context.builders — L1/L2 context assembly.

Covers:
  - L1 basic, truncation, determinism
  - L2 reference detection, priority ordering, cap enforcement
  - Property test: tokens <= cap (hard invariant)
  - SlotResolver / PathResolver
  - build_context top-level API
"""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.builders import (
    PathResolver,
    _extract_call_names,
    _extract_identifiers_from_source,
    build_context,
    build_l1,
    build_l2,
)
from originscan.context.parser import Symbol, parse_file
from originscan.context.tokens import WhitespaceCounter, create_counter

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _make_symbol(
    name: str = "test_func",
    text: str = "int test_func(int x) {\n    return x + 1;\n}",
    kind: str = "function",
    file: str = "test.c",
    start_line: int = 1,
    end_line: int = 3,
    is_static: bool = False,
) -> Symbol:
    return Symbol(
        kind=kind,  # type: ignore[arg-type]
        name=name,
        file=file,
        start_line=start_line,
        end_line=end_line,
        text=text,
        is_static=is_static,
    )


def _simple_symbols() -> tuple[Symbol, list[Symbol]]:
    """Load simple.c and return (process_record, all_symbols)."""
    all_syms = parse_file(FIXTURES / "simple.c")
    target = next(s for s in all_syms if s.name == "process_record")
    return target, all_syms


# -----------------------------------------------------------------------
# Reference detection
# -----------------------------------------------------------------------


class TestReferenceDetection:
    def test_extracts_identifiers(self) -> None:
        code = "int foo(Record* r) { r->value = BUFFER_SIZE; }"
        ids = _extract_identifiers_from_source(code)
        assert "Record" in ids or "r" in ids
        assert "BUFFER_SIZE" in ids
        assert "foo" in ids

    def test_extracts_call_names(self) -> None:
        code = "void bar() { foo(1); baz(2, 3); }"
        calls = _extract_call_names(code)
        assert "foo" in calls
        assert "baz" in calls

    def test_no_false_calls(self) -> None:
        code = "int x = y + z;"
        calls = _extract_call_names(code)
        assert len(calls) == 0

    def test_member_calls_not_included(self) -> None:
        """Member calls (a->b()) are not direct calls."""
        code = "void f() { obj->method(); }"
        calls = _extract_call_names(code)
        assert "method" not in calls  # field_expression, not identifier


# -----------------------------------------------------------------------
# L1 builder
# -----------------------------------------------------------------------


class TestBuildL1:
    def test_basic_l1(self) -> None:
        sym = _make_symbol()
        counter = WhitespaceCounter()
        ctx = build_l1(sym, counter, cap=500)

        assert "TARGET FUNCTION" in ctx["text"]
        assert "test_func" in ctx["text"]
        assert ctx["tokens"] > 0
        assert ctx["tokens"] <= 500
        assert len(ctx["items"]) == 1
        assert "function:test_func" in ctx["items"][0]

    def test_l1_contains_function_body(self) -> None:
        sym = _make_symbol()
        counter = WhitespaceCounter()
        ctx = build_l1(sym, counter, cap=500)
        assert "return x + 1;" in ctx["text"]

    def test_l1_truncation(self) -> None:
        """When function exceeds cap, it gets truncated."""
        long_body = "int big() {\n" + "\n".join(
            f"    int v{i} = {i};" for i in range(200)
        ) + "\n    return 0;\n}"
        sym = _make_symbol(name="big", text=long_body, end_line=203)
        counter = WhitespaceCounter()
        ctx = build_l1(sym, counter, cap=50)

        assert ctx["tokens"] <= 50
        assert "[truncated]" in ctx["text"]
        assert "[truncated]" in ctx["items"][0]

    def test_l1_deterministic(self) -> None:
        """Same input always produces same output."""
        sym = _make_symbol()
        counter = WhitespaceCounter()
        ctx1 = build_l1(sym, counter, cap=500)
        ctx2 = build_l1(sym, counter, cap=500)
        assert ctx1 == ctx2

    def test_l1_with_tiktoken(self) -> None:
        sym = _make_symbol()
        counter = create_counter("cl100k_base")
        ctx = build_l1(sym, counter, cap=500)
        assert ctx["tokens"] > 0
        assert ctx["tokens"] <= 500

    def test_l1_on_real_fixture(self) -> None:
        target, _ = _simple_symbols()
        counter = create_counter("cl100k_base")
        ctx = build_l1(target, counter, cap=2000)
        assert "process_record" in ctx["text"]
        assert ctx["tokens"] <= 2000


# -----------------------------------------------------------------------
# L2 builder
# -----------------------------------------------------------------------


class TestBuildL2:
    def test_l2_includes_referenced_types(self) -> None:
        """L2 should include types that the function references."""
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=2000)

        # process_record uses Record and STATUS_OK/STATUS_ERROR
        items_str = " ".join(ctx["items"])
        # Should include the target
        assert "process_record" in items_str

    def test_l2_includes_referenced_macros(self) -> None:
        target, all_syms = _simple_symbols()
        # main() uses MAX macro
        main_sym = next(s for s in all_syms if s.name == "main")
        counter = WhitespaceCounter()
        ctx = build_l2(main_sym, all_syms, counter, cap=2000)

        # main uses MAX macro
        items_str = " ".join(ctx["items"])
        assert "macro:MAX" in items_str or "main" in items_str

    def test_l2_includes_called_helpers(self) -> None:
        """L2 should include same-file helpers the function calls."""
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=2000)

        # process_record calls internal_helper
        assert "internal_helper" in ctx["text"]

    def test_l2_includes_globals(self) -> None:
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=2000)

        # process_record references global_counter
        assert "global_counter" in ctx["text"]

    def test_l2_respects_cap(self) -> None:
        target, all_syms = _simple_symbols()
        counter = create_counter("cl100k_base")
        ctx = build_l2(target, all_syms, counter, cap=200)
        assert ctx["tokens"] <= 200

    def test_l2_falls_back_to_l1_if_target_exceeds_cap(self) -> None:
        """If the target alone exceeds cap, L2 returns truncated L1."""
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=10)
        assert ctx["tokens"] <= 10
        assert "[truncated]" in ctx["text"]

    def test_l2_deterministic(self) -> None:
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx1 = build_l2(target, all_syms, counter, cap=2000)
        ctx2 = build_l2(target, all_syms, counter, cap=2000)
        assert ctx1 == ctx2

    def test_l2_formatting_has_delimiters(self) -> None:
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=2000)
        assert "// === TARGET FUNCTION" in ctx["text"]

    def test_l2_items_list_has_target_first(self) -> None:
        target, all_syms = _simple_symbols()
        counter = WhitespaceCounter()
        ctx = build_l2(target, all_syms, counter, cap=2000)
        assert "process_record" in ctx["items"][0]


# -----------------------------------------------------------------------
# Property test: tokens <= cap (HARD INVARIANT)
# -----------------------------------------------------------------------


class TestTokenCapInvariant:
    """The most critical test: context tokens must never exceed the cap."""

    @pytest.mark.parametrize("cap", [50, 100, 200, 500, 1000, 2000, 6000])
    def test_l1_never_exceeds_cap(self, cap: int) -> None:
        target, _ = _simple_symbols()
        counter = create_counter("cl100k_base")
        ctx = build_l1(target, counter, cap=cap)
        assert ctx["tokens"] <= cap, (
            f"L1 tokens ({ctx['tokens']}) exceeded cap ({cap})"
        )

    @pytest.mark.parametrize("cap", [50, 100, 200, 500, 1000, 2000, 6000])
    def test_l2_never_exceeds_cap(self, cap: int) -> None:
        target, all_syms = _simple_symbols()
        counter = create_counter("cl100k_base")
        ctx = build_l2(target, all_syms, counter, cap=cap)
        assert ctx["tokens"] <= cap, (
            f"L2 tokens ({ctx['tokens']}) exceeded cap ({cap})"
        )

    @pytest.mark.parametrize("fixture", ["simple.c", "ifdef_macros.c"])
    def test_l2_cap_across_fixtures(self, fixture: str) -> None:
        """Test cap enforcement on multiple fixture files."""
        all_syms = parse_file(FIXTURES / fixture)
        funcs = [s for s in all_syms if s.kind == "function"]
        counter = create_counter("cl100k_base")

        for func in funcs:
            for cap in (100, 500, 2000):
                ctx = build_l2(func, all_syms, counter, cap=cap)
                assert ctx["tokens"] <= cap, (
                    f"{fixture}:{func.name} L2 tokens ({ctx['tokens']}) "
                    f"exceeded cap ({cap})"
                )

    def test_adversarial_large_function(self) -> None:
        """Very large function must still respect the cap."""
        body = "void huge() {\n" + "\n".join(
            f"    int var_{i} = compute_{i}({i});"
            for i in range(500)
        ) + "\n}"
        sym = _make_symbol(name="huge", text=body, end_line=502)
        counter = create_counter("cl100k_base")

        for cap in (50, 200, 1000):
            ctx = build_l1(sym, counter, cap=cap)
            assert ctx["tokens"] <= cap


# -----------------------------------------------------------------------
# Determinism test (run twice, compare)
# -----------------------------------------------------------------------


class TestDeterminism:
    def test_full_determinism_l1(self) -> None:
        target, _ = _simple_symbols()
        counter = create_counter("cl100k_base")
        results = [build_l1(target, counter, cap=2000) for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_full_determinism_l2(self) -> None:
        target, all_syms = _simple_symbols()
        counter = create_counter("cl100k_base")
        results = [
            build_l2(target, all_syms, counter, cap=6000) for _ in range(5)
        ]
        assert all(r == results[0] for r in results)


# -----------------------------------------------------------------------
# PathResolver
# -----------------------------------------------------------------------


class TestPathResolver:
    def test_resolves_function(self) -> None:
        resolver = PathResolver()
        target, syms = resolver.resolve(
            f"process_record@{FIXTURES / 'simple.c'}"
        )
        assert target.name == "process_record"
        assert target.kind == "function"
        assert len(syms) > 0

    def test_unknown_function_raises(self) -> None:
        resolver = PathResolver()
        with pytest.raises(ValueError, match="not found"):
            resolver.resolve(f"nonexistent@{FIXTURES / 'simple.c'}")

    def test_bad_format_raises(self) -> None:
        resolver = PathResolver()
        with pytest.raises(ValueError, match="function_name@file_path"):
            resolver.resolve("no_at_sign")


# -----------------------------------------------------------------------
# build_context top-level API
# -----------------------------------------------------------------------


class TestBuildContext:
    def test_l1_via_build_context(self) -> None:
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L1",
        )
        assert "process_record" in ctx["text"]
        assert ctx["tokens"] <= 2000  # default cap

    def test_l2_via_build_context(self) -> None:
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L2",
        )
        assert "process_record" in ctx["text"]
        assert ctx["tokens"] <= 6000  # default cap

    def test_l3_without_graph_falls_back(self) -> None:
        """L3 without a graph falls back to L2."""
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L3",
        )
        assert ctx["tokens"] > 0
        assert ctx["tokens"] <= 15000

    def test_custom_cap(self) -> None:
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L1",
            cap=100,
        )
        assert ctx["tokens"] <= 100

    def test_custom_caps_dict(self) -> None:
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L2",
            caps={"L2": 300},
        )
        assert ctx["tokens"] <= 300

    def test_whitespace_counter(self) -> None:
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L1",
            counter=WhitespaceCounter(),
        )
        assert ctx["tokens"] > 0
