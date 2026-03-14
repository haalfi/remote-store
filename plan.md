# Implementation Plan: ID-075 — Dagster Integration (`ext.dagster`)

**Scope:** v1 only — `remote_store_io_manager(store)` factory function.
v2 (`DagsterStoreResource`, `RemoteStoreIOManager`) is explicitly deferred.

**Key decisions from research (`sdd/research/research-dagster-extension.md`):**
- Wrap raw `IOManager` base class (NOT `UPathIOManager` — avoids fsspec dep leak per ADR-0003)
- Serializer protocol with built-in pickle/JSON/Parquet
- Path from `context.get_asset_identifier()` → `"/".join(parts) + ext`
- `dagster>=1.9` floor; optional `pyarrow>=14.0` for Parquet serializer
- In-tree `ext/dagster.py` (consistent with `ext/arrow.py`, `ext/otel.py`)

---

## Step 1: Spec — `sdd/specs/031-ext-dagster.md`

Write the spec with prefix `DAG`, covering v1 scope:

| ID | Title |
|----|-------|
| DAG-001 | Pickle roundtrip (MemoryBackend) |
| DAG-002 | JSON roundtrip |
| DAG-003 | Parquet roundtrip (pandas DataFrame) |
| DAG-004 | Partitioned asset — path includes partition key |
| DAG-005 | Multi-segment asset key maps to nested path |
| DAG-006 | *(reserved for v2 — DagsterStoreResource)* |
| DAG-007 | Missing file raises NotFound on load |
| DAG-008 | handle_output adds metadata to context |
| DAG-009 | Custom serializer protocol respected |
| DAG-010 | Missing PyArrow for parquet gives helpful error |

Each section follows the spec format: Invariant, Preconditions, Postconditions, Raises, Example.

## Step 2: Tests — `tests/test_dagster.py`

Write tests *before* implementation (SDD workflow). Each test marked with `@pytest.mark.spec("DAG-NNN")`.

- Use `build_output_context` / `build_input_context` from dagster (no orchestrator needed)
- Use `MemoryBackend` for all tests (no I/O)
- DAG-003 (Parquet) conditionally skipped if pyarrow not installed
- DAG-010 tests the error message when pyarrow is missing (mock the import)

Test structure: one class per logical group (`TestPickleSerializer`, `TestJsonSerializer`, `TestParquetSerializer`, `TestPathGeneration`, `TestMetadata`, `TestCustomSerializer`, `TestErrorHandling`).

## Step 3: Implementation — `src/remote_store/ext/dagster.py`

**Exports (`__all__`):**
- `remote_store_io_manager` — factory function
- `Serializer` — protocol class (for custom serializers)
- `PickleSerializer`, `JsonSerializer`, `ParquetSerializer` — built-ins

**Internal:**
- `_RemoteStoreIOManagerImpl(IOManager)` — not exported
- `_asset_path(context, ext)` — derives storage path from asset identifier
- `_resolve_serializer(serializer)` — maps string names to instances

**Module structure:**
```
import guard for dagster (same pattern as ext/arrow.py)
Serializer protocol
PickleSerializer, JsonSerializer, ParquetSerializer
_asset_path helper
_RemoteStoreIOManagerImpl
remote_store_io_manager factory
```

**Key behaviors:**
- `handle_output(context, obj)`: serialize → `store.write(path, data)` → `context.add_output_metadata({"path": path, "size": len(data)})`
- `load_input(context)`: `store.read_bytes(path)` → deserialize → return
- `None` handling: write pickled `None` (Dagster convention — allows distinguishing "never materialized" from "materialized as None")
- Multi-partition `load_input`: deferred (open question #2 in research) — v1 handles single partition only

## Step 4: `pyproject.toml` — add `dagster` extra

Add under `[project.optional-dependencies]`:
```toml
dagster = ["dagster>=1.9"]
```

## Step 5: Guide — `guides/dagster.md`

Short user-facing guide covering:
- Installation (`pip install "remote-store[dagster]"`)
- Basic usage with `remote_store_io_manager`
- Serializer options (pickle, JSON, Parquet)
- Custom serializer example
- Usage with Registry
- Cross-reference to data-lake-patterns.md

## Step 6: Docs wiring

- `docs-src/api/ext-dagster.md` — API reference page with `:::` directives
- Update `docs-src/api/_nav.yml` — add ext-dagster entry
- Update `docs-src/api/index.md` — add row to extensions summary table

## Step 7: Ripple-check updates (same commit as code)

Per the ripple-check table for "An extension":
- **README.md**: add row to extensions table
- **CHANGELOG.md**: add entry under `[Unreleased]`
- **BACKLOG.md**: mark ID-075 as `[~]` with v1 done, v2 remaining
- **`docs-src/_nav.yml`**: add dagster guide if applicable

## Step 8: Lint, typecheck, test

```bash
hatch run lint
hatch run typecheck
hatch run test
```

Fix any issues before committing.

---

## Open questions to resolve during implementation

1. **`handle_output` for `None`**: Research recommends writing it (Dagster convention). Will implement this way.
2. **Multi-partition `load_input`**: Deferred — v1 supports single partition only. Document this limitation.
3. **`extension` override**: Not supported in v1 — extension comes from serializer.

## Files created/modified

| File | Action |
|------|--------|
| `sdd/specs/031-ext-dagster.md` | Create |
| `tests/test_dagster.py` | Create |
| `src/remote_store/ext/dagster.py` | Create |
| `guides/dagster.md` | Create |
| `docs-src/api/ext-dagster.md` | Create |
| `docs-src/api/_nav.yml` | Edit |
| `docs-src/api/index.md` | Edit |
| `pyproject.toml` | Edit |
| `README.md` | Edit |
| `CHANGELOG.md` | Edit |
| `sdd/BACKLOG.md` | Edit |
