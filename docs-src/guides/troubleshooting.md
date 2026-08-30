# Troubleshooting

Common errors and their solutions when using `remote-store`.

## ImportError for optional dependencies

**Symptom:** `ImportError: No module named 'pyarrow'` (or `paramiko`,
`azure.storage.blob`, etc.)

**Cause:** Backend-specific dependencies are optional extras.

**Fix:** Install the extra for your backend:

```bash
pip install "remote-store[s3]"         # S3 backend (fsspec + s3fs)
pip install "remote-store[s3-pyarrow]" # S3-PyArrow backend
pip install "remote-store[sftp]"       # SFTP backend (paramiko)
pip install "remote-store[azure]"      # Azure backend
pip install "remote-store[all]"        # Everything
```

## Windows file-locking errors (WinError 32)

**Symptom:** `PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process`

**Cause:** An unclosed stream from `store.read()` keeps a file handle open.
On Windows (unlike Unix), open handles prevent deletion and cleanup.

**Fix:** Always close streams or use a context manager:

```python
# Good
stream = store.read("data.csv")
try:
    content = stream.read()
finally:
    stream.close()

# Better
with store.read("data.csv") as stream:
    content = stream.read()
```

## Unicode / cp1252 encoding errors on Windows

**Symptom:** `UnicodeEncodeError: 'charmap' codec can't encode character`

**Cause:** Windows console uses cp1252 by default. Characters like em dashes,
arrows, or box-drawing characters crash `print()`.

**Fix:** Use ASCII-only characters in print statements. For Polars DataFrames,
use `iter_rows(named=True)` with manual formatting instead of `print(df)`.

## SFTP host-key verification failure

**Symptom:** `SSHException: Server host key not found` or similar.

**Cause:** Paramiko requires host-key verification by default.

**Fix:** Set the host-key policy via ``SFTPUtils.HostKeyPolicy`` or a config
dict. Available policies: ``STRICT`` (default), ``TRUST_ON_FIRST_USE``,
``AUTO_ADD`` (dev/testing only).

Programmatic:

```python
from remote_store.backends import SFTPUtils, SFTPBackend

backend = SFTPBackend(
    host="sftp.example.com",
    username="user",
    password="pass",
    host_key_policy=SFTPUtils.HostKeyPolicy.TRUST_ON_FIRST_USE,
)
```

Dict config (for ``RegistryConfig``):

```python
config = {
    "backends": {
        "my-sftp": {
            "type": "sftp",
            "host": "sftp.example.com",
            "username": "user",
            "password": "pass",
            "host_key_policy": "tofu",  # or "auto" for dev/testing only
        }
    },
    "stores": {"default": {"backend": "my-sftp"}},
}
```

See the [SFTP backend guide](backends/sftp.md) for full configuration details.

## SFTP `IncompatiblePeer` on connect

**Symptom:** `paramiko.ssh_exception.IncompatiblePeer: Incompatible ssh
peer (no acceptable {host key | kex algorithm | cipher | MAC})` during
``SFTPBackend`` connect. The error wraps four distinct negotiation
failures; the actionable next step depends on which one.

