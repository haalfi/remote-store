# BUG-250 — `[graph]`'s drift smoke reaches one of the extra's four declared dependencies
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`scripts/drift_smoke_map.py:79` routes `graph` to
`["--import-only", "remote_store.aio.backends._graph.http"]`. That module's only
third-party import is `httpx`; `_graph/auth.py` imports `msal`, `msal-extensions`
and `platformdirs` lazily inside the methods that need them (`auth.py:173`,
`auth.py:194`). Reproduction: import the module and diff `sys.modules` — `httpx`
loads, `cffi` / `cryptography` / `platformdirs` / `msal` / `msal_extensions` do not.
So `check-graph` can go green while every drifted package in
`infra/drift-locks/graph.txt` is unexercised, and a `cryptography` or `msal` major
rides that verdict into a refresh and into a user's install. Hit in the
2026-08-10 firing (trace finding #32): all three drifted packages were outside
the smoke's reach, and the accepted `cryptography` 49→50 major turned out to be
covered only incidentally, by `[azure]` and `[sftp]` smoking identical pins.
The import-only shape is deliberate (BUG-225) — it catches a graph-hostile `httpx`
without needing msal or a network. A fix must widen reach without regressing that:
import the lazy call sites behind a no-network path, or add a cassette-backed target.
Worth auditing the other `--import-only` entry (`otel`) for the same shape.
