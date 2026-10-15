# PRD — OriginScan P4: Context Builder & Tool

> Scope: the P4 workstream only (Context & tool lead). Source of truth: *OriginScan Project Overview* (Sep 21, 2026) and *Team Brief* (Oct 11, 2026).
> Status: no code exists yet. This PRD assumes a greenfield start inside the team mono-repo.

## 1. Background

OriginScan studies whether knowing who wrote code (human or AI) should change how much surrounding code a vulnerability detector reads, and ships a pull-request scanner that applies the answer. One Python codebase serves both the study and the tool, so the tool behaves exactly as measured.

P4 owns the part that turns a function (or a PR diff) into detector-ready **context** at three depths, and the user-facing **tool** around it.

## 2. Goals

1. Build `build_context(slot_id, level) -> Context` for levels L1/L2/L3 with enforced token caps. P5's experiment runner depends on it by **Week 5**.
2. Build the `originscan` CLI that scans a diff or repo and emits JSON + Markdown reports.
3. Build a GitHub Action that runs the CLI on each PR in a repo we own and posts a comment.
4. Build the provenance reader (`ai` / `human` / `unknown` per changed function).
5. Reuse the *same* context-builder modules in the study and the tool (credibility requirement).

## 3. Non-goals

- Not an AI-code detector: provenance comes from metadata only; fall back safely when absent.
- Not an auto-fixer: detection and reporting only.
- Not production-hardened: research prototype on repos we own or fork.
- Not owned by P4: policy engine / `policy.yaml` (P5), detector prompts and runner (P5), static adapter (P3), dataset/Docker (P2), dashboard (P5).
- No scanning of third-party PRs, no unsolicited comments on others' PRs.

## 4. Users

| User | Need |
|---|---|
| P5 (experiment runner) | A deterministic, cached `build_context` with token counts per level |
| Developers / CI | `originscan scan` on a diff; readable report |
| Maintainers (repos we own) | Automatic PR comment with findings, confidence, level used, tokens |
| Paper reviewers | Same code path as the study; reproducible output |

## 5. Functional requirements

Priority follows the overview: **Must / Should / Could**.

### 5.1 Parsing and function extraction (Must)
- FR-1: Parse C and C++ with tree-sitter; extract functions with file, name, start/end line, source text.
- FR-2: Extract file-level items: struct/union/enum/typedef declarations, globals, `#define` macros, helper (static) functions.
- FR-3: Given a unified diff, return the set of changed functions.
- FR-4: Tolerate parse errors and partial trees without crashing; log and continue.

### 5.2 Context levels (Must)
- FR-5: **L1 Function** — target function only.
- FR-6: **L2 File** — L1 + *selected* same-file types, globals, macros, helpers (selected by relevance to the function, never the whole file dumped).
- FR-7: **L3 Repo slice** — L2 + 1–2 hop callers/callees across files + referenced types.
- FR-8: Every level has a configurable token cap; output must never exceed it. Truncation must be deterministic and prioritised (target function always kept first).
- FR-9: Return `Context = {text: str, tokens: int, items: list[str]}` where `items` lists what was included (for reports and debugging).
- FR-10: Same input always yields the same output (determinism; required for replication).

### 5.3 Approximate call graph (Must)
- FR-11: Index a repo once; resolve callers/callees by name with a documented ambiguity rule (same file → same directory → anywhere, with ties broken deterministically).
- FR-12: Document known limits: function pointers, macro-generated calls, same-named statics.
- FR-13: Cache the index on disk keyed by repo commit hash.

### 5.4 Provenance reader (Must)
- FR-14: Read `Co-authored-by` trailers, known agent bot authors, and tool metadata from commits.
- FR-15: Output `ai | human | unknown` per changed function (via the commits that touched its lines).
- FR-16: Known-agent identifiers live in a config file, not in code.

