# Decision Log (P5)

One entry per decision, written the day it is made. Newest at the bottom.
Format: date · decision · rule/reason · where it lives.

| Decision | Rule | Decide by | Status |
| --- | --- | --- | --- |
| Grid row and input file formats | As listed in P5 Phase 1 | Oct 20 | Decided Oct 26 |
| Data source | SecRepoBench; PrimeVul pairs if its format is unusable | Oct 22 | Decided Oct 26 |
| Dev/test split | Repo is dev if hash(repo name) mod 5 = 0 | Oct 22 | Decided Oct 26 |
| Duplicate rule | Keep the copy that runs on real data, passes tests and matches the data model | — | Decided Oct 26 |
| Token caps | About the 95th percentile of measured sizes | Oct 25 | Open |
| Money cap | Cheapest of the 3 budget options that still covers RQ1–RQ3 | Oct 25 | Open |
| Models | 2 detectors from different families; 2–3 generators; fits the cap | Oct 25 | Open |
| Confidence signal for escalation | 3-run agreement, same as the study | Oct 25 | Open |
| Embedding model for D3 | Best same-CWE top-3 hit rate on dev | Nov 8 | Open |
| Start plan B labels? | Only if no AI labels exist by Nov 15 | Nov 15 | Open |
| τ, λ, P-Origin, test size | Tuned on dev only | Nov 29 | Open |
| Run RQ4? | Only if money remains after Sprint 9 | Dec 13 | Open |
| What goes in `policy.yaml` | Best accuracy at equal budget; confidence-only if origin doesn't help | Dec 27 | Open |

## Entries

### 2026-10-17 · Repo and environment setup

- Created `main` from `contextTool` (no `main` existed) and the `p5` working branch.
- CI now runs on every branch and installs the `exp` and `analysis` extras; `rag` is
  left out of CI because it pulls torch.
- P5 dependencies are optional extras in `pyproject.toml` (`exp`, `rag`, `analysis`,
  or `p5` for all three). numpy and scipy keep lower bounds that still resolve on
  Python 3.11 (numpy 2.5 and scipy 1.18 dropped 3.11). Exact versions get frozen in
  the replication lockfile (Phase 7).
- Local dev uses Python 3.12 in `.venv`.

### 2026-10-26 · Gate 1 data source: SecRepoBench, PrimeVul pairs as fallback

- The corpus is SecRepoBench (318 tasks, 27 C/C++ repos). Each task records its repo,
  commit, target function and CWE, which map directly onto `slots.csv`.
- Fallback: PrimeVul's paired functions (pre-fix and post-fix), used only if
  SecRepoBench's format turns out to be unusable for `scripts/make_slots.py`. A switch
  gets its own entry here.
- Human-version labels come from construction: pre-fix = vulnerable, post-fix = safe.
- Source file pinned: Hugging Face `ai-sec-lab/SecRepoBench`, revision
  `ee16f4324e13bccfc84482dd9689a3190d016833`,
  `data/code_completion-00000-of-00001.parquet` (318 rows, 27 repos), sha256
  `f84953e29cb607e439aa7e7b8ca002c5e7b6ecf46a9315054887e1c3696ec0b1`. Stored
  (git-ignored) at `data/raw/secrepobench/code_completion.parquet`.
- Lives in: `scripts/make_slots.py` → `data/slots.csv`.

### 2026-10-26 · Dev/test split: repo is dev if hash(repo name) mod 5 = 0

- Split by repo, not by function, so functions from one repo never sit on both sides.
  Expect about 20% of repos in dev.
- Repo names are normalised to lowercase `owner/name` (e.g. `imagemagick/imagemagick`).
  The same normalised form is written to the `repo` column of `slots.csv` and
  `split.csv`, so the two files always join exactly. Rule for SecRepoBench's
  `repo_addr`: drop the host, a trailing `/` and `.git`; owner and name are the last
  two path segments (`git://git.code.sf.net/p/matio/matio` → `matio/matio`); a
  single segment is used as both (`git.ffmpeg.org/ffmpeg.git` → `ffmpeg/ffmpeg`).
  Code: `exp/corpus.py` `normalize_repo()`; both scripts must import it.
- The hash is pinned so the split is reproducible: SHA-256 of the normalised repo name
  as UTF-8, read as an integer —
  `int(hashlib.sha256(repo.encode("utf-8")).hexdigest(), 16) % 5 == 0` → dev, else test.
  Python's built-in `hash()` is not used because it is randomised per process.
- All tuning (prompts, caps, τ, λ, P-Origin) uses dev only; test is not looked at
  until the Phase 6 values are committed.
- Lives in: `data/split.csv` (`repo`, `split`). **Frozen once tuning starts:** after
  that, the file is never regenerated or edited, even if the rule or the repo list
  changes. Repos added later get a new entry here before they are used.
  Mechanism: set `split.frozen: true` in `config/experiment.yaml` and
  `scripts/make_split.py` refuses to rewrite the file.
- First result (2026-10-26, not frozen yet): 8 of 27 repos in dev (29.6%), 126 of 318
  slots (39.6%). Dev: blosc/c-blosc2, ffmpeg/ffmpeg, file/file, gnome/libxml2,
  imagemagick/imagemagick (50 slots), libredwg/libredwg, mm2/little-cms, php/php-src.
  split.csv sha256 `021a5833b249710e0e0e6fa1826f337aa96caab25bf13cee86e2dfe2ee45c719`.
  Above the ~20% target. **Kept as is (2026-10-26):** the rule was fixed before the
  result was seen; changing it to hit a share would be tuning by outcome. Test keeps
  192 slots, enough for the 150-slot candidate size. Freezes when tuning starts.

### 2026-10-26 · Duplicate rule: which copy to keep when two exist

- If two copies of something exist (corpus, split, labels, resolver, `choose_start`,
  or any other piece), keep the one that:
  1. runs on real data,
  2. passes tests, and
  3. matches the data model (`docs/data-model.md`).
- The paper and the tool use only the kept copy. Each time the rule is applied, add an
  entry here naming both copies, which one was kept, and why.

### 2026-10-26 · Grid row and input file formats

Formats defined in docs/data-model.md. After the first real run, fields can be added but not renamed or removed.

### 2026-10-26 · One `choose_start`, default all-L1 (duplicate rule applied)

- Three copies existed: `PolicyConfig.choose_level` in `policy.py` (reads `policy.yaml`,
  CWE overrides; used by `scan`), `choose_start` in `runner.py` (own `DEFAULT_POLICY`
  dict, human→L1, ai→L2), and the stub in `interfaces.py` (always L1).
- Kept: `PolicyConfig.choose_level`. It is the only one that reads the real policy
  file and CWE overrides, and the CLI already uses it. `runner.choose_start` and
  `interfaces.choose_start` now delegate to it with unchanged signatures;
  `runner.DEFAULT_POLICY` is removed.
- Default is now all-L1 (confidence-only). Sending AI code to L2 by default assumed
  an answer to RQ3 before the study gives one. Origin-aware start levels come only
  from a `policy.yaml` exported in Phase 8.
- P4's tests that expected AI→L2 by default now expect L1; tests of policy plumbing
  use an explicit origin-aware policy instead of the default.
