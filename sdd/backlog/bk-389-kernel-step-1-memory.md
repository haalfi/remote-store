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
the spec 003 clauses the kernel's cells trace to (item 4 below), the
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
   003 clauses item 4 below adds for the cells no ID covers yet [corrected
   after PR #1055 merged: as merged this said existing IDs only]. BK-394 exports
   the public names RFC-0017 § Impact lists, `Session` excepted (it lands at
   step 2, D5), together with the specs that describe them.
6. **Key validation, normalisation and the root are the kernel's.** Round 1
   of this planning PR's review found the Memory placement table putting key
   validation in the driver, against D1: a driver "carries no path, root,
   type, closed or mapping logic".
   Rounds 2 to 4 refuted three prose statements of this rule in turn, so the
   rule is the table below and nothing else. It covers the **operations**
   only. Three parts are not decided here: the addressing members, a key
   holding a backslash, and `glob`. Each touches existing clauses (BE-025,
   NPR-021/NPR-004, RES-020, PATH-002), so the maintainer placed them in
   **BK-395**, on which this item depends. See **Deferred to BK-395** below.

   **Pipeline, per operation.** (1) The closed guard, when the driver declares
   `close_is_terminal`. (2) Refusals, `InvalidPath`: a key starting with `/`, a `..`
   segment, a null byte. (3) Normalisation: empty and `.` segments are
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
   answer differently today.

   | Key class (examples) | Probes: `exists`, `is_file`, `is_folder` | File-shaped: `read`, `read_bytes`, `read_seekable`, `get_file_info`, `delete`, `move`/`copy` source | Write-shaped: `write`, `write_atomic`, `open_atomic`, `move`/`copy` destination | Folder-shaped: `list_files`, `list_folders`, `iter_children`, `get_folder_info` | `delete_folder` |
   |---|---|---|---|---|---|
   | root (`""`, `"."`, `"./"`, `".//"`, `"./."`) | the root's answer (BE-029) | `InvalidPath` | `InvalidPath` (BE-029) | the root folder; **Δ** `get_folder_info` on `"./"`, `".//"`, `"./."`, which raises `InvalidPath` today | `InvalidPath`, refused by the kernel, never reaching `delete_tree` or the list-then-delete synthesis |
   | `/`-led (`"/"`, `"/./"`, `"/f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
   | `..` segment (`"d/../f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
   | null byte | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` |
   | non-canonical (`"d//f"`, `"d/./f"`, `"d/"`) | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer | the canonical key's answer |
   | canonical, no backslash (`"f"`, `"d/f"`) | passed through | passed through | passed through | passed through | passed through |

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
   outside the Δ marks matches the table. The `native_path` and `to_key`
   cells and the `"d\\f"` cells are BK-395's evidence, not this table's.
   Round 5's measuring reviewer then ran `list_folders`, `iter_children`,
   `read`, `read_seekable`, `write_atomic`, `open_atomic` and `copy` the same
   way and found no unmarked difference. **What the Δ cells reach:** no
   conformance cell, since the read-side root cells use only `""` and `"."`.
   `Store` normalises its own inputs, so the Δ is visible only to a caller
   holding a backend directly. BK-394 lists it as a step-1 Memory cell change.

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
   answer pinned]. Step 5 therefore adds a present-root cell, and changes
   the absent-root pins only where the table answers them differently. `SFTPBackend` likely answers
   the same: its `_sftp_path` maps the root to `base_path` and its `_rmtree`
   ends in `rmdir` (read from `_sftp.py`, not run). A flat wire's `"d//f"` or
   `"./"` are further examples. This decision adds nothing else to D3's list.

   **Deferred to BK-395.** Three parts are decided before kernel code, in
   BK-395, not here:
   - The addressing members `native_path`, `resolve` and `to_key`. Applying
     the refusals to the first two would make them raise, against BE-025's
     and NPR-021/NPR-004's totality. Normalising `resolve`'s key would change
     `resolve(".")`'s `plan.key`, against RES-020.
   - A key holding a backslash. Memory stores it today. But PATH-002
     converts a backslash to `/` in `RemotePath`, so `BackendContract.dfy`
     §5a's `WellFormedPath`, `RemotePath`'s fixed point, holds none, and spec
     003 calls such a key not canonical. Every returned path folds it to `/`.
   - `glob` patterns.

   The maintainer recorded a preferred answer for each at the ceiling:
   addressing stays total, with refused keys passed through raw and
   `plan.key` kept as the caller's; a backslash is refused; and a pattern's
   literal prefix goes through the pipeline. BK-395 verifies each against the
   clauses above before adopting it. The pipeline has no answer for a
   backslash key until BK-395 closes, and the kernel PR does not start
   before then.

   **Not `RemotePath`'s rules, nor `LocalBackend._resolve()`'s.** The
   refusals and normalisation are spec 013's MEM-DS-005 table, which both
   Memory classes implement today, and this item's PR restates them as a
   spec 003 clause (item 4 below; moved from BK-394 after PR #1055 merged). A comparison at master `9caef6b` shows
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
8. **Removing one empty folder is an optional protocol,
   `SupportsRemoveFolder`.** Decided after this planning PR's verification
   round, which found that D1 had no primitive for it. That leaves spec
   013's non-recursive `delete_folder`, and Local's and SFTP's later, with
   nothing to call. The protocol has one member, `remove_folder(key)`.
   [Corrected after PR #1055 merged, from its closing-pass review; maintainer
   decisions taken through the interview. As merged, the kernel checked
   emptiness itself with `list_page(key, limit=1)`, which split Memory's
   one-lock check-and-detach (MEM-026, `_memory.py` lines 316 to 336) into
   three driver calls, left the probe's `delimiter` open, and excluded the
   `implicit` drivers that remove an empty folder today.]
   - **The driver refuses atomically.** `remove_folder(key)` removes the
     folder only if it is empty, and otherwise fails with what `classify`
     maps to `DirectoryNotEmpty`. It does so in one wire step where the wire
     has one: Memory under its lock, Local's and SFTP's `rmdir`. Where the
     wire has none, the driver checks and removes itself and documents the
     race, as `AzureBackend` on HNS (`get_paths(max_results=1)` then
     `delete_directory`, `_azure.py` lines 1154 to 1157) and GR-043 do
     today.
   - **Who carries it.** Required when `parents == "explicit"`, checked at
     construction. Optional when `implicit`: Graph and Azure HNS have folder
     objects and carry it at steps 7 and 4. Never for `none`, which has no
     folder objects.
   - `delete_folder(recursive=False)`: the kernel runs decision 6's pipeline,
     answers `NotFound` or not-a-folder from `stat`, then calls
     `remove_folder`. It makes no emptiness probe of its own.
   - `delete_folder(recursive=True)` without `SupportsDeleteTree`: the kernel
     walks the subtree with `list_page(prefix, delimiter="/")`, so a folder
     holding no files still arrives as a common prefix, deletes the files,
     then calls `remove_folder` on each folder, deepest first. This walk is
     not decision 7's listing, which wants files only.

   RFC-0017 D1's protocol table carries the row. Both Memory drivers
   implement it beside `SupportsDeleteTree` (BK-394's MEM-014 placement).
   Its kernel cells trace to the spec 003 clause item 4 below adds.

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
4. Spec 003 clauses for the kernel cells no spec ID covers yet, so the suite
   follows SPEC → TEST → IMPLEMENT (`000-process.md` Rule 1). [Added after
   PR #1055 merged, from its closing-pass review; the maintainer moved the
   key clause here from BK-394.] Each is scoped to a class on the kernel, and
   no class is on it until BK-394:
   - the key rule of decision 6: its refusals, normalisation and root check
     on the canonical key;
   - the root `delete_folder` refusal (`InvalidPath`), which BE-029 § Out of
     scope leaves undefined;
   - decision 8: `remove_folder`'s atomic refusal, who carries it, and the
     kernel's `delete_folder` sequences.

**Depends on** BK-388, whose postconditions the kernel is written against,
and on BK-395, which decides the key rule's remainder (decision 6).
As landed, the root rule is a postcondition ranked after the closed guard,
not a precondition, so the kernel's order per operation is closed
(`Live()`), then the root check on the key (`write`, the `move`/`copy`
source then destination), then the driver [superseded by decision 6's
pipeline, which adds the refusals and normalisation and runs the root check
on every operation its table covers, not only these; the addressing members
and `glob` are BK-395's; what follows is the BK-388 obligation that pipeline
discharges]. On `write` and the destination
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
  table. The addressing members answer it raw today; that is BK-395's.
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
