# RFC-0013: `list_folders(pattern=…)` — Name-Based Glob Filter

## Status

Implemented

## Summary

Add an optional `pattern=` keyword to `Store.list_folders` and
`AsyncStore.list_folders`, mirroring the existing `list_files(pattern=…)`
(STORE-014). When set, `FolderEntry` items whose `.name` does not match the
pattern via `fnmatch.fnmatch` are excluded from results. Filtering runs at
the Store level after BFS traversal and path rebasing; `max_depth` controls
traversal depth, `pattern` filters yielded results, and the two compose
naturally.

## Motivation

`list_files` accepts `pattern=` for name-based glob filtering at the Store
level. `list_folders` does not. There is no design reason for the asymmetry
— `FolderEntry` has carried `.name` since ID-072 / v0.17.0 (PathEntry
protocol), so name-based filtering is purely a Store-level concern.

Citizen-developer use cases that motivate the parameter:

- Listing only date-partitioned subfolders: `list_folders(prefix, pattern="20*")`.
- Filtering Hive-style partition folders: `pattern="ds=*"`.
- Discovering tenant-specific subtrees: `pattern="tenant_*"`.

Without the kwarg these all require post-hoc Python filtering on top of an
unfiltered `list_folders` walk, which obscures intent and (for deep walks)
forces materialisation that `pattern=` could elide at iteration time.

## Proposal

### API surface

```python
def list_folders(
    self,
    path: str,
    *,
    pattern: str | None = None,
    max_depth: int | None = None,
) -> Iterator[FolderEntry]: ...
```

Same signature on `AsyncStore.list_folders` returning `AsyncIterator[FolderEntry]`.

### Spec changes

- New rule `STORE-017` in `sdd/specs/001-store-api.md`:
  `list_folders(path, *, pattern=None, max_depth=None)` accepts an optional
  `pattern` keyword. When set, `FolderEntry` items whose `.name` does not
  match the pattern via `fnmatch.fnmatch` are excluded. Filtering is
  Store-level, applied after BFS traversal and path rebasing.
- `DEPTH-002` in `sdd/specs/037-depth-limited-listing.md` updated: signature
  gains `pattern=None`; filtering-order note added — depth controls
  traversal, pattern filters yielded results.

### Behaviour

- `pattern is None` is identical to today's behaviour (no filter).
- BFS continues regardless of pattern match: a folder whose name does not
  match the pattern is still descended into when `max_depth > 0`. The
  pattern is a yield filter, not a traversal pruner. Callers who want
  pattern-pruned traversal can compose `pattern=` with a manual descent.
- Composes with `max_depth` independently: `list_folders(p, pattern="raw_*",
  max_depth=2)` yields all folders named `raw_*` at depths 0, 1, and 2.

### Subclass propagation

- `ProxyStore.list_folders` and `ObservedStore.list_folders` accept
  `pattern=` and forward it.
- `CachedStore.list_folders` extends its cache key tuple with the pattern:
  `("list_folders", path, pattern_key, depth_key)` where `pattern_key`
  uses `"\x00"` as the sentinel for `None` (matching the existing
  `depth_key` convention).

## Alternatives Considered

### Push `pattern=` into the `Backend` ABC's `list_folders`

Rejected. `Backend.list_files` does not accept `pattern=` either — `list_files`
filtering is already Store-level. Pushing filtering down would either (a)
break parity between `list_files` and `list_folders`, or (b) require the same
migration on `list_files`, which is out of scope. Backend-native filtering
would only pay off if a backend exposed prefix-aware listing (e.g. S3
`ListObjectsV2` with `Prefix`), and even then the prefix is path-level, not
name-glob — fnmatch is not directly expressible as an S3 prefix.

### Filter as part of BFS, pruning non-matching subtrees from descent

Rejected. A non-matching folder name says nothing about the names of its
descendants. Example: `archive/raw_2026/` with `pattern="raw_*"` — `archive`
does not match, but its child `raw_2026` does. Pruning at the parent level
would skip the descent and miss `raw_2026` entirely; the user would see no
match where the spec requires one. Pruning would change results, not just
performance. The semantics chosen here (yield-time filter) keep `pattern=`
and `max_depth=` orthogonal.

### Add a separate `glob_folders(...)` extension instead

Rejected. `ext.glob.glob_files()` already exists for path-based globs;
`list_folders(pattern=…)` is the name-based parallel of `list_files
(pattern=…)`, not a path-glob feature. Splitting it into an extension would
fragment the API by symmetry boundary alone, with no implementation
benefit.

## Impact

- **Public API:** No change to `__all__` (method already exported). New
  keyword-only parameter with `None` default — additive, non-breaking.
- **Backwards compatibility:** Non-breaking. Existing call sites continue
  to work unchanged. Pre-v1 semver acknowledged but not invoked.
- **Performance:** `fnmatch.fnmatch` is O(name × pattern) per yielded
  entry; negligible vs the listing I/O. No new round trips.
- **Cache shape:** `CachedStore` cache keys for `list_folders` now include
  a pattern slot. The old key was a 3-tuple `("list_folders", path,
  depth_key)`; the new key is a 4-tuple `("list_folders", path,
  pattern_key, depth_key)`. Python tuple equality requires equal length, so
  no prior 3-tuple entry can ever match a new 4-tuple lookup. Persisted
  cache entries from prior versions become unreachable after upgrade and
  will be evicted by TTL. The implementation reuses the same `"\x00"`
  null-sentinel convention already used by `list_files` cache keys — see
  `ext/cache.py` for the encoding.
- **Testing:** `tests/test_glob.py::TestListFoldersPattern` covers fnmatch
  semantics (exact, wildcard, single-char), the `pattern=None` no-op
  equivalence, `max_depth` composition, and a real-backend end-to-end check.
  Wrapper-forwarding tests live alongside the existing wrapper suites
  (`test_proxy.py`, `test_observe.py`, `test_cache.py`) and the async parity
  cases in `tests/aio/test_async_store.py`.

## Open Questions

None at acceptance. Future work — pushing `pattern=` into the `Backend` ABC's
listing methods. Native `Backend.glob()` already exists (Local, S3,
S3-PyArrow, Azure, SQLBlob, SQLQuery declare `Capability.GLOB`), but it
matches full paths, not basenames, so it does not subsume the basename
fnmatch filter introduced here. If a backend ever exposes basename-aware
listing (or if `Capability.GLOB` is generalised to accept basename
patterns), a separate RFC can migrate `list_files` and `list_folders`
together. This RFC does not foreclose that path.

## References

- Backlog: ID-178.
- Specs: `sdd/specs/001-store-api.md` STORE-014 (the parent symmetry
  target), STORE-017 (new); `sdd/specs/037-depth-limited-listing.md`
  DEPTH-002 (amended).