### 5.5 CLI (Must)
- FR-17: `originscan scan --diff <file|range> [--repo PATH] [--out DIR] [--format json,md]`
- FR-18: `originscan context --slot-id ID --level L1|L2|L3` (used by the study; prints the Context).
- FR-19: Load a policy file if present (P5's `policy.yaml`) to choose the start level; otherwise use the confidence-only default.
- FR-20: Exit codes: 0 ok, 1 findings above threshold (optional flag), 2 usage/config error.

### 5.6 Report generator (Must)
- FR-21: JSON + Markdown reports with: finding, CWE, line, confidence, level used, input/output tokens.
- FR-22: Report states provenance per function and the policy used.

### 5.7 GitHub Action (Must)
- FR-23: Workflow runs the CLI on `pull_request` events and posts or updates a single PR comment.
- FR-24: API keys only from repository secrets; never logged.

### 5.8 Should / Could
- Should: per-PR token budget cap that stops escalation (FR-25); "unknown origin" mode that falls back to confidence-only (FR-26).
- Could: cross-family reviewer routing, only if RQ4 supports it (FR-27).

## 6. Dependencies on teammates

| Dependency | Owner | Needed by | P4 mitigation |
|---|---|---|---|
| Interfaces & data model frozen (§6.2/6.3 of overview) | P2, P4, P5 | Week 1, Day 5 | Draft `interfaces.py` first |
| Benchmark repos / slot snapshots | P2 | Week 3 | Develop against 3 public C repos meanwhile |
| `detect()` implementation | P5 | Week 5 | Ship a stub detector for tests |
| `choose_start()` / `policy.yaml` | P5 | Weeks 10–11 | Stub returning confidence-only default |
| Semgrep/CodeQL adapter | P3 | Weeks 11–12 | CLI adapter interface with a fake |

## 7. Phases (what to do, in order)

The P4 work is split into 8 phases that follow the 14-week plan. Finish a phase's tests before starting the next one. Phases 3 and 4 overlap in the calendar, but work through them one at a time. Section references (design.md §x) point to `design.md`.

| Phase | Weeks | Theme | Exit gate |
|---|---|---|---|
| 1 | 1 | Foundations | Interfaces frozen Day 5 |
| 2 | 2-3 | Parser and token counter | Parser tested; context design ready for Gate 1 |
| 3 | 3-5 | L1/L2 builders | **Builder usable by P5 (Week 5)** |
| 4 | 4-6 | Index, call graph, L3 | Unit-tested on 3 repos, caps enforced |
| 5 | 6-7 | Integration and pilot support | Runner works end to end |
| 6 | 8-10 | Diff, provenance, CLI skeleton | `originscan scan` runs with FakeDetector |
| 7 | 11-12 | Reports, GitHub Action, policy | Demo PR scanned, comment posted |
| 8 | 13-14 | Docs, paper sections, demo | Submission |

Critical path: Phases 1, 2, 3. If time is short, cut from Phase 4 (hop-2 callers/callees) before touching Phases 1-3.

### Phase 1: Foundations (Week 1)
**Goal:** a runnable, CI-checked skeleton with frozen interfaces, and proof that tree-sitter can extract a function and its callers/callees from one C repo.
- [ ] 1.1 Package skeleton (`src/originscan/` with `context/`, `provenance/`, `cli/`, `report/`), `pyproject.toml` (Python 3.11), `tests/`, `config/`, `docs/`. Confirm the layout with the team.
- [ ] 1.2 `interfaces.py`: `Level`, `Origin`, `Context`, `Finding`, `build_context`, `detect`, `choose_start` (design.md §2).
- [ ] 1.3 Config loader for `config/context.yaml` and `config/agents.yaml`.
- [ ] 1.4 CI running `pytest`, `mypy`, `ruff` on every PR.
- [ ] 1.5 Pin tree-sitter packages (check current names on PyPI) and record versions.
- [ ] 1.6 Spike script: parse one small C repo, extract a function, list its callers and callees by name.
- [ ] 1.7 Day 5: review interfaces and data model with P2 and P5, freeze, create `docs/interface-changes.md`.
- [ ] 1.8 One-page spike report (what worked, what broke, blockers).

**Done when:** tests, mypy and ruff pass locally and in CI; spike works on a real C repo; P2 and P5 have acknowledged the interfaces.

### Phase 2: Parser and token counter (Weeks 2-3)
**Goal:** reliable C/C++ symbol extraction and a pluggable token counter, plus the context design note for Gate 1.
- [ ] 2.1 `context/parser.py`: `Symbol` dataclass, `parse_source`, `parse_file` (design.md §3).
- [ ] 2.2 Extract functions, struct/union/enum definitions, typedefs, globals, macros, static functions.
- [ ] 2.3 C++ support: qualified names, in-class methods, extension detection.
- [ ] 2.4 Error tolerance: still return valid symbols when the tree has `ERROR` nodes; log a warning.
- [ ] 2.5 `context/tokens.py`: `TokenCounter` protocol, tiktoken default, whitespace fallback.
- [ ] 2.6 Fixtures: plain and static functions, nested macros, `#ifdef` blocks, syntax errors, a C++ class.
- [ ] 2.7 `docs/context-design.md`: what goes in L1/L2/L3, priority order, proposed caps, known limits; share with P5.

**Done when:** parser output is correct on every fixture; the broken-syntax fixture does not raise; context design reviewed by P5.

### Phase 3: L1 and L2 builders (Weeks 3-5)
**Goal:** `build_context` for L1 and L2 with hard token caps, deterministic output, and a working hand-off to P5. **Critical-path deliverable.**
- [ ] 3.1 Per-file symbol lookup (the repo-wide index comes in Phase 4).
- [ ] 3.2 Reference detection: which types, macros, globals and helpers a function uses (identifier match on the tree, not substring search).
- [ ] 3.3 `build_l1` with the truncation rule (cut at a line boundary, add `// [truncated]`).
- [ ] 3.4 `build_l2` with the priority order in design.md §5 (types, macros, globals, helpers).
- [ ] 3.5 Output formatting with delimiters and the `items` list.
- [ ] 3.6 `SlotResolver` protocol so `build_context(slot_id, level)` can use P2's data later; path-based resolver for now.
- [ ] 3.7 Tests: golden files, **property test that tokens <= cap**, determinism (run twice, compare).
- [ ] 3.8 `docs/using-build-context.md` and a demo to P5.
- [ ] 3.9 Fill in provisional caps in `config/context.yaml` with P5.

**Done when:** golden tests pass; zero cap violations; P5 can call `build_context` on a handful of functions.

### Phase 4: Repo index, call graph and L3 (Weeks 4-6)
**Goal:** index a whole repo, resolve callers/callees approximately, add L3. The hardest phase.
- [ ] 4.1 `context/index.py`: `RepoIndex.build(root, commit)`, ignore globs (`build/`, `third_party/`, `vendor/`).
- [ ] 4.2 Index cache keyed by commit hash and config hash.
- [ ] 4.3 `context/callgraph.py`: extract call identifiers, flag member calls.
- [ ] 4.4 Name resolution with the ambiguity rule (design.md §4); keep `ambiguous` flags and an `unresolved` list.
- [ ] 4.5 `callers` and `callees` with hop depth and deterministic order.
- [ ] 4.6 `build_l3`: L2 plus callees, windowed callers, referenced types, hop 2 if budget remains; ambiguous items last and labelled.
- [ ] 4.7 Multi-file fixture repo with known edges and ambiguity cases (same-named statics, function pointer, macro call).
- [ ] 4.8 Run on **3 real C repos**; record extraction accuracy on a sample and build times.
- [ ] 4.9 `docs/callgraph-limits.md`.

**Done when:** known edges found and ambiguous ones flagged; L3 never exceeds its cap; "unit-tested on 3 repos" met; cached reload is faster than rebuild.

### Phase 5: Integration and pilot support (Weeks 6-7)
**Goal:** P5's runner calls `build_context` at all three levels end to end, and the Week 7 pilot (Gate 2) is not blocked by context issues.
- [ ] 5.1 Integration test: runner -> `build_context` -> `detect` (real or fake) across L1/L2/L3.
- [ ] 5.2 Real `SlotResolver` for P2's slot format (write `docs/slot-format.md` from what P2 gives you).
- [ ] 5.3 Measure per-level tokens and build time on pilot slots; give P5 the numbers to replace the 1.5k/5k/12k assumptions.
- [ ] 5.4 Tune caps and ranking with P5 if needed; log each change with its config hash.
- [ ] 5.5 Context cache keyed by (commit, function id, level, config hash).
- [ ] 5.6 Bug-fix buffer for issues found by P5 and P2.
- [ ] 5.7 Support the Gate 2 review: token statistics and known limitations.
- [ ] 5.8 Start Methods notes for the paper (context section).

**Done when:** context produced for every pilot slot without crashes; token statistics delivered before the pilot; no open P0 context bugs.

### Phase 6: Diff mapper, provenance and CLI skeleton (Weeks 8-10)
**Goal:** `originscan scan` runs end to end on a real diff using `FakeDetector`.
- [ ] 6.1 `context/diff.py`: parse unified diffs, map new-side hunks to functions; handle deleted-only hunks and non-function changes.
- [ ] 6.2 `provenance/git.py`: mockable git wrapper (commits touching given lines).
- [ ] 6.3 `provenance/reader.py`: `Co-authored-by` trailers, bot authors, tool metadata keys from `config/agents.yaml`; output `ai | human | unknown` with evidence.
- [ ] 6.4 Synthetic git repos in tests: trailer, bot author, plain human, squash with no metadata (-> unknown).
- [ ] 6.5 `cli/main.py` (Typer): `scan`, `context`, `index` (design.md §8).
- [ ] 6.6 `DetectorAdapter` protocol and `FakeDetector`.
- [ ] 6.7 Escalation loop: start level -> detect -> escalate if confidence < tau, respecting a budget (default confidence-only from L1).
- [ ] 6.8 CLI tests with `CliRunner`; exit codes 0/1/2.

**Done when:** diff fixtures map to the expected functions; provenance labels and evidence are right on all synthetic repos; `originscan scan --repo X --diff Y` prints per-function results.

### Phase 7: Reports, GitHub Action and policy loading (Weeks 11-12)
**Goal:** a demo PR in a repo we own is scanned automatically and gets a comment with findings, confidence, level used and token cost.
- [ ] 7.1 Internal result model shared by both report formats.
- [ ] 7.2 JSON report following the schema in design.md §9.
- [ ] 7.3 Markdown report: summary table, hidden marker `<!-- originscan -->`, disclaimer line.
- [ ] 7.4 Load P5's `policy.yaml` and call `choose_start`; fall back to confidence-only for `unknown` origin.
- [ ] 7.5 Per-PR token budget cap; report when it was hit.
- [ ] 7.6 Plug in P3's static adapter and P5's detectors behind `DetectorAdapter` (FakeDetector is enough for the demo if they are late).
- [ ] 7.7 `action/`: `action.yml`, entrypoint, comment poster that updates its own comment via the marker.
- [ ] 7.8 Example workflow (`pull_request` trigger, `fetch-depth: 0`, API keys from secrets).
- [ ] 7.9 Demo repo (team-owned) and an end-to-end demo PR with AI and human commits.
- [ ] 7.10 Dry-run mode that prints the comment body instead of posting.

**Done when:** report JSON matches the schema; the demo PR gets exactly one comment, updated on new pushes; budget cap and unknown-origin fallback are tested; no API key appears in logs.

### Phase 8: Docs, writing and demo (Weeks 13-14)
**Goal:** documented tool, P4 paper sections written, demo recorded, nothing blocking submission.
- [ ] 8.1 README: install, quick start, CLI reference, Action setup, config files.
- [ ] 8.2 `docs/limitations.md`: approximate call graph, preprocessor effects, approximate token counts, provenance needs metadata, research prototype.
- [ ] 8.3 Paper: "Methods: context" and "OriginScan" sections (you are lead writer); P1 integrates.
- [ ] 8.4 Cross-review one section you did not write (Week 13).
- [ ] 8.5 Replication hooks with P2: the Docker image runs `build_context` and the CLI.
- [ ] 8.6 Re-run all tests and the demo from a fresh clone.
- [ ] 8.7 Record the demo video (Week 14): open PR -> scan -> comment.
- [ ] 8.8 Final cleanup: remove dead code, pin dependencies, tag a release.

**Done when:** a fresh clone with Docker reproduces the P4 parts of the main tables (with P2); Methods and OriginScan sections reach P1 in Week 13; the demo video shows a PR scan end to end.

### Rules for every phase
1. Do not change `interfaces.py` after Phase 1 without logging it in `docs/interface-changes.md` and telling P2 and P5.
2. Every PR gets one reviewer from another workstream.
3. Each phase ends with tests green, `mypy` and `ruff` clean, and a short note in `docs/progress.md` (done, deferred).
4. If a dependency is late: use `FakeDetector` for `detect()`, a confidence-only default for `policy.yaml`, and 3 small public C repos if P2's repos are not ready.

## 8. Acceptance criteria ("done when")

- Context builder: **unit-tested on 3 repos; token caps enforced** (hard limit, tested with adversarial large inputs).
- CLI + Action: **scans a demo PR end to end and posts a comment**.
- Determinism test: identical output across two runs and across machines (given the same commit).
- Tests run in CI on every PR; one reviewer from another workstream per PR.

## 9. Success metrics

| Metric | Minimum | Target |
|---|---|---|
| Functions extracted correctly on 3 test repos | ≥ 95% of sampled functions | ≥ 99% |
| Token cap violations | 0 | 0 |
| CLI works on a demo repo | yes | yes, plus Action live |
| Context build time for L3 (cached index) | measured and reported | < 2 s per function |

(The numeric targets for extraction accuracy and speed are P4 proposals, not from the overview; confirm with the team.)

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Call graph inaccurate without a build system | Wrong L3 context | Document as approximate; ambiguity rule; report `items` so errors are visible |
| `#ifdef`/macro-heavy code parses poorly | Missing L2 items | Error-tolerant parsing; fixture tests with macro-heavy files |
| Token caps are an implicit research decision | Results depend on ranking heuristics | Make caps and ranking configurable in YAML; log the config per run; co-decide with P5 |
| Slip on Week 5 builder blocks P5 and Gate 2 | Project-wide delay | Ship L1 and L2 first; L3 can be rough initially |
| Tokenizer mismatch with target LLMs | Cap accuracy | Pluggable token counter; default is an approximation, recorded in each run |

## 11. Open questions

- Token caps per level (overview gives *average* tokens 1.5k / 5k / 12k as planning assumptions, not caps) — P4 proposes, P5 consulted.
- Is the CodeMentor tree-sitter code available for reuse? Plan assumes **not**.
- Which tokenizer for counting? Depends on P5's final model list.
- Real submission deadline (affects what gets cut first: dashboard, RQ4, agentic-PR corpus).

## 12. Ethics and constraints

- Public code and repos the team owns or forks only.
- No new exploit code written or released.
- Likely new vulnerabilities in live projects are reported privately via the project's security policy.
- API keys in secrets, never in code or logs.
