# BUG-313 — `LocalBackend`'s `get_file_info` and path predicates misanswer a path they may not `stat`
<!-- doc: repo-only -->

Filed by BUG-280's closing round. Its sibling sweep listed every place that
classifies a path with `Path.is_file` or `is_dir`. BUG-280 fixed the folder
walks among them. `get_file_info` was left out of that PR's scope by decision.

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

**The `Store` path that inherits it.** `Store.get_folder_info(path,
max_depth=N)` asks `backend.is_folder(path)` before it aggregates through
`list_files`. When `path`'s parent cannot be traversed:
- with a `max_depth`, it leaks the raw `PermissionError` on 3.11 to 3.13 and
  answers `NotFound` on 3.14;
- with `max_depth=None`, it reaches the backend aggregate and raises
  `PermissionDenied` since BUG-280.

`tests/backends/local/test_listing_permission.py` pins that cell as a strict
`xfail`. It names this item, and it fails the day the `max_depth` form raises
`PermissionDenied`.

## Advisory prescription

For `get_file_info`, classify and measure with one `stat`, as BUG-280's
`_stat_or_absent` does for the walks. Map a `PermissionError` to
`PermissionDenied`. Keep `InvalidPath` for a directory and `NotFound` for an
absent path.

The predicates are the open decision. BE-021 forbids them from raising, so on a
denial they must answer something. `False` is what 3.14 already does, and it
makes the `Store` `max_depth` form answer `NotFound` on every version. That
removes the leak, but leaves the two `max_depth` forms disagreeing.

Making the two forms agree means changing `Store`'s depth branch, so that it
learns about a denial without asking a predicate. That reaches every backend,
which is why it was kept out of BUG-280.

The next ring is every other hit of the whole-class pattern above, outside the
walks BUG-280 fixed and the predicates and `get_file_info` this item names:

- **`delete_folder`**: `if not full.exists()` and then `if not full.is_dir()`,
  both outside its `except OSError`. Nothing after them maps the error, so on a
  path whose parent cannot be traversed the pre-check *is* the leak: a raw
  `PermissionError` on 3.11 to 3.13, `NotFound` on 3.14. This was read from the
  code and not run.
- **The writers**: `write`, `write_atomic` and `open_atomic`, at their `is_dir()`
  and `overwrite`-guard `exists()`.
- **`move` and `copy`**: the source `exists()` / `is_dir()` and the destination
  `is_dir()` / `exists()`.

For the writers and for `move` / `copy`, the operation after the pre-check maps
a `PermissionError` itself, so a pre-check that answers wrongly may never be
reached. Measure each before deciding.

`read`, `read_bytes` and `delete` are not in this ring. Their `is_dir()` sits
inside an `except PermissionError` arm and only chooses between `InvalidPath`
and `PermissionDenied` there.
