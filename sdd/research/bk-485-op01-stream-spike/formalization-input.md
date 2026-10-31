# The outside formalization proposal, and what the spike made of it

<!-- doc: repo-only -->

**Date:** 2026-10-31
**Backlog items:** BK-485
**Status:** Input with verdicts, for step 5. Unverified: a ChatGPT answer the
maintainer passed on on 2026-10-30, which grades no sources. Distilled here in
this repo's terms; the answer itself is not committed.

---

## 1. What was proposed

The proposal models OP-01 as a protocol: an operation is correct when every
sequence of bytes, failures, cancellations and retries a caller can observe
lies in a set the contract allows for that backend. It builds that in five
layers and names one technique per layer.

| Layer | Proposed form | Proposed check |
|---|---|---|
| 1. Abstract state | State vector (namespace, versions, handles, calls, environment, capabilities); `normalize`, `classify`; an abstraction map from each backend's state | Exhaustive or proof for the classification partition |
| 2. Value contracts | Pre- and postconditions per read form; outcomes as a sum type (success, typed failure, cancelled) | Property tests |
| 3. Stream lifecycle | Extended state machine: control states plus data (position, pinned content, retries) and guarded transitions, in guarded-command form | Machine invariants |
| 4. Concurrency | TLA+ action system: reader, API writer, external actor, environment; one action per significant step | TLC (Apalache optional), safety invariants, liveness only under fairness |
| 5. Conformance | Hypothesis `RuleBasedStateMachine` against real adapters, with fault injection; trace refinement after hiding internal steps; ioco optional | Generated traces with an oracle of allowed outcomes |

Backend differences enter as parameters: one model per capability profile and
environment assumption set, and each backend's observable traces must be a
subset of its profile's model.

It was written from the 24-row table of step 1 (`extract/`), so it saw no
embedded tables, none of D21, D23 or D38, and not D41's register, and it says
so.

## 2. Where the repo already stands

Most of the stack is already decided; the proposal adds tools and patterns
inside it, not a new frame.

| Proposal | Already decided in |
|---|---|
| Lifetime and concurrency in TLA+ | `SPEC-DESIGN.md` Rule 3: a lifetime's source is a TLA+ module, with a closed-world state diagram checked both ways; Rule 4: lifetime and environment are governed by TLA+ |
| Value contracts | Rule 3: a single call is one invariant per section plus an outcome table; Rule 4: Dafny governs function and single call |
| Abstract namespace | Rule 4: Alloy and Lean govern structure; spec 051 states the tree, spec 052 ν and Ω (KEY-013) |
| Profiles as parameters | Rule 5: a behaviour that differs by backend is a named, declared profile |
| Environment assumptions | Rule 3: an Assumptions section, one line per stable ID |
| Liveness under fairness | Rule 3: bounded obligations a test can fail; fairness goes to Assumptions |
| Hypothesis stateful model | RFC-0029 R4's toolchain: the reference model in Python with a Hypothesis state machine, history checks by Porcupine |

## 3. Verdicts

What the spike measured, per element. "Used" means the spike built it and the
report's runs exercised it.

| Element | Spike | Verdict |
|---|---|---|
| Guarded transitions (layer 3) | Used: `stream_rules.toml`, 16 rules, guard plus effect | **Keep.** It made completeness checkable (`check_rules`) and generated the checks. Per Rule 3 it is an oracle and evidence; the lifetime's governing source stays a TLA+ module |
| Hypothesis stateful conformance with fault injection (layer 5) | Used: `conform.py`, Local plain and with faults below the library | **Keep.** It found C1 to C4 and F9 against a real backend |
| Observable-only comparison, internal steps hidden | Used: `conform.py` compares return, raised category and warnings, and judges a fault only once it reaches the backend | **Keep.** The "reached the backend" rule is the spike's own; the proposal states hiding internal events in general |
| Profiles as parameters | Partly: two typing modes (strict, protocol only), no capability profile | Untested beyond typing |
| Sum-typed outcomes (layer 2) | Partly: categories as names in the rules (`raises`) | Untested as a type |
| TLA+ action system, TLC (layer 4) | Not used: the slice has no interleaving | Untested; the slice for it is pinning under writes (D21, D22, D25, D26) |
| Abstraction map, refinement proof | Not used | Untested |
| ioco | Not used | Untested; the proposal itself ranks it optional |

The proposal also stated two points the record leaves implicit, both of which
the spike later found as gaps: a failed `read(n)` must not count bytes it did
not deliver (report F7), and `b''` for a positive `n` only at the end (which
sidesteps F1's `read(0)` case).

## 4. Worth carrying into step 5

- **The guarded-command form** for a transition (state guard, input guard,
  effect, postcondition), as the shape of the stream's rows until its TLA+
  module exists.
- **The refinement criterion:** a backend's observable traces lie within its
  profile's allowed set, after internal steps (retries, buffering, listing)
  are hidden. That is what `conform.py` checks informally.
- **Per-byte provenance for E4:** each delivered byte equals the file's byte at
  that position at some instant between the open and its delivery. D26 already
  says this in prose; the proposal gives it a checkable form, to verify in
  place of prefix-of-pinned-content when E4 applies.
- **A ghost buffer variable** for D40: bytes held ≤ a bound independent of the
  item's size, with the caller's own request counted apart.
- **Its TLA+ action list** (open, read portion, fail, close, cancel; API
  replace and delete; external replace, delete, in-place write, archive;
  transport failure, retry, resume, credential expiry) as a starting
  vocabulary for the pinning module, and its first configuration: two readers,
  one API writer, one external actor, two content versions, short contents.
- **Its property list** as a checklist, re-derived from the full record rather
  than from the 24-row view it was written on. Its numbering is not reusable:
  the spike's P10 and P11 (`check_stream.py`) name other properties than the
  proposal's P10 (E4 provenance) and P11 (SFTP resume).

## 5. Not to carry

- **Its stream states.** Opening, Open, Failed, Closed: no Exhausted, which
  D18 has, and opening is a call, not a state.
- **Its backend profile table.** Several cells are guesses; it labels them
  obligations, not facts. One contradicts the record: pinned resume on Local
  is "profile dependent" there, while `O33` notes that Local's descriptor
  never drops.
- **Its mapping of decisions to properties.** Built on the stale 24-row view
  (report § 2), it misses the decisions that bind the most.
- **Unbounded liveness.** Rule 3 admits only bounded obligations; the proposal
  agrees, conditioning progress on stated assumptions.
