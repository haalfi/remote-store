# Research: Depth-Limited Listing

**Date:** 2026-03-26
**Scope:** `list_files(max_depth=N)` and `list_folders(depth=N)` — performance
analysis, native backend feasibility, and a phased design proposal following
the glob three-tier pattern (ADR-0009).
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
  Listing top-level dataset directories (`depth=1`) without scanning millions
  of leaf files.
- **Shallow inventory:** Show the first two levels of a project folder for a
  UI tree view without fetching the full recursive listing.
- **Controlled recursion:** Enumerate files at depth 0–2 to populate a preview
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

**Depth-limited alternative:** `os.walk()` with a depth counter. This is a
well-known pattern and trivially efficient — `os.walk()` yields level by
level, so stopping at depth N skips all deeper `readdir()` calls entirely.

```python
# Sketch: depth-limited walk
for depth, (dirpath, dirnames, filenames) in enumerate(os.walk(root)):
    if depth > max_depth:
        break
    # yield files...
    if depth == max_depth:
        dirnames.clear()  # prevent os.walk from descending further
```

**Takeaway:** Native depth limiting is trivially efficient for Local. The
`rglob()` approach scans everything; `os.walk()` with depth tracking stops
early. Direct I/O savings.

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
better.** For S3 and Azure, it depends on tree shape — but the extension
approach (flat scan) is never *worse* than the level-by-level approach for
those backends, so S3/Azure can keep the flat-scan-and-filter strategy even in
the native implementation and still be correct.

---

## 4. Design Proposal: Three-Tier Depth-Limited Listing

Following the glob pattern (ADR-0009): Tier 1 simple Store-level API,
Tier 2 native backend capability, Tier 3 portable extension.

### Tier 1: `list_files(max_depth=…)` — Store-level parameter

Add an optional `max_depth: int | None` parameter to `Store.list_files()`:

```python
def list_files(
    self,
    path: str,
    *,
    recursive: bool = False,
    pattern: str | None = None,
    max_depth: int | None = None,
) -> Iterator[FileInfo]:
```

**Semantics:**
- `max_depth=None` (default): current behavior — `recursive` flag controls.
- `max_depth=0`: only files directly in `path` (same as `recursive=False`).
- `max_depth=1`: files in `path` + files in its direct subfolders.
- `max_depth=N`: files up to N folder levels below `path`.
- When `max_depth` is set, `recursive` is ignored (depth is more precise).

