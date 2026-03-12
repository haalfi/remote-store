# Research: Store API Refinement

**Date:** 2026-03-12
**Backlog items:** ID-071 (Store API refinement), related: ID-063 (write_text convenience)
**Status:** Research complete — awaiting design decisions

---

## 1. Motivation

The `Store` public API is approaching v1 freeze. Before locking the surface, a
systematic audit is needed to catch inconsistencies, misleading docstrings, and
missing convenience methods that would be breaking to fix after v1.

This research applies two lenses:

- **Internal consistency audit** — do return types, naming, and docstrings
  match the actual type aliases and behavior across all Store methods?
- **Cross-ecosystem comparison** — how do equivalent APIs (pathlib, fsspec,
  PyFilesystem2, Go io/fs, Rust object_store, Java NIO, .NET System.IO) handle
  the same problems? Where does `remote-store` diverge without good reason?

## 2. Scope

Six concerns identified by the audit, ordered by impact:

1. **Normalize child/listing return shapes** — `iter_children()` returns `FileInfo | str`; `list_folders()` returns bare names while `list_files()` returns `FileInfo` with full paths
2. **Fix misleading `write()` / `write_atomic()` docstrings** — docstrings claim `str` is accepted but `WritableContent = BinaryIO | bytes`; consider adding `write_text()` for symmetry with `read_text()`
3. **Fix the `read_text(errors=...)` reference** — cites `codecs.register` instead of the correct pointer
4. **Add explicit ordering/performance guarantees for listing methods** — `iter_children()` documents backend-defined ordering but `list_files()`, `list_folders()`, `glob()` do not
5. **Clarify atomicity/metadata guarantees for `move()` and `copy()`** — backend-dependent behavior is undocumented
6. **Visually separate advanced escape hatches** — `unwrap()`, `native_path()`, and native `glob()` are backend-specific but not marked as such in docstrings

Plus cross-cutting concerns surfaced during the audit:

- **README API table descriptions** lag behind actual contracts (bare names, mixed types, file-only constraints)
- **Backend behavior matrix** is missing — users of `supports()` cannot tell what a capability means per backend
- **Thread-safety statement** is absent from the `Store` class docstring

---

## 3. Normalize Child/Listing Return Shapes

### Problem

| Method | Returns | Path shape |
|--------|---------|------------|
| `list_files()` | `Iterator[FileInfo]` | store-relative full path |
| `list_folders()` | `Iterator[str]` | bare name (not full path) |
| `iter_children()` | `Iterator[FileInfo \| str]` | mixed: FileInfo for files, str name for folders |

From a user's perspective: "I called `list_folders('data')` and got `['reports', 'archive']` — bare names I have to manually join back to paths. But `list_files('data')` gave me `FileInfo` objects with full paths. Why the asymmetry?" And `iter_children()` is worse — it yields `FileInfo` for files but plain `str` for folders, forcing an `isinstance` branch just to iterate a directory.

### Validation method

**Cross-ecosystem comparison** of how storage/filesystem APIs handle directory listing return types:

