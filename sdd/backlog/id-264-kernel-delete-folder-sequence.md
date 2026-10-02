# ID-264 — The kernel's `delete_folder` sequence around `SupportsRemoveFolder` is undecided
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Split out of BK-389's decision 8 in PR #1056, at
the maintainer's direction, after nine review rounds. Every round from 2 to 9
found a new defect in the `delete_folder` sequence, each in a case the
previous fix had not reached: atomicity, the error-path trigger, `implicit`
drivers, the `parents == "none"` path, the `delete_tree` refusal, and a
`delete_tree` that deletes a file. Rounds 1 to 5 are counted by `hatch run
ship-report 1056`; rounds 6 to 9 are PR #1056's verification reviews. What held
from round 5 on stays in BK-389's decision 8: the protocol, its atomic
removal, and who carries it. The sequence the kernel runs around it is
decided here, against fake drivers, before BK-389's kernel PR writes the
spec 003 clause (its item 8) and the cells that trace to it. BK-389 depends
on this item.

## What it decides

1. **Which refusals the kernel probes.** The candidate below probes after
   any refusal but a typed `DirectoryNotEmpty`. That set includes a typed
   `BackendUnavailable`, and probably a credential
   `PermissionDenied`, which say nothing about the key's state. On SFTP the
   probe's `stat` reconnects after a dead channel (`_sftp.py` lines 3273 to
   3284, SFTP-010), so an `rmdir` that landed before the drop answers
   `NotFound`, or silent success under `missing_ok`, where today it answers
   `BackendUnavailable`; an unreachable host pays a second timeout. RFC-0017
   D2's general flow probes only after `NotFound`.
2. **What `delete_tree` must refuse.** The candidate probes only after a
   `delete_tree` refusal, but D1's `SupportsDeleteTree` row does not oblige
   `delete_tree` to refuse a file or an absent key. Round 9 read that Graph's
   `DELETE /items/{path}` and Azure HNS `delete_directory`
   (`self._delete(recursive=True)`, installed SDK,
   `aio/_data_lake_directory_client_async.py` line 304) delete a file item.
   Today both classes check the type first and answer `InvalidPath`: Graph
   at `aio/backends/_graph/backend.py` lines 1331 to 1337, HNS through
   `hdi_isfolder` (BUG-198) at `aio/backends/_azure.py` lines 963 to 965.
   Without a contract or a kernel pre-check, steps 4 and 7 would delete the
   file and answer success: data loss and a BE-013 violation. Not
   reproduced against a live wire.
3. **What the folder-objects recursive walk answers when a `remove_folder`
   on the way refuses.** The candidate sends it through the full error-path
   table, whose listing arm, and a typed `DirectoryNotEmpty` passing
   through, can make a recursive delete answer `DirectoryNotEmpty` under a
   concurrent writer.
4. **Whether a recursive delete may answer `DirectoryNotEmpty`.** The
   candidate says it never does (BE-013). Round 9 measured that false for
   Local today: `shutil.rmtree` runs inside the same `except OSError`
   handler as `rmdir` (`_local.py` lines 500 to 510), and with a concurrent
   writer under `d/e0`, `delete_folder("d", recursive=True)` answered
   `DirectoryNotEmpty` in 198 of 200 runs. BE-013 lists `DirectoryNotEmpty`
   only for `recursive=False`; it does not forbid it on a recursive call.
5. **Confirm or amend the candidate's `parents == "none"` table**, the part
   with the most measurement behind it (below).

**Exit criteria:** each of the five is decided and written into BK-389's
decision 8 and RFC-0017 D1's `SupportsRemoveFolder` row; every cell is
measured against today's answer on the driver classes the steps migrate
(Memory, Local, SFTP, S3Boto3, SQLBlob, async Azure flat and HNS, Graph),
or marked read-only with its reason; each changed cell names the step that
lists it; RFC-0017 D2's probe bullet, flowchart, § Impact Performance and
Testing agree.

## Candidate design, as it stood at PR #1056's head `40151bc`

Moved verbatim from BK-389's decision 8, with the measurements. It is the
starting point, not a decision: items 1 to 4 above refute parts of it.

