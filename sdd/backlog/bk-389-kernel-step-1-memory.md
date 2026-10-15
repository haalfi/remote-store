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
   after the bytes land. That is the shape of BUG-299 and of retired BUG-297
   (now BK-394's Memory cells and BUG-300), which both write first and then raise. For a key that passes (2), a canonical `""` is exactly
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

   | Key class (examples) | Probes: `exists`, `is_file`, `is_folder` | File-shaped: `read`, `read_bytes`, `read_seekable`, `get_file_info`, `delete`, `move`/`copy` source | Write-shaped: `write`, `write_atomic`, `open_atomic`, `move`/`copy` destination | Folder-shaped: `list_files`, `list_folders`, `iter_children`, `get_folder_info` | `delete_folder` | Addressing: `native_path` and `resolve(k).native_path`; `resolve(k).key` is the caller's `k` in every row |
   |---|---|---|---|---|---|---|
   | root (`""`, `"."`, `"./"`, `".//"`, `"./."`) | the root's answer (BE-029) | `InvalidPath` | `InvalidPath` (BE-029) | the root folder; **Δ** `get_folder_info` on `"./"`, `".//"`, `"./."`, which raises `InvalidPath` today | `InvalidPath`, refused by the kernel, never reaching `delete_tree` or the list-then-delete synthesis | the driver's answer for `""`, the bare root; **Δ** on `"./"`, `".//"`, `"./."`, echoed raw today |
   | `/`-led (`"/"`, `"/./"`, `"/f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | `..` segment (`"d/../f"`) | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | null byte | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | `InvalidPath` | the raw key passed to the driver |
   | backslash (`"d\\f"`, `"e\\g"`, `"\\"`) | `InvalidPath`; **Δ**, `True` or `False` today | `InvalidPath`; **Δ**, served from the stored key, or `NotFound`, today | `InvalidPath`; **Δ**, `write("d\\f")` and `move("f", "\\")` store today, `write("\\")` stores then raises, and `move("f", "d\\f")` onto a stored `d\f` answers `AlreadyExists` | `InvalidPath`; **Δ**, `"e\\g"` listed and aggregated, `"d\\f"` lists empty, `"\\"` empty or `NotFound`, today | `InvalidPath`; **Δ**, `"e\\g"` removed and `"\\"` `NotFound` today | the raw key passed to the driver |
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
   own docstring ("the root rule does not
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
   nothing for `""` and `"."`, step 5. All on Linux: on Windows `\` is a
   path separator, so `"d\\*.csv"` likely matches `d/a.csv` there today
   (read from `_local.py`'s `self._root.glob(pattern)`, not run), and
   `Store.glob("d\\*.csv")` would go from matches to `InvalidPath`, a
   Windows cell step 5 measures;
   `SQLBlobBackend.glob`, on a store holding no backslash key, answers `[]`
   for `"./d/*.csv"`, `"d//*.csv"` and `"d/./*.csv"`, where the kernel
   matches `d/a.csv`, `[]` for `"d/*/."`, where the kernel's `"d/*"`
   matches `d/a.csv`, and `[]` for every refused pattern, where the kernel
   answers `InvalidPath`, step 3. Step 3 also reworks SQL-BLOB-061's
   `tests/backends/sqlblob/test_like_prefix.py`: its `backend` fixture
   writes the backslash key `a\b/s.txt` from `SEEDS` before every test that
   uses it, so that seed must leave the fixture, and the cells that pass a
   backslash key or pattern themselves invert to `InvalidPath`, the
   parametrisations with id `backslash`, `a\\x` and `backslash_in_tail`
   (`pytest --collect-only -q` on that file lists each).
   Not run, so each step measures its own addressing and backslash cells,
   and its `glob` cells where it declares `GLOB`: SQLBlob's operations and
   addressing and all of `SQLQueryBackend`, which declares `GLOB`
   (`_QUERY_CAPABILITIES`), step 3; `S3Boto3Backend` (`GLOB`), step 2;
   `AsyncAzureBackend` (`GLOB`), step 4; `SFTPBackend`, step 6;
   `GraphBackend`, step 7; `ReadOnlyHttpBackend`, step 8; and
   `LocalBackend`'s backslash operations, step 5, of which one was run:
   on Linux `write("d\\f")` creates a file named `d\f` in the root and
   returns path `d/f`, where the kernel answers `InvalidPath`. SQLBlob's
   operation cells include BUG-300's `write("\\")`, which raises
   `InvalidPath` with `exists("\\")` then `True` (run at master `57d0797`),
   so step 3 pins `InvalidPath` with nothing stored. Each `GLOB`
   driver's step also lists `Store.glob`'s cells, which depend on
   `root_path`: `Store` and `AsyncStore` prepend the root to the raw pattern
   (`f"{root}/{pattern}"`, GLOB-007), so a leading `/` is refused under an
   empty root and becomes a dropped empty segment under a non-empty one.
   Measured at master `57d0797` on Local, `Store.glob("/d/*.csv")` raises
   `NotImplementedError` with `root_path=""` and matches with
   `root_path="r"`; the kernel keeps that split as `InvalidPath` against a
   match, and `Store.glob`'s own pattern handling is GLOB-007's, not the
   kernel's. `ext.glob.glob_files` already answers a non-canonical pattern
   by capability tier on master, and the kernel rule keeps the `GLOB`
   side's answers; the measurement and the open decision are BK-405's
   [dossier](bk-405-ext-glob-fallback-tier-split.md). This decision adds
   nothing else to D3's list.

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
     backend refusing it. This also decides retired BUG-297's fix:
     `write("\\")` never reaches the driver (its open work is BK-394's
     Memory cells and BUG-300 for SQLBlob). The refusal covers input keys
     only: what a listing yields for a stored key holding a backslash that
     another tool wrote is BK-399's, decided in this item's kernel PR.
     [Decided 2026-10-11, the maintainer through the interview, the
     recommended option: a listed key the rule would refuse or rewrite is
     **omitted** from every listing, `glob` and the folder aggregate, and
     logged. Folding names another node and raising makes every sibling
     unlistable; it stays reachable through addressing and `unwrap()`. A
     driver aggregating natively owes the same omission. BE-030 states it.]
   - **`glob(pattern)` takes the pipeline segment-wise over the whole
     pattern.** Order: the capability first (a driver without `SupportsGlob`
     declares no `GLOB`, so `CapabilityNotSupported` as BE-024 states,
     closed or not, as `BackendContract.dfy` exempts `RequireCapability`
     from `Live()` because it reads declared data; the maintainer's
     decision in PR #1061's round 4), then the closed guard, then step
     (2)'s refusals over the raw pattern (a leading `/`, a `..` segment, a
     null byte, a backslash), then step (3) exactly as for a key: every
     empty and `.` segment is dropped, wildcard characters untouched inside
     their segments. **One addition: if the raw pattern ends in `/` and
     something remains, the canonical pattern keeps that trailing `/`**,
     since in a pattern it selects directories only (the maintainer's
     decisions in PR #1061's rounds 7 and 8). Then the driver gets the
     canonical pattern, so a native driver's prefix listing (GLOB-018 to
     GLOB-020) starts from it. A canonical `""` names the root, a folder,
     and yields nothing, since `glob` returns only files (GLOB-004, BE-024).
     The rule above is authoritative; the table below is worked examples
     of it, one per edge class, and any pattern not shown follows the rule
     (an already canonical pattern, such as `"**/*.csv"`, passes unchanged):

     | Raw pattern | Kernel's answer |
     |---|---|
     | `"d/*.csv"`, `"./d/*.csv"`, `"d//*.csv"`, `"d/./*.csv"` | `"d/*.csv"` to the driver |
     | `"d/*/"`, `"d/*//"`, `"./d/*/"`, `"d/./*/"` | `"d/*/"` (directories only, so no file) |
     | `"d//"`, `"d/./"` | `"d/"` |
     | `"d/*/."` | `"d/*"` (a trailing `.` is dropped like any `.`; the raw pattern does not end in `/`) |
     | `""`, `"."`, `"./"`, `".//"` | `""`, the root: nothing |
     | `"/"`, `"/./"`, `"/d/*.csv"` | `InvalidPath` (leading `/`, refused at step (2) before step (3)) |
     | `"*/../x"`, `"d/*\0"`, `"d\\*.csv"` | `InvalidPath` |

     Measured at master `57d0797`: `glob("d/*/")` and `glob("**/")` answer
     `[]` on Local and SQLBlob, and `glob("d/*/.")` answers `['d/a.csv']`
     on Local and `[]` on SQLBlob, so SQLBlob's `"d/*/."` cell changes at
     step 3. Unlike a key, a pattern reaches the backend from `Store.glob`
     without `RemotePath`, so these cells are visible through `Store` once a
     `GLOB` driver migrates. No step-1 cell: neither Memory class declares
     `GLOB`.

   **Clauses checked, and who amends each.** This paragraph is the one
   home for which clauses BK-395's answers affect and which item amends
   each; BK-394, BK-390, RFC-0017 § Impact and BK-395's dossier point here
   rather than restating it. BE-025 permits `native_path` to normalise and
   requires totality and the verbatim round trip of `..` and null bytes, all
   kept; NPR-004 and NPR-021 require totality; RES-020 and RES-025 hold as
   stated above; PATH-002 binds `RemotePath`, which `Store` applies before
   the backend, so a refused **key** reaches only a caller holding a backend
   directly (a `glob` pattern does not pass `RemotePath`, above). **Three
   round-trip clauses are contradicted, and were already false on master**
   (found in PR #1061's rounds 4 and 5): spec 010's NPR-005 ("holds for
   `k == ""` as well as every non-empty key — except … `"."`") and NPR-020
   ("for all valid keys except the root spelling `"."`"), and spec 003's
   BE-029 § Round-trip consequence ("The identity holds verbatim for every
   other key"). Under this rule a non-canonical key's address inverts to its
   canonical key, as BE-025 already allows, and `GraphBackend` does so
   today: run offline at master `57d0797` (`GraphBackend("drive-x",
   token_provider=lambda: "t")`), `to_key(native_path(k))` is `"d/f"` for
   `"d//f"` and `"d/./f"`, `"d"` for `"d/"` and `""` for `"./"` and `".//"`.
   BK-398 amends all three, by maintainer decision; it can land any time
   and must land before BK-394, the first PR to put a class on the kernel,
   which only re-checks them (not before this item's kernel PR). Two clauses outside spec 003 are made incomplete or
   false only once Memory runs on the kernel, so BK-394 amends them: spec
   013's MEM-DS-005 table, which has no backslash row, and NPR-020's
   Overrides line, "`MemoryBackend` inherits the identity default" (spec
   010 line 280), false once Memory's `native_path` answers the canonical
   key (found in PR #1061's rounds 3 and 6). Otherwise spec 003 gains
   clauses, which item 8 lists: BE-025 and BE-029's addressing row, BE-029's
   backslash paragraphs, and BE-024's pattern rule.

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
     - **Superseded on 2026-10-15** in its probe rule, the walk's on-the-way
       probes, the probe of a refused listing of `key` (now only its first page
       gets A.8's rows; a later page propagates), the claim that only
       `delete_folder` calls `stat` without following links (`delete` and a
       `move` source do too), the driver obligation below, and in the
       `parents == "none"` paragraph its list-first order (on a flat namespace
       the key is `stat`ed first, A.3), its unprobed `delete_tree` refusal after
       a non-empty listing (now A.8's flat `delete_tree` row) and its table's
       "a file and a prefix both" row, by spec 003's
       BE-031 and BE-032 (§ Resumed against RFC-0021 below): every refusal in
       BE-032's probe set is probed, a refusal on the walk's way propagates, and
       drivers owe no rule about how a refusal is typed. The history and
       measurements below stand as recorded.
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
       latter today (its `except OSError` arm), and with it 24 Local
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
     | a file and a prefix both (superseded: `InvalidPath`, nothing removed, BE-031) | `DirectoryNotEmpty` | the files under it removed, the file kept |
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
     BK-395's answers as decision 6 states them. The clauses those answers
     contradict or leave incomplete, and who amends each, are decision 6's
     **Clauses checked, and who amends each**; what lands here is the
     additions: BE-025 and BE-029's addressing row gain the kernel's addressing rule
     (canonical key to the driver, a refused key raw, `plan.key` the
     caller's); BE-029's backslash paragraphs ("a backslash-only key is
     **not** refused by this clause") gain that a class on the kernel
     refuses it under the key rule, by the route that paragraph permits;
     and BE-024 gains the pattern rule and its order. Any other clause
     outside spec 003 they contradict is BK-394's [maintainer's decision in
     PR #1056's round 4];
   - the root `delete_folder` refusal (`InvalidPath`), which BE-029 § Out of
     scope leaves undefined;
   - decision 8: `remove_folder`'s atomic refusal and who carries it,
     `delete_tree`'s refusal, and the kernel's `delete_folder` sequence as
     decision 8 states it (decided in BK-396), including a recursive
     `DirectoryNotEmpty` under a concurrent writer, and the rule that
     `delete_folder` never treats a link as a folder (with the
     `follow_links` flag on `stat` and `list_page`);
   - BE-017's folder `modified_at` rule (item 3), moved here from BK-394 at
     the maintainer's decision in the kernel PR, so its cells trace to a
     clause [added 2026-10-12].

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

## As landed (2026-10-11, the kernel PR)

Where it lives: `src/remote_store/_kernel/`, unexported. `_async/driver.py`
and `_async/kernel.py` are the source; `_sync/driver.py` and `_sync/kernel.py`
are generated from them by `scripts/gen_sync_kernel.py` (unasync's token pass,
then ruff), whose `--check` runs in `preflight`; `_async/_io.py` and
`_sync/_io.py` are the hand-written seam (stream and content shapes);
`backend.py` and `aio_backend.py` hold each runtime's own members. Spec 003
gained BE-030 (key rule, BK-399's answer), BE-031 (`delete_folder`) and
BE-017's aggregation sentence (moved from BK-394 at the maintainer's
decision, so the kernel's cells trace to a clause). Tests: `tests/_kernel/`,
every cell in both runtimes; the `delete_folder` cells run the real kernel
and `rfc-0017-delete-folder-measure.py`'s decided `Kernel` side by side,
the 88-cell `enum` product included.

Choices the decisions above left open, as built:

- **Driver records.** `put` returns a `PutResult` without a path, so no driver
  builds a `RemotePath` (decision 6's "result path before the commit").
  `get_range` returns `bytes` and may return fewer than asked. `copy`,
  `SupportsAtomicMove.move` and `open_write` take `overwrite`;
  `SupportsRename` declares `rename_replaces`.
- **Construction** refuses, with `ValueError`, a flat driver with folder objects
  (added 2026-10-12, § Condition space); a driver with folder objects and
  no `remove_folder`; a declared capability its protocols cannot back, for each
  of `ATOMIC_MOVE`, `ATOMIC_WRITE`, `GLOB`, `COPY` and `MOVE` (the checks in
  `_check_construction`); and a class whose own `close_is_terminal` differs
  from its driver's. A driver with `parents == "explicit"` and no
  `ensure_parents` is refused too (§ Condition space, decision 8; until then
  it was built and its writes under a missing folder answered `NotFound`,
  against BE-009). `move`, `copy` and `write_atomic` decide their means before
  `ensure_parents` runs, so a refused call creates no folders.
- **Capabilities.** `glob`, `write_atomic`, `open_atomic`, `move` and `copy`
  are refused by the declared capability (`GLOB`, `ATOMIC_WRITE`, `MOVE`,
  `COPY`), not by the protocols behind it, ahead of the closed guard and the
  key rule (BE-030), and a write with a non-empty `metadata` by
  `USER_METADATA` (WR-010's strict gate) after the root refusal, all before
  any I/O. `move` and `copy` went by their means until 2026-10-12
  (§ Condition space).
- **`get_folder_info` on an empty aggregate**, on a hierarchical namespace,
  stats the key: fail-open on `parents == "none"`, where it is the error path's
  type probe, and fail-closed with folder objects, where an empty folder exists
  and the stat decides. On a flat namespace, since 2026-10-15, A.3's `stat` has
  already run, so only the probe listing `list_page(limit=1)` types it.
- **Wrong-type probes by namespace.** Superseded on 2026-10-15 by spec 003's
  BE-032 (RFC-0021), which is the authority; § Resumed against RFC-0021
  below says what changed. As it stands: every probe of what a key resolves
  to reads `_state`, the error-path probes of a refused call follow A.8's
  per-call rows (`_read_refused`, `_write_refused`, `_parents_refused`,
  `_holds_nothing`, `delete_folder`'s `_df_refused` and `_df_prefix_refused`),
  and A.4's flat write checks and A.3's flat folder-operation `stat` call
  `_stat` directly, since they are determinants. On a flat driver `_state`'s
  `stat` miss is followed by one `list_page(key, delimiter="/", limit=1)`
  except where no folder can matter (`is_file`, a write target). On a
  hierarchical driver the ancestors' `stat` calls follow a miss when the
  caller asks for the walk (a write target's error path), and follow a `stat`
  that raises a non-miss refusal in the probe set whether or not it asks; a
  `stat` raising outside the probe set is the unknown answer, with no walk.
- **Absent container.** The kernel reads it as `NotFound` for every `Op` but
  `write`, `write_atomic`, `open_atomic`, `probe`, the identity scopes and
  `close`, which keep `classify`'s answer; an error the driver raised
  already typed is never re-typed by it (RFC-0017 D2). On `parents == "none"`,
  `delete_folder`'s determinant listing reads a `NotFound` as empty, where the
  model's flat drivers absorb the container's 404 themselves (BE-013).
- **Move and copy** on a driver with `ensure_parents`, and since 2026-10-15
  on every flat driver, stat the source first, so a missing source creates no
  destination folders and outranks A.4's destination checks (BE-018's order).
- **Streams.** Both runtimes catch `(OSError, EOFError, *stream_catch)` in
  `read`; outside that set an error propagates unmapped in both, as
  `_ErrorMappingStream` does today (SIO-012). A first draft mapped every
  `Exception` on the async side only.
- **Driver obligations the kernel relies on instead of probing:**
  `SupportsDeleteTree.delete_tree` refuses a link at `key` without traversing
  it, since the kernel calls it with no probe before it (BE-031);
  `list_page(follow_links=False)` never lists a link's target, and `delete`
  removes a link itself, since the walk lists `key` with no `stat` first
  (BE-031, added 2026-10-12); `get`, `delete`, `move`, `rename` and `copy` refuse
  an absent or non-file key (the source, for the two-key ones); `list_page`
  refuses a prefix that is a file or lies under one, or lists nothing; and on a
  hierarchical namespace every write primitive and `ensure_parents` refuse a
  folder at the key or a file above it, all without changing anything and in
  any shape, which the kernel types (§ Condition space); on a flat namespace
  the kernel's own checks refuse those writes since 2026-10-15 (BE-032 A.4),
  where they had landed under BE-008's flat exemption, and a flat driver owes
  byte-ordered listings and a `NotFound`/`InvalidPath` listing refusal only
  for an empty prefix (BE-032 A.8);
  `connection_dead` is pure inspection, passed as the sync stream's
  `is_fatal` (SIO-010).
- **`delete_folder` departs from the formal model in one state:** a walk
  over a stored key BE-030 omits answers `DirectoryNotEmpty`, where
  `BackendContract.dfy`'s `DeleteFolder` requires a recursive call to
  succeed; BE-031 says so, and BK-394 reconciles the model. **`write` departs
  in three:** WR-010's gate outranks the type, ancestor and overwrite checks
  (the driver's write answers them on a hierarchical namespace, BE-032's A.4
  checks the first two on a flat one, and the gate stays ahead of that I/O),
  so a write carrying metadata on a class without `USER_METADATA` answers
  `CapabilityNotSupported` where `Write` answers `InvalidPath` for a folder
  at the key or a file above it, and `AlreadyExists` for an existing file
  without `overwrite`; BE-030 says so (added 2026-10-12).
- **`unasync` is pinned in the `dev` extra**, not in the hatch environment
  alone as the evidence above (2026-10-02) proposed: CI's test jobs install
  `.[dev]`, not the hatch env, and import the generator's tests, so an
  env-only pin turned them red on the kernel PR's first push.
- **`_flat_ns._addressable_segments` is restated, not imported:** importing it
  runs `remote_store.backends.__init__`, which imports every backend, and the
  backends will subclass the kernel.

## Condition space (2026-10-12, the kernel PR's review)

*Superseded on 2026-10-15 for what a key resolves to:* the BE-030 paragraphs this
section names (**A key a call needs to be a file**, *What is at a key*) are now
BE-030's **What a key resolves to**, a pointer to BE-032, and the key-resolution
product moved from `tests/_kernel/test_condition_space.py` to A.10's two suites,
`test_tree_results.py` and `test_encoding_observations.py` (§ Resumed against
RFC-0021). The measurements below stand as recorded.

**Why it is enumerated.** The kernel PR's review refuted one condition four
times, in rounds 3, 5, 6 and 7: how a folder at a key a call needs to be a file
is detected and typed, and by whom (the kernel's probes or a driver
obligation). Each narrowing was argued from one reading and refuted by a state
it did not consider, so the maintainer had the space written down once and
generated as a test before anything else was fixed (`/ship`'s repeat-site
check). The rule is BE-030's **A key a call needs to be a file**. This section
holds the axes and the decisions, and
`tests/_kernel/test_condition_space.py` holds the product, whose oracle is
written from the rule.

**Decisions** (the maintainer through the interview, the recommended option
each time):

1. A flat driver with folder objects is refused at construction. Its `stat`
   cannot see its own folder objects. No planned driver is one: RFC-0017 D1
   lists flat drivers as `parents == "none"`, and Graph, HNS, Local and SFTP
   as hierarchical.
2. `namespace`, not `parents`, keys the write-target check. On the kernel,
   BE-008's "no native directory concept" is the flat namespace. Keyed on
   `parents == "none"`, a write onto a folder on (hierarchical, `none`) gave
   two answers for one state: `InvalidPath` on the routes that stat first,
   the wire's raw refusal on the others. `parents` governs folder objects
   only (`remove_folder`, `delete_tree`, `ensure_parents`, empty folders).
3. The kernel types the refusal: one fail-open probe after any refusal typed
   `NotFound`, `AlreadyExists`, `PermissionDenied` or untyped. A driver
   refuses a folder in its wire's own shape and is not asked to type it,
   which would put an `is_dir()` re-check like `_local.py`'s in the driver,
   against D1. A pre-write `stat` was rejected: it puts a round trip on the
   hot path, against BE-021.
4. WR-010's gate keeps its place, and BE-030 records the departure from
   `BackendContract.dfy`'s `Write`. BK-394 reconciles the model.
5. `move` and `copy` are gated on the declared `MOVE` and `COPY`, ahead of
   the closed guard, as `write_atomic` is (the maintainer's round-6 decision
   for that gate).
6. A file above a write target is typed by the kernel too (decided after the
   closing round over `f454037`, whose three members each found it untyped).
   After a refusal in the probe set, when no folder is at the key, the kernel
   stats each ancestor fail-open, and a file among them is `InvalidPath`;
   `ensure_parents`' refusal gets the same probes, and the two determinant
   stats read `NotFound` as a miss, since a POSIX `stat` under a file raises
   ENOTDIR. Leaving it to each driver's `classify` was the alternative.
7. `delete` refusing an absent or non-file key is a driver obligation, stated
   with the source obligation of `move`, `rename` and `copy`. A wire whose
   delete is idempotent (S3) checks first; how is step 2's to decide. A
   kernel `stat` before `delete` behind a new driver flag was the
   alternative.
8. An explicit-parents driver without `ensure_parents` is refused at
   construction, as one with folder objects and no `remove_folder` is
   (decided after the second closing round, over `c6d01ea`). BE-009 says a
   write creates its parents; such a driver could not, and its writes under
   a missing folder answered `NotFound`. Recording a BE-009 departure was the
   alternative.
9. A listing's first-page refusal in the probe set is typed by the kernel
   too, as the file-key refusal is: fail-open probes that find no folder
   (nothing or a file at the prefix, or a file above it) make it an empty
   listing, and `get_folder_info` then types the aggregate. A `list_page`
   obligation to refuse only as `NotFound` or `InvalidPath` was the
   alternative. The same round fixed two defects with no decision in them:
   `move` by rename with `overwrite` answered `AlreadyExists` for a file its
   destination check missed, and the write-target probes kept walking after
   the answer was known.

**Axes** of the product as it stood through round 10, each a parameter,
counted from `pytest --collect-only -q` on the file then. § Re-plan after
round 10 replaced it with one shared axis set; this table is that history:

| Product | Axes | Cells |
|---|---|---|
| A write onto each state | route (`write`; `write_atomic` by atomic put, wire temporary, temp and rename; `open_atomic` by wire temporary, by spool, sync only) × driver (flat/`none`, hierarchical/`none`, `implicit`, `explicit`) × target (absent, file, folder, under a file) × `overwrite` × the wire's refusal (EISDIR, EEXIST, EACCES, ENOENT, untyped, a dead service), only where a hierarchical wire meets a folder or a file above the key × `stat` under a file (answers `None`, raises ENOTDIR), only for that target | 1300 |
| A transfer between each pair of states | route (`move` by atomic move, replacing rename, displace and restore, copy then delete; `copy`) × driver × source (file, absent, folder) × destination (as above) × `overwrite` × the wire's key order (source or destination first) × the wire's refusal, where a folder or a file above is met × `stat` under a file, for that destination | 10000 |
| A file-shaped read on each state | call (`read`, `read_bytes`, `read_seekable` ranged and spooled, `delete` with and without `missing_ok`, `get_file_info`) × driver × state × the wire's refusal at a folder × `stat` under a file | 480 |
| Each capability gate | op (`glob`, `write_atomic`, `open_atomic`, `move`, `copy`, a `write` and a `write_atomic` carrying metadata) × declared × backed by protocols × posture (open, terminal-closed) × key (valid, root, refused, and self for `move`/`copy`) | 296 |
| A folder-shaped listing on each state | call (`list_files`, recursive and not, `list_folders`, `iter_children`, `get_folder_info`) × driver × state × the wire's refusal to list a file or a key under one, where a driver with folder objects meets one × `stat` under a file | 500 |
| Construction | `namespace` × `parents` × `ensure_parents` | 24 |

**Who decides each answer.** The driver's obligations, each to refuse without
changing anything and in any shape: a read, `delete` or two-key source on an
absent or non-file key; a listing of a file prefix or one under a file; and,
on a hierarchical namespace, a write meeting a folder at the key or a file
above it, and `ensure_parents` meeting a file above it. So the
driver decides *that* a call fails, never *how* it is typed. The kernel's
determinants, whose failure is the call's (the four sites that raise
`_state`'s error, `grep -n "raise seen.error"` in `_async/kernel.py`:
`_node`, `_file_entry`, `_write_target` and `get_folder_info`, with their
callers, plus the opt-in walk's own `stat` loop in `_prepare_write`;
enumerated 2026-10-12): the probes `exists`, `is_file` and `is_folder`,
whose `stat`, or on a flat driver whose folder listing after a `stat`
miss, is the answer; `get_file_info` and a ranged `read_seekable`; the source
check of a self-operation, of a rename route, and of every transfer when
the driver has explicit parents or the opt-in walk is on; the destination
`stat` of `move` by rename, and of `write_atomic` by temp and rename without
`overwrite`; the opt-in file-ancestor walk; and the empty-aggregate `stat`
of `get_folder_info` with folder objects. The kernel's error-path probes
type every refusal in the probe set. A dead service, a lock and a non-empty
folder pass through, since they say nothing about the key.

**What the product found against the kernel at `b9351b5`** (the review's
last head; this section's first fake, `pytest --junitxml` grouped by
assertion). 1600 of its first 7680 cells failed:

- writes, 180: a folder at the target answered in the wire's shape
  (`AlreadyExists`, `PermissionDenied`, untyped, 51 each) where it should be
  `InvalidPath`, and `NotFound` on the routes with no probe at all (the wire
  temporary's commit, the temp-and-rename promote, 27);
- transfers, 1248: a folder at either key answered in the wire's shape
  (`AlreadyExists` 306, `PermissionDenied` 318, untyped 318), and a
  destination folder refused as ENOENT answered `NotFound` (72); with folders
  at both keys, the `InvalidPath` named the destination (96); and on a
  destination-first wire an absent source answered the destination's refusal
  (`InvalidPath` 72, `AlreadyExists` 18, `PermissionDenied` 24, untyped 24),
  where BE-018 ranks the source's `NotFound` first;
- reads, 108: a folder answered `AlreadyExists`, `PermissionDenied` or
  untyped (36 each), since only a `NotFound` was probed;
- capability gates, 60: `move` and `copy` with the capability undeclared,
  presented or not, answered by the call, the closed guard or the key rule
  where `CapabilityNotSupported` ranks first;
- construction, 4: flat with folder objects built.

The fix's first draft failed 168 cells, all one shape: an absent source's
`NotFound` overridden by a folder at the destination, against BE-018's order.
It was corrected before the commit.

**The axis the first product held fixed.** It varied the wire's refusal only
for a folder, and its fake's `stat` answered `None` under a file, so a file
above the key was always refused in a shape the fake typed itself. The
closing round over `f454037` found that, all three members independently.
With both axes added (decision 6), 1535 of the then 12088 cells failed at
`f454037`'s kernel (`pytest --junitxml`, grouped by assertion): writes 495
and transfers 1040, in which a file above the key answered in the wire's
shape (`AlreadyExists`, `PermissionDenied` or untyped, 114 each for writes
and 208 each for transfers) or `NotFound` (144 and 368), and in which a
`stat` raising under a file ended the rename routes with `NotFound` before
the wire was reached: where a flat write should land (3 and 16), and where
the wire's dead-service refusal should surface (6 and 32).

**The folder-key product and the construction axis** (decisions 8 and 9),
run at `c6d01ea`'s kernel (`pytest --junitxml`, grouped by assertion): the
listing product failed 188 cells. In 180 a refusal to list a file, or a key
under one, typed `AlreadyExists`, `PermissionDenied` or untyped, propagated:
144 listings that should yield nothing, 12 `get_folder_info` calls that should
answer `InvalidPath` and 24 that should answer `NotFound`, 60 per shape. The
other 8 were the oracle's own error, asserting that `list_folders("d")` is
non-empty for a folder holding only a file, and the oracle was corrected.
Construction failed 2 cells (explicit without `ensure_parents` built). The
two targeted cells failed in both runtimes: `move` with `overwrite` answered
`AlreadyExists`, and an `AlreadyExists` on `a/b/c/d/e` spent five `stat`s
where one answers.

## Re-plan after round 10 (2026-10-12, the kernel PR's review)

*Superseded on 2026-10-15 in its classifier anchor and its test layout:* the
classifier follows BE-032 (BE-030's *What is at a key* is now **What a key
resolves to**), and the shared axis set described below no longer lives in
`test_condition_space.py`, which keeps only `glob`, the capability gates and
construction; key resolution is crossed by A.10's two suites (§ Resumed against
RFC-0021). The history, counts and mutation list stand as recorded.

**Why.** The third closing round over `7e20b25` found a flat listing whose
denied or untyped first page answered empty while the prefix held files: a
silent wrong value, more severe than round 9's, in code a fix pass changed,
so `/ship`'s divergence check fired. Rounds 7 to 10 had one shape: each fix
added a probe to one call family, and the next round found a family or an
axis nobody had crossed. Six helpers each answered "what is at this key"
with their own namespace and `stat` rules (`_probe`, `_stat_open`,
`_folder_is_wrong_type`, `_target_is_wrong_type`, `_holds_nothing`,
`_target_stat`, over `_node_at`), and the maintainer had the work re-planned
in a fresh session before anything was fixed.

**Decisions** (the maintainer through the interview, the recommended option
each time):

10. One classifier and one oracle. `_state(op, key)` answers absent, file,
    folder, under a file or unknown for every call that needs a file or a
    folder, and each family maps a refusal and that answer to its result.
    Extending each helper in place, and narrowing the kernel's job back to
    driver obligations (reversing decision 9), were the alternatives.
11. A `stat` under a file that raises untyped or a denial is typed by the
    kernel: on a hierarchical namespace a `stat` that raises in the probe set
    is followed by the ancestors' `stat` calls, a file among them makes the
    key absent for a probe or a read, and the wrong type for a write. A
    driver obligation that `stat` answers `None` or `NotFound` there was the
    alternative.
12. The double race of round 10 (a file `move`'s check missed, gone before a
    rename that cannot replace displaced it) is fixed here: the move then
    lands. Filing it was the alternative.
13. The product runs as one pytest item per family and runtime, every cell
    checked and each disagreeing cell named, after it reached 60,996 cells.
    Pruning below the 40k bound the plan set, and a separate lane, were the
    alternatives. The bound's premise proved half wrong: the run's crashes
    were the fake's `asyncio.run` per call, which on Windows opens a socket
    pair per loop and exhausted the socket buffers (WinError 10055); with
    one loop kept for the process the whole product runs in 8.16 s.

**The classifier.** BE-030 states it as *What is at a key*; `_state` and
`_above` in `_async/kernel.py` are its one implementation. On a flat
namespace a key is never under a file and a file at a prefix rules out
nothing below it, which is round 10's defect: `_holds_nothing` inferred
"empty" from a file at a flat prefix.

**The shared axis set**, defined once in `tests/_kernel/test_condition_space.py`
and crossed by every family where reachable (the module docstring states the
one pruning rule): the driver (`namespace` × `parents`); eight key states
(absent, absent under an absent folder, a file, an empty folder, a folder
holding a file, under a file, deeper under a file, a flat key shadowing a
prefix); the refusal (the wire's own, in each native shape where the state
makes it refuse, or one injected on the family's first primitive call
whatever the state, or on a flat driver one of the folder probe's listing);
and six `stat` behaviours (truthful; ENOTDIR, untyped
or denied under a file; the cell's own key denied; every `stat` down).
`delete_folder` stays in `test_delete_folder.py`, compared with the decided
model over the model's key states and its enumerated probe space, both of
which already hold a key under a file and a raising `stat`.

| Family | Cells, sync + async |
|---|---|
| Probes (`exists`, `is_file`, `is_folder`) | 549 + 549 |
| File-shaped reads (`read`, `read_bytes`, `read_seekable` ranged and spooled, `delete` with and without `missing_ok`, `get_file_info`) | 5589 + 3861 |
| Writes (six routes, sync-only `open_atomic` included) | 11376 + 7584 |
| Transfers (five routes) | 22336 + 22336 |
| Folder-shaped calls (four listings, `get_folder_info` by listing and by push-down) | 4908 + 4908 |
| `glob`, capability gates, construction | 56, 296, 24 |

Counts from each family's generator called per runtime (and `_gate_cells()`),
and `pytest --collect-only` for `glob` and construction: 84,372 in all, after
the closing round over `936f7f0` added the flat folder probe's refusal
(below); the product at `936f7f0` held 60,996.

**What it found at `72ae8f9`** (the review's last head, the same run): 2405
cells. Probes 126: a `stat` raising untyped or denied under a file, or
denied with an absent ancestor, raised where BE-004/BE-005 answer `False`.
Reads 189: the same `stat` shapes made `get_file_info` and a ranged
`read_seekable` raise where BE-016 answers `NotFound`. Writes 468 and
transfers 592: the same shapes made the rename routes' and temp-and-rename's
determinant raise raw where BE-030 answers `InvalidPath` for a file above,
or a miss for an absent ancestor. Folder-shaped calls 1030: a denied or
untyped first page on a flat prefix, real folder or not, answered empty
(round 10's defect), the push-down let `AlreadyExists`, `PermissionDenied`
and untyped refusals through raw where the listing route types them, and
the empty aggregate's determinant raised raw under a file. Plus the race as
a targeted cell in `test_kernel.py`, failing in both runtimes with `NotFound`
naming the destination.

**Mutations** of the new classifier, each in the async source with the sync
twin regenerated, `tests/_kernel` run per mutation; all ten killed (product
cells failing in parentheses): `_holds_nothing`'s flat branch dropped (216);
round 10's "anything but `BackendUnavailable` holds nothing" (2256, where
it failed 2 incidental cells at `72ae8f9`); the ancestor walk dropped
(5803); the walk shortcut inverted (1456); a raising `stat` not walked
(4203); an unknown answer read as absent (2266); an absent ancestor read as
unknown (213); the push-down routed around the listing rule (440); a write
target under a file not typed by its determinant (72); and the race fix
removed (killed by its targeted cell).

**The closing round over `936f7f0`** found the axis this product had pruned
by a false premise: its docstring said `get_file_info` and the probes call
only `stat`, but on a flat driver `_state` follows a `stat` miss with
`list_page(limit=1)`, and that listing was never refused. `_state` read its
`NotFound` as unknown, so on a flat driver whose container is absent
`exists` and `is_folder` raised `NotFound`, where 72ae8f9 answered `False`
(BE-004, BE-021 § Reach); all three members found it. A `NotFound` or
`InvalidPath` there is now an empty listing, as on a listing's first page.
With that refusal crossed on flat drivers for the probes, the file-shaped
reads and a transfer's source, the product failed at `936f7f0`'s kernel
on exactly the `NotFound` and `InvalidPath` shapes: probes 20 + 20, reads
10 + 5, transfers 1424 + 1424 (the error-path probe of a flat source). The
absent-container test gained a flat arm, which failed in both runtimes,
and every family now asserts that it generated cells.

## Resumed against RFC-0021 (2026-10-15, the kernel PR)

The closing round over `a630ef5` left seven threads open, two of them one
cluster: `delete_folder`'s own probe rule disagreed with `_state` on one
`stat` answer, and passed a `PermissionDenied` unprobed on a driver
obligation the protocol never stated. The maintainer parked the PR and had the
model settled first (BK-432, RFC-0021, accepted 2026-10-13). The resume lands
its Appendix A as spec 003's BE-032 and re-derives the kernel from it, in
scope "all of Appendix A but links" (decision log
`sdd/decisions/3288309c-08e5-4f79-a209-8f9d7fca793f.jsonl`).

What changed in the kernel, each against BE-032:

- **One probe set** (`_in_probe_set`): `NotFound`, `InvalidPath`,
  `AlreadyExists`, `PermissionDenied`, untyped. `_may_be_a_folder` (which
  left out `InvalidPath`) and `delete_folder`'s `_probe_wanted` (only
  `NotFound` and untyped) are gone, and with them planning decision 8's obligation that
  `classify` type ENOENT/ENOTDIR as `NotFound` (A.8: drivers owe no rule
  about a refusal's shape but the two typing rules).
- **Per-call rows replace the wrong-type helpers** (A.8, rule 4): a refused
  `get`/`delete` now also answers `NotFound` on a miss (it answered only a
  folder before); a refused write answers `AlreadyExists` for an item without
  `overwrite`; `ensure_parents` probes only the ancestors; a hierarchical
  listing's first page refused on an existing folder now stands (it read as
  empty for `NotFound`/`InvalidPath`).
- **`delete_folder` reads `_state`** (threads 1 and 2): a raising
  `NotFound`/`InvalidPath` `stat` is a miss, and the rows are `remove_folder`'s
  and `delete_tree`'s. On the walk's way a refusal now propagates unprobed,
  only a `NotFound` tolerated (A.9); the on-way probes are gone.
- **A.4 always, on a flat namespace**: one `stat` per ancestor and one
  `list_page(k, limit=1)` before every write and transfer destination, failing
  closed; `reject_write_under_file_ancestor` is gone from the kernel, and a
  flat transfer checks its source first.
- **A.3 on a flat namespace**: a folder operation `stat`s its key first (an
  item is empty, or `InvalidPath` for `get_folder_info` and `delete_folder`),
  and listings omit what lies below a listed item through `_Shadows`, a stack
  over the byte-ordered listing.
- **The fake** lists a flat item and a prefix of one name together, in byte
  order, and its flat `stat` looks the key up alone.

Left open, each stated in BE-032: links (A.7) are not on the kernel, since no
driver declares `links` until Local or SFTP moves; `glob` applies neither
A.3's `stat` nor its omission (BK-439).