| Library | List files | List folders | Combined | Return uniformity |
|---------|-----------|-------------|----------|-------------------|
| Python `pathlib` | `iterdir()` | `iterdir()` | Same method | Uniform `Path` objects, filter with `is_file()`/`is_dir()` |
| Python `os` | `scandir()` | `scandir()` | Same method | Uniform `DirEntry` with `.is_file()`, `.is_dir()`, `.name`, `.path` |
| PyFilesystem2 | `listdir()` / `scandir()` | `listdir()` / `scandir()` | Same method | `listdir` → uniform `str` names; `scandir` → uniform `Info` objects with `is_dir` flag |
| fsspec | `ls(detail=True)` | `ls(detail=True)` | Same method | Uniform dicts with `"type": "file"|"directory"` |
| Go `io/fs` | `ReadDir()` | `ReadDir()` | Same method | Uniform `DirEntry` with `IsDir()`, `Name()`, `Info()` |
| Go `afero` | `ReadDir()` | `ReadDir()` | Same method | Uniform `os.FileInfo` |
| Rust `std::fs` | `read_dir()` | `read_dir()` | Same method | Uniform `DirEntry` with `file_type()` |
| Rust `object_store` | `list()` | `list_with_delimiter()` | Separate | `list()` → `ObjectMeta`; delimiter → `ListResult { objects, common_prefixes }` |
| Java `java.nio.file` | `Files.list()` / `newDirectoryStream()` | Same | Same method | Uniform `Path` objects |
| .NET `System.IO` | `GetFiles()` / `GetDirectories()` | Separate | `GetFileSystemEntries()` | Separate returns strings; `DirectoryInfo.EnumerateFileSystemInfos()` returns uniform `FileSystemInfo` |
| Node.js `fs` | `readdir({withFileTypes})` | Same | Same method | `withFileTypes: true` → uniform `Dirent` with `isFile()`, `isDirectory()` |

**Overwhelming industry consensus**: when a method returns both files and folders, they use a **uniform type** with a `kind`/`type`/`is_dir` discriminator — never a union of unrelated types.

### Recommendation

**Option A: Introduce `ChildEntry` dataclass**

```python
@dataclasses.dataclass(frozen=True)
class ChildEntry:
    name: str           # bare name (last path component)
    path: RemotePath     # store-relative full path
    kind: Literal["file", "folder"]
    info: FileInfo | None = None  # populated for files, None for folders
```

- `iter_children()` → `Iterator[ChildEntry]`  (uniform type, no isinstance branching)
- `list_folders()` → `Iterator[str]` remains for the simple "give me folder names" case, BUT also add `list_folders_info()` → `Iterator[ChildEntry]` for callers who need full paths

**Option B (minimal): Make `list_folders()` return store-relative paths**

- `list_folders()` → `Iterator[str]` but full store-relative paths instead of bare names
- `iter_children()` stays `FileInfo | str` but the `str` is now a full path

This is simpler but doesn't fix the isinstance branching issue.

**Option C (alternative): FolderEntry dataclass**

```python
@dataclasses.dataclass(frozen=True)
class FolderEntry:
    name: str
    path: RemotePath
```

- `list_folders()` → `Iterator[FolderEntry]`
- `iter_children()` → `Iterator[FileInfo | FolderEntry]` (still a union, but both are named types with `.name` and `.path`)

**Option D (preferred): Protocol + FolderEntry**

```python
@typing.runtime_checkable
class PathEntry(Protocol):
    """Structural type shared by all listing results."""
    @property
    def name(self) -> str: ...
    @property
    def path(self) -> RemotePath: ...

@dataclasses.dataclass(frozen=True)
class FolderEntry:
    name: str
    path: RemotePath
```

`FileInfo` already has `name: str` and `path: RemotePath`, so it satisfies
`PathEntry` structurally — no inheritance change needed. `FolderEntry` likewise
satisfies it by construction.

- `list_folders()` → `Iterator[FolderEntry]`
- `iter_children()` → `Iterator[PathEntry]` (uniform type in the signature)
- `list_files()` → `Iterator[FileInfo]` (unchanged — callers still get full metadata)

Callers of `iter_children()` get `.name` and `.path` on every entry without
isinstance. Callers who need file-specific metadata (size, modified_at) narrow
with `isinstance(entry, FileInfo)` — which is the correct semantic: "I want
richer info that only files have."

**Migration impact:** This is a **behavioral** change requiring migration for
existing callers, not just a type-level one. Currently `iter_children()` yields
bare `str` names for folders. Under Option D, folders become `FolderEntry`
objects. Existing code like:

```python
for child in store.iter_children("data"):
    if isinstance(child, str):
        subfolder_path = f"data/{child}"  # child IS the name string
```

