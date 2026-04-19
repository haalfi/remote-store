# Research: OBS-003 Hand Decomposition (ID-147)

**Date:** 2026-04-19
**Status:** Hand-decomposition exercise; precedes any TLA+ authoring for
Observer.
**Scope:** Apply the spec-decomposition discipline from
[`sdd/formal/README.md`](../formal/README.md) § TLA+ as a spec-decomposition
discipline to OBS-003 (ObservedStore proxy), ahead of writing the TLA+
module. Establish the invariant shortlist and surface any latent spec
drift *before* the module is drafted.
**Related:** ID-147, [spec 019](../specs/019-ext-observe.md) § OBS-003,
OBS-003a, OBS-004, OBS-005, OBS-009; [ID-147b PoC](research-id-147b-tla-poc.md);
[`sdd/research/research-id-147-tla-augmentation.md`](research-id-147-tla-augmentation.md).

---

## 1. What bundling looks like in OBS-003

OBS-003 is a 9-step override recipe plus three postconditions. Adjacent
items (OBS-003a, OBS-004, OBS-005, OBS-009) add further hook-dispatch
and error-propagation constraints. Reading across those sections, the
claims that actually need to hold are interleaved, not listed.

Conjunction spots (the cheap "and"/enumeration spotter from the
authoring rule):

- OBS-003 step 6 *and* step 7 (per-op hook *and* on_any) on success.
- OBS-003 step 8 (on_error fires *and* re-raises).
- OBS-003 postconditions bundle three things: no arg/return mutation,
  after-hook exceptions suppressed, around exceptions propagate.
- OBS-009 bundles: original exception always re-raises, after-hook
  exceptions never mask the original, around is not suppressed.

Per the authoring rule, more than one independently falsifiable claim
means the spec item should decompose before review. OBS-003 clearly
crosses that threshold.

---

## 2. Spec-level drift surfaced by the exercise

**OBS-003 step 6 vs. OBS-004: does `on_<op>` fire on failure?**

- OBS-003's step-sequence reads as: steps 6–7 are the success branch,
  step 8 is the error branch. A strict reading says `on_<op>` fires
  only on success.
- OBS-004 states: "Each `on_<op>` callback receives a `StoreEvent`
  **after** the operation completes (success or failure)."
- Code (`observe.py:200-206`, `_fire`) fires the per-op hook
  unconditionally (no `error is None` guard), then on_any
  unconditionally, then on_error only when `error is not None`.

Code matches OBS-004. OBS-003's step list is textually compatible with
either reading; a reader choosing the "steps 6-7 success, step 8 error"
mental model would mis-describe the implementation.

