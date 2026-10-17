# BK-449 — No interaction protocol with states joins `Store`, kernel, driver and `Session`
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit 023](../audits/audit-023-kernel-migration-readiness.md),
finding T20 and proposal P0, at `52448e0`. The audit's evidence, probes and
**Checked:** lines are the record; this dossier does not copy them.

**The gap.** The contract is stated call by call, and the Python `Protocol`
classes fix signatures. No artifact states the interaction as a protocol: the
states each party passes through, which call is legal in which state, which
transition a failure, a cancellation or a close takes, and which party owns each
exit. The states exist, scattered: the backend's closed posture (BE-020), the
`Session`'s connect, invalidate and reconnect (RFC-0017 D5, an interface without
states), a write handle's open, commit or abort, a read stream's lifecycle, a
listing's cursor. `ResourceSafety.dfy` §1 and §3 model the pre-kernel classes.
Memory has no `Session`, so the audit drew this from the design text, not from
measurement.

**What it decides** (audit-023 P0, advisory):

- the state sets: backend, `Session`, read stream, write handle, listing cursor,
  caller's content iterator;
- each call's meaning in each state: the closed guard, `unwrap`, a repeated
  `close`, when a refusal surfaces (at the call or at the first iteration);
- the owner of each exit on every path, cancellation included;
- where it is stated and checked: a spec 003 section, a state model in the
  formal layer, one conformance cell per transition on a session-less and a
  `Session` driver.

**Findings it carries:** T20; the state half of T5 (close after a failed read),
T11 (`unwrap` after close) and T16 (the `open_write` handle); the lower-ranked
rows on repeated `close`, async `connection_dead`, cancellation routes and
async refusal timing.

- **(was BK-448, absorbed here)** The async kernel leaves a caller's content
  iterator suspended when it refuses a chunk or the write fails: `_marked`
  (`_kernel/_async/_io.py`) raises on a non-bytes chunk without `aclose()` on the
  caller's iterator, so its `finally` runs only at GC, on whatever loop is then
  current (BUG-335: 4 of 4 write routes). No spec covers caller-supplied content;
  the nearest, SEEK-011, closes a stream the library consumed. Its open decision,
  the kernel closes what it abandons or BE-030 says the caller owns it, is one of
  this item's exit owners.

**Due:** before RFC-0017 D3 step 2, the first remote driver and its `Session`.
BK-450's owner table names `Session` obligations that this item's states define.