will fail at runtime — `isinstance(child, str)` returns `False` for
`FolderEntry`, so the folder branch never triggers. **All callers must change
`child` → `child.name` (or `child.path`) for the folder branch.** Similarly,
`list_folders()` callers that treat results as plain strings must update to
access `.name` or `.path` on `FolderEntry` objects. Migration guidance must
be included in the CHANGELOG and upgrade guide when this change ships.

**Approachability trade-off:** `Protocol` + structural typing is less familiar to
citizen developers than concrete classes. Users may see `PathEntry` in IDE
completions and not know what a Protocol is. However, they don't *need* to know —
they just use `.name` and `.path`. By contrast, Option C's union
(`FileInfo | FolderEntry`) is arguably more discoverable: both types are concrete
classes you can click through to in your IDE. The protocol's advantages
(extensibility, no isinstance) are library-designer concerns. This trade-off
should be weighed during the design decision.

This is strictly better than Option C's `FileInfo | FolderEntry` union because:

1. **The common-case code path uses no isinstance at all.** Iterating names or
   paths works directly on `PathEntry`. Option C's union technically has the
   same attributes, but the type checker still sees a union and may require
   narrowing depending on the operation.
2. **The protocol is the documented contract.** Type checkers enforce that both
   `FileInfo` and `FolderEntry` satisfy `PathEntry`. If a future entry type is
   added (e.g., `SymlinkEntry`), it just needs to satisfy the same protocol —
   no union expansion needed.
3. **No wrapper, no inheritance.** `FileInfo` stays unchanged. `FolderEntry` is
   a simple dataclass. The protocol is purely structural — existing code that
   constructs `FileInfo` or `FolderEntry` doesn't change.

### Analysis

| Criterion | Option A | Option B | Option C | **Option D** |
|-----------|----------|----------|----------|------------|
| isinstance-free iteration | Yes | No | Partially (union still typed) | **Yes** |
| `list_folders()` returns full paths | Yes | Yes | Yes | **Yes** |
| `FileInfo` unchanged | No (wrapped) | Yes | Yes | **Yes** |
| Type-checker enforced contract | N/A | N/A | Duck-typed coincidence | **Protocol-enforced** |
| Extensible to new entry kinds | Requires updating `ChildEntry.kind` | N/A | Requires union expansion | **Just satisfy protocol** |
| Migration scope | `iter_children` return type | `list_folders` return values | `list_folders` + `iter_children` types | `list_folders` + `iter_children` types |

**Recommendation: Option D.** It gives the cleanest caller ergonomics, enforces
the shared contract at the type level, and is the most extensible. The protocol
is tiny (two properties), so it adds minimal API surface. `FileInfo` is
untouched — it already structurally satisfies `PathEntry`.

### Decision needed

Which option to pursue? This is the most impactful change and affects Backend ABC, all backend implementations, specs, tests, docs.

---

## 4. Fix Misleading write/write_atomic Docstrings

### Problem

The `write()` docstring says:

> `:param content: Data to write (``bytes``, ``str``, or readable binary stream).`

But `WritableContent = BinaryIO | bytes` — **`str` is not actually accepted**. The docstring is wrong.

Furthermore, even if we wanted to accept `str`, the encoding contract is unspecified. `read_text()` has explicit `encoding` and `errors` params, but the write side has no equivalent.

### Validation method

| Library | Write accepts str? | If yes, how encoded? |
|---------|-------------------|---------------------|
| Python `pathlib` | Separate methods: `write_text(data, encoding=)` vs `write_bytes(data)` | Explicit encoding param |
| PyFilesystem2 | Separate: `writetext(text, encoding=)` vs `writebytes(data)` | Explicit encoding param |
| fsspec | `pipe(path, value)` — bytes only | N/A |
| Go | `WriteFile(name, data)` — `[]byte` only | N/A |
| Rust `std::fs` | `write(path, contents: AsRef<[u8]>)` — accepts both | Implicit (Rust strings are UTF-8) |
| Rust `object_store` | `put(location, payload)` — bytes only | N/A |
| Java NIO | Separate: `Files.writeString(path, text)` (Java 11+) vs `Files.write(path, bytes)` | Explicit charset param |
| .NET | Separate: `File.WriteAllText(path, text)` vs `File.WriteAllBytes(path, bytes)` | Explicit encoding param |
| Node.js | `writeFile(path, data)` — accepts both | Encoding option toggles string vs Buffer |
| boto3 S3 | `put_object(Body=...)` — bytes/stream | N/A |

