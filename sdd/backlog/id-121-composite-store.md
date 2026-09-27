# ID-121 — CompositeStore (research complete)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 4](../BACKLOG.md#no-workarounds) by the ADR-0040 § 4
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`CompositeStore(Store)` — core Store subclass (not extension) that composes
multiple stores into one. Deterministic fallthrough resolution for reads, union
LIST (deduplicated), writes to primary tier only. The one genuinely new
user-facing capability in this file, and one a user cannot cheaply build
themselves.
- [Research](../research/research-sqlalchemy-backend.md#52-compositestore-id-120)
  (anchor uses historical ID-120 from research doc; now ID-121 after swap)
- Depends on: unified `resolve()` → `ResolutionPlan` (ID-120) — **satisfied**:
  `Store.resolve()` ships and returns a `ResolutionPlan` (see BACKLOG-DONE.md).
  Remaining: at least two working backends to be useful; pairs well with
  ID-119 (landed) — so both conditions are already met.
- Next: design as a separate spec — backend-agnostic, useful independently.
- **Cache-key derivation from `ResolutionPlan`** (was ID-123, absorbed here).
  `ext.cache` should derive cache keys from `ResolutionPlan` fields instead of
  ad-hoc `(operation, path)` tuples (RES-100, proposed in
  [043](../specs/043-resolution-plan.md)). Single-backend cache keys are already
  correct *for the default per-store cache*, so this is only valuable once
  composition exists. **The one case that was reachable today is now
  BUG-251** in section 2: it reproduced, so it is a defect rather than a
  motivating example, and it is filed where declining CompositeStore cannot
  retire it. Keep it in view when designing here — identity-derived keys are
  the wide fix for it, and this is where that scheme gets decided.

## Re-measured, 2026-09-27

Unchanged. `rg -l CompositeStore src` finds nothing. `Store.resolve()` is at
`src/remote_store/_store.py:908`; ID-120 and ID-119 are `[x]` in
`BACKLOG-DONE.md` (`rg -n 'ID-119|ID-120' sdd/BACKLOG-DONE.md`). The research
link's anchor resolves to `### 5.2 CompositeStore (ID-120)` in
`research-sqlalchemy-backend.md`. RES-100 is still Phase 2 in
`043-resolution-plan.md:261`, and BUG-251 is open in § 2. Found by the
ADR-0040 § 4 conversion.
