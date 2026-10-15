"""C/C++ source parser using tree-sitter.

Extracts Symbol objects (functions, structs, unions, enums, typedefs,
globals, macros) from source files. Tolerates parse errors gracefully.

See design.md §3.

Public API:
    parse_file(path)           -> list[Symbol]
    parse_source(src, lang)    -> list[Symbol]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

C_LANGUAGE = Language(tsc.language())
CPP_LANGUAGE = Language(tscpp.language())

# Extension → language mapping (design.md §3)
_EXT_TO_LANG: dict[str, Language] = {
    ".c": C_LANGUAGE,
    ".h": C_LANGUAGE,
    ".cc": CPP_LANGUAGE,
    ".cpp": CPP_LANGUAGE,
    ".cxx": CPP_LANGUAGE,
    ".hpp": CPP_LANGUAGE,
    ".hh": CPP_LANGUAGE,
    ".hxx": CPP_LANGUAGE,
}

SymbolKind = Literal[
    "function", "struct", "union", "enum", "typedef", "global", "macro"
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """A code symbol extracted from a source file.

    See design.md §3 for the specification.
    """

    kind: SymbolKind
    name: str
    file: str
    start_line: int
    end_line: int
    text: str
    is_static: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_identifier(node: Node | None) -> str:
    """Recursively find the identifier name in a declarator node."""
    if node is None:
        return "<unknown>"

    if node.type == "identifier":
        return node.text.decode("utf-8") if node.text else "<unknown>"

    if node.type == "qualified_identifier":
        # C++: A::B::func — return the full qualified name
        return node.text.decode("utf-8") if node.text else "<unknown>"

    if node.type == "field_identifier":
        return node.text.decode("utf-8") if node.text else "<unknown>"

    if node.type == "destructor_name":
        return node.text.decode("utf-8") if node.text else "<unknown>"

    if node.type == "operator_name":
        return node.text.decode("utf-8") if node.text else "<unknown>"

    if node.type == "function_declarator":
        child = node.child_by_field_name("declarator")
        if child:
            return _find_identifier(child)

    if node.type == "pointer_declarator":
        for child in node.children:
            result = _find_identifier(child)
            if result != "<unknown>":
                return result

    if node.type == "parenthesized_declarator":
        for child in node.children:
            result = _find_identifier(child)
            if result != "<unknown>":
                return result

    if node.type == "reference_declarator":
        for child in node.children:
            result = _find_identifier(child)
            if result != "<unknown>":
                return result

    # Generic fallback: look for the first identifier child
    for child in node.children:
        if child.type in ("identifier", "qualified_identifier", "field_identifier"):
            return child.text.decode("utf-8") if child.text else "<unknown>"

    return "<unknown>"


def _is_static(node: Node) -> bool:
    """Check if a node has a 'static' storage class specifier."""
    for child in node.children:
        if child.type == "storage_class_specifier" and child.text == b"static":
            return True
    return False


def _node_text(node: Node, source: bytes) -> str:
    """Extract the text of a node from the source."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _check_errors(root: Node, file_path: str) -> bool:
    """Walk the tree and log warnings for ERROR nodes.

    Returns True if any errors were found.
    """
    has_errors = False

    def visit(node: Node) -> None:
        nonlocal has_errors
        if node.type == "ERROR":
            has_errors = True
            line = node.start_point[0] + 1
            logger.warning(
                "Parse error in %s at line %d (continuing with partial results)",
                file_path,
                line,
            )
        for child in node.children:
            visit(child)

    visit(root)
    return has_errors


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


def _extract_functions(root: Node, source: bytes, file_path: str) -> list[Symbol]:
    """Extract function definitions."""
    symbols: list[Symbol] = []

    def visit(node: Node) -> None:
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            name = _find_identifier(declarator)
            static = _is_static(node)

            symbols.append(Symbol(
                kind="function",
                name=name,
                file=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                text=_node_text(node, source),
                is_static=static,
            ))
            # Don't recurse into nested functions (C doesn't have them,
            # but we guard against it)
            return

        for child in node.children:
            visit(child)

    visit(root)
    return symbols


