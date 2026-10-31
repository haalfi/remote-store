# The outside formalization proposal, read against OP-01 and against this spike

<!-- doc: repo-only -->

**Date:** 2026-10-31
**Backlog items:** BK-485
**Status:** Input, critically read, for step 5. Unverified: a ChatGPT answer the
maintainer passed on on 2026-10-30, which grades no sources. Written from the
24-row table of step 1 (`extract/`), so it saw no embedded tables, none of D21,
D23 or D38, and not D41's register; it says so itself. Its ideas are restated
here in this repo's terms and matched to the record; the answer itself is not
committed.

---

## 1. The proposal in brief

OP-01 is a protocol, not a function: a backend is correct when every sequence
of bytes, failures, cancellations and retries a caller can observe lies in the
set the contract allows for that backend. The proposal builds that set in five
layers (abstract state, value contracts, a stream state machine with data,
a TLA+ action system for concurrency, model-based conformance against real
adapters) and makes backend differences parameters of one model,
`M(C_b, A_b)`, with `Traces(impl_b) ⊆ Traces(M(C_b, A_b))` after hiding
internal steps.

Most of that frame is already the repo's (§ 2). Its value lies in specific
ideas inside it, several of which challenge choices this spike made (§ 4).

## 2. What the repo already decides

| Proposal | Already decided in |
|---|---|
| Lifetime and concurrency in TLA+ | `SPEC-DESIGN.md` Rule 3: a lifetime's source is a TLA+ module, with a closed-world diagram checked both ways; Rule 4: TLA+ governs lifetime and environment |
| Value contracts | Rule 3: a single call is one invariant per section plus an outcome table; Rule 4: Dafny governs function and single call |
| Abstract namespace | Rule 4: Alloy and Lean govern structure; spec 051 states the tree, spec 052 ν and Ω (KEY-013) |
| Profiles as parameters | Rule 5: a behaviour that differs by backend is a named, declared profile |
| Environment assumptions | Rule 3: an Assumptions section, one line per stable ID |
| Liveness under fairness | Rule 3: bounded obligations a test can fail; fairness goes to Assumptions |
| Hypothesis stateful model | RFC-0029 R4's toolchain: a Python reference model with a Hypothesis state machine, history checks by Porcupine |

So the proposal is not a new frame. It is a second, independent derivation of
the frame the repo chose, and where the two agree that is weak evidence the
frame fits OP-01. Where they differ, § 4 asks which side is wrong.

## 3. Ideas worth digging, matched to OP-01

Each idea below names the decisions it lands on and what digging it means.

### 3.1 Three things that are not one: existence, readability, version availability

The proposal separates "the key names an item", "the item can be read now" and
"the content the stream pinned can still be served". OP-01 already has all
three, spread over different decisions: D9's partition (existence), E15 with
D19 and D30 (exists but not readable), D22 and D31 (the pinned content is gone:
changed). The spike's rules collapse the last two into one Failed state with
one category. **Dig:** a model state that carries version availability apart
from the stream's control state, so `O15` (E15 mid-stream: changed or not
readable?) and `O44` (an Azure metadata write changes the ETag but not the
content) become model questions with a counterexample, not prose ones.

### 3.2 The stream is an interval with one designated instant, not an atomic read

The proposal warns against modelling a stream as one linearizable read: it is
open across many caller calls, can fail after delivering bytes, and its
classification has one instant t₀ inside the open. That is D22 almost word for
word (one instant t₀ inside the open call; every byte from that content), so
it confirms the record. **Dig:** it also names the case D21 and D22 do not
cover alone. If open is a phase in which environment actions interleave, the
model can produce the history of `O20` and `O35` (a GET answering 404, then O3
creating `d` and `d/f` before the listing) instead of a reviewer reconstructing
it by hand.

### 3.3 Internal steps hidden: retries and resume are τ, not states

