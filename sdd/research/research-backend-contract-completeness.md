# Research: Backend Contract Completeness

**Date:** 2026-04-05
**Status:** Complete
**Scope:** Gap analysis of the backend ABC as a behavioral contract.
Identifies six categories of underspecified behavior where concrete backends
diverge, maps each to historical bugs and spec gaps, and proposes spec
amendments as a prerequisite for BK-139's conformance work.
**Related:** BK-139,
[research-bug-prevention-beyond-testing.md](research-bug-prevention-beyond-testing.md),
[003-backend-adapter-contract.md](../specs/003-backend-adapter-contract.md),
[006-streaming-io.md](../specs/006-streaming-io.md),
[007-atomic-writes.md](../specs/007-atomic-writes.md),
[037-depth-limited-listing.md](../specs/037-depth-limited-listing.md).

**Context:** The bug-prevention research (BK-139) recommends property-based
testing and extended conformance tests to catch cross-backend behavioral
inconsistencies. But conformance tests can only verify behavior that is
*specified*. This document asks the upstream question: is the backend ABC
well-defined enough to serve as a complete behavioral contract, or are there
gaps that must be closed in the specs before testing can be effective?

**Finding:** The ABC defines the *structural* contract (signatures, types,
capabilities) well but leaves significant *behavioral* surface area
unspecified. The 22 bugs fixed in 0.21.1 cluster in exactly these gaps.
Six categories of underspecified behavior are identified below.

---

## 1. Methodology

For each abstract method in `_backend.py`, we compared:

1. **Spec language** — the behavioral guarantees in `sdd/specs/003-*`,
   `006-*`, `007-*`, `036-*`, `037-*`
2. **ABC docstrings** — any additional constraints stated in code
3. **Concrete implementations** — Local, Memory, S3, SFTP, Azure, SQL
4. **Store assumptions** — what `_store.py` relies on that the ABC doesn't
   guarantee

A divergence is a case where two backends produce observably different results
for the same input, and the spec does not designate either behavior as correct.

---

## 2. Gap Categories

### Gap 1: Precondition Evaluation Order

**What the spec says:** BE-008 states `write(overwrite=False)` raises
`AlreadyExists` if the file exists. The spec does not address what happens
when the path names an existing *directory*, or which error takes precedence
when multiple preconditions fail simultaneously.

**What backends do:**

| Backend | Path-is-directory | Check timing |
|---------|-------------------|--------------|
| Local (`_local.py:149`) | `InvalidPath` (checked first) | Check-then-act |
| Memory (`_memory.py:124`) | `InvalidPath` (checked first, under lock) | Atomic |
| S3 (`_s3.py:142`) | `AlreadyExists` (no dir/file distinction) | Check-then-act |
| SFTP (`_sftp.py:326`) | No explicit check | Check-then-act |
| Azure (`_azure.py:345`) | No explicit check (virtual dirs) | Check-then-act |
| SQL (`_sqlalchemy.py:384`) | No dir concept | Atomic (transaction) |

**Divergence:** Calling `write("existing_dir", data, overwrite=False)` raises
`InvalidPath` on Local/Memory but `AlreadyExists` on S3. The caller cannot
write portable error handling without knowing which backend is underneath.

**Bugs caused:** BUG-154 (Local `write()` leaking `IsADirectoryError`).
BUG-153 (Local `read()`/`delete()` leaking `IsADirectoryError`) is related
but belongs to Gap 2 — the read/delete path is an error-discrimination issue,
not a write-precondition issue.

**What's missing from the spec:**
- BE-008 needs: "If `path` names an existing directory, raises `InvalidPath`.
  This check MUST precede the overwrite check."
- General rule: precondition checks MUST be evaluated in a defined order:
  path validity → type conflict → overwrite conflict → I/O.

---

### Gap 2: Error Discrimination Granularity

**What the spec says:** BE-021 requires all backend-native exceptions to be
mapped to `RemoteStoreError` subtypes. The spec does not define *which*
native conditions map to *which* subtype beyond the per-method `Raises:`
clauses.

**What backends do:**

| Scenario | Local | SFTP | S3 | Azure |
|----------|-------|------|----|-------|
| Read a directory | `InvalidPath` | `NotFound` (errno) | `NotFound` (s3fs) | `NotFound` (blob API) |
| Delete with permission error | `PermissionDenied` | Swallowed as `NotFound` (BUG-145) | `PermissionDenied` | `PermissionDenied` |
| List with permission error | `PermissionDenied` | Swallowed silently (BUG-146) | `PermissionDenied` | Depends on HNS |
| `_ensure_parent_dirs` permission | `PermissionDenied` | Swallowed silently (BUG-147) | N/A (no dirs) | N/A (no dirs) |