**Finding:** OBS-003 step 6 should be rewritten to name the
outcome-independence explicitly (e.g. "Fires the matching `on_<op>`
callback (if set), regardless of success or failure"), or OBS-004's
sentence should be cross-referenced from step 6. This is a cheap spec
fix — probably the first win from the decomposition exercise, and it
already pays for the session.

Writing the TLA+ invariant would have forced the same choice. The
hand-decomposition surfaces it earlier, at no tooling cost.

---

## 3. Candidate invariant shortlist

Five claims decomposed from OBS-003 + OBS-003a + OBS-009, each
independently falsifiable by a one-line model mutation. The research
doc's original three (`EventBijection`, `HookRouting`, `NoDoubleDispatch`)
collapse `HookRouting` across two orthogonal axes (op class vs.
outcome) and merge `NoDoubleDispatch` into `EventBijection`; the split
below separates them.

| # | Invariant | Claim | Falsifying mutation |
|---|-----------|-------|---------------------|
| I1 | `EventPerCompletedOp` | For every inner-method call, exactly one `StoreEvent` is dispatched to `on_any` (if set) | skip on_any on the error branch; double-fire on_any |
| I2 | `RoutingByOpClass` | `on_<op>` routes per OBS-003a (read→on_read, write→on_write, ...) | route `read` to `on_write` |
| I3 | `HookOutcomeContract` | on_<op> and on_any fire regardless of outcome; on_error fires iff `error ≠ None` | fire on_error on success; skip on_<op> on failure |
| I4 | `ErrorAlwaysReraise` | The inner exception re-raises even if `on_error` (or any after-hook) raises | on_error raises → proxy raises that instead |
| I5 | `AfterHookExceptionIsolated` | A raising on_<op>/on_any/on_error leaves the observable result/exception of the operation unchanged | on_any raises on success → proxy raises that |

Orthogonality argument (pre-TLC, to be confirmed under break-and-catch):

- I1 partitions by "how many events fired" — independent of which hook
  buckets were touched.
- I2 partitions by "which hook was called" — independent of count.
- I3 partitions by "outcome × hook" — independent of routing correctness.
- I4, I5 partition by "what the hook did" (raise vs. not) — independent
  of I1–I3.

If break-and-catch later shows two invariants catch the same mutation,
merge them; that is itself a signal the underlying claims were not
actually independent.

---

## 4. What deliberately stays out of this module

- **Around context-manager semantics (OBS-005).** Around's
  `__enter__`/`__exit__` ordering vs. inner call, and around-exception
  propagation, is a different concern from dispatch/routing. If a TLA+
  invariant for it is written, it belongs in its own module
  (`OBS005Around.tla`), not bundled here. Decomposition rule: one
  concern per module.
- **BufferedObserver queueing (OBS-006).** Backpressure drop semantics
  are orthogonal to proxy dispatch. Out of scope for the OBS-003 module.
- **OTel bridge (OBS-011..014).** The bridge composes *with* the proxy
  but its attribute conventions are not dispatch-level properties.
- **WriteResult injection (OBS-015).** The WR-018 PoC
  (`WR018ProxyForwarding.tla`) already covers the proxy-forwarding
  shape. OBS-015 is the ObservedStore-side mirror; modelling it here
  would duplicate the PoC. Cross-link, do not reimplement.

---

## 5. Module plan

**Single module, five invariants:** `Observer.tla` under
`sdd/research/tla-poc/` (PoC staging; promotion to `sdd/formal/tla/`
follows the authoring rule — *after* a real regression catch). Shadows
OBS-003 + OBS-003a + OBS-009.

Expected model size: small. States are `(op ∈ OpSet, outcome ∈
{success, error}, hookRaised ∈ {none, on_any, on_op, on_error}) →
observedEvents`. With `OpSet = {read, write, delete}` and three hook
buckets, TLC enumeration should finish in seconds (same order as the
PoC's 116-state WR-018 model).

**Break-and-catch matrix to populate after authoring** (mirrors PoC §2.2):

| Break | Expected invariant | Others expected |
|---|---|---|
| Skip `on_any` on error path | `EventPerCompletedOp` | — |
| Route `read` to `on_write` | `RoutingByOpClass` | — |
| Fire `on_error` on success | `HookOutcomeContract` | — |
| `on_error` suppresses inner raise | `ErrorAlwaysReraise` | — |
| `on_any` raise masks inner result | `AfterHookExceptionIsolated` | — |

If any row triggers more than one invariant, those invariants are not
orthogonal and the decomposition needs another pass.

---

## 6. Deliverables from this note

1. **Spec fix (pre-TLA+):** clarify OBS-003 step 6 with outcome
   independence, or cross-reference OBS-004. Small edit; ride the ID-147
   PR.
2. **TLA+ module:** `Observer.tla` + `MC_Observer.tla` + `MC_Observer.cfg`
   in `sdd/research/tla-poc/` implementing I1–I5.
3. **Break-and-catch table:** populate § 5 after the model runs green.
4. **Rescope ID-147 backlog item:** drop `Backend.tla` + `Store.tla`
   (abstract-layer targets the authoring rules now discourage); keep
   `Observer.tla` as the one concrete target; add informational
   `verify-tla` CI step as a sibling deliverable.

---

## 7. What the exercise cost and whether it paid

Time: ~30 minutes (read OBS-003 + adjacent sections, skim code to
resolve ambiguity, draft the invariant table). The payoff is the § 2
drift finding — surfaced before any TLA+ was written, at effectively
zero cost. On that evidence alone, the hand-decomposition step belongs
*before* any Specula-assisted authoring or direct TLA+ drafting: once
the decomposition is explicit, mechanical translation is a smaller,
safer task.
