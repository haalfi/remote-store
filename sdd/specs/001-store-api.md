# Store API Specification

## Overview

`Store` is the primary user-facing abstraction — a thin, immutable wrapper around a backend, scoped to a root path. This spec also defines the metadata and identity models (`FileInfo`, `FolderInfo`, `RemoteFile`, `RemoteFolder`) that form the Store's data contract.

---

## Store

### STORE-001: Construction

**Invariant:** Constructed with a `Backend` and `root_path` string.

### STORE-002: Path Validation

**Invariant:** All path arguments are validated via `RemotePath`.

### STORE-003: Root Path Scoping

**Invariant:** Store prepends `root_path` to all relative paths before delegating to the backend.

### STORE-004: Delegation

**Invariant:** All I/O is delegated to the backend. Store adds no I/O logic of its own.

### STORE-005: Capability Check

**Invariant:** `supports(capability)` checks whether the backend supports a capability.

### STORE-006: Capability Gating

**Invariant:** Capability-gated methods raise `CapabilityNotSupported` before delegating if the capability is missing.

### STORE-007: Thread Safety

**Invariant:** Store is immutable and safe to share across threads.

### STORE-008: Full API Surface

**Invariant:** Store exposes: `read`, `read_bytes`, `write`, `write_atomic`, `delete`, `delete_folder`, `exists`, `is_file`, `is_folder`, `list_files`, `list_folders`, `get_file_info`, `get_folder_info`, `move`, `copy`.

---

## Metadata Models

### MOD-001: FileInfo Immutability

**Invariant:** `FileInfo` is a frozen dataclass — immutable after construction.
**Postconditions:** Attribute assignment raises `FrozenInstanceError`.

### MOD-002: FileInfo Required Fields

**Invariant:** `FileInfo` has required fields: `path` (`RemotePath`), `name` (`str`), `size` (`int`), `modified_at` (`datetime`).

### MOD-003: FileInfo Optional Fields

**Invariant:** `FileInfo` has optional fields: `checksum` (`str | None`, default `None`), `content_type` (`str | None`, default `None`), `extra` (`dict[str, object]`, default empty dict).

### MOD-004: FolderInfo Required Fields

**Invariant:** `FolderInfo` is a frozen dataclass with required fields: `path` (`RemotePath`), `file_count` (`int`), `total_size` (`int`).

### MOD-005: FolderInfo Optional Fields

**Invariant:** `FolderInfo` optional fields: `modified_at` (`datetime | None`, default `None`), `extra` (`dict[str, object]`, default empty dict).

### MOD-006: RemoteFile and RemoteFolder

**Invariant:** `RemoteFile` and `RemoteFolder` are immutable value objects holding a `RemotePath` via a `path` attribute.

### MOD-007: Equality and Hashing

**Invariant:** `FileInfo`, `FolderInfo`, `RemoteFile`, and `RemoteFolder` support equality and hashing based on `path`.
