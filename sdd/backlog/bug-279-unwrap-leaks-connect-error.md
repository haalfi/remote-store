# BUG-279 — `unwrap(SFTPClient)` leaks the raw paramiko or socket error when the connection cannot be established
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

SFTP-024's invariant is stated over "no paramiko, socket, or OS exception
raised *by the backend*" reaching callers. `unwrap` returns `self._sftp`
(`SFTP-026`), which evaluates the lazy property and so can run the whole
connect budget — and it is **not** wrapped in `_errors()`, so whatever
`_connect` raises escapes unmapped.
**Measured** against a backend that has never connected, one entry into
`_connect` per case:

| connect-time shape | raised |
|---|---|
| refused port | `paramiko.ssh_exception.NoValidConnectionsError` |
| DNS failure | `socket.gaierror` |
| connect timeout | `TimeoutError` |

Every other operation answers `BackendUnavailable` for all three.
**What it costs a caller:** someone following the health-check guide writes
`except BackendUnavailable` and gets none of these; an escape hatch that is
documented as returning the driver's client instead raises a driver exception
the error model promises never to surface.
**Disposition, and it is a real choice rather than a one-liner.** Either wrap
the property access in `_errors()` — which makes `unwrap` obey SFTP-024 at
the cost of the escape hatch no longer being transparent about *why* it could
not hand back a client — or amend SFTP-024 to carve `unwrap` out explicitly,
on the grounds that a caller reaching for the driver has opted into driver
errors. **The carve-out is the likelier answer** (the method's whole purpose
is driver access) but it is currently neither stated nor tested, so the
invariant reads as breached rather than bounded. Whichever way, SFTP-026 gains
a `Raises:` line, which it has never had.
**Pre-existing, not introduced by BUG-274** — that item only measured it,
while accounting for why `unwrap` is excluded from its operation enumeration.
**Found by BUG-274's round-5 unprimed reviewer.**