- **The error path, enumerated.** After any refusal **except a typed
  `DirectoryNotEmpty`**, the kernel runs the error-path probes: one `stat`,
  then, for a folder still present, one `list_page(key, delimiter="/",
  limit=1)`. The probe's answer replaces the driver's: absent `NotFound`,
  file `InvalidPath`, non-empty folder `DirectoryNotEmpty`, else the
  driver's error stands. A probe that itself raises answers nothing: the
  driver's refusal is raised, with the probe's exception chained as its
  context (maintainer's decision in round 5). A typed `NotFound` is probed
  too, as RFC-0017 D2's flow does, because SFTP's wire types a file as
  `NotFound` (Local's `delete_folder` classifier types it
  `PermissionDenied`). `missing_ok` applies to the final `NotFound`. Only
  the probed answer can race, never the removal. The driver columns are
  what `rmdir` gives through the classifier each driver's `delete_folder`
  uses today: Local's handler maps `ENOTEMPTY` (or 145) to
  `DirectoryNotEmpty` and every other `OSError` to `PermissionDenied`
  (`_local.py` lines 505 to 510); SFTP's `_map_exception` maps
  `FileNotFoundError` to `NotFound` (`_sftp.py` line 3271) and an
  errno-less failure to an untyped `RemoteStoreError` (run in round 4). The
  last column is today's answer, measured for Local and Memory in rounds 3
  and 4, read for SFTP (`_sftp.py` lines 1358 to 1388):

  | Key state | Memory `remove_folder` | Local `rmdir` → `classify` | SFTP v3 `rmdir` → `classify` | Kernel | Answer |
  |---|---|---|---|---|---|
  | empty folder | removed | removed | removed | — | removed |
  | folder holding files | `DirectoryNotEmpty` | `ENOTEMPTY` → `DirectoryNotEmpty` | errno-less failure, untyped | probe on SFTP only: `stat` folder, `list_page` non-empty | `DirectoryNotEmpty` |
  | folder holding only an empty folder | `DirectoryNotEmpty` | `ENOTEMPTY` → `DirectoryNotEmpty` | errno-less failure, untyped | probe on SFTP only; `delimiter="/"` sees the subfolder | `DirectoryNotEmpty` |
  | file `f` | `InvalidPath` | `ENOTDIR` → `PermissionDenied` | `ENOENT` → `NotFound` | probe: `stat` file | `InvalidPath` |
  | key under a file `f/x` | `NotFound` | `ENOTDIR` → `PermissionDenied` | `ENOENT` → `NotFound` | probe: `stat` absent | `NotFound` |
  | absent | `NotFound` | `ENOENT` → `PermissionDenied` | `ENOENT` → `NotFound` | probe: `stat` absent | `NotFound` |

  Local's symlinks, measured in round 4 (`os.rmdir` gives `ENOTDIR` on
  each; the rule simulated by hand): a dangling symlink, a symlink to a file
  and a symlink to an empty directory keep today's answers; a symlink to a
  non-empty directory answers `PermissionDenied` today and
  `DirectoryNotEmpty` under the probe. A permission-denied folder was not
  measured (the container runs as uid 0).
- **`parents == "none"`, enumerated.** No folder objects, so `remove_folder`
  is never called. The kernel lists first and `stat`s only when the listing
  is empty, the order the flat classes use today: `S3Boto3Backend`
  (`_s3_boto3.py` lines 615 to 622), `SQLBlobBackend` (`_sqlalchemy.py`
  lines 967 to 978) and flat `AsyncAzureBackend` (`aio/backends/_azure.py`
  lines 978 to 988). The listing is `list_page(key, delimiter="/", limit=1)`
  for a non-recursive call; for a recursive one, `list_page(key,
  delimiter=None, limit=1)` before `delete_tree`, or, without
  `SupportsDeleteTree`, one paged `list_page(key, delimiter=None)` whose
  files the kernel deletes. On an empty listing, `stat`: a file answers
  `InvalidPath`, anything else `NotFound`, to which `missing_ok` applies.
  Spec 003 BE-021 (lines 751 to 778) fixes how a raise is answered: the
  listing is the determinant and fails closed; the `stat` after an empty
  listing fails open, so the empty listing's `NotFound` stands. Today
  `S3Boto3Backend` and flat `AsyncAzureBackend` answer that way (S3Boto3
  measured under moto in rounds 8 and 9, 403 and 503, 32 cells; Azure's
  `_flat_is_blob`, `aio/backends/_azure.py` lines 244 to 252, read);
  `SQLBlobBackend._reject_file` propagates the raise (measured in round 9,
  16 cells), so step 3 lists that one cell.

  | Key state | non-recursive | recursive (`delete_tree`, or the listed files) |
  |---|---|---|
  | files under the prefix | `DirectoryNotEmpty` | removed |
  | file `f`, nothing under it | `InvalidPath` | `InvalidPath` |
  | a file and a prefix both | `DirectoryNotEmpty` | the files under it removed, the file kept |
  | absent, or under a file (`f/x`) | `NotFound` | `NotFound` |

  Every cell is today's answer on SQLBlob (`sqlite://`, 24 cells measured
  in round 8, answers and post-state) and on the two other classes
  (S3Boto3's call counts measured under moto in round 8, every path
  including `delete_tree`; Azure read).
- **`delete_folder(recursive=False)`, folder objects present.** The kernel
  calls `remove_folder` with no probe before it, so no check is split from
  the removal, and probes after a refusal as the error-path table states.
  SFTP's `stat`, `listdir`, `rmdir` sequence today (`_sftp.py` lines 1358
  to 1388) becomes `rmdir` with this probe at step 6.
- **`delete_folder(recursive=True)` without `SupportsDeleteTree`, folder
  objects present.** The kernel walks the subtree with `list_page(prefix,
  delimiter="/")`, so a folder holding no files still arrives as a common
  prefix, deletes the files, then calls `remove_folder` on each folder,
  deepest first; the last call, on `key`, answers an absent key or a file
  through the error-path table's probes (item 3 above). Measured in round
  7 with Memory and Local as stand-ins: 28 cells match today.
- **`delete_folder(recursive=True)` with `SupportsDeleteTree`, folder
  objects present.** A `delete_tree` refusal gets the `stat` probe only,
  never the listing: absent `NotFound`, file `InvalidPath`, otherwise the
  driver's error stands, a raising probe leaving it standing (items 2 and 4
  above). Memory and Local reproduce today's answers under it (20 cells,
  round 9).
