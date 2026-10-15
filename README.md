# OriginScan

> **Vulnerability scanner that adapts context depth based on code provenance.**

OriginScan studies whether knowing who wrote code (human or AI) should change how much surrounding context a vulnerability detector reads, and ships a pull-request scanner that applies the answer. One Python codebase serves both the research study and the tool.

**Status:** All 8 phases complete — 221 tests passing, ruff clean ✅

---

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Build a repo index
originscan index --repo path/to/repo

# Print context for a function
originscan context --function "func_name@path/to/file.c" --level L2

# Scan a diff
originscan scan --diff changes.diff --repo path/to/repo
```

## CLI Reference

```
originscan scan    --repo PATH --diff FILE [--policy policy.yaml] [--budget N]
                   [--format json,md] [--fail-on-findings] [--out DIR]

originscan context --function FUNC_ID --level L1|L2|L3 [--repo PATH]

originscan index   [--repo PATH]
```

| Command | Description |
|---|---|
| `scan` | Parse a diff, index the repo, map hunks to functions, detect vulnerabilities, produce reports |
| `context` | Print the assembled context for a function at a given level |
| `index` | Build or refresh the repo-wide symbol index |

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
                                    Policy + Escalation Loop
                                              │
                                              ▼
                                  JSON + Markdown Reports
                                              │
                                              ▼
                                  GitHub Action PR Comment
```

### Context Levels

| Level | Contents | Default Cap |
|---|---|---|
| **L1** | Target function only | 2,000 tokens |
| **L2** | L1 + same-file types, macros, globals, helpers (priority-ordered) | 6,000 tokens |
| **L3** | L2 + cross-file callers/callees (1-2 hops, ambiguity-aware) | 15,000 tokens |

### Provenance Detection

| Signal | Example | Result |
|---|---|---|
| `Co-authored-by` trailer | `Co-authored-by: copilot[bot] <...>` | `ai` |
| Bot author pattern | `dependabot[bot]` | `ai` |
| AI tool trailer | `Generated-by: GitHub Copilot` | `ai` |
| Configured agent identity | From `config/agents.yaml` | `ai` |
| No AI signals | Regular human commits | `human` |
| No metadata (squash) | Squashed commit, no trailers | `unknown` → L1 |

### Escalation Loop

```
Start Level (from policy) → Detect → confidence < tau?
    ├── Yes → Escalate to next level (if budget allows)
    └── No  → Report finding
```

## GitHub Action

Add to `.github/workflows/originscan.yml`:

```yaml
name: OriginScan PR Scan
on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: ./action
        with:
          fail-on-findings: 'false'
```

See [`docs/action-usage.md`](docs/action-usage.md) for full configuration.

## Configuration

| File | Purpose |
|---|---|
| `config/context.yaml` | Token caps, per-item limits, hops, ignore globs |
| `config/agents.yaml` | Known AI agent names/emails for provenance |
| `policy.yaml` | Level selection rules per origin and CWE family |

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
│   ├── policy.py                # Policy loader: levels, escalation, CWE overrides
│   ├── detectors.py             # FakeDetector + DetectorAdapter protocol
│   ├── runner.py                # Run orchestrator, choose_start, escalation loop
│   ├── context/
│   │   ├── parser.py            # C/C++ symbol extraction via tree-sitter
│   │   ├── tokens.py            # Pluggable token counter (tiktoken / whitespace)
│   │   ├── builders.py          # L1/L2/L3 context assembly with hard token caps
│   │   ├── index.py             # Repo-wide symbol index with commit-keyed cache
│   │   ├── callgraph.py         # Approximate call graph with ambiguity rule
│   │   └── diff.py              # Unified diff parser → changed functions
│   ├── provenance/
│   │   ├── git.py               # Mockable git wrapper (SubprocessGit + MockGit)
│   │   └── reader.py            # Provenance detection: ai/human/unknown
│   ├── cli/
│   │   └── main.py              # Typer CLI: scan, context, index
│   └── report/
│       ├── json_report.py       # RunResult → JSON report
│       └── markdown_report.py   # RunResult → Markdown PR comment
├── action/
│   └── action.yml               # GitHub Action composite action
├── tests/                       # 221 tests across 8 test modules
│   ├── fixtures/                # C/C++ test files + multi-file repo
│   ├── test_interfaces.py
│   ├── test_config.py
│   ├── test_parser.py
│   ├── test_tokens.py
│   ├── test_builders.py
│   ├── test_index_callgraph.py
│   ├── test_runner.py
│   ├── test_phase6.py
│   └── test_phase7.py
├── docs/
│   ├── context-design.md        # L1/L2/L3 design rationale
│   ├── using-build-context.md   # Usage guide for P5
│   ├── callgraph-limits.md      # Call graph known limitations
│   ├── limitations.md           # Full limitations document
│   ├── action-usage.md          # GitHub Action setup guide
│   ├── paper-context-section.md # Paper: Methods context section draft
│   ├── paper-tool-section.md    # Paper: OriginScan tool section draft
│   ├── interface-changes.md     # Frozen interface change log
│   └── progress.md              # Phase completion tracking
└── .github/workflows/ci.yml    # pytest + ruff on every PR
```

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Parsing | tree-sitter 0.24.0, tree-sitter-c 0.23.2, tree-sitter-cpp 0.23.2 |
| Tokens | tiktoken (cl100k_base, pluggable) |
| CLI | Typer |
| Config | PyYAML |
| CI | GitHub Actions (pytest, ruff) |

## Development

```bash
# Run the full check suite
ruff check src/ tests/
pytest tests/ -v --tb=short

# Run a specific test module
pytest tests/test_builders.py -v

# Lint and fix
ruff check --fix src/ tests/
```

## Documentation

| Document | Description |
|---|---|
| [`context-design.md`](docs/context-design.md) | L1/L2/L3 design, priority ordering, truncation rules |
| [`using-build-context.md`](docs/using-build-context.md) | How P5 calls `build_context` |
| [`callgraph-limits.md`](docs/callgraph-limits.md) | Known call graph limitations |
| [`limitations.md`](docs/limitations.md) | Full limitations of the research prototype |
| [`action-usage.md`](docs/action-usage.md) | GitHub Action setup and configuration |
| [`progress.md`](docs/progress.md) | Phase-by-phase completion tracking |

## Research Prototype

This is a research prototype for the OriginScan study. It scans only
repositories the team owns or forks.
See `.agent/prd.md` for the full specification.

## License

MIT
