# BK-389 — RFC-0017's kernel does not exist, so no backend can migrate onto it
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** Minted by BK-387 as all of RFC-0017 D3 step 1. The
maintainer's condition on
[ADR-0042](../adrs/0042-contract-kernel-over-thin-drivers.md): it stays
Proposed until the first backend runs on the new design, and it is accepted in
that PR.

**Split (2026-10-02, planning PR).** Under
[§ Completing work](../BACKLOG.md#how-this-file-works) "partly done", step 1
ships as two PRs, in this order. This item keeps the **kernel PR**, which runs
under the Proposed ADR. **BK-394** ([dossier](bk-394-memory-drivers-accept-adr-0042.md))
is the **Memory PR**: the two Memory drivers, every step-1 spec amendment, the
guide, its check script and the homepage snippet, and ADR-0042 and RFC-0017
set to Accepted. "That PR" in the paragraph above is BK-394's. **Both PRs
merge only after the v0.33.0 tag.** Items 2 (the Memory half), 4, 5, 6 and 7
of the original list moved verbatim to BK-394's dossier; the numbering below
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
   entry. Its fake-driver suite traces to existing spec IDs. BK-394 exports
   the public names RFC-0017 § Impact lists, together with the specs that
   describe them.

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
   no time is known.

**Depends on** BK-388, whose postconditions the kernel is written against.
As landed, the root rule is a postcondition ranked after the closed guard,
not a precondition, so the kernel's order per operation is closed
(`Live()`), then the root check on the key (`write`, the `move`/`copy`
source then destination), then the driver. On `write` and the destination
the check is `AddressesRoot`, the slash-and-dot segment test, wider than
`is_root`; on the source BE-029 requires only `is_root`, and the wider test
is permitted, not verified. Against an absent
container a `write` under the root is left to the backend spec (the Dafny
witness recreates the container), and `RequireCapability` answers after
close. The kernel decides root-ness on raw keys; the obligation for every
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
  the probe: `is_root` `False`, split `[]`). Once the kernel decides
  root-ness, what it hands the driver for such a key is the kernel's to fix;
  the read side follows BE-029, and the write side the `AddressesRoot`
  entry above.
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
