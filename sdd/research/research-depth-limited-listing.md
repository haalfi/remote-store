# Research: Depth-Limited Listing

**Date:** 2026-03-26
**Status:** Proposed
**Scope:** `list_files(max_depth=N)` and `list_folders(max_depth=N)` —
performance analysis, native backend feasibility, and a phased design proposal.
**Related:** ID-107, ID-108, ID-112, ID-113,
[ADR-0009](../adrs/0009-glob-three-tier-design.md),
[018-glob.md](../specs/018-glob.md).

---

## 1. Problem Statement

`Store.list_files()` offers a binary choice: `recursive=False` (depth 0 only)
or `recursive=True` (all depths). `Store.list_folders()` always returns
immediate children (depth 0). There is no way to request "files/folders up to
N levels deep."

Real use cases where depth control matters:

- **Dataset discovery:** A data lake has `dataset/version/partition/` structure.
  Listing top-level dataset directories (`max_depth=1`) without scanning
  millions of leaf files.
- **Shallow inventory:** Show the first two levels of a project folder for a
  UI tree view without fetching the full recursive listing.
- **Controlled recursion:** Enumerate files at depth 0--2 to populate a preview
  table, without waiting for a full S3 `find()` over 250k+ objects.

The workaround today is `list_files(recursive=True)` and post-filtering by
path component count. This is **correct but wasteful** — every backend fetches
the full tree, then the caller discards most of it.

---

## 2. Current Backend Listing Mechanisms

Understanding what each backend does under the hood is critical for evaluating
whether native depth-limiting would actually reduce I/O.

### 2.1 S3 (s3fs) and S3 PyArrow

| Mode | Mechanism | I/O cost |
|------|-----------|----------|
| `recursive=False` | `s3fs.ls()` — single `ListObjectsV2` with `Delimiter=/` | 1 paginated API stream |
| `recursive=True` | `s3fs.find()` — single `ListObjectsV2` **without** delimiter | 1 paginated API stream (all keys) |

S3 has no server-side depth parameter. `ListObjectsV2` supports only two modes:
flat (all keys under prefix) or delimiter-based (one level of CommonPrefixes).

**Depth-limited alternatives for S3:**

- **Level-by-level delimiter listing:** Call `ListObjectsV2` with `Delimiter=/`
  at each discovered prefix, up to `max_depth` levels. Cost: O(folders within
  depth) API calls, but each returns only one level.
- **Single flat scan + client filter:** One `find()` call, filter by path depth
  client-side. Cost: 1 API stream, but transfers all object metadata.

Which is faster depends on the shape of the data:

| Scenario | Flat scan + filter | Level-by-level |
|----------|-------------------|----------------|
| 10k files, depth 1 of 5 levels | Fetches 10k, keeps ~2k | 1 + ~20 API calls |
| 250k files, depth 1 of 3 levels | Fetches 250k, keeps ~1k | 1 + ~50 API calls |
| 100 files, depth 10 | Fetches 100, keeps all | 10+ chained API calls |
| Wide + shallow (1k dirs, 10 files each) | Fetches 10k | 1 + 1k API calls |

**Takeaway:** For S3, level-by-level is better when depth is shallow and the
tree is deep/large. Flat scan is better when depth is large or the tree is
small. A native implementation should choose the strategy based on heuristics
or let the caller hint.

### 2.2 Azure Blob Storage

| Mode | HNS (Data Lake) | Non-HNS (Blob prefix) |
|------|-----------------|----------------------|
| `recursive=False` | `get_paths(recursive=False)` | `walk_blobs()` with prefix |
| `recursive=True` | `get_paths(recursive=True)` | `list_blobs()` flat scan |

Same story as S3 for non-HNS: no server-side depth parameter, only flat vs.
delimiter-based. HNS has `get_paths(recursive=bool)` — binary, no depth.

**Depth-limited alternative:** Same level-by-level approach using `walk_blobs()`
at each level. Same tradeoffs as S3.

### 2.3 Local Filesystem

