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
