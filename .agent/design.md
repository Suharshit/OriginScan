# Design — OriginScan P4: Context Builder & Tool

> Companion to `prd.md` and `architecture.md`. This file defines *how each component behaves*: algorithms, interfaces, config, CLI UX, report format, and testing. Written so an AI coding agent (Antigravity) can implement it module by module.

## 0. Rules for the coding agent

1. Python 3.11. Type hints everywhere; `mypy --strict` clean on `context/`, `provenance/`, `cli/`.
2. Implement **one module at a time** in the build order of §10. Do not start a module until the previous one has passing tests.
3. Never change the public interfaces in §2 without a note in `docs/interface-changes.md` (P2 and P5 depend on them).
4. Everything deterministic: no randomness, no dict-order dependence, no wall-clock in outputs.
5. No network calls in `context/`, `provenance/`. Only `detect/` adapters (not P4) call LLM APIs.
6. API keys come from environment variables only; never log them.
7. Prefer small pure functions. Every function with logic gets a unit test.
8. Do not invent features beyond `prd.md`.

## 1. Design principles

- **Selected context, never dumped.** Naive appending hurts detector accuracy (CPRVul, Lira et al.). Each level *selects* by relevance and obeys a hard token cap.
- **Same code for study and tool.** `build_context` is called identically by P5's runner and the CLI.
- **Approximate but honest.** The call graph is name-based; every context returns `items` so users can see what was included, and ambiguity is documented, not hidden.
- **Fail soft.** Parse errors, missing metadata, unresolved symbols degrade the context; they never crash a scan.

## 2. Core interfaces (frozen Week 1, Day 5)

```python
# interfaces.py
from typing import Literal, TypedDict

Level = Literal["L1", "L2", "L3"]
Origin = Literal["ai", "human", "unknown"]

class Context(TypedDict):
    text: str          # prompt-ready code context
    tokens: int        # token count of `text`
    items: list[str]   # ids of included elements, e.g. "func:foo@src/a.c:10-42"

def build_context(slot_id: str, level: Level) -> Context: ...

# Owned by P5, consumed by P4's CLI through an adapter:
class Finding(TypedDict):
    verdict: bool
    cwe: str | None
    line: int | None
    confidence: float
    input_tokens: int
    output_tokens: int

def detect(ctx: Context, detector: str, run: int) -> Finding: ...
def choose_start(origin: Origin, cwe_family: str | None) -> str: ...  # returns "L1"/"L2"/"L3"
```

`slot_id` example: `libxml2_cve2023_1234_f3` (from overview §6.3). For the CLI path (no slot), use the lower-level API in §4.

## 3. Parsing (`context/parser.py`)

### Data classes
```python
@dataclass(frozen=True)
class Symbol:
    kind: Literal["function","struct","union","enum","typedef","global","macro"]
    name: str
    file: str
    start_line: int
    end_line: int
    text: str
    is_static: bool = False
```

### Behaviour
- Language chosen by extension: `.c`, `.h` → C; `.cc`, `.cpp`, `.cxx`, `.hpp`, `.hh` → C++.
- Walk the tree-sitter tree; collect `function_definition`, `struct_specifier`/`union_specifier`/`enum_specifier` with bodies, `type_definition`, top-level `declaration` (globals), `preproc_def`/`preproc_function_def`.
- Handle C++ qualified names (`A::b`) and methods defined in-class.
- If the tree contains `ERROR` nodes, still extract valid sibling symbols; record a warning.
- `parse_file(path) -> list[Symbol]`, `parse_source(src, lang) -> list[Symbol]` (the latter for tests).

## 4. Repo index and call graph (`context/index.py`, `context/callgraph.py`)

### Index
- `RepoIndex.build(root, commit)` walks source files (skip `build/`, `third_party/`, `vendor/`, configurable globs), parses each, stores symbols by name and by file.
- Persist to `.originscan/index-<commit>.json` (or SQLite). Reload if the commit matches.

### Call extraction
- Within each function body, collect `call_expression` identifiers (plain names; for `a->b()` and `a.b()` record the member name with a flag `member=True`).
- Build `callees[f]` = resolved names; invert for `callers`.

