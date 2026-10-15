# Progress Log

## Phase 1: Foundations (Week 1)

- [x] 1.1 Package skeleton created (`src/originscan/` with all subpackages)
- [x] 1.2 `interfaces.py` with `Level`, `Origin`, `Context`, `Finding`, protocols, stubs
- [x] 1.3 Config loader for `config/context.yaml` and `config/agents.yaml`
- [x] 1.4 CI workflow (pytest, mypy, ruff)
- [x] 1.5 tree-sitter packages pinned in `pyproject.toml`
- [x] 1.6 Spike script: `scripts/spike_treesitter.py`
- [ ] 1.7 Day 5: review interfaces with P2 and P5
- [ ] 1.8 Spike report

### Notes
- Token caps in `context.yaml` are provisional (2k/6k/15k) — need confirmation from P5.
- tree-sitter pinned: `tree-sitter==0.24.0`, `tree-sitter-c==0.23.2`, `tree-sitter-cpp==0.23.2`
- Config hash function added for reproducibility tracking.

## Phase 2: Parser and Token Counter (Weeks 2-3)

- [x] 2.1 `context/parser.py`: `Symbol` dataclass, `parse_source`, `parse_file`
- [x] 2.2 Extract functions, struct/union/enum, typedefs, globals, macros, static functions
- [x] 2.3 C++ support: qualified names, in-class methods, extension detection
- [x] 2.4 Error tolerance: valid symbols extracted despite ERROR nodes; logged warnings
- [x] 2.5 `context/tokens.py`: `TokenCounter` protocol, tiktoken default, whitespace fallback
- [x] 2.6 Fixtures: `simple.c`, `static_funcs.c`, `ifdef_macros.c`, `syntax_error.c`, `cpp_class.cpp`
- [x] 2.7 `docs/context-design.md`: L1/L2/L3 contents, priority order, proposed caps, known limits

### Notes
- 72 tests passing, ruff clean
- tree-sitter-c/cpp 0.23.2 compatible with tree-sitter 0.24.0 (ABI v14)
- Parser extracts all 7 symbol kinds correctly across all fixtures
- Error tolerance confirmed: syntax_error.c extracts valid symbols around broken code

## Phase 3: L1 and L2 Builders (Weeks 3-5) — CRITICAL PATH

- [x] 3.1 Per-file symbol lookup
- [x] 3.2 Reference detection via tree-sitter identifier matching (not substring search)
- [x] 3.3 `build_l1` with truncation rule (line boundary + `// [truncated]`)
- [x] 3.4 `build_l2` with priority order: types → macros → globals → helpers
- [x] 3.5 Output formatting with delimiters and `items` list
- [x] 3.6 `SlotResolver` protocol + `PathResolver` (path-based for now)
- [x] 3.7 Tests: property test (tokens ≤ cap), determinism (5x runs), adversarial large input
- [x] 3.8 `docs/using-build-context.md` — usage guide for P5

### Notes
- 119 tests passing, ruff clean
- Token cap invariant tested at caps: 50, 100, 200, 500, 1000, 2000, 6000
- Cap tested across multiple fixtures (simple.c, ifdef_macros.c) and all functions
- Adversarial test: 500-line function respects cap
- Determinism verified: 5 identical runs produce identical output
- P5 can call `build_context("func@file.c", "L1")` or `"L2"` now

## Phase 4: Repo Index, Call Graph, and L3 (Weeks 4-6)

- [x] 4.1 `context/index.py`: `RepoIndex.build(root, commit)` with ignore globs
- [x] 4.2 Index cache keyed by commit hash (`.originscan/index-<commit>.json`)
- [x] 4.3 `context/callgraph.py`: extract call identifiers, flag member calls
- [x] 4.4 Name resolution with ambiguity rule (same file > same dir > anywhere)
- [x] 4.5 `callers` and `callees` with hop depth (BFS) and deterministic order
- [x] 4.6 `build_l3`: L2 + callees, callers, hop 2, ambiguous edges last with labels
- [x] 4.7 Multi-file fixture repo (`tests/fixtures/multifile/`) with known edges
- [x] 4.9 `docs/callgraph-limits.md`

### Notes
- 143 tests passing, ruff clean
- Index: parses all files, relative paths, cache roundtrip verified
- Call graph: resolves direct calls, static functions in same file, flags ambiguity
- L3: includes cross-file callees/callers, respects cap at 100/500/1k/5k/15k
- L3 falls back to L2 gracefully when no call graph is provided
- Unresolved external calls (libc) correctly tracked but not included in context

## Phase 5: Integration and Pilot Support (Weeks 6-7)

- [x] 5.1 Integration test: runner -> `build_context` -> `detect` (FakeDetector) across L1/L2/L3
- [x] 5.2 `choose_start(origin, policy)` — deterministic level chooser (default: human→L1, ai→L2)
- [x] 5.3 `run_experiment()` orchestrator with timing metadata, config hash, token stats
- [x] 5.4 `FakeDetector` — deterministic detector satisfying `DetectorAdapter` protocol
- [x] 5.5 `Slot`, `SlotResult`, `RunResult` data classes with full metadata
- [x] 5.6 `compute_token_stats()` — per-level min/max/mean/median token statistics
- [x] 5.7 Error handling: bad slots caught without crashing the run
- [x] 5.8 Custom policy, detector, counter, and cap overrides supported

### Notes
- 170 tests passing, ruff clean
- Integration test covers L1/L2/L3 end-to-end with FakeDetector
- Level selection verified: human→L1, ai→L2 by default policy
- Multiple runs per slot supported (runs_per_slot=N)
- Token cap invariant holds across all levels and fixtures
- Error in one slot does not crash the entire experiment run
