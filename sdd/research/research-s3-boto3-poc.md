# Research: `s3-boto3` backend lane — PoC and disposition

**Item ID:** ID-202
**Date:** 2026-06-01
**Method:** Built a standalone boto3-direct backend (`S3Boto3Backend`) and ran the full Stage-1 conformance suite against it under in-process moto; measured maintenance cost from the landed diff; assessed interop by reading the extension call paths.
**Status:** PoC complete (landed test-only). Disposition below is advisory — the user decides whether to promote, park, or reject.

---

## 1. Question

Three of the S3 pains the `s3` / `s3-pyarrow` lanes carry are *s3fs-specific*
and cannot be fixed from our side:

1. **aiobotocore dep-pin cascade.** `s3` pulls `s3fs` → `aiobotocore` → a
   pinned `botocore`, which can collide with a user's own `boto3`.
2. **>5 GB multipart-restart cliff** (s3fs-fuse #1936).
3. **fsspec listing-cache staleness** (fsspec/filesystem_spec #324; the
   subject of ID-201).

A boto3-direct backend has none of them. ID-202 asks: does a third S3 lane
justify its maintenance cost? Decide on three axes — user value, maintenance
cost, interop loss — and record one of **Ship / Park / Reject**.

## 2. What the PoC delivers

- **`src/remote_store/backends/_s3_boto3.py`** — `S3Boto3Backend`, a standalone
  `Backend` subclass (not `_S3Base`; see § 4). boto3-only: `get_object` Range
  reads for a seekable lazy `read()`, `put_object` / `upload_fileobj` +
  `TransferConfig` for writes, paginated `list_objects_v2` for the control
  path, `copy_object` + `delete_objects` for move/copy/delete-folder.
- **Capability parity with `S3Backend`** — all capabilities except
  `ATOMIC_MOVE` (move is a non-atomic copy+delete), including `SEEKABLE_READ`
  (delivered by a Range-request reader modelled on `_AzureRangeReader`),
  `LAZY_READ`, `WRITE_RESULT_NATIVE`, and `USER_METADATA`.
- **Typed-error mapping** built from `ClientError.response['Error']['Code']`
  directly (see [research-s3-error-mapping-fidelity.md](research-s3-error-mapping-fidelity.md)):
  404 → `NotFound`; 403 and the credential codes (`AccessDenied`,
  `InvalidAccessKeyId`, `SignatureDoesNotMatch`, `ExpiredToken`) →
  `PermissionDenied`; 5xx / endpoint errors → `BackendUnavailable`.
- **Extra (proposed, not landed)** `s3-boto3 = ["boto3>=1.34"]` — a single
  dependency, no `aiobotocore`. Deliberately *not* declared in `pyproject.toml`
  yet: declaring it would surface `pip install remote-store[s3-boto3]` in the
  generated user-facing `FEATURES.md` / tested-versions docs, advertising an
  install path for a backend that is not registered (a config `type =
  "s3-boto3"` would not resolve). The lane's tests run on the `boto3` already
  present in the dev/bench environments; the extra lands with the Ship
  increment (§ 6).
- **Conformance fixtures** `s3_boto3_moto` (+ `s3_boto3_moto_strict` for the
  file-ancestor opt-in), wired through the declarative `backends.toml` /
  `fixtures.toml` registry and instantiated directly (no public backend
  registration — the lane is test-only pending this disposition).
- **Targeted tests** (`tests/backends/s3/test_boto3.py`): a mid-stream-abort
  test (see § 3a), the error-code → typed-error mapping rows, a moto 404
  round trip, and opt-in live tests (a real-403 mapping check and a >5 GB
  multipart smoke, both gated and never run in `hatch run all`).

**Conformance result:** the full Stage-1 surface passes against
`s3_boto3_moto` and `s3_boto3_moto_strict` under moto (189 parametrized
cases for the default fixture; the strict fixture adds the file-ancestor
error-fidelity set). No production-code divergence was needed elsewhere.

## 3. Findings by axis

### (a) User value

All three retired pains are real, and the PoC adds a fourth win:

- **aiobotocore cascade gone.** The lane depends only on `boto3`. A user who
  already pins `boto3` for their own SDK use installs `remote-store[s3-boto3]`
  with no transitive `aiobotocore`/`botocore` pin to reconcile.
- **>5 GB cliff gone.** `boto3.s3.transfer.TransferConfig` handles multipart
  without the s3fs-fuse restart bug. The opt-in `test_multipart_above_5gb_has_no_cliff`
  smoke proves a 5 GiB + 1 byte object round-trips by size.
- **Listing-cache staleness gone.** The lane keeps no listing cache; every
  `list_*` is a fresh `list_objects_v2`. (This is the read-after-write
  correctness ID-201 is spiking for the s3fs lane — the boto3 lane sidesteps
  it structurally, at the cost of never serving a listing from cache.)
- **BUG-214 not inherited.** The s3fs lane committed a *truncated-but-complete*
  object when the content source failed mid-stream (BUG-214). The boto3 lane
  cannot: `put_object` never sends a partial body, and `upload_fileobj` aborts
  the multipart upload on a reader exception. The mid-stream-abort test asserts
  neither an object nor an orphaned multipart upload survives — the guarantee
  holds **by construction**, with no `discard()`-style fix.

Cost side: a third S3 lane is a third thing for a citizen developer to choose
between (`s3` vs `s3-pyarrow` vs `s3-boto3`). Choice-paralysis is a genuine
DX tax for the project's primary audience, and the three lanes' differences
are subtle (control vs data path, fsspec-shape vs not).

### (b) Maintenance cost

Measured from the landed diff (non-blank, non-comment lines):

| File | Lines (code) | Note |
|---|---|---|
| `_s3_boto3.py` | ~625 | Standalone backend |
| `_s3.py` (`S3Backend`) | ~280 | Leans on `_s3_base.py` |
| `_s3_base.py` (shared) | ~409 | Reused by `s3` + `s3-pyarrow` |
| `_s3_pyarrow.py` | ~430 | Leans on `_s3_base.py` |
| `tests/.../test_boto3.py` | ~272 | Targeted tests |
| `tests/.../fixtures/s3_boto3_moto.py` | ~58 | Fixture factory |

The headline cost: **`_s3_boto3.py` is standalone (~625 lines)** because
`_S3Base`'s listing and metadata methods are s3fs-coupled
(`self._s3fs.ls(...)`) and cannot be reused. It reuses only the three
SDK-agnostic free functions (`_normalize_endpoint_url`, `_resolve_tls_ca_bundle`,
`_validate_tls_ca_bundle`) and reimplements the HeadObject → `FileInfo`
parsing. So the lane roughly *doubles* the per-backend S3 code that
`_S3Base` was created to avoid duplicating.

Test-matrix expansion: one new fixture family runs the full conformance
surface under moto (the `s3_boto3` slice is ~17 s wall-clock in-process,
serial). No new container or live dependency in the default gate.

A promotion to a first-class lane would add more: an `AsyncS3Boto3Backend`
(currently out of scope), public registry/`_info`/`__all__`/`FEATURES`
wiring, a setup guide, and ongoing boto3 API-drift maintenance for the
multipart and pagination edge cases `_S3Base` already shields the other
lanes from.

### (c) Interop loss

Smaller than feared. The downstream extensions are built on the **`Store`
API**, not on a native fsspec handle:

- **`ext.arrow` / `ext.parquet`.** `StoreFileSystemHandler` probes
  `store.unwrap(pyarrow.fs.FileSystem)` for a Tier-1 native-PyArrow fast
  path and **falls back gracefully** to the Store-API read/write path when
  the backend does not expose one. The boto3 lane's `unwrap` returns only a
  `botocore.client.BaseClient`, so it takes the fallback — but so does the
  plain `s3` (s3fs) lane, which also does not unwrap to a PyArrow
  `FileSystem`. **The boto3 lane is therefore on par with `s3` for Arrow /
  Parquet; only `s3-pyarrow` gets the Tier-1 zero-copy path.**
- **`ext.dagster`.** Reads and writes through the `Store` API; works
  unchanged.

The one genuine loss: a user who calls `store.unwrap(s3fs.S3FileSystem)` to
drive an fsspec-native workflow gets a `botocore` client instead. That is a
niche escape hatch, and the `s3` / `s3-pyarrow` lanes remain available for it.

## 4. Design note: why standalone, not `_S3Base`

The backlog suggested sharing `_S3Base` "where sensible". In practice the
sensible-to-share surface is small: `_S3Base`'s listing / metadata methods
(`list_files`, `list_folders`, `iter_children`, `get_folder_info`) all call
`self._s3fs.ls(...)` and assume an fsspec instance, and the abstract `_s3fs`
property has no boto3 analogue. The boto3 lane reuses the three module-level
free functions and reimplements the rest.

A cleaner factoring exists — split `_S3Base` into an SDK-agnostic base (path
helpers, HeadObject → `FileInfo`, error scaffolding) plus an s3fs-listing
layer, so all three lanes inherit the agnostic part. That refactor touches
the two shipped S3 backends and must keep their conformance green, so it is
deliberately **not** done in the PoC: it is work the **Ship** path would
absorb, not speculative churn a **Reject** would waste.

## 4a. Known cross-lane differences and caveats (record before Ship)

Surfaced in PR review. None block the Park PoC; each is a Ship-promotion item.

- **Borrowed spec marks.** The lane marks the s3fs-lane error IDs
  (`S3-015`/`016`/`018`) directly. `S3-018`'s postcondition literally names
  `backend == "s3"`, and `S3-017` covers *connection* errors only — so the 5xx
  → `BackendUnavailable` rows are intentionally left **unmarked** (no spec
  clause maps server 5xx responses). Borrowing is acceptable for a test-only
  Park; a Ship promotion needs a dedicated `S3B-*` spec block (or generalized
  `S3-018` postconditions), mirroring how the pyarrow lane created
  `S3PA-018`/`S3PA-019` that *reference* the `S3-*` IDs.
- **`read()` vs `read_seekable()` buffering.** Each `_S3RangeReader.readinto`
  is one ranged `GetObject`. `read()` wraps it in a 1 MiB `BufferedReader`, so a
  sequential consume issues ~1 GET per MiB rather than ~1 GET per 8 KiB
  `readall()` chunk; bulk sequential reads should still prefer `read_bytes`
  (single GET). `read_seekable()` — the path PyArrow's random `read_at` uses
  (`ext.arrow` Tier-3 → `pa.PythonFile`) — is deliberately **not** buffered: a
  `BufferedReader` invalidates its buffer on every `seek()`, so each small
  `read_at` would otherwise pay a full 1 MiB GET and refetch overlapping ranges.
  The override returns the bare Range reader, keeping each `read_at` to one GET
  of the requested range. This matches the Azure / S3PyArrow "no `BufferedReader`
  on the seekable path" contract (`_azure.py` `read_seekable`).
- **Exact-key overwrite / collision check.** The `overwrite=False` and
  dst-collision guards in `write` / `open_atomic` / `move` / `copy` use an
  exact-key HEAD, not a prefix-exists probe. So `write("a/b")` when only
  `a/b/c` exists proceeds here, whereas the s3fs lane raises `AlreadyExists`
  (its `exists()` is `True` for a prefix). The boto3 behavior is arguably more
  correct for a flat namespace (a prefix is not an object), and no conformance
  test covers write-over-prefix — but it is a behavioral divergence a Ship
  promotion would expose to users migrating from the `s3` lane.
- **`copy` / `move` > 5 GB.** `copy_object` is a single-part server-side copy,
  which S3 caps at 5 GB; larger objects need a multipart copy
  (`UploadPartCopy`), which the s3fs lane's `copy` handles internally. So the
  headline >5 GB *upload* win (via `TransferConfig`) does **not** extend to the
  *copy* path — a Ship promotion needs multipart-copy support for parity.

## 5. Reproduction

```
# Conformance (Stage 1, moto, in-process):
hatch run test tests/backends -k s3_boto3

# Targeted error-mapping + BUG-214 abort tests:
hatch run test tests/backends/s3/test_boto3.py

# Opt-in live checks (real AWS; never in `hatch run all`):
RS_TEST_LIVE_S3=1 hatch run pytest -m live tests/backends/s3/test_boto3.py
RS_TEST_LIVE_S3=1 RS_TEST_S3_5GB=1 hatch run pytest -m live \
    tests/backends/s3/test_boto3.py -k 5gb
```

## 6. Disposition (advisory)

**Recommendation: Park as test-only.** Keep the landed PoC in the tree behind
its conformance fixtures, but do **not** promote it to a first-class
user-facing lane yet (no registry / `_info` / `__all__` / `FEATURES` wiring,
no async variant, no CHANGELOG entry). Revisit promotion when either trigger
fires:

1. **s3fs upstream stalls** on the >5 GB (#1936) or listing-cache (#324)
   issues such that the `s3` lane's correctness gap becomes a shipped-user
   problem; or
2. **the aiobotocore dep-pin cascade bites a real user** (a reported install
   conflict against their own `boto3`).

Rationale: the lane is *viable and correct* (full conformance parity,
BUG-214 avoided by construction, minimal interop loss) and genuinely retires
all three pains — but for today's users the `s3` and `s3-pyarrow` lanes cover
the same surface, so promoting a third install path now buys mostly
choice-paralysis and a doubled per-backend maintenance footprint for a
marginal gain. Landing it test-only preserves the work and keeps it
conformance-green against every future change, so the promotion cost is a
docs/wiring/async increment rather than a from-scratch rebuild whenever a
trigger fires.

**If the user chooses Ship instead**, the increment is: the `_S3Base`
refactor in § 4, declaring the `s3-boto3` extra in `pyproject.toml` (with its
drift-lock baseline), public wiring (`_registry.py`, `_info._BACKEND_EXTRAS`,
`backends/__init__.__all__`, regenerated `FEATURES.md`), an
`AsyncS3Boto3Backend`, a `guides/backends/` page positioning the three lanes
as peers, and a user-facing CHANGELOG entry — each a follow-up `BK-NNN`.

**If the user chooses Reject**, archive this note as the rationale for not
splitting the S3 surface and remove the test-only lane; the boto3 escape
hatch remains available via `store.unwrap()` on the existing lanes.
