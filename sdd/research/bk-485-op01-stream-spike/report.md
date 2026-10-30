# Research: OP-01's stream decisions, carried from prose to checks (BK-485)

<!-- doc: repo-only -->

**Date:** 2026-10-30
**Backlog items:** BK-485
**Status:** Spike complete. A point-in-time snapshot per
[`sdd/000-process.md` § Document types](../../000-process.md#document-types).
The scripts and their runs: [`README.md`](README.md).

---

## 1. Question and answer

Can OP-01's prose decisions reach checks that run against a real backend
through steps a script can check, each step derived from the one below it?
For one slice, the read stream's lifecycle, yes. Rules with guards and effects
are the step that carries it. They make the slice's completeness checkable,
generate the checks, and judge Local unchanged. Most of the yield is
not the conformance verdict but what each step forced into the open: ten
places where the prose does not fix an outcome (F1 to F10, § 6), five of them
not among the record's open items.

The staircase came from an outside critique the maintainer passed on (a
ChatGPT answer proposing contracts, an extended state machine, TLA+ and
model-based testing; not committed, sources not graded). This spike tried the
cheap lower steps only:

| Step | Artifact | Checked by |
|---|---|---|
| 0 | The record (prose) | Review, as today |
| 1 | Extraction: scenario and decision per decision | A script; § 2 |
| 2 | The slice as typed rows, then as guarded rules | The rules: every call matches exactly one rule (§ 4) |
| 3 | Reference model (Python) | Rows replayed, a Hypothesis machine, four mutants (§ 3) |
| 4 | Local, plain and with injected faults | The same rules as oracle (§ 5) |
| 5 | Formal check (TLA+) | Not tried: the slice has no interleaving |

Inputs: the record at `f1595ff`, read in this session; no other `sdd/` file
shaped the rules. Local's API was read only as far as an adapter needs:
`Store.read`, `LocalBackend.read` (`open(full, "rb")`), and the class names in
`_errors.py`.

## 2. Step 1: the extraction, and a stale filter

`extract_decisions.py` keeps the decisions whose own **Open items** field is
`none` and expands a bare `(a)` from the Options field: 24 of 44.

That filter is stale. Reopens and gaps found later (`OP-01/O14` to `O45`) are
listed in the record's Open items section, and no decision's own field is
updated. `stale_filter.py` measures it on the 24: 23 are mentioned somewhere in
a later item's text (an upper bound: it counts context mentions, and RFC-0024's
own "D5"); 10 are the decision an item reopens, notes or finds a gap in, by the
item's lead clause (a lower bound: it misses `O26`, whose three gaps name D3
and D16 only in its Dependent line). The record's Axis status table is the
current source. That is one data point for BK-505's record-quality question,
not its measurement.

