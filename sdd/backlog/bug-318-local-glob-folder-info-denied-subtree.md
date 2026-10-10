# BUG-318 — `LocalBackend.glob` and `get_folder_info` leave out a subtree they cannot read
<!-- doc: repo-only -->

Filed by BUG-280 (PR #1113), whose orient probe found the same swallowing walk
under `glob` and `get_folder_info` that it fixed in the recursive `list_files`,
outside the agreed scope. The index entry holds the current diagnosis; this file
is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

## Evidence

**Where the measurements were taken.** BUG-280 was delivered twice: PR #1093
(branch `bug-280-local-listing-permission`, base `31ebe6be7`) and PR #1113. The
first filed this defect as BUG-311 and measured it on its branch. Neither
branch changes `glob` or `get_folder_info`: `git diff 31ebe6be7 eff7953bb`
leaves `_local.py` untouched, and #1113's `_local.py` hunks touch only the three
listings, their helpers and the imports. So what follows describes master's
code for both methods.

**`glob` swallows by a different stdlib route on each interpreter**, read from
each installed interpreter's standard library rather than run:

| Interpreter | Where the denial is dropped |
|---|---|
| 3.11 | `pathlib._RecursiveWildcardSelector._iterate_directories` ends in `except PermissionError: return` |
| 3.12 | the same method walks with `Path.walk()`, whose default `on_error=None` ignores the error |
| 3.13, 3.14 | `glob.py`'s `select_recursive_step` wraps its `scandir` in `except OSError: pass` |

So `glob("a/**/*.txt")` returns the readable part of the tree as if it were the
whole. On 3.13 a patch on `os.scandir` does not reach that selector:
`glob._StringGlobber` binds `scandir = staticmethod(os.scandir)` at class
creation. A test that fences this needs a real denial (POSIX `chmod`, a Windows
`(RD)` ACL) or a patch on the selector's own attribute.

**A denied top folder lists empty too.** With a real ACL denial (`icacls /deny
RD`) on 3.13.11, Windows, `glob("a/**/*.txt")` and `glob("a/*.txt")` both
returned `[]` for a denied `a`.

**`glob`'s `is_file()` filter answers by interpreter**, for a folder that lists
but cannot be traversed (simulated: `os.stat` refused on the folder's entries,
POSIX's `genericpath.isfile` / `isdir` swapped in, on Windows):

- on 3.11.15, 3.12.13 and 3.13.11, `glob("a/**/*.txt")` raises a bare
  `PermissionError`, because `Path.is_file` re-raises `EACCES`: a never-leak
  breach, which is BUG-319's class;
- on 3.14.0 it silently returns the rest, because `is_file` answers `False`.

**`get_folder_info` drops a denied subfolder** through `rglob`: BUG-280's orient
probe (Python 3.13.11, Windows, trace
[`bug-280`](../traces/bug-280-local-listing-permission-leak.yml) § orient) found
it skips a subfolder whose scan is denied, as `list_files` did before BUG-280.

**A subfolder in Windows' classic delete-pending state** (delete disposition
set while a second handle stays open) still lists in its parent and `stat`s, but
its scan fails with `PermissionError`, `winerror` 5. Measured with
[`delete_pending_probe.py`](../research/token-usage/delete_pending_probe.py)'s
P1b on Windows 11, Python 3.13.11, NTFS and ReFS: master and #1093 skip it in
the recursive `list_files`, #1113 raises `PermissionDenied` for it. Python's own
`rmdir` and `rmtree` did not produce the state on either filesystem.
`test_a_subfolder_in_the_classic_delete_pending_state_raises` pins it; spec 003
lists it under BE-021's Known divergences with this item.

## Why it was not BUG-280

`list_files(recursive=True)` and `glob` reach the same OS behaviour through
different stdlib entry points. `glob` takes a caller's pattern, so replacing
`Path.glob` with a walk means re-implementing pattern matching over it, or
checking the pattern's directories separately. That is a design choice of its
own, and GLOB-005's symlink-escape skip has to survive it.

## Advisory prescription

Raise `PermissionDenied` naming the refused folder when the walk meets one, as
the recursive `list_files` does through `_listing_error` and
`_raise_walk_error`, including the link skip BE-021 now states for a listing's
entries. Decide whether `get_folder_info` aggregates over `list_files` instead
of `rglob`, which would inherit both. Check what GLOB-004's postconditions and
GLOB-017 (empty results) say about a partly readable tree.

The open decision, a subfolder that vanishes mid-walk: skipping it is what every
Local walk does today, and a dangling Windows junction reaches the walk the same
way, since `os.walk` descends into a junction (`is_symlink()` is `False` for it).
Raising for a vanished one was tried in BUG-280's round 3 and reverted in round
4 because it aborted listings over a dangling junction. The classic
delete-pending folder belongs to the same decision: Windows reports it as
denied, though it is going away. RFC-0017's kernel takes Local's listings over
at D3 step 5; a fix here becomes that driver's `classify`.
