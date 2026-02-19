# Remote Store Package — Design Specification (v1)

This document is the **authoritative design reference** for the Remote Store Package.  
It defines the final, agreed architecture and semantics and is intended to be used as a
continuous validation checklist during implementation and review.

---

## 1. Purpose

The package provides a **professional, production-grade, backend-agnostic abstraction for remote storage** that allows applications and citizen developers to interact with remote folders and files **without caring about the underlying storage technology**.

Initial target backends:

- S3 / MinIO
- Azure Storage (Blob / ADLS)
- SFTP / SSH-based filesystems

The package is designed to be:

- Easy to use
- Safe by default
- Streaming-first
- Extensible
- Framework-agnostic

---

## 2. Core Design Principles

1. Folder-scoped access is the primary abstraction  
2. Streaming is the default for all I/O  
3. Atomic writes are first-class  
4. Explicit configuration always wins  
5. Backend capabilities are declared, not assumed  
6. Fail early and explicitly  
7. No framework or event-loop dependencies
8. Minimal, rock-solid dependencies (see §2.1)
9. Compatible with structured concurrency
10. Citizen-dev friendly, senior-dev capable
11. fsspec is an implementation detail, not the API

### 2.1 Dependency Policy

**Runtime dependencies** — keep absolute minimal:
- The core package has **zero** runtime dependencies (`dependencies = []`).
- Backend extras pull in only what they need; each dependency must be well-known, battle-tested, and best-in-class for its purpose.
- Minimum versions are always pinned (`>=X.Y`) to guarantee the features we rely on.

**Dev dependencies** — keep minimal and non-overlapping:
- Every dev dependency must bring a clear, distinct benefit (no two tools covering the same job).
- Prefer established, single-purpose tools (ruff over pylint+isort+black, pytest over unittest, etc.).
- Pin minimum versions the same way as runtime extras.

---

## 3. Core Abstractions

### 3.1 Store

A **Store** represents a *logical remote folder* and is the **primary user-facing abstraction**.

Characteristics:

- Always scoped to a root path
- All operations use **relative paths**
- Immutable and cheap to create
- Safe to share across threads or tasks

Responsibilities:

- Read, write, list, move, copy, delete files
- Provide metadata
- Enforce safe defaults

No backend-specific terminology is exposed.

---

### 3.2 Path & Identity Objects

#### RemotePath (internal / semi-public)

- Immutable, validated path reference
- Normalization delegated to backend
- Provides parent / name resolution

#### RemoteFile / RemoteFolder (optional public)

- Immutable value objects
- No I/O behavior
- Used for validation, metadata, logging

Users typically do **not** construct these directly.

---

### 3.3 Metadata Objects

#### FileInfo

Immutable snapshot of file metadata.

Backend-agnostic fields:

- `path`
- `name`
- `size`
- `modified_at`

Optional:

- `checksum` (e.g. ETag, MD5)
- `content_type`
- backend-specific `extra` metadata

---

#### FolderInfo

Aggregated folder metadata.

Fields:

- `path`
- `file_count`
- `total_size`
- `modified_at`
- backend-specific `extra` metadata

Folder metadata may be:

- computed
- cached
- backend-provided

Policy is explicit and configurable.

---

## 4. Backend Adapter Contract

Backends encapsulate **all storage-specific behavior**.

### 4.1 Backend Identity & Capabilities

Each backend declares:

- name (e.g. `s3`, `azure`, `sftp`)
- scheme
- supported features (atomic writes, copy, move, glob, recursion, metadata)
- case sensitivity
- path constraints

Capabilities are **queried, not inferred**.

---

### 4.2 Path Handling

Backends define:

- path normalization rules
- validation logic
- canonical representation
- reverse resolution via `to_key()` (native/absolute path → backend-relative key)

The Store composes `Backend.to_key()` with its own `root_path` stripping to
provide a full native-to-store-relative conversion. Listing methods apply this
automatically so that returned paths are directly usable as input (round-trip
invariant). No implicit path rewriting occurs in the core.

---

### 4.3 I/O Operations

All backends must support:

- Streaming reads
- Streaming writes
- Existence checks
- File vs folder distinction
- Deletion

Internal buffering is allowed, but the exposed API is always streaming.

---

### 4.4 Atomic Writes

Atomic writes are capability-driven.

- If supported:
  - Writes go to a temporary location
  - Commit is atomic from the reader’s perspective
- If not supported:
  - Backend raises a capability error
  - Core decides fallback behavior

Atomicity is **never assumed**.

---

### 4.5 Metadata & Listing

Backends must provide:

- File metadata
- Folder metadata
- Iteration over children

Optional features:

- Recursive listing
- Globbing

Unsupported features fail **explicitly**.

---

### 4.6 Move & Copy

- Guaranteed only within the same backend
- Overwrite behavior is explicit
- Cross-backend operations are handled outside the backend layer

---

### 4.7 Error Model

Backends must map native errors into normalized errors:

- NotFound
- AlreadyExists
- PermissionDenied
- InvalidPath
- CapabilityNotSupported
- BackendUnavailable

Backend-specific exceptions never leak upward.

---

## 5. Streaming & Cancellation Semantics

- All I/O is streaming-first
- Cancellation propagates naturally
- Cancellation is never swallowed or remapped
- Partially opened resources are cleaned up where possible

---

## 6. Configuration Model

### 6.1 Configuration as Description

Configuration **describes**, it does not instantiate.

It defines:

- backends
- credentials
- stores (folder-scoped entry points)

---

### 6.2 Store Profiles (Primary Unit)

A **store profile** defines:

- backend reference
- root path
- credential reference
- optional store-specific policies

Citizen developers interact with stores **by name**.

---

