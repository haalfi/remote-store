# Add Backend — Scaffold a New Backend Implementation

You are scaffolding a new backend for the remote-store project. This skill
guides you through the complete 11-step checklist from CONTRIBUTING.md and
generates the necessary boilerplate.

## Arguments

The user should provide:
- **Backend name** (e.g., `gcs`, `ftp`) — used for file names and registration
- **Display name** (e.g., `Google Cloud Storage`, `FTP`) — used in docs
- **Optional dependency** (e.g., `gcsfs>=2023.1`) — leave empty for stdlib-only backends

If not provided, ask the user for these values before proceeding.

## Step-by-Step Checklist

Execute all steps. The backend is not complete until every step is done.

### Step 1: Write the spec

Create `sdd/specs/NNN-<name>-backend.md` where NNN is the next available number.

Use existing backend specs (013-memory-backend.md for simplest reference,
008-s3-backend.md, 012-azure-backend.md for network backends) as reference
for format and coverage. The spec must define:
- Section IDs using a unique prefix (e.g., `GCS-001`, `FTP-001`, `MEM-001`)
- Constructor parameters and their semantics
- Connection lifecycle (lazy connect pattern)
- Path handling and `to_key()` semantics
- Error mapping (which native exceptions map to which `RemoteStoreError` subtypes)
- Backend-specific capabilities and limitations
- Atomic write strategy (native, simulated, or unsupported)

### Step 2: Implement the backend

Create `src/remote_store/backends/_<name>.py`. Use the following patterns
(mandatory for all backends):

- `from __future__ import annotations` at top
- Module docstring explaining why it exists
- Implement `Backend` ABC from `src/remote_store/_backend.py`
- **Lazy connection**: no network call in `__init__`, connect on first operation
- **Error mapping**: `_errors()` context manager mapping native exceptions to
  `RemoteStoreError` subtypes (NotFound, AlreadyExists, PermissionDenied, etc.)
- **Region comments**: `# region: BE-006` through `# endregion` for spec grouping
- **Streaming I/O**: `read()` must return a real file handle, NOT `BytesIO(full_content)`
- **`to_key()` method**: convert native/absolute paths to store-relative keys
- **`__repr__` masking**: secrets display as `'***'` when set, `None` when unset
- **Capability declaration**: accurate `capabilities()` property
- **Method ordering**: class vars, `__init__`, properties, public methods, dunders, private

Reference `src/remote_store/backends/_memory.py` (simplest, zero dependencies) or
`_s3.py` (network backend with lazy connection and error mapping) for the exact patterns.

### Step 3: Register the backend

Add the backend to `src/remote_store/_registry.py` in `_register_builtin_backends()`.
Follow the pattern used for S3/SFTP: try-import with fallback if dependency missing.
For zero-dependency backends, follow the Memory pattern (unconditional registration).

Also export from `src/remote_store/backends/__init__.py` if it should be importable.

### Step 4: Add conformance fixture

Add a pytest fixture in `tests/backends/conftest.py` that creates and tears down
the backend for testing. Follow existing fixtures (local_backend, s3_backend, etc.).

The entire conformance suite in `tests/backends/test_conformance.py` runs
automatically against any backend returned by a `*_backend` fixture.

### Step 5: Add backend-specific tests

Create `tests/backends/test_<name>.py` for backend-specific behavior not covered
by the conformance suite. Reference spec IDs with `@pytest.mark.spec("PREFIX-NNN")`.

### Step 6: Add user guide

Create `guides/backends/<name>.md` covering:
- Installation (`pip install remote-store[<name>]`)
- Configuration (constructor parameters)
- Usage examples
- Backend-specific notes and limitations

### Step 7: Update docs navigation

- Add the guide to `mkdocs.yml` nav under the Backends section
- Add entry to `docs-src/backends/_nav.yml`
- Update `guides/backends/index.md` Supported Backends table

### Step 8: Update README

- Add row to the Supported Backends table in `README.md`
- Add installation extra to the Installation section (if applicable)

### Step 9: Add configuration example

Add a backend config example to `examples/configuration.py`, following the
existing pattern for other backends.

### Step 10: Add optional dependency

If the backend requires external packages, add to `pyproject.toml`
`[project.optional-dependencies]` with minimum version pins (`>=X.Y`).

### Step 11: Update CONTRIBUTING.md

Update the Repository Structure section if the new files change the layout.

### Step 12: Update BACKLOG.md and CHANGELOG.md

- Mark relevant backlog items as done
- Add entry to `[Unreleased]` section in CHANGELOG.md

## Verification

After completing all steps:
1. Run `hatch run all` (lint + typecheck + test-cov + examples)
2. Run `/ripple-check` to verify cross-references
3. Confirm conformance tests pass for the new backend

## Important

- The #1 mistake when adding backends is forgetting cross-references (README table,
  docs nav, registry auto-registration). That's why steps 7-11 exist.
- The S3 Quick Start was broken in v0.5.0 because auto-registration missed 3
  backends (AF-001). Always verify the registry step.
- GLOB capability was declared but no `glob()` method existed (AF-002). Only
  declare capabilities that are actually implemented.
