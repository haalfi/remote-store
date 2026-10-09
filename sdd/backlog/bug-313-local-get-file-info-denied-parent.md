# BUG-313 — `LocalBackend`'s `get_file_info` and path predicates misanswer a path they may not `stat`
<!-- doc: repo-only -->

Filed by BUG-280's third review round, before the PR was narrowed and its
review restarted. Its sibling sweep listed every place that
classifies a path with `Path.is_file` or `is_dir`. BUG-280 fixes the
single-level scans among them; the recursive walks and `get_folder_info` went
to BK-416 (RFC-0017 step 5). `get_file_info` was left out of that PR's scope by
decision.

The next round's measuring member found that the public predicates `exists`,
`is_file` and `is_folder` have the same shape, which the first filing missed. It
also found that one `Store` path inherits the predicates' answer. The item was
widened to both.

The first sweep's pattern, `rg -n "\.is_(file|dir)\(\)"`, cannot see
`Path.exists`. The pattern that enumerates the whole class is
`rg -n "\.exists\(\)|\.is_(file|dir)\(\)" src/remote_store/backends/_local.py`.

## Evidence

Measured at the BUG-280 branch on Windows. The script denies `os.stat` on every
entry inside `a`, which is what a POSIX `0o444` directory does to a non-root
user. It also substitutes POSIX's `genericpath.isfile` and `isdir` for Windows'
native ones.

| Interpreter | `get_file_info("a/f.txt")` | `is_file` / `is_folder` | `exists` |
|---|---|---|---|
| 3.11.15, 3.12.13, 3.13.11, 3.13.13 | raw `builtins.PermissionError`, no `path` | raw `builtins.PermissionError` | raw `builtins.PermissionError` |
| 3.14.0, 3.14.2 | `NotFound`, path `a/f.txt` | `False` | `True` with this script (see below) |

The `exists` cell on 3.14 shows how far this script reaches, and says nothing
about the method. On 3.14, `Path.exists` calls `os.path.exists`, and on Windows
that is the builtin `nt._path_exists`, which never reaches the patched `os.stat`.
The script swaps in `genericpath.isfile` and `isdir` but not `exists`. On POSIX,
`genericpath.exists` catches `OSError` and would answer `False`, but that is
unmeasured.

`is_file` and `is_folder` were measured on 3.11.15, 3.13.13 and 3.14.2.
`get_file_info` was measured on every interpreter in its row.

BE-021's canonical table wants `PermissionDenied` for an operation the OS
denies. BE-021 also forbids `exists`, `is_file` and `is_folder` from raising at
all. So the predicates breach the contract on 3.11 to 3.13 whatever the right
non-raising answer turns out to be.

The mechanism is the one BUG-280 measured for the walks. Each of these asks
`Path.is_dir` / `is_file` / `exists`:
- on 3.11 to 3.13, those re-raise `EACCES`, and nothing maps it;
- on 3.14, they call `os.path.isdir` / `isfile` / `exists`, whose POSIX forms
  answer `False` for any `OSError`, so a path the OS refuses to `stat` reads as
  absent.

**`get_folder_info` inherits it, through both `Store` routes.** On a folder
whose parent cannot be traversed, `get_folder_info` and `Store.get_folder_info`
both classify the folder with `is_file()` / `is_dir()`, with or without a
`max_depth`; the `max_depth` form asks `backend.is_folder(path)` before it
aggregates through `list_files`. Measured with this item's script on BUG-280's
narrowed tree, committed as `cdcaa35c6`, where `get_folder_info` is master's
code, all three forms leak a raw `builtins.PermissionError` on 3.11.15
and 3.13.11 and answer `NotFound` on 3.14.0. The routes agree; they agree on
the wrong answer.

## Advisory prescription

**Decide first whether this waits for BK-416.** At RFC-0017 step 5, Local's one
`classify` behind the kernel answers every row here, and the walks with them;
fixing them one method at a time first is the per-site pattern BUG-280 stopped.

If it is fixed here: for `get_file_info`, classify and measure with one `stat`,
as BUG-280's `_stat_or_absent` does for the single-level scans. Map a
`PermissionError` to `PermissionDenied`. Keep `InvalidPath` for a directory and
`NotFound` for an absent path.

The predicates are the open decision. BE-021 forbids them from raising, so on a
denial they must answer something. `False` is what 3.14 already does; it removes
the leak, but then `Store.get_folder_info(max_depth=N)` answers a denied folder
`NotFound`, a missing folder rather than a refused one. Avoiding that means
`Store`'s depth branch learning about a denial without asking a predicate, which
reaches every backend.

The next ring is every other hit of the whole-class pattern above. It excludes
the single-level scans BUG-280 fixed, the recursive walks and `get_folder_info`
(BK-416), the predicates and `get_file_info` this item names, and `glob`'s
`item.is_file()`, which is BUG-311's. Each was measured with this
item's script shape, extended to deny `open` and `unlink` inside the folder
and to swap in `genericpath.exists`, on 3.11.15, 3.13.11 and 3.14.0, unless it
is marked as read.

- **`delete_folder`**: `if not full.exists()` and then `if not full.is_dir()`,
  both outside its `except OSError`, so nothing after them maps the error. On
  3.11 to 3.13 both forms leak a raw `PermissionError`. On 3.14 the strict form
  answers `NotFound`, and **`missing_ok=True` returns cleanly while the folder
  is still on disk**: a delete reported done that never happened. The 3.14
  cells were measured by BUG-280's sixth review round, before the narrowing,
  on 3.14.0. This is the
  most urgent member of the ring.
- **`check_health`**: `if not self._root.is_dir()` on a root whose parent cannot
  be traversed leaks a raw `PermissionError` on 3.11 and 3.13 and answers
  `NotFound` on 3.14, for a root that is there.
- **`read` and `delete`**: their `is_dir()` sits inside the `except
  PermissionError` arm, to choose `InvalidPath` or `PermissionDenied`, but on
  3.11 to 3.13 that `is_dir()` itself re-raises `EACCES`. A raw
  `PermissionError` then escapes the handler, as measured for both on 3.11 and
  3.13. On 3.14 both answer `PermissionDenied`. **`read_bytes`** has the same
  shape and is read only: the script's `open` patch does not reach its read.
- **The writers**: `write`, `write_atomic` and `open_atomic`, at their `is_dir()`
  and `overwrite`-guard `exists()`. Read only.
- **`move` and `copy`**: the source `exists()` / `is_dir()` and the destination
  `is_dir()` / `exists()`. Read only.

For the writers and for `move` / `copy`, the operation after the pre-check maps
a `PermissionError` itself, so a pre-check that answers wrongly may never be
reached. Measure each before deciding.
