# BK-396 — The kernel's `delete_folder` sequence around `SupportsRemoveFolder` is undecided
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Split out of BK-389's decision 8 in PR #1056, at
the maintainer's direction, after nine review rounds. Every round from 1 to 9
found a new defect in the `delete_folder` sequence, each in a case the
previous fix had not reached: atomicity, the error-path trigger, `implicit`
drivers, the `parents == "none"` path, the `delete_tree` refusal, and a
`delete_tree` that deletes a file. Rounds 1 to 5 are counted by `hatch run
ship-report 1056`; rounds 6 to 9 are PR #1056's verification reviews. What held
from round 5 on stays in BK-389's decision 8: the protocol, its atomic
removal, and who carries it. The sequence the kernel runs around it was
decided here (§ Outcome below), against fake drivers, before BK-389's kernel
PR writes the spec 003 clause (its item 8) and the cells that trace to it;
BK-389 depended on this item until it closed. Filed as ID-264 until PR #1056's round 10, so that PR's review
threads use that name.

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

## Outcome (2026-10-02)

All five items are decided, plus one finding the measurement surfaced and
three that review surfaced (items 7 to 9 below), each
by the maintainer through the interview with the measured cells in front of
them. The sequence now lives in
[BK-389's decision 8](bk-389-kernel-step-1-memory.md#decisions-planning-pr-2026-10-02),
together with the changed cells and the step that lists each. This section
records what each choice was weighed against. The derivation is
`sdd/rfcs/rfc-0017-delete-folder-measure.py`, whose docstring gives the run
order and its bounds. It runs today's classes (Memory, Local, SFTP on the
in-process paramiko server, S3Boto3 on moto, SQLBlob on sqlite, flat Azure on
Azurite 3.37.0) and a model of the kernel over fake drivers, with one option
switch per item. HNS and Graph have no emulator, so they were read, and the
model covers their wire.

1. **Probe set: a typed `NotFound` or an untyped refusal only.** The
   candidate's set (any refusal but a typed `DirectoryNotEmpty`) changed 12
   of the 30 injected non-state fault cells (`compare faults`):
   `PermissionDenied` or `BackendUnavailable` on a non-empty folder became
   `DirectoryNotEmpty`, and an SFTP `rmdir` that landed before the channel
   died answered `NotFound`, or returned under `missing_ok`. The decided set
   changed none of them. Its cost falls on the driver: Local's
   `delete_folder` handler, which types every non-`ENOTEMPTY` error
   `PermissionDenied`, changed 22 Local cells under it, so the driver must
   classify by errno.
2. **`delete_tree` refuses a file or an absent key, removing nothing.** With
   no rule, a naive Memory `delete_tree` deleted file `f` and answered
   success (2 of 24 cells), and so did the modelled Graph and HNS wires. A
   kernel `stat` before `delete_tree` also kept all 24 Memory cells, but it
   splits Memory's one-lock delete into two primitives and still leaves
   Graph's and HNS's race. The contract, mirroring `remove_folder`'s, was
   chosen.
3. **The walk tolerates a `NotFound` on the way.** With one concurrent
   deleter injected (`d/a` gone before its `delete`, `d/e1` before its
   `remove_folder`), the candidate's full table answered `NotFound` and left
   `d/e0/b` and `d/e1/c` undeleted. The decided walk answered success with an
   empty tree (`compare races`). Today's answer under a concurrent deleter
   was not measured: an unsynchronised deleter thread removes its files
   before the walk lists them as often as during it, so its tally could not
   show tolerance mid-walk, and `race` runs the writer only.
4. **A recursive delete may answer `DirectoryNotEmpty`** under a concurrent
   writer on a walk. Today, in 200 threaded runs each (`race 200`), Local
   answered it in 187 in the latest run (success in 13; the race's hit
   rate varies from run to run), and SFTP
   answered an untyped `RemoteStoreError` in all 200. The alternative, a
   kernel that re-walks up to three passes, succeeded only by deleting the
   writer's new file, and under a persistent writer ended in
   `BackendUnavailable`.
5. **The `parents == "none"` table is confirmed.** It matched all 60 base
   cells and every S3Boto3 and flat Azure fault cell. SQLBlob's raising-`stat`
   cells, which the candidate counted as one, are 8: two key states ×
   `recursive` × `missing_ok`.
