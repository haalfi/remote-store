# Formal Verification Layer (`sdd/formal/`)

Dafny specifications modelling the remote-store backend behavioural
contract.  These files are **specification artefacts**, not runtime code.

## Purpose

The 0.21.1 patch release fixed 22 bugs.  Root-cause analysis (BK-140)
identified six gaps in the backend ABC where behaviour was unspecified
and backends diverged.  This verification layer encodes those
requirements as machine-checkable pre/postconditions so that:

1. The contract itself is **internally consistent** — no postcondition
   contradicts another.
2. The contract is **satisfiable** — at least one implementation
   (MemoryBackend) meets every postcondition.
3. Key **algebraic properties** hold by construction — depth-filter
   inclusivity, resource-leak freedom, precondition ordering.

## Files

| File | What it models | BK-140 gaps |
|------|---------------|-------------|
| `BackendContract.dfy` | Abstract backend trait — error model, capabilities, all operation pre/postconditions | Gaps 1–5 |
| `MemoryBackend.dfy` | Reference refinement proving the contract is satisfiable | All |
| `DepthCounting.dfy` | Verified `DEPTH-001` algorithm and four depth properties | Gap 4 |
| `ResourceSafety.dfy` | Handle lifecycle, `_safe_wrap` invariant, move atomicity state machine, connection lifecycle | Gaps 5, 6 |

## Gap coverage

| # | Gap | Spec | Dafny encoding | Caveat |
|---|-----|------|----------------|--------|
| 1 | Precondition evaluation order | BE-008 | `Write` postconditions: `IsDir → InvalidPath` before `IsFile && !overwrite → AlreadyExists`. Mutually exclusive by `EntryPartition`. | Error-path frame condition (`fs == old(fs)` on error) not machine-checked; verified in MemoryBackend by construction only. |
| 2 | Canonical error-mapping table | BE-021 | `Read`/`Delete`/`GetFileInfo`/`Move`/`Copy`: directory → `InvalidPath`, missing → `NotFound` | Same frame condition caveat as Gap 1. |
| 3 | Listing on missing paths | BE-014/015 | `ListFiles`/`ListFolders`: `ensures r.Ok?` + empty on missing + completeness lower bound | Fully machine-checked (upper + lower bounds). |
| 4 | Depth-counting algorithm | DEPTH-001 | `DepthCounting.dfy`: reference algorithm + 5 proved lemmas (`ChildHasNonNegativeDepth`, `calc` blocks). Depth filter requires `Depth >= 0`. | Fully machine-checked. |
| 5 | Move atomicity | BE-018 | `ResourceSafety.dfy` `MovePhase` state machine: atomic vs copy-delete | |
| 6 | Acquire-then-wrap safety | SIO-001 | `ResourceSafety.dfy` `SafeWrap`/`UnsafeWrap`: leak-freedom proof | |

## Running the verifier

