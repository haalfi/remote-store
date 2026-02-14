# Models Specification

## Overview

Immutable data objects representing file and folder metadata, and identity value objects for remote resources.

## MOD-001: FileInfo Immutability

**Invariant:** `FileInfo` is a frozen dataclass — immutable after construction.
**Postconditions:** Attribute assignment raises `FrozenInstanceError`.

## MOD-002: FileInfo Required Fields

**Invariant:** `FileInfo` has required fields: `path` (`RemotePath`), `name` (`str`), `size` (`int`), `modified_at` (`datetime`).

## MOD-003: FileInfo Optional Fields

**Invariant:** `FileInfo` has optional fields: `checksum` (`str | None`, default `None`), `content_type` (`str | None`, default `None`), `extra` (`dict[str, object]`, default empty dict).

## MOD-004: FolderInfo Required Fields

**Invariant:** `FolderInfo` is a frozen dataclass with required fields: `path` (`RemotePath`), `file_count` (`int`), `total_size` (`int`).

## MOD-005: FolderInfo Optional Fields

**Invariant:** `FolderInfo` optional fields: `modified_at` (`datetime | None`, default `None`), `extra` (`dict[str, object]`, default empty dict).

## MOD-006: RemoteFile and RemoteFolder

**Invariant:** `RemoteFile` and `RemoteFolder` are immutable value objects holding a `RemotePath` via a `path` attribute.

## MOD-007: Equality and Hashing

**Invariant:** `FileInfo`, `FolderInfo`, `RemoteFile`, and `RemoteFolder` support equality and hashing based on `path`.
