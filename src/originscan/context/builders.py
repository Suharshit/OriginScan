"""Context builders for L1, L2, L3 with hard token caps.

L1 — target function only.
L2 — L1 + selected same-file types, macros, globals, helpers.
L3 — L2 + repo-slice callers/callees (Phase 4).

Hard invariant: ctx["tokens"] <= cap[level].

See design.md §5.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from originscan.context.parser import C_LANGUAGE, CPP_LANGUAGE, Symbol
from originscan.context.tokens import TokenCounter, create_counter
from originscan.interfaces import Context, Level

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from originscan.context.callgraph import CallGraph
    from originscan.context.index import RepoIndex

# ---------------------------------------------------------------------------
# Reference detection (design.md §5: "identifier match on the tree")
# ---------------------------------------------------------------------------


def _extract_identifiers_from_source(text: str, is_cpp: bool = False) -> set[str]:
    """Extract all identifier tokens from a code snippet using tree-sitter.

    This is the "referenced" check: an item is referenced by a function
    if its identifier appears in the function's tree-sitter token stream.
    Uses tree-level matching, NOT substring search (design.md §5).
    """
    from tree_sitter import Node

    lang = CPP_LANGUAGE if is_cpp else C_LANGUAGE
    # Walk the tree to collect all identifier tokens directly.
    from tree_sitter import Parser

    parser = Parser(lang)
    tree = parser.parse(text.encode("utf-8"))

    identifiers: set[str] = set()

    def visit(node: Node) -> None:
        if node.type in ("identifier", "type_identifier", "field_identifier"):
            name = node.text.decode("utf-8") if node.text else ""
            if name:
                identifiers.add(name)
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return identifiers


def _extract_call_names(text: str, is_cpp: bool = False) -> set[str]:
    """Extract function names that are directly called in a code snippet.

    Looks for call_expression nodes and extracts the function identifier.
    """
    from tree_sitter import Node, Parser

    lang = CPP_LANGUAGE if is_cpp else C_LANGUAGE
    parser = Parser(lang)
    tree = parser.parse(text.encode("utf-8"))

    calls: set[str] = set()

    def visit(node: Node) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "identifier" and func.text:
                calls.add(func.text.decode("utf-8"))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return calls


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_target(symbol: Symbol) -> str:
    """Format the target function with delimiters."""
    loc = f"{symbol.file}:{symbol.start_line}-{symbol.end_line}"
    return f"// === TARGET FUNCTION ({loc}) ===\n{symbol.text}"


def _format_file_context(label: str, items_text: str) -> str:
    """Format a file-context section with a labelled delimiter."""
    return f"// === FILE CONTEXT: {label} ===\n{items_text}"


def _format_helper(symbol: Symbol, signature_only: bool = False) -> str:
    """Format a helper function (full or signature-only)."""
    loc = f"{symbol.file}:{symbol.start_line}-{symbol.end_line}"
    if signature_only:
        # Extract just the signature (first line or up to opening brace)
        lines = symbol.text.split("\n")
        sig_lines: list[str] = []
        for line in lines:
            sig_lines.append(line)
            if "{" in line:
                break
        sig = "\n".join(sig_lines).rstrip(" {").rstrip()
        return f"// === HELPER: {symbol.name} ({loc}) [signature only] ===\n{sig};"
    return f"// === HELPER: {symbol.name} ({loc}) ===\n{symbol.text}"


def _make_item_id(symbol: Symbol) -> str:
    """Create a deterministic item ID for the items list."""
    loc = f"{symbol.file}:{symbol.start_line}-{symbol.end_line}"
    return f"{symbol.kind}:{symbol.name}@{loc}"


def _truncate_at_line_boundary(text: str, max_tokens: int, counter: TokenCounter) -> str:
    """Truncate text from the end at a line boundary.

    Appends ``// [truncated]`` marker. Ensures the result fits within
    max_tokens (including the marker).
    """
    marker = "\n// [truncated]"
    marker_tokens = counter.count(marker)
    available = max_tokens - marker_tokens

    if available <= 0:
        return "// [truncated]"

    lines = text.split("\n")
    result_lines: list[str] = []

    for line in lines:
        candidate = "\n".join(result_lines + [line])
        candidate_tokens = counter.count(candidate)
        if candidate_tokens > available:
            break
        result_lines.append(line)

    if not result_lines:
        # Even one line exceeds budget — include as much of the first line
        # as we can (rare edge case)
        return lines[0][:100] + marker

    return "\n".join(result_lines) + marker


# ---------------------------------------------------------------------------
# Slot resolver protocol (design.md §5 / PRD 3.6)
# ---------------------------------------------------------------------------


class SlotResolver(Protocol):
    """Resolves a slot_id to a target function Symbol and its file symbols.

    P2 will provide a real implementation; for now we use PathResolver.
    """

    def resolve(self, slot_id: str) -> tuple[Symbol, list[Symbol]]:
        """Return (target_function, all_symbols_in_same_file)."""
        ...


class PathResolver:
    """Resolve slot_id as ``function_name@file_path``.

    For development and testing before P2's slot format is available.

    Example slot_id: ``"process_record@tests/fixtures/simple.c"``
    """

    def resolve(self, slot_id: str) -> tuple[Symbol, list[Symbol]]:
        """Parse slot_id and extract symbols from the file."""
        from originscan.context.parser import parse_file

        if "@" not in slot_id:
            raise ValueError(
                f"PathResolver expects slot_id as 'function_name@file_path', "
                f"got: {slot_id!r}"
            )

        func_name, file_path = slot_id.split("@", 1)
        all_symbols = parse_file(file_path)

        target = None
        for s in all_symbols:
            if s.kind == "function" and s.name == func_name:
                target = s
                break

        if target is None:
            available = [s.name for s in all_symbols if s.kind == "function"]
            raise ValueError(
                f"Function '{func_name}' not found in {file_path}. "
                f"Available: {available}"
            )

        return target, all_symbols


# ---------------------------------------------------------------------------
# L1 builder
# ---------------------------------------------------------------------------


def build_l1(
    target: Symbol,
    counter: TokenCounter,
    cap: int,
) -> Context:
    """Build L1 context: target function only.

    If the function exceeds the cap, it is truncated from the end at a
    line boundary with ``// [truncated]`` appended.
    """
    formatted = _format_target(target)
    tokens = counter.count(formatted)

    if tokens <= cap:
        return Context(
            text=formatted,
            tokens=tokens,
            items=[_make_item_id(target)],
        )

    # Truncate the function body
    truncated = _truncate_at_line_boundary(formatted, cap, counter)
    truncated_tokens = counter.count(truncated)
    item_id = _make_item_id(target) + "[truncated]"

    return Context(
        text=truncated,
        tokens=truncated_tokens,
        items=[item_id],
    )


# ---------------------------------------------------------------------------
# L2 builder
# ---------------------------------------------------------------------------


def build_l2(
    target: Symbol,
    file_symbols: list[Symbol],
    counter: TokenCounter,
    cap: int,
    per_item_limit: int = 1500,
) -> Context:
    """Build L2 context: L1 + selected same-file context.

    Priority order (design.md §5):
      1. Target function (always included first)
      2. Types (structs, typedefs, enums) referenced by the function
      3. Macros referenced by the function
      4. Globals referenced by the function
      5. Helper functions called by the target (full or signature-only)

    "Referenced" means the symbol's name appears as an identifier in the
    function's tree-sitter tokens.
    """
    # Start with L1
    target_text = _format_target(target)
    target_tokens = counter.count(target_text)

    # If target alone exceeds cap, fall back to truncated L1
    if target_tokens > cap:
        return build_l1(target, counter, cap)

    # Detect which identifiers and calls the function uses
    is_cpp = any(
        target.file.endswith(ext) for ext in (".cpp", ".cc", ".cxx", ".hpp", ".hh")
    )
    referenced_ids = _extract_identifiers_from_source(target.text, is_cpp)
    called_names = _extract_call_names(target.text, is_cpp)

    # Categorize same-file symbols (excluding the target itself)
    types: list[Symbol] = []
    macros: list[Symbol] = []
    globals_: list[Symbol] = []
    helpers: list[Symbol] = []

    for sym in file_symbols:
        if sym == target:
            continue

        if sym.kind in ("struct", "union", "enum", "typedef"):
            if sym.name in referenced_ids:
                types.append(sym)
        elif sym.kind == "macro":
            if sym.name in referenced_ids:
                macros.append(sym)
        elif sym.kind == "global":
            if sym.name in referenced_ids:
                globals_.append(sym)
        elif sym.kind == "function" and sym.name in called_names:
            helpers.append(sym)

    # Sort each group deterministically by (start_line, name)
    for group in (types, macros, globals_, helpers):
        group.sort(key=lambda s: (s.start_line, s.name))

    # Assemble candidates in priority order
    assembled_text = target_text
    assembled_tokens = target_tokens
    items: list[str] = [_make_item_id(target)]

    # 1. Types
    if types:
        type_texts: list[str] = []
        for sym in types:
            sym_text = sym.text
            sym_tokens = counter.count(sym_text)
            if assembled_tokens + sym_tokens + 5 <= cap:  # +5 for delimiter
                type_texts.append(sym_text)
                assembled_tokens += sym_tokens + 5
                items.append(_make_item_id(sym))
        if type_texts:
            section = _format_file_context("types", "\n".join(type_texts))
            # Recalculate exact token count with formatting
            assembled_text = assembled_text + "\n" + section
            assembled_tokens = counter.count(assembled_text)

    # 2. Macros
    if macros:
        macro_texts: list[str] = []
        for sym in macros:
            sym_text = sym.text
            sym_tokens = counter.count(sym_text)
            if assembled_tokens + sym_tokens + 5 <= cap:
                macro_texts.append(sym_text)
                assembled_tokens += sym_tokens + 5
                items.append(_make_item_id(sym))
        if macro_texts:
            section = _format_file_context("macros", "\n".join(macro_texts))
            assembled_text = assembled_text + "\n" + section
            assembled_tokens = counter.count(assembled_text)

    # 3. Globals
    if globals_:
        global_texts: list[str] = []
        for sym in globals_:
            sym_text = sym.text
            sym_tokens = counter.count(sym_text)
            if assembled_tokens + sym_tokens + 5 <= cap:
                global_texts.append(sym_text)
                assembled_tokens += sym_tokens + 5
                items.append(_make_item_id(sym))
        if global_texts:
            section = _format_file_context("globals", "\n".join(global_texts))
            assembled_text = assembled_text + "\n" + section
            assembled_tokens = counter.count(assembled_text)

    # 4. Helpers (called functions in the same file)
    for sym in helpers:
        sym_tokens = counter.count(sym.text)
        # If the helper is small enough, include full text
        if sym_tokens <= per_item_limit:
            formatted_helper = _format_helper(sym, signature_only=False)
        else:
            formatted_helper = _format_helper(sym, signature_only=True)

        helper_tokens = counter.count(formatted_helper)
        if assembled_tokens + helper_tokens + 1 <= cap:
            assembled_text = assembled_text + "\n" + formatted_helper
            assembled_tokens = counter.count(assembled_text)
            items.append(_make_item_id(sym))

    # Final exact token count (not estimated)
    final_tokens = counter.count(assembled_text)

    return Context(
        text=assembled_text,
        tokens=final_tokens,
        items=items,
    )


# ---------------------------------------------------------------------------
# L3 builder
# ---------------------------------------------------------------------------


def build_l3(
    target: Symbol,
    file_symbols: list[Symbol],
    counter: TokenCounter,
    cap: int,
    per_item_limit: int = 1500,
    graph: CallGraph | None = None,
    index: RepoIndex | None = None,
    hops_max: int = 2,
) -> Context:
    """Build L3 context: L2 + repo-slice callers/callees.

    After L2 items (design.md §5):
      1. Callees (hop 1) from other files: signature + body up to per_item_limit
      2. Callers (hop 1): call-site function, trimmed to window around call
      3. Types referenced by those callers/callees
      4. Hop 2 callers/callees if budget remains
      - Ambiguous edges included last and labelled ``// [ambiguous match]``
    """
    if graph is None or index is None:
        # Fall back to L2 if no call graph available
        logger.warning("L3 requested but no call graph; falling back to L2")
        return build_l2(target, file_symbols, counter, cap, per_item_limit)

    # Start with L2 content
    l2_ctx = build_l2(target, file_symbols, counter, cap, per_item_limit)
    assembled_text = l2_ctx["text"]
    assembled_tokens = l2_ctx["tokens"]
    items = list(l2_ctx["items"])

    fn_id = graph.fn_id_for(target)

    # Collect cross-file callees and callers
    # Separate non-ambiguous (priority) from ambiguous (included last)
    callee_edges = graph.callees(fn_id, hops=1)
    caller_edges = graph.callers(fn_id, hops=1)

    non_ambiguous_callees = [e for e in callee_edges if not e.ambiguous]
    non_ambiguous_callers = [e for e in caller_edges if not e.ambiguous]
    ambiguous_callees = [e for e in callee_edges if e.ambiguous]
    ambiguous_callers = [e for e in caller_edges if e.ambiguous]

    # Helper to add a cross-file symbol to the context
    def _try_add_symbol(
        sym: Symbol, label: str, is_ambiguous: bool = False
    ) -> bool:
        nonlocal assembled_text, assembled_tokens

        # Skip if already included (same-file items from L2)
        sym_item_id = _make_item_id(sym)
        if sym_item_id in items:
            return False

        # Format the symbol
        loc = f"{sym.file}:{sym.start_line}-{sym.end_line}"
        ambig_tag = " [ambiguous match]" if is_ambiguous else ""

        sym_tokens = counter.count(sym.text)
        if sym_tokens > per_item_limit:
            # Trim to signature only for large functions
            sig_lines: list[str] = []
            for line in sym.text.split("\n"):
                sig_lines.append(line)
                if "{" in line:
                    break
            sig = "\n".join(sig_lines).rstrip(" {").rstrip()
            formatted = (
                f"// === {label}: {sym.name} ({loc})"
                f"{ambig_tag} [signature only] ===\n{sig};"
            )
        else:
            formatted = f"// === {label}: {sym.name} ({loc}){ambig_tag} ===\n{sym.text}"

        formatted_tokens = counter.count(formatted)
        if assembled_tokens + formatted_tokens + 1 > cap:
            return False

        assembled_text = assembled_text + "\n" + formatted
        assembled_tokens = counter.count(assembled_text)
        items.append(sym_item_id)
        return True

    # 1. Non-ambiguous callees (hop 1)
    for edge in non_ambiguous_callees:
        sym = graph.get_symbol(edge.callee)
        if sym and sym.file != target.file:
            _try_add_symbol(sym, "CALLEE")

    # 2. Non-ambiguous callers (hop 1)
    for edge in non_ambiguous_callers:
        sym = graph.get_symbol(edge.caller)
        if sym and sym.file != target.file:
            _try_add_symbol(sym, "CALLER")

    # 3. Hop 2 if budget remains
    if hops_max >= 2 and assembled_tokens < cap:
        hop2_callees = graph.callees(fn_id, hops=2)
        hop2_callers = graph.callers(fn_id, hops=2)

        # Only include hop-2 edges not already seen in hop 1
        hop1_ids = {e.callee for e in callee_edges} | {e.caller for e in caller_edges}

        for edge in hop2_callees:
            if edge.callee not in hop1_ids and not edge.ambiguous:
                sym = graph.get_symbol(edge.callee)
                if sym:
                    _try_add_symbol(sym, "CALLEE (hop 2)")

        for edge in hop2_callers:
            if edge.caller not in hop1_ids and not edge.ambiguous:
                sym = graph.get_symbol(edge.caller)
                if sym:
                    _try_add_symbol(sym, "CALLER (hop 2)")

    # 4. Ambiguous edges last
    for edge in ambiguous_callees:
        sym = graph.get_symbol(edge.callee)
        if sym and sym.file != target.file:
            _try_add_symbol(sym, "CALLEE", is_ambiguous=True)

    for edge in ambiguous_callers:
        sym = graph.get_symbol(edge.caller)
        if sym and sym.file != target.file:
            _try_add_symbol(sym, "CALLER", is_ambiguous=True)

    final_tokens = counter.count(assembled_text)

    return Context(
        text=assembled_text,
        tokens=final_tokens,
        items=items,
    )


# ---------------------------------------------------------------------------
# Top-level build_context
# ---------------------------------------------------------------------------


def build_context(
    slot_id: str,
    level: Level,
    resolver: SlotResolver | None = None,
    counter: TokenCounter | None = None,
    cap: int | None = None,
    per_item_limit: int = 1500,
    caps: dict[str, int] | None = None,
    graph: CallGraph | None = None,
    index: RepoIndex | None = None,
    hops_max: int = 2,
) -> Context:
    """Build detector-ready context for a function at a given level.

    This is the main entry point used by both P5's experiment runner
    and the CLI.

    Args:
        slot_id: Function identifier (format depends on the resolver).
        level: Context depth — ``"L1"``, ``"L2"``, or ``"L3"``.
        resolver: SlotResolver to look up the target function.
                  Defaults to PathResolver.
        counter: Token counter. Defaults to tiktoken cl100k_base.
        cap: Override the token cap for this call.
        per_item_limit: Max tokens per individual included item (L2+).
        caps: Dict of level -> cap overrides (e.g. from config).
        graph: CallGraph for L3 (optional; L3 falls back to L2 without it).
        index: RepoIndex for L3 (optional).
        hops_max: Max call-graph hops for L3.

    Returns:
        Context with text, token count, and included items list.
    """
    if resolver is None:
        resolver = PathResolver()
    if counter is None:
        counter = create_counter()

    # Resolve caps
    default_caps: dict[str, int] = {"L1": 2000, "L2": 6000, "L3": 15000}
    if caps:
        default_caps.update(caps)
    effective_cap = cap if cap is not None else default_caps[level]

    # Resolve target
    target, file_symbols = resolver.resolve(slot_id)

    if level == "L1":
        return build_l1(target, counter, effective_cap)
    elif level == "L2":
        return build_l2(target, file_symbols, counter, effective_cap, per_item_limit)
    elif level == "L3":
        return build_l3(
            target, file_symbols, counter, effective_cap, per_item_limit,
            graph=graph, index=index, hops_max=hops_max,
        )
    else:
        raise ValueError(f"Unknown level: {level!r}")

