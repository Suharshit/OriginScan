# Interface Changes Log
#
# DO NOT modify interfaces.py without logging the change here and notifying P2 and P5.
# See prd.md §7 Phase 1, rule 1.
#
# Format:
#   ## YYYY-MM-DD — Change title
#   - What changed
#   - Why
#   - Who was notified

## Initial freeze — Week 1, Day 5

- `Level`, `Origin`, `Context`, `Finding` TypedDicts defined
- `build_context`, `detect`, `choose_start` function signatures defined
- `DetectorAdapter` protocol defined
- Stub implementations provided
- P2 and P5 to acknowledge

## 2026-10-26 — `choose_start` stub delegates to policy.py

- What changed: the body of `interfaces.choose_start` now calls
  `default_policy().choose_level(origin, cwe_family)`. Signature, `ChooseStartFn` and
  all types are unchanged; the result is still L1 for every origin.
- Why: one start-level implementation only (`PolicyConfig.choose_level`), so the stub
  cannot drift from the policy (docs/decisions.md, 2026-10-26).
- Who was notified: P4 and P2 (to notify; no contract change)