| Mode | Mechanism |
|------|-----------|
| `recursive=False` | `Path.iterdir()` — single `readdir()` syscall |
| `recursive=True` | `Path.rglob("*")` — full recursive `os.scandir()` walk |

**Depth-limited alternative:** `os.walk()` with depth computed from the
directory path. `os.walk()` traverses top-down in DFS order, so computing
depth relative to the root lets us prune subtrees by clearing `dirnames`:

```python
# Sketch: depth-limited walk
root_depth = str(root).count(os.sep)
for dirpath, dirnames, filenames in os.walk(root):
    depth = dirpath.count(os.sep) - root_depth
    if depth < max_depth:
        # yield files in dirpath...
        pass
    elif depth == max_depth:
        # yield files in dirpath, but stop descending
        dirnames.clear()
    else:
        # should not reach here if dirnames.clear() worked,
        # but guard defensively
        dirnames.clear()
        continue
```

Note: `enumerate(os.walk(...))` would be incorrect here — `os.walk` yields
directories in DFS order, not level-by-level, so the iteration index does not
correspond to filesystem depth in branched trees. Computing depth from the
path component count is the reliable approach.

**Takeaway:** Native depth limiting is trivially efficient for Local. The
`rglob()` approach scans everything; `os.walk()` with path-based depth
tracking stops early. Direct I/O savings.

### 2.4 SFTP

| Mode | Mechanism |
|------|-----------|
| `recursive=False` | `listdir_attr()` — 1 SFTP round-trip |
| `recursive=True` | Manual recursion: `listdir_attr()` per directory | O(total_dirs) round-trips |

SFTP has **no bulk recursive listing**. Each directory requires an independent
network round-trip. This makes depth limiting the most impactful optimization:

| Depth | Directories listed (10 dirs/level) | SFTP round-trips saved vs full recursion (4 levels) |
|-------|-----------------------------------|-----------------------------------------------------|
| 0 | 1 | ~1110 |
| 1 | 11 | ~1100 |
| 2 | 111 | ~1000 |
| Full | 1111 | 0 |

**Takeaway:** SFTP benefits the most from native depth limiting. Every skipped
level avoids real network round-trips. The extension-only approach (full
recursive scan + filter) would still make all those round-trips.

### 2.5 Memory

| Mode | Mechanism |
|------|-----------|
| `recursive=False` | Direct `children` dict iteration |
| `recursive=True` | Iterative DFS with stack |

The stack already tracks `(node, prefix)`. Adding depth tracking is trivial:
change to `(node, prefix, depth)` and skip pushing children when
`depth >= max_depth`.

**Takeaway:** Minor optimization (in-memory traversal is already fast), but
trivial to implement and useful for test correctness.

### 2.6 HTTP

Does not support listing (`CapabilityNotSupported`). Not relevant.

---

## 3. Performance Summary

| Backend | Extension approach (full scan + filter) | Native approach (stop early) | Savings |
|---------|----------------------------------------|------------------------------|---------|
| **SFTP** | O(total_dirs) round-trips | O(dirs within depth) round-trips | **Critical** — network I/O |
| **Local** | Full `rglob()` filesystem walk | `os.walk()` stops at depth N | **High** — syscall I/O |
| **S3** | 1 flat API stream (all keys) | Level-by-level delimiter calls | **Depends on shape** (§2.1) |
| **Azure** | 1 flat API stream or HNS recursive | Level-by-level `walk_blobs()` | **Depends on shape** (§2.2) |
| **Memory** | Full DFS traversal | DFS with depth cutoff | **Low** — in-memory |

The key insight: **for SFTP and Local, native depth limiting is unambiguously
better.** For S3 and Azure, neither strategy dominates — flat scan transfers
more metadata but uses fewer API calls, while level-by-level uses more API
calls but transfers less data (§2.1). The flat-scan-and-filter strategy is a
safe default for S3/Azure because it is always *correct* and avoids the
complexity of shape-dependent heuristics. It may transfer unnecessary data for
shallow depth on large trees, but avoids the O(folders) API call overhead
that level-by-level incurs on wide trees.