**Diagnose first.**
[`SFTPUtils.scan_host_algorithms()`](../reference/api/sftp-utils.md#remote_store.backends.SFTPUtils.scan_host_algorithms)
parses the server's `SSH_MSG_KEXINIT` advertisement over a raw socket
(no paramiko, no authentication). Print the relevant name-list to
identify which list the server narrowed.

**Fix per failure mode:**

- `no acceptable host key` — typically a legacy server advertising only
  `ssh-rsa` against a modern paramiko (5+) that removed it from
  defaults. See the SFTP guide's
  [Legacy Servers](backends/sftp.md#legacy-ssh-rsa) section;
  `SFTPUtils.enable_ssh_rsa_compat()` re-enables `ssh-rsa` at process
  startup.
- `no acceptable kex algorithm` / `cipher` / `MAC` — server narrowed a
  different list. Widen the matching list via the SFTP constructor's
  `connect_kwargs={"disabled_algorithms": ...}`; the
  `enable_ssh_rsa_compat()` helper does not address these.

## SFTP transfer stalls: hangs, or fails after two minutes

**Symptom, one of two.** Either an SFTP read or write **never returns** — no
exception, no log line, and whatever worker or pool slot it was running on stays
occupied — or it **fails after about two minutes** with a traceback whose last
line carries no message of its own:

```
remote_store._errors.BackendUnavailable:  | path='delivery.csv' | backend='sftp'
```

There is nothing in `remote_store`'s log to accompany it. To confirm the
diagnosis, enable paramiko's own DEBUG logging and look for a request going out
with no reply coming back.

Both symptoms come from the same fault: a peer that goes silent mid-operation.
Which one you see depends on whether the bound below is armed, which on v0.31.0
and later it is by default. Pick your branch:

- **It failed after ~2 minutes and your server has no legitimate pause that
  long.** The bound did its job — go to **4. The bound worked** below.
- **It failed after ~2 minutes and your server does legitimately pause that
  long.** Raise the bound: see **Choosing a value** at the end of this section.
- **It never returned at all.** The bound is not doing its job; work through
  causes 1 to 3.

**Cause.** `SFTPBackend`'s `timeout` bounds the *connect* phase only. It is
passed to paramiko as `timeout` / `banner_timeout` / `auth_timeout` /
`channel_timeout`, and the last of those bounds how long the client waits for a
channel to *open*, not traffic on an opened one. Once the channel is up,
paramiko applies no bound of its own, so a peer that completes the handshake and
then stops sending would block indefinitely. This is a silent peer, not a
dropped connection: a drop raises and is recovered from, whereas silence looks
exactly like a very slow transfer.

**What stops it.** [`io_timeout`](backends/sftp.md#bounding-a-stalled-transfer)
bounds that silence, and on **v0.31.0 and later it is on by default at 120 s** —
so a silent peer raises `BackendUnavailable` after two minutes and the backend
reconnects on the next operation, rather than hanging. If you are seeing an
unbounded hang, work through the three causes below.

**1. The bound is off**, which happens two ways.

*You passed `io_timeout=None`.* Drop it — the default applies on its own, and you
need pass nothing:

```python
from remote_store.backends import SFTPBackend

backend = SFTPBackend(host="files.example.com", username="deploy")
```

*You are on a version before v0.31.0.* `io_timeout` does not exist there, so
there is nothing to set: an open channel is unbounded and cannot be bounded.
Upgrading is the only route — see the
[migration guide](../reference/migration.md).

**2. It is the one genuinely unbounded wait.** A server that opens the SSH
channel and then never answers the `sftp` subsystem request hangs regardless:
paramiko waits for that reply on an untimed event, so no channel timeout reaches
it. That needs a wedged SSH daemon rather than a wedged SFTP subsystem — rarer
than the stall above, but it is the shape to suspect when the bound appears to
do nothing.

**3. It is not hung, only slow.** The bound is on silence *between* bytes, not
on the transfer as a whole, so a multi-gigabyte fetch that legitimately takes an
hour never trips it — and equally, never looks hung to `io_timeout`. Time the
transfer rather than assuming a stall.

**4. The bound worked**, and what to do with the failure. If the call failed
after ~2 minutes against a peer that really did go silent, nothing is
misconfigured. The operation is **not retried** — the connect-phase
`RetryPolicy` does not cover a stall — so recovery is yours to drive:

- A streamed read raises rather than returning short, so the bytes you already
  received are a valid prefix and the handle is dead. Discard it and start the
  read again; do not try to resume it.
- The backend drops the dead client, so the **next** operation reconnects on its
  own. The store stays usable — you do not need to rebuild it.
- **The failure does not tell you the operation did not happen.** A timeout means
  no reply came back; if the silence was on the return path, the server did the
  work and only the answer was lost. A stalled `move` may have moved the file, and
  a stalled `write_atomic` may have written it. A stalled plain `write` or `copy`
  may have left the destination untouched, emptied, or holding an unpredictable
  prefix. Re-check the state rather than assuming a rollback, retry with
  `overwrite=True`, and never append to a partial file. The
  [full per-operation table](backends/sftp.md#capabilities) is in the SFTP guide.

If this is happening often against a server you believe is healthy, the bound is
probably too tight for it — see **Choosing a value** below.

**Choosing a value.** Size it against the longest legitimate pause your server
can produce (an antivirus or dedup appliance may go quiet on `open()` of a large
file), not against total transfer time. Raising it costs only how quickly a
stall is noticed; lowering it turns a healthy-but-quiet server into intermittent
`BackendUnavailable`, which is harder to diagnose than the hang it replaced.
`0` does not mean "no bound": it is rejected at construction. `None` is the way
to ask for no bound.

## Azure: HNS vs flat namespace

**Symptom:** `move()` or `copy()` fails on Azure with unexpected errors.

**Cause:** Azure Blob Storage has two modes: flat namespace (default) and
hierarchical namespace (HNS / ADLS Gen2). Some operations behave differently.

**Fix:** Ensure the `hns` you declared matches the actual account type. The
Azure backend does not auto-detect HNS — you pass `hns=True` for ADLS Gen2 or
`hns=False` for flat Blob Storage. A mismatch (e.g. `hns=False` against a real
HNS account) makes the backend use the wrong code path. If you are unsure of an
account's type, call `AzureUtils.detect_hns(...)` once and pass the result. HNS
accounts support true directory operations; flat namespace accounts simulate
them, and HNS is recommended for data lake workloads.

## S3 endpoint configuration for MinIO / local S3

**Symptom:** Connection errors when using MinIO or another S3-compatible service.

**Cause:** The default S3 endpoint points to AWS. Local services need an
explicit endpoint URL.

**Fix:**

```python
config = {
    "backends": {
        "minio": {
            "type": "s3",
            "bucket": "my-bucket",
            "endpoint_url": "http://localhost:9000",
            "key": "minioadmin",
            "secret": "minioadmin",
        }
    },
    "stores": {"default": {"backend": "minio"}},
}
```

## CapabilityNotSupported error

**Symptom:** `CapabilityNotSupported: Backend 'memory' does not support GLOB`

**Cause:** Not all backends support every operation. Memory and SFTP lack
native glob.

**Fix:** Check capabilities before calling, or use the portable fallback:

```python
from remote_store import Capability, glob_files

if Capability.GLOB in store.capabilities():
    results = store.glob("**/*.csv")
else:
    results = glob_files(store, "**/*.csv")
```

See the [Capabilities Matrix](../reference/capabilities-matrix.md) for the full
backend x capability table.

## DatasetIncomplete error

**Symptom:** `DatasetIncomplete: Dataset at 'silver/orders' is incomplete`

**Cause:** The `_SUCCESS` marker is missing (partial write) or one or more
Parquet part files listed in the manifest cannot be found.

**Fix:**
- Check that the write completed successfully (look for `_SUCCESS` under the
  dataset key).
- If parts are missing, the dataset was likely interrupted mid-write. Re-run
  the write with `overwrite=True`.
- Concurrent writers to the same `dataset_key` are not safe — coordinate
  externally.

## ManifestCorrupted error

**Symptom:** `ManifestCorrupted: Failed to parse manifest JSON`

**Cause:** The `manifest.json` file under a dataset key exists but contains
invalid JSON or is missing required fields.

**Fix:**
- Inspect the manifest: `store.read_bytes("silver/orders/manifest.json")`.
- If corrupted, delete and re-write the dataset with `overwrite=True`.
- The `reason` attribute on the exception carries the specific parse failure.

## See also

- [Getting Started](../tutorial/getting-started.md) — installation and quick start
- [Choosing a Backend](choosing-a-backend.md) — picking the right backend
- [Error Handling example](../../examples/errors/error_handling.py)
