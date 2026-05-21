# RFC-0014: Dagster Compute Log Manager

## Status

Draft

## Summary

Add `RemoteStoreComputeLogManager` to `ext.dagster` — a Dagster
[`ComputeLogManager`](https://docs.dagster.io/deployment/dagster-plus/management/managing-compute-logs-and-error-messages)
implementation that captures op/step `stdout` and `stderr` and persists them to
any remote-store backend (Local, S3, SFTP, Azure). It is configured in
`dagster.yaml` as a Dagster *instance* component, complementing the existing
`IOManager` adapter, which handles asset/op return values. The two share one
config surface (`backend_type` + `backend_options`). Uniquely, this brings
**SFTP** compute-log storage to Dagster, which Dagster has no native support
for.

## Motivation

This RFC originates from a user request.

`ext.dagster` today wraps a `Store` as a Dagster `IOManager` — it persists the
*values* assets and ops return (`sdd/specs/031-ext-dagster.md`, DAG-001 –
DAG-020). Dagster has a second, independent storage extension point that
`ext.dagster` does not touch: the `ComputeLogManager`, which persists the raw
`stdout`/`stderr` text emitted while a step runs. These are the logs the
Dagster UI shows under a run's "stdout"/"stderr" tabs.

Dagster ships `LocalComputeLogManager` and `NoOpComputeLogManager` in core.
Cloud-backed variants live in the per-cloud libraries:
`S3ComputeLogManager` (`dagster-aws`), `AzureBlobComputeLogManager`
(`dagster-azure`), `GCSComputeLogManager` (`dagster-gcp`).

The gap this RFC fills mirrors the one the IOManager adapter already fills, plus
a capability gap no Dagster library covers:

1. **Duplicate configuration.** A team already running remote-store has
   configured a backend, credentials, retry policy, and TLS settings once. To
   persist *compute logs* to that same cloud bucket today, they must *also*
   install and configure `dagster-aws` / `dagster-azure` with a second copy of
   bucket name, credentials, and endpoint. The IOManager adapter exists
   precisely to avoid this duplication for asset I/O; compute logs are left out.

2. **No SFTP option at all.** Dagster has no SFTP compute log manager in any
   library. remote-store *does* have an SFTP backend. On-prem and air-gapped
   deployments whose only durable, off-host target is an SSH/SFTP server
   currently have no off-the-shelf way to ship Dagster compute logs anywhere
   durable.

3. **Ephemeral workers lose logs.** With `LocalComputeLogManager` on a
   Kubernetes / ECS run launcher, compute logs are written to the *run worker's*
   local disk. When the pod or task is reclaimed, the logs vanish — the UI shows
   nothing for completed runs. A cloud-backed compute log manager is the
   standard fix; remote-store users should get it without a second dependency.

4. **One config surface.** A team can point both the IOManager and the
   ComputeLogManager at the same `backend_type` + `backend_options`, keeping
   asset storage and log storage consistent and configured once.

Compute logs are operationally important: they are where an operator looks
first when a step fails. Making them durable on the storage layer a team
already operates is a direct, user-motivated win.

## Proposal

### Module location

`src/remote_store/ext/dagster.py` — a new section in the existing module, under
the existing optional `dagster` extra (`pip install "remote-store[dagster]"`).
No new install extra. This matches the research decision for the IOManager
adapter (`research-dagster-extension.md` §5): first-party extension, single
package, consistent with `ext/arrow.py`, `ext/otel.py`.

### Why this is shaped differently from the IOManager adapter

A `ComputeLogManager` is not a resource. Two structural facts drive the design:

| | `IOManager` (existing `ext.dagster`) | `ComputeLogManager` (this RFC) |
|---|---|---|
| Stores | Asset / op return values | Raw `stdout` / `stderr` of step execution |
| Wired into | `Definitions(resources=...)` — a **resource** | `dagster.yaml` — a Dagster **instance** component |
| Constructed by | A factory the user calls, passing a live `Store` | Dagster, from a YAML config dict |
| Lifetime | Per-run (`setup` / `teardown` hooks) | Process-lifetime singleton (webserver, daemon, every run worker) |

Two consequences:

1. **It cannot be handed a live `Store`.** Dagster instantiates the manager
   from a `dagster.yaml` dict. The class must therefore *build its own* `Store`
   from configuration — exactly what `_build_store(backend_type,
   backend_options, root_path)` already does for `DagsterStoreResource` and
   `RemoteStoreIOManager`. That helper is reused unchanged.

2. **It cannot stream `stdout`/`stderr` straight to a `Store`.** Capture works
   by dup'ing OS file descriptors onto a *real local file*; a file descriptor
   cannot point at a remote object. Every cloud compute log manager therefore
   captures to a local temp directory first, then uploads. Dagster factors this
   capture-locally-then-upload machinery into a template-method base,
   `TruncatingCloudStorageComputeLogManager`, leaving subclasses to implement a
   small set of cloud hooks.

### Core class

```python
class RemoteStoreComputeLogManager(
    TruncatingCloudStorageComputeLogManager,
    ConfigurableClass,
):
    """Captures op/step stdout+stderr to any remote-store backend.

    Logs are captured to a local temp directory (file-descriptor level),
    then uploaded to the Store on step completion — and, when
    `upload_interval` is set, periodically while the step runs so the UI
    can tail them.
    """
```

`TruncatingCloudStorageComputeLogManager` (Dagster core) provides the inherited
behaviour: `capture_logs`, `is_capture_complete`, `get_log_data_for_type`,
`get_log_metadata`, the partial-upload polling thread, and 50 MB upload
truncation. `ConfigurableClass` provides the `dagster.yaml` plumbing. The
subclass implements only the cloud hooks below.

### Configuration (`dagster.yaml`)

```yaml
compute_logs:
  module: remote_store.ext.dagster
  class: RemoteStoreComputeLogManager
  config:
    backend_type: sftp
    backend_options:
      host: logs.example.com
      username: dagster
    root_path: dagster/compute-logs
    upload_interval: 30
```

Config fields (via `ConfigurableClass.config_type()`):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `backend_type` | `str` | *(required)* | Registered backend type (`local`, `s3`, `sftp`, `azure`, `memory`) |
| `backend_options` | `dict` | `{}` | Kwargs for the backend constructor |
| `root_path` | `str` | `""` | Store root prefix for all log objects |
| `local_dir` | `str` | system temp dir | Local staging directory for capture |
| `prefix` | `str` | `"dagster"` | Path prefix within the Store |
| `skip_empty_files` | `bool` | `false` | Skip uploading zero-byte log files |
| `upload_interval` | `int \| None` | `None` | Seconds between partial uploads while a step runs; `None` disables live tailing |

`backend_options` reuses the secret-wrapping conventions already applied by
`_build_store` / `RegistryConfig.from_dict`, so sensitive keys
(`password`, `account_key`, …) are wrapped consistently with the rest of the
library.

### Hook implementations

`TruncatingCloudStorageComputeLogManager` requires the following. Each maps
directly onto the public `Store` API:

| Dagster hook | remote-store implementation |
|---|---|
| `local_manager` (property) | A `LocalComputeLogManager(local_dir)` held by the instance |
| `upload_interval` (property) | Returns the `upload_interval` config field |
| `_upload_file_obj(data, log_key, io_type, partial)` | `store.write(path, data, overwrite=True)` — `data` is `IO[bytes]`, accepted by `WritableContent` |
| `download_from_cloud_storage(log_key, io_type, partial)` | `store.read(path)` streamed into the local staging file |
| `cloud_storage_has_logs(log_key, io_type, partial)` | `store.is_file(path)` |
| `display_path_for_type(log_key, io_type)` | `store.native_path(path)` — human-readable location for the UI |
| `download_url_for_type(log_key, io_type)` | Returns `None` in v1 — see Open Questions |
| `delete_logs(log_key=None, prefix=None)` | `store.delete(path, missing_ok=True)` per `io_type` × partial; or `store.delete_folder(prefix, recursive=True, missing_ok=True)` |
| `on_subscribe` / `on_unsubscribe` | Delegate to `PollingComputeLogSubscriptionManager` (UI live-tail polling) |
| `get_log_keys_for_log_key_prefix(prefix, io_type)` | `store.list_files(prefix)` + reconstruct log-key sequences |

### Path scheme

A Dagster `log_key` is a `Sequence[str]` (e.g.
`[run_id, "compute_logs", step_key]`). The Store-relative path for one stream:

```
{prefix}/storage/{*log_key[:-1]}/{log_key[-1]}.{ext}[.partial]
```

where `ext` is `out` for `stdout`, `err` for `stderr` (Dagster's
`IO_TYPE_EXTENSION`), and the `.partial` suffix marks an in-progress upload. The
Store's `root_path` is the namespace prefix and is not embedded in this logic —
identical to the path-derivation contract for the IOManager (DAG-005).

### Required capabilities

The configured backend must declare `READ`, `WRITE`, `DELETE`, `METADATA`, and
`LIST`. All five built-in backends (Local, S3, SFTP, Azure, Memory) declare all
five, so there is no real-world gating failure — but the constructor will call
`store.supports(...)` and raise a clear, early error if a future or custom
backend is missing one, rather than failing mid-run.

### Lifecycle

The manager is a process-lifetime singleton. The `Store` is built once in
`__init__` and closed in `dispose()`, alongside disposing the local manager and
the subscription manager. For connection-based backends (SFTP, S3) this means a
connection is held open for the life of the Dagster process — acceptable and
consistent with how those backends behave under any long-lived service.

### New spec sections (proposed)

Extend `sdd/specs/031-ext-dagster.md` (same extension, same spec file) with a
new section, IDs `DAG-021` – `DAG-032`:

- `DAG-021`: `RemoteStoreComputeLogManager` — `ConfigurableClass` plumbing
  (`config_type`, `from_config_value`, `inst_data`).
- `DAG-022`: Store construction from config via `_build_store`; capability
  validation at construction.
- `DAG-023`: `local_manager` and `upload_interval` properties.
- `DAG-024`: Remote path scheme (`prefix`, `log_key`, `io_type`, `.partial`).
- `DAG-025`: `_upload_file_obj` — upload a local log file to the Store.
- `DAG-026`: `download_from_cloud_storage` — download from Store to local stage.
- `DAG-027`: `cloud_storage_has_logs` — existence check.
- `DAG-028`: `display_path_for_type` / `download_url_for_type` behaviour.
- `DAG-029`: `delete_logs` — by `log_key` (all stream/partial variants) and by
  `prefix`; deletes local *and* Store copies.
- `DAG-030`: `on_subscribe` / `on_unsubscribe` — subscription delegation.
- `DAG-031`: `get_log_keys_for_log_key_prefix` — enumerate stored log keys.
- `DAG-032`: lifecycle — `dispose()` closes the Store.

## Alternatives Considered

### A: Tell users to use `dagster-aws` / `dagster-azure` for compute logs

The status quo. Rejected: it forces a second dependency and a duplicated copy
of backend configuration, which is the exact friction the IOManager adapter was
built to remove. It also leaves SFTP — and any backend without a Dagster
library — with no option at all.

### B: Ship as a separate `remote-store-dagster` PyPI package

Rejected for the same reasons the IOManager adapter rejected it
(`research-dagster-extension.md` §5): doubled maintenance, harder discovery, and
inconsistency with every other first-party `ext/*` module. The compute log
manager shares the `dagster` extra and `_build_store` helper with the existing
adapter — splitting them apart would be strictly worse.

### C: Subclass `ComputeLogManager` directly

Rejected. The raw `ComputeLogManager` base would force us to reimplement
local file-descriptor capture, the partial-upload polling thread, cursor
math, and 50 MB truncation. `TruncatingCloudStorageComputeLogManager` is the
seam Dagster designed for exactly this — `S3ComputeLogManager`,
`AzureBlobComputeLogManager`, and `GCSComputeLogManager` all use it. Subclassing
it keeps remote-store's surface to ~10 small hooks and insulates us from churn
in the capture machinery.

### D: Subclass `LocalComputeLogManager` and override upload

An older pattern (pre-`CloudStorageComputeLogManager`). Rejected: superseded by
the cloud-storage base, which already *composes* a `LocalComputeLogManager`
internally. Overriding `LocalComputeLogManager` directly would fight the
framework.

### E: Capture `stdout`/`stderr` straight into `store.open_atomic()`

Rejected because it is not possible. OS-level capture redirects file
descriptors, which must target a real local file. There is no way to bind a
descriptor to a remote `Store` object. Local-stage-then-upload is not a design
choice; it is the only workable model, and the reason the cloud base exists.

### F: A separate `ext/dagster_logs.py` module

A minor placement variant — keep the compute log manager out of `dagster.py`.
Rejected for v1: it would split a single extension across two files for no
benefit, since both halves share the `dagster` extra and `_build_store`. Left as
an Open Question only in case `dagster.py` grows unwieldy.

## Impact

- **Public API:** Adds `RemoteStoreComputeLogManager` to `ext.dagster.__all__`.
  Not re-exported from the top-level `remote_store` package (ADR-0013 — optional
  extensions are not re-exported). The class is referenced by *string* in
  `dagster.yaml` (`module` + `class`), so the import path
  `remote_store.ext.dagster` is itself part of the public contract.
- **Backwards compatibility:** Non-breaking. Pure addition; no change to the
  existing IOManager API or to spec IDs DAG-001 – DAG-020.
- **Dependency:** Uses `TruncatingCloudStorageComputeLogManager`,
  `LocalComputeLogManager`, `PollingComputeLogSubscriptionManager`,
  `ConfigurableClass`, and the Dagster config primitives. These have been stable
  since well before the current `dagster>=1.9` floor, but the exact import
  paths must be pinned down — see Open Questions. No new third-party dependency
  beyond the existing `dagster` extra.
- **Performance:** Capture is local and on the hot path only to the extent
  `LocalComputeLogManager` already is — no remote I/O during step execution
  except the optional `upload_interval` partial uploads. The final upload
  happens at step completion. 50 MB upload truncation is inherited.
- **Testing:** Unit tests against `MemoryBackend` (round-trip capture → upload →
  download → read; `delete_logs`; `cloud_storage_has_logs`; path scheme;
  multi-key prefix enumeration). Integration tests against Local, S3, and SFTP
  backends. Where Dagster exposes a compute-log-manager conformance harness, run
  it. Tests carry `@pytest.mark.spec("DAG-0NN")` per the SDD traceability rule.

## Open Questions

1. **Download URLs.** `S3ComputeLogManager` mints presigned URLs and
   `AzureBlobComputeLogManager` mints SAS URLs so the browser fetches logs
   directly from cloud storage. remote-store has no URL-minting primitive.
   v1 returns `None` from `download_url_for_type`, so the Dagster webserver
   streams log bytes through itself via `get_log_data` (the same behaviour as
   `LocalComputeLogManager`). This is correct but means the webserver process
   must also be able to reach the backend. Should remote-store grow a
   `Store.signed_url()` capability so this can be improved later? Out of scope
   for this RFC; flagged for a possible future RFC.

2. **`dagster` version floor.** Confirm that `dagster>=1.9` exposes
   `TruncatingCloudStorageComputeLogManager`, `PollingComputeLogSubscriptionManager`,
   and the `ConfigurableClass` config helpers at stable import paths. If the
   required surface only stabilised later, either bump the floor or use a
   version-guarded import. To be resolved during the spec/implementation phase.

3. **Spec placement.** This RFC proposes extending `031-ext-dagster.md` rather
   than creating a new spec file, on the grounds that it is the same extension
   module. Confirm that is preferred over a dedicated
   `0NN-ext-dagster-compute-logs.md`.

4. **Module placement.** Same-file (`ext/dagster.py`) vs a sibling
   `ext/dagster_logs.py` — see Alternative F. Recommended: same file.

5. **`get_log_keys_for_log_key_prefix` scope.** The base class raises
   `NotImplementedError` by default; implementing it (DAG-031) enables the UI's
   per-run log-file listing. Confirm it is in scope for v1 rather than deferred.

6. **`backend_options` and Dagster `EnvVar`.** Should sensitive values in
   `backend_options` accept Dagster's `EnvVar("...")` directly, or require plain
   strings / OS env vars? This is the same unresolved question carried by the
   v2 IOManager work (`research-dagster-extension.md` §11.1); the two should be
   answered together for a consistent config story.

## References

- Dagster compute logs:
  <https://docs.dagster.io/deployment/dagster-plus/management/managing-compute-logs-and-error-messages>
- Dagster `ComputeLogManager` API:
  <https://docs.dagster.io/api/dagster/internals#dagster._core.storage.compute_log_manager.ComputeLogManager>
- `S3ComputeLogManager` source (reference implementation):
  `python_modules/libraries/dagster-aws/dagster_aws/s3/compute_log_manager.py`
- `CloudStorageComputeLogManager` / `TruncatingCloudStorageComputeLogManager`:
  `python_modules/dagster/dagster/_core/storage/cloud_storage_compute_log_manager.py`
- Existing Dagster extension: `sdd/specs/031-ext-dagster.md`,
  `sdd/research/research-dagster-extension.md`
- Store API: `sdd/specs/001-store-api.md`
- ADR-0008: Extension architecture (`sdd/adrs/0008-extension-architecture.md`)
- ADR-0013: Drop optional extension re-exports
  (`sdd/adrs/0013-drop-optional-extension-reexports.md`)
- ADR-0003: fsspec is an implementation detail
  (`sdd/adrs/0003-fsspec-is-implementation-detail.md`)
