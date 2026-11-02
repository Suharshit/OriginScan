# Decision Log (P5)

One entry per decision, written the day it is made. Newest at the bottom.
Format: date · decision · rule/reason · where it lives.

| Decision | Rule | Decide by | Status |
| --- | --- | --- | --- |
| Grid row and input file formats | As listed in P5 Phase 1 | Oct 20 | Decided Oct 26 |
| Data source | SecRepoBench; PrimeVul pairs if its format is unusable | Oct 22 | Decided Oct 26 |
| Dev/test split | Repo is dev if hash(repo name) mod 5 = 0 | Oct 22 | Decided Oct 26 |
| Duplicate rule | Keep the copy that runs on real data, passes tests and matches the data model | — | Decided Oct 26 |
| `version_id`, `code_path`, AI base commit | `<slot_id>.<variant>`; `code_path` = stored body; AI bodies go into the fixing commit | — | Decided Oct 26 |
| Token caps | About the 95th percentile of measured sizes | Oct 25 | Open |
| Money cap | Cheapest of the 3 budget options that still covers RQ1–RQ3 | Oct 25 | Decided Nov 2 ($10) |
| Models | 2 detectors from different families; 2–3 generators; fits the cap | Oct 25 | Decided Nov 2 (cheap model after Kaggle pilot) |
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

### 2026-10-26 · AI versions get their own call graph for L3