Install [Dafny](https://github.com/dafny-lang/dafny) (v4.9.1+), then:

```bash
dafny verify sdd/formal/BackendContract.dfy
dafny verify sdd/formal/MemoryBackend.dfy
dafny verify sdd/formal/DepthCounting.dfy
dafny verify sdd/formal/ResourceSafety.dfy
```

CI runs the `verify-formal` job automatically when `sdd/formal/` or
`sdd/specs/` files change.

## Verification practices

These files follow Dafny best practices to keep proofs small, stable,
and maintainable:

- **`assert` breadcrumbs**: Every branch in MemoryBackend methods has
  explicit assertions guiding the solver to the postcondition, rather
  than relying on it to search the full state space.
- **`calc` blocks**: Depth arithmetic uses step-by-step calculation
  chains so the proof is readable and solver-stable.
- **No empty lemma bodies**: Every lemma has an explicit proof or
  at minimum assert breadcrumbs.  "Obvious" facts are still spelled out.
- **Non-vacuous refinements**: MemoryBackend.ListFiles iterates the map
  and filters by child-prefix, depth, and recursive flag, rather than
  returning `[]` to trivially satisfy postconditions.
- **`old(fs)` convention**: All mutating method precondition checks
  use `old(fs)` to prevent post-state mutations from affecting
  error-path reasoning.
- **`src == dst` handling**: Move and Copy explicitly handle self-move
  and self-copy as no-ops, with assertions proving each postcondition
  holds for the identity case.

## Dafny ↔ Hypothesis PBT cross-reference

Each Dafny postcondition has a planned corresponding Hypothesis
property test.  Dafny proves the property for all inputs structurally;
Hypothesis will stress-test the Python implementation with randomised
inputs.  Test names below are the target names for BK-139b / BK-140a;
some may not yet exist in the `tests/` directory.

### Backend contract properties

| Dafny postcondition | Test | Property |
|---|---|---|
| `Write: IsDir(old(fs)) → InvalidPath` | `test_write_on_directory_raises_error` | `write(dir)` → error, never `AlreadyExists` |
| `Write: IsDir + overwrite=True → InvalidPath` | `test_write_on_directory_overwrite_still_raises_error` | Precondition ordering: type check before overwrite |
| `Read: IsDir → InvalidPath` | `test_read_on_directory_raises_error` | `read(dir)` → error |
| `Read: !PathExists → NotFound` | `test_read_missing_raises_not_found` | `read(missing)` → `NotFound` |
| `Delete: IsDir → InvalidPath` | `test_delete_on_directory_raises_error` | `delete(dir)` → error |
| `DeleteFolder: IsFile → InvalidPath` | `test_delete_folder_on_file_raises_error` | `delete_folder(file)` → error |
| `DeleteFolder: !recursive + HasChildren` | `test_delete_folder_non_recursive_non_empty_raises` | → `DirectoryNotEmpty` |
| `GetFileInfo: IsDir → InvalidPath` | `test_get_file_info_on_directory_raises_error` | `get_file_info(dir)` → error |
| `ListFiles: ensures r.Ok?` | `test_list_files_missing_path_yields_empty` | `list_files(missing)` → `[]`, no error |
| `ListFiles: depth ≤ max_depth` | `test_list_files_recursive_max_depth` | Depth boundary inclusive |
| `ListFiles: completeness` | `test_list_files_all_results_are_children` | All results are children of path |
| `ListFolders: ensures r.Ok?` | `test_list_folders_missing_path_yields_empty` | `list_folders(missing)` → `[]` |
| `Move/Copy: IsDir(src) → InvalidPath` | `test_source_is_directory_raises_error` | dir src → error |
| `Move/Copy: IsDir(dst) → InvalidPath` | `test_destination_is_directory_raises_error` | dir dst → error |
| `Move/Copy: src==dst → no-op` | `test_self_copy_preserves_data`, `test_self_move_preserves_data` | Data preserved |
| `WriteReadConsistency` lemma | `test_roundtrip`, P4 stateful model | `write(p,c); read(p) == c` |
| `MoveIsNotNoop` lemma | `test_move_removes_source`, P4 stateful model | `move(a,b)` changes filesystem |

### Depth counting properties

| Dafny lemma | Hypothesis test | Property |
|---|---|---|
| `ImmediateChildDepthIsZero` | `test_depth_immediate_child` | `depth("r", "r/f") == 0` |
| `MaxDepthZeroIsImmediate` | `test_list_max_depth_zero` | `max_depth=0` → immediate children only |
| `DepthFilterIsInclusive` | `test_depth_filter_boundary` | `depth==N` passes `filter(N)` |
| `DepthFilterExcludesDeeper` | `test_depth_filter_boundary` | `depth==N+1` fails `filter(N)` |

### Resource safety properties

| Dafny method/lemma | Hypothesis test | Property |
|---|---|---|
| `SafeWrap` + `SafeWrapImpliesNoLeaks` | `test_safe_wrap_no_leak` | `_safe_wrap` never leaks handles |
| `UnsafeWrap` | `test_unsafe_wrap_leaks` | Pre-fix pattern leaks raw handle |
| `SafeConnect` + `SafeConnectNeverLeaks` | `test_sftp_connect_cleanup` | SFTP client closed on failure |
| `CopyDeleteMove` | `test_move_copy_delete_partial` | Partial move raises error, not silent dup |

## Relationship to Python code

| Layer | Source of truth | Verified by |
|-------|----------------|-------------|
| Spec (`.md`) | Human-readable requirements | Review |
| Dafny (`.dfy`) | Machine-checkable contract | Dafny verifier |
| Python (`_backend.py`) | Runtime implementation | pytest + Hypothesis PBT |

The Dafny model is **not** auto-generated from Python.  It is a
parallel specification that must be kept in sync with spec amendments
(BK-140).  When a spec changes, the corresponding Dafny postcondition
is updated; if the verifier rejects it, the spec has an internal
contradiction.

## Design decisions

- **Abstract trait, not class extraction.** Dafny models the *contract*,
  not the Python class hierarchy.  This keeps the model small and
  focused on behavioural properties.
- **MemoryBackend as oracle.** The Dafny MemoryBackend is the reference
  implementation.  Property-based tests (BK-139a P4) use the Python
  MemoryBackend as their oracle.  Both must agree.
- **Resource safety as state machine.** Pre/postconditions alone
  cannot express temporal properties (handle acquired then leaked).
  `ResourceSafety.dfy` uses explicit state tracking to model and
  prove these.
- **Safe/Unsafe pairs.** Each safety property is demonstrated with both
  a correct implementation (proves the invariant holds) and a buggy
  implementation (proves the invariant *fails*).  This shows the
  invariant is not vacuously true.
- **No error-path frame condition.** `ensures r.Err? ==> fs == old(fs)`
  would be ideal but `r.Err?` taints method bodies as
  specification-only in Dafny, preventing compiled assignments and
  return statements.  The MemoryBackend preserves `fs` on error paths
  by construction instead.
