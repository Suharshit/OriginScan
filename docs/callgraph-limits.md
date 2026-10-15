# Call Graph Limitations

> Documents known limits of the approximate call graph (PRD task 4.9).
> These are inherent to name-based resolution without a compiler.

## What Works

- **Direct function calls:** `foo()` resolved by name.
- **Static functions:** resolved correctly within the same file.
- **Cross-file calls:** resolved using the ambiguity rule (same file > same dir > anywhere).
- **Ambiguity detection:** flagged on edges when resolution is not unique.
- **BFS traversal:** callers/callees up to N hops with deterministic ordering.

## What Doesn't Work (Known Limits)

| Limitation | Example | Impact |
|---|---|---|
| **Function pointers** | `void (*fp)(int) = &foo; fp(42);` | Call not detected |
| **Callbacks** | `register_handler(on_event);` | `on_event` not linked to caller |
| **Macro-generated calls** | `CALL_MACRO(foo)` expands to `foo()` | Call hidden inside macro |
| **C++ overload resolution** | `void f(int)` vs `void f(double)` | Wrong overload may be chosen |
| **C++ virtual dispatch** | `base->method()` | Resolved to base class only |
| **Same-named statics** | `static void helper()` in multiple files | Ambiguity rule picks one |
| **Indirect calls via structs** | `table->ops->read()` | Member call, not resolved |

## Ambiguity Rule

When multiple functions share a name, resolution follows this priority:

1. **Same file** as the caller
2. **Same directory** as the caller
3. **Unique match** anywhere in the repo
4. **Multiple matches**: prefer non-static, then shortest path distance from caller, then lexicographic path order

Ambiguous resolutions are flagged with `ambiguous=True` on the edge and
appear **last** in L3 context, labelled `// [ambiguous match]`.

## Unresolved Calls

External calls (libc, system libraries, third-party functions) are
recorded in `CallGraph.unresolved` but not included in context. This
is expected and correct — the context builder only includes code from
the indexed repository.

## Mitigation

- Every context returns an `items` list showing exactly what was included.
- Ambiguous edges are labelled, never silently included.
- These limits are documented in reports for transparency.
- The call graph is an approximation; it improves context but does not
  guarantee completeness.
