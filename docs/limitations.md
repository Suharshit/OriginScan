# Known Limitations

> Documents known limitations of OriginScan as a research prototype.
> Transparency about these limits is critical for the paper and users.

## Context Building

### Approximate Call Graph
- **Name-based resolution only**: No compiler-level type information.
  Function pointers, callbacks, virtual dispatch, and macro-generated calls
  are not detected. See [`callgraph-limits.md`](callgraph-limits.md) for details.
- **No preprocessor expansion**: `#ifdef` branches, macro bodies, and
  conditional compilation are parsed as-is. A function behind a false `#ifdef`
  will still be indexed but may not represent the actual compiled code.
- **C/C++ only**: The parser currently supports C and C++ via tree-sitter.
  Other languages would require additional tree-sitter grammars and parser rules.

### Approximate Token Counts
- Token counts use tiktoken (`cl100k_base` by default), which approximates
  OpenAI's tokenizer. Actual token usage may differ slightly depending on
  the model and API version.
- The hard cap invariant (`tokens <= cap`) is enforced, but the cap is on
  the *estimated* token count, not the actual model tokenization.

### L3 Coverage
- Hop-2 callers/callees are included only if token budget remains after hop-1.
- Ambiguous call-graph edges are included last and labelled, but the chosen
  resolution may be wrong.
- Member calls (`a->method()`, `obj.func()`) are flagged but not resolved.

## Provenance Detection

### Metadata Dependency
- Provenance detection relies on git metadata: `Co-authored-by` trailers,
  bot author patterns, and configured agent identities.
- **Squash merges** that strip trailers produce `unknown` origin, which
  falls back to L1 (conservative).
- Repositories that do not use conventional bot naming or trailers will
  have reduced detection accuracy.

### No Code Style Analysis
- OriginScan does not analyze code style or patterns to infer AI authorship.
  It relies solely on commit metadata. This is a deliberate design choice
  for determinism and reproducibility.

## Detection

### Research Prototype
- The `FakeDetector` produces deterministic but non-meaningful findings.
  Real vulnerability detection requires plugging in LLM-based or static
  analysis detectors via the `DetectorAdapter` protocol.
- Detection accuracy depends entirely on the plugged-in detector, not
  on OriginScan's context building.

### Escalation Limits
- The escalation loop (`L1 → L2 → L3`) adds cost but does not guarantee
  improved detection. The tau threshold and budget cap are configurable
  but require tuning per detector.

## Operational

### Performance
- Repo indexing is linear in the number of source files. Large repos
  (>10K files) may take several seconds. The commit-keyed cache mitigates
  repeated indexing.
- Call graph construction is O(functions × avg_calls). Very large codebases
  may benefit from incremental indexing (not yet implemented).

### Security
- API keys must be provided via environment variables, never in config files.
- The GitHub Action uses `${{ github.token }}` by default, which has
  limited permissions scoped to the repository.
