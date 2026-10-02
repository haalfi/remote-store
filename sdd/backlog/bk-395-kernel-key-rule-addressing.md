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
     every raw key (`"./"`, `"d//f"`, `"/f"`, `"d/../f"`, `"f\0"`), and
     `resolve(".")` gives `plan.key == "."`.
   - The withdrawn table made `native_path` and `resolve` raise on refused
     keys, and changed `resolve(".")`'s `plan.key` to `""`.
2. **A key holding a backslash.**
   - Memory stores `d\f` today, but PATH-002 and `BackendContract.dfy` §5a
     (`WellFormedPath`) exclude a backslash, and spec 003 (BE-029) says such
     a key "is not canonical".
   - `RemotePath` cannot hold a backslash. So every path Memory returns for
     that key folds it to `d/f`: `WriteResult`, `FileInfo` (both classes),
     and listings, where `list_files` over `d/f` and `d\f` yields `d/f`
     twice. Measured by round 5's measuring reviewer.
3. **`glob` patterns.** `glob` is one of the 21 members the kernel
   implements, and it reaches `SupportsGlob`. Nothing yet says whether a
   pattern's literal prefix gets the refusals and normalisation.

**The maintainer's preferred answers, recorded at the ceiling and not yet
verified against the clauses above:**

1. Addressing stays total. Root and non-canonical spellings are normalised;
   refused keys go to the driver raw, round-tripping as BE-025 says.
   `plan.key` stays the caller's key; only `native_path` is canonicalised.
2. A backslash is refused with `InvalidPath`, matching PATH-002 and §5a.
   That is a step-1 Memory cell change, since Memory stores `d\f` today.
3. A pattern's literal prefix, up to the first wildcard, goes through the
   pipeline. The wildcard part goes to `SupportsGlob` unchanged.

**Exit criteria:** each of the three is decided and added to BK-389's
decision 6, as a column or row of its table, or as a stated exclusion with
its reason. Each step-1 Memory cell it changes is listed in BK-394's item 2.
Any clause it contradicts is amended in BK-394's spec list.