---

## 4. Design Proposal: Two-Phase Depth-Limited Listing

### 4.1 Depth semantics (unified across `list_files` and `list_folders`)

Both `list_files` and `list_folders` use the same `max_depth` parameter with
consistent semantics:

- `max_depth=None` (default): current behavior unchanged.
- `max_depth=0`: items directly in `path` itself (no descent).
- `max_depth=1`: items in `path` + items in its direct subfolders.
- `max_depth=N`: items up to N folder levels below `path`.

Using the same parameter name and semantics for both methods avoids the
off-by-one confusion that would arise from naming one `max_depth` and the
other `depth` with different reference frames.

### 4.2 Interaction with `recursive`

When `max_depth` is provided, it takes full control of traversal depth —
`recursive` is ignored. This avoids contradictory states and keeps the
contract simple:

- `max_depth=None` (default): `recursive` flag controls, as today.
- `max_depth=0`: items in `path` only (equivalent to `recursive=False`).
  `recursive` is ignored.
- `max_depth > 0`: descend up to N levels. `recursive` is ignored — depth
  implies recursion.

The alternative — raising `ValueError` when `max_depth > 0` and
`recursive=False` — was considered but rejected. Since `recursive` defaults
to `False`, callers writing `store.list_files(path, max_depth=2)` would hit
the `ValueError` unless they also passed `recursive=True`, which is redundant.
Ignoring `recursive` when `max_depth` is set is the more ergonomic contract.

### 4.3 Interaction with `pattern`

`Store.list_files(pattern=)` applies fnmatch on basenames client-side.
When combined with `max_depth`:

1. Depth filtering applies first (determines which files to consider).
2. Pattern filtering applies second (filters the depth-limited set by name).

These compose naturally — no special handling needed.

### 4.4 Interaction with `iter_children`

`Store.iter_children()` returns `FileInfo | FolderEntry` at a single level.
It stays single-level by design. Depth-limiting applies only to `list_files`
and `list_folders`. Users who want depth-limited mixed listings can combine
the two calls.

### 4.5 Phase 1: Store-level parameters with client-side filtering

Add `max_depth` to `Store.list_files()` and `Store.list_folders()`:

```python
def list_files(
    self,
    path: str,
    *,
    recursive: bool = False,
    pattern: str | None = None,
    max_depth: int | None = None,
) -> Iterator[FileInfo]:

def list_folders(
    self,
    path: str,
    *,
    max_depth: int | None = None,
) -> Iterator[FolderEntry]:
```

**Implementation at Store level — no ABC change:**

- `list_files(max_depth=N)`: delegates to
  `Backend.list_files(path, recursive=True)` and filters results client-side
  by counting path components relative to `path`. The Store already does
  client-side filtering for `pattern` — depth filtering follows the same
  approach.
- `list_folders(max_depth=N)`: BFS using `Backend.list_folders()` at each
  level, up to `max_depth` levels. Each BFS step is one call to the existing
  backend method.

This matches how `pattern` was added: Store-level concern, no backend
awareness needed, works with all backends immediately.

**What ships:** Store parameter, spec, tests, docs. No new extension module.

**Effort:** Small-medium. Store plumbing, spec, ~150 lines of tests.

### 4.6 Phase 2: Backend-native optimization

Add `max_depth: int | None = None` as an optional keyword parameter to
`Backend.list_files()`:

```python
# Backend ABC — default implementation
def list_files(
    self, path: str, *, recursive: bool = False, max_depth: int | None = None,
) -> Iterator[FileInfo]:
```

**Default behavior in ABC:** The default implementation ignores `max_depth` and
uses the existing `recursive` logic. This is backward-compatible — existing
backend implementations (including third-party) continue to work without
changes.

