# BK-405 — `ext.glob.glob_files` answers a non-canonical pattern differently by capability tier
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Filed on 2026-10-03 in BK-395's PR (#1061),
rounds 9 and 10, while deciding the kernel's `glob` pattern rule (BK-389's
dossier, decision 6). The divergence exists on master, independent of the
kernel.

**What it is.** `glob_files` delegates to `Store.glob` on a store declaring
`GLOB` (GLOB-010), whose backend handles the pattern natively, and otherwise
falls back to `extract_prefix`, `list_files` and `pattern_to_regex` over the
pattern exactly as given (GLOB-011, GLOB-012, GLOB-014). A non-canonical
pattern therefore answers by tier: the fallback's regex is anchored on the
raw pattern, so `"./d/*.csv"` can never match the key `d/a.csv`.

**Recipe** (run with `hatch run python` on the PR head, whose `src/` equals
master `ffce774`'s, `git diff --stat ffce774 HEAD -- src` empty): a `Store`
over `MemoryBackend` (no `GLOB`) and one over a `LocalBackend` on a temp
root (`GLOB`), each holding `d/a.csv`, `d/sub/b.csv` and `top.csv`;
`glob_files(store, p)` for each pattern below.

| Pattern | Memory (fallback) | Local (`GLOB`) |
|---|---|---|
| `"d/*.csv"` | `['d/a.csv']` | `['d/a.csv']` |
| `"./d/*.csv"` | `[]` | `['d/a.csv']` |
| `"d//*.csv"` | `[]` | `['d/a.csv']` |
| `"d/./*.csv"` | `[]` | `['d/a.csv']` |
| `"d/*/."` | `[]` | `['d/a.csv']` |
| `"/d/*.csv"` | `[]` | `NotImplementedError` |

Once a `GLOB` driver runs on BK-389's kernel, its column follows decision
6's pattern rule instead, which agrees with Local's on every row but the
last.

**The open decision: a leading `/`.** On a `GLOB` store with a non-empty
`root_path` the kernel sees the root-joined pattern, not the caller's:
`Store.glob` prepends the root raw (`f"{root}/{pattern}"` only when the
root is non-empty, GLOB-007, `_store.py`), so the kernel refuses
`"/d/*.csv"` with `InvalidPath` under an empty root and drops the
resulting empty segment, matching, under a non-empty one (BK-389's
dossier, decision 6, Later drivers). Aligning the fallback with "the
kernel's rule" therefore needs a choice: refuse a leading `/` (agreeing
with the `GLOB` tier only under an empty root), strip it (agreeing only
under a non-empty root), or change GLOB-007 so `Store.glob` itself treats
it one way under any root.

**Advisory prescription.** Normalise the pattern in the fallback by
decision 6's rule (refusals, then dropping empty and `.` segments, keeping
a literal trailing `/`) before `extract_prefix`, once the leading-`/`
choice is made, and pin the table above as cross-tier conformance cells.

**Outcome (2026-10-17).** The leading `/` is stripped, by changing GLOB-007:
`Store.glob`, `AsyncStore.glob` and the fallback all read a pattern as spec
004 reads a path, before the root prepend. Why strip and not refuse: a pattern
is a predicate over Keys, no Key carries a leading `/` (spec 051 TREE-011), so
`"/d/*.csv"` can only name what `"d/*.csv"` names, and `read`, `exists` and
`list_files` already accept that spelling through PATH-004. The kernel's
refusal of a leading `/` (decision 6) stays where it is, at the backend
boundary, which `Store` now never reaches with one. Diverges from the
prescription in one point: `..` and a null byte are refused, as PATH-003 and
PATH-007 refuse them; a backslash is left to BK-447. Re-run of the recipe
above on the fix's branch, under `root_path` `""` and `"r"`: all six rows
answer `['d/a.csv']` on both tiers, 12 of 12, the last row included. The
pinning cells are
`tests/ext/test_glob.py::TestGlobFiles::test_tiers_agree_on_pattern_spelling`.
