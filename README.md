# OriginScan

> **Vulnerability scanner that adapts context depth based on code provenance.**

OriginScan studies whether knowing who wrote code (human or AI) should change how much surrounding context a vulnerability detector reads, and ships a pull-request scanner that applies the answer. One Python codebase serves both the research study and the tool.

**Status:** Phase 2 complete — Parser & Token Counter ✅

---

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type check
mypy src/originscan/interfaces.py src/originscan/config.py

# Lint
ruff check src/ tests/

# Run the tree-sitter spike (built-in sample or provide a C file)
python scripts/spike_treesitter.py
python scripts/spike_treesitter.py path/to/some/file.c

# CLI (stub — commands wired up in later phases)
originscan --help
```

## How It Works

```
C/C++ Source ──► Tree-sitter Parser ──► Repo Index & Call Graph
                                              │
                                              ▼
                                     Context Builder (L1/L2/L3)
                                              │
Git History ──► Provenance Reader ──►  ai / human / unknown
                                              │
                                              ▼
                                     CLI: originscan scan
                                              │
                                              ▼
                                  JSON + Markdown Reports
                                              │
                                              ▼
                                  GitHub Action PR Comment
```

### Context Levels

| Level | Contents | Approx. Tokens |
|---|---|---|
| **L1** | Target function only | ~1.5k |
| **L2** | L1 + same-file types, macros, globals, helpers | ~5k |
| **L3** | L2 + 1-2 hop callers/callees across files | ~12k |

## Project Structure

```
originscan/
├── pyproject.toml               # Python 3.11, pinned dependencies
├── config/
│   ├── context.yaml             # Token caps, per-item limits, hops, ignore globs
│   └── agents.yaml              # Known AI agent identities for provenance
├── src/originscan/
│   ├── interfaces.py            # Frozen types: Context, Finding, Level, Origin
│   ├── config.py                # YAML config loader with deterministic hashing
│   ├── context/
│   │   ├── parser.py            # C/C++ symbol extraction via tree-sitter
│   │   ├── tokens.py            # Pluggable token counter (tiktoken / whitespace)
│   │   ├── index.py             # Repo-wide symbol index (Phase 4)
│   │   ├── callgraph.py         # Approximate call graph (Phase 4)
│   │   ├── builders.py          # L1/L2/L3 context assembly (Phase 3)
│   │   └── diff.py              # Diff → changed functions (Phase 6)
│   ├── provenance/
│   │   ├── reader.py            # ai/human/unknown labelling (Phase 6)
│   │   └── git.py               # Thin git wrapper (Phase 6)
│   ├── cli/
│   │   └── main.py              # Typer CLI: scan, context, index
│   └── report/
│       ├── json_report.py       # JSON report (Phase 7)
│       └── markdown_report.py   # Markdown PR comment (Phase 7)
├── action/                      # GitHub Action (Phase 7)
├── scripts/
│   └── spike_treesitter.py      # Phase 1 tree-sitter validation spike
├── tests/
│   ├── fixtures/                # C/C++ test files
│   │   ├── simple.c             # Functions, structs, enums, macros, globals
│   │   ├── cpp_class.cpp        # C++ class, namespaces, qualified methods
│   │   ├── syntax_error.c       # Error tolerance testing
│   │   ├── ifdef_macros.c       # Preprocessor-heavy code
│   │   └── static_funcs.c       # All-static functions and globals
│   ├── test_interfaces.py
│   ├── test_config.py
│   ├── test_parser.py
│   └── test_tokens.py
├── docs/
│   ├── context-design.md        # L1/L2/L3 design (Gate 1 deliverable)
│   ├── interface-changes.md     # Change log for frozen interfaces
│   └── progress.md              # Phase completion tracking
└── .github/workflows/ci.yml     # pytest + mypy + ruff on every PR
```

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Parsing | tree-sitter 0.24.0, tree-sitter-c 0.23.2, tree-sitter-cpp 0.23.2 |
| Tokens | tiktoken (cl100k_base, pluggable) |
| CLI | Typer |
| CI | GitHub Actions (pytest, mypy, ruff) |

## Development

```bash
# Run the full check suite
ruff check src/ tests/
mypy src/originscan/interfaces.py src/originscan/config.py
pytest tests/ -v --tb=short
```

## Research Prototype

This is a research prototype for the OriginScan study. It scans only repositories the team owns or forks. See `.agent/prd.md` for the full specification.

## License

MIT
