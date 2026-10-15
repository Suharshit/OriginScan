# OriginScan Tool Description

> Draft paper section describing the OriginScan tool.
> P4 is lead writer; P1 integrates.

## 4.x OriginScan

OriginScan is a vulnerability scanning tool that adapts its analysis depth
based on the provenance of code changes. It is designed for integration into
pull request workflows, where it automatically determines whether changed
functions were authored by humans or AI tools, selects an appropriate context
depth, and runs vulnerability detection.

### Architecture

The tool consists of five modules:

1. **Context** (`originscan.context`): Tree-sitter-based C/C++ parser,
   three-level context builder (L1/L2/L3), repo-wide symbol index with
   commit-keyed caching, and approximate name-based call graph.

2. **Provenance** (`originscan.provenance`): Git metadata reader that
   classifies code as AI-generated, human-written, or unknown based on
   commit trailers, author patterns, and configured agent identities.

3. **Detection** (`originscan.detectors`): Adapter protocol for pluggable
   vulnerability detectors (LLM-based, static analysis, or fake for testing).
   Includes an escalation loop that increases context depth when detection
   confidence is below a threshold.

4. **Reporting** (`originscan.report`): JSON and Markdown report generators
   with per-function findings, token statistics, and timing metadata.

5. **CLI and Action** (`originscan.cli`, `action/`): Command-line interface
   (`scan`, `context`, `index`) and GitHub Action for automated PR scanning
   with comment posting.

### Workflow

A typical OriginScan run proceeds as follows:

```
PR opened → git diff → parse hunks → map to functions
         → for each function:
              determine origin (ai/human/unknown)
              choose start level (policy)
              build context (L1/L2/L3)
              run detection
              escalate if confidence < tau
         → generate JSON + Markdown reports
         → post/update PR comment
```

### Design Decisions

- **Deterministic**: Given the same commit and configuration, all outputs
  are identical. No randomness in context building or level selection.
- **No network in context**: Context building and provenance detection
  are fully offline. Only detector adapters make API calls.
- **Hard token caps**: The context never exceeds configured limits,
  preventing unexpected costs with LLM-based detectors.
- **Transparency**: Every finding includes the exact items included in
  context, the level used, and a configuration hash for reproduction.

### Availability

OriginScan is available as a Python package installable via pip, and as
a GitHub Action for CI/CD integration. The tool requires Python 3.11+
and tree-sitter for C/C++ parsing.
