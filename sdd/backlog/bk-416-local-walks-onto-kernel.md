# BK-416 — `LocalBackend`'s recursive walks map their own errors, and RFC-0017 step 5 is where they get one classifier
<!-- doc: repo-only -->

Filed by BUG-280 (PR #1093) when it stopped. BUG-280 was filed as "three
listing methods leak a raw `PermissionError`". Over seven review rounds it grew
into a `LocalBackend`-only error model for every folder walk, and each round
found the next site or error class the per-site rules had missed. Round 7
measured a Windows regression in that model.

The maintainer then cut BUG-280 back to the single-level scans (`list_files`
without `recursive`, `list_folders`, `iter_children`). The walks were left as
master has them, for RFC-0017's kernel. Under RFC-0017 the kernel owns:

- the never-leak choke point on every `list_page` iteration, which RFC-0017
  names for BUG-249 and BUG-280;
- the recursive walk and `max_depth` (BK-389 decision 7);
- the `get_folder_info` aggregate.

A `LocalDriver` supplies `list_page` and one `classify(exc, op, key)`. Local
migrates at step 5. This item is that step's `LocalBackend` half, written down
before the step exists so the evidence is not lost.

## What ships after BUG-280, measured

Every row was measured on BUG-280's narrowed tree, committed as `cdcaa35c6`,
against master `31ebe6be7` on Windows, CPython 3.11.15, 3.13.11 and 3.14.0. "Denied listing" is a real
`icacls /deny RD`. "Unstattable entries" is BUG-280's `_deny_child_stat`
shape: `os.stat` refused on a folder's entries, with POSIX's `genericpath`
predicates swapped in.

| Call | Denied subfolder listing | Subfolder with unstattable entries |
|---|---|---|
| recursive `list_files` | subtree silently left out, every version | 3.11–3.13: `PermissionDenied`; 3.14: silently left out |
| recursive `list_files(max_depth=N)` | subtree silently left out | `PermissionDenied`, every version |
| `get_folder_info` | under-counts silently | 3.11–3.13: raw `builtins.PermissionError`; 3.14: under-counts silently |
| `Store.get_folder_info(max_depth=N)` | under-counts silently, through `list_files` | as `list_files(max_depth=N)` |

A denied **listed** folder is dropped the same way. BUG-280's round 3 measured
it at `2103ed1de`. With `a` itself at chmod 0 or 0o111, on Linux uid 1000 on
3.11 to 3.14, and under a real `icacls /deny RD` on Windows 3.13, two calls
return `[]`, where the non-recursive call raises `PermissionDenied`:
`list_files("a", recursive=True)` and the `max_depth=5` form. `get_folder_info`
counts 0. The only check on the listed folder before the walk is a `stat`,
which a folder that refuses its listing still answers. On 3.14 the plain walk
also drops a listed folder that lists but cannot be traversed: with `a` at
0o444, `list_files("a")` raises and `list_files("a", recursive=True)` returns
`[]`. BUG-280's round 5 measured that on Linux 3.14.8 at `0b069ab3b`.

Two of these cells are BE-021 breaches:
- the silent drop, of a subtree or of the whole listing, a short answer that
  looks complete;
- `get_folder_info`'s raw leak.

`tests/backends/local/test_listing_permission.py` pins the denied-listing cases
as eight strict `xfail` cells naming this item, in
`test_a_recursive_walk_raises_on_a_denied_folder`: four entry points, each with
the subfolder and with the listed folder denied. They fail the day the walks
raise, and the marks have to come off then. So does
`test_a_recursive_list_files_maps_a_denial_it_meets[recursive]` on 3.14, which
pins the plain walk's skip of an unstattable entry there.

## What the rounds learned, for the driver's `classify`

- **A denied folder must raise, and a vanished one must read as absent.** On
  Windows the two are not told apart by exception type. A folder deleted
  concurrently while a walk lists it often answers `PermissionError` with
  `winerror=5` (the delete-pending state). BUG-280's round 7 measured this
  with one thread looping `rmtree` / recreate on `a/sub` and the other calling
  each walk 3000 times, with an `os.walk` hook that re-raised every
  `PermissionError`.

  | Interpreter | Calls answering `PermissionDenied` (gfi / recursive / `max_depth`) |
  |---|---|
  | 3.13.11 | 401 / 388 / 297 |
  | 3.11.15 | 1717 / 1706 / 1692 |
  | 3.14.0 | 317 / 159 / 75 |

  Under the same churn, master leaked a raw `FileNotFoundError` in 38–265
  calls. The rates depend on the scheduler. A classifier that answers "denied"
  from the exception alone turns a concurrent delete into a permission error.
  Telling them apart, for example by a re-check, is **unmeasured** and is this
  item's open decision. Run a deterministic delete-pending reproduction first.

  BUG-280's single-level scans meet the same state, and map it. Measured with
  `tmp/bug280/scan_churn.py` (gitignored; the shape is one thread looping
  `rmtree` / recreate and the other calling the method 3000 times). The branch
  was BUG-280 at `cdcaa35c6`, master was `31ebe6be7`, and the runs were on
  Windows. With the listed folder `a` itself churned:

  | Interpreter | Branch: `PermissionDenied` (`list_files` / `list_folders` / `iter_children`) | master: raw `PermissionError` (`winerror=5`) |
  |---|---|---|
  | 3.11.9 | 33 / 7 / 0 | 24 / 34 / 8 |
  | 3.13.11 | 35 / 40 / 26 | 52 / 59 / 53 |
  | 3.14.2 | 54 / 65 / 83 | 40 / 36 / 56 |

  With only the folder's children churned, the branch answered all 3000 calls
  of each method, while master leaked a raw `FileNotFoundError` in 9 to 261
  calls of `list_files` and `iter_children` (none of `list_folders`).
  `classify` inherits this: the scans' "a removed folder lists as empty" holds
  on Windows only once the delete has completed.
- **A link the caller cannot read through is skipped, by BE-021's listing
  clause.** BUG-280 gave the single-level scans that rule
  (`_entry_stat_or_absent`); the walks do not follow it yet. Measured with
  `tmp/bug280/link_walk_probe.py` (gitignored). It is simulated on Windows:
  `a/link` is a plain file whose `lstat` reports a link and whose `stat` is
  refused, with POSIX `genericpath.isfile` / `isdir` swapped in. The tree is
  `a/f.txt`, `a/sub/g.txt`, `a/link`.

  | Call | 3.11.15, 3.12.13, 3.13.11 | 3.14.0 |
  |---|---|---|
  | `list_files("a")` | `a/f.txt` | `a/f.txt` |
  | `list_files("a", recursive=True)` | `PermissionDenied` | both files |
  | `list_files(..., max_depth=5)` | `PermissionDenied` | `PermissionDenied` |
  | `get_folder_info("a")`, `Store.get_folder_info("a")` | raw `PermissionError` | 2 |
  | `Store.get_folder_info("a", max_depth=5)` | `PermissionDenied` | `PermissionDenied` |

  The same tree therefore lists one level deep and fails recursively, and
  `get_folder_info` leaks. `classify` has to answer the link from `lstat`, as
  the scans do.
- **A link that escapes the root is answered two ways, and BE-021 leaves it
  open.** The single-level scans list it, because its `stat` succeeds, and a
  `read` of that key then raises `InvalidPath("Path escapes root directory")`.
  `glob` skips it (GLOB-005). The recursive walks never descend into a folder
  link (`os.walk` with `followlinks=False`, and `rglob`). BE-021's link clause
  decides only dangling, looping and refused-target links, so `classify` has
  to choose.
  This was read from the code by BUG-280's round 3 and not run.
- **The walks' native errors are mapped, but not classified.** BUG-280 keeps the
  recursive branches inside `list_files`' handler, so whatever escapes them
  reaches the caller as `PermissionDenied` or a `RemoteStoreError`, never raw.
  That includes a file removed mid-walk (`FileNotFoundError` from its `stat`)
  and, under `max_depth`, a dangling link or a link loop within the depth
  bound. `os.walk` lists those links as files, and their `stat` fails on every
  call. A link below the bound is never reached: with one at
  `a/sub/dangling.txt`, `max_depth=0` lists and `max_depth=1` raises. Master
  leaked all of them raw; `classify` should answer them as absences. BUG-280's
  round 4 measured them on Linux 3.11 to 3.14 at `a387794f3`. Under churn,
  plain recursive raised `RemoteStoreError` in 20 to 42 calls and `max_depth`
  in about 200, per interpreter, over about 4 s per mode. Every `max_depth`
  call over a dangling link or loop within the bound raised. Round 5 measured
  the depth bound at `0b069ab3b`. On Windows 3.11 the plain walk raises too,
  for a dangling junction or a junction loop, because 3.11's `rglob` selectors
  catch only `PermissionError`; 3.12 to 3.14 skip them.
- **On 3.11 and 3.12, a link loop in the path itself leaks a bare
  `RuntimeError`.** `_resolve` resolves the deepest existing ancestor, and
  `Path.resolve` raises `RuntimeError("Symlink loop from …")` there; 3.13 and
  3.14 do not. It reaches every operation, not only listings, because every
  operation resolves its path. BUG-280's round 4 measured it on Linux 3.11 and
  3.12, on head and master alike, for `list_files('a/loop1')`, `a/self/x` and
  the other listing calls. `classify` needs it, and the fix belongs in
  `_resolve`, not per operation.
- **`_resolve` reports a folder mid-delete as escaping the root.** In the same
  listed-folder runs, both trees raised `InvalidPath("Path escapes root
  directory")` in up to 350 of 3000 calls per method; one run (3.11.9, the
  branch's `iter_children`) met none. `_within_root` resolves
  the deepest existing ancestor, and a delete-pending folder resolves to
  something that is not under the root. The cause is read from the code and the
  message, not traced further. The kernel's absence answer has to come before
  this check, or the check has to learn the state.
- **"Absent" is a short list, not "anything but a denial".** When a folder's
  scan fails with a non-permission `OSError` (`EIO`, `ENAMETOOLONG`,
  `WinError 362` for a cloud placeholder whose provider is not running), the
  walks mostly skip the folder. The `max_depth` walk's `os.walk` and plain
  `rglob` on 3.12 to 3.14 do. Plain `rglob` on 3.11 does not: its selectors
  catch only `PermissionError`, so the error propagates, now mapped. That was
  read from each interpreter's `pathlib` / `glob` source. BUG-280's
  single-level scans read as absent only
  `_is_absence`'s set, which is what `Path.is_dir` read as `False` on 3.11 to
  3.13: `ENOENT`, `ENOTDIR`, `EBADF`, `ELOOP`, and `winerror` 21, 123 and 1921.
  They map anything else to a `RemoteStoreError` naming the listed key, as SFTP
  does for `EIO`. That is the shape for `classify`: a short absence list, a
  denial, and a mapped error for the rest, not a skip and not a leak. The
  scans' cells inject `EIO` at the folder's `stat`, an entry's `stat` and the
  folder's scan; nothing injects it into the walks yet.
- **Classify from one `stat`, not from `Path.is_file` / `is_dir`.** On 3.14
  those call `os.path.isfile` / `isdir`, whose POSIX forms answer `False` on
  `EACCES`. On 3.11–3.13 they re-raise it. BUG-280's `_stat_or_absent` is the
  shape, and it also closes the window between classifying an entry and
  measuring it.
- **`Store.get_folder_info` takes two routes:** the backend aggregate for
  `max_depth=None`, and `list_files` plus `is_folder` otherwise. They have
  disagreed twice on one denial. Under the kernel both are one listing, which
  removes the split rather than patching it; BUG-313 keeps the `is_folder`
  half.

## Absorbed

**BK-415**, an opt-in way to skip folders the caller may not read, is
absorbed here. It was filed while BUG-280 still made the recursive walks raise
on a denial. The question survives, as a kernel-level listing option rather
than a `LocalBackend` parameter.

## Related

- **BUG-311:** `glob`, the same silent drop through `Path.glob`.
- **BUG-313:** `get_file_info`, the path predicates, the `read` / `delete`
  pre-checks, `delete_folder` and `check_health`. Its `delete_folder` cell
  (`missing_ok=True` returning cleanly with the folder still on disk, on 3.14)
  is the most urgent one.
- Both are the same classification problem, and step 5's one `classify` is
  where they converge.