**Store delegation:** When `max_depth` is not `None`, `Store.list_files()`
passes it through to the backend. The Store still applies client-side depth
filtering on the result — this is a no-op when the backend already filtered
natively, and a correctness safety net when it didn't. No `TypeError`
catching, no `inspect.signature` probing — just always filter at the Store
level and let native backends reduce the work upstream.

**Backend overrides:**

| Backend | Native strategy |
|---------|----------------|
| **Local** | `os.walk()` with depth counter (§2.3). Clear win. |
| **SFTP** | Pass depth limit through recursive calls. Clear win. |
| **Memory** | Track depth in DFS stack. Trivial. |
| **S3** | Keep flat scan + client filter. Level-by-level is a future optimization when tree shape heuristics are available. |
| **Azure** | Same as S3 — flat scan + client filter. |

**`Backend.list_folders()` — no ABC change needed.** Recursive folder listing
is always a BFS/DFS traversal using `list_folders()` at each level. The
Store-level implementation (Phase 1) handles this without backend changes.
The backends that benefit most (SFTP) already get the win through
`list_files(max_depth=N)` stopping the recursion early.

Backends that implement `max_depth` natively don't need a new capability flag.
Unlike glob, there is no semantic difference between "native" and "fallback"
depth filtering — the result is identical. The only difference is performance.

**Backend implementation priority:**

| Backend | Priority | Reason |
|---------|----------|--------|
| **SFTP** | P0 | Biggest I/O savings (network round-trips) |
| **Local** | P0 | `os.walk()` depth cutoff is trivial and effective |
| **Memory** | P1 | Easy, useful for tests |
| **S3** | P2 | Flat scan is often optimal anyway; level-by-level needs heuristics |
| **Azure** | P2 | Same reasoning as S3 |

**Effort:** Medium. ABC change, 2--3 backend overrides, Store delegation
update, spec updates, test updates.

---

## 5. Why Not an Extension Module?

The original proposal included a `ext/listing.py` module with
`list_files_deep()` and `list_folders_deep()` as a Phase 1 deliverable,
following the glob three-tier pattern (ADR-0009). On review, this adds
API surface that would be deprecated shortly after:

- **Glob's extension earned its existence** because `ext.glob.glob_files()`
  does something `Store.list_files(pattern=)` cannot — full-path matching
  with `**` patterns. The extension provides genuinely different behavior.
- **Depth filtering has no such gap.** `Store.list_files(max_depth=N)` is
  the complete API. An extension wrapping it adds nothing.
- **Naming is awkward.** "Deep" implies going deeper, but the feature limits
  depth. Any name (`list_files_to_depth`, `list_files_bounded`) is clunky
  compared to the native parameter.

The simpler path: add `max_depth` to Store directly (Phase 1) with
client-side filtering. This ships the same user-facing API without a
throwaway extension layer.

### Comparison with glob pattern

| Aspect | Glob | Depth-Limited Listing |
|--------|------|----------------------|
| **Store param** | `list_files(pattern=...)` — name filter | `list_files(max_depth=N)` — depth filter |
| **Native backend** | `Backend.glob()` + `Capability.GLOB` | `Backend.list_files(max_depth=N)` — no new capability |
| **Extension** | `ext.glob.glob_files()` — full path glob (genuinely different) | Not needed — Store param is sufficient |
| **Fallback** | `list_files()` + client regex | `list_files(recursive=True)` + client depth filter |
| **ABC change?** | Yes (new `glob()` method) | Yes (new `max_depth` kwarg, Phase 2 only) |

The key difference: glob needed three tiers because each tier offers distinct
semantics. Depth limiting does not — the output is always identical regardless
of where filtering happens. Two phases (Store param, then backend
optimization) are sufficient.

---

## 6. Alternatives Considered

### A. Extension only — never add to Store/Backend

**Pros:** No ABC change, no risk of breaking backends.
**Cons:** Permanently leaves performance on the table for SFTP and Local.
Users who need depth limiting always pay for a full recursive scan.

**Verdict:** Insufficient long-term. The Store parameter (Phase 1) is nearly
as simple and avoids the throwaway extension problem.

