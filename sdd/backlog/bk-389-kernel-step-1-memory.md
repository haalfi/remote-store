# BK-389 — RFC-0017's kernel does not exist, so no backend can migrate onto it
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Minted by BK-387 as all of RFC-0017 D3 step 1. The
maintainer's condition on
[ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md): it stays
Proposed until the first backend runs on the new design, and it is accepted in
that PR.

**Split (2026-10-02, planning PR).** Step 1 ships as two PRs, in this order.
Nothing had shipped at the split, so it is not yet
[§ Completing work](../BACKLOG.md#how-this-file-works)'s "partly done": the
remainder is minted ahead of the close, and the kernel PR closes this item
as `[x]` with BK-394 as that remainder. This item keeps the **kernel PR**, which runs
under the Proposed ADR. **BK-394** ([dossier](bk-394-memory-drivers-accept-adr-0042.md))
is the **Memory PR**: the two Memory drivers, every step-1 spec amendment but
the spec 003 clauses the kernel's cells trace to (item 8 below), the
guide, its check script and the homepage snippet, and ADR-0042 and RFC-0017
set to Accepted. "That PR" in the paragraph above is BK-394's. **Both PRs
merge only after the v0.33.0 tag.** Items 2 (the Memory half), 4, 5, 6 and 7
of the original list moved verbatim to BK-394's dossier, where additions made
at the split are marked as such there; the numbering below
is the original's, so a gap is a moved item.

## Decisions (planning PR, 2026-10-02)

Each taken by the maintainer through the interview, the recommended option in
every case. RFC-0017 carries the same answers at the question each settles.

1. **Open Question 2, `Page`: decided.** A `Page` is whatever one `list_page`
   call returns. A driver whose wire has no page boundary returns its native
   unit (one directory read, one response) as one `Page`, possibly empty. The
   kernel keys BE-021's first-page bound on the first `Page` received by the
   **operation**, across every `list_page` call a walk makes, never per call.
   No flag on `Page` or `Driver`. The step-1 public shape of `Page` is final:
   entries, common prefixes, next cursor. BUG-257's shape (a bound restarted
   per request) cannot be expressed against this kernel; Graph meets it at
   step 7, or BUG-257 is fixed in place earlier per its dossier.
2. **Open Question 3, flags: step 1 builds to them.** One kernel with
   `namespace` and `parents` as values. Both Memory drivers are
   `hierarchical` and `explicit`, so step 1 exercises one combination; the
   two-kernel fallback can be judged no earlier than the first flat driver
   (step 2, S3).
3. **Open Question 5, construction: deferred to step 3 (BUG-245).** The shape
   step 1 keeps open: the kernel's constructor takes a **built** driver,
   `DriverBackend(driver, *, reject_write_under_file_ancestor=False)` and its
   async twin; each public class builds its driver in its own `__init__`.
   Step 3 may add a wrapped-build form (a classmethod or factory run inside
   the choke point) beside it, never instead of it. Memory's constructor
   cannot fail, so step 1 maps nothing at construction.
4. **Close posture: the driver declares it.** `close_is_terminal: bool` is a
   `Driver` and `AsyncDriver` attribute, a sixth beside D1's five. The
   kernel's closed guard (BE-020) runs only when it is `True`, ahead of the
   root check as BK-388 ranks them. Both Memory drivers declare `False`,
   matching `MemoryBackend.dfy`'s `closeIsTerminal := false`.