6. **New: `delete_folder` never treats a link as a folder.** A Local driver whose `stat`
   and `list_page` follow links deleted `tn/a` through `sn -> tn` on a
   recursive delete, where `rmtree` refuses today. With `lstat` semantics,
   nothing was deleted through a link, and the 12 Local symlink cells became
   `InvalidPath`. That corrects the candidate's symlink paragraph below,
   which simulated the rule by hand: with today's classifier its
   non-recursive cells reproduce (`compare local`, `Lt P0`), but its
   recursive walk through `sn` also deleted `tn/a`, which the paragraph
   does not show. Under the decided rule every cell with a link at the key
   is `InvalidPath`, and a link nested below the key is deleted as a file,
   its target kept, as today (`compare summary`, 12 of 44 Local cells
   changed). The rule binds `delete_folder` only: `stat` and `list_page`
   take `follow_links`, and only `delete_folder` passes `False`, so no
   other operation's cell changes (today's link-following members:
   `_local.py` lines 183, 585 and 604). The maintainer chose that scope,
   and then that flag over a link marker on `Entry`, which could not
   represent a dangling link, the key's own listing or a common prefix.

PR #1057's round 1 found two cases the six left open, and the maintainer
decided both on measured cells (`compare extra`):

7. **A probe that raises leaves the refusal standing, and `missing_ok`
   applies to a `NotFound` one** (BE-021's fail-open rule, as the `none`
   path already applied it). As first written, the refusal was raised even
   under `missing_ok=True`, against BE-013. Raising the probe's own error
   instead would have kept SFTP's 8 cells, which answer
   `BackendUnavailable` today, but contradicted BE-021.
8. **A `parents == "none"` recursive delete without `SupportsDeleteTree`
   tolerates a `NotFound` on a listed file**, as the walk does. Today flat
   Azure answers `NotFound` under a concurrent deleter, even with
   `missing_ok=True`, and leaves the rest of the prefix in place.

Item 7's condition, a refusal the probes do not replace, was refuted again on
a raising listing and on the walk's probes, so it was enumerated (the
repeat-site check):

9. **One rule for a refusal the probes do not replace.** The space is three
   contexts × refusal × `stat` × listing × `missing_ok`, 64 cells
   (`compare enum`, which prints both rules side by side). Under item 7's
   narrower rule, 3 cells raise `NotFound` to a `missing_ok=True` caller
   (the refusal says absent and the `stat` finds a folder), and 4 walk
   cells fail the whole delete: an untyped refusal on an entry already gone
   answers `NotFound`, and one on an entry still a file answers
   `InvalidPath`. The maintainer chose one rule: the refusal stands,
   `missing_ok` applying to a `NotFound`, and on the walk an absent outcome
   is tolerated and a file delete keeps its own refusal. It changes those 7
   cells and no other, and every other figure here re-runs unchanged. The
   alternative weighed was to raise a refuted `NotFound` as untyped.

## Candidate design

Condensed from BK-389's decision 8 at PR #1056's head `40151bc`, plus round
9's measurements; the original text is `git show
40151bc61:sdd/backlog/bk-389-kernel-step-1-memory.md`. It is the starting
point, not a decision: items 1 to 4 of § What it decides refute parts of
it, and wherever this text and § Outcome differ (items 1 to 9 there,
including the symlink paragraph's "one changed cell", the raising-probe
sentence and SQLBlob's one cell), the Outcome stands.

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
  `DirectoryNotEmpty` under the probe, the one changed cell, for step 5 to
  list. A permission-denied folder was not
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
  through the error-path table's probes (§ What it decides, item 3). Measured in round
  7 with Memory and Local as stand-ins: 28 cells match today.
- **`delete_folder(recursive=True)` with `SupportsDeleteTree`, folder
  objects present.** A `delete_tree` refusal gets the `stat` probe only,
  never the listing: absent `NotFound`, to which `missing_ok` applies, file
  `InvalidPath`, otherwise the driver's error stands, a raising probe
  chained to it (§ What it decides, items 2 and 4). The reason: a recursive delete never
  answers `DirectoryNotEmpty` (BE-013), and a folder whose tree delete
  failed is non-empty almost by definition, so the listing arm would turn
  Local's `PermissionDenied` (`_local.py` line 510) or an HNS 403 into
  `DirectoryNotEmpty`. Memory and Local reproduce today's answers under it (20 cells,
  round 9).