### B. New `Capability.DEPTH_LIST` flag

Add a capability that signals "this backend supports `max_depth` natively."
The extension checks the capability and delegates or falls back.

**Pros:** Follows glob pattern exactly.
**Cons:** Unnecessary complexity. Unlike glob, depth filtering produces
identical results whether done natively or client-side. A capability flag is
for semantic differences, not performance differences. The Store can handle
the fallback transparently.

**Verdict:** Rejected. No user-visible behavioral difference to gate on.

### C. Add `max_depth` to Backend ABC as required parameter

Make `max_depth` a required parameter on `Backend.list_files()`.

**Pros:** All backends must handle it.
**Cons:** Breaking change for all backend implementations, including
third-party backends (e.g., community backends following the Build Your Own
Backend guide).

**Verdict:** Rejected. Optional keyword with default `None` is
backward-compatible.

### D. Separate `list_files_depth()` method on Backend

Add a new abstract method instead of extending the existing one.

**Pros:** Clean separation, no signature change.
**Cons:** Duplicates listing logic. Every backend would need two nearly
identical methods. Maintenance burden.

**Verdict:** Rejected. An optional kwarg is simpler.

### E. Extension-first, then promote to Store

Ship `ext/listing.py` with `list_files_deep()` / `list_folders_deep()` first,
then add Store parameters and deprecate the extension.

**Pros:** Incremental delivery, lowest-risk first step.
**Cons:** Ships public API that will be deprecated. Extension naming is
awkward ("deep" = limiting depth). The Store parameter with client-side
filtering is equally simple to implement and avoids the deprecation cycle.

**Verdict:** Rejected. Adding the Store parameter directly is just as easy
and avoids throwaway API surface. See §5.

---

## 7. Backlog Items

This research proposes splitting ID-107 and ID-108 into two phases:

### Phase 1 — Store parameters with client-side filtering

- **ID-107 — `Store.list_files(max_depth=N)` with client-side filtering**
  Add `max_depth` parameter to `Store.list_files()`. Implement via
  `Backend.list_files(recursive=True)` + client-side depth filtering at the
  Store level. Spec, tests, docs. No ABC change, no extension module.

- **ID-108 — `Store.list_folders(max_depth=N)` with BFS traversal**
  Add `max_depth` parameter to `Store.list_folders()`. Implement via BFS
  using `Backend.list_folders()` at each level. Spec, tests, docs. No ABC
  change.

### Phase 2 — Backend-native optimization

- **ID-107b — `Backend.list_files(max_depth=N)` native optimization**
  Add optional `max_depth` kwarg to `Backend.list_files()` ABC.
  Implement native depth limiting in Local (`os.walk()`), SFTP (recursive
  call depth tracking), Memory (DFS stack depth). S3/Azure: client-side
  filter (flat scan is often optimal). Store continues to filter client-side
  as safety net.
  Depends on: ID-107.

- **ID-108b — `Store.list_folders(max_depth=N)` optimization (if needed)**
  Evaluate whether backend-native folder depth limiting is needed based on
  Phase 1 usage. The Store-level BFS may be sufficient — folder listings are
  typically much smaller than file listings.
  Depends on: ID-108.

---

## 8. Recommendation

**Proceed with Phase 1 (Store parameters) first.** Add `max_depth` to
`Store.list_files()` and `Store.list_folders()` with client-side filtering.
No ABC change, no extension module, no new capability. This ships correct
behavior with a clean API that will remain stable through Phase 2.

**Follow with Phase 2 (native backend optimization) when depth-limited
listing sees real usage.** The performance gap is most acute for SFTP
(network round-trips) and Local (filesystem I/O). S3 and Azure can defer
native optimization — their flat scan is often competitive with or better
than level-by-level delimiter listing.

Phase 1 and Phase 2 can ship in the same release or separately. The user-
facing API (`Store.list_files(max_depth=N)`) is identical in both phases —
Phase 2 only changes performance characteristics.
