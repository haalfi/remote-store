# Research: TLA+ PoC — WriteResult Spec Consistency (ID-147b)

**Date:** 2026-04-18
**Status:** PoC complete; feeds [PR 450](https://github.com/haalfi/remote-store/pull/450) review.
**Scope:** A deliberately minimal TLA+ spike targeting ID-146's `WriteResult`
landing (spec 045), evaluating TLA+ as both a bug-finder and a
spec-decomposition discipline.
**Related:** [ID-146](../BACKLOG.md), [PR 450](https://github.com/haalfi/remote-store/pull/450),
[spec 045](../specs/045-write-result.md),
[spec 001](../specs/001-store-api.md),
[spec 003](../specs/003-backend-adapter-contract.md),
[RFC-0011](../rfcs/rfc-0011-write-result.md).

**Context.** The ID-146 spec round was long and mixed human/AI review
still left latent spec bugs. Markdown specs grow expressive faster than
they grow checkable: a single item like WR-018 can bundle four
independent claims behind one paragraph, and a reviewer (human or AI)
has no mechanical way to confirm they've checked each claim in
isolation. This PoC asks whether a minimal TLA+ layer — one module per
spec concern — can address both problems at once: catch bugs, and
force the spec into smaller, non-contradicting pieces.

---

## 1. PoC scope

Two modules, one invariant table each, deliberately disjoint:

| Module | Targets | Invariants |
|---|---|---|
| `WriteHeadRoundTrip.tla` | spec 045 § WR-006, WR-008 (field mapping only; gating not modelled) | `WriteHeadAgree`, `HeadIsSidecar` |
| `WR018ProxyForwarding.tla` | spec 045 § WR-018 | `ProxyForwardUnchanged`, `PostWriteCacheNotTracked`, `EventPerWrite` |

Both run under a single TLC image built by `scripts/tlc_check.sh` (Docker
wrapper, no local Java, no local jar). First-run image build ≈ 15 s;
subsequent runs ≈ 3 s end-to-end for either model.

Everything outside this scope (async, errors beyond `CapabilityNotSupported`,
backend-specific variants, multi-writer interleaving, the rest of
spec 045) is explicitly deferred — the point is to evaluate the
approach on the smallest useful target, not to cover the spec.

## 2. Results

### 2.1 Green runs

| Model | Distinct states | Depth | TLC runtime | All invariants |
|---|---|---|---|---|
| `MC` (WriteHead) | 1092 | 5 | <1 s | hold |
| `MC2` (WR-018) | 116 | 4 | <1 s | hold |

### 2.2 Break-and-catch

Each break mutates one line of the TLA+ model to violate exactly one
invariant; TLC should produce a counterexample at minimum depth and
report only the violated invariant. If the reported error set is larger
than one invariant, the invariants are redundant (a signal that the
spec items they came from are not actually independent).

| Break | Module change | Invariant triggered | Others triggered | Depth |
|---|---|---|---|---|
| Drop WR-008 rename (`last_modified ← fi_size`) | `HeadResult.last_modified` | `WriteHeadAgree` | — | 2 |
| Wrong `source` (`BASIC` instead of `SIDECAR`) | `HeadResult.source` | `HeadIsSidecar` | — | 2 |
| Proxy mutates on forward (+1 to size) | `wr_c = [wr_b EXCEPT !.size = ...]` | `ProxyForwardUnchanged` | — | 2 |
| Skip cache invalidation | `cache_paths' = cache_paths` | `PostWriteCacheNotTracked` | — | 2 |
| Skip event emission | `events' = events` | `EventPerWrite` | — | 2 |

Every break surfaced its target invariant and no others at the minimum
possible depth (one Write). `WriteHeadAgree` and `HeadIsSidecar` are
deliberately disjoint — the data-field break and the source break each
trigger exactly one. The five invariants are mutually independent.

## 3. Findings

### 3.1 TLA+ as a bug finder

TLC caught every deliberate bug at the first opportunity. That is not
an achievement — the bugs were seeded to be catchable — but it
establishes that the model is actually checking what the invariant
names claim it checks. With that baseline, the model becomes
useful for regressions a reviewer could miss: the WR-008 field rename
is easy for a human to transcribe wrong into Python; the proxy
forwarding contract is easy to violate accidentally when a proxy layer
adds ergonomic features; cache invalidation is the class of bug that
only surfaces on a second read.

### 3.2 TLA+ as a spec-decomposition discipline

The more interesting finding is what writing the TLA+ module surfaced
about the Markdown spec.

**WR-018's Markdown is one paragraph. Its TLA+ encoding surfaces four
distinct claims.** Three are independently checkable TLC invariants;
the fourth is trivially enforced by the action's constructor:

1. Return-type widening — trivially enforced: `MkWR` always produces a
   record with the expected domain; no reachable state can violate it.
   Noted for completeness; not a TLC invariant.
2. Unchanged forwarding (`ProxyForwardUnchanged`) — independently breakable.
3. Post-write cache state (`PostWriteCacheNotTracked`) — independently breakable.
4. Event emission (`EventPerWrite`) — independently breakable.

The break-and-catch table above is the empirical evidence: breaks for
(2), (3), (4) each trigger exactly one invariant without disturbing the
others. An independent failure mode per claim is the definition of
"this is really multiple specs pretending to be one".

A secondary observation: WR-018's phrase *"never substitute, mutate,
or synthesise fields"* collapses in TLA+ to a single field-wise
equality. The three verbs are stylistic emphasis, not independent
content. The cost of that emphasis in a Markdown-only world is zero;
the cost in a world where reviewers are counting claims is a false
signal that there are three things to check.

### 3.3 Combined consequence

The two findings reinforce each other: the bugs TLC catches are easier
to think about precisely because the invariants they violate have
names. A spec item that bundles four claims under one label gives
reviewers — human or AI — no hooks to attach verification to. A spec
item that maps 1:1 to one named invariant can be reviewed as "is this
invariant correctly stated, and did the code preserve it?" The
TLA+ translation is the forcing function that produces the named hooks.

## 4. Recommendations

### 4.1 Feeding the PR 450 review

PR 450's three-module plan (`Backend`, `Store`, `Observer`) is right in
principle but over-scoped for a first commitment. Based on this PoC's
data points:

- **Keep the one-module-per-concern rule, drop the three-module
  hierarchy.** `EXTENDS` composition was not needed to express either
  invariant in this PoC; stand-alone modules were cleaner.
- **Target spec items with demonstrable bundling, not abstract layers.**
  WR-018 was a concrete win because it had four visibly independent
  claims. "Capability gate ordering" in the abstract does not.
- **Scope CI enforcement to modules that have survived break-and-catch.**
  Until a module demonstrates independent invariants (as these two did),
  its CI value is aspirational.

### 4.2 Proposed repo workflow

A lightweight rule that this PoC's data supports:

> When adding a normative spec item with more than one conjunction in
> its Markdown statement, write the corresponding TLA+ invariant
> first. If the invariant decomposes into independent top-level
> conjuncts, split the spec item into that many sub-items *before*
> review.

This is cheap (the TLA+ need not be verified to pay off — just
written), mechanical (the count of top-level conjuncts is
objective), and addresses the problem the ID-146 round surfaced:
long spec PRs with bundled claims that survive review.

### 4.3 Not recommended

- Promoting `sdd/research/tla-poc/` to `sdd/formal/tla/` until at least
  one TLA+ check would have caught a historical spec bug on a real
  branch. A seeded break is evidence the tool works; a caught
  regression is evidence the workflow pays.
- CI gating. The existing Dafny job is optional for a reason; adding a
  mandatory TLA+ gate on the back of a two-module PoC would be
  over-confident.
- Larger models covering more of spec 045 in one file. The
  decomposition argument cuts against it.

## 5. Limitations

- **Bounded models.** TLC's guarantees are finite-state. `MaxClock=4`
  with two paths and two data sizes enumerates cleanly; scaling
  constants changes runtime from milliseconds to minutes.
- **WR-008 gating not modelled.** WR-008 requires `head()` to raise
  `CapabilityNotSupported` when the backend lacks `METADATA`. Because
  `HeadResult` is a pure function (not an action), the capability gate
  cannot be expressed as a reachability property in this module.
  Only the field-mapping half of WR-008 is checked.
- **PostWriteCacheNotTracked is stronger than WR-018.** The model has
  no `Read` action, so a legitimate post-read cache re-population
  cannot happen. The invariant therefore bans tracking a written path
  forever, not just at write time.
- **No async.** Spec 029 (async Store API) is not modelled; async
  concurrency is the regime where TLC's interleaving enumeration is
  most valuable, and also where authoring cost is highest.
- **Translation risk.** A TLA+ module can be internally consistent
  and still misrepresent the Markdown. This PoC mitigated it by
  seeding deliberate bugs and confirming TLC caught them at minimum
  depth; it does not eliminate it.

## 6. Artefacts

- `sdd/research/tla-poc/WriteHeadRoundTrip.tla` + `MC.tla` + `MC.cfg`
- `sdd/research/tla-poc/WR018ProxyForwarding.tla` + `MC2.tla` + `MC2.cfg`
- `scripts/tlc.Dockerfile`, `scripts/tlc_check.sh`
- Run: `bash scripts/tlc_check.sh sdd/research/tla-poc MC`
  or `... MC2`
