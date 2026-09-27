# BUG-266 — No artifact maps an observable SFTP failure onto the arm that handles it, and four prose attempts were each refuted
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`_map_exception` dispatches on exception *type*, and SFTP-023 states the arms
that way — correctly, and pinned by tests. What no artifact states correctly is
the other direction: given a failure a reader can observe (a refused port, a
wedged daemon, a silent peer, a rejected credential, a DNS failure), which arm
does it reach and what does the caller get.
**Four attempts to summarise that in a sentence were each refuted by
measurement**, all during BK-359's review loop: "a failed probe logs once per
poll"; "two records per poll, three under `AUTO_ADD`"; "a failed probe writes
more than one record" (zero under `RetryPolicy.disabled()`); and "only a probe
that fails by timeout reaches the mapping" — refuted by a bad SSH banner, an
accept-then-hangup and an `AuthenticationException`, all three of which reach
`_unavailable` through the `SSHException` arm with one `op="error_mapping"`
record.
**The diagnosis is that the space has axes a sentence cannot carry**: the
observable failure, the mapping arm, the retry policy's `max_attempts`, and
the host-key policy. Each refuted attempt stated one cell of that product as
though it were the whole table.
**Disposition:** write it once as a parametrised test enumerating
observable-failure x arm, asserting the resulting type, message shape and
record count, then let the spec and the guides point at the test rather than
restate it. The harness exists — `_StallRelay` plus the in-process server
already drive stalls in both directions, and BK-359's review produced working
probes for a refused port, a DNS failure, a bad banner and an
accept-then-hangup. Sized M because the enumeration, not the assertion, is the
work.
**Filed by BK-359's round 4**, after that loop's repeat-site check fired:
three rounds refuting one condition means enumerate the space rather than
restate it a fourth time.
