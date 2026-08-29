# Migration Guide

Breaking changes and upgrade paths between `remote-store` versions.

`remote-store` has been published on PyPI since v0.11.0 (first Beta release).
The core Store API is stable, but extensions may evolve. This page documents
changes that require action when upgrading.

## v0.30.0 to v0.31.0

**SFTP reads and writes are now bounded by default:**

In v0.30.0, an SFTP read or write that stalled on an already-open channel had no
bound and no way to set one. v0.31.0 adds `SFTPBackend(io_timeout=...)` and
defaults it to `120.0` seconds, so every caller is affected whether or not they
configure anything.

**If your server legitimately pauses for minutes, raise the bound rather than
removing it:**

```python
backend = SFTPBackend(host="files.example.com", username="deploy", io_timeout=300)
```

That is the usual answer for an antivirus or dedup appliance that goes quiet on
`open()` of a large file: you keep the protection and move the threshold past
your server's longest legitimate pause.

**To remove the bound entirely, pass `None`:**

```python
backend = SFTPBackend(host="files.example.com", username="deploy", io_timeout=None)
```

That restores the unbounded channel, and only that — the other v0.31.0 change on
this backend, in the next section, applies whatever you pass here. Note `0` is
**not** the opt-out — it raises `ValueError`, because paramiko reads it as
non-blocking rather than as a bound, and every SFTP operation waits on a reply,
so all of them would fail at once.

**What changes if you do nothing.** An operation against a peer that completes
the SSH handshake and then stops sending used to block forever, with no
exception and no log line. It now raises
[`BackendUnavailable`](api/errors.md) after 120 s of silence, and the backend
drops the dead client so the next operation reconnects.

```python
# Before (v0.30.0): the call never returns
store.read_bytes("delivery.csv")

# After (v0.31.0): raises BackendUnavailable after 120 s of silence
store.read_bytes("delivery.csv")
```

