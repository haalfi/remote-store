# Research: User-Expectation-Driven Discovery of Source & Doc Gaps

**Date:** 2026-06-14
**Status:** Proposal (methodology); one instance executed (Graph concurrency review)
**Scope:** A repeatable methodology for finding the places where remote-store
behaves, fails, or reads differently from what a reasonable user expects —
across the whole expectation surface, not one lens at a time — and routing each
divergence to the right adaptation (code, spec, docs, or cross-backend
conformance).
**Related:** [TESTING.md](../TESTING.md), [spec 048 (testing architecture)](../specs/048-testing-architecture.md),
[research-bug-prevention-beyond-testing.md](research-bug-prevention-beyond-testing.md),
[audit-016 (Graph backend review)](../audits/audit-016-graph-backend-review.md),
`sdd/BACKLOG.md` § Graph (BK-287..292, BUG-219).

**Context:** A user reaches for remote-store carrying a mental model — from real
filesystems, from `dict`, from `pathlib`, from the native cloud SDK, from the
*other* backends they already use. Where the library quietly violates that
model, they hit a surprise. The conformance suite does not catch these, because
a conformance test encodes *the library's* assumed behavior, not *the user's*
expectation — and a cassette/mock encodes the assumed response shape, not the
real service's. The Graph backend concurrency review (a FastAPI app sharing one
store, exercised live "go hard") surfaced real divergences exactly here — an
`aclose()`-during-shutdown `RuntimeError`, an `overwrite=True` conflict on
consumer OneDrive, an unspecified concurrency contract, and a stale ADR. But
concurrency was only *one* way to probe expectations. This document generalizes
that single success into a method, because the expectation space is broad and we
can otherwise only guess at it.

---

## 1. The problem: the expectation surface is open-ended

We cannot enumerate every expectation a user holds — there are too many, and
many are implicit. Ad-hoc review depends on whoever happens to think of the
right angle on the right day (concurrency surfaced because someone pictured a
FastAPI app). That is not a method; it is luck with good instincts.

The reframe that makes it tractable: **an expectation always comes from a
*source*, and the sources are enumerable even though the expectations are not.**
A user assumes a behavior because it is *like* something they know, because a
*doc promised* it, because the *API shape* implies it, or because a *sibling*
(another backend, the sync twin) does it that way. Walk the sources, and each
one mass-produces concrete candidate expectations. You stop brainstorming and
start *generating*.

---

## 2. The lens catalog — the generators

Each lens is a question-template that emits a checklist of candidate
expectations. The catalog is the durable asset; concurrency is what two of these
lenses produce when pointed at an async backend. Grounded in findings this repo
has actually shipped, so the lenses are concrete rather than abstract:

| Lens | Generator question | Real evidence (what it found / would find) |
|------|--------------------|---------------------------------------------|
| **Analogy** | "A user expects this to behave like ⟨real filesystem · `dict` · `pathlib` · the sync `Store` · the *other* backends · the native SDK · the OneDrive web UI⟩." | `overwrite=False` ≈ `O_EXCL` create-if-absent (held ✓); `move` ≈ atomic rename (✗ — `ATOMIC_MOVE` withheld, under-surfaced at point of use) |
| **Doc-promise** | "Every example, every `Returns:`/`Raises:`, every capability claim, every guide sentence *is a contract* — is it true today?" | async-guide snippet that raised `RuntimeError`; the BK-261 overwrite-409 caveat scoped "SharePoint-only" when it also fires on consumer OneDrive; `explanation/concurrency.md` over-generalizing TOCTOU to "all backends" |
| **API-surface / edge** | "For each public method × {empty · huge · missing · already-exists · wrong-type · unicode · boundary sizes · trailing slash · `..`} — what would a reasonable user assume?" | `copy_timeout=None` unbounded; range/seek boundaries; edge-input rejection gaps (cf. the 0.21.1 bug taxonomy) |
| **Cross-consistency** | "Same operation across backends, sync vs async, `Store` vs `Backend` — do they *agree*? A divergence is either a bug or an undocumented surprise." | the bridged-sync-is-safe-but-SFTP-is-not asymmetry (true, but documented nowhere); per-backend error-fidelity drift (a move-race loser raising generic `RemoteStoreError` vs typed `NotFound`) |
| **Persona / workflow** | "Walk one persona's end-to-end journey (FastAPI app · data pipeline · notebook explorer · Dagster job · CLI tool) and flag every point behavior could surprise *them*." | concurrency (the FastAPI shared-store persona) — the originating instance |
| **Failure-mode** | "For each op, enumerate plausible real failures (network drop · throttle · auth-expiry · partial write · conflict · quota · mid-stream mutate) — typed? documented? recoverable?" | the copy/move monitor hanging on a `4xx` poll (fixed as BUG-218); token-expiry; mid-stream delete |
| **Lifecycle / resource** | "Construct · reuse · share · close · use-after-close · context-manager · cleanup — any surprise?" | `aclose()` during in-flight ops raising an untyped `RuntimeError` (filed BUG-219) |
| **Scale / performance** | "Large files · many files · deep trees · huge listings · streaming — does the mental model survive volume?" | connection-pool saturation; spool I/O head-of-line-blocking the event loop |

