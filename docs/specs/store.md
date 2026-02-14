# Store Specification

## Overview

`Store` is the primary user-facing abstraction — a thin, immutable wrapper around a backend, scoped to a root path.

## STORE-001: Construction

**Invariant:** Constructed with a `Backend` and `root_path` string.

## STORE-002: Path Validation

**Invariant:** All path arguments are validated via `RemotePath`.

## STORE-003: Root Path Scoping

**Invariant:** Store prepends `root_path` to all relative paths before delegating to the backend.

## STORE-004: Delegation

**Invariant:** All I/O is delegated to the backend. Store adds no I/O logic of its own.

## STORE-005: Capability Check

**Invariant:** `supports(capability)` checks whether the backend supports a capability.

## STORE-006: Capability Gating

**Invariant:** Capability-gated methods raise `CapabilityNotSupported` before delegating if the capability is missing.

## STORE-007: Thread Safety

**Invariant:** Store is immutable and safe to share across threads.

## STORE-008: Full API Surface

**Invariant:** Store exposes: `read`, `read_bytes`, `write`, `write_atomic`, `delete`, `delete_folder`, `exists`, `is_file`, `is_folder`, `list_files`, `list_folders`, `get_file_info`, `get_folder_info`, `move`, `copy`.