def _extract_types(root: Node, source: bytes, file_path: str) -> list[Symbol]:
    """Extract struct, union, enum, and typedef definitions."""
    symbols: list[Symbol] = []

    def visit(node: Node) -> None:
        if node.type == "type_definition":
            # typedef ... Name;
            name = "<unknown>"
            for child in node.children:
                if child.type == "type_identifier":
                    name = child.text.decode("utf-8") if child.text else "<unknown>"
            symbols.append(Symbol(
                kind="typedef",
                name=name,
                file=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                text=_node_text(node, source),
            ))
            return

        if node.type in ("struct_specifier", "union_specifier", "enum_specifier"):
            kind_map = {
                "struct_specifier": "struct",
                "union_specifier": "union",
                "enum_specifier": "enum",
            }
            kind = kind_map[node.type]
            name_node = node.child_by_field_name("name")
            name = (
                name_node.text.decode("utf-8")
                if name_node and name_node.text
                else "<anon>"
            )
            # Only include if it has a body (not just a forward declaration)
            body = node.child_by_field_name("body")
            if body:
                # Check if this is inside a typedef — if so, skip to avoid
                # duplication (the typedef visitor handles it)
                parent = node.parent
                if parent and parent.type == "type_definition":
                    pass  # Let the typedef handler cover it
                else:
                    symbols.append(Symbol(
                        kind=kind,  # type: ignore[arg-type]
                        name=name,
                        file=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        text=_node_text(node, source),
                    ))

        # C++ class_specifier
        if node.type == "class_specifier":
            name_node = node.child_by_field_name("name")
            name = (
                name_node.text.decode("utf-8")
                if name_node and name_node.text
                else "<anon>"
            )
            body = node.child_by_field_name("body")
            if body:
                parent = node.parent
                if not (parent and parent.type == "type_definition"):
                    symbols.append(Symbol(
                        kind="struct",  # Treat C++ classes as structs
                        name=name,
                        file=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        text=_node_text(node, source),
                    ))

        for child in node.children:
            visit(child)

    visit(root)
    return symbols


def _extract_macros(root: Node, source: bytes, file_path: str) -> list[Symbol]:
    """Extract preprocessor macro definitions."""
    symbols: list[Symbol] = []

    def visit(node: Node) -> None:
        if node.type in ("preproc_def", "preproc_function_def"):
            name_node = node.child_by_field_name("name")
            name = (
                name_node.text.decode("utf-8")
                if name_node and name_node.text
                else "<unknown>"
            )
            symbols.append(Symbol(
                kind="macro",
                name=name,
                file=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                text=_node_text(node, source),
            ))
            return

        for child in node.children:
            visit(child)

    visit(root)
    return symbols


def _extract_globals(root: Node, source: bytes, file_path: str) -> list[Symbol]:
    """Extract top-level global variable declarations."""
    symbols: list[Symbol] = []

    for child in root.children:
        if child.type == "declaration":
            # Skip if it looks like a function declaration (has a
            # function_declarator descendant without a body)
            has_func_decl = False

            def _check_func_decl(n: Node) -> None:
                nonlocal has_func_decl
                if n.type == "function_declarator":
                    has_func_decl = True
                for c in n.children:
                    _check_func_decl(c)

            _check_func_decl(child)
            if has_func_decl:
                continue

            # Extract the variable name from the declarator
            declarator = child.child_by_field_name("declarator")
            name = _find_identifier(declarator) if declarator else "<unknown>"
            static = _is_static(child)

            symbols.append(Symbol(
                kind="global",
                name=name,
                file=file_path,
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                text=_node_text(child, source),
                is_static=static,
            ))

    return symbols


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_language(path: Path) -> Language | None:
    """Detect the tree-sitter Language from a file extension.

    Returns None if the extension is not recognized.
    """
    return _EXT_TO_LANG.get(path.suffix.lower())


def parse_source(
    src: str | bytes,
    lang: Language,
    file_path: str = "<source>",
) -> list[Symbol]:
    """Parse source code and extract symbols.

    Args:
        src: Source code as a string or bytes.
        lang: tree-sitter Language to use.
        file_path: File path for Symbol.file (for identification only).

    Returns:
        List of extracted Symbol objects, ordered by start_line.
    """
    source = src.encode("utf-8") if isinstance(src, str) else src

    parser = Parser(lang)
    tree = parser.parse(source)

    # Check for parse errors (log but don't crash — FR-4)
    _check_errors(tree.root_node, file_path)

    # Extract all symbol types
    symbols: list[Symbol] = []
    symbols.extend(_extract_functions(tree.root_node, source, file_path))
    symbols.extend(_extract_types(tree.root_node, source, file_path))
    symbols.extend(_extract_macros(tree.root_node, source, file_path))
    symbols.extend(_extract_globals(tree.root_node, source, file_path))

    # Sort by start_line for deterministic output (design.md §0 rule 4)
    symbols.sort(key=lambda s: (s.start_line, s.name))

    return symbols


def parse_file(path: str | Path) -> list[Symbol]:
    """Parse a source file and extract symbols.

    Args:
        path: Path to a C or C++ source file.

    Returns:
        List of extracted Symbol objects.

    Raises:
        ValueError: If the file extension is not recognized.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    lang = detect_language(path)
    if lang is None:
        raise ValueError(
            f"Unrecognized file extension '{path.suffix}' for {path}. "
            f"Supported: {', '.join(sorted(_EXT_TO_LANG.keys()))}"
        )

    source = path.read_bytes()
    # Use a POSIX-style relative path for Symbol.file (determinism)
    file_str = path.as_posix()

    return parse_source(source, lang, file_str)