5. **The kernel is private in this PR.** It lands in underscore modules,
   unexported from `__all__`, with no API reference page, guide or CHANGELOG
   entry. Its fake-driver suite traces to existing spec IDs, and to the spec
   003 clauses item 8 below adds for the cells no ID covers yet [corrected
   after PR #1055 merged: as merged this said existing IDs only]. BK-394 exports
   the public names RFC-0017 § Impact lists, `Session` excepted (it lands at
   step 2, D5), together with the specs that describe them.
6. **Key validation, normalisation and the root are the kernel's.** Round 1
   of this planning PR's review found the Memory placement table putting key
   validation in the driver, against D1: a driver "carries no path, root,
   type, closed or mapping logic".
   Rounds 2 to 4 refuted three prose statements of this rule in turn, so the
   rule is the table below and nothing else. It covers the **operations**,
   and, since BK-395, the addressing members, a key holding a backslash and
   `glob`: those three touched existing clauses (BE-025, NPR-021/NPR-004,
   RES-020, PATH-002), so the maintainer placed them in BK-395, which decided
   them on 2026-10-03. See **Decided in BK-395** below, which also states
   `glob`'s rule, the one part outside the table, since a pattern is not a
   key class.

   **Pipeline, per operation.** (1) The closed guard, when the driver declares
   `close_is_terminal`. (2) Refusals, `InvalidPath`: a key starting with `/`, a `..`
   segment, a null byte, a backslash (the last added by BK-395). (3) Normalisation: empty and `.` segments are
   dropped, so `//`, `/./` and a trailing `/` fold and every root spelling
   becomes `""`. (4) The root check on
   the canonical key, where `""` is the root. (5) The driver, with the
   canonical key. For a write, the kernel builds the result's path from that
   key before the driver commits, so no key the kernel accepts can fail
   after the bytes land. That is the shape of BUG-299 and of BK-395's absorbed
   BUG-297, which both write first and then raise. For a key that passes (2), a canonical `""` is exactly
   `AddressesRoot` of the raw key (`BackendContract.dfy` §5c: every segment
   `""` or `"."`). The `/`-led spellings it also accepts (`"/"`, `"/./"`) are
   refused at (2) with the same `InvalidPath`. So the write side and the
   `move`/`copy` destination get the wide predicate BE-029 requires, and the
   read side and the source get it too, which spec 003 permits under BE-008
   ("the floor is `is_root` and a backend MAY exceed it").

   **The table.** Rows are key classes and columns are member groups. A cell
   is the kernel's answer; **Δ** marks a cell where both Memory classes
   answer differently today. The backslash row and the addressing column are
   BK-395's.

   | Key class (examples) | Probes: `exists`, `is_file`, `is_folder` | File-shaped: `read`, `read_bytes`, `read_seekable`, `get_file_info`, `delete`, `move`/`copy` source | Write-shaped: `write`, `write_atomic`, `open_atomic`, `move`/`copy` destination | Folder-shaped: `list_files`, `list_folders`, `iter_children`, `get_folder_info` | `delete_folder` | Addressing: `native_path`, `resolve` |
   |---|---|---|---|---|---|---|
   | root (`""`, `"."`, `"./"`, `".//"`, `"./."`) | the root's answer (BE-029) | `InvalidPath` | `InvalidPath` (BE-029) | the root folder; **Δ** `get_folder_info` on `"./"`, `".//"`, `"./."`, which raises `InvalidPath` today | `InvalidPath`, refused by the kernel, never reaching `delete_tree` or the list-then-delete synthesis | the driver's answer for `""`, the bare root; **Δ** on `"./"`, `".//"`, `"./."`, echoed raw today |
   | `/`-led (`"/"`, `"/./"`, `"/f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | `..` segment (`"d/../f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | null byte | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | backslash (`"d\\f"`, `"e\\g"`, `"\\"`) | `InvalidPath`; **Δ**, `True` or `False` today | `InvalidPath`; **Δ**, served from the stored key, or `NotFound`, today | `InvalidPath`; **Δ**, `write("d\\f")` and `move("f", "\\")` store today, and `write("\\")` stores then raises | `InvalidPath`; **Δ**, `"e\\g"` listed and aggregated, `"\\"` empty or `NotFound`, today | `InvalidPath`; **Δ**, `"e\\g"` removed and `"\\"` `NotFound` today | the raw key passed to the driver |
   | non-canonical (`"d//f"`, `"d/./f"`, `"d/"`) | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer; **Δ**, echoed raw today |
   | canonical, no backslash (`"f"`, `"d/f"`) | passed through | passed through | passed through | passed through | passed through | passed through |

   **Derivation of the Δ column.** Both Memory classes were run on a store
   holding `f` and `d/f` over 17 keys: the 15 `""`, `"."`, `"./"`, `".//"`,
   `"./."`, `"/"`, `"/./"`, `"/f"`, `"d/../f"`, `"f\0"`, `"d\\f"`, `"d//f"`,
   `"d/./f"`, `"d/"`, `"f"`, plus `"d/f"` and `"d"` to check the
   non-canonical row against. The sync class was run through `exists`, `is_file`, `is_folder`,
   `read_bytes`, `get_file_info`, `write`, `delete`, `delete_folder`,
   `list_files(recursive=True)`, `get_folder_info`, `move` as source and as
   destination, `native_path` and `to_key`. The async class was run through the same set
   less `is_file`, `get_file_info` and `to_key`, and the two classes agree on
   every shared cell. Every measured operation cell for a backslash-free key
   outside the Δ marks matches the table. The addressing column and the
   backslash row were measured by BK-395, whose dossier's § Outcome gives
   the recipe; every cell of both outside the Δ marks matches the table.
   Round 5's measuring reviewer then ran `list_folders`, `iter_children`,
   `read`, `read_seekable`, `write_atomic`, `open_atomic` and `copy` the same
   way and found no unmarked difference. **What the Δ cells reach:** no
   conformance cell, since the read-side root cells use only `""` and `"."`.
   `Store` normalises its own inputs, so the Δ is visible only to a caller
   holding a backend directly. BK-394 lists it as a step-1 Memory cell change,
   with BK-395's addressing and backslash Δ cells, which are also invisible
   through `Store`: it hands the backend a `RemotePath`-normalised key, so
   never a backslash nor a non-canonical spelling.

   **Later drivers.** RFC-0017 D3's enumerated cell changes now include this
   table. Each step's PR lists **every** cell of it where its driver answers
   differently today, canonical keys included. For example,
   `LocalBackend.delete_folder("", recursive=True)` removes the root
   directory itself today. That was measured on a temp root in this PR's
   verification round, and `"."` does the same. The table refuses it. No
   test pins that answer on a present root: the two root `delete_folder`
   tests in `tests/backends/local/test_absent_root.py` run on its `backend`
   fixture, which removes the root first, so they pin the absent-root cells
   [corrected after PR #1055 merged: as merged this called the present-root
   answer pinned]. Step 5 therefore adds a present-root cell, and inverts
   every absent-root root `delete_folder` pin, since the table's
   `InvalidPath` comes before the driver, so neither an absent container
   nor `missing_ok` reaches it:
   `test_folder_shaped_operations_still_accept_the_root` (`None` under
   `missing_ok=True`, `""` and `"."`) and
   `test_strict_delete_folder_on_the_root_answers_from_the_filesystem`
   (`NotFound`, `""` and `"."`, recursive and not) all become `InvalidPath`.
   Item 8's spec 003 root clause ends the rationale three texts give, so
   step 5 rewrites all three: the second test's docstring ("a call no spec
   decides"), the first test's docstring (`test_absent_root.py` lines 312
   to 316, "`delete_folder` and `get_folder_info` … legitimately take the
   root", still true of `get_folder_info`), and `LocalBackend.delete_folder`'s
   own docstring (`_local.py` lines 477 to 484, "the root rule does not
   reach a folder *delete*"; listed in PR #1056's round 9). `SFTPBackend` likely answers
   the same: its `_sftp_path` maps the root to `base_path` and its `_rmtree`
   ends in `rmdir` (read from `_sftp.py`, not run). A flat wire's `"d//f"` or
   `"./"` are further examples. BK-395's parts add these, measured at master
   `57d0797` by its dossier's recipe: `LocalBackend.native_path` echoes
   `"./"`, `".//"`, `"./."`, `"d//f"`, `"d/./f"` and `"d/"` under the root
   (`<root>/./` and so on), step 5; `LocalBackend.glob` raises an untyped
   `NotImplementedError` for `"/d/*.csv"` and `ValueError` for `""` and
   `"."`, and answers `[]` for `"../*.csv"`, `"d\\*.csv"` and `"d/*\0"`;
   the kernel answers `InvalidPath` for the four refused patterns and
   nothing for `""` and `"."`, step 5;
   `SQLBlobBackend.glob`, on a store holding no backslash key, answers `[]`
   for `"./d/*.csv"`, `"d//*.csv"` and `"d/./*.csv"`, where the kernel
   matches `d/a.csv`, and `[]` for every refused pattern, where the kernel
   answers `InvalidPath`, step 3. Step 3 also inverts two SQL-BLOB-061 cells
   in `tests/backends/sqlblob/test_like_prefix.py` to `InvalidPath`: the
   `a\b` seed, which writes a backslash key directly, and the
   `backslash_in_tail` glob cell, which matches `"*\\b/s.txt"` against it.
   Not run, so each step measures its own addressing and backslash cells,
   and its `glob` cells where it declares `GLOB`: SQLBlob's operations and
   addressing and all of `SQLQueryBackend`, which declares `GLOB`
   (`_QUERY_CAPABILITIES`), step 3; `S3Boto3Backend` (`GLOB`), step 2;
   `AsyncAzureBackend` (`GLOB`), step 4; `SFTPBackend`, step 6;
   `GraphBackend`, step 7; `ReadOnlyHttpBackend`, step 8. This decision
   adds nothing else to D3's list.

   **Decided in BK-395** (2026-10-03, the maintainer through the interview,
   the recommended option each time; measurements and recipe in its
   [dossier](bk-395-kernel-key-rule-addressing.md) § Outcome):
   - **Addressing stays total.** `native_path(key)` and `resolve(key)` run no
     closed guard (BE-029's named carve-out) and never raise for the key. A
     key passing step (2) is normalised by step (3) and the driver receives
     the canonical key, so every root spelling reaches it as `""`. A key
     step (2) refuses reaches the driver **raw**, which keeps BE-025's
     verbatim round trip for `..` and null bytes. `resolve` returns the
     driver's plan with `key` replaced by the caller's key, so RES-020's
     `plan.key == path` holds and `resolve(".").key` stays `"."`; its
     `native_path` is the kernel's `native_path(key)`, so RES-025 holds.
     `to_key` is forwarded unchanged: its input is a native path, not a key,
     and NPR-005 makes it stripping, not validation.
   - **A backslash is refused** at step (2), on every operation. That keeps
     the driver's domain inside `BackendContract.dfy` §5a's
     `WellFormedPath`, which excludes `\`. Folding it as PATH-002 does would
     make `d\f` collide with `d/f` on a driver that stores both, as Memory
     does, which is BE-029's withdrawn fold. `"\\"` is refused as a
     backslash key, not as the root, so `RootPath.dfy`'s
     `BackslashIsNotRoot` is unaffected. Addressing passes it raw, so the
     refusal widens no addressing predicate, the condition BE-029 sets for a
     backend refusing it. This also settles BUG-297's key: `write("\\")`
     never reaches the driver.
   - **`glob(pattern)` takes the pipeline segment-wise over the whole
     pattern.** Order: the closed guard, then the capability (a driver
     without `SupportsGlob` declares no `GLOB`, so `CapabilityNotSupported`
     as BE-024 states), then step (2)'s refusals over the whole pattern (a
     leading `/`, a `..` segment, a null byte, a backslash), then step (3)'s
     dropping of empty and `.` segments anywhere in it, wildcard characters
     untouched inside their segments, then the driver with the canonical
     pattern. GLOB-012's literal prefix is therefore cut from an already
     canonical pattern. A pattern that normalises to `""` names the root, a
     folder, and yields nothing (GLOB-017). Unlike a key, a pattern reaches
     the backend from `Store.glob` without `RemotePath`, so these cells are
     visible through `Store` once a `GLOB` driver migrates. No step-1 cell:
     neither Memory class declares `GLOB`.

   **Clauses checked, none contradicted.** BE-025 permits `native_path` to
   normalise and requires totality and the verbatim round trip of `..` and
   null bytes, all kept; NPR-004 and NPR-021 require totality; RES-020 and
   RES-025 hold as stated above; PATH-002 binds `RemotePath`, which `Store`
   applies before the backend, so the refusal reaches only a caller holding a
   backend directly. Spec 003 gains clauses rather than losing any (item 8).

   **Not `RemotePath`'s rules, nor `LocalBackend._resolve()`'s.** The
   refusals and normalisation are spec 013's MEM-DS-005 table, which both
   Memory classes implement today, plus BK-395's backslash refusal, which
   neither does, and this item's PR restates them as a
   spec 003 clause (item 8 below; moved from BK-394 after PR #1055 merged). A comparison at master `9caef6b` shows
   where the other two rules differ from it:
   - `RemotePath` folds `"/a/b"` to `a/b`, converts the backslash in
     `"a\\b"` to `/`, and raises on every root spelling.
   - `_resolve` accepts a `..` that stays inside the root (`"a/../b"` to
     `b`) and a null byte.

   Step 5, which migrates Local, therefore enumerates the `..` and null-byte
   cells for direct `LocalBackend` callers.
7. **A recursive listing is one `delimiter=None` request** (decided in round
   2 of this planning PR's review). For `list_files(recursive=True)` and an
   aggregation without `SupportsFolderStats`, the kernel calls
   `list_page(prefix, delimiter=None)` and follows the cursor, whatever the
   driver's `namespace`. A hierarchical wire's driver walks behind the cursor,
   one `Page` per wire request, so decision 1's per-operation bound sees every
   page. The kernel applies `max_depth` (DEPTH-003) to what comes back, so a
   hierarchical remote driver may read below the depth; a depth hint to the
   driver is revisited when Local or SFTP migrates (steps 5, 6). Memory
   answers in one locked `Page`, which keeps spec 013's MEM-025 snapshot.
8. **Removing one empty folder is a protocol, `SupportsRemoveFolder`,
   required when `parents` is `"explicit"` or `"implicit"`.** (A protocol
   in D1's sense: its presence is detected per class.) Decided after this planning PR's verification
   round, which found that D1 had no primitive for it. That leaves spec
   013's non-recursive `delete_folder`, and Local's and SFTP's later, with
   nothing to call. The protocol has one member, `remove_folder(key)`.
   [Corrected after PR #1055 merged, from its closing-pass review; maintainer
   decisions taken through the interview. As merged, the kernel checked
   emptiness itself with `list_page(key, limit=1)`, which split Memory's
   one-lock check-and-detach (MEM-026, `_memory.py` lines 316 to 336) into
   three driver calls, left the probe's `delimiter` open, and excluded the
   `implicit` drivers that remove an empty folder today.]
   - **The removal is atomic.**
     `remove_folder(key)` removes an empty folder and refuses anything else
     without removing it, in one step: Memory under its lock, which is where
     all four checks and the detach run today (MEM-026), and Local's and
     SFTP's `rmdir`, which refuse a non-empty folder and a file natively
     (measured for Local in PR #1056's round 3: `os.rmdir` removed no file,
     non-empty directory or symlink).
   - **The `delete_folder` sequence around it.** [Split out in PR #1056
     at the maintainer's direction, after every review round from 1 to 9
     found a new defect in it. Decided in BK-396 on 2026-10-02, each
     choice the maintainer's through the interview.] Measured against
     today's classes by `sdd/rfcs/rfc-0017-delete-folder-measure.py`, whose
     docstring gives the run order and its bounds. The **Changed cells**
     list below is its `compare summary` output; every other figure names
     its own `compare` section inline. BK-396's
     [dossier](bk-396-kernel-delete-folder-sequence.md) holds the candidate
     this replaces and the options the interview weighed.
     - *Which refusals are probed.* Only a typed `NotFound` and an untyped
       `RemoteStoreError` get the error-path probes: one `stat`, then, for
       a folder still present, one `list_page(key, delimiter="/",
       limit=1)` where the call can answer `DirectoryNotEmpty`. The probes
       replace the refusal with the key's state: absent `NotFound` (to
       which `missing_ok` applies), file `InvalidPath`, non-empty folder
       `DirectoryNotEmpty`. **When they do not replace it**, because a
       probe raised (its exception chained) or the probes found a folder
       they cannot type further, the refusal stands, and `missing_ok`
       applies to it when it is a `NotFound`: the refusal is the call's
       linearisation point, and this is BE-021's fail-open rule, which the
       `parents == "none"` path below also follows. Since Local's and
       SFTP's drivers type a file as `NotFound`, a file under `missing_ok`
       on either returns quietly when the `stat` probe cannot run. [Added
       in PR #1057's rounds 1 and 2, the maintainer's decisions; the
       condition's space, four contexts (`remove_folder`, `delete_tree`,
       and the walk's `delete` and `remove_folder`) × refusal × `stat` ×
       listing × `missing_ok`, is enumerated by `compare enum`, 88 cells.]
       Every other typed refusal passes through unprobed, since a
       `BackendUnavailable` or a `PermissionDenied` says nothing about the
       key. Measured on 30 injected non-state faults (`PermissionDenied` on
       Local and SFTP, and SFTP's dead channel before and after a landed
       `rmdir`, `compare faults`): the kernel answers
       the injected type in all 30. Probing them instead changed 12,
       including a landed `rmdir` answered `NotFound` by SFTP's
       reconnecting `stat`. **Driver obligation:** `classify` types a
       refusal about the key's state (`ENOENT`, `ENOTDIR`) as `NotFound`,
       never `PermissionDenied`. Local's `delete_folder` handler does the
       latter today (`_local.py` lines 505 to 510), and with it 24 Local
       cells would change (`compare local`, `Lt P1`, a link-following
       driver), 2 of them a link nested below `key` whose target's file is
       deleted through the link. So step 5's driver classifies by errno.
     - *Folder objects (`parents` `"explicit"` or `"implicit"`),
       `recursive=False`.* `remove_folder(key)` with no probe before it,
       then the probes above on a refusal.
     - *Folder objects, `recursive=True`, with `SupportsDeleteTree`.*
       `delete_tree(key)`, which D1's row binds. It removes a folder's tree
       and refuses a file or an absent key without removing anything, in
       one step where the wire has one (Memory's lock).
       A wire without one checks, then removes, and documents that race as
       `remove_folder` does: Graph's `DELETE` on an item and HNS
       `delete_directory` remove a file item too (round 9's reading of
       their code and SDK, not run against a live wire), so
       their drivers check first. A refusal gets the `stat` probe only,
       never the listing.
     - *Folder objects, `recursive=True`, without `SupportsDeleteTree` (the
       walk).* `list_page(prefix, delimiter="/")` down the tree, so a
       folder holding no files still arrives as a common prefix. Then the
       files are deleted and `remove_folder` runs deepest first, `key`
       last. On the way, a refusal from `delete` or `remove_folder` goes
       through the probe rule above for its own key, with two differences:
       an absent outcome, a typed `NotFound` or a probe answering absent,
       is tolerated (the entry is already gone), and a `delete` whose probe
       finds a file keeps its own refusal, a file being that call's right
       type. A file swapped for a non-empty directory mid-walk answers
       `DirectoryNotEmpty` (`compare extra`), and a subfolder whose
       `remove_folder` refuses untyped and whose probe finds a file
       answers `InvalidPath` for that subfolder, with the files deleted
       before it gone (`compare enum`). The walk's own listing
       follows the same rule: a listing of `key` that refuses goes through
       the probe rule for `key`, and a subfolder's listing that answers
       `NotFound`, or lists empty because a concurrent deleter removed it,
       is tolerated. Its other refusals go through the probe rule for that
       subfolder: a `PermissionDenied` passes through before anything is
       removed, and an untyped refusal on a non-empty subfolder answers
       `DirectoryNotEmpty` (`compare extra`, Local and SFTP). [Added in
       PR #1057's round 4, the maintainer's decision.] Only the calls on
       `key` itself, its listing and the final `remove_folder`, apply
       `missing_ok`.
     - *A recursive delete may answer `DirectoryNotEmpty`*, on a walk,
       when a writer adds under the tree mid-walk. BE-013 lists it only for
       `recursive=False` and forbids nothing, and item 8's clause states
       it. Memory's one-step `delete_tree` cannot.
     - *`delete_folder` never treats a link as a folder.* `stat` and
       `list_page` take `follow_links: bool = True`; every operation but
       `delete_folder` keeps the default, so its answers through links are
       today's. `delete_folder` calls both with `follow_links=False`, a
       view in which a link (a symbolic link, dangling or not, or a
       Windows junction, which Local follows without `is_symlink()`
       reporting it) is a non-folder entry. So the walk deletes a link
       below `key` as a file instead of descending into it, and the probes
       answer `InvalidPath` for a link at `key`. [Maintainer's decisions in
       PR #1057's rounds 3 and 4; the alternatives weighed are in BK-396's
       Outcome, item 6.] The
       reason: a driver that follows links in the walk deleted the
       target's file through a link to a non-empty directory, where
       `rmtree` refuses today. The view is what the 12 changed Local cells
       below were measured under (the script's `Ll` driver); a link nested
       below `key` keeps today's answer, its target untouched (`compare
       summary`). Item 8 states the flag.
     - *`parents == "none"`.* No folder objects, so `remove_folder` is
       never called. The kernel lists first and `stat`s only after an
       empty listing, the order `S3Boto3Backend`, `SQLBlobBackend` and
       flat `AsyncAzureBackend` use today. The listing is
       `list_page(key, delimiter="/", limit=1)` for a non-recursive call.
       For a recursive one it is `list_page(key, delimiter=None, limit=1)`
       before `delete_tree`, or, without `SupportsDeleteTree`, one paged
       `list_page(key, delimiter=None)` whose files the kernel deletes,
       tolerating a `NotFound` on a listed file as the walk does [added in
       PR #1057's round 1, the maintainer's decision].
       After an empty listing, `stat`: a file answers `InvalidPath`,
       anything else `NotFound`, to which `missing_ok` applies. Per BE-021,
       the listing is the determinant and fails closed, and the `stat`
       fails open, so a raising `stat` leaves the empty listing's
       `NotFound`. After a non-empty listing, a refusal from `delete_tree`,
       or one other than that tolerated `NotFound` from a listed file's
       `delete`, passes through unprobed: the listing, the determinant,
       already settled the key's state (the model's `Kernel._none`).

     | Key state, folder objects | `recursive=False` | `recursive=True` |
     |---|---|---|
     | empty folder | removed | removed |
     | folder holding files, or only an empty folder | `DirectoryNotEmpty` | removed (`DirectoryNotEmpty` under a concurrent writer on a walk) |
     | file, or a symbolic link | `InvalidPath` | `InvalidPath`, nothing removed |
     | absent, or under a file (`f/x`) | `NotFound` | `NotFound` |

     | Key state, `parents == "none"` | `recursive=False` | `recursive=True` |
     |---|---|---|
     | files under the prefix | `DirectoryNotEmpty` | removed |
     | file `f`, nothing under it | `InvalidPath` | `InvalidPath` |
     | a file and a prefix both | `DirectoryNotEmpty` | the files under it removed, the file kept |
     | absent, or under a file (`f/x`) | `NotFound` | `NotFound` |

     **Changed cells, by the step that lists them**, against today's
     answers and post-state:
     - Step 1, Memory: none of 24.
     - Step 3, SQLBlob: 8 of 20 injected-fault cells. A raising `stat`
       after an empty listing (file `f`, or absent, × `recursive` ×
       `missing_ok`) answers `BackendUnavailable` today, because
       `_reject_file` propagates it. The kernel answers `NotFound`, or
       returns under `missing_ok`. Its 20 base cells are unchanged, and so
       are S3Boto3's 20 and flat Azure's 20, with all 40 fired fault cells
       on each.
     - Step 4, flat Azure: 2 cells, a concurrent deleter on a recursive
       delete (`d/a` deleted by another client just before the backend
       deletes it, `missing_ok` either way). Today it answers `NotFound`
       and leaves `d/b`; the kernel tolerates the `NotFound` and empties
       the prefix.
     - Step 5, Local: 12 of 44, every one a link at `key` (a link nested
       below `key` keeps today's answer). A dangling link
       answers `NotFound` today (silent under `missing_ok`), and a link to
       an empty or a non-empty directory answers `PermissionDenied`. The
       kernel answers `InvalidPath` for all three, × `recursive` ×
       `missing_ok`. A link to a file keeps `InvalidPath`. Not measured: a
       permission-denied folder (the container runs as uid 0), and Windows
       junctions (the container is Linux), so step 5 measures both. With no
       today to compare against, because Local has no wire to drop, step 5
       also lists the cells where a failing `stat` probe leaves a file
       answered `NotFound`, or quiet under `missing_ok` (`compare extra`).
     - Step 6, SFTP: none of 24 base cells. Under a concurrent writer the
       recursive delete answers an untyped `RemoteStoreError` today (200 of
       200 threaded runs, `race 200`, printed by `compare races`) and
       `DirectoryNotEmpty` on the kernel (`compare summary`), a typing
       change. With the probe's `stat` dropping the channel (absent key or
       file, × `recursive` × `missing_ok`), 8 cells: today's first call is
       that `stat`, so it answers `BackendUnavailable`; the kernel answers
       `NotFound`, or returns under `missing_ok`. Its symbolic links were
       not measured, so step 6 measures them.
     - Steps 4 and 7, HNS and Graph: read, not run (no emulator). Today
       both check the type first and answer `InvalidPath` for a file (Graph
       `aio/backends/_graph/backend.py` lines 1336 to 1337, HNS through
       `hdi_isfolder` at `aio/backends/_azure.py` lines 963 to 965). Their
       check-then-remove keeps that answer, and the model of their wire
       reproduces it.
   - **A wire with no one-step removal.** The driver checks and then
     removes, and must document that race. Azure on HNS
     (`get_paths(max_results=1)` then `delete_directory`; in
     `AsyncAzureBackend`, the class step 4 migrates, `aio/backends/_azure.py`
     lines 967 to 973, and in the sync class step 4 replaces, `_azure.py`
     lines 1154 to 1157) and GR-043 check and then remove today, and none
     documents the race (a case-insensitive search for `race|TOCTOU` finds
     nothing in either Azure module, and spec 044's hits are GR-018's create
     race and the move race, none in GR-043), so the note is new at steps 4
     and 7.
   - **Who carries it: a rule on `parents`.** Required whenever the driver
     has folder objects, `parents == "explicit"` or `"implicit"`, checked at
     construction: Graph and Azure HNS carry it at steps 7 and 4. Never
     called when `parents == "none"`, which has no folder objects; a driver
     class that carries it for one mode and serves `none` in another (the
     one Azure driver RFC-0017 D4 keeps for flat and HNS) is therefore fine.
     [Maintainer's decision in PR #1056's round 5, replacing "optional when
     `implicit`", under which a present empty folder answered `NotFound`.]

   RFC-0017 D1's protocol table carries the row. Both Memory drivers
   implement it beside `SupportsDeleteTree` (BK-394's MEM-014 placement).
   Its kernel cells trace to the spec 003 clause item 8 below adds.

## What it owes

1. The kernel, written once as `AsyncDriverBackend` over `AsyncDriver`, with
   the surface both runtimes share generated into `DriverBackend` by `unasync`
   (Open Question 1). The generated file is committed with a drift check. A
   small hand-written sync layer supplies `read_seekable`, `open_atomic` and
   `read`'s `BinaryIO`, which the async surface lacks. The design is RFC-0017
   D1, D2 and D6, with the decisions above.
2. A fake-driver kernel suite per § Impact, Testing. (The Memory drivers and
   their conformance gate moved to BK-394.)
   - The kernel suite runs BE-029's six root write spellings as fake-driver
     kernel cells. ID-251 (done, PR #1050) already widened the conformance
     cells to them and settled the `"./"` oracle question: `DafnyOracleBackend`
     folds through the compiled `RootPath.dfy` §5 entry, so nothing about the
     oracle is open here. Its dossier carries the measurement.
   - **(was ID-261, absorbed here)** The fake driver can present an absent
     container, which no conformance fixture arranges, so BE-029's order
     (closed guard, then the root check, then the driver) becomes observable
     once for every class on the kernel. ID-261's evidence is in its
     [dossier](id-261-root-order-unobservable.md).
   - BK-345's kernel half: the absent-container answers BE-021 § Reach
     decides, per `Op`, as fake-driver cells. Its registry gate stays BK-345's,
     as per-driver `container_absent` cells from step 2.
3. The `max_depth` algorithm on DEPTH-003's reading (BUG-240's decision), and
   the folder `modified_at` aggregation as RFC-0017 D3 fixes it: the latest
   known file time, skipping the `datetime.min` UTC sentinel, and `None` when
   no time is known. The kernel computes it over a listing; a driver with
   `SupportsFolderStats` must return the same value (BK-394's spec 013
   placement gives both Memory drivers one).
8. Spec 003 clauses for the kernel cells no spec ID covers yet, so the suite
   follows SPEC → TEST → IMPLEMENT (`000-process.md` Rule 1). [Added after
   PR #1055 merged, from its closing-pass review; the maintainer moved the
   key clause here from BK-394. Numbered 8, after the original list's 1 to
   7, so that the gaps at 4 to 7 still mark the items that moved to BK-394.] Each
   is scoped to a class on the kernel, and no class is on it until BK-394:
   - the key rule of decision 6: its refusals, the backslash among them,
     normalisation and root check on the canonical key, together with
     BK-395's answers as decision 6 states them. BK-395 found no clause
     contradicted, inside spec 003 or out, so what lands here is additions:
     BE-025 and BE-029's addressing row gain the kernel's addressing rule
     (canonical key to the driver, a refused key raw, `plan.key` the
     caller's); BE-029's backslash paragraphs ("a backslash-only key is
     **not** refused by this clause") gain that a class on the kernel
     refuses it under the key rule, by the route that paragraph permits;
     and BE-024 gains the pattern rule and its order. A clause outside spec
     003 that a later answer did contradict would still be BK-394's
     [maintainer's decision in PR #1056's round 4];
   - the root `delete_folder` refusal (`InvalidPath`), which BE-029 § Out of
     scope leaves undefined;
   - decision 8: `remove_folder`'s atomic refusal and who carries it,
     `delete_tree`'s refusal, and the kernel's `delete_folder` sequence as
     decision 8 states it (decided in BK-396), including a recursive
     `DirectoryNotEmpty` under a concurrent writer, and the rule that
     `delete_folder` never treats a link as a folder (with the
     `follow_links` flag on `stat` and `list_page`).

**Depends on** BK-388, whose postconditions the kernel is written against.
BK-395, which decided the key rule's remainder (decision 6), and BK-396,
which decided the `delete_folder` sequence (decision 8), are done.
As landed, the root rule is a postcondition ranked after the closed guard,
not a precondition, so the kernel's order per operation is closed
(`Live()`), then the root check on the key (`write`, the `move`/`copy`
source then destination), then the driver [superseded by decision 6's
pipeline, which adds the refusals and normalisation and runs the root check
on every operation its table covers, not only these, and BK-395 extended it
to `glob` and stated the addressing members' rule; what follows is the
BK-388 obligation that pipeline discharges]. On `write` and the destination
the check is `AddressesRoot`, the slash-and-dot segment test, wider than
`is_root`; on the source BE-029 requires only `is_root`, and the wider test
is permitted, not verified. Against an absent
container a `write` under the root is left to the backend spec (the Dafny
witness recreates the container), and `RequireCapability` answers after
close. The kernel decides root-ness on raw keys [since decision 6: on the
canonical key, which for a valid key is `AddressesRoot` of the raw key, so
the obligation below is unchanged]; the obligation for every
spelling is the raw-key entry in `RootPath.dfy` §5, not the trait alone.
`close()` is not promised to keep the store's contents. See
`sdd/formal/README.md` gaps 9 to 11.

## Evidence for the kernel (2026-10-02, master `9caef6b`)

Re-derived before writing, each with its command; the audit that first
reported them was read-only and its figures were not carried. "The probe"
below is this, run with `hatch run python`: for each of `""`, `"."`, `"./"`,
`".//"`, print `is_root(p)` and `MemoryBackend._split_path(p)`; write
`d/a.txt`, set that entry's `modified_at` to `datetime.min` in UTC through
`_traverse`, print `get_folder_info("d").modified_at`; `close()`, then
`write("e.txt", b"y")`; and the same three steps on `AsyncMemoryBackend` with
`aclose()`.

- **`unasync` is not installed and no manifest names it.** `hatch run python
  -c "import unasync"` and `python -c "import unasync"` both raise
  `ModuleNotFoundError`; a search for `unasync` in `pyproject.toml` finds
  nothing. Adding it is a dependency change, so the ripple-check's
  *Dependency* row applies (a dev-only tool belongs to the hatch environment,
  not to an extra).
- **The two surfaces do not map token for token.** Read from
  `src/remote_store/_backend.py` and `src/remote_store/aio/_async_backend.py`:
  `read_seekable` (`_backend.py` line 140) and `open_atomic` (line 265) have
  no async counterpart; sync `read` returns `BinaryIO` (line 111), async
  `read` an `AsyncIterator[bytes]` (`_async_backend.py` line 104); the sync
  lifecycle method is `close` (line 563), the async one `aclose` (line 381).
  D6 already puts the first three in the hand-written sync layer; `aclose`
  to `close` is a name mapping the generator has to be told, not a token
  `unasync`'s defaults strip.
- **Neither base class has `probe()`.** No `def probe` in either file above;
  `check_health` is a no-op default on both (`_backend.py` line 545,
  `_async_backend.py` line 384). PING-002's "the kernel runs the driver's
  required `probe()`" therefore replaces a default, as BK-394's spec 026 row
  states.
- **A closed guard exists in five modules, six classes, and in neither Memory
  class, by posture.** `if self._closed:` followed by a `BackendUnavailable`
  raise appears in `backends/_azure.py`, `aio/backends/_azure.py`,
  `aio/backends/_graph/backend.py`, `backends/_s3_base.py` (shared by
  `S3Backend` and `S3PyArrowBackend`) and `backends/_s3_boto3.py`; the word
  `closed` has no hit in either `_memory.py`. That matches BE-020, which gives
  Memory `close_is_terminal = False`: measured with the probe, a
  `write` after `close()` (sync) and after `aclose()` (async) succeeds. The
  kernel's guard is therefore conditional on the declared posture (decision 4).
- **The root spellings differ between `is_root` and Memory's splitter.**
  `is_root` accepts `""` and `"."` only (`_path.py` `_ROOT_SPELLINGS`);
  `MemoryBackend._split_path` and the async module's `_split_path` drop empty
  and `.` segments, so `"./"` and `".//"` also split to the root (measured,
  the probe: `is_root` `False`, split `[]`). Decision 6 settles it: the
  kernel normalises such a key to `""` and decides the root on that, so it
  is the root on every operation. Memory answers it that way today on every
  measured operation except `get_folder_info`, the Δ cell of decision 6's
  table. The addressing members answer it raw today; under BK-395's rule
  the kernel normalises it first, a Δ cell of the same table.
- **Neither Memory class skips the unknown-time sentinel in
  `get_folder_info`.** A folder whose only file carries `datetime.min` in UTC
  answers that sentinel, sync and async, where the kernel's rule
  (item 3) answers `None` (the probe). `_known_modified_at` (`_models.py` line 27) is
  called only by `Store`, `AsyncStore`, `ext.arrow` and `S3PyArrowBackend`.
  No Memory cell changes: Memory's `write` stamps the current time, so its
  files never carry the sentinel through the public API.

**What it does not include.** The Memory drivers and everything step 1 makes
true (BK-394); step 2 onward (RFC-0017 D3); the spec amendments of later steps
(BK-390).