**The bound is on silence between bytes, not on the transfer.** A large file
over a slow link is unaffected however long it takes — a multi-gigabyte fetch
that runs for an hour never trips a 120 s bound, because bytes keep arriving.
What trips it is a flow that stops making progress. So a legitimately slow
transfer needs no change; a server that pauses for a long time on a single
operation (an antivirus or dedup appliance scanning a large file when you open
it) is the case to size the value against. See the
[SFTP guide](../guides/backends/sftp.md#bounding-a-stalled-transfer) for tuning.

**Scope:** SFTP only. No other backend's timeouts change.
[`ReadOnlyHttpBackend`](api/backends/http.md) already defaulted `timeout=30.0`, and
this brings SFTP into line with it rather than introducing a new kind of limit.

**Seeking to the end of an SFTP stream raises where it used to answer `0`:**

`SFTPBackend`'s streams resolve `seek(offset, os.SEEK_END)` by asking the server
for the file's size. That request used to go out through paramiko, which
discards its failure and reports a size of `0` — so on a stalled connection, or
against a server that refuses to stat an open handle, the seek returned `0` for
a file of any size and raised nothing. The backend now issues the request
itself, so the failure surfaces.

```python
# Before (v0.30.0): a wrong answer, indistinguishable from an empty file
with store.read("data.bin") as stream:
    size = stream.seek(0, os.SEEK_END)   # 0, on a 1 GiB file, no error

# After (v0.31.0): the failure reaches you
with store.read("data.bin") as stream:
    size = stream.seek(0, os.SEEK_END)   # raises
```

**What to change.** Code that treated a `0` from seek-to-end as "empty file" was
reading a wrong answer. Catch [`RemoteStoreError`](api/errors.md), which covers
both causes — the two do **not** raise the same subclass, and that is deliberate
rather than an oversight:

| Cause | Raises | Why |
|-------|--------|-----|
| A stalled connection | `BackendUnavailable` | The connection is dead; the cached client is dropped and the next operation reconnects |
| A server refusing to stat the handle | `RemoteStoreError` | The connection is healthy and nothing is wrong with it — only this one request is refused |

Sizing a file with `get_file_info(path).size` is unaffected and always reported
the failure.

**You may not have written the seek.** SFTP streams report themselves seekable,
so `read_seekable()` hands them to analytical readers such as PyArrow, which
size a file with `seek(0, os.SEEK_END)` before reading its footer. If such a
read previously returned empty or nonsense against a flaky SFTP endpoint, this
is why, and it now raises instead. This applies to reads large enough to stream:
the PyArrow adapter materialises anything at or below its
`materialization_threshold` and never seeks the stream at all — see the
[PyArrow adapter guide](../guides/pyarrow-adapter.md) for that setting.

**Scope:** SFTP only. Every other backend resolves an end-relative seek without
a request that can fail, and their streams are byte-for-byte unchanged. The
failure also arrives one `io_timeout` sooner than before on a stalled
connection, because the release of a condemned stream no longer pays the bound a
second time.

**Flat-namespace backends now raise `InvalidPath` for a wrong-typed path:**

A backend that stores keys rather than nodes — the S3 family, Azure on a flat
(non-hierarchical) account, and the SQL backends — cannot ask the store whether
a path is a directory; it has to derive that from a prefix listing. For a long
time those backends did not, so a file operation aimed at a folder either raised
`NotFound` or, worse, reported success. The hierarchical backends (Local, SFTP,
Memory, Azure on a hierarchical-namespace account, OneDrive) already raised
[`InvalidPath`](api/errors.md) for the same calls. They now all agree:

| Operation | Old answer (flat namespace) | New |
|-----------|-----------------------------|-----|
| `read`, `read_bytes`, `read_seekable` on a folder | `NotFound`, or an empty read of the bare prefix | `InvalidPath` |
| `delete` on a folder | silent no-op | `InvalidPath` |
| `get_file_info` on a folder | `NotFound` | `InvalidPath` |
| `delete_folder` on a file | `NotFound` | `InvalidPath` |
| `get_folder_info` on a file | counted the file as its own content | `InvalidPath` |
| `move` / `copy` from a folder source | succeeded | `InvalidPath` |

**What to change.** `InvalidPath` and `NotFound` are both `RemoteStoreError`
subclasses, so an `except RemoteStoreError` clause is unaffected. Two narrower
cases need action:

- An `except NotFound` clause standing in for "wrong type" no longer fires
  there. Catch `InvalidPath` instead.
- Code that relied on `delete(folder)` doing nothing, or on a folder-source
  `move` / `copy` reporting success, now gets an error. Those calls were
  reporting an operation that had not happened: use `delete_folder` for a
  folder, and `move` / `copy` on files.

**Scope:** the operations above, which are the ones that can *fail* on a
wrong-typed path. On a flat namespace a write to a key that shadows a prefix
still succeeds, so there was no error there to reclassify, and `write`,
`write_atomic`, `open_atomic` and the `move` / `copy` destination are unchanged.

**`""` and `"."` name the store root on every backend that lists:**

The store root is a folder, it always exists, and both spellings address it.
Several backends previously disagreed: `is_file("")` raised rather than
answering `False`, `get_folder_info(".")` raised on Local, Memory and SFTP, and
an SFTP store's root did not exist at all until its first write.

**Scope:** backends declaring `Capability.LIST`. "The root is a folder"
presupposes a backend that *has* folders, and `LIST` is how a backend declares
it enumerates them. [`ReadOnlyHttpBackend`](api/backends/http.md) declares no
`LIST` — it exposes a flat set of addressable objects with no root to speak of,
resolves the empty key to its base URL and reads that — so the table below does
not describe it, and nothing about it changed.

| Call on the store root | Answer from v0.31.0 |
|------------------------|---------------------|
| `exists("")`, `is_folder("")` | `True` |
| `is_file("")` | `False` |
| `get_folder_info("")` | aggregates the whole store; zero on an empty one |
| `read`, `get_file_info`, `delete` on the root | `InvalidPath` — the root is a folder, not a file |
| `write`, `write_atomic`, `open_atomic` on the root | `InvalidPath`, decided from the key before any request is issued |

The last row changed behaviour rather than an error type. A write addressed at
the root used to reach the storage system: on SFTP with no `base_path` it left
the store's own container directory as a regular **file**, and `open_atomic`
returned cleanly having done it. Every spelling that addresses the root is now
refused — `""`, `"."`, `"./"`, `".//"`, `"./."` and `"/"` — and so is the root as
a `move` or `copy` **destination**, which on `S3Boto3Backend` used to return
cleanly *and delete the source*. Writes to a path *under* the root are unaffected
and still create the container where that is the backend's documented behaviour.

**`max_depth` is inert without `recursive=True` on the `Backend` ABC:**

Calling a backend's `list_files()` **directly** with `max_depth=` and
`recursive=False` now yields the immediate children for every value of
`max_depth`, identical to omitting it. Some backends previously expanded the
traversal instead.

[`Store.list_files()`](api/store.md) is unaffected and needs no change: it
normalises `max_depth` into `recursive` before delegating, so depth still takes
full control there. Only code holding a [`Backend`](api/backend.md) and calling
it without going through `Store` needs to pass `recursive=True` alongside
`max_depth`.

**S3 failures that arrived as the wrong type now arrive as the right one:**

Two classes of S3 failure reached callers misclassified. Both change which
`except` clause fires, and neither is a new restriction.

*A denied operation is `PermissionDenied`, not `NotFound`.* On `S3Backend` and
`S3PyArrowBackend` a 403 was read as absence on `delete`, the `move` / `copy`
source, `delete_folder` and `get_folder_info` — and `delete(missing_ok=True)`
swallowed it entirely and returned. All of them now raise `PermissionDenied`,
the tolerant delete included: `missing_ok` forgives a missing file, not a
refused one, and a delete that silently did nothing against a denied bucket
reported success for work that never happened.

*A listing failure is a `RemoteStoreError`, not a raw `botocore.ClientError`.*
`S3Boto3Backend`'s `list_files()`, `list_folders()` and `iter_children()` called
the paginator without the error mapping the rest of the class uses, so botocore's
own exception reached the caller untouched and an `except RemoteStoreError`
clause caught every backend but this one. `glob()` reaches the wire through
`list_files` and was affected the same way. If you wrote an
`except botocore.exceptions.ClientError` for these three listings specifically,
it no longer fires — catch `RemoteStoreError`.

**An absent root or container reads as an absent path, not as an error:**

When the directory, bucket, container or table holding your data is not there, a
store now answers as it would for a store with nothing in it. It used to raise,
with a type that varied by backend: `InvalidPath("Path escapes root directory")`
from a `LocalBackend` whose root had been deleted, `BackendUnavailable` from
`SQLBlobBackend` against a dropped table, and a `NotFound`-versus-clean-return
disagreement between the two deletes elsewhere. This affects `LocalBackend` with
a deleted root, and `S3Boto3Backend`, `AzureBackend`, `AsyncAzureBackend` and
`SQLBlobBackend` with a missing bucket, container or table.

| Call | Answer from v0.31.0 |
|------|---------------------|
| `delete(p, missing_ok=True)`, `delete_folder(p, missing_ok=True)` | return cleanly |
| `delete(p)`, `delete_folder(p)` | `NotFound` |
| `read`, `read_bytes`, `read_seekable`, `get_file_info`, `get_folder_info`, `move` / `copy` source | `NotFound` |
| `exists`, `is_file`, `is_folder` | `False` |
| `list_files`, `list_folders`, `iter_children`, `glob` | empty |
| `exists("")`, `is_folder("")` on the store root | `True` — the root is a folder whether or not the container is |

**One root answer has not caught up, and the guide says so rather than
promising it.** `get_folder_info("")` should aggregate to zero against an absent
container exactly as it does against an empty one, and on `LocalBackend` and
`SQLBlobBackend` it does. On `S3Boto3Backend`, `AzureBackend` and
`AsyncAzureBackend` it still raises `NotFound`: those three short-circuit the
probes at the root but route `get_folder_info` through a listing whose 404 they
do not tolerate there. Treat it as unfinished rather than as the contract — keep
a `NotFound` handler if you aggregate the root of a store that may not exist.

**What to change.** An `except` clause that caught the old error to detect a
store that is not there no longer fires. [`Store.ping()`](api/store.md) —
`Backend.check_health()` if you hold a backend directly — is the operation whose
job is to report an unreachable store, and it answers on four of the five
backends above: `NotFound` for a deleted `LocalBackend` root and for a missing
`S3Boto3Backend` bucket or `AzureBackend` / `AsyncAzureBackend` container. On
`LocalBackend` it also reports a root path occupied by something that is not a
directory, which no other operation can see: the root answers as a folder by
definition, so nothing else observes what is actually there.

**On `SQLBlobBackend`, `ping()` is not yet that check.** The SQL backends verify
connectivity with a bare `SELECT 1` that never looks at the table, so a dropped
table and a discarded in-memory store both report healthy. There, a `write()` is
what surfaces the absence — it still raises `BackendUnavailable`. That is a gap
in `ping()` rather than a rule about `write()`: expect it to close, and reach
for `ping()` first on every other backend here.

**`write()` is not a portable substitute for it either.** The contract
deliberately leaves `write` against an absent container to each backend, and
they differ in both directions: a write under a deleted `LocalBackend` root
recreates the root and succeeds, where the `SQLBlobBackend` case above raises.

**One case is about `close()` rather than a missing container.** Disposing an
in-memory SQLite engine destroys the database rather than releasing a connection
to it, so on a `SQLBlobBackend` over in-memory SQLite every operation after
`close()` now reports an empty store — including the tolerant deletes, which used
to raise. If you relied on a tolerant delete raising after `close()` to catch a
use-after-close, track the closed state yourself.

**An absent OneDrive or SharePoint drive reads as an absent path:**

[`GraphBackend`](api/aio/backends/graph.md) and its sync adapter used to answer
with `BackendUnavailable` whenever Graph reported `404 resourceNotFound` — the
drive-identity code, which any item-by-path URL can return because every such URL
embeds the drive. A deleted or misconfigured drive therefore failed as a backend
identity error even on the operations the backend contract decides otherwise. It
now answers those the way the backend contract decides an absent container:

| Call against an absent drive | Answer from v0.31.0 |
|------------------------------|---------------------|
| `delete(p, missing_ok=True)`, `delete_folder(p, missing_ok=True)` | return cleanly |
| `delete(p)`, `delete_folder(p)`, `read`, `read_bytes`, `get_file_info`, `get_folder_info`, `move` / `copy` source | `NotFound` |
| `list_files`, `list_folders`, `iter_children` | empty |
| `exists`, `is_file`, `is_folder` | `False` (unchanged) |

**What to change.** If you told a dead drive from a missing item by catching
`BackendUnavailable` on a read, that no longer works. Three checks still
distinguish the two, in this order:

1. `Store.ping()` — the operation designed for the question, and the first
   of the two that still raise `BackendUnavailable`.
2. A `write()` — the second, so a misconfigured drive still surfaces as a
   configuration error on the first write against a freshly configured store,
   which is what a caller runs first. Its mid-upload chunk requests are
   item-scoped by design, so a drive that disappears *during* a large upload
   answers `NotFound`.
3. `exists("")` — a probe rather than an escalation, so it answers `False`
   rather than raising, and it is sound **only on a store with no `base_path`**.
   On a scoped store it addresses the `base_path` folder instead, where `False`
   means "drive gone *or* `base_path` folder missing" and distinguishes nothing.

Resolving the drive itself is unchanged: a store whose drive cannot be resolved
at all still fails as a configuration error before any operation runs.

**Both replacements are bounded by what your tier reports.** Some tiers, consumer
OneDrive among them, answer a nonexistent drive with `itemNotFound` rather than
`resourceNotFound`. There, `ping()` and `write()` distinguish nothing either —
and nothing did before this release, because the escalation never fired.

**`GraphBackend(base_path=".")` now means the drive root.** It used to scope the
whole store under a drive folder literally named `.` and send every write there.
`"./"`, `".//"` and any interior `.` segment normalise the same way, so
`base_path="a/./b"` scopes to `a/b`. A drive folder genuinely named `.` can no
longer be named by `base_path`; it stays reachable as an ordinary key under a
`base_path` that is not itself a root spelling. Every other `base_path` value is
unaffected.

## v0.29.1 to v0.30.0

**SFTP `write()` / `write_atomic()` no longer return a `last_modified` timestamp:**

To cut per-operation round trips, the SFTP backend dropped the post-write
`stat` call that was the only source of `WriteResult.last_modified` on the write path.
SFTP's write response carries no timestamp, so the field is now `None` after an SFTP
`write()` or `write_atomic()`. `WriteResult.size` (the uploaded byte count) is
unaffected, and no other backend changes.

```python
# Before (v0.29.1): last_modified populated from a post-write stat
result = store.write("data.bin", payload)   # SFTP backend
result.last_modified                          # datetime(...)

# After (v0.30.0): last_modified is None on the SFTP write path
result = store.write("data.bin", payload)
result.last_modified                          # None
```

If you need the timestamp after a write, read it back explicitly:

```python
info = store.get_file_info("data.bin")
info.last_modified
```

**Why:** the timestamp cost a synchronous `stat` round trip per write that raw paramiko
skips, about +100 ms at 100 ms RTT. `WR-001a` already permits `None` for a field a
backend's write response does not carry, so `None` is within the existing `WriteResult`
contract.

**SFTP failure paths now raise precise error types on non-OpenSSH servers:**

Several SFTP failure paths that previously raised a generic `RemoteStoreError` on servers
whose error shapes differ from OpenSSH now raise the canonical type:

| Condition (non-OpenSSH server)                             | Old error          | New error          |
|------------------------------------------------------------|--------------------|--------------------|
| Permission-denied classification stat (`EACCES`/`EPERM`)   | `RemoteStoreError` | `PermissionDenied` |
| Mode-less existing target on an `overwrite=False` write    | `RemoteStoreError` | `InvalidPath`      |
| `delete` of a missing path behind an opaque-error ancestor | `RemoteStoreError` | `NotFound`         |

One accepted consequence of the defensive mode-less policy: a mode-less *regular file*
written under `overwrite=False` now surfaces `InvalidPath` rather than `AlreadyExists`.
The `delete` recheck honours `missing_ok=True` exactly as the ENOENT path already did.

All new types subclass `RemoteStoreError`, so an `except RemoteStoreError` clause is
unaffected and most code needs no change. **If you catch specific types**, a failure that
previously fell through to a generic handler will now be caught by a narrower
`except PermissionDenied` / `except NotFound` / `except InvalidPath` clause first.

**Scope:** SFTP only, and only on non-OpenSSH servers whose error shapes differ from
OpenSSH. An OpenSSH-backed SFTP endpoint already raised the precise types and is
unchanged.

## v0.28.0 to v0.29.0

**Azure HNS is now an explicit, mandatory declaration:**

`AzureBackend` and `AsyncAzureBackend` no longer auto-detect Hierarchical
Namespace (ADLS Gen2) by probing the account on first use. You must now declare
the account's nature with the required `hns` argument. A backend constructed
without `hns` raises `ValueError`.

```python
# Before (v0.28.0): HNS auto-detected on first I/O
backend = AzureBackend(container="data", account_name="acct", account_key="...")

# After (v0.29.0): declare hns explicitly
backend = AzureBackend(container="data", hns=True, account_name="acct", account_key="...")
```

The same applies to config `options` (`"hns": true`) and to `AsyncAzureBackend`.

**If you do not know an account's HNS status**, discover it once with the new
fail-loud helper and pass the result:

```python
from remote_store.backends import AzureUtils

is_hns = AzureUtils.detect_hns(account_name="acct", account_key="...")
backend = AzureBackend(container="data", hns=is_hns, account_name="acct", account_key="...")
```

`AzureUtils.adetect_hns(...)` is the async sibling. Both raise on a probe error
rather than silently falling back to flat behavior.

**Why:** the old `GetAccountInfo` probe could fail, return propagation-delayed
authorization state, or be denied by least-privilege credentials — silently
degrading an HNS account to flat semantics. A declared value is deterministic
from construction and removes that failure class.

## v0.24.1 to v0.25.0

**`[sftp]` extra now requires `paramiko>=3.0`:**

The SFTP backend uses paramiko 3.0's `channel_timeout=` connect kwarg. Environments
pinned to `paramiko<3` must upgrade. `pip install "remote-store[sftp]"` resolves the
correct version automatically; pinned `paramiko==2.x` will now conflict.

**Azure HNS error types now match the canonical mapping:**

On real ADLS Gen2 (Hierarchical Namespace) accounts, many `AzureBackend` and
`AsyncAzureBackend` operations previously raised the wrong error type when the path
named a directory blob (or, conversely, a file blob where a directory was expected).
Stage 3 live verification in this release surfaced the deviations; all now raise
`InvalidPath` per the canonical mapping. **If you catch the old error types**, those
clauses will no longer fire on HNS:

| Operation                                      | Old error (HNS)                          | New error      |
|------------------------------------------------|------------------------------------------|----------------|
| `read`, `read_bytes`, `read_seekable` on dir   | silently returned `b""`                  | `InvalidPath`  |
| `delete` on dir (file API)                     | silently destroyed directory marker (**data loss**) | `InvalidPath`  |
| `get_file_info` on dir                         | `NotFound`                               | `InvalidPath`  |
| `is_folder` on file                            | `True`                                   | `False`        |
| `get_folder_info` on file                      | `NotFound`                               | `InvalidPath`  |
| `delete_folder` on file                        | `DirectoryNotEmpty` / `NotFound`         | `InvalidPath`  |
| `move` / `copy` on dir source or dest          | `RemoteStoreError(InvalidInput)` / `AlreadyExists` | `InvalidPath`  |
| `open_atomic` on dir target                    | `AlreadyExists`                          | `InvalidPath`  |
| `write` / `write_atomic` on dir target         | `AlreadyExists`                          | `InvalidPath`  |
| `move(p, p)` / `copy(p, p)` self-op            | `AlreadyExists`                          | no-op          |

Flat-namespace blob accounts (non-HNS) and Azurite were already correct and are
unaffected. Sync and async siblings behave identically.

**`Store.move(p, p)` / `copy(p, p)` self-op error type:**

Across all backends, `Store.move` / `copy` and `AsyncStore.move` / `copy` now raise
`InvalidPath` (was `NotFound`) when the source path is a directory and `src == dst`.
The file no-op case is unchanged.

**`hatch run test-cov` no longer enforces `--cov-fail-under=95`:**

The coverage floor moved to a new `hatch run test-cov-strict` script. Local
`test-cov` is now a coverage *report* only; CI runs the strict variant. If your
tooling or CI relied on `test-cov` failing under 95% switch to `test-cov-strict`.

## v0.24.0 to v0.24.1

**S3 botocore Config options route through `config_kwargs`:**

Pre-built `botocore.config.Config` objects are no longer accepted in
`client_options["client_kwargs"]`. Pass the same constructor kwargs through
`config_kwargs` (a plain dict) instead. The old form raised `TypeError` at
first I/O on s3fs ≥ 2024.x already; v0.24.1 fails fast with `ValueError` at
backend construction and a message naming the supported channel.

- Old: `S3Backend(..., client_options={"client_kwargs": {"config": Config(connect_timeout=10, retries={"max_attempts": 5})}})`
- New: `S3Backend(..., client_options={"config_kwargs": {"connect_timeout": 10, "retries": {"max_attempts": 5}}})`

The new "Botocore Client Tuning" section in `docs-src/guides/backends/s3.md`
documents proxies, retries, timeouts, and MinIO path-style addressing with
runnable snippets. Applies to both `S3Backend` and `S3PyArrowBackend`.

**Custom backends must declare `CAPABILITIES: ClassVar[CapabilitySet]`:**

If you maintain a custom `Backend` or `AsyncBackend` subclass, add a
class-level `CAPABILITIES` attribute exposing the capability set without
requiring instantiation, and delegate the `capabilities` property to it.
Conformance and the new graph-IR generator both read from this class
attribute. See `docs-src/guides/custom-backend-guide.md` § "Step 3" for the
template; existing constructor-set capability logic continues to work, but
the ClassVar is required for static extraction.

## v0.20.0 to v0.21.0

**`ParquetSerializer.deserialize()` returns Arrow Table:**

`ParquetSerializer.deserialize()` now returns a `pyarrow.Table` instead of a
`pandas.DataFrame`. This removes the hidden hard dependency on pandas for
`remote-store[dagster,arrow]` users.

- Old: `result = serializer.deserialize(data)  # pandas DataFrame`
- New: `result = serializer.deserialize(data)  # pyarrow.Table`
- If you need pandas: `df = serializer.deserialize(data).to_pandas()`
- If you need polars: `df = pl.from_arrow(serializer.deserialize(data))`

Custom subclasses that override `deserialize()` (e.g. `PolarsParquetSerializer`
from the medallion example) continue to work but the override is now optional —
the base class already returns a framework-neutral Arrow Table.

## v0.19.0 to v0.20.0

**Deprecated aliases removed:**

Three factory functions renamed in v0.18.0 have had their old names removed:

- `pydantic_to_registry_config()` → use `from_pydantic()`
- `remote_store_io_manager()` → use `dagster_io_manager()`
- `cached_store()` → use `cache()`

Pre-v1: removed without a deprecation cycle. Find-and-replace is sufficient.

## v0.18.0 to v0.19.0

**Factory function renames:**

Three ext factory functions were renamed for naming consistency.
Old names emitted `DeprecationWarning` in v0.18.x and are removed after
v0.19.0 (see [above](#v0190-to-v0200)).

- `pydantic_to_registry_config()` → `from_pydantic()`
- `remote_store_io_manager()` → `dagster_io_manager()`
- `cached_store()` → `cache()`

## v0.17.0 to v0.18.0

**Extension imports moved:**

Optional-dependency extensions are no longer re-exported from
`remote_store.__init__`. Import them directly from their extension module:

- Old: `from remote_store import pyarrow_fs, StoreFileSystemHandler`
- New: `from remote_store.ext.arrow import pyarrow_fs, StoreFileSystemHandler`

- Old: `from remote_store import otel_hooks, otel_observe`
- New: `from remote_store.ext.otel import otel_hooks, otel_observe`

- Old: `from remote_store import pydantic_to_registry_config`
- New: `from remote_store.ext.pydantic import from_pydantic`

- Old: `from remote_store import from_yaml`
- New: `from remote_store.ext.yaml import from_yaml`

Pure-Python extensions (`ext.batch`, `ext.transfer`, `ext.glob`, `ext.observe`,
`ext.cache`, `ext.partition`) are unchanged — they were already unconditionally
exported from `remote_store.__init__`.

## v0.15.0 to v0.16.0

**YAML config loader moved to extension:**

- `RegistryConfig.from_yaml()` has been removed from the core class and
  replaced by `from_yaml()` in `remote_store.ext.yaml`.
- Old: `config = RegistryConfig.from_yaml("config.yaml")`
- New: `from remote_store.ext.yaml import from_yaml` then `config = from_yaml("config.yaml")`
- Install the optional extra: `pip install "remote-store[yaml]"`

## v0.13.0 to v0.14.0

**Config loaders (new feature, no breaking changes):**

- `RegistryConfig.from_toml()` and `from_yaml()` are new. Existing
  `from_dict()` usage continues to work unchanged.
- `from_dict()` now warns on unknown keys. If you were passing
  extra keys silently, you will see warnings. Remove the unknown keys or
  suppress the warning.

## v0.12.0 to v0.13.0

**Credential hygiene:**

- Backend config values for keys named `key`, `secret`, `password`,
  `account_key`, `sas_token`, and `connection_string` are now automatically
  wrapped in `Secret` objects by `from_dict()`.
- If you were accessing these values directly as strings, use
  `secret.reveal()` to get the plain-text value.
- `repr()` and `str()` of config objects now mask credentials with `***`.

## v0.11.0 to v0.12.0

**Glob capability:**

- `Store.glob()` now requires `Capability.GLOB`. Backends that do not support
  it (Memory, SFTP) will raise `CapabilityNotSupported`.
- Use `ext.glob.glob_files()` as a portable fallback for all backends.

## General upgrade advice

1. Pin to a specific minor version in production: `remote-store>=0.16,<0.17`.
2. Read the [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
   for each version you skip.
3. Run your test suite after upgrading — the library has 95%+ coverage and
   you should too.

## See also

- [CHANGELOG](https://github.com/haalfi/remote-store/blob/master/CHANGELOG.md)
- [Contributing](../../CONTRIBUTING.md) — stability tiers and versioning policy