**Implementation at Store level:** When `max_depth` is not `None`,
`Store.list_files()` delegates to `Backend.list_files(path, max_depth=N)`.
If the backend raises `TypeError` (doesn't accept `max_depth`), falls back
to `Backend.list_files(path, recursive=True)` + client-side depth filtering.

This mirrors GLOB-001: `pattern` was added to `Store.list_files()` as a
Store-level filter that works with any backend, no new capability needed.

**`list_folders` counterpart:** Add an optional `depth: int | None` parameter
to `Store.list_folders()`:

```python
def list_folders(
    self,
    path: str,
    *,
    depth: int | None = None,
) -> Iterator[FolderEntry]:
```

**Semantics:**
- `depth=None` (default): current behavior — immediate children only.
- `depth=0`: immediate children only (same as default).
- `depth=1`: children + grandchildren.
- `depth=N`: N+1 levels of nesting.

**Implementation at Store level:** BFS using `store.list_folders(path)` at
each level, up to `depth` levels. When backend supports native depth, delegate
directly.

### Tier 2: `Backend.list_files(max_depth=…)` — Native backend optimization

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
backend implementations continue to work without changes.

**Backend overrides:**

| Backend | Native strategy |
|---------|----------------|
| **Local** | `os.walk()` with depth counter (§2.3). Clear win. |
| **SFTP** | Pass depth limit through recursive calls. Clear win. |
| **Memory** | Track depth in DFS stack. Trivial. |
| **S3** | Keep flat scan + client filter for now. Level-by-level is a future optimization when tree shape heuristics are available. |
| **Azure** | Same as S3 — flat scan + client filter. |

Backends that implement `max_depth` natively don't need a new capability flag.
The parameter is optional with a default of `None` (no limit). Unlike glob,
there is no semantic difference between "native" and "fallback" depth
filtering — the result is identical. The only difference is performance.

**`Backend.list_folders()` depth parameter:** Not added to the ABC. Recursive
folder listing is always a BFS/DFS traversal using `list_folders()` at each
level. The Store-level implementation handles this without backend changes,
and the backends that benefit most (SFTP) already get the win through
`list_files(max_depth=N)` stopping the recursion early.

### Tier 3: `ext.listing` — Portable extension helpers

Extension module `src/remote_store/ext/listing.py` with two functions:

```python
def list_files_deep(
    store: Store,
    path: str,
    *,
    max_depth: int | None = None,
    pattern: str | None = None,
) -> Iterator[FileInfo]:
    """List files under *path* with an optional depth limit.

    Delegates to ``store.list_files(path, max_depth=N, pattern=pattern)``
    when the Store supports the ``max_depth`` parameter. Otherwise falls
    back to ``store.list_files(path, recursive=True)`` with client-side
    depth filtering.
    """


def list_folders_deep(
    store: Store,
    path: str,
    *,
    depth: int | None = None,
) -> Iterator[FolderEntry]:
    """List folders under *path* with an optional depth limit.

    Delegates to ``store.list_folders(path, depth=N)`` when the Store
    supports the ``depth`` parameter. Otherwise performs a BFS traversal
    using ``store.list_folders()`` at each level.
    """
```

**Why keep the extension if Store already has the parameters?**

The extension serves the same role as `ext.glob.glob_files()`:
- **Backward-compatible entry point** that works with any Store version.
- **Documentation hub** — the module docstring and examples explain depth
  semantics in one place.
- **Composability** — combines depth limiting with pattern filtering in a
  single call, where `Store.list_files` requires both parameters separately.

However, unlike glob where the extension provides genuinely different behavior
(full path matching vs. name-only), the depth extension is thinner. If the
Store-level parameters are sufficient, the extension may not be needed long
term. The recommendation is to **start with the extension (Phase 1) and
promote to Store parameters (Phase 2)** — at that point the extension becomes
a thin wrapper and may be deprecated.

---

## 5. Comparison with Glob Pattern

| Aspect | Glob | Depth-Limited Listing |
|--------|------|----------------------|
| **Tier 1** (Store param) | `list_files(pattern=…)` — name filter | `list_files(max_depth=N)` — depth filter |
| **Tier 2** (native backend) | `Backend.glob()` + `Capability.GLOB` | `Backend.list_files(max_depth=N)` — no new capability needed |
| **Tier 3** (extension) | `ext.glob.glob_files()` | `ext.listing.list_files_deep()` |
| **Fallback mechanism** | `list_files()` + client regex | `list_files(recursive=True)` + client depth filter |
| **Backend optimization** | Prefix extraction | Early traversal termination |
| **New capability?** | Yes (`GLOB`) | No — result is identical, only perf differs |
| **ABC change?** | Yes (new `glob()` method) | Yes (new `max_depth` kwarg on `list_files()`) |
| **Backward compatible?** | Yes (non-abstract default) | Yes (default `max_depth=None` preserves behavior) |

The key difference from glob: depth limiting does **not** need a new
capability. The output is always the same set of files — the backend just
produces them more efficiently. With glob, the native implementation may use
different pattern semantics, so the capability flag signals "this backend
supports full glob natively."

---

## 6. Phased Delivery

### Phase 1: Extension helpers (no ABC change)

**Scope:** New `ext/listing.py` module with `list_files_deep()` and
`list_folders_deep()`. Spec, tests, exports, docs.

**How it works:**
- `list_files_deep()`: calls `store.list_files(path, recursive=True)` and
  filters by path depth client-side.
- `list_folders_deep()`: BFS using `store.list_folders()` at each level.

**Limitations:**
- Always fetches the full recursive listing before filtering (SFTP: all
  round-trips, S3: full `find()`).
- Acceptable for small-to-medium trees. Problematic for 100k+ file trees
  when only depth 1 is needed.

**Effort:** Small. ~50 lines of code, ~100 lines of tests, spec, docs.

### Phase 2: Store parameters + backend optimization

**Scope:** Add `max_depth` to `Store.list_files()` and `depth` to
`Store.list_folders()`. Update `Backend.list_files()` ABC with optional
`max_depth` kwarg. Implement native optimizations in Local, SFTP, Memory.

**How it works:**
- Store delegates `max_depth` to backend when provided.
- Backends that understand `max_depth` stop traversal early.
- Backends that don't are handled by Store-level fallback (same as Phase 1).
- `ext.listing` functions become thin wrappers around the Store parameters.

**Backend implementation priority:**

| Backend | Priority | Reason |
|---------|----------|--------|
| **SFTP** | P0 | Biggest I/O savings (network round-trips) |
| **Local** | P0 | `os.walk()` depth cutoff is trivial and effective |
| **Memory** | P1 | Easy, useful for tests |
| **S3** | P2 | Flat scan is often optimal anyway; level-by-level needs heuristics |
| **Azure** | P2 | Same reasoning as S3 |

**Effort:** Medium. ABC change, 2–3 backend overrides, Store plumbing,
spec updates, test updates.

---

## 7. Alternatives Considered

### A. Extension only — never add to Store/Backend

**Pros:** No ABC change, no risk of breaking backends.
**Cons:** Permanently leaves performance on the table for SFTP and Local.
Users who need depth limiting always pay for a full recursive scan.

**Verdict:** Insufficient long-term. Fine as Phase 1.

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
third-party backends.

**Verdict:** Rejected. Optional keyword with default `None` is
backward-compatible.

### D. Separate `list_files_depth()` method on Backend

Add a new abstract method instead of extending the existing one.

**Pros:** Clean separation, no signature change.
**Cons:** Duplicates listing logic. Every backend would need two nearly
identical methods. Maintenance burden.

**Verdict:** Rejected. An optional kwarg is simpler.

---

## 8. Backlog Items

This research proposes splitting ID-107 and ID-108 into phased delivery:

### Phase 1 items (extension helpers)

- **ID-107a — `ext.listing.list_files_deep()` extension helper**
  Portable depth-limited file listing via `store.list_files(recursive=True)`
  + client-side depth filtering. Spec, tests, exports, docs.

- **ID-108a — `ext.listing.list_folders_deep()` extension helper**
  Portable depth-limited folder listing via BFS over
  `store.list_folders()`. Spec, tests, exports, docs.

### Phase 2 items (native backend optimization)

- **ID-107b — `Store.list_files(max_depth=N)` + backend optimization**
  Add `max_depth` parameter to `Store.list_files()` and
  `Backend.list_files()`. Implement native depth limiting in Local
  (`os.walk()`), SFTP (recursive call depth tracking), and Memory
  (DFS stack depth). S3/Azure: client-side filter (flat scan is often
  optimal). Update `ext.listing.list_files_deep()` to delegate to Store
  parameter.

- **ID-108b — `Store.list_folders(depth=N)` Store-level BFS**
  Add `depth` parameter to `Store.list_folders()`. Implement BFS
  traversal at Store level (no backend ABC change needed for folders).
  Update `ext.listing.list_folders_deep()` to delegate.

---

## 9. Recommendation

**Proceed with Phase 1 (extension helpers) first.** This ships correct
behavior quickly, establishes the API surface and semantics, and provides a
portable solution that works with all backends today. The extension becomes
the reference implementation for the Phase 2 Store-level fallback.

**Follow with Phase 2 (native) when depth-limited listing sees real usage.**
The performance gap is most acute for SFTP (network round-trips) and Local
(filesystem I/O). S3 and Azure can defer native optimization — their flat scan
is often competitive with or better than level-by-level delimiter listing.

The three-tier pattern (Store parameter → backend optimization → extension
fallback) is proven by glob and seekable-read. Depth-limited listing fits
naturally into the same architecture.