### 6.3 Backend Configuration

Backend configuration contains:

- connection options
- shared backend defaults

Credentials are not embedded by default.

---

### 6.4 Credential Resolution

Credentials are:

- referenced by name
- resolved via environment variables or external providers
- never hardcoded

Secrets are separated from non-secrets.

---

### 6.5 Configuration Resolution Rules (Locked)

1. Config-as-code has absolute priority  
2. Environment variables are used only if no config is provided  
3. No merging, no overrides  
4. Backend defaults apply last  

This ensures deterministic, test-safe behavior.

---

## 7. Registry

### 7.1 Purpose

The **Registry**:

- loads configuration
- validates it
- instantiates backend adapters lazily
- provides access to stores
- manages backend lifecycle hooks

It does **not**:

- manage application lifecycle
- spawn background tasks
- depend on async frameworks

---

### 7.2 Registry Behavior

- Created with optional config
- If config is provided → environment ignored
- If config is absent → environment used
- Validation happens immediately

---

### 7.3 Backend Lifecycle

- One backend adapter instance per backend config
- Shared across stores
- Lazy initialization
- Optional lifecycle hooks (`close`, `aclose`)

---

### 7.4 Store Lifecycle

- Stores are immutable views
- Cheap to create
- May be cached by the registry
- Safe for concurrent use

---

## 8. Concurrency & Lifecycle Integration

- No dependency on anyio / asyncio / trio
- No background tasks
- Explicit lifecycle hooks only
- Compatible with structured concurrency
- Task groups own execution and cancellation

Registry and backends are **passive resources**.

---

## 9. Explicitly Out of Scope

- Global singleton registries
- Implicit environment overrides
- Framework-specific integrations
- Async-only APIs
- Pandas-specific helpers in core
- Cross-backend copy/move in core
- Implicit background cleanup

---

## 10. Role of fsspec

- fsspec is used **internally** by backend adapters
- It is never exposed in the public API
- Backend adapters decide how to combine:
  - fsspec
  - boto3
  - pyarrow
  - adlfs
  - sshfs

---

## 11. Code Style

This section defines the coding conventions for the project. All code must pass `ruff check`, `ruff format`, and `mypy --strict`.

### 11.1 Formatting & Linting

- **Formatter/linter:** ruff (line-length 120)
- **Type checking:** mypy strict mode
- **`from __future__ import annotations`** in every module

### 11.2 Module & Package Descriptions

Every module starts with a 1–2 sentence docstring explaining *why it exists*:

```python
"""Normalized error hierarchy for remote_store."""
```

Package `__init__.py` files follow the same rule:

```python
"""Backend implementations for remote_store."""
```

### 11.3 Type Annotations

Public method signatures use PEP 604 union syntax (Python >=3.10):

```python
def __init__(self, config: RegistryConfig | None = None) -> None: ...
def write(self, path: str, content: BinaryIO | bytes, *, overwrite: bool = False) -> None: ...
```

- Required args are positional; behavior flags are keyword-only (`*`).
- `X | None` replaces `Optional[X]`, `X | Y` replaces `Union[X, Y]` (PEP 604).
- `typing` imports only for generics not yet built-in (`Callable`, `Iterator`, etc.).

### 11.4 Docstrings

reST-style (`:param:`, `:returns:`, `:raises:`). Short and purpose-focused:

```python
def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
    """Write content to a file.

    :param path: Relative path within the store.
    :param content: Bytes or binary stream to write.
    :param overwrite: If ``True``, replace existing file.
    :raises AlreadyExists: If file exists and ``overwrite`` is ``False``.
    """
```

### 11.5 Region Comments

Use `# region:` / `# endregion` for **conceptual grouping only** — not around things already collapsible in IDEs (classes, functions). Useful in large classes like `LocalBackend`:

```python
# region: BE-006 through BE-007: read operations
def read(self, path: str) -> BinaryIO:
    ...

def read_bytes(self, path: str) -> bytes:
    ...
# endregion
```

No empty lines between the region marker and the first item. One empty line before `# region:` and after `# endregion`.

### 11.6 Method Ordering

Within a class, methods are ordered by logical grouping:

1. Class variables / constants
2. `__init__`
3. Properties
4. Public methods (grouped by domain: read, write, delete, list, etc.)
5. Dunder methods (`__eq__`, `__hash__`, `__repr__`)
6. Private helpers

### 11.7 Comments

Minimal, long-term value only. Do not comment *what* the code does — comment *why* when the reason is non-obvious. No TODO comments without a linked issue.

### 11.8 Constants

- Public: `UPPER_SNAKE_CASE`
- Private: `_UPPER_SNAKE_CASE`

### 11.9 `__all__`

Declared only in public-facing `__init__.py` modules. Internal modules (`_errors.py`, etc.) do not need `__all__` — the underscore prefix signals "internal".

### 11.10 Error Messages

f-strings with context for human-readable tracebacks. Structured attributes (`.path`, `.backend`, `.capability`) for programmatic access:

```python
raise NotFound(f"File not found: {path}", path=path, backend=self.name)
```

### 11.11 Test Style

Tests are grouped into classes by spec aspect. The class docstring references the spec IDs covered:

```python
class TestRemotePathNormalization:
    """PATH-002 through PATH-006: normalization rules."""

    @pytest.mark.spec("PATH-002")
    def test_backslash_to_forward_slash(self) -> None:
        assert str(RemotePath("a\\b\\c")) == "a/b/c"

    @pytest.mark.spec("PATH-005")
    def test_collapse_consecutive_slashes(self) -> None:
        assert str(RemotePath("a///b")) == "a/b"
```

Each test method carries a `@pytest.mark.spec("ID")` marker for traceability.

---

**End of Design Specification**