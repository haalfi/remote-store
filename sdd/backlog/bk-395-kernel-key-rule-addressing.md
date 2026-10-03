# BK-395 — The kernel's key rule is undecided for addressing, backslash keys and `glob`
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Minted on 2026-10-02 in BK-389's planning PR (PR
#1055). That PR states the kernel's key rule as a pipeline and an
operation-by-key-class table, in BK-389's dossier, decision 6. Its review ran
five rounds. In round 5, the ceiling, the table's addressing column and
backslash row were found to contradict existing clauses. The maintainer cut
those parts, and `glob`, out of BK-389's planning and into this item. BK-389
depends on it: the kernel PR does not start until it closes.

**What it decides**, each against the named clauses, before kernel code:

1. **Addressing: `native_path`, `resolve`, `to_key`.**
   - BE-025 (spec 003) says `native_path` is "Pure, deterministic, total
     (never raises)" and that `..` and null bytes "round-trip verbatim".
     NPR-021 (spec 010) gives `native_path` the totality NPR-004 gives
     `to_key`: "must return a string for every input; must not raise".
   - RES-020 (spec 043) states `plan.key == path`.
   - BE-020 carves addressing out of the closed guard.
   - `to_key`'s input is a native path, not a key.
   - Measured at master `9caef6b`, both Memory classes: `native_path` echoes
     `"./"`, `"d//f"`, `"/f"`, `"d/../f"` and `"f\0"` raw, while
     `native_path(".")` already answers `""` (the default's `strip_root`), and
     `resolve(".")` gives `plan.key == "."`.
   - The withdrawn table made `native_path` and `resolve` raise on refused
     keys, and changed `resolve(".")`'s `plan.key` to `""`.
2. **A key holding a backslash.**
   - Memory stores `d\f` today. PATH-002 (spec 004) **converts** a backslash
     to `/` in `RemotePath`, so `BackendContract.dfy` §5a's `WellFormedPath`,
     `RemotePath`'s fixed point, contains none. Spec 003 (BE-029) says such a
     key "is not canonical".
   - `RemotePath` cannot hold a backslash. So every path Memory returns for
     that key folds it to `d/f`: `WriteResult`, `FileInfo` (both classes),
     and listings, where `list_files` over `d/f` and `d\f` yields `d/f`
     twice. Measured by round 5's measuring reviewer.
   - **(was BUG-297, absorbed here)** Called on the backend directly,
     `write("\\")` stores the row on `SQLBlobBackend` and `MemoryBackend`,
     then raises `InvalidPath` ("Path is empty after normalization") while
     building `WriteResult(path=RemotePath(path))`, which folds `\` to `/`;
     `exists("\\")` is then `True`. Measured at master `9caef6b` by the BL-011
     session (PR #1054), on those two backends and that key only. `Store`
     rejects the key first and stores nothing. Its open decision was: reject
     `\` in path validation, or build the result before committing. Rejecting
     it is a different rule from treating it as the root: `RootPath.dfy`'s
     lemma `BackslashIsNotRoot` proves `"\\"` is not the root. BK-389's
     decision 6 now has the kernel build the result path before the driver
     commits; this item still owes the answer for the key itself.
3. **`glob` patterns.** `glob` is one of the 21 members the kernel
   implements, and it reaches `SupportsGlob`. Nothing yet says whether a
   pattern's literal prefix gets the refusals and normalisation.

**The maintainer's preferred answers, recorded at the ceiling and not yet
verified against the clauses above:**

1. Addressing stays total. Root and non-canonical spellings are normalised;
   refused keys go to the driver raw, round-tripping as BE-025 says.
   `plan.key` stays the caller's key; only `native_path` is canonicalised.
2. A backslash is refused with `InvalidPath`. That keeps such keys out of
   the driver, as §5a's well-formed domain does. It diverges from PATH-002,
   which folds a backslash rather than refusing it. Folding would make `d\f`
   collide with `d/f` on a driver that stores both today, as Memory does.
   That is a step-1 Memory cell change, since Memory stores `d\f` today.
3. A pattern's literal prefix, up to the first wildcard, goes through the
   pipeline. The wildcard part goes to `SupportsGlob` unchanged.

**Exit criteria:** each of the three is decided and added to BK-389's
decision 6, as a column or row of its table, or as a stated exclusion with
its reason. Each step-1 Memory cell it changes is listed in BK-394's item 2.
Its answers, and any spec 003 clause they contradict, are amended in
BK-389's spec 003 list, item 8, since the kernel PR waits on this item and
its cells need a spec ID. A contradicted clause in another spec (PATH-002,
NPR-021, NPR-004, RES-020) is amended in BK-394's spec list. (Both set in
PR #1056's rounds 3 and 4.)

## Outcome (2026-10-03)

Decided by the maintainer through the interview, the recommended option each
time. The answers are stated once, in
[BK-389's dossier](bk-389-kernel-step-1-memory.md), decision 6 (**Decided in
BK-395**, the table's backslash row and addressing column, and its **Later
drivers** paragraph); this section keeps only how they were reached.

1. **Addressing:** the preferred answer, adopted as recorded.
2. **Backslash:** the preferred answer, adopted as recorded.
3. **`glob`:** the preferred answer **narrowed**. Running only the literal
   prefix through the pipeline leaves `"*/../x"`, `"*//x"` and a null byte
   after the first wildcard to the driver, which D1 says carries no path
   logic, and the two `GLOB` backends measured below already disagree on
   `"*/../*.csv"` (Local `InvalidPath`, SQLBlob `[]`). So the refusals apply to the whole pattern and empty and `.`
   segments drop anywhere in it; GLOB-012's prefix is then cut from a
   canonical pattern.

Every clause the exit criteria name was checked, and none is contradicted:
the reasons are in decision 6's **Clauses checked** paragraph. So BK-394's
spec list gains nothing outside spec 003, and BK-389's item 8 carries
additions to BE-024, BE-025 and BE-029.

**Recipe** (master `57d0797`, run with `hatch run python`, every answer the
returned value or the exception's class name):
- *Addressing.* For each of the 17 keys `""`, `"."`, `"./"`, `".//"`,
  `"./."`, `"/"`, `"/./"`, `"/f"`, `"d/../f"`, `"f\0"`, `"d\\f"`, `"\\"`,
  `"d//f"`, `"d/./f"`, `"d/"`, `"f"`, `"d/f"`: `native_path(k)`,
  `resolve(k).key` and `to_key(native_path(k))` on `MemoryBackend`,
  `AsyncMemoryBackend` and a `LocalBackend` on a temp root.
- *Backslash.* A fresh store per call, per class, holding `f`, `"d\\f"`
  and `"e\\g/h"`; on `"d\\f"`, `"e\\g"` and `"\\"` run `exists`,
  `is_folder`, `is_file`, `read_bytes`, `get_file_info`, `delete`,
  `write(overwrite=True)`, `list_files(recursive=True)`, `get_folder_info`,
  `delete_folder(recursive=True)`, `move(k, "z")` and `move("f", k)` (the
  async class less `is_file` and `get_file_info`). Separately, on a store
  holding `d/f`, `write("d\\f")` and `list_files("", recursive=True)`.
- *`glob`.* A `LocalBackend` whose root holds `d/a.csv`, `d/sub/b.csv` and
  `top.csv`, with `outside.csv` beside the root, and an in-memory SQLite
  `SQLBlobBackend` holding the same three, over the patterns `"d/*.csv"`,
  `"./d/*.csv"`, `"d//*.csv"`, `"d/./*.csv"`, `"/d/*.csv"`, `"../*.csv"`,
  `"d/../*.csv"`, `"*/../*.csv"`, `"d\\*.csv"`, `"d/*\0"`, `"**/*.csv"`, plus
  `""` and `"."` on Local.

What came back: both Memory classes echo every key raw from `native_path`
and `resolve(k).key` except `"."`, whose `native_path` is `""`; Local's
`to_key` alone folds a backslash. `write("d\\f")` beside `d/f` returns path
`d/f`, both are read back distinctly, and the listing yields `d/f` twice.
The per-operation backslash answers are decision 6's Δ cells, and the
`glob` answers its **Later drivers** cells.
