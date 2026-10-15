"""Approximate name-based call graph with ambiguity tracking.

Extracts call_expression identifiers from function bodies, resolves
names using the ambiguity rule (same file -> same dir -> anywhere),
and provides BFS-based callers/callees queries with hop depth.

See design.md §4 (Call extraction and Name resolution sections).

Public API:
    CallGraph.build(index)     -> CallGraph
    CallGraph.callees(fn_id, hops)  -> list[ResolvedEdge]
    CallGraph.callers(fn_id, hops)  -> list[ResolvedEdge]
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from tree_sitter import Node, Parser

from originscan.context.parser import C_LANGUAGE, CPP_LANGUAGE, Symbol

if TYPE_CHECKING:
    from originscan.context.index import RepoIndex

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawCall:
    """A raw call expression found in a function body."""

    name: str
    member: bool = False  # True for a->b() or a.b()


@dataclass(frozen=True)
class ResolvedEdge:
    """A resolved call-graph edge."""

    caller: str  # fn_id of the caller
    callee: str  # fn_id of the callee
    ambiguous: bool = False  # True if resolution was ambiguous


def _make_fn_id(sym: Symbol) -> str:
    """Create a deterministic function ID."""
    return f"{sym.name}@{sym.file}:{sym.start_line}-{sym.end_line}"


# ---------------------------------------------------------------------------
# Call extraction
# ---------------------------------------------------------------------------


def _extract_calls(func: Symbol) -> list[RawCall]:
    """Extract call_expression names from a function body."""
    is_cpp = any(
        func.file.endswith(ext) for ext in (".cpp", ".cc", ".cxx", ".hpp", ".hh")
    )
    lang = CPP_LANGUAGE if is_cpp else C_LANGUAGE
    parser = Parser(lang)
    tree = parser.parse(func.text.encode("utf-8"))

    calls: list[RawCall] = []

    def visit(node: Node) -> None:
        if node.type == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                if fn_node.type == "identifier" and fn_node.text:
                    calls.append(RawCall(
                        name=fn_node.text.decode("utf-8"), member=False
                    ))
                elif fn_node.type == "field_expression":
                    field_node = fn_node.child_by_field_name("field")
                    if field_node and field_node.text:
                        calls.append(RawCall(
                            name=field_node.text.decode("utf-8"), member=True
                        ))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return calls


# ---------------------------------------------------------------------------
# Name resolution (design.md §4 ambiguity rule)
# ---------------------------------------------------------------------------


def _resolve_name(
    name: str,
    caller_file: str,
    index: RepoIndex,
) -> tuple[Symbol | None, bool]:
    """Resolve a called function name to a Symbol.

    Ambiguity rule (in order):
      1. Same file
      2. Same directory
      3. Unique match anywhere in the repo
      4. Multiple matches: prefer non-static, then shortest path
         distance, then lexicographic path. Record ambiguous=True.
      5. No match: return None (external/libc).

    Returns:
        (resolved_symbol, ambiguous)
    """
    candidates = index.symbols_by_name.get(name, [])
    funcs = [s for s in candidates if s.kind == "function"]

    if not funcs:
        return None, False

    # 1. Same file
    same_file = [f for f in funcs if f.file == caller_file]
    if len(same_file) == 1:
        return same_file[0], False
    if len(same_file) > 1:
        # Multiple in same file — prefer non-static, then first by line
        non_static = [f for f in same_file if not f.is_static]
        if len(non_static) == 1:
            return non_static[0], False
        chosen = sorted(same_file, key=lambda s: (s.is_static, s.start_line))[0]
        return chosen, True

    # 2. Same directory
    caller_dir = str(PurePosixPath(caller_file).parent)
    same_dir = [f for f in funcs if str(PurePosixPath(f.file).parent) == caller_dir]
    if len(same_dir) == 1:
        return same_dir[0], False
    if len(same_dir) > 1:
        non_static = [f for f in same_dir if not f.is_static]
        if len(non_static) == 1:
            return non_static[0], False
        chosen = sorted(same_dir, key=lambda s: (s.is_static, s.file, s.start_line))[0]
        return chosen, True

    # 3. Unique match anywhere
    if len(funcs) == 1:
        return funcs[0], False

    # 4. Multiple matches — apply tie-breaking
    # Prefer non-static
    non_static = [f for f in funcs if not f.is_static]
    pool = non_static if non_static else funcs

    # Sort by path distance from caller, then lexicographic
    def _path_distance(f: Symbol) -> int:
        caller_parts = PurePosixPath(caller_file).parts
        callee_parts = PurePosixPath(f.file).parts
        common = 0
        for a, b in zip(caller_parts, callee_parts, strict=False):
            if a == b:
                common += 1
            else:
                break
        return len(caller_parts) + len(callee_parts) - 2 * common

    pool.sort(key=lambda f: (_path_distance(f), f.file, f.start_line))
    return pool[0], True


# ---------------------------------------------------------------------------
# CallGraph
# ---------------------------------------------------------------------------


@dataclass
class CallGraph:
    """Approximate name-based call graph.

    Edges are resolved using the ambiguity rule. Provides BFS-based
    callers/callees queries with configurable hop depth.
    """

    # fn_id -> list of ResolvedEdge (outgoing)
    _callees: dict[str, list[ResolvedEdge]] = field(default_factory=lambda: defaultdict(list))
    # fn_id -> list of ResolvedEdge (incoming)
    _callers: dict[str, list[ResolvedEdge]] = field(default_factory=lambda: defaultdict(list))
    # fn_id -> Symbol
    _fn_map: dict[str, Symbol] = field(default_factory=dict)
    # Unresolved external calls
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # (caller_fn_id, name)

    @classmethod
    def build(cls, index: RepoIndex) -> CallGraph:
        """Build a call graph from a RepoIndex.

        Extracts calls from every function, resolves names, and builds
        the caller/callee maps.
        """
        graph = cls()
        all_funcs = index.functions()

        # Build fn_id map
        for func in all_funcs:
            fn_id = _make_fn_id(func)
            graph._fn_map[fn_id] = func

        # Extract and resolve calls
        for func in all_funcs:
            caller_id = _make_fn_id(func)
            raw_calls = _extract_calls(func)

            # Deduplicate by name (keep first occurrence)
            seen_names: set[str] = set()
            for call in raw_calls:
                if call.name in seen_names:
                    continue
                seen_names.add(call.name)

                # Skip member calls for now (design.md: flag but don't resolve)
                if call.member:
                    continue

                resolved, ambiguous = _resolve_name(
                    call.name, func.file, index
                )

                if resolved is None:
                    graph.unresolved.append((caller_id, call.name))
                    continue

                callee_id = _make_fn_id(resolved)
                # Skip self-recursion edges for graph traversal clarity
                if callee_id == caller_id:
                    continue

                edge = ResolvedEdge(
                    caller=caller_id,
                    callee=callee_id,
                    ambiguous=ambiguous,
                )
                graph._callees[caller_id].append(edge)
                graph._callers[callee_id].append(edge)

        # Sort edges deterministically
        for edges in graph._callees.values():
            edges.sort(key=lambda e: (e.ambiguous, e.callee))
        for edges in graph._callers.values():
            edges.sort(key=lambda e: (e.ambiguous, e.caller))

        logger.info(
            "Call graph: %d functions, %d edges, %d unresolved",
            len(graph._fn_map),
            sum(len(v) for v in graph._callees.values()),
            len(graph.unresolved),
        )

        return graph

    def get_symbol(self, fn_id: str) -> Symbol | None:
        """Look up a Symbol by fn_id."""
        return self._fn_map.get(fn_id)

    def fn_id_for(self, func: Symbol) -> str:
        """Get the fn_id for a Symbol."""
        return _make_fn_id(func)

    def callees(self, fn_id: str, hops: int = 1) -> list[ResolvedEdge]:
        """Get callees up to N hops away (BFS, deterministic order)."""
        return self._bfs(fn_id, hops, direction="callees")

    def callers(self, fn_id: str, hops: int = 1) -> list[ResolvedEdge]:
        """Get callers up to N hops away (BFS, deterministic order)."""
        return self._bfs(fn_id, hops, direction="callers")

    def _bfs(
        self, start: str, hops: int, direction: str
    ) -> list[ResolvedEdge]:
        """BFS traversal collecting edges up to *hops* deep."""
        edge_map = self._callees if direction == "callees" else self._callers
        visited: set[str] = {start}
        result: list[ResolvedEdge] = []
        frontier = [start]

        for _hop in range(hops):
            next_frontier: list[str] = []
            for node in frontier:
                for edge in edge_map.get(node, []):
                    target = edge.callee if direction == "callees" else edge.caller
                    if target not in visited:
                        visited.add(target)
                        result.append(edge)
                        next_frontier.append(target)
            frontier = sorted(next_frontier)  # deterministic BFS order

        return result
