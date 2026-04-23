# Depth-Limited Listing

Adds `max_depth` parameter to `Store.list_files()` and `Store.list_folders()`
for controlling traversal depth without fetching the full recursive tree.

**Related:** [Research](../research/research-depth-limited-listing.md),
ID-107, ID-108, ID-107b.

---

## DEPTH-001: list_files(max_depth=N)

**Invariant:** `list_files(path, *, recursive=False, pattern=None, max_depth=None)`
accepts an optional `max_depth` keyword. Depth is the number of folder levels
between the listing root and the file's parent directory:

- `max_depth=None` (default): defers to `recursive`.
- `max_depth=0`: files directly in `path` only (equivalent to `recursive=False`).
- `max_depth=N` (N > 0): files up to N folder levels below `path`.

When `max_depth` is set, `recursive` is ignored — depth takes full control of
traversal.

**Validation:** `max_depth < 0` raises `ValueError`.

**Filtering order:** depth filtering applies first, then `pattern` filtering.
The two compose naturally.

**Implementation (Phase 1):** Client-side filtering at the Store level.
`max_depth=0` delegates with `recursive=False`; `max_depth > 0` delegates with
`recursive=True` and filters results by path component count. No Backend ABC
change.

**Reference depth algorithm:** Depth for a file at `file_path` relative to
listing root `root` is defined as:

```
depth = len(RemotePath(file_path).parent.parts) - len(RemotePath(root).parts)
```

`max_depth=N` includes files where `depth <= N` (inclusive comparison). Backend
implementations MUST use this definition as the correctness oracle. The
comparison operator MUST be `<=`, not `<`. Implementations that use
slash-counting (`rel.count("/")`) or traversal-level counters are both
acceptable so long as their output is equivalent to the above formula for all
well-formed paths (no trailing slashes, no empty segments).

**Depth examples:**

```
store.list_files("data", max_depth=1)

data/file_a.csv          -> depth 0  included (0 <= 1)
data/raw/file_b.csv      -> depth 1  included (1 <= 1)
data/raw/2026/file_c.csv -> depth 2  excluded (2 > 1)
```

---

## DEPTH-002: list_folders(max_depth=N)

**Invariant:** `list_folders(path, *, max_depth=None)` accepts an optional
`max_depth` keyword controlling how many levels of subfolders to return:

- `max_depth=None` or `max_depth=0`: immediate children only (current behavior).
- `max_depth=N` (N > 0): subfolders up to N levels deep via BFS traversal using
  `Backend.list_folders()` at each level.

**Validation:** `max_depth < 0` raises `ValueError`.

**Implementation (Phase 1):** BFS at the Store level. Each BFS step calls the
existing `Backend.list_folders()` for one level. Cost is O(total folders within
depth), not O(depth). No Backend ABC change.

---

## DEPTH-003: Backend-native `max_depth` optimization

**Invariant:** `Backend.list_files(path, *, recursive=False, max_depth=None)`
accepts an optional `max_depth` keyword. Backends that implement native depth
limiting prune traversal early, reducing I/O. Backends that do not override the
parameter simply ignore it — the Store-level client-side filter (DEPTH-001)
serves as a correctness safety net.

**ABC signature:**

```python
@abc.abstractmethod
def list_files(
    self, path: str, *, recursive: bool = False, max_depth: int | None = None,
) -> Iterator[FileInfo]:
```

**Default behavior:** `max_depth=None` preserves existing `recursive` semantics.
When `max_depth` is set, backends that support it prune traversal natively;
others yield the full recursive result and the Store filters client-side.

**Store delegation:** `Store.list_files()` passes `max_depth` through to the
backend call. The existing client-side depth filter remains as a no-op safety
net when the backend already filtered natively.

**No capability flag:** Unlike glob, depth filtering produces identical results
whether done natively or client-side. The optimization is purely performance.

**Backend strategies:**

| Backend    | Native strategy                                       |
|------------|-------------------------------------------------------|
| **Local**  | `os.walk()` with depth counter; skip dirs beyond limit. |
| **SFTP**   | Depth tracking in recursive calls; stop recursing at limit. |
| **Memory** | DFS stack depth tracking; don't push beyond limit.    |
| **S3**     | Accept parameter, no native optimization (flat scan + client filter). |
| **Azure**  | Accept parameter, no native optimization (flat scan + client filter). |
| **HTTP**   | Accept parameter; raises `CapabilityNotSupported` (listing not supported). |
