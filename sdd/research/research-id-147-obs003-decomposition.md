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

Claims decomposed from OBS-003 + OBS-003a + OBS-009, each independently
falsifiable by a one-line model mutation. The research doc's original
three (`EventBijection`, `HookRouting`, `NoDoubleDispatch`) collapse
`HookRouting` across two orthogonal axes (op class vs. outcome) and
merge `NoDoubleDispatch` into `EventBijection`; the split below
separates them.

This section was drafted with five invariants. Break-and-catch (§ 8)
showed I3 bundled two independently-falsifiable claims and I3 is now
listed as I3a/I3b below, giving six invariants total.

| # | Invariant | Claim | Falsifying mutation |
|---|-----------|-------|---------------------|
| I1  | `EventPerCompletedOp` | For every inner-method call, exactly one `StoreEvent` is dispatched to `on_any` (if set) | skip on_any on the error branch; double-fire on_any |
| I2  | `RoutingByOpClass` | `on_<op>` routes per OBS-003a (read→on_read, write→on_write, ...) | route `read` to `on_write` |
| I3a | `ClassHookOutcomeIndependent` | `on_<op>` fires for every call whose op is in that class, irrespective of outcome | skip class hook on the error branch |
| I3b | `ErrorHookFiresOnErrorOnly` | `on_error` fires for every error call and only for error calls | fire on_error on success; skip on_error on failure |
| I4  | `ErrorAlwaysReraise` | On every error call, the caller observes an error (structural shadow of OBS-009 at this model's level of detail) | visible outcome becomes success on an inner error |
| I5  | `AfterHookExceptionIsolated` | On every success call, the caller observes a success (structural shadow of the OBS-003 after-hook isolation postcondition) | visible outcome becomes error on an inner success |

I4 and I5 are *structural* invariants: the current `Call` action has no
`HookRaise` sub-action, so they check that the action body couples
`visible_outcomes` to `outcome`, not that a raising after-hook is
behaviourally suppressed. A faithful behavioural encoding of OBS-009 /
the after-hook isolation postcondition would add a non-deterministic
`HookRaise(i)` action that may attempt to alter the visible outcome,
and the invariants would assert that the visible outcome is still the
inner outcome regardless. That strengthening is deferred to a
follow-up if a real regression surfaces (`sdd/formal/README.md`
rule 3).

Orthogonality argument (confirmed under break-and-catch, § 8) — note
"orthogonal" below means "the seeded mutations do not overlap," not
that the underlying physical claims are fully independent:

- I1 partitions by "how many events fired" — independent of which hook
  buckets were touched.
- I2 partitions by "which hook was called" — independent of count.
- I3a and I3b each partition the outcome×hook space along one axis
  (per-op hook vs. error hook); a mutation on either axis leaves the
  other untouched.
- I4 and I5 partition by inner outcome (error path vs. success path);
  an error-path mutation and a success-path mutation trigger only
  their own invariant.

If break-and-catch had shown two invariants catching the same mutation,
the right response would be to merge them — itself a signal the
underlying claims were not actually independent at the seeded-mutation
level.

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

**Single module, six invariants:** `Observer.tla` under
`sdd/formal/tla/` (the live informal TLA+ layer — physical location is
decoupled from CI gate status; the `sdd/research/tla-poc/` tree is the
frozen 2026-04 PoC and stays as a historical artefact). Covers OBS-003
step 6/7 + OBS-003a dispatch routing at the checked level; OBS-009 is
shadowed only structurally (see module header *Scope caveat*).

Expected model size: small. States are `(op ∈ OpSet, outcome ∈
{success, error}) → five append-only sequences (inner_calls,
any_events, class_events[class], error_events, visible_outcomes)`.
With `OpSet = {read, write, delete}` and three hook buckets, TLC
enumeration finishes in well under a second (259 distinct states at
depth 4 for `MaxCalls = 3`).

The original plan included a `hookRaised ∈ {none, on_any, on_op,
on_error}` dimension to model OBS-009's "after-hook raises but inner
outcome is re-raised" directly. The shipped `Observer.tla` omits it —
`Call` is a single atomic transition with no hook-raise sub-action, so
I4 and I5 check the structural property `visible == inner` on each
path rather than the behavioural OBS-009 claim (see module header's
*Scope caveat* paragraph). Adding `HookRaise` is deferred until a real
regression motivates it (ID-150 revisit).

See § 8 for the actual break-and-catch log populated as each invariant
landed. Each row triggered exactly one invariant at minimum depth.

---

## 6. Deliverables from this note

1. **Spec fix (pre-TLA+):** clarify OBS-003 step 6 with outcome
   independence, or cross-reference OBS-004. Small edit; ride the ID-147
   PR.
2. **TLA+ module:** `Observer.tla` + `MC3.tla` + `MC3.cfg`
   in `sdd/formal/tla/` implementing I1, I2, I3a, I3b, I4, I5.
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

---

## 8. Break-and-catch log

Populated as each invariant lands. Format mirrors
[research-id-147b-tla-poc.md](research-id-147b-tla-poc.md) § 2.2.

| Break | Module change | Invariant triggered | Others triggered | Depth |
|---|---|---|---|---|
| Skip `on_any` append unconditionally | `any_events' = any_events` | `EventPerCompletedOp` | — | 2 |
| Misroute to non-matching class bucket | `![CHOOSE c : c # ClassOf[op]]` in `Call` | `RoutingByOpClass` | — | 2 |
| Skip per-op hook append on error | `class_events' = class_events` when `outcome = "error"` | `ClassHookOutcomeIndependent` | — | 2 |
| Fire `on_error` on success instead of error | `outcome = "success"` guard on `error_events` append | `ErrorHookFiresOnErrorOnly` | — | 2 |
| Emit `"success"` on the error visible-outcome path | `visible_outcomes' = Append(visible_outcomes, "success")` | `ErrorAlwaysReraise` | — | 2 |
| Emit `"error"` on the success visible-outcome path | `visible_outcomes' = Append(visible_outcomes, "error")` | `AfterHookExceptionIsolated` | — | 2 |

All rows landed. Each break triggers exactly one invariant at minimum
depth 2; no collapses. The decomposition holds under TLC.

Reconciliation with § 3: the original shortlist listed five invariants,
but break-and-catch confirmed that I3 (`HookOutcomeContract`) bundled
two independently-falsifiable claims. The module splits them as
`ClassHookOutcomeIndependent` (I3a) and `ErrorHookFiresOnErrorOnly`
(I3b), giving six invariants in `Observer.tla`: I1, I2, I3a, I3b, I4,
I5. The I4/I5 seeded mutations partition cleanly along the
inner-outcome axis (error-path vs. success-path). The caveat flagged
in § 3 stands: without a `HookRaise` sub-action in the model, the
"orthogonality" here is at the level of the seeded mutations, not at
the level of the OBS-009 / after-hook-isolation claims the module's
header text shadows.
