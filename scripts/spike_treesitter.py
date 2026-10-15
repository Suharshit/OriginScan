"""Spike script — Phase 1 task 1.6.

Parse a small C file with tree-sitter, extract functions, and list
callers/callees by name. This validates that tree-sitter works and
that we can extract the data needed for the context builder.

Usage:
    python scripts/spike_treesitter.py [path_to_c_file]

If no file is provided, uses a built-in sample.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

C_LANGUAGE = Language(tsc.language())


def create_parser() -> Parser:
    """Create a tree-sitter parser for C."""
    parser = Parser(C_LANGUAGE)
    return parser


# ---------------------------------------------------------------------------
# Sample C code (used when no file is provided)
# ---------------------------------------------------------------------------

SAMPLE_C = """\
#include <stdio.h>
#include <stdlib.h>

#define MAX_SIZE 1024

typedef struct {
    int x;
    int y;
} Point;

static int helper_add(int a, int b) {
    return a + b;
}

int compute_distance(Point* p1, Point* p2) {
    int dx = helper_add(p1->x, -(p2->x));
    int dy = helper_add(p1->y, -(p2->y));
    return dx * dx + dy * dy;
}

void print_point(Point* p) {
    printf("Point(%d, %d)\\n", p->x, p->y);
}

int main(int argc, char* argv[]) {
    Point a = {1, 2};
    Point b = {4, 6};

    print_point(&a);
    print_point(&b);

    int dist = compute_distance(&a, &b);
    printf("Distance squared: %d\\n", dist);

    return 0;
}
"""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_functions(tree_root: Node, source: bytes) -> list[dict[str, object]]:
    """Extract all function definitions from a tree-sitter parse tree."""
    functions: list[dict[str, object]] = []

    def visit(node: Node) -> None:
        if node.type == "function_definition":
            # Get the declarator to find the function name
            declarator = node.child_by_field_name("declarator")
            name = _find_identifier(declarator) if declarator else "<unknown>"

            # Check if static
            is_static = False
            for child in node.children:
                if child.type == "storage_class_specifier" and child.text == b"static":
                    is_static = True
                    break

            functions.append({
                "name": name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "is_static": is_static,
                "text": source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            })

        for child in node.children:
            visit(child)

    visit(tree_root)
    return functions


def _find_identifier(node: Node | None) -> str:
    """Recursively find the identifier name in a declarator."""
    if node is None:
        return "<unknown>"
    if node.type == "identifier":
        return node.text.decode("utf-8") if node.text else "<unknown>"
    # For function_declarator, look at the first child (the name)
    if node.type == "function_declarator":
        child = node.child_by_field_name("declarator")
        if child:
            return _find_identifier(child)
    # For pointer_declarator, look inside
    if node.type == "pointer_declarator":
        for child in node.children:
            result = _find_identifier(child)
            if result != "<unknown>":
                return result
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8") if child.text else "<unknown>"
    return "<unknown>"


def extract_call_expressions(func_node: Node, source: bytes) -> list[str]:
    """Extract function call names from within a function body."""
    calls: list[str] = []

    def visit(node: Node) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                if func.type == "identifier":
                    name = func.text.decode("utf-8") if func.text else None
                    if name:
                        calls.append(name)
                elif func.type == "field_expression":
                    # a->b() or a.b()
                    field = func.child_by_field_name("field")
                    if field and field.text:
                        calls.append(f".{field.text.decode('utf-8')}  [member call]")

        for child in node.children:
            visit(child)

    visit(func_node)
    return calls


def extract_types(tree_root: Node, source: bytes) -> list[dict[str, str]]:
    """Extract struct/union/enum/typedef definitions."""
    types: list[dict[str, str]] = []

    def visit(node: Node) -> None:
        if node.type == "type_definition":
            # typedef ... Name;
            text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            # Find the typedef name (last identifier before semicolon)
            name = "<unknown>"
            for child in node.children:
                if child.type == "type_identifier":
                    name = child.text.decode("utf-8") if child.text else "<unknown>"
            types.append({"kind": "typedef", "name": name, "text": text})

        elif node.type in ("struct_specifier", "union_specifier", "enum_specifier"):
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node and name_node.text else "<anon>"
            kind = node.type.replace("_specifier", "")
            text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            # Only include if it has a body (not just a forward reference)
            body = node.child_by_field_name("body")
            if body:
                types.append({"kind": kind, "name": name, "text": text})

        elif node.type in ("preproc_def", "preproc_function_def"):
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node and name_node.text else "<unknown>"
            text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            types.append({"kind": "macro", "name": name, "text": text})

        for child in node.children:
            visit(child)

    visit(tree_root)
    return types


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = create_parser()

    # Load source
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"Error: file not found: {file_path}")
            sys.exit(1)
        source = file_path.read_bytes()
        print(f"=== Parsing: {file_path} ===\n")
    else:
        source = SAMPLE_C.encode("utf-8")
        print("=== Parsing: built-in sample ===\n")

    tree = parser.parse(source)

    # Check for errors
    has_errors = False

    def check_errors(node: Node) -> None:
        nonlocal has_errors
        if node.type == "ERROR":
            has_errors = True
            print(f"  [!] Parse error at line {node.start_point[0] + 1}")
        for child in node.children:
            check_errors(child)

    check_errors(tree.root_node)
    if has_errors:
        print("  (Continuing with partial results — error tolerance test)\n")
    else:
        print("  [OK] No parse errors\n")

    # Extract types
    types = extract_types(tree.root_node, source)
    print(f"--- Types/Macros ({len(types)}) ---")
    for t in types:
        print(f"  [{t['kind']}] {t['name']}")
    print()

    # Extract functions
    functions = extract_functions(tree.root_node, source)
    print(f"--- Functions ({len(functions)}) ---")
    for func in functions:
        static_tag = " [static]" if func["is_static"] else ""
        print(f"  {func['name']}{static_tag}  (lines {func['start_line']}-{func['end_line']})")

    # Build caller/callee map
    print("\n--- Call Graph ---")

    # Re-parse to get function nodes for call extraction
    func_nodes: list[tuple[str, Node]] = []

    def collect_func_nodes(node: Node) -> None:
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            name = _find_identifier(declarator) if declarator else "<unknown>"
            func_nodes.append((name, node))
        for child in node.children:
            collect_func_nodes(child)

    collect_func_nodes(tree.root_node)

    callee_map: dict[str, list[str]] = {}
    for name, node in func_nodes:
        calls = extract_call_expressions(node, source)
        callee_map[name] = calls

    # Build caller map (inverse)
    all_func_names = {f["name"] for f in functions}
    caller_map: dict[str, list[str]] = {name: [] for name in all_func_names}
    for caller, callees in callee_map.items():
        for callee in callees:
            clean_name = callee.split("[")[0].strip().lstrip(".")
            if clean_name in caller_map:
                caller_map[clean_name].append(caller)

    for name, node in func_nodes:
        calls = callee_map.get(name, [])
        callers = caller_map.get(name, [])
        print(f"\n  {name}:")
        print(f"    calls:     {calls if calls else '(none)'}")
        print(f"    called by: {callers if callers else '(none)'}")

    print("\n=== Spike complete ===")
    print(f"  Functions: {len(functions)}")
    print(f"  Types:     {len(types)}")
    print(f"  Edges:     {sum(len(v) for v in callee_map.values())}")


if __name__ == "__main__":
    main()
