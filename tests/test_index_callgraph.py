"""Tests for originscan.context.index and originscan.context.callgraph.

Covers:
  - RepoIndex.build on multifile fixture
  - Symbol lookup by name/file
  - CallGraph.build, callers, callees
  - Name resolution ambiguity rule
  - L3 builder with call graph
  - Token cap invariant for L3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from originscan.context.builders import build_context, build_l3
from originscan.context.callgraph import CallGraph, _make_fn_id
from originscan.context.index import RepoIndex
from originscan.context.tokens import WhitespaceCounter, create_counter

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MULTIFILE = FIXTURES / "multifile"


# -----------------------------------------------------------------------
# RepoIndex
# -----------------------------------------------------------------------


class TestRepoIndex:
    @pytest.fixture()
    def index(self) -> RepoIndex:
        return RepoIndex.build(MULTIFILE, commit="test_commit_abc123")

    def test_parses_all_files(self, index: RepoIndex) -> None:
        assert index.files_parsed >= 4  # main.c, utils.c, types.c, types.h
        assert index.files_failed == 0

    def test_symbols_by_file(self, index: RepoIndex) -> None:
        files = list(index.symbols_by_file.keys())
        assert any("main.c" in f for f in files)
        assert any("utils.c" in f for f in files)
        assert any("types.c" in f for f in files)

    def test_symbols_by_name(self, index: RepoIndex) -> None:
        assert "main" in index.symbols_by_name
        assert "process_and_validate" in index.symbols_by_name
        assert "create_record" in index.symbols_by_name

    def test_get_function(self, index: RepoIndex) -> None:
        func = index.get_function("process_and_validate")
        assert func is not None
        assert func.kind == "function"
        assert func.name == "process_and_validate"

    def test_get_function_unknown(self, index: RepoIndex) -> None:
        assert index.get_function("nonexistent") is None

    def test_functions_list(self, index: RepoIndex) -> None:
        funcs = index.functions()
        names = [f.name for f in funcs]
        assert "main" in names
        assert "log_message" in names
        assert "compute_hash" in names

    def test_all_symbols_sorted(self, index: RepoIndex) -> None:
        syms = index.all_symbols
        for i in range(len(syms) - 1):
            assert (syms[i].file, syms[i].start_line) <= (
                syms[i + 1].file, syms[i + 1].start_line,
            )

    def test_relative_paths(self, index: RepoIndex) -> None:
        """Symbol file paths should be relative to the repo root."""
        for sym in index.all_symbols:
            assert not Path(sym.file).is_absolute()

    def test_cache_roundtrip(self, index: RepoIndex, tmp_path: Path) -> None:
        """Saving and loading from cache produces an equivalent index."""
        index._save_cache(tmp_path)
        loaded = RepoIndex._load_cache(tmp_path, index.commit)
        assert loaded is not None
        assert loaded.commit == index.commit
        assert loaded.files_parsed == index.files_parsed
        assert len(loaded.all_symbols) == len(index.all_symbols)


# -----------------------------------------------------------------------
# CallGraph
# -----------------------------------------------------------------------


class TestCallGraph:
    @pytest.fixture()
    def index(self) -> RepoIndex:
        return RepoIndex.build(MULTIFILE, commit="test_commit_abc123")

    @pytest.fixture()
    def graph(self, index: RepoIndex) -> CallGraph:
        return CallGraph.build(index)

    def test_build_succeeds(self, graph: CallGraph) -> None:
        assert graph is not None

    def test_main_calls_known_functions(self, graph: CallGraph, index: RepoIndex) -> None:
        main_fn = index.get_function("main")
        assert main_fn is not None
        fn_id = _make_fn_id(main_fn)
        callees = graph.callees(fn_id, hops=1)
        callee_names = []
        for edge in callees:
            sym = graph.get_symbol(edge.callee)
            if sym:
                callee_names.append(sym.name)
        assert "create_record" in callee_names
        assert "process_and_validate" in callee_names
        assert "print_result" in callee_names

    def test_process_calls_compute_hash(self, graph: CallGraph, index: RepoIndex) -> None:
        func = index.get_function("process_and_validate")
        assert func is not None
        fn_id = _make_fn_id(func)
        callees = graph.callees(fn_id, hops=1)
        callee_names = [
            graph.get_symbol(e.callee).name
            for e in callees
            if graph.get_symbol(e.callee)
        ]
        assert "compute_hash" in callee_names
        assert "log_message" in callee_names

    def test_callers_of_log_message(self, graph: CallGraph, index: RepoIndex) -> None:
        func = index.get_function("log_message")
        assert func is not None
        fn_id = _make_fn_id(func)
        callers = graph.callers(fn_id, hops=1)
        caller_names = [
            graph.get_symbol(e.caller).name
            for e in callers
            if graph.get_symbol(e.caller)
        ]
        assert "process_and_validate" in caller_names or "print_result" in caller_names

    def test_hop2_reaches_deeper(self, graph: CallGraph, index: RepoIndex) -> None:
        main_fn = index.get_function("main")
        assert main_fn is not None
        fn_id = _make_fn_id(main_fn)

        hop1 = graph.callees(fn_id, hops=1)
        hop2 = graph.callees(fn_id, hops=2)
        assert len(hop2) >= len(hop1)

    def test_static_resolved_same_file(
        self, graph: CallGraph, index: RepoIndex
    ) -> None:
        """log_internal is static — should resolve within same file."""
        func = index.get_function("log_message")
        assert func is not None
        fn_id = _make_fn_id(func)
        callees = graph.callees(fn_id, hops=1)
        callee_names = [
            graph.get_symbol(e.callee).name
            for e in callees
            if graph.get_symbol(e.callee)
        ]
        assert "log_internal" in callee_names

    def test_unresolved_contains_externals(self, graph: CallGraph) -> None:
        """External calls like printf, strncpy should be unresolved."""
        unresolved_names = [name for _, name in graph.unresolved]
        # At least some libc calls should be unresolved
        assert len(unresolved_names) > 0

    def test_deterministic(self, index: RepoIndex) -> None:
        g1 = CallGraph.build(index)
        g2 = CallGraph.build(index)
        # Same edges
        assert set(g1._callees.keys()) == set(g2._callees.keys())
        for key in g1._callees:
            assert g1._callees[key] == g2._callees[key]


# -----------------------------------------------------------------------
# L3 builder
# -----------------------------------------------------------------------


class TestBuildL3:
    @pytest.fixture()
    def index(self) -> RepoIndex:
        return RepoIndex.build(MULTIFILE, commit="test_commit_abc123")

    @pytest.fixture()
    def graph(self, index: RepoIndex) -> CallGraph:
        return CallGraph.build(index)

    def test_l3_includes_cross_file_callees(self, index: RepoIndex, graph: CallGraph) -> None:
        func = index.get_function("main")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = WhitespaceCounter()
        ctx = build_l3(func, file_syms, counter, cap=5000, graph=graph, index=index)

        # L3 should include cross-file functions
        assert "create_record" in ctx["text"] or "process_and_validate" in ctx["text"]

    def test_l3_includes_cross_file_callers(self, index: RepoIndex, graph: CallGraph) -> None:
        func = index.get_function("compute_hash")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = WhitespaceCounter()
        ctx = build_l3(func, file_syms, counter, cap=5000, graph=graph, index=index)

        # compute_hash is called by process_and_validate (different file)
        items_str = " ".join(ctx["items"])
        assert "process_and_validate" in ctx["text"] or "process_and_validate" in items_str

    def test_l3_respects_cap(self, index: RepoIndex, graph: CallGraph) -> None:
        func = index.get_function("main")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = create_counter("cl100k_base")
        for cap in (100, 500, 1000, 5000, 15000):
            ctx = build_l3(func, file_syms, counter, cap=cap, graph=graph, index=index)
            assert ctx["tokens"] <= cap, f"L3 exceeded cap {cap}: {ctx['tokens']}"

    def test_l3_deterministic(self, index: RepoIndex, graph: CallGraph) -> None:
        func = index.get_function("main")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = WhitespaceCounter()
        results = [
            build_l3(func, file_syms, counter, cap=5000, graph=graph, index=index)
            for _ in range(3)
        ]
        assert all(r == results[0] for r in results)

    def test_l3_fallback_without_graph(self, index: RepoIndex) -> None:
        """L3 without a call graph should fall back to L2."""
        func = index.get_function("main")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = WhitespaceCounter()
        ctx = build_l3(func, file_syms, counter, cap=5000)
        # Should still produce valid context (L2 fallback)
        assert ctx["tokens"] > 0
        assert "main" in ctx["text"]

    def test_l3_has_more_items_than_l2(self, index: RepoIndex, graph: CallGraph) -> None:
        """L3 should generally include more items than L2."""
        from originscan.context.builders import build_l2

        func = index.get_function("main")
        assert func is not None
        file_syms = index.get_file_symbols(func.file)
        counter = WhitespaceCounter()
        l2 = build_l2(func, file_syms, counter, cap=5000)
        l3 = build_l3(func, file_syms, counter, cap=5000, graph=graph, index=index)
        assert len(l3["items"]) >= len(l2["items"])


# -----------------------------------------------------------------------
# build_context with L3
# -----------------------------------------------------------------------


class TestBuildContextL3:
    def test_l3_no_longer_raises(self) -> None:
        """L3 should work now (falls back to L2 without graph)."""
        ctx = build_context(
            f"process_record@{FIXTURES / 'simple.c'}",
            "L3",
        )
        # Without graph, falls back to L2
        assert ctx["tokens"] > 0
        assert ctx["tokens"] <= 15000
