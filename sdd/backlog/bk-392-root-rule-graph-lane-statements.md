# BK-392 — Root-rule and Graph-lane statements contradict what BK-388 measured
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** PR #1047 (BK-388) changed what spec 003 says about
the root-destination guard and the Graph replay lane. Its closing review
panels found seven older statements, six measured false and one to check. They were
filed here rather than fixed, because they sit outside that PR's model-only
scope.

**The sites.**

| # | Site | Says | Measured |
|---|---|---|---|
| 1 | spec 003, BE-029's Graph coverage row | "the five file-shaped operations other than the `move`/`copy` source" | Graph is async: `_ASYNC_ROOT_FILE_OPS` (`tests/backends/conformance/test_async_extended.py`) lists six, of which four are not the `move`/`copy` source |
| 2 | spec 003, BE-021's Graph paragraph ("Its lane skips both new rosters, because those seed through `write`") | Graph's lane cannot run the root-refusal cells | at BK-388's round-4 head, `pytest -k "graph_replay and TestBackendRootPath"` gave 8 passed: the `move`/`copy` source cells and the root-destination cell, all key-decided and unseeded (BK-388 trace) |
| 3 | `tests/backends/graph/aio/test_backend.py`, the docstring calling the root-refusal cells conformance-unreachable | the same | as row 2 |
| 4 | `src/remote_store/backends/_flat_ns.py`, the root-destination guard's docstring | with the container present the destination probe reports a directory, "true there and measured both ways" | with a missing source the guard changes the error class (below) |
| 5 | `src/remote_store/backends/_local.py`, `_reject_root_as_write_target` | "With the root present … the guard changes only the message" | as row 4 |
| 6 | `src/remote_store/backends/_sftp.py`, its route into the same guard | "With it present … the guard changes the message and not the verdict" | as row 4 |
| 7 | `tests/backends/conformance/test_io.py`, `test_root_as_move_or_copy_destination_is_refused` | on a hierarchical backend "this cell only changes the message" | not measured: that cell seeds its source, so the claim may hold for it; check before rewording |

Sites 5 and 6 defer to site 4's docstring ("whose docstring carries the
rule"), so site 4 is the one to correct first. Rows 4 to 6 state the
message-only claim without qualifying the source's existence, and the
measurement below uses a missing source.

**The measurement behind rows 4 to 6.** It uses a `LocalBackend` over a fresh
temporary directory, so the root is present, and a source that does not exist.
`move("missing.txt", "")` and `copy("missing.txt", "")` answer `InvalidPath`
with the guard in place. With `remote_store.backends._flat_ns._reject_root_as_write_target`
patched to a no-op (`unittest.mock.patch.object`; `_local.py` imports it inside
the method, so the patch reaches it), both answer `NotFound`. That is the
source check firing first. So on a present container the guard is what
satisfies BE-018's root-destination carve-out; it does not merely reword the
error. The conformance cell `test_root_destination_outranks_a_missing_source`
pins the guarded outcome on every lane.

**Decision.** None open. Each site is reworded to the measured behaviour.