### Name resolution (ambiguity rule, in order)
1. Same file.
2. Same directory.
3. Unique match anywhere in the repo.
4. Multiple matches: prefer non-static; then shortest path distance from the caller's file; then lexicographic path. Record `ambiguous=True` on the edge.
5. No match (libc, external): drop; keep in `unresolved` list.

### Known limits (to document in README and report)
Function pointers, callbacks, macro-generated calls, same-named static functions, C++ overload resolution and virtual dispatch are **not** resolved precisely.

### API
```python
def callees(index, fn_id, hops: int = 1) -> list[str]   # BFS, deterministic order
def callers(index, fn_id, hops: int = 1) -> list[str]
```

## 5. Context builders (`context/builders.py`)

### Common
- `TokenCounter` protocol: `count(text: str) -> int`. Default implementation uses `tiktoken` (`cl100k_base`) as an approximation; recorded in run metadata. Pluggable per model.
- Each level assembles an **ordered list of candidate items**, each with `(priority, text, id)`. Items are added in priority order until the cap would be exceeded; a non-fitting item is skipped (or truncated if it is the target function, see below). Ties break by id.
- Output text uses clear delimiters:

```
// === TARGET FUNCTION (src/a.c:10-42) ===
<code>
// === FILE CONTEXT: types ===
...
// === CALLER: foo (src/b.c:100-130) ===
...
```

### L1
- Candidate: target function only.
- If it alone exceeds the cap: truncate the body from the end at a line boundary and add `// [truncated]`. Record in `items` as `func:...[truncated]`.

### L2 (L1 + same-file)
Priority order after the target:
1. Types referenced by the function (structs, typedefs, enums) in the same file.
2. Macros referenced by name in the function.
3. Globals referenced by name.
4. Same-file helper functions called by the target (full text if small; signature only if large).
- "Referenced" = identifier appears in the function's tokens (simple identifier match from the tree, not substring search).

### L3 (L2 + repo slice)
After L2 items:
1. Callees (hop 1) from other files: signature + body up to a per-item limit.
2. Callers (hop 1): the call-site function, trimmed to a window around the call.
3. Types referenced by those callers/callees.
4. Hop 2 callers/callees if budget remains.
- Ambiguous edges are included last and labelled `// [ambiguous match]`.

### Caps
- Config in `config/context.yaml`:
```yaml
token_caps: {L1: TBD, L2: TBD, L3: TBD}   # fill with values agreed with P5 after the Week 1 pilot
per_item_limit: TBD
hops_max: 2
```
- Planning averages from the overview (1.5k / 5k / 12k tokens) are *averages*, not caps. Choose caps after the Week 1 pilot.
- Hard invariant: `ctx["tokens"] <= cap[level]`. Verified by a property test.

### Caching
Cache `Context` by `(commit, function_id, level, config_hash)`; helps the "cache L3 contexts" cost-saving plan.

## 6. Diff → functions (`context/diff.py`)

- Parse unified diffs (`unidiff` library or a small parser).
- For each changed file, map hunk line ranges (new side) to the function symbols that contain them. Changes outside any function are ignored (optionally reported as "non-function change").
- Deleted-only hunks map to the enclosing function on the old side, flagged `deleted_only`.

## 7. Provenance reader (`provenance/reader.py`)

### Signals
- `Co-authored-by:` trailers matching entries in `config/agents.yaml` (e.g. known AI tool identities).
- Commit author name/email matching known agent bot accounts.
- Tool metadata trailers if present (configurable keys).

### Algorithm
- For each changed function, collect commits touching its changed lines (`git blame`/`git log -L`-style, behind a thin `git.py` wrapper).
- Rule: any matching AI signal on a commit that introduced changed lines → `ai`. All commits have an author and none match → `human`. If history is unavailable or ambiguous (squash with no metadata) → `unknown`.
- Output includes the *evidence* (commit hash, matched rule) for the report.
- `unknown` triggers the confidence-only fallback policy.

## 8. CLI (`cli/main.py`, Typer)

```
originscan scan    --repo PATH --diff FILE|RANGE [--policy policy.yaml] [--budget N]
                   [--out DIR] [--format json,md] [--fail-on-findings]
originscan context --repo PATH --function ID --level L1|L2|L3     # prints Context
originscan index   --repo PATH                                     # builds/refreshes index
```

