# Decision Log (P5)

One entry per decision, written the day it is made. Newest at the bottom.
Format: date · decision · rule/reason · where it lives.

| Decision | Rule | Decide by | Status |
| --- | --- | --- | --- |
| Grid row and input file formats | As listed in P5 Phase 1 | Oct 20 | Open |
| Data source | SecRepoBench; PrimeVul pairs if its format is unusable | Oct 22 | Open |
| Dev/test split | Repo is dev if hash(repo name) mod 5 = 0 | Oct 22 | Open |
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
