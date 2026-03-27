# Implementation Plan: ID-119 — SQLBlobBackend (v1)

## Goal

Implement `SQLBlobBackend` — a read-write key-value blob store backed by SQLAlchemy, with SQLite specializations. This is the v1 foundation per the research doc's prioritization. `SQLQueryBackend` (v2) and `CompositeStore` (ID-120) are out of scope.

## Scope

- `_SQLAlchemyBaseBackend` (shared base for future `SQLQueryBackend`)
- `SQLBlobBackend` (full Backend contract, all 10 capabilities)
- SQLite optimizations (WAL, blobopen streaming, PRAGMA tuning)
- Spec, tests, backlog updates, CHANGELOG, docs

## Dependencies

- `sqlalchemy>=2.0` (required extra)
- No PyArrow dependency (that's v2/SQLQueryBackend)

---

## Steps

### 1. Spec: `sdd/specs/040-sql-blob-backend.md`

Write the formal spec following existing spec format (e.g., 013-memory-backend.md). Cover:

- **SQL-BLOB-001..010**: Core operations (read, write, delete, list, move, copy, glob, metadata, atomic write, seekable read)
- **SQL-BLOB-011..015**: Schema definition, auto-creation, `create_table=False` introspection, column detection
- **SQL-BLOB-016..020**: Engine lifecycle (owned vs borrowed), health check, close/dispose, unwrap, context manager
- **SQL-BLOB-021..025**: SQLite specializations (WAL, `PRAGMA synchronous=NORMAL`, `blobopen()` streaming on 3.11+, `GLOB` operator)
- **SQL-BLOB-026..028**: `max_blob_size` guard, error mapping (SQLAlchemy → remote-store errors), thread safety
- **SQL-BLOB-030**: Capabilities declaration (all 10)

### 2. Backlog & CHANGELOG updates

- `sdd/BACKLOG.md`: Move ID-119 status to `[~]` in-progress, note "v1: SQLBlobBackend"
- `CHANGELOG.md`: Add `[Unreleased]` entry under **Added**: `SQLBlobBackend` — SQLAlchemy-based key-value blob storage with SQLite optimizations

### 3. Implement `_SQLAlchemyBaseBackend` + `SQLBlobBackend`

**File:** `src/remote_store/backends/_sqlalchemy.py`

#### 3a. `_SQLAlchemyBaseBackend(Backend)` — abstract shared base

```python
class _SQLAlchemyBaseBackend(Backend):
    """Shared base for SQLAlchemy-backed storage backends."""
```

- `__init__(url: str | None = None, *, engine: Engine | None = None)` — exactly one of `url` or `engine` required
  - `url` → create and own engine (`create_engine(url)`)
  - `engine` → borrow (close is no-op)
- `check_health()` → `SELECT 1`
- `close()` → dispose owned engine, no-op for borrowed
- `unwrap(type_hint)` → return `Engine`
- `_map_error()` context manager → catch `SQLAlchemyError` subtypes, raise `NotFound` / `AlreadyExists` / `PermissionDenied` / `BackendError`
- Detect SQLite via `engine.dialect.name == "sqlite"` for specialization flag

#### 3b. `SQLBlobBackend(_SQLAlchemyBaseBackend)` — full KV blob store

**Schema** (default table `remote_store_objects`):
```sql
CREATE TABLE remote_store_objects (
    key          TEXT PRIMARY KEY CHECK (length(key) > 0),
    data         BLOB NOT NULL,
    size         INTEGER NOT NULL,
    modified_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_type TEXT,
    digest       TEXT,
    extra        TEXT
);
```

**Constructor params:**
- `url: str | None` / `engine: Engine | None` (from base)
- `table_name: str = "remote_store_objects"`
- `create_table: bool = True`
- `max_blob_size: int | None = None`

**Capabilities:** All 10 (`READ`, `WRITE`, `DELETE`, `LIST`, `MOVE`, `COPY`, `ATOMIC_WRITE`, `METADATA`, `GLOB`, `SEEKABLE_READ`).

**Operation mapping:**

| Method | SQL |
|--------|-----|
| `exists(path)` | `SELECT 1 FROM t WHERE key = :key` |
| `is_file(path)` | Same as exists (all entries are files) |
| `is_folder(path)` | `SELECT 1 FROM t WHERE key LIKE :prefix` (prefix = path + "/") |
| `read(path)` | SQLite 3.11+: `blobopen()` → streaming `BinaryIO`. Else: `SELECT data WHERE key = :key` → `BytesIO` |
| `read_bytes(path)` | `SELECT data FROM t WHERE key = :key` |
| `write(path, content)` | `INSERT ... ON CONFLICT(key) DO UPDATE` (if overwrite) or `INSERT` (raise AlreadyExists) |
| `write_atomic(path, content)` | Same as write — single SQL statement is inherently atomic |
| `open_atomic(path)` | Yield `BytesIO` buffer; on success commit via write; on exception discard |
| `delete(path)` | `DELETE FROM t WHERE key = :key` |
| `delete_folder(path, recursive)` | `DELETE FROM t WHERE key LIKE :prefix` (recursive) or check-then-error |
| `list_files(path)` | `SELECT key, size, modified_at, ... FROM t WHERE key LIKE :prefix` with depth filtering for non-recursive |
| `list_folders(path)` | Derive virtual folder names from key prefixes |
| `get_file_info(path)` | `SELECT size, modified_at, content_type, digest, extra FROM t WHERE key = :key` |
| `get_folder_info(path)` | `SELECT COUNT(*), SUM(size), MAX(modified_at) FROM t WHERE key LIKE :prefix` |
| `move(src, dst)` | `UPDATE t SET key = :dst WHERE key = :src` (check dst doesn't exist unless overwrite) |
| `copy(src, dst)` | `INSERT INTO t SELECT :dst, data, ... FROM t WHERE key = :src` |
| `glob(pattern)` | Convert glob to SQL LIKE/GLOB; for SQLite use native `GLOB`, others use `LIKE` with conversion |

**SQLite specializations** (when `engine.dialect.name == "sqlite"`):
- On engine creation: `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`
- `read()`: Use `connection.connection.blobopen()` on Python ≥3.11 for streaming reads; fallback to `BytesIO(SELECT data)` on 3.10
- `glob()`: Use SQLite `GLOB` operator (case-sensitive, supports `*` and `?`) instead of `LIKE`

**Path handling:**
- Validate paths using the same rules as other backends (no `..`, no null bytes, no leading `/`)
- Store keys as normalized strings (forward slashes, no trailing slash)

**Thread safety:**
- SQLAlchemy engine handles connection pooling
- Each operation gets its own connection from the pool
- No shared mutable state beyond the engine

#### 3c. Error mapping

| SQLAlchemy exception | remote-store error |
|---------------------|--------------------|
| `IntegrityError` (duplicate key) | `AlreadyExists` |
| `OperationalError` (connection) | `BackendError` |
| `NoResultFound` / empty result | `NotFound` |
| `ProgrammingError` (permissions) | `PermissionDenied` |

### 4. Registration & packaging

- **`src/remote_store/backends/__init__.py`**: Add try/except import block for `SQLBlobBackend`
- **`src/remote_store/_registry.py`**: Add lazy registration under type name `"sql-blob"`
- **`pyproject.toml`**: Add optional dependency group:
  ```toml
  sql = ["sqlalchemy>=2.0"]
  ```
  Add `sqlalchemy>=2.0` to dev dependencies for testing.

### 5. Tests: `tests/test_backend_sqlblob.py`

Spec-traced tests with `@pytest.mark.spec("SQL-BLOB-NNN")`:

- **Schema tests**: auto-create table, custom table name, `create_table=False` with existing table, missing optional columns graceful degradation
- **CRUD tests**: write + read round-trip, overwrite=True/False, delete, delete_folder recursive/non-recursive, missing_ok
- **List tests**: list_files recursive/non-recursive, list_folders (virtual), iter_children, empty prefix
- **Metadata tests**: get_file_info all fields, get_folder_info aggregates, content_type, digest, extra JSON
- **Move/Copy tests**: move basic, move overwrite, copy basic, copy overwrite, move/copy missing source
- **Atomic write tests**: write_atomic, open_atomic success, open_atomic exception rollback
- **Glob tests**: `*`, `**`, `?` patterns, nested patterns
- **Seekable read**: read returns seekable, read_seekable
- **Engine lifecycle**: owned engine disposal, borrowed engine not disposed, check_health, unwrap
- **SQLite specializations**: WAL mode enabled, blobopen streaming (3.11+ only, skip on 3.10)
- **max_blob_size**: write exceeding limit raises error
- **Error mapping**: NotFound, AlreadyExists, path validation
- **Capabilities**: all 10 declared and functional
- **Concurrency**: concurrent writes from multiple threads

Target: ≥95% coverage on the new module.

### 6. Documentation

- **`guides/backends/sql-blob.md`**: User guide — installation, quickstart, SQLite example, PostgreSQL example, schema customization, performance guidelines, max_blob_size
- **`docs-src/api/backends/sql-blob.md`**: API reference page (`:::remote_store.backends.SQLBlobBackend`)
- **Update docs nav**: Add sql-blob entries to `docs-src/` `_nav.yml` files
- **README.md**: Add row to backends table (`SQLBlob | SQL databases via SQLAlchemy | sql`)
- **`examples/backends/sql_blob_example.py`**: Runnable example with SQLite (no credentials needed)

### 7. Final verification

- `hatch run lint` — clean
- `hatch run typecheck` — clean (mypy strict)
- `hatch run test` — all pass, ≥95% coverage
- Ripple-check per CLAUDE-REFERENCE.md (backend change touches: README backends table, pyproject.toml extras, guides, docs nav, examples, specs, CONTRIBUTING.md repo structure, registry)

---

## Out of scope (future work)

- `SQLQueryBackend` (v2 — ID-119 continued)
- `CompositeStore` (ID-120)
- `ResolutionPlan` introspection API (ID-121)
- `FileInfo.size: int | None` contract change (v2)
- ADBC / ConnectorX fast paths (v3)
- Column name mapping for existing tables (v2 if demand)

## Risks

| Risk | Mitigation |
|------|------------|
| `blobopen()` edge cases on concurrent access | Test with threading; fallback to `BytesIO` is always safe |
| Glob-to-SQL translation complexity | SQLite has native GLOB; for other dialects, convert `*`→`%`, `?`→`_` in LIKE |
| Virtual folder derivation performance on large tables | Index on `key` (PK) handles prefix scans; document scale guidelines |
| Engine pool exhaustion under load | Use SQLAlchemy defaults; document pool_size tuning for production |