The proposal puts retry, buffering, listing and cleanup on internal τ
transitions, with an optional `Recovering` sub-state of Open that the caller
never sees. That is the reading `O18` asks the record to adopt (the resume
happens inside the read that met the reset, not on "the next read", D39's
option wording), and D16's "recovery has one place, inside a read". **Dig:**
writing D38 and D39 as τ steps under one call makes the attempt limit a
counted variable, which turns `O32` (no attempt limit bounds a stream's total
waiting once bytes flow) into a checkable property instead of a note.

### 3.4 Quiescence as an observable: ioco and timeouts

ioco treats "no output" as an observation (quiescence). OP-01's timeouts are
exactly that: D12 fails a request when no byte arrives for T_idle, E9 is the
stall. **Dig:** a conformance oracle that can observe quiescence can test D12,
D13 and D14's deviation (Local terminates when the OS's I/O completes) as
allowed traces, and it is the natural place to settle `O27` (a stalled connect:
timeout or unavailable) and `O41` (name resolution before any timeout, so the
sync form's bound is the resolver's). The proposal ranks ioco optional; for
AX-5 it is the method that fits.

### 3.5 Assume-guarantee per backend, with the record's own parameters

`M(C_b, A_b)` has a direct reading in OP-01. `C_b` is D43's four variation
points (termination, read-after-write, pinned resume, O3 in-place
modification), each static per backend. `A_b` is the Environment table: which
of E1 to E15 can arise on that backend (E4 only on file-system backends, D26;
E15 only where archive tiers or customer keys exist). **Dig:** stating each profile as that pair makes
SPEC-DESIGN Rule 5's declared profile a model parameter a conformance run can
select, which the spike approximated only with two typing modes.

### 3.6 Per-byte provenance for in-place modification

Under E4 the proposal drops "delivered bytes are a prefix of the pinned
content" and checks instead that each delivered byte equals the file's byte at
that position at some instant between the open and its delivery. That is D26's
Decision restated as a checkable trace property. **Dig:** it is testable on
Local today by a writer thread modifying the file in place during a stream,
with no new library code.

### 3.7 A ghost variable for memory

`buffered(h) ≤ B(C_b)`, independent of the item's size, with the caller's own
request counted apart: D40 in checkable form. **Dig:** the variable flags
`O34` at once (`readline()` on content with no newline asks for no size and
holds the whole item), which the record found by running CPython. The bound
then needs D40 or `readline`'s signature to change, which is `O34`'s open
choice.

### 3.8 Failed reads deliver nothing, and EOF is an output

