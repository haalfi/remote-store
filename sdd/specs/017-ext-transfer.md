# ext.transfer — Upload, Download, Cross-Store Transfer Specification

## Overview

`ext.transfer` provides three standalone functions for moving data between
local files and Stores, or between two Stores: `upload`, `download`, and
`transfer`. All functions stream data via `BinaryIO` — the extension never buffers the
full file content. End-to-end memory behavior depends on the backend's
`write()` implementation (see SIO-003). An optional `on_progress` callback fires per chunk.

**Module:** `src/remote_store/ext/transfer.py`
**Dependencies:** None (pure Python, always available)
**Related:** [001-store-api.md](001-store-api.md) (Store API), ID-023
(unifies ID-001 cross-store transfer and ID-009 upload/download).

---

## Requirements

### XFER-001: upload Signature

**Invariant:** `upload(store, local_path, remote_path, *, overwrite=False, on_progress=None) -> None`. `store` is a `Store` instance. `local_path` is a `str | os.PathLike[str]`. `remote_path` is a `str`. `on_progress` is `Callable[[int], None] | None`.

### XFER-002: upload Streaming

**Invariant:** `upload` opens the local file in binary read mode, wraps it in a `_ProgressReader` (if `on_progress` is provided), and passes the file handle directly to `store.write()`. The extension never buffers the full file content in memory.

### XFER-003: upload overwrite

**Invariant:** The `overwrite` parameter is forwarded to `store.write()`. When `False` (default), writing to an existing remote path raises `AlreadyExists`.

### XFER-004: upload FileNotFoundError

**Invariant:** If the local file does not exist, `upload` raises `FileNotFoundError` (stdlib). This error is raised before any Store interaction.

### XFER-005: upload on_progress

**Invariant:** When `on_progress` is not `None`, the callback fires once per `read()` call with the number of bytes read in that call (not cumulative). When `on_progress` is `None`, no wrapping occurs.

### XFER-006: download Signature

**Invariant:** `download(store, remote_path, local_path, *, overwrite=False, on_progress=None) -> None`. `store` is a `Store` instance. `remote_path` is a `str`. `local_path` is a `str | os.PathLike[str]`. `on_progress` is `Callable[[int], None] | None`.

### XFER-007: download Streaming

**Invariant:** `download` calls `store.read()` to get a stream, then reads chunks of 1 MiB (`1_048_576` bytes) and writes each chunk to the local file. The extension never buffers the full file content in memory. The remote stream is always closed via `try/finally`.

### XFER-008: download overwrite Guard

**Invariant:** When `overwrite=False` (default) and the local file already exists, `download` raises `FileExistsError` (stdlib). This check happens before calling `store.read()`.

### XFER-009: download on_progress

**Invariant:** When `on_progress` is not `None`, the callback fires once per chunk written to the local file, with the number of bytes in that chunk (not cumulative).

### XFER-010: download Stream Cleanup

**Invariant:** The remote stream returned by `store.read()` is always closed, even if an error occurs during the download. Implemented via `try/finally`.

### XFER-011: transfer Signature

**Invariant:** `transfer(src_store, src_path, dst_store, dst_path, *, overwrite=False, on_progress=None) -> None`. `src_store` and `dst_store` are `Store` instances (may be the same). `src_path` and `dst_path` are `str`. `on_progress` is `Callable[[int], None] | None`.

### XFER-012: transfer Streaming

**Invariant:** `transfer` calls `src_store.read()` to get a stream, wraps it in a `_ProgressReader` (if `on_progress` is provided), and passes the wrapped stream to `dst_store.write()`. The extension never buffers the full file content in memory.

### XFER-013: transfer overwrite

**Invariant:** The `overwrite` parameter is forwarded to `dst_store.write()`. When `False` (default), writing to an existing destination raises `AlreadyExists`.

### XFER-014: transfer on_progress

**Invariant:** When `on_progress` is not `None`, the callback fires once per `read()` call on the source stream, with the number of bytes read (not cumulative). Progress is tracked via a `_ProgressReader` wrapper around the source stream.

### XFER-015: transfer Stream Cleanup

**Invariant:** The source stream returned by `src_store.read()` is always closed, even if an error occurs during the transfer. Implemented via `try/finally`.

### XFER-016: No Backend Coupling

**Invariant:** All transfer functions operate exclusively through the public `Store` API (`read`, `write`). They never access `store._backend` or any backend internals. This ensures they work correctly with `Store.child()`, capability gating, path rebasing, and any future Store wrapper.

### XFER-017: Capability Gating Propagation

**Invariant:** Capability errors (`CapabilityNotSupported`) raised by Store methods propagate immediately. Transfer functions do not catch or wrap these errors.