### `scan` flow
1. Load config, build/load index.
2. Diff → changed functions.
3. Provenance per function.
4. Policy: `choose_start(origin, cwe_family)` if `policy.yaml` is given and origin ≠ unknown; else start at L1 (confidence-only).
5. For each function: build context at the start level → call detectors via the adapter → if confidence is below τ (from policy or default), escalate one level (respect `--budget`).
6. Write reports.

### Detector adapter
```python
class DetectorAdapter(Protocol):
    def run(self, ctx: Context, run: int) -> Finding: ...
```
Provide `FakeDetector` (deterministic, for tests and demo without API keys). Real adapters come from P5 (LLM/RAG) and P3 (static).

## 9. Report generator (`report/`)

### JSON schema (per scan)
```json
{
  "scan_id": "...", "commit": "...", "policy": "origin|confidence-only",
  "functions": [{
    "id": "func:foo@src/a.c:10-42",
    "origin": "ai", "origin_evidence": ["abc123: co-authored-by rule"],
    "levels_tried": ["L1", "L2"], "level_used": "L2",
    "findings": [{"cwe": "CWE-787", "line": 31, "confidence": 0.67, "verdict": true}],
    "input_tokens": 5120, "output_tokens": 210
  }],
  "totals": {"input_tokens": 0, "output_tokens": 0, "budget": null}
}
```

### Markdown (PR comment)
- Header with commit, policy, total tokens.
- Table: function | origin | level used | finding (CWE, line) | confidence | tokens.
- Footer: link to methodology and the line "Research prototype; results may include false positives."
- A hidden marker `<!-- originscan -->` so the Action updates its own comment instead of posting duplicates.

## 10. GitHub Action (`action/`)

- `action.yml` (composite or Docker action) + `.github/workflows/originscan.yml` example:
  - Trigger: `pull_request` (opened, synchronize).
  - Steps: checkout with `fetch-depth: 0`, set up Python 3.11, install package, run `originscan scan --diff origin/${{ github.base_ref }}...HEAD`, post/update comment via the GitHub REST API.
  - Secrets: LLM API keys via `secrets.*`; never echoed.
- Restricted to repositories the team owns or forks (document in README).

## 11. Testing strategy

| Layer | Tests |
|---|---|
| Parser | Fixture C/C++ files: normal funcs, static funcs, macros, typedef structs, `#ifdef` blocks, syntax errors |
| Index/call graph | Small multi-file fixture repo with known edges; ambiguity cases; unresolved externals |
| Builders | Golden-file tests for L1/L2/L3 output; **property test: tokens ≤ cap**; determinism (run twice, compare) |
| Diff mapper | Hunks inside, across, outside functions; deleted-only |
| Provenance | Synthetic git repos with trailers/bot authors/none |
| CLI | `typer.testing.CliRunner` with `FakeDetector` |
| Action | Dry-run mode printing the comment body; manual demo PR in a repo we own |
| Acceptance | Run on **3 real C repos** (the "unit-tested on 3 repos" criterion); pick small, easy-to-parse ones first |

CI: `pytest`, `mypy`, `ruff` on every PR.

## 12. Build order for the agent

The full task list per phase is in `prd.md` section 7. This is the module order inside it:

| PRD phase | Modules to implement |
|---|---|
| 1 | `interfaces.py`, config loading, repo skeleton, CI, spike script |
| 2 | `context/parser.py`, `context/tokens.py` |
| 3 | `context/builders.py` (L1, L2), reference detection, `SlotResolver`; **hand off to P5 early** |
| 4 | `context/index.py`, `context/callgraph.py`, L3 builder |
| 5 | Real `SlotResolver`, context cache, integration tests with P5's runner |
| 6 | `context/diff.py`, `provenance/*`, CLI, `FakeDetector`, escalation loop |
| 7 | `report/*`, `action/`, policy loading, budget cap, unknown-origin mode |
| 8 | README, limitations doc, paper sections, demo |

## 13. Out of scope for this design

Policy learning, detector prompts, RAG, statistics, dashboard, dataset generation (other workstreams).
