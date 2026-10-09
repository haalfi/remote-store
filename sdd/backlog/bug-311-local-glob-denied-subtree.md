# BUG-311 — `LocalBackend.glob` drops a denied subtree silently
<!-- doc: repo-only -->

Filed by BUG-280, which fixed the same shape in `LocalBackend.list_files`'
recursive branches and left `glob` out of scope by decision rather than by
oversight.

## Evidence

Measured at the BUG-280 branch on CPython 3.13.11 (Windows) with a tree
`a/f.txt`, `a/sub/g.txt`. `LocalBackend.glob("a/**/*.txt")` walks through
`Path.glob`, and the 3.13 recursive selector
(`glob._Globber.recursive_selector`'s `select_recursive_step`) wraps its
`scandir` in `except OSError: pass`. So a subfolder the OS refuses to list is
skipped, and the call returns the readable part of the tree as if it were the
whole of it. Read from the interpreter's source with `inspect.getsource`, not
injected: patching `os.scandir` does not reach that selector on 3.13, because
`glob._StringGlobber` binds `scandir = staticmethod(os.scandir)` at class
creation. A cell that fences this needs a real denial (POSIX `chmod`) or a patch
on the selector's own attribute.

The other supported interpreters swallow too, by different code, read from each
installed interpreter's standard library rather than from runs. On 3.11,
`pathlib._RecursiveWildcardSelector._iterate_directories` ends in
`except PermissionError: return`. On 3.12, the same method walks with
`Path.walk()`, whose default `on_error=None` ignores the error. On 3.14,
`glob.py`'s `select_recursive_step` keeps 3.13's `except OSError: pass`.

A later measurement on the same branch, with a real ACL denial (`icacls /deny
RD`) on 3.13.11, found a denied **top** folder also returns `[]` from
`glob("a/**/*.txt")` and `glob("a/*.txt")`, not only a denied subtree.

`glob` also filters with `item.is_file()`, and a folder that lists but cannot be
traversed answers differently by interpreter. This was measured with BUG-280's
`_deny_child_stat` simulation (denied `os.stat` on the folder's entries,
POSIX's `genericpath.isfile` / `isdir` swapped in), on Windows, not against a
real POSIX directory. `glob("a/**/*.txt")`:
- on 3.11.15, 3.12.13 and 3.13.11, raises a bare `builtins.PermissionError`,
  because `Path.is_file` re-raises `EACCES`. That is a never-leak breach of
  BE-021, not a silent drop, and both base and BUG-280's head do it.
- on 3.14.0, silently returns the rest, because `is_file` answers `False`.

So this item owes a mapping on 3.11 to 3.13 as well as an answer on 3.14.

## Why it is not BUG-280

`list_files(recursive=True)` and `glob` reach the same OS behaviour through
different stdlib entry points. BUG-280 replaced `rglob` with
`os.walk(onerror=...)`. `glob` takes a caller's pattern, so the same swap means
re-implementing pattern matching over a walk, or checking the pattern's
directories separately. That is a design choice of its own, and GLOB-005's
symlink-escape skip has to survive it.

## Advisory prescription

Raise `PermissionDenied`, naming the pattern's prefix, when the walk meets a
denied folder. That matches `list_files` after BUG-280 and SFTP's recursive
walk. Check first whether GLOB-004's postconditions or GLOB-017 (empty results)
say anything about a partly readable tree.
