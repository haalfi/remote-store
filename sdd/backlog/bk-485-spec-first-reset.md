# BK-485 — The v1 Store API has no observable-semantics specs, so implementation runs ahead of decided behaviour
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).
The decision record is
[`research-spec-first-reset.md`](../research/research-spec-first-reset.md),
made binding by [RFC-0024](../rfcs/rfc-0024-spec-first-reset.md).

## First `/observe` run (`exists`, 2026-10-23)

**A throwaway test of the tool, kept off master:** the research doc and its
decision log are on branch `throwaway/bk-485-observe-research` (`92fe4fc`). The
maintainer typed `/observe exists` in a fresh session on `bk-485-observe`.

- **What held.** The hook armed the session; the canary was refused before
  each axis; reads outside the ground (`scripts/observe_ground.py`, the reset
  research doc) were refused; Bash was blocked, so the doc was committed only
  after `/clear`. All 15 axes closed: 18 decisions, AX-6 and AX-11 not
  applicable, 9 environment rows, 3 open items. The maintainer found the
  questions right in number and size.
- **What failed: priming.** The maintainer saw the store API as 0.33 has it in
  the recommendations. Traced: `research-store-model-axioms.md`, then a
  register row, carries 0.33 and kernel design in its § 10 (`InvalidPath`, the
  flat-store undecodable state the session used as its E5 example). It left
  the register. Two category names (`backend-unavailable`,
  `permission-denied`) match 0.33's error classes without any ground file
  naming them, so the skill now makes each recommendation cite a ground clause
  or named prior art, else mark it `unsourced`.
- **Not exercised:** the Bash, Glob, WebFetch and write-elsewhere probes; unit
  tests cover them. A short probe-only run is still owed.
- **The session's own report** listed 13 problems. The tool-level ones were
  fixed in PR #1178 (method files named by path, which ground to read,
  the backlog item asked in the first dialog, the canary on axes closed
  without a question, the stop hook, an Environment list decided at doc
  creation, an axis settled by an earlier decision, one home for open items,
  the four-option dialog limit). The two about method go below.

## Format RFC input (§ 9 step 6)

**A critique of F1 to F6, for the format RFC to weigh; nothing here is
decided.** The maintainer passed it on on 2026-10-23 from a ChatGPT session.
It is unverified: like that tool's deep-research run (research § 5), it grades
no sources. Its mapping of `read()` decisions onto the categories is left out,
because those are research § 7's candidates and would prime a design session.
What fits within the binding F decisions already went into
[`observe-axes.md`](../observe-axes.md); the rest waits for this RFC.

| F | Critique | Verdict for the RFC |
|---|---|---|
| F1 | One authority per claim is right, but one formula, row or transition per unit is too rigid: one claim can need several coordinated predicates. A formal model and a test oracle may differ in representation if their relation is checked. | Weigh. Keep the single authority; test the one-unit rule on the `read()` slice before relaxing it. |
| F2 | The categories mix kinds of claim (structure, value, single call), behaviour over time (resource life, multi-observer), assumptions (environment) and mechanisms (profile, non-promise register). They are facets, not a partition. | Applied to the axes as one home axis per question, other facets cited. The RFC decides whether the category list says so. |
| F3 | The terms answer different questions: what the contract leaves open (unspecified, MAY, not promised), who fixes it (profile-declared), what the caller can know (indeterminate). "Unspecified" must still state the admissible observations. | Applied to the axes. The RFC states the split and the admissible-set rule in `SPEC-DESIGN.md`. |
| F4 | Three charges. A normal value set at a stronger guarantee than every backend meets reads as a promise the portable API does not make; separate a portable baseline, declared refinements a caller may query, and deviations below the baseline. A warning repairs no contract: a caller who needs a guarantee needs a refusal. Warning frequency ("once per store instance, operation and deviation") is implementation policy, not contract. Profiles should be checked for internal consistency. | The open point. F4 as decided has no home for a backend that offers more than the normal value. Decide with the `read()` slice's variation points in hand; AX-15 stays on F4 until then. |
| F5 | "No test asserts what is not promised" cannot be checked in general: an implicit assumption names no register entry. What can be checked: tests name the claims they verify, tests without one are flagged, explicit conflicting assertions are caught. Register only plausible, consequential non-promises. | Applied to AX-14 (bounded register, explicit assertions). The RFC rewords F5's check to what is decidable. |
| F6 | Retry safety depends on the operation and its guarantees, not on the error category alone: a re-read is mutation-free but may see another version. Separate actual, observable and known effect. | Applied to AX-12 and AX-13. The RFC decides whether the failure category carries the three effects. |

Two more, from the first `/observe` run's own report (above):

- **Decisions that bind every operation have no home.** `exists`'s D2 (an
  unacceptable key is rejected identically by every operation) and its open
  items on a timeout bound and a profile surface are shared; the next
  operation's session would rediscover them. A shared layer for such
  decisions, as for the environment list, is the RFC's to place (D5 grows
  shared layers from what operations need).
- **F3 lacks "admitted, not required".** A failure category that may surface
  but need not (`exists`'s store-integrity failure on a non-store state) fits
  none of F3's terms; the session coined the phrase.
