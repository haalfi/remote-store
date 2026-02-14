# Backend Contract Specification

## Overview

The `Backend` ABC defines the contract all storage backends must implement. It is the most critical spec in the system — every operation, error condition, and capability is defined here.

## BE-001: Abstract Base Class

**Invariant:** `Backend` is an ABC. Subclasses must implement all abstract methods.

## BE-002: Name Property

**Invariant:** `name` property returns a unique identifier string for the backend type (e.g. `"local"`, `"s3"`).

## BE-003: Capabilities Property

**Invariant:** `capabilities` property returns a `CapabilitySet` declaring all supported operations.

## BE-004: exists()

**Invariant:** `exists(path)` returns `bool`. Returns `False` for missing paths — never raises `NotFound`.

## BE-005: is_file() / is_folder()

**Invariant:** `is_file(path)` returns `True` only if `path` is a file. `is_folder(path)` returns `True` only if `path` is a folder. Both return `False` for non-existent paths.

## BE-006: read()

**Invariant:** `read(path)` returns a `BinaryIO` stream for the file content.
**Raises:** `NotFound` if the file does not exist.

## BE-007: read_bytes()

**Invariant:** `read_bytes(path)` returns the full file content as `bytes`.
**Raises:** `NotFound` if the file does not exist.

## BE-008: write()

**Invariant:** `write(path, content, overwrite=False)` creates or overwrites a file.
**Preconditions:** `content` is `bytes` or `BinaryIO`.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.

## BE-009: write Creates Intermediate Directories

**Invariant:** `write` creates any intermediate directories automatically.

## BE-010: write_atomic()

**Invariant:** `write_atomic(path, content, overwrite=False)` writes via a temporary file + atomic rename.
**Raises:** `AlreadyExists` if the file exists and `overwrite=False`.

## BE-011: write_atomic Capability Gate

**Invariant:** `write_atomic` raises `CapabilityNotSupported` if the backend lacks `ATOMIC_WRITE`.

## BE-012: delete()

**Invariant:** `delete(path, missing_ok=False)` removes a file.
**Raises:** `NotFound` if the file is missing and `missing_ok=False`.
**Postconditions:** If `missing_ok=True`, no error for missing files.

## BE-013: delete_folder()

**Invariant:** `delete_folder(path, recursive=False, missing_ok=False)` removes a folder.
**Raises:** `NotFound` if the folder is missing and `missing_ok=False`. Fails if folder is non-empty and `recursive=False`.

## BE-014: list_files()

**Invariant:** `list_files(path, recursive=False)` returns `Iterator[FileInfo]`.
**Postconditions:** Returns only files, not folders. If `recursive=True`, includes files in all subdirectories.

## BE-015: list_folders()

**Invariant:** `list_folders(path)` returns `Iterator[str]` of immediate subfolder names.

## BE-016: get_file_info()

**Invariant:** `get_file_info(path)` returns `FileInfo`.
**Raises:** `NotFound` if the file does not exist.

## BE-017: get_folder_info()

**Invariant:** `get_folder_info(path)` returns `FolderInfo`.
**Raises:** `NotFound` if the folder does not exist.

## BE-018: move()

**Invariant:** `move(src, dst, overwrite=False)` renames/moves a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

## BE-019: copy()

**Invariant:** `copy(src, dst, overwrite=False)` duplicates a file.
**Raises:** `NotFound` if `src` does not exist. `AlreadyExists` if `dst` exists and `overwrite=False`.

## BE-020: close()

**Invariant:** `close()` is optional (default no-op). Called for resource cleanup.

## BE-021: Error Mapping

**Invariant:** Backend-native exceptions never leak. All exceptions are mapped to `remote_store` error types.

## BE-022: unwrap()

**Invariant:** `unwrap(type_hint)` returns the native backend handle if it matches the requested type.
**Raises:** `CapabilityNotSupported` if the backend cannot provide the requested type.
