# Clause schema for the whole-record pass

<!-- doc: repo-only -->

One TOML file per group (`a.toml` to `d.toml`) plus `../pilot.toml`, checked
together by `../check_whole.py`. Record: `observe/OP-01/freeze-1` (`a7de4e31`).

A **clause** is one observable behaviour: given (pre-state), when (call or
trigger), then (outcome), stated as it holds after every amendment of the
decisions it cites. A decision that states no behaviour of its own (a
definition, a table shape, a pointer, a close-out note) goes in `record_text`
with its reason.

```toml
[[clause]]
id = "A01"                      # group letter + two digits
given = "..."
when = "..."
then = "..."
decided_by = ["D8", "D53"]      # deciding decisions as amended, latest wording last
axis = "AX-3"
path = "absent"
trigger = ["O1"]                # a set: every row that reaches this outcome
form = "both"
api = "both"
state = "none"
scope = "portable"
kind = "single call"
status = "decided"
gap = "F3"                      # optional: spike F-n, or OP-01/O<n> for an open item
local = "untested"

[[record_text]]
decision = "D100"
reason = "..."
```

| Facet | Vocabulary |
|---|---|
| path | success, end, absent, caller-error, content-failure, storage-failure, cancellation, release, concurrent, non-promise, lifetime-end, configuration |
| trigger | list of O1, O2, O3, Runtime, GC, E1..E19 (Environment rows); a row is named wherever one describes the event (a cancellation is E14), and a World-triggered response lists the rows that reach it |
| form | stream, whole, text, both (whole and stream), all (whole, text, stream), handle |
| api | sync, async, both |
| state | stream: Open, Exhausted, Failed, Closed, not-Closed, any; none (no stream exists yet: a whole read, a stream's open) |
| scope | portable, variation:<D43 point>, backend:<name> |
| kind | structure, function, single call, lifetime, environment, liveness (SPEC-DESIGN Rule 2) |
| status | decided, partly, implied, open |
| local | pass, untested, not-offered, C1..C8 (spike evidence only; default untested) |

Decided conventions (2026-11-03 dialog):

- **Kind, trigger apart:** the library's response to a World row is the kind
  of the behaviour (lifetime for a stream, single call for a whole read); the
  trigger facet carries the World row. `environment` is kept for assumptions
  about the World and D43 deviations.
- **Trigger is a set** of rows, taken from D19's exposure table and D34/D96
  where they name rows.
- **Status measures the behaviour**, not readiness to land: a clause whose
  behaviour is decided is `decided`, and a landing block (OP-01/O9's category
  names) goes in `gap`.
- **State sets are allowed** (`not-Closed`, `any`); split a clause only where
  the outcome differs.
- `path = absent` for a missing key, a folder or root where an item is asked (not an item); `content-failure`
  for content the call cannot use (a strict decode); `concurrent` for an overlapping
  O2/O3 change; `configuration` for timeouts, defaults, retries, profiles.
