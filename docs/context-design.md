# Context Design — OriginScan P4

> Gate 1 deliverable (PRD task 2.7). Defines what goes into each context
> level, the priority order, proposed caps, and known limitations.
> Share with P5 for review.

## 1. Levels at a Glance

| Level | Contents | Target use |
|---|---|---|
| **L1 — Function** | Target function only | Baseline; lowest cost |
| **L2 — File** | L1 + selected same-file types, macros, globals, helpers | Adds local context |
| **L3 — Repo slice** | L2 + 1-2 hop callers/callees + referenced types across files | Full neighbourhood |

## 2. Priority Order (what gets included first)

Each level assembles an **ordered list of candidate items**. Items are added
in priority order until the token cap is reached.

### L1
1. Target function body (always included; truncated from end if over cap)

### L2 (after L1)
1. Types (structs, typedefs, enums) referenced by the function — same file
2. Macros referenced by the function — same file
3. Globals referenced by the function — same file
4. Same-file helper functions called by the target (full body if small, signature-only if large)

### L3 (after L2)
1. Callees (hop 1) from other files — signature + body up to per-item limit
2. Callers (hop 1) — call-site function trimmed to a window around the call
3. Types referenced by those callers/callees
4. Hop 2 callers/callees if budget remains
5. Ambiguous edges included **last**, labelled `// [ambiguous match]`

## 3. "Referenced" Definition

An item is **referenced** by a function if its identifier appears in the
function's tree-sitter token stream. This is identifier-level matching on the
parsed tree, **not** substring search on source text.

## 4. Proposed Token Caps

| Level | Provisional cap | Planning average (from overview) |
|---|---|---|
| L1 | 2,000 | ~1,500 |
| L2 | 6,000 | ~5,000 |
| L3 | 15,000 | ~12,000 |

- Caps are **hard limits**: `ctx["tokens"] <= cap[level]` is a tested invariant.
- Planning averages are averages across the benchmark, not caps.
- Per-item limit: 1,500 tokens (for individual callees, callers, etc.)
- **Action needed:** confirm with P5 after running on pilot slots.

## 5. Truncation Rules

1. Target function **always** appears first and is never dropped.
2. If the target function alone exceeds the cap, truncate its body from the
   end at a line boundary and append `// [truncated]`.
3. Other items are skipped (not truncated) if they don't fit.
4. Large helper functions in L2 are reduced to signature-only.

## 6. Output Format

```
// === TARGET FUNCTION (src/a.c:10-42) ===
<function body>
// === FILE CONTEXT: types ===
<struct/typedef/enum definitions>
// === FILE CONTEXT: macros ===
<macro definitions>
// === CALLER: foo (src/b.c:100-130) ===
<caller snippet>
```

Each context returns:
- `text`: the formatted block above
- `tokens`: count of tokens in `text`
- `items`: list of element IDs included (e.g. `"func:foo@src/a.c:10-42"`)

## 7. Known Limitations

- **Call graph is approximate:** name-based resolution only; function pointers,
  macro-generated calls, C++ overloads/virtual dispatch are not resolved.
- **Preprocessor:** `#ifdef` branches are all visible to tree-sitter (no
  preprocessor execution), so some symbols may be from inactive branches.
- **Token counts are approximate:** tiktoken cl100k_base may not match the
  target model's tokenizer exactly.
- **No semantic analysis:** reference detection uses identifier matching,
  not type checking.

## 8. Tokenizer

Default: **tiktoken cl100k_base**. Pluggable via `TokenCounter` protocol.
The tokenizer name is recorded in every run's metadata for reproducibility.
A whitespace-based fallback is available for environments without tiktoken.

## 9. Open Questions for P5

1. Are the proposed caps (2k/6k/15k) appropriate for the planned models?
2. Should per-item limit differ between callers and callees?
3. Any preference on tie-breaking when multiple items compete for the last slot?
