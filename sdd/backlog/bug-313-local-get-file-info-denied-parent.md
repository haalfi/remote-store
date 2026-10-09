# BUG-313 — `LocalBackend`'s `get_file_info` and path predicates misanswer a path they may not `stat`
<!-- doc: repo-only -->

Filed by BUG-280's closing round. Its sibling sweep listed every place that
classifies a path with `Path.is_file` or `is_dir` (`rg -n "\.is_(file|dir)\(\)"
src/remote_store/backends/_local.py`). BUG-280 fixed the folder walks among
them. `get_file_info` was left out of that PR's scope by decision.

The next round's measuring member found that the same sweep also hits the public
predicates `exists`, `is_file` and `is_folder`, which the first filing missed.
It also found that one `Store` path inherits the predicates' answer. The item
was widened to both.

## Evidence

Measured at the BUG-280 branch on Windows. The script denies `os.stat` on every
entry inside `a`, which is what a POSIX `0o444` directory does to a non-root
user. It also substitutes POSIX's `genericpath.isfile` and `isdir` for Windows'
native ones.

| Interpreter | `get_file_info("a/f.txt")` | `exists` / `is_file` / `is_folder` |
|---|---|---|
| 3.11.15, 3.12.13, 3.13.11, 3.13.13 | raw `builtins.PermissionError`, no `path` | raw `builtins.PermissionError` (measured on 3.11.15 and 3.13.13) |
| 3.14.0, 3.14.2 | `NotFound`, path `a/f.txt` | `False` (measured on 3.14.2) |

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

The other `is_dir()` pre-checks in `_local.py`, which guard `read`, `write`,
`move` and `copy`, are the next ring. Measure each before deciding: the
operation after each pre-check maps a `PermissionError` itself, so a pre-check
that answers wrongly may never be reached.
