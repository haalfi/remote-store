# BK-450 — The driver boundary has no single enforcement point, so each kernel site re-checks a driver by hand
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit 023](../audits/audit-023-kernel-migration-readiness.md),
proposals P1, P5 and P6, at `52448e0`. Each finding below is a section of the
audit, with its probe, output and **Checked:** line; this dossier does not copy
them.

**One item, because one boundary.** Every part changes what crosses between
`Store`, kernel and driver, and every part takes its owners from BK-449's
states. Filed as one by the maintainer's choice; the parts can still land as
separate PRs under this ID.

**Parts** (advisory; untracked sub-bullets, no IDs):

- **T1 first, a defect today.** `FileInfo.metadata` is the stored dict and
  `WriteResult.metadata` the caller's; `copy` shares one dict between source and
  destination. Copy in `_file_info`, `_write_result` and `MemoryTree.copy`.
- **One decode step** for every `Entry`, `Page` and `PutResult`: domain and
  shape check, mapping copy, canonical-key omission, key under prefix, `stat`
  names its key. Carries T9, T15 (`metadata={}` echoed as `{}`), the return-shape
  row, and the canonical omission on listings.
- **One stream adapter and one fault rule** for `read`, `read_bytes` and the
  ranged read: one caught set, a close failure never masking a read failure,
  `__aiter__` inside the guard. Carries T4 and T5. The close failure's rule (logged, never raised, fed to
  `connection_dead`) is below, moved out of spec 052 until this part builds
  it; BK-449 already gave the async `read` and both runtimes'
  `read_bytes` SIO-010's skip. **Constraint** (from a review the maintainer
  brought to PR #1159, filed here by their choice, decision log
  `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl`): the rule must not
  swallow an integrity failure. Spec 052 BE-038 puts length and checksum checks at the
  client's own end-of-data read, where they raise before any close; an SDK that
  verifies a checksum or trailer only at close would have that failure logged as
  teardown noise. The adapter tells the two apart (a typed disposition: clean
  teardown, integrity verified or failed, the underlying error) and raises an
  integrity failure even after every byte was yielded.
- **One declaration record** validated at construction: `namespace` and
  `parents` in their domain, optional protocols implemented rather than
  inherited, `rename_replaces`, `ensure_parents`. Carries T2, T10 and the
  detection-message row.
- **Driver duties stated on the protocol and in BE-032 A.8:** the `open_write`
  and `commit` overwrite duty (T16), `src != dst` as a kernel guarantee, the
  native-aggregate omission (T13; Memory's `folder_stats` counts every node),
  `container_absent` for untyped errors only. BK-449 added a row: an overwrite
  conflict, refused in one wire step at `commit` or `put` (now in spec 053 A.8's driver
  list), is typed `AlreadyExists`, which nothing checks. The other driver
  duties (idempotent `close`, BE-034; `abort` after a failed `commit`, BE-039;
  end of data at the client's own end-of-data read, BE-038; transport-level
  `connection_dead`, 052's Terms) are stated on the protocol docstrings; since
  BK-456's 052 prune, Memory's drivers have cells for BE-038 and BE-039
  (`tests/backends/memory/test_driver_duties.py`), and no other driver does. One more, unstated anywhere: a
  `put` that returns success has consumed all of the caller's async content.
  A driver that returns early has truncated the write; the kernel closes the
  iterator it left suspended (spec 052 BE-033's exit table) and reports success.
  Found by PR #1159's closing measuring pass.
- **One meaning per capability flag, checked in each runtime** (P5, T6):
  `LAZY_READ` as per-chunk pull, `SEEKABLE_READ` withheld by async backends,
  async Memory withdrawing both, an async cell replacing the e2e exemption.
- **One owner per check between `Store` and kernel** (P6): capability gating,
  path validation and normalisation, error-path attribution. Carries T12's
  prose half (BE-027) and the error-path row.

Each part's owner (kernel check, driver obligation or `Session` obligation) is
audit-023 P1's table; re-derive it against BK-449's outcome, spec 052 BE-033 to
BE-039 and spec 053 A.8's driver list, before acting.

**Due:** before RFC-0017 D3 step 2, after BK-449. The P6 part changes no driver
code and may trail to step 8.

## Moved out of spec 052, 2026-10-20

Verbatim from `sdd/specs/052-backend-lifetime.md` at `6e4c4fd`, by BK-456's
052 prune: no read path meets the row (measured at `fc8a644`: sync `read`
suppresses a close failure silently, `_stream.py:243`; async `read` lets it
propagate, `aio_backend.py:65-67`; `read_bytes` maps it through the choke and
raises it, `_kernel/_async/kernel.py:734-737`), and no test marks it, so it is
intent, which a spec does not carry ([`SPEC-DESIGN.md` Ready item 3](../SPEC-DESIGN.md#ready)).
When this item builds the stream adapter, the rule goes back as a row of spec
052 BE-035. A dated record, not kept current.

BE-033, Exit owners:

> | a read stream's close that fails after a successful read | the kernel's stream adapter | the close failure is logged, never raised, and fed to `connection_dead`; a read failure outranks a close failure |
