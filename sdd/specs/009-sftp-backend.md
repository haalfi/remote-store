# SFTP Backend Specification

## Overview

`SFTPBackend` implements the `Backend` ABC for SSH File Transfer Protocol (SFTP) servers
using **pure paramiko** internally. It maps the Backend contract onto a real remote
filesystem accessed over SSH/SFTP.

Unlike fsspec's `SFTPFileSystem` (which hardcodes `AutoAddPolicy`), this backend
provides explicit host key policy control via a `HostKeyPolicy` enum, PEM key
sanitization for Azure Key Vault compatibility, and tenacity-based retry for
transient SSH errors.

**Dependencies:** `paramiko`, `tenacity` (optional extra: `pip install remote-store[sftp]`)

---

## Construction

### SFTP-001: Constructor Parameters

**Invariant:** `SFTPBackend` is constructed with a required `host` and optional
connection/authentication parameters.
**Signature:**
```python
SFTPBackend(
    host: str,
    *,
    port: int = 22,
    username: str | None = None,
    password: str | None = None,
    pkey: Any = None,                   # paramiko.PKey, lazy-typed
    base_path: str = "/",               # root on remote server
    host_key_policy: HostKeyPolicy = HostKeyPolicy.STRICT,
    known_host_keys: str | None = None,
    host_keys_path: str | None = None,  # defaults to ~/.ssh/known_hosts
    config: dict | None = None,         # may contain "known_host_keys"
    timeout: int = 10,
    connect_kwargs: dict | None = None, # extra SSHClient.connect() kwargs
)
```
**Postconditions:** The backend stores configuration but does not connect during
construction (see SFTP-004).

### SFTP-002: Backend Name

**Invariant:** `name` property returns `"sftp"`.

### SFTP-003: Capability Declaration

