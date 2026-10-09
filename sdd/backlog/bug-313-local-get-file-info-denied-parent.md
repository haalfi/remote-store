# BUG-313 — `LocalBackend.get_file_info` answers a file it may not `stat` as missing, or leaks `PermissionError`
<!-- doc: repo-only -->

Filed by BUG-280's closing round. Its sibling sweep looked for every place that
classifies a path with `Path.is_file` or `is_dir` (`rg -n "\.is_(file|dir)\(\)"
src/remote_store/backends/_local.py`). BUG-280 fixed the folder walks among
them, and `get_file_info` was left out of that PR's scope by decision.

## Evidence

Measured at the BUG-280 branch on Windows. The test file is `a/f.txt`. The
script denies `os.stat` on every entry inside `a`, which is what a POSIX `0o444`
directory does to a non-root user. It also substitutes POSIX's
`genericpath.isfile` and `isdir` for Windows' native ones:

| Interpreter | `get_file_info("a/f.txt")` |
|---|---|
| 3.13.11 | raw `builtins.PermissionError`, no `path` |
| 3.14.0 | `NotFound`, path `a/f.txt` |

BE-021's canonical table wants `PermissionDenied` for an operation the OS
denies. 3.11 and 3.12 were not run here. Their `Path.is_file` re-raises
`EACCES` just as 3.13's does, which BUG-280 measured for the walks.

The mechanism is the one BUG-280 measured for the walks. `get_file_info` asks
`full.is_dir()` and then `full.is_file()` before its own `stat`:
- on 3.11 to 3.13, `Path.is_dir` / `is_file` re-raise `EACCES`, and nothing maps
  it;
- on 3.14, they call `os.path.isdir` / `isfile`, whose POSIX forms answer `False`
  for any `OSError`, so the method concludes the file is missing.

## Advisory prescription

Classify and measure with one `stat`, as BUG-280's `_stat_or_absent` does for the
walks. Map a `PermissionError` to `PermissionDenied`. Keep `InvalidPath` for a
directory and `NotFound` for an absent path. The other `is_dir()` pre-checks in
`_local.py`, which guard `read`, `write`, `move` and `copy`, are the next ring
of the same class. Measure each before deciding: the operation after each
pre-check maps a `PermissionError` itself, so a pre-check that answers wrongly
may never be reached.
