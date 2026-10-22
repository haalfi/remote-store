# ADR-0049: Close and Concurrent-Use Postures Are Declared per Backend

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

Records why spec 052's BE-020 and BE-028 declare a posture rather than one
behaviour for every backend, and the maintainer's answers of 2026-10-20 that
BK-456's 052 prune put into them (decision log
`sdd/decisions/dd1c9401-8614-5d9e-aa25-af591b8788f8.jsonl`). The clauses are
the spec's; this record gives their why. A search of `sdd/adrs/` for
`close_is_terminal`, `terminal close`, `concurrent-use`, `thread_safe` and
`single_connection` finds no ADR that decides either posture.

## Context

Backends differ in what their native clients allow. A cloud SDK client holds
connections and credentials that a close releases, and reopening them silently
hides a use-after-close. A stateless or in-memory backend has nothing worth
refusing. One SFTP channel, or `urllib`'s shared opener, cannot be shared
between threads; a cloud SDK client can. A single behaviour for every backend
would be false for some of them, and a behaviour left implicit was the
assumption a `Store` caller had to read source to check. Two facts found by
audit 024 constrain the statement: what the concurrency lane asserts is weaker
than the per-operation atomicity spec 052 claimed (S3's `move` is copy then
delete, S3-028), and a posture can depend on configuration (SQL-BLOB-072,
HTTP-CONC-001), while no attribute in `src/` declares it.

## Decision

- **Close is a declared posture, `close_is_terminal`.** A terminal close turns a use-after-close (a likely bug) into a clear typed error instead of a silent resource reopen, while leaving stateless/cheap backends freely reusable. *Reverse when* a reusable backend is shown to leak or reopen something a caller can observe.
- **A gate on an undeclared capability outranks the closed guard on every
  backend**, as on the kernel, for a call the capability names as a whole
  (`GLOB`, `ATOMIC_WRITE`, on the kernel `MOVE` and `COPY`): capability data is
  not a live operation, so a closed backend still answers what it cannot do.
  WR-010's metadata refusal depends on an argument and keeps BE-008's rank,
  after the closed guard. *Reverse when* a backend needs a live call to know
  its capabilities.
- **The sync adapter is outside BE-020's postures.** Its close is ASYNC-083's
  one-shot `RuntimeError`; the inherited `close_is_terminal = False`
  misdeclares it, a defect filed apart rather than a reason to bend BE-020.
- **Concurrent use is a declared posture, `thread_safe` or `single_connection`.** This clause turns "thread-safe" from an unstated assumption into an explicit per-backend obligation a caller can read from the spec without reading source. Like CAP-007's quality flags, declaring the posture gates no method; it documents a property every method has.
- **`thread_safe` promises what the conformance lane asserts**: no error a
  lone call would not raise, writes to distinct keys all landing, reads that
  see a completed write. Per-operation atomicity is a capability's
  (`ATOMIC_MOVE`, `ATOMIC_WRITE`). *Reverse when* a cell asserts more for
  every `thread_safe` backend.
- **A backend's spec declares its posture per configuration**, until code
  declares it, which is a gap against `SPEC-DESIGN.md` Rule 5 tracked in the
  backlog. *Reverse when* a declaration in code exists: it then becomes the
  profile's declaration.

## Consequences

- Positive: each posture's outcomes are a table a test can fail, and a
  backend's choice is stated where its reader looks.
- Negative: a backend's posture lives in prose in its own spec, which nothing
  checks against the registry the concurrency lane reads.
- Neutral: the sync adapter keeps a close behaviour that no posture names.