Tables embedded in a decision (D9's partition, D19's exposure, D41's register)
do not survive a one-line cell; the extraction drops them.

## 3. Step 3: rows and a reference model

30 example rows (`stream_rows.toml`) became `stream_model.py`. `check_stream.py`
replays every row (29 pass, 6 of them on an assumption; R30 is the open item
`OP-01/O5`), runs 300 Hypothesis examples against invariants written from the
decisions (P03 to P11), and shows each of the slice's 8 decisions behind at
least one row and one invariant. `mutate.py` breaks the model four ways (Failed
not sticky, a byte consumed on a failed transfer, `close()` raising a release
failure, a cancelled read leaving Failed); each makes the check fail.

Rows are examples: `read(4)` on `"abcdef"` fixes one input. The rule lived in
the invariants, written by hand.

## 4. Step 2b: guarded rules

`stream_rules.toml` holds 16 live rules and the open item `O5`. A rule is a
guard over the oracle's state and the call (`when`) and an effect: `accept`, a
predicate over the returned value, which admits D7's nondeterministic chunk
sizes; `raises`; `warns`; `advance`; `to`. `rules_engine.py` interprets them as
an oracle.

What rules add over rows:

- **A completeness check.** Over 3 contents, every valid state and position, 7
  events, 4 injected faults and 6 sizes, every call matches exactly one rule.
  That is D18's table's claim, made checkable; drafting against it forced
  guards for cases no row listed (`chunks(0)` on a Failed stream, a release
  fault on a read).
- **Generated checks.** Hypothesis draws calls; the rules judge them.
- **Two artifacts that agree.** The rules judge the model written earlier from
  the rows: 0 divergences.

A fault counts only once it reaches the backend: the oracle judges a call by
the fault that fired, not the one armed. A buffered read never reaches the raw
file, and NP3 leaves read-ahead unpromised, so the rules must not depend on it.

One rule was corrected before landing. Drafted first, a cancellation on a call
that needed no transfer was ignored; `O45` reads D20 as closing the stream in
every state. RF5 now covers Open, Exhausted and Failed. Before the fix, Local's
end-of-file faults surfaced as a divergence; after it they are judged by the
rule F10 assumes (§ 6).

On the dossier's F1 question (one formula, row or transition per unit): the
16 rules each cite one or two decisions, and D18 spreads over 7 of them
(counted from the rules' `src`). A unit here is a guarded transition, not a
decision.

## 5. Step 4: the same rules against Local

`conform.py` drives `Store(LocalBackend(dir)).read(key)`, comparing only what a
caller observes: return value, raised category, warnings. Then again with
faults injected below the library: for `LocalBackend.read`'s one call,
`open` returns `BufferedReader(FaultyRaw(FileIO(path)))`, whose raw layer
raises `OSError(EIO)` on a read, `KeyboardInterrupt` on a read or close, or
`OSError` after releasing on close. The stream is CPython's own
`BufferedReader`, as in production. Typing is judged twice: strict (library
categories only; `BackendUnavailable` is unavailable) and protocol only (any
`OSError` counts as unavailable), separating D27 from the state machine. 400
examples per run.

Plain Local diverges on three rules:

| Rules | Local | Cause |
|---|---|---|
| RF4, RF7 (D6) | `read(-2)` raises `ValueError` | `io.BufferedReader` accepts only n ≥ 0 or -1 (run directly): F9 |
| Z1 (D2) | `seekable()` is `True` | `open(full, "rb")` is seekable |

With faults (F9 and Z1 parked), five rules diverge in each mode. A divergence
ends its example, so a later rule often shows an earlier step's cause; by
cause:

| # | Decision | Local today | Rules |
|---|---|---|---|
| C1 | D20 | A cancelled read or close leaves the stream open | RF2, K1, G1 |
| C2 | D16 | Failed is not sticky: the next read reaches the OS again | RF3 |
| C3 | D27 | An OS error surfaces as `OSError`, not a library category | RF6, K3 (strict) |
| C4 | D36 | `close()` raises a release failure | K3 |

Not exercised on Local: RF1 and RF8 (no `chunks()`, D7). C1 to C4 are where
0.33's Local stream, a plain file object, is behind decided v1 behaviour, not
defects in the prose; audit-025 § 4 ranks D20 (rank 2) and D27 (rank 7) among
the costs ahead.

**The wrapper's limits.** A fault fires only at the start of a raw call, never
mid-read; `release_fail` releases the descriptor before raising;
`_dealloc_warn` is delegated so `ResourceWarning` behaves as with a plain file.
A real NFS `EIO` was not run.

## 6. What the prose leaves open

Each finding is a cell the slice's decisions do not fix, or fix in two places
that disagree. The match against the record's `O14` to `O45` is by reading
their text in this session.

| # | Finding | In the record |
|---|---|---|
| F1 | D6's option says `b''` "only at the end"; its decision `min(n, r)` gives `b''` for `read(0)` mid-stream | new |
| F2 | A cancelled `close()` (D36) has no next state | partly: `O16` (exposure at s4), `O45` (D20's states) |
| F3 | D17 warns for "an open stream"; whether an unclosed Exhausted or Failed stream warns is unstated | new |
| F4 | `readinto` and `readline` have no value semantics | `O25` |
| F5 | `chunks(size ≤ 0)`: the state after, and whether Closed or Failed raise at the call or at the first `next()` | partly: `O36` (the state) |
| F6 | D16 "the same category" vs D18 "the same failure again" | `O26` (G4) |
| F7 | A failed read delivers no bytes in that call; only D6 and D16 together imply it, and D39's resume rests on it | new |
| F8 | A cancellation on a call that needs no transfer | superseded by `O45`; the rules follow D20 (§ 4) |
| F9 | D6 decides n < 0 reads the rest and cites `io.BufferedIOBase`, which raises `ValueError` for n < -1 | new |
| F10 | Exhausted is the oracle's fact (pos = length), not the stream's: a stream learns the end from a read returning nothing, which reaches the backend and can fail or be cancelled | new |

Seven of the 16 rules carry an `assumed` field: six rest on F1, F2, F3, F4,
F5 or F10, and Z2 on `io.IOBase` (`seekable()` on a closed file). Findings and gaps are reported only; what to do with them is the
maintainer's (CLAUDE.md § Audits).

## 7. Limits and what this does not feed

- **One author.** Rows, rules, model and oracle share an author and some
  assumptions; the mutants show the checks can fail, not that they are
  complete. Local is the first artifact written by someone else.
- **One slice, one backend.** Pinning under writes (D21, D22, D25, D26),
  retries and resume (D38, D39), memory (D40) and every network backend are
  untried.
- **Not BK-506.** Everything here derives from the record, so RFC-0029 R4's
  read scope keeps it from any session writing that trial's oracles. It
  measures nothing about faithfulness.
- **Not step 5's model.** RFC-0024 § 9 step 5's model and profile tables are
  BK-485's own deliverables; this folder freezes and is not extended into them.
