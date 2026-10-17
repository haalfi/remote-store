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
  `__aiter__` inside the guard. Carries T4 and T5. BE-033 states the close
  failure's rule (logged, never raised, fed to `connection_dead`) as *not yet
  met* by this part; BK-449 already gave the async `read` and both runtimes'
  `read_bytes` SIO-010's skip. **Constraint** (from a review the maintainer
  brought to PR #1159, filed here by their choice, decision log
  `sdd/decisions/062e5181-cc50-5b17-963f-e9da78bad8ee.jsonl`): the rule must not
  swallow an integrity failure. BE-033 puts length and checksum checks at the
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
  conflict, refused in one wire step at `commit` or `put` (BE-033's exit
  owners), is typed `AlreadyExists`, which nothing checks. BE-033's other driver
  rows (idempotent `close`, `abort` after a failed `commit`, end of data at the
  client's own end-of-data read, transport-level `connection_dead`) are stated
  on the protocol docstrings and unchecked too. One more, unstated anywhere: a
  `put` that returns success has consumed all of the caller's async content.
  A driver that returns early has truncated the write; the kernel closes the
  iterator it left suspended (BE-033's exit-owner row) and reports success.
  Found by PR #1159's closing measuring pass.
- **One meaning per capability flag, checked in each runtime** (P5, T6):
  `LAZY_READ` as per-chunk pull, `SEEKABLE_READ` withheld by async backends,
  async Memory withdrawing both, an async cell replacing the e2e exemption.
- **One owner per check between `Store` and kernel** (P6): capability gating,
  path validation and normalisation, error-path attribution. Carries T12's
  prose half (BE-027) and the error-path row.

Each part's owner (kernel check, driver obligation or `Session` obligation) is
audit-023 P1's table; re-derive it against BK-449's outcome, spec 003 BE-033's
exit-owner table, before acting.

**Due:** before RFC-0017 D3 step 2, after BK-449. The P6 part changes no driver
code and may trail to step 8.