**Divergence:** The same failure mode produces different error types across
backends. SFTP's broad `except OSError` handlers without `errno`
discrimination turned permission errors into silent returns.

**Bugs caused:** BUG-145, BUG-146, BUG-147 (SFTP error swallowing);
BUG-153 (Local `read()`/`delete()` leaking `IsADirectoryError` instead of
mapping to `NotFound`).

**What's missing from the spec:**
- BE-021 needs a **canonical error mapping table** per scenario:

  | Scenario | Required error type |
  |----------|-------------------|
  | Read/write a path that is a directory | `InvalidPath` |
  | Operation on non-existent file | `NotFound` |
  | Operation denied by credentials | `PermissionDenied` |
  | Parent creation fails (permissions) | `PermissionDenied` |
  | Parent creation fails (path conflict) | `InvalidPath` |

- Rule: Broad exception handlers (`except OSError`, `except Exception`) in
  backends MUST discriminate by error code or type before mapping. Silent
  returns are only permitted for `exists()`, `is_file()`, `is_folder()`.

---

### Gap 3: Listing Behavior on Non-Existent Paths

**What the spec says:** BE-014 defines `list_files()` postconditions (returns
only files, supports recursive) but does NOT specify behavior when `path`
doesn't exist. BE-026 (`iter_children`) explicitly says "non-existent paths
yield nothing" — but this guarantee is not stated for `list_files()` or
`list_folders()`.

**What backends do:**

| Backend | list_files(missing_path) | list_folders(missing_path) |
|---------|-------------------------|---------------------------|
| Local (`_local.py:272`) | Empty iterator (silent) | Empty iterator (silent) |
| Memory (`_memory.py:211`) | Empty iterator (silent) | Empty iterator (silent) |
| S3 (`_s3_base.py:~150`) | Empty iterator (S3 returns empty for missing prefixes) | Empty iterator |
| SFTP (`_sftp.py:~460`) | Empty iterator (catches ENOENT) | Empty iterator |
| Azure (`_azure.py:~510`) | Empty iterator: HNS catches `NotFound` and returns; non-HNS prefix query returns empty naturally | Empty iterator |
| SQL (`_sqlalchemy.py:~455`) | Empty iterator (prefix query returns no rows) | Empty iterator |

**Current state:** All backends agree on the missing-path case (empty
iterator), but this is *accidental consensus* — the spec does not require it.
A new backend implementer could reasonably raise `NotFound`. Note: Azure HNS
does propagate non-`NotFound` errors differently from non-HNS (see Gap 2),
but for the missing-path case specifically, both code paths converge on empty.

**Store safety net:** The Store does NOT catch `NotFound` from listing
operations — it trusts the backend to return empty. If a backend raised
`NotFound`, callers would see an unhandled exception.

**What's missing from the spec:**
- BE-014 needs: "If `path` does not exist or is not a folder, the iterator
  yields nothing. `list_files()` MUST NOT raise `NotFound` for missing
  paths."
- Same clause needed for BE-015 (`list_folders`).

---

### Gap 4: `max_depth` Counting Semantics

**What the spec says:** DEPTH-001 defines depth as "the number of folder
levels between the listing root and the file's parent directory" with an
example:

```
store.list_files("data", max_depth=1)

data/file_a.csv          → depth 0  ✓ included
data/raw/file_b.csv      → depth 1  ✓ included
data/raw/2026/file_c.csv → depth 2  ✗ excluded
```

The spec provides this *example* but does not specify a *reference algorithm*.

**What backends do:**

| Backend | Depth algorithm | Code location |
|---------|----------------|---------------|
| Local | `len(Path(dirpath).relative_to(full).parts)` — path-part count | `_local.py:282` |
| Memory | Iterative DFS with depth counter on stack entries | `_memory.py:540` |
| SFTP | Recursive `_depth` parameter incremented per level | `_sftp.py:490` |
| S3 | Breadth-first queue with depth counter | `_s3_base.py:~155` |
| Azure | `rel.count("/")` — slash-counting | `_azure.py:524` |
| SQL | `suffix.count("/")` — slash-counting | `_sqlalchemy.py:476` |

**Divergence:** Azure and SQL count `/` characters in the relative path
suffix. Local/Memory/SFTP count directory traversal levels. These produce
identical results for *well-formed* paths but could diverge for edge cases
(trailing slashes, empty segments from double-slashes, etc.).

**Comparison operator divergence:**

| Backend | Condition | What it controls |
|---------|-----------|-----------------|
| Local | `depth > max_depth` → skip dir contents | Files at max_depth included; dirs at max_depth not entered |
| Memory | `depth >= max_depth` → don't recurse into subdir | Files at max_depth included (yielded before recursion check) |
| Azure | `depth > max_depth` → skip file | Post-hoc filter on yielded files |
| SQL | `depth > max_depth` → skip file | Post-hoc filter on yielded files |
| SFTP | `depth >= max_depth` → don't recurse into subdir | Files at max_depth included (yielded before recursion check) |