**Invariant:** `SFTPBackend` declares all capabilities **except** `GLOB`:
`READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `RECURSIVE_LIST`, `METADATA`.
**Rationale:**
- `ATOMIC_WRITE`: Simulated via temp file + rename (see SFTP-014). Orphan temp
  files are possible on connection failure -- documented caveat.
- `GLOB`: Not supported. SFTP has no server-side glob; client-side glob over
  `listdir` would be inefficient and misleading.
- `MOVE`: Implemented via `posix_rename` with fallback (see SFTP-018).
- `COPY`: Implemented via read + write (no server-side copy in SFTP, see SFTP-019).

### SFTP-004: Lazy Connection

**Invariant:** No network call occurs during `__init__`. The SSH/SFTP connection is
established lazily on first operation.
**Rationale:** Fail-fast at construction is undesirable -- the backend may be created
during application wiring before the network is available. Automatic reconnection
on staleness is also supported (see SFTP-010).

### SFTP-005: Construction Validation

**Invariant:** `host` must be a non-empty string. Passing an empty or whitespace-only
host raises `ValueError` at construction time.
**Postconditions:** No network validation of host reachability at construction time.

---

## Connection

### SFTP-006: HostKeyPolicy Enum

**Invariant:** `HostKeyPolicy` controls how unknown remote host keys are handled:
- `STRICT` (default): Reject unknown hosts. Requires host key in known_hosts.
- `TRUST_ON_FIRST_USE`: Accept and save on first connect, verify on subsequent connects.
- `AUTO_ADD`: Accept any key. **Development/testing only -- not safe for production.**

### SFTP-007: Host Key Resolution Chain

**Invariant:** Known host keys are resolved with first-match precedence:
1. `known_host_keys` constructor parameter (code-level override)
2. `config["known_host_keys"]` dict value
3. `SFTP_KNOWN_HOST_KEYS` environment variable
4. `host_keys_path` file on disk (default: `~/.ssh/known_hosts`)

**Postconditions:** If none of the above yield keys and the policy is `STRICT`,
connection will fail with a host key verification error.

### SFTP-008: PEM Key Sanitization

**Invariant:** `_sanitize_pem()` normalizes PEM line separators, handling the Azure
Key Vault quirk where newlines may be replaced with spaces or other characters.
**Postconditions:** The sanitized PEM string has standard `\n` line separators within
the Base64 payload. Invalid PEM structures (not 5 parts) raise `ValueError`.

### SFTP-009: Tenacity Retry on Connect

**Invariant:** The `_connect()` method retries on transient SSH errors using tenacity:
3 attempts, exponential backoff (2s min, 10s max).
**Retried exceptions:** `paramiko.SSHException`, `OSError`, `EOFError`.
**Postconditions:** After all retries are exhausted, the original exception is reraised.

### SFTP-010: Staleness Detection and Reconnect

**Invariant:** The lazy `_sftp` property checks connection liveness by calling
`stat('.')`. If the connection is stale (e.g. server dropped it), the backend
reconnects transparently.
**Postconditions:** Callers do not need to handle connection drops explicitly.

---

## Filesystem Model

### SFTP-011: Real Directories

**Invariant:** SFTP operates on a real remote filesystem with actual directories,
unlike S3's virtual prefix-based folders. `is_folder()` uses `stat()` + `S_ISDIR`.
**Postconditions:** Folders exist independently of their contents.

### SFTP-012: Write Creates Intermediate Directories

**Invariant:** `write("a/b/c.txt", content)` creates intermediate directories `a/`
and `a/b/` if they do not exist.
**Rationale:** SFTP servers reject writes to non-existent directories. Creating them
automatically matches the convenience of local and S3 backends.

### SFTP-013: Empty Folders Persist

**Invariant:** Unlike S3 (where folders vanish when empty), empty directories on an
SFTP server persist after their contents are deleted.
**Postconditions:** `is_folder("dir")` returns `True` even after all files under
`dir/` are deleted.

---

## Operations

### SFTP-014: Atomic Write (Simulated)

**Invariant:** `write_atomic` writes to a temporary file `.~tmp.<name>.<uuid8>` in
the same directory as the target, then renames to the target via `posix_rename`.
**Caveat:** If the connection drops between write and rename, the orphan temp file
remains. This is **simulated** atomicity, not true atomicity -- the capability is
declared to enable the write-then-rename pattern, but the caveat must be documented.
**Postconditions:** On success, the temp file is gone and the target contains the
new content. On failure, the backend attempts to clean up the temp file.

### SFTP-015: Atomic Write Overwrite Semantics

**Invariant:** `write_atomic(path, content, overwrite=False)` raises `AlreadyExists`
if the target already exists. With `overwrite=True`, the existing file is replaced.

### SFTP-016: delete_folder Recursive

**Invariant:** `delete_folder(path, recursive=True)` walks the directory tree
bottom-up, deleting files then directories.
**Raises:** `NotFound` if the folder does not exist and `missing_ok=False`.

### SFTP-017: delete_folder Non-Recursive

**Invariant:** `delete_folder(path, recursive=False)` succeeds only if the directory
is empty.
**Raises:** `NotFound` if missing. `RemoteStoreError` if the directory is not empty.

### SFTP-018: Move Via posix_rename

**Invariant:** `move(src, dst)` attempts `posix_rename` (atomic overwrite), falls back
to `rename`, and falls back to copy + delete if rename fails entirely.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and
`overwrite=False`.

### SFTP-019: Copy Via Read + Write

**Invariant:** `copy(src, dst)` reads the source file and writes it to the destination.
There is no server-side copy operation in SFTP -- data passes through the client.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and
`overwrite=False`.

---

## Error Mapping

### SFTP-020: NotFound Mapping

**Invariant:** `IOError` with `errno.ENOENT` (errno 2) and `FileNotFoundError` are
mapped to `NotFound`.
**Postconditions:** `path` and `backend` attributes are set on the error.

### SFTP-021: PermissionDenied Mapping

**Invariant:** `IOError` with `errno.EACCES` (errno 13) is mapped to `PermissionDenied`.

### SFTP-022: AlreadyExists Mapping

**Invariant:** `IOError` with `errno.EEXIST` (errno 17) is mapped to `AlreadyExists`.

### SFTP-023: BackendUnavailable Mapping

**Invariant:** `paramiko.SSHException` and its subclasses (authentication failures,
channel errors, etc.) are mapped to `BackendUnavailable`.

### SFTP-024: No Native Exception Leakage

**Invariant:** No paramiko, socket, or OS exceptions propagate to callers. All are
mapped to `remote_store` error types per BE-021.
**Postconditions:** `backend` attribute is set to `"sftp"` on all mapped errors.

---

## Resource Management

### SFTP-025: close()

**Invariant:** `close()` closes both the SFTP client and the underlying SSH transport.
**Postconditions:** Safe to call multiple times (idempotent). After close, further
operations will trigger a new connection via lazy init.

### SFTP-026: unwrap(SFTPClient)

**Invariant:** `unwrap(paramiko.SFTPClient)` returns the underlying SFTP client.
**Raises:** `CapabilityNotSupported` for any other type hint.
**Rationale:** Escape hatch for users who need paramiko-specific features (per ADR-0003).

### SFTP-027: Idempotent Close

**Invariant:** Calling `close()` multiple times must not raise. Internal state is
set to `None` after close, and the next operation will reconnect lazily.