**Industry consensus**: 8 of 10 libraries either provide a separate `write_text()` method with explicit encoding or only accept bytes. Silently encoding strings with an assumed default is a portability trap. The explicit-pair pattern (`write_text`/`write_bytes` or `writetext`/`writebytes`) is the dominant approach in Python, Java, and .NET.

### Recommendation

1. **Fix the docstring immediately** — remove "``str``" from `write()` and `write_atomic()` parameter descriptions. This is a documentation bug, not a feature gap.
2. **Consider adding `write_text()`** as a convenience (symmetric with `read_text()`):
   ```python
   def write_text(self, path: str, text: str, *, encoding: str = "utf-8",
                  overwrite: bool = False) -> None:
       self.write(path, text.encode(encoding), overwrite=overwrite)
   ```
   This would complete the read_text/write_text symmetry that users expect from pathlib.

### Decision needed

- Fix-docstring is mandatory.
- `write_text()` addition is optional but recommended for symmetry. Decide whether to add it now (pre-v1) or defer.

---

## 5. Fix the `read_text(errors=...)` Reference

### Problem

The docstring says:

> `See :func:`codecs.register` for valid values.`

`codecs.register` is for registering custom codecs. The correct reference for error handler names is `codecs.register_error` or more practically, the built-in error handler names documented in the Python `codecs` module ("strict", "ignore", "replace", "backslashreplace", "xmlcharrefreplace").

### Recommendation

Change to:

```
See the :mod:`codecs` module for available error handlers
(e.g., ``"strict"``, ``"ignore"``, ``"replace"``).
```

Or more precisely:

```
Standard error handlers: ``"strict"`` (default, raises ``UnicodeDecodeError``),
``"ignore"``, ``"replace"``, ``"backslashreplace"``.
See :func:`codecs.register_error` for custom handlers.
```

### Impact

Docstring-only change. No code change needed.

---

## 6. Add Explicit Ordering/Performance Guarantees for Listing Methods

### Problem

`iter_children()` documents that ordering is backend-defined. `list_files()`, `list_folders()`, and `glob()` do not. Callers need to know:

- **Ordering**: Is it deterministic? Alphabetical? Backend-defined?
- **Laziness**: Are results streamed or buffered? What are the memory implications for large directories?
- **Pagination**: Are there backend-specific round-trip implications?

### Validation method

| Library | Ordering guarantee | Laziness |
|---------|-------------------|----------|
| Python `pathlib.iterdir()` | "in arbitrary order" (documented) | Iterator (lazy) |
| Python `os.scandir()` | "in arbitrary order" (documented) | Iterator (lazy) |
| fsspec `ls()` | Not specified | Returns list (eager) |
| PyFilesystem2 `scandir()` | Not specified | Iterator |
| Go `io/fs.ReadDir()` | "sorted by filename" (documented) | Eager (returns slice) |
| Rust `std::fs::read_dir()` | "in no particular order" (documented) | Iterator (lazy) |
| Rust `object_store::list()` | Not specified | AsyncStream (lazy) |
| Java NIO `Files.list()` | Not specified | Stream (lazy) |
| .NET `EnumerateFiles()` | Not specified | IEnumerable (lazy) |
| Node.js `readdir()` | Not specified | Returns array (eager) |
| boto3 `list_objects_v2` | Lexicographic by key (S3 guarantees this) | Paginated |