Memory and SFTP use `>=` but apply the check to *subdirectory recursion*, not
to file yielding — files at exactly `max_depth` are still yielded. Local/Azure/SQL
use `>` but apply the check differently (traversal pruning vs post-hoc filter).
All backends produce the same observable results for well-formed paths. The
divergence is in implementation strategy, not in output — but the lack of a
reference algorithm means a new backend could misinterpret the semantics.

**Store safety net:** DEPTH-003 says the Store applies client-side depth
filtering as a correctness guarantee even if backends get it wrong
(`_store.py:393-396`). This masks backend bugs rather than preventing them.

**Bugs caused:** BUG-152 (S3 ignoring max_depth), BUG-155 (Azure ignoring
max_depth). Note: both bugs were missing-implementation (the parameter was
accepted but filtering logic was absent), not algorithm-disagreement bugs.
A reference algorithm in the spec would have made these gaps obvious during
implementation and review.

**What's missing from the spec:**
- DEPTH-001 needs a **reference algorithm**, not just an example:
  "Depth is computed as the number of path segments between the listing root
  and the file's parent, i.e., `len(RemotePath(file.path).parent.parts) -
  len(RemotePath(root).parts)`. `max_depth=N` includes files where
  `depth <= N`."
- Explicitly state the comparison: inclusive (`depth <= max_depth`), not
  exclusive.

---

### Gap 5: Move/Copy Atomicity and Failure Modes

**What the spec says:** BE-018 defines `move(src, dst)` as "renames/moves a
file" with error conditions for missing source and existing destination. The
spec says nothing about atomicity, partial failure, or whether the operation
can leave data in both locations.

AW-006 defines atomicity for `write_atomic` on Local (POSIX `os.replace`),
but no spec covers move/copy atomicity per backend.

**What backends do:**

| Backend | move() implementation | Atomic? | Failure mode |
|---------|----------------------|---------|--------------|
| Local (`_local.py:360`) | `shutil.move()` → `os.rename` | Yes (same FS) | Fails cleanly |
| Memory (`_memory.py:369-370`) | Dict detach+attach under lock | Yes | Fails cleanly |
| S3 (`_s3.py:213-214`) | `copy()` then `rm()` | **No** | Copy succeeds + rm fails = **duplicate** |
| SFTP (`_sftp.py:603-614`) | `posix_rename()` → `rename()` → copy+delete | Best-effort cascade | May leave duplicate on fallback path |
| Azure HNS (`_azure.py:674-677`) | `rename_file()` | Yes | Fails cleanly |
| Azure non-HNS (`_azure.py:679-681`) | `start_copy_from_url()` + `delete_blob()` | **No** | Copy succeeds + delete fails = **duplicate** |
| SQL (`_sqlalchemy.py:617`) | `UPDATE ... SET key=dst WHERE key=src` | Yes (transaction) | Fails cleanly |

**Divergence:** S3 and Azure non-HNS can leave files in *both* source and
destination on partial failure. Memory, Local, and SQL cannot. This is an
observable behavioral difference invisible from the ABC.

**What's missing from the spec:**
- BE-018 needs: "Backends SHOULD implement `move()` atomically where the
  underlying storage supports it. If the backend uses a copy-then-delete
  strategy, it MUST document this in its capability declaration. The caller
  MUST NOT assume atomicity unless the backend declares it."
- Consider a `Capability.ATOMIC_MOVE` (parallel to `ATOMIC_WRITE`) so
  callers can query whether move is safe under concurrent access.
- Same analysis applies to BE-019 (`copy()`) — though copy has no
  delete-after phase, partial failure can still leave a corrupt destination.

---

### Gap 6: Resource Lifecycle on Error Paths

**What the spec says:** SIO-001 says "the caller is responsible for consuming
and closing the stream." SIO-004 says "if a read operation fails, no partial
stream is returned — the error is raised before any data is returned."
SIO-005 says "partially opened resources are cleaned up where possible."

The spec does not define what happens in the *gap* between acquiring the raw
handle and returning the wrapped stream to the caller. This is the
acquire-then-wrap phase.

**What backends do:**

```
# Pattern in all affected backends:
def read(self, path: str) -> BinaryIO:
    raw = self._native_open(path)          # ← raw handle acquired
    return _ErrorMappingStream(raw, ...)   # ← if __init__ raises, raw leaks
