# Data Model (P5)

The four files the experiment reads and writes. Field lists are fixed by the P5
Phase 1 plan; change them only with an entry in [`decisions.md`](decisions.md).
File locations come from `paths:` in `config/experiment.yaml`; all of them sit under
the git-ignored `data/`.

| File | Written by | One row per |
| --- | --- | --- |
| `data/grid/*.parquet` | `exp/run.py` | detector call |
| `data/slots.csv` | `scripts/make_slots.py`, `exp/generate.py` | code version to scan |
| `data/labels.csv` | P3, or P5 by construction | code version |
| `data/split.csv` | `scripts/make_split.py` | repo |

Joins: grid → `labels.csv` by `version_id`; `slots.csv` → `split.csv` by `repo`.

## Grid row (one per detector call)

Python type: `CallRecord` in `exp/grid.py`, with the same fields in the same order
(checked by `tests/test_data_model.py`). Field types are defined there. P4's `Finding`
stays unchanged; the extra fields live in `CallRecord`.

```text
slot_id
version_id
origin
generator
repo
file
function
split
level
context_tokens
detector
model_id
prompt_version
run
pred_vulnerable
pred_cwe
pred_line
confidence
parse_ok
input_tokens
output_tokens
latency_ms
cost_usd
status
run_id
git_commit
config_hash
timestamp
```

- Labels are **not** in the row. They are joined later by `version_id`
  (`analysis/join_labels.py`), so detectors can run before any labels exist.
- One call is identified by (`version_id`, `detector`, `level`, `run`). Resume skips
  a call whose row already exists; `exp/grid.py check` lists any missing combination.
- Failed calls are still written, with their `status`, so missing data is visible.
- `parse_ok` is false when the reply could not be parsed; the run does not crash.

## `slots.csv`

```text
slot_id
version_id
origin
generator
repo
commit
file
function
cwe
cwe_family
code_path
```

- One row per version. Each AI version produced by `exp/generate.py` is a new
  `version_id` row.
- `repo` is lowercase `owner/name` (e.g. `mm2/little-cms`), made by `exp/corpus.py`
  `normalize_repo()` (decision of 2026-10-26). The same text appears in the grid and
  in `split.csv`, and it is the exact input to the split hash.

## `labels.csv`

```text
version_id
label_vulnerable
label_cwe
label_source
```

- Human versions are labelled by construction: pre-fix = vulnerable, post-fix = safe.
- AI-version labels come from P3, or from plan B (SecRepoBench security tests) if none
  exist by Nov 15.

## `split.csv`

```text
repo
split
```

- `repo` is the same lowercase `owner/name` text as in `slots.csv`.
- `split` is `dev` or `test`. A repo is dev if the SHA-256 of its `repo` text
  (UTF-8), read as an integer, mod 5 = 0 (decision of 2026-10-26). Columns are
  `SPLIT_COLUMNS` in `exp/corpus.py`.
- Frozen once tuning starts (`split.frozen: true` in `config/experiment.yaml`).