Two of its rules the record leaves implicit: a failed `read(n)` commits no
partially received bytes (this spike's F7, and what D39's "no gap or repeated
byte" rests on), and `b''` for a positive `n` only when no bytes remain (which
sidesteps F1's `read(0)` case). It also treats EOF as an observable output, not
a state, which § 4.2 takes up.

### 3.9 Fault injection needs a controllable adapter or proxy

The proposal says fault injection needs a controllable adapter or proxy. The
spike built one for Local (a raw-file wrapper under `BufferedReader`). **Dig:**
for S3, Azure and SFTP the same layer is a network proxy between the SDK and
the service, so the same rules can judge D28, D38 and D39 on the backends where
they matter most.

### 3.10 A small first TLC configuration

Two readers, one API writer, one external actor, two content versions, short
contents, a few environment events: small enough for TLC to exhaust, with the
action list open, read portion, fail, close, cancel; API replace and delete;
external replace, delete, in-place write, archive; transport failure, retry,
resume, credential expiry. **Dig:** that is a usable starting point for the
pinning module (D21, D22, D25, D26), the slice the spike left out.

## 4. Where it challenges this spike, and the record

### 4.1 The spike put the stream lifecycle in Python rules; the repo says TLA+

The spike first skipped TLA+ because "the slice has no interleaving".
`SPEC-DESIGN.md` Rule 3 says otherwise: a lifetime's source is a TLA+ module,
the stream lifecycle is a lifetime, and the proposal puts it in a TLA+ action
system too. On that reading `stream_rules.toml` is an oracle and evidence, not
a candidate source, and skipping TLA+ for want of interleaving read the repo's
rule too narrowly; the report's § 1 table now carries the Rule 3 reading. What
the spike does
show is that the rules' guard-and-effect form maps onto TLA+ actions one to
one, so the move is a translation, not a redesign.

### 4.2 Exhausted may not be a state the stream can be in

The proposal has no Exhausted state; EOF is an output. The first reading of
that was "it misses D18's Exhausted". F10 says the stream itself cannot know it
is at the end until a read returns nothing, and that read can still fail or be
cancelled; Local's fault runs showed it. So the proposal's choice may be the
better model: Exhausted as "end observed" (after a `b''`), not "position equals
length". That is a reopen candidate for D18, not a detail of the spike.

### 4.3 Observables alone cannot check the frame

The spike compares only what a caller sees from the stream. D10 promises that
nothing any API call observes changes after a read, which no stream observable
can show. The proposal's abstraction map from a backend's state to the model's
state is what such a check needs: observe the store through OP-09 and OP-20
after each step and map it. Without it, D10 and D17's "release changes no store
state" are untested by construction.

### 4.4 Faults at any point, not only at a call's start

The proposal's environment acts as an independent agent whose actions
interleave anywhere. The spike's wrapper fires a fault only at the start of a
raw call, never mid-read, and the report lists that as a limit. The proposal's
form is what E8's "lost or reset mid-call" and D20's "bytes half-received"
actually describe.

### 4.5 The spike traded shrinking for a report, and lost reproducibility

The proposal values Hypothesis for shrinking a failure to a short, reproducible
trace. `conform.py` records divergences instead of failing, so nothing shrinks,
and the runs are not seeded: plain Local's RF7 showed in four of five runs.
**Dig:** a seeded or derandomized run for the reported figures, and a failing
mode that shrinks for a single divergence.

### 4.6 Bounded checks prove nothing beyond their bound

The proposal says TLC and Apalache check a bounded model and prove nothing for
arbitrary sizes. `check_rules` is the same kind of check: three contents, six
sizes. Its "every call matches exactly one rule" holds over that domain only,
which the report now states; the same caveat binds any TLC result in step 5.

## 5. Wrong on the facts, set aside

| Claim | Why it is set aside |
|---|---|
| Pinned resume on Local is "profile dependent" | `O33` notes Local's descriptor never drops (D42's dialog) |
| A library `DecodeError` category | D32 decides the builtin `UnicodeDecodeError`, not a library category |
| Its property-to-decision mapping (P01 to P14) | Built on the stale 24-row view (report § 2); misses D21, D23, D38 and D41. The properties stand as a checklist, the mapping does not |
| Its numbering P10, P11 | Collides with the spike's `check_stream.py`, where P10 and P11 name other properties than its E4 provenance and SFTP resume |
| One environment agent for cancellation | The record keeps cancellation apart as the Runtime actor (E14); D20 treats it as no storage failure |

## 6. What step 5 takes from this

- Write the stream lifecycle as a TLA+ module, with `stream_rules.toml` as its
  test oracle (§ 4.1, SPEC-DESIGN Rule 3).
- Raise D18's Exhausted as a reopen: end observed, not position at length
  (§ 4.2, F10).
- Give the model version availability apart from control state (§ 3.1, `O15`,
  `O44`).
- Model retry and resume as counted internal steps (§ 3.3, `O18`, `O32`).
- Use an abstraction map to check D10's frame (§ 4.3).
- Treat quiescence as an observation for AX-5 (§ 3.4, `O27`, `O41`).
- State each backend's profile as D43's points and the Environment rows it
  admits (§ 3.5).
- Check D26 by per-byte provenance on Local (§ 3.6) and D40 by a ghost buffer
  variable (§ 3.7, `O34`).
- Inject faults mid-call, by proxy for network backends (§ 3.9, § 4.4).
- Seed or derandomize reported runs (§ 4.5).