**Observation**: most APIs explicitly document ordering as either "arbitrary" or "sorted". Laziness is typically clear from the return type (iterator vs list).

### Recommendation

Add to docstrings of `list_files()`, `list_folders()`, `glob()`:

```
Ordering is backend-defined and may vary; callers must not depend on it.
Results are yielded lazily; backends may use pagination internally.
```

This is a docstring-only change. If we want to guarantee sorted output, that's a code change (sorting at the Store layer), but it would defeat the laziness benefit for large directories.

### Decision needed

Document "no ordering guarantee" (recommended) vs add Store-level sorting?

---

## 7. Clarify Atomicity/Metadata Guarantees for move and copy

### Problem

The docs are good but leave three questions unanswered:

1. **Is `move()` atomic on all backends?** (Local: yes via `os.replace`; S3: no, it's copy+delete; SFTP: depends on server)
2. **Does `copy()` preserve metadata?** (modification time, content type, custom metadata)
3. **Are `move()` and `copy()` file-only?** (The current code uses `_require_file_path`, so yes, but it's not documented)

### Validation method

Cross-ecosystem patterns for move/copy:

| Library | Move name | Copy name | Atomicity documented? | Metadata documented? | File-only? |
|---------|-----------|-----------|----------------------|---------------------|------------|
| pathlib | `rename()` / `replace()` | N/A (`shutil.copy2`) | `replace` is atomic on same FS | `shutil.copy2` preserves metadata | File-only (rename) |
| PyFilesystem2 | `move()` + `movedir()` | `copy()` + `copydir()` | Not documented | Not documented | Separate file/dir methods |
| fsspec | `mv()` (alias: `move`, `rename`) | `cp()` (alias: `copy`) | Not documented | Not documented | Not specified |
| Go afero | `Rename()` | N/A (manual) | Follows `os.Rename` | N/A | Not specified |
| Rust `std::fs` | `rename()` | `copy()` | "atomic on same FS" | "copies permission bits" | File-only for copy |
| Rust `object_store` | `rename()` + `rename_if_not_exists()` | `copy()` + `copy_if_not_exists()` | Default: copy+delete (not atomic) | Not documented | Files only (no folders in object stores) |
| Java NIO | `Files.move()` | `Files.copy()` | `ATOMIC_MOVE` option | `COPY_ATTRIBUTES` option | Both support dirs |
| .NET | `File.Move()` | `File.Copy()` | Not documented | Not documented | File-only (separate `Directory.Move`) |
| boto3 S3 | `copy_object` + `delete_object` | `copy_object` | No native move; copy+delete | S3 copies metadata by default | Files only |

**Key insight**: Java NIO is the gold standard here — explicit `ATOMIC_MOVE` and `COPY_ATTRIBUTES` option flags. Most other APIs leave atomicity and metadata undocumented or backend-implicit. Documenting these guarantees (even as "backend-dependent") puts us ahead of most.

### Recommendation

Add to `move()` docstring:
```
Atomicity is backend-dependent. Local backends use ``os.replace`` (atomic
on the same filesystem). Object-store backends (S3, Azure) typically
implement move as copy-then-delete, which is not atomic.

This method operates on files only. To move a folder, iterate its contents.
```

Add to `copy()` docstring:
```
Metadata preservation is backend-dependent. Some backends (local, SFTP)
may not preserve all metadata (modification time, content type).

This method operates on files only. To copy a folder, iterate its contents.
```

### Impact

Docstring-only changes. Factual accuracy needs verification by checking each backend implementation.

---

## 8. Visual Separation of Escape Hatches

### Problem

`unwrap()`, `native_path()`, and `glob()` (native backend glob) are backend-specific escape hatches mixed in with the portable API. Their docstrings don't warn callers that using them ties code to a specific backend.

### Recommendation

This is a **docs presentation** concern, not a code concern. In the mkdocstrings-generated page, we could:

1. Add a "Backend-Specific Interop" section header comment in the source
2. Add admonition boxes to the docstrings: `.. warning:: This method exposes backend-specific behavior...`

For the docstrings, add a note like:

```
.. note::
    **Advanced — backend-specific.** Using this method ties your code
    to a specific backend. For portable alternatives, see ...
```

### Impact

Docstring-only changes. Possibly also docs template changes.

---

## 9. Cross-Cutting Concerns

Beyond individual method docstrings, the audit surfaced three API documentation gaps that span the whole Store surface.

### 9a. `write_text()` gap is user-visible in quickstart — Phase 1 priority

The first code example a new user encounters uses `b"Hello, world!"`. This is lower-level than pathlib-trained Python developers expect. A `write_text()`/`read_text()` hello-world would be more natural. This is the **#1 priority for the target audience**: forcing citizen developers into bytes-land before they've even stored a file contradicts the "just works" promise.

The design decision is already made by every comparable library: pathlib (`write_text`), PyFilesystem2 (`writetext`), Java NIO (`Files.writeString`), .NET (`File.WriteAllText`) — all cited in §4. There's no ambiguity. `write_text()` should ship in Phase 1 alongside the docstring fixes, not wait for a separate design decision phase.

### 9b. README API table descriptions lag behind actual contracts

The README's API summary table has descriptions that are accurate but miss key contracts:

| Current description | What's missing |
|---|---|
| `list_folders(path)` → "Iterate subfolder names" | Doesn't say these are bare names (not paths) — the exact asymmetry from §3 |
| `iter_children(path)` → "Iterate files and folders in one pass" | Doesn't hint at the mixed return type |
| `move(src, dst)` → "Move or rename" | Doesn't say file-only |
| `copy(src, dst)` → "Copy a file" | Good — already says "file" |
| `glob(pattern)` → "Native glob (capability-gated)" | Doesn't say backend-specific |
| `write(path, content)` → "Write bytes or binary stream" | Good — correctly omits `str` here, but docstring still claims it |

These descriptions should be updated **after** the docstring fixes in Phase 1, so they stay consistent with the source of truth.

### 9c. Backend behavior matrix — essential for the core promise (Phase 1)

Users of `supports(capability)` can check **whether** a backend has a capability, but cannot tell **what** that capability means concretely on each backend. "Write once, run anywhere" implicitly promises predictable cross-backend behavior. When `move()` is atomic on Local but copy+delete on S3, users need to know *before* they deploy. This matrix is the honest version of the portability promise and should ship as documentation in Phase 1, not wait for Phase 3 implementation. A per-backend behavior matrix belongs in the API docs:

| Behavior | Local | S3 | S3-PyArrow | SFTP | Azure | Memory |
|---|---|---|---|---|---|---|
| `move()` atomicity | Atomic (same FS) | Copy+delete | Copy+delete | Server-dependent | Copy+delete | Atomic |
| `copy()` preserves metadata | No (new mtime) | Yes (S3 copies metadata) | Yes | No | Yes | No |
| `write_atomic()` | Yes (temp+rename) | Yes (temp+rename) | Yes | Yes (temp+rename) | Yes (temp+rename) | Yes |
| Native `glob()` | Yes | Yes | Yes | No | Yes | No |
| `list_files()` ordering | OS-dependent | Lexicographic (S3) | Lexicographic | OS-dependent | Lexicographic | Insertion order |

This needs verification against actual backend implementations before publishing.

### 9d. Thread-safety statement missing from Store class docstring

The spec says Store is thread-safe (immutable after construction), but the class docstring doesn't mention it. Add:

```
Thread-safe: ``Store`` is immutable and can be shared across threads.
Backend thread safety depends on the underlying library.
```

---

## 10. Execution Plan

### Phase 1: Docstring fixes, `write_text()`, and documentation gaps

1. Fix `write()` / `write_atomic()` docstrings — remove `` ``str`` `` from content param description (§4)
2. Fix `read_text(errors=...)` reference — `codecs.register` → correct pointer (§5)
3. Add ordering/laziness guarantees to `list_files()`, `list_folders()`, `glob()` docstrings (§6)
4. Add atomicity/metadata/file-only notes to `move()` and `copy()` docstrings (§7)
5. Add "advanced — backend-specific" notes to `unwrap()`, `native_path()`, `glob()` docstrings (§8)
6. Add thread-safety statement to `Store` class docstring (§9d)
7. Implement `write_text()` — design is settled by ecosystem precedent (§4, §9a)
8. Build and verify backend behavior matrix as documentation (§9c) — audit each backend
9. Update README API table descriptions to match improved docstrings (§9b)

### Phase 2: API design decision (requires choice before implementation)

10. Listing normalization approach — Option D preferred (§3), but see approachability trade-off

### Phase 3: Implementation

11. Implement chosen listing normalization (§3)
12. Update specs, tests, docs, examples, BACKLOG, CHANGELOG per ripple-check table

---

## 11. Method Name Validation Summary

Based on cross-ecosystem analysis, current names are well-chosen. Notes:

| Current name | Ecosystem alignment | Verdict |
|-------------|-------------------|---------|
| `read()` | Universal | Keep |
| `read_bytes()` | pathlib `read_bytes()` | Keep |
| `read_text()` | pathlib `read_text()`, PyFS `readtext()` | Keep |
| `write()` | Universal | Keep |
| `write_atomic()` | Unique (most libs don't have this) | Keep — clear intent |
| `open_atomic()` | Unique | Keep — clear intent |
| `delete()` | Common (vs `remove` in pathlib/os) | Keep — `delete` is more common in storage APIs |
| `delete_folder()` | `rmdir`/`rmtree` in stdlib, but `delete_folder` is clearer | Keep |
| `list_files()` | Common pattern | Keep |
| `list_folders()` | Return type needs work (see §1) | Keep name, fix return type |
| `iter_children()` | `iterdir()` in pathlib, `scandir()` in os | Name is fine, return type needs work |
| `glob()` | Universal | Keep |
| `move()` | Split: `rename` (pathlib, Go, Rust, object_store), `move` (PyFS, Java NIO, .NET), `mv` (fsspec) | Keep — `move` is the higher-level abstraction name; `rename` implies same-filesystem |
| `copy()` | Universal | Keep |
| `exists()` | Universal | Keep |
| `is_file()` | `pathlib.is_file()`, Go `IsRegular()` | Keep |
| `is_folder()` | `pathlib.is_dir()`, but "folder" aligns with cloud storage | Keep — consistent with rest of API |
| `get_file_info()` | `stat()` (pathlib/os), `info()` (PyFS), `head_object` (S3) | Keep — more descriptive than `stat` |
| `get_folder_info()` | Unique (most APIs don't aggregate folder stats) | Keep |
| `child()` | `opendir()` (PyFS), `chdir()` (fsspec) | Keep — clearer semantics |
| `ping()` | Common in database clients | Keep |
| `supports()` | Capability pattern common in Java/enterprise | Keep |
| `unwrap()` | `getDelegate()` (Java), `inner()` (Rust), type-assertion (Go) | Keep — Rust-inspired, clear |
| `native_path()` | `getsyspath()` (PyFS), `__fspath__()` (pathlib), `BlobClient.Uri` (.NET) | Keep — clearer than alternatives |
| `to_key()` | Unique (inverse of `native_path`) | Keep |

**No method renames recommended.** The names are well-aligned with industry conventions and internally consistent.

---

## 12. Appendix: Verified Cross-Ecosystem Sources

Analysis based on verified API documentation from:
- Python: pathlib, os, fsspec, PyFilesystem2, boto3 S3
- Go: io/fs, afero
- Rust: std::fs, object_store crate
- Java: java.nio.file (Files), Apache Commons VFS
- .NET: System.IO (File, Directory), Azure.Storage.Blobs
- Node.js: fs, AWS SDK JS v3
