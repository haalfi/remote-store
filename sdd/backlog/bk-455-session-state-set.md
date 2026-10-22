# BK-455 — The `Session` has obligations but no state set, and its close/run race no model
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** BK-449 stated the `Session`'s exits in BE-033's
exit-owner table and left its states open. No `Session` exists in `src/`
(`rg 'class \w*Session|def invalidate|def run\(' src/remote_store` finds only
`ext/cache.py`, unrelated), so no row below has a cell. When this item builds
it, these obligations go back into spec 052 as sections of its own, beside the
state set this item decides.

## Moved out of spec 052, 2026-10-20

Verbatim from `sdd/specs/052-backend-lifetime.md` at `6e4c4fd`, by BK-456's
052 prune: they bind a component that does not exist, so they are intent,
which a spec does not carry ([`SPEC-DESIGN.md` Ready item 3](../SPEC-DESIGN.md#ready)).
The definition of `connection_dead` the first row carries stayed in spec 052's
Terms. A dated record, not kept current.

Terms:

> - **`Session`**: the connection owner of a remote driver (RFC-0017 D5). BE-033
>   states its obligations and no states for it.

BE-033, Scope:

> A `Session` (RFC-0017 D5) has an interface here and no
> states; its obligations below bind it.

BE-033, States:

> | `Session` | not stated here | — |

BE-033, Exit owners:

> | a connection a failure condemns | the `Session` | `invalidate` closes the client at once, and a stream on it fails mapped at its next read. `connection_dead` means transport-level death, the socket or session gone, never an error the next request on the same connection survives. A cancel never invalidates |
> | `unwrap` on a `Session` driver | the `Session` | goes through `run`, so after `invalidate` it reconnects |
> | a `close` racing in-flight calls on a `thread_safe` class (BE-028) | the `Session` | creating and tearing down the client is atomic against the closed flag, under a lock held around the accessor alone, never over I/O, and async re-checks after its connect await; `close` waits for no in-flight call, and the teardown wakes blocked calls, which fail mapped. On a `single_connection` class concurrent `close` is already the caller's misuse |
