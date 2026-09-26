# BUG-269 — `observe.md`'s level and `op` tables are enumerations that were already false on master, and BK-359 adds to both
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`docs-src/guides/observe.md` § *Logging levels used* and § *Structured `extra`
fields* are written as enumerations over the whole library — the section three
headings up names `remote_store.backends._local` as an example logger, so
backend records are in scope, not just `ext.observe`'s.
**Both were already false on master**, which is what keeps this out of
BK-359's scope rather than in it:
| Row | Says | Contradicted on master by |
| --- | --- | --- |
| `WARNING` | "Suppressed hook exceptions, fallback behaviour" | the `AUTO_ADD` host-key warning, `backends/_sftp.py:1828` — neither |
| `op` | "Operation name (`"read"`, `"write"`, ...)" | `op="connect"` (3 sites), `"download"`, `"upload"`, `"transfer"` — 5 non-operation values, counted by `git grep -n 'extra={"op"' origin/master -- src/` |
| `ERROR` | "Before re-raising backend errors" | nothing in `src/` logs at that level — **BUG-267**, filed separately |

BK-359 adds one more of each: an `op="error_mapping"` `WARNING` that is not a
suppressed hook exception and not an operation name. It is the third and sixth
instance respectively, not the first.
**Why it is filed and not fixed.** BK-359 rewrote these rows once; the rewrite
was reverted with the rest of its guide prose after four rounds found defects
in it, and this item is the paired record that revert owes — the same pairing
BUG-268 made for `troubleshooting.md`. Correcting the `op` row is not a fact
but a contract decision: whether `op` means "Store operation" (in which case
`connect`, `transfer` and `error_mapping` are misuses of the field) or
"operation or internal stage" (in which case the row is merely under-written).
That decision sits next to **BUG-267**'s, which is why both should be taken
together and neither inside a fix pass. **BUG-266** owns the observable-failure
→ arm table and reaches neither row.