The catalog is seeded by reasoning and *grown by reality* (§6): every real
support question, issue, and surprise becomes a new row, so over time the method
tests *observed* expectations, not only imagined ones.

---

## 3. The pipeline

1. **Broad sweep** (cheap, mostly static): apply *every* lens *shallowly* — one
   or two candidates each — to one target (a backend, an extension, the Store
   API). Read source and docs; produce a heatmap of which lenses look fragile.
2. **Prioritize**: rank candidates by **expectation-strength × blast-radius ×
   hit-likelihood** (how confidently a reasonable user assumes it × how badly
   they are burned × how often they would hit it).
3. **Deep-dive** the hot lenses. For behavior that depends on the real service,
   this is a live "go hard" battery against a throwaway account (the shape the
   concurrency review used); for static or contract claims, it is source reading
   plus deterministic probes. **Predict the expected behavior before testing** —
   the run is hypothesis-testing, not confirmation-seeking. (In the concurrency
   review this discipline caught a *wrong* prediction: the assumed "token
   stampede" was actually an event-loop block.)
4. **Classify** each divergence into exactly one bucket — this is the output that
   *names the area needing adaptation*: **bug** (code) · **spec-gap** (sdd) ·
   **doc-gap** (docs) · **cross-backend-inconsistency** · **by-design /
   needs-disclosure**.
5. **Route** the adaptation (§4) and record it as an `sdd/audits/` doc plus
   backlog items.

The engine is the existing orchestrate panel, but organized **by lens, not by
domain** — each agent works one lens, which parallelizes naturally and maps to
the generators rather than to file ownership.

---

## 4. Routing: where adaptations land

A divergence is only useful if it changes something durable. Route by reusing
the test tiers spec 048 already defines, so a finding is not re-discovered:

| Finding kind | Lands in |
|--------------|----------|
| Backend-agnostic behavioral expectation (create-once race, read-after-write, aclose-during-inflight, bridge concurrency) | the **cross-backend conformance spine** (`tests/backends/conformance/`), so it runs for *every* backend forever — deterministically where possible |
| Backend-specific server-semantics (real throttling, real conflict arbitration, listing lag) | the per-backend **live tier** + a re-runnable harness, milestone-gated |
| Citizen-dev "does the documented story hold" narrative | the `../remote-store-expectations` black-box DX repo |
| Spec/contract gap | a new spec clause / ID (e.g. the proposed `GR-059` concurrency contract) |
| Doc gap | the relevant guide / explanation page |

Promoting backend-agnostic expectations into conformance is the highest-leverage
move: it converts a one-off discovery into a permanent guard that protects every
current and future backend.

---

## 5. Two altitudes, and the cost discipline

- **Broad sweep** is cheap (static) and answers *where to look*. Run it per
  backend and before declaring a backend GA.
- **Deep-dive** is expensive (live creds, a throwaway account, real time and
  money) and answers *what actually happens*. It is **milestone-gated**, not
  per-PR. A live battery aspirationally run on every change rots into skipped
  ceremony; gating it to "before GA" and "periodic drift check" (services change
  underneath us) keeps it honest.

The sweep's heatmap is what justifies each expensive deep-dive.

---

## 6. Keeping it honest

- **Stopping rule.** A lens is worked until a round yields nothing new
  surprising (loop-until-dry). We do not pretend the space is closed; we declare
  a lens "dry for now" and move on.
- **Empirical feedback loop.** The catalog starts as educated guessing and
  becomes empirical: real support questions, GitHub issues, and surprises from
  the expectations repo each become a new catalog row. This is the direct answer
  to "we can only guess" — we guess to seed, then replace guesses with observed
  reality.

---

## 7. Prior art — why this is complementary, not redundant

This method sits **upstream** of the existing quality machinery; it finds *what
to encode*, the others encode it. Build-vs-reuse, explicitly:

- **Conformance suite (spec 048).** Tests each method's *specified* contract
  across backends. It cannot generate a user expectation the spec never stated —
  e.g. "is a shared instance safe across coroutines?" was unspecified, so
  conformance was silent. This method *produces* those expectations; the best of
  them then *become* conformance tests (§4). Reuse, downstream.
- **Property-based testing.** PBT generates random *inputs* against a known
  property. This method generates the *properties* (expectations) themselves,
  which are semantic and analogy-driven, not input-space exploration. The two
  compose: a lens names the property, PBT can stress its input space.
- **[research-bug-prevention-beyond-testing.md](research-bug-prevention-beyond-testing.md).**
  That doc evaluates *mechanisms* (DbC, PBT, extended conformance, resource
  safety) for encoding and enforcing known contracts. This doc is the *discovery*
  front-end: it finds the boundary, cross-backend, lifecycle, and edge-input gaps
  that doc identified as the dominant bug surface — but proactively, from the
  user's mental model, rather than from a post-hoc bug taxonomy.
- **Audits (`sdd/audits/`).** An audit reviews a *delivered* artifact for
  correctness against its own spec. This method reviews against the *user's*
  expectation, which may exceed or contradict the spec — and a finding can be
  "the spec itself under-promises/over-promises."

Net: nothing here replaces an existing tier. The new asset is the **expectation
catalog + generation pipeline** — a way to stop relying on instinct for *which*
expectations to chase.

---

## 8. Worked example — the Graph concurrency review (first instance)

The method's first execution, retrofitted to the catalog to show the mapping:

- **Lenses applied:** persona (FastAPI shared store) + lifecycle (close
  semantics) + scale (parallel load), pointed at the async-native Graph backend.
- **Predict-first:** the panel wrote the expected behavior per scenario before
  any live run; one prediction (token "stampede") was refuted live (it was a
  loop-block), validating the discipline.
- **Deep-dive:** a live "go hard" battery against a throwaway OneDrive (14
  scenarios — create-once race, overwrite integrity, read/list-after-write,
  stream-vs-mutate, aclose race, pool saturation, bridge concurrency).
- **Outcome:** core expectations *held* (overwrite=False is a server-atomic
  create; no torn writes; read-your-writes; deadlock-free bridge), and the
  divergences classified cleanly into code (BUG-219), spec (BK-287, the proposed
  `GR-059`), docs (BK-288), test-lane (BK-289), and robustness (BK-290/291/292) —
  plus a stale-ADR doc-accuracy fix (the ADR-0025 "chunk hashing" misattribution).

The same target still has *seven untried lenses*. A broad sweep over those is the
natural next pilot, and the cheapest test of whether the catalog earns its keep.

---

## 9. Recommendation

1. **Pilot the broad sweep** on the Graph backend (seven untried lenses, mostly
   static) to confirm the catalog surfaces new hotspots cheaply; then on Azure
   (the other async-native backend, same bridge surface) to confirm it
   generalizes across backends.
2. If it earns its keep, **formalize** the catalog + pipeline as a process guide
   (peer of TESTING.md/DESIGN.md) and optionally a thin skill so a sweep is one
   command.
3. **Wire the routing** so findings land permanently: backend-agnostic
   expectations into conformance, backend-specific into the live tier, the DX
   narrative into the expectations repo.

The method's promise is modest but real: it converts "we can only guess at user
expectations" into "we mechanically walk the sources of expectation, and we know
which lenses are still dry."
