# Methods: Context Building

> Draft paper section for the OriginScan paper.
> P4 is lead writer for this section; P1 integrates.

## 3.x Context Construction

We introduce a three-level context construction pipeline that adapts the
amount of code provided to a vulnerability detector based on code provenance
metadata. The key insight is that AI-generated code, which we can identify
from git metadata, may benefit from broader context to catch vulnerabilities
that emerge from incomplete understanding of the surrounding codebase.

### Levels

**L1 (Function).**
The target function body, including its signature and any inline comments.
If the function exceeds the token cap, it is truncated at a line boundary
with a `// [truncated]` marker. This is the minimal context and serves as
the baseline.

**L2 (File).**
L1 plus selected same-file symbols that the target function references.
We use tree-sitter to extract identifier nodes from the function body and
match them against symbols defined in the same file. Symbols are included
in priority order: types and structs, macros, global variables, then helper
functions. Each symbol is formatted with a delimiter showing its location.
Inclusion stops when the token cap is reached.

**L3 (Repo Slice).**
L2 plus cross-file callers and callees from an approximate call graph.
We extract `call_expression` identifiers from function bodies and resolve
them using a name-based ambiguity rule: same file > same directory > unique
match anywhere > multiple matches (flagged as ambiguous). Non-ambiguous
edges are included first; ambiguous edges are appended last with explicit
labels. Hop-2 transitive callers/callees are included if token budget remains.

### Token Cap Invariant

All levels enforce a hard invariant: `tokens <= cap[level]`. Default caps
are 2,000 (L1), 6,000 (L2), and 15,000 (L3) tokens as measured by tiktoken
(`cl100k_base`). The caps are configurable. We enforce the cap by checking
token count after each symbol addition and stopping when the budget would
be exceeded. For oversized functions, we truncate at a line boundary rather
than mid-token.

### Provenance-Adaptive Level Selection

The starting level for each function is determined by its code provenance:

| Origin | Default Level | Rationale |
|---|---|---|
| `human` | L1 | Human code is typically well-integrated |
| `ai` | L2 | AI code may miss file-level context |
| `unknown` | L1 | Conservative fallback |

These defaults can be overridden by a policy file with per-CWE-family rules.
An escalation loop allows the detector to request more context: if detection
confidence falls below a threshold tau, context is rebuilt at the next level
up to a configurable budget cap.

### Provenance Detection

We determine code provenance from git commit metadata:
1. `Co-authored-by` trailers matching known bot patterns
2. Commit author names/emails matching bot conventions (e.g., `[bot]` suffix)
3. AI tool trailers (e.g., `Generated-by: GitHub Copilot`)
4. Configurable agent identities from `config/agents.yaml`

When metadata is ambiguous or absent (e.g., squash merges), the origin
defaults to `unknown`, triggering the conservative L1 starting level.

### Implementation

The pipeline is implemented in Python 3.11 using tree-sitter for parsing.
The repo index is cached to disk keyed by git commit hash for fast reloads.
All operations are deterministic: given the same commit and configuration,
the context output is identical across runs. No network calls are made
during context building; API keys are only used by detector adapters.

### Reproducibility

Each scan run records a configuration hash (covering caps, policy, and
tokenizer), enabling exact reproduction of context for any finding.
The `RunResult` data structure captures per-function timing, token counts,
and the list of included items for every detection run.