```

| Backend | Wrapping layers | Protected? |
|---------|----------------|------------|
| Local | Direct `open()` → no wrapping | N/A (OS handles) |
| Memory | `BytesIO` from dict | N/A (in-memory) |
| S3 (`_s3.py:130-134`) | s3fs handle → `_ErrorMappingStream` → `BufferedReader` | **No** (BUG-159) |
| SFTP (`_sftp.py:~385`) | paramiko `SFTPFile` → `_ErrorMappingStream` | Fixed (BUG-142) |
| Azure (`_azure.py:~310`) | Azure downloader → `_ErrorMappingStream` | Fixed (BUG-158) |

**Bugs caused:** BUG-142, BUG-156, BUG-158, BUG-159 (4 resource leak bugs).

**What's missing from the spec:**
- SIO-001 needs: "Between acquiring a raw handle and returning the wrapped
  stream, backends MUST ensure the raw handle is closed if wrapping fails.
  The recommended pattern is `_safe_wrap(raw, wrapper)` which closes `raw`
  on any exception from `wrapper`."
- This is not just a testing gap — it's a *contract* gap. The ABC docstring
  for `read()` should state the resource safety invariant.

---

## 3. Combinatorial View

The backend ABC has ~18 abstract methods. Each can be called with various
parameter combinations. Across 7 backends, the behavioral test space is:

```
Methods (18) × Parameter combos (~5 avg) × Backends (7) × State conditions (~3)
= ~1,890 behavioral test points
```

The current conformance suite covers ~490 of these (~26%). The gaps above
identify the *categories* where the remaining 74% contains bugs.

A property-based stateful model (BK-139 P4) can explore this space
combinatorially, but only if the oracle — the behavioral contract — defines
what "correct" means for each point. Currently, ~30% of the behavioral
surface has no specified correct answer.

---

## 4. Relationship to BK-139

BK-139 implements prevention strategies from the bug-prevention research.
This contract analysis is **upstream** — it defines what the tests should
verify.

| BK-139 deliverable | Depends on contract? | Which gap? |
|--------------------|---------------------|------------|
| `_safe_wrap` helper | No (structural fix) | — |
| Hypothesis P4 (stateful model) | **Yes** — model needs oracle | Gaps 1–5 |
| Hypothesis P1–P3 | No (pure-function roundtrips) | — |
| Extended conformance (param combos) | **Yes** — expected values need spec | Gaps 1, 3, 4 |
| Extended conformance (error fidelity) | **Yes** — correct error type needs spec | Gap 2 |
| Extended conformance (resource cleanup) | Partially — pattern is clear | Gap 6 |
| `check_error_handling.py` | No (static pattern) | — |

**Recommendation:** Spec amendments for Gaps 1–5 should be completed before
or alongside BK-139's P4 and extended conformance work. Gap 6's amendment
can ship with the `_safe_wrap` deliverable.

---

## 5. Proposed Spec Amendments

| Spec | Gap | Amendment |
|------|-----|-----------|
| BE-008 | 1 | Add precondition order: path validity → type conflict → overwrite |
| BE-021 | 2 | Add canonical error mapping table for cross-cutting scenarios |
| BE-014 | 3 | Add "MUST NOT raise NotFound for missing paths; yields nothing" |
| BE-015 | 3 | Same clause for `list_folders()` |
| DEPTH-001 | 4 | Add reference algorithm with `RemotePath.parts` counting and inclusive comparison |
| BE-018 | 5 | Document atomicity is backend-dependent; consider `ATOMIC_MOVE` capability |
| SIO-001 | 6 | Add acquire-then-wrap safety invariant |

These amendments tighten the contract without changing any existing correct
behavior — they codify what all backends already do (or should do). Where a
backend currently diverges from the tightened contract, that's a bug to fix.

---

## 6. Impact on Test Design

With tightened specs, the test design becomes straightforward:

**For conformance tests (BK-139 extended suite):**
- Gap 1: `test_write_on_directory_raises_invalid_path` (all backends)
- Gap 2: `test_read_on_directory_raises_remote_store_error` (all backends)
- Gap 3: `test_list_files_missing_path_yields_nothing` (all backends)
- Gap 4: `test_list_files_max_depth_reference_algorithm` (all backends)
- Gap 5: Document-only (no behavioral test, but capability query test)
- Gap 6: `test_read_wrapper_failure_closes_raw_handle` (per-backend with monkeypatch)

**For property-based model (BK-139 P4):**
- The model oracle can now define:
  - `write(dir_path)` → `InvalidPath` (not `AlreadyExists`)
  - `list_files(missing)` → empty (not `NotFound`)
  - `move()` post-state: src gone, dst present (atomicity is backend flag)
  - depth counting uses parts-based algorithm

Without these amendments, the P4 oracle would need per-backend exception
tables, defeating the purpose of a unified behavioral contract.