- Bug found in `CorpusResolver` (#7): L3 took callers/callees from a CallGraph built
  over the original repo, which never sees an AI body. An AI body with a different
  line count was not found, so its L3 silently fell back to L2. One with the same line
  count was found, and got the human version's callees.
  Either way L3 was wrong for AI code only, which biases the origin × level comparison.
- Fix: `CorpusResolver.graphs_for(version_id, index, graph)`. AI versions get a copy
  of the repo index with only their file's symbols swapped, and a CallGraph rebuilt
  from it (cached per version). Human versions get the repo's own index and graph,
  after a check that the target is in the graph with the same text (catches an index
  built at the wrong commit). The runner must pass these to `build_context`.
- P4's index, call graph and builders are unchanged.
- Cost to measure in the Phase 2 token pilot: one full CallGraph build per AI
  version. If too slow on large repos, rebuild only edges touching the swapped file.

### 2026-10-26 · `version_id` format, `code_path` meaning, AI base commit

- `slot_id` = `srb-<SecRepoBench task id>`: one target function. The 318 task ids are
  unique and numeric. `version_id` = `<slot_id>.<variant>`, with variants
  `human-pre`, `human-post` and `ai-<gen>`, where `<gen>` is a generator key from
  `config/experiment.yaml`. Allowed characters: lowercase letters, digits, `-`,
  plus one `.` separator.
  - Reason: safe as a file name (no `:` or `/`, which matters on Windows); splits into
    slot and variant with one `split(".")`; built only from the source id, so stable;
    the `srb-` prefix leaves room for LLMVul rows (`llmvul-...`).
- `code_path` = path under `data/` to the version's function body:
  `bodies/<slot_id>/<variant>.c`. The source file comes from `repo` + `commit` +
  `file` in the clone under `paths.repos`, so `code_path` only has to locate the body.
  Human bodies are stored too (uniform rows; F7 copy check reads bodies directly;
  `make_slots.py` can check that a re-extracted body matches the stored one).
- AI bodies are swapped into the **fixing commit**, the same base as `human-post`.
  - Reason: SecRepoBench evaluates completions with the project at the fixing commit
    and uses the parent only to confirm the crash ("revert the project to the fixing
    commit state"), so plan B labels can reuse their setup. Each task's fix modifies
    only one function, so the fixing and parent repos differ only in the target
    function; the base choice does not change the surrounding context.
  - Source: SecRepoBench paper, arXiv 2504.21205v3.
  - First proposal was the parent commit; changed after checking the paper.
- Size: 318 slots, 636 commits (no two tasks share a fixing commit), 171 distinct
  files. With 2–3 generators, that is 1,272–1,590 versions.

### 2026-11-02 · Models, providers and money cap (open-weight only)

- **Rule:** open-weight models only, free tiers + self-hosting, so the study is reproducible
  and costs at most $10. Exact IDs copied from each provider's console on 2026-11-02.

| Role | Model ID | Provider | Free limit seen on Nov 2 |
| --- | --- | --- | --- |
| Generator g1 | `qwen/qwen3.8-27b` | Groq | 30 RPM, 1k req/day, 8k TPM, 200k tokens/day |
| Generator g2 | `models/gemma-4-31b-it` | Google AI Studio (own free key) | 30 RPM, 16k tokens/min, 14,400 req/day |
| Strong detector | `nvidia/nemotron-3-ultra-550b-a55b:free` (provisional) | OpenRouter | same; 1M context |
| Cheap detector | 7–14B Qwen coder (set after pilot) | vLLM on Kaggle 2× T4 | 30 GPU h/week, no token cap |

- **Why not Groq for the strong detector:** Groq's free tier allows 8k tokens per minute,
  and a request larger than that is refused. L3 contexts are capped at 15k tokens, so L3
  cannot run on Groq at all, and 200k tokens/day would need ~28 days for ~5.6M tokens.
  Groq is used for g1 (≈7k tokens per call) and for L1/L2 smoke tests only.
- **Why not Cerebras now:** API keys need a card on file before they work. Deferred; it
  stays the backup home for the strong detector (gpt-oss-120b) if OpenRouter fails.
- **Strong detector, option B chosen provisionally:** Nemotron 3 Ultra on OpenRouter with a
  one-time $10 top-up (1,000 req/day). A strong-detector run is ~900 calls, about one day.
  Option A (gpt-oss-120b on Cerebras) is a one-line config change if the team prefers it.
- **Families (for RQ4):** generators Qwen (g1) and Gemma (g2); detectors Qwen coder (cheap)
  and NVIDIA Nemotron (strong). Same-family pair: g1 × cheap. Cross-family: everything else.
- **Risks:** free OpenRouter models can be renamed or removed → generate all AI versions
  early and freeze them; record `provider`, `model_id` and date in every grid row.
  Free providers may log prompts → acceptable, all inputs are public CVE code.
- Money cap: `money_cap_usd: 10`. Removed `anthropic` and `google-genai` from the `exp` extras.
- Where it lives: `config/experiment.yaml` (`detectors`, `generators`, `providers`),
  `.env.example`, `docs/setup-models.md`.

**Smoke test, 2026-11-02 (`scripts/smoke_models.py --big`):**
- Nemotron 3 Ultra (OpenRouter) and Qwen 3.8 27B (Groq): OK.
- Groq refused an L3-size prompt: HTTP 413 "Request too large … TPM: Limit 8000,
  Requested 14400". Confirms: no L3 on Groq's free tier.
- `google/gemma-4-31b-it:free` returned HTTP 429 "temporarily rate-limited upstream"
  (Google AI Studio) on every retry → g2 switched to `google/gemma-4-26b-a4b-it:free`
  (same Gemma family, so the RQ4 family pairs are unchanged). If both stay busy, plug a
  free Google AI Studio key into OpenRouter (Settings → Integrations) or call it directly.
- The college Wi-Fi inspects HTTPS (certificate errors even with `truststore`); the test
  passed on a personal network. Run API jobs off campus or on Kaggle.
- The 26B free model on OpenRouter was also rate-limited upstream. Final for g2: **Gemma 4
  31B called directly on Google AI Studio with our own free key** (no card). Free limits
  seen Nov 2: 30 RPM, 16k tokens/min, 14,400 req/day; at ~7k tokens per generation that is
  ~2 calls/min, so 150 generations take ~75 minutes. Fastest of the three free providers.

