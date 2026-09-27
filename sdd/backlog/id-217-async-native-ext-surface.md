# ID-217 — Async-native extension surface (owner for the deferred async `ext.*`)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 4](../BACKLOG.md#no-workarounds) by the ADR-0040 § 4
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`src/remote_store/aio/ext/` ships only `write.py` (`write_with_hash`); there is
no async equivalent of `ext.glob`, `ext.observe`, `ext.otel`, or `ext.integrity`
(audit-016 M6). A native `AsyncStore` consumer — the natural audience for an
async-native backend such as Graph — reaches the full `ext.*` surface only by
dropping to `AsyncBackendSyncAdapter` (ADR-0025), which forfeits the async
streaming the backend exists to provide. GR-003 calls this out for `GLOB`
specifically: async callers compose pattern matching over `list_files`
themselves "until an async equivalent of `ext.glob` lands as a separate backlog
item" — this is that item, and it owns the surface as a whole.
**Decision pending:** build per-extension async equivalents (glob first, as the
smallest and the one a spec promises), or formally decline the ecosystem and
document the sync-adapter route as the supported path. Declining is a
legitimate close; either outcome removes an open promise from a shipped spec.
- **`ext.cache` warning on a bridged backend** (was ID-218, absorbed here).
  `CachedStore` with an unset `max_content_size` materialises whatever the
  wrapped backend yields (`ext/cache.py`). Over a sync REST backend that is
  merely inconvenient; over an async-native backend reached through
  `AsyncBackendSyncAdapter` it silently defeats the streaming the user chose
  the backend for. ADR-0025 § Risks flags this and promises the cache
  extension "should learn to warn when wrapped over a bridged backend
  (tracked separately)"; this bullet is that owner. Scope: emit a warning (or
  require an explicit `max_content_size`) when `cache()` wraps a `Store` whose
  backend is an `AsyncBackendSyncAdapter` and `max_content_size` is unset.
  It is the same root cause — extensions do not understand async backends —
  so it resolves with the decision above rather than beside it. ADR-0025's
  sentence still reads "(tracked as ID-218)" and is Accepted, so it is not
  edited; `BACKLOG-DONE.md` § Absorbed is what makes that citation resolve.

## Correction, 2026-09-27

GR-003 no longer reads "lands as a separate backlog item": it now names this
item, "until an async equivalent of `ext.glob` lands (tracked as ID-217, the
async-native `ext.*` surface owner)" (`rg -n 'async equivalent of' sdd/specs`,
`044-graph-backend.md:97-99`). The gap itself is unchanged:
`ls src/remote_store/aio/ext/` lists `__init__.py` and `write.py` against
fifteen modules besides `__init__.py` in `src/remote_store/ext/`, and
`rg -n 'AsyncBackendSyncAdapter|warnings' src/remote_store/ext/cache.py` finds
nothing, so the absorbed ID-218 warning is unbuilt. ADR-0025:269 still reads
"(tracked as ID-218)". Found by the ADR-0040 § 4 conversion.
