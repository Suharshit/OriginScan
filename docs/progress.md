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
