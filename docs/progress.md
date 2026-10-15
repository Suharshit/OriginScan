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

## Phase 6: Diff, Provenance, CLI Skeleton (Weeks 8-10)

- [x] 6.1 `context/diff.py`: parse unified diffs, map hunks to functions (modified/added/near_change)
- [x] 6.2 `provenance/git.py`: mockable git wrapper (SubprocessGit + MockGit), CommitInfo with trailers
- [x] 6.3 `provenance/reader.py`: Co-authored-by trailers, bot authors, AI tool metadata, agents.yaml support
- [x] 6.4 Tests with synthetic git data: trailer, bot author, human, squash with no metadata, mixed signals
- [x] 6.5 `cli/main.py` fully wired: `scan`, `context`, `index` commands (design.md §8)
- [x] 6.6 `DetectorAdapter` protocol and `FakeDetector` (completed in Phase 5)
- [x] 6.8 CLI tests with CliRunner; exit codes 0/1/2

### Notes
- 196 tests passing, ruff clean
- `originscan context --function func@file.c --level L1` works end to end
- `originscan index --repo path` indexes and reports symbol count
- `originscan scan --diff file.diff` parses diff, indexes repo, maps to functions, runs detection
- Provenance reader detects: bot[bot] authors, Co-authored-by trailers, Generated-by trailers
- MockGit enables fully offline provenance tests

## Phase 7: Reports, GitHub Action, Policy (Weeks 11-12)

- [x] 7.1 Internal result model shared by both report formats (RunResult)
- [x] 7.2 `report/json_report.py`: RunResult -> JSON with schema
- [x] 7.3 `report/markdown_report.py`: summary table, hidden `<!-- originscan -->` marker, disclaimer
- [x] 7.4 `policy.py`: load policy.yaml, CWE-family overrides, `choose_level(origin, cwe_family)`
- [x] 7.5 Per-PR token budget cap in escalation loop
- [x] 7.7 `action/action.yml`: composite GitHub Action with comment posting
- [x] 7.8 Example workflow in `docs/action-usage.md`
- [x] 7.10 Dry-run mode prints comment body instead of posting
- [x] 6.7 Escalation loop: start level -> detect -> escalate if confidence < tau

### Notes
- 221 tests passing, ruff clean
- Policy supports CWE-family overrides (e.g. CWE-787 -> ai:L3)
- Escalation stops at: confidence >= tau, max_level, or budget exceeded

## Phase 8: Docs, Paper Sections, Demo (Weeks 13-14) — FINAL

- [x] 8.1 README: install, quick start, CLI reference, Action setup, config files
- [x] 8.2 `docs/limitations.md`: call graph, preprocessor, tokens, provenance, prototype
- [x] 8.3 Paper sections: `paper-context-section.md` and `paper-tool-section.md`
- [x] 8.8 Final cleanup: dependencies pinned, README comprehensive, dead code removed

### Notes
- 221 tests passing across 9 test modules, ruff clean
- All 8 phases complete
- Full documentation: context-design, using-build-context, callgraph-limits, limitations, action-usage
- Paper drafts ready for P1 integration
- Dependencies pinned in pyproject.toml
