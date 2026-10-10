# BUG-319 — `LocalBackend`'s single-path stats leak a raw `PermissionError`, and a looping key a `RuntimeError`
<!-- doc: repo-only -->

Filed by BUG-280's first review round (PR #1113), from the probe that refuted
its migration note's premise that every other `LocalBackend` operation already
maps a denial. The index entry holds the current diagnosis; this file is
evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence

**Where the measurements were taken.** BUG-280 was delivered twice: PR #1093
(branch `bug-280-local-listing-permission`, base `31ebe6be7`) and PR #1113. The
first filed the same class as BUG-313 and measured it on its branch. Neither
branch changes the methods below: `git diff 31ebe6be7 eff7953bb` leaves
`_local.py` untouched, and #1113's `_local.py` hunks touch only the three
listings, their helpers and the imports. So what follows describes master's
code.

**The filing probe** (#1113, round 1; trace
[`bug-280`](../traces/bug-280-local-listing-permission-leak.yml), step
`tmp/probe_premise.py`): an `EACCES` injected on one file's `os.stat`, Windows,
Python 3.13. `glob`, `get_folder_info`, `get_file_info`, `exists` and `is_file`
each let the raw `PermissionError` through; `read_bytes` did not.

**Per interpreter** (#1093's BUG-313, Windows): the script denies `os.stat` on
every entry inside `a`, which is what a POSIX `0o444` directory does to a
non-root user, and substitutes POSIX's `genericpath.isfile` and `isdir` for
Windows' native ones.

| Interpreter | `get_file_info("a/f.txt")` | `is_file` / `is_folder` | `exists` |
|---|---|---|---|
| 3.11.15, 3.12.13, 3.13.11, 3.13.13 | raw `PermissionError`, no `path` | raw `PermissionError` | raw `PermissionError` |
| 3.14.0, 3.14.2 | `NotFound`, path `a/f.txt` | `False` | `True` with this script (see below) |

The 3.14 `exists` cell shows the script's reach, not the method's answer:
Windows' `os.path.exists` is the builtin `nt._path_exists`, which never reaches
the patched `os.stat`. POSIX's `genericpath.exists` catches `OSError` and would
answer `False`; that is unmeasured. `is_file` and `is_folder` were measured on
3.11.15, 3.13.13 and 3.14.2; `get_file_info` on every interpreter in its row.

The mechanism: each method asks `Path.is_dir` / `is_file` / `exists`. On 3.11 to
3.13 those re-raise `EACCES` and nothing maps it; on 3.14 they call
`os.path.isdir` / `isfile` / `exists`, whose POSIX forms answer `False` for any
`OSError`, so a path the OS refuses to `stat` reads as absent. BE-021 forbids
`exists`, `is_file` and `is_folder` from raising at all, so the predicates
breach it on 3.11 to 3.13 whatever the right non-raising answer is.

**`get_folder_info` inherits it through both `Store` routes.** On a folder whose
parent cannot be traversed, `get_folder_info` and `Store.get_folder_info`, with
or without `max_depth`, leak a raw `PermissionError` on 3.11.15 and 3.13.11 and
answer `NotFound` on 3.14.0 (measured at #1093's `cdcaa35c6`).

**The ring around it**, every other hit of the whole-class pattern
`rg -n "\.exists\(\)|\.is_(file|dir)\(\)" src/remote_store/backends/_local.py`
outside the listings and `glob` (BUG-318). Measured with the same script shape,
extended to deny `open` and `unlink` inside the folder and to swap in
`genericpath.exists`, on 3.11.15, 3.13.11 and 3.14.0, unless marked as read:

- **`delete_folder`**: `if not full.exists()` and `if not full.is_dir()` sit
  outside its `except OSError`. On 3.11 to 3.13 both forms leak a raw
  `PermissionError`. On 3.14 the strict form answers `NotFound`, and
  **`missing_ok=True` returns cleanly while the folder is still on disk**: a
  delete reported done that never happened (3.14.0).
- **`check_health`**: `if not self._root.is_dir()` on a root whose parent cannot
  be traversed leaks a raw `PermissionError` on 3.11 and 3.13, and answers
  `NotFound` on 3.14 for a root that is there.
- **`read` and `delete`**: their `is_dir()` sits inside the `except
  PermissionError` arm, to choose `InvalidPath` or `PermissionDenied`, but on
  3.11 to 3.13 that `is_dir()` itself re-raises, and a raw `PermissionError`
  escapes the handler (3.11, 3.13). On 3.14 both answer `PermissionDenied`.
  `read_bytes` has the same shape; read only.
- **The writers** (`write`, `write_atomic`, `open_atomic`) at their `is_dir()`
  and `overwrite`-guard `exists()`, and **`move` / `copy`** at the source and
  destination checks: read only. The operation after each pre-check maps a
  `PermissionError` itself, so a pre-check that answers wrongly may never be
  reached; measure each before deciding.

**The looping key**: `_resolve` raises Python's `RuntimeError` for a key that is
or passes through a symlink loop, on 3.11 (measured on `list_files` and
`exists`); 3.14 answers the loop as absent. #1093's spec text records the same
for 3.11 and 3.12, and 3.13 answering as 3.14 does. Every keyed operation goes through `_resolve`, so the fix is there rather
than per operation.

## Advisory prescription

Decide first whether this waits for RFC-0017's kernel, where Local's one
`classify` answers every row at D3 step 5; fixing them one method at a time
first is the per-site pattern BUG-280 stopped. `delete_folder(missing_ok=True)`
on 3.14 argues against waiting.

If fixed here: for `get_file_info`, classify and measure with one `stat` and map
a `PermissionError` to `PermissionDenied`, keeping `InvalidPath` for a directory
and `NotFound` for an absent path. The predicates are the open decision: BE-021
forbids them from raising, so on a denial they must answer something. `False`
removes the leak, but then `Store.get_folder_info(max_depth=N)`, which asks
`backend.is_folder(path)` first, answers a denied folder `NotFound`; avoiding
that means `Store`'s depth branch learning about a denial without asking a
predicate, which reaches every backend.
