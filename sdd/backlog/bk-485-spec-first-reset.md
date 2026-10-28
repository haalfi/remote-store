# BK-485 — The v1 Store API has no observable-semantics specs, so implementation runs ahead of decided behaviour
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).
The decision record is
[`research-spec-first-reset.md`](../research/research-spec-first-reset.md),
made binding by [RFC-0024](../rfcs/rfc-0024-spec-first-reset.md).

## First `/observe` run (`exists`, 2026-10-23)

**A throwaway test of the tool, kept off master:** its record (then still a
research doc under `sdd/research/`) and decision log are on branch `throwaway/bk-485-observe-research` (`92fe4fc`). The
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
- **Probed separately (2026-10-24).** A fresh session armed by `/observe
  probe`, with the maintainer's go-ahead, tried ten calls once each: a `src/`
  read, Bash, Glob, a Grep over `src`, a WebFetch and a WebSearch naming
  remote-store, a write to spec 051 and an Agent call were refused, each
  naming its rule (S1 to S4); reading the axes and writing the record were
  allowed. Its `send_message` to the orchestrating session was refused too.
  The S1 refusal read as garbled to it, so it now says "describe version
  0.33".
- **The session's own report** listed 13 problems. The tool-level ones were
  fixed in PR #1178 (method files named by path, which ground to read,
  the backlog item asked in the first dialog, the canary on axes closed
  without a question, the stop hook, an Environment list decided at doc
  creation, an axis settled by an earlier decision, one home for open items,
  the four-option dialog limit). The two about method go below.

## OP-01 review candidates (BK-499, 2026-10-28)

Step 5's review (RFC-0028 P2) has not run on OP-01. BK-499's untold runs on
the record at `c58ee74` raised these outside audit-025. Each names the runs
that raised it, with that run's finding label: E the End pass, R1 and R2 the
two reader runs (RFC-0028 § Evidence; the reports came back to BK-499's
session and are not committed, so the labels are their only trace). None was
re-read against the record; `/observe-review OP-01` verifies them and files
what holds as open items:

- D12 vs D28 and D34: E7's "connect never completes" is timeout and unavailable (E 3, R1 1a, R2 1d).
- D22 vs D39, D42 and D43: a lost pin fails changed or unavailable (R1 1b, R2 1c; E dropped it as a declared variation).
- D9's adopted "failure path only" vs D41's NP2 (E 1, R1 1f, R2 1a).
- The Session's "no decision cites a clause they check" vs KEY-001 and KEY-013 in D4 and D9 (E 12, R1 § 2, R2 2b).
- D25's "when an O3 change becomes visible is the backend's", in neither D41 nor D43 (E 7, R1 § 2, R2 2d).
- D38's and D12's bound on waiting vs D39's limit restarting (E 8, R1 § 3, R2 3a).
- D34's changed row naming E4 vs D26 (E 4, R1 1e; R2 dropped it).
- D2's `readline` vs D40's memory bound (E 9, R2 1g).
- Axis rows "one reopen explicitly open" with no open item behind them (R1 § 2, R2 2f).

OP-01's record predates the Asked line, so the review's readers pair its
decisions by hand (`/observe-review` step 1).

## Format RFC input (§ 9 step 6)

**A critique of F1 to F6, for the format RFC to weigh; nothing here is
decided.** The maintainer passed it on on 2026-10-23 from a ChatGPT session.
It is unverified: like that tool's deep-research run (research § 5), it grades
no sources. Its mapping of `read()` decisions onto the categories is left out,
because those are research § 7's candidates and would prime a design session.
What fits within the binding F decisions already went into
[`observe/axes.md`](../observe/axes.md); the rest waits for this RFC.

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
  operation's session would rediscover them. The decisions about the surface
  as a whole moved to [BK-493](bk-493-operation-catalogue.md), as spec 053.
  The home for the rest is [`sdd/observe/shared.md`](../observe/shared.md)
  (BK-495, [RFC-0027](../rfcs/rfc-0027-observe-playground.md)): its sections
  for handle, lifetime and state, and its Lands elsewhere table for these
  three: the key refusal to spec 052 and the error layer, the profile surface
  to OP-18's flow, a timeout bound to each entry's AX-5 and a shared one to
  OP-01's flow.
- **F3 lacks "admitted, not required".** A failure category that may surface
  but need not (`exists`'s store-integrity failure on a non-store state) fits
  none of F3's terms; the session coined the phrase.
