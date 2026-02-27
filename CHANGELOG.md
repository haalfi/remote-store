# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes.

## [Unreleased]

### Added

- **`Store.child(subpath)` — runtime sub-scoping** -- returns a new Store scoped to a subfolder, sharing the parent's backend instance (no new connections). Child stores do not close the shared backend on `close()` or context manager exit. Validated via `RemotePath`, chainable (`store.child("a").child("b")`), equality-transparent with directly constructed stores. Spec: `015-store-child.md` (ID-021)
- **Cloud backend examples** -- 5 new example scripts (`s3_backend.py`, `s3_pyarrow_backend.py`, `sftp_backend.py`, `azure_backend.py`, `store_child.py`) demonstrating each backend with self-contained env-var configuration and graceful failure messages. All Store API methods now have example coverage
- **Claude Code reusable skills** -- 6 slash-command skills in `.claude/commands/` codifying recurring workflows: `/ripple-check` (cross-reference validation), `/release` (6-phase release checklist), `/add-backend` (12-step scaffolding), `/backlog-sync` (backlog update helper), `/pr-preflight` (11-check pre-submission validation), `/add-spec` (SDD spec + test scaffolding) (ID-030)

### Changed

- **Release checklist expanded** -- replaced the 5-item release checklist in CONTRIBUTING.md with a 6-phase process covering pre-flight, content freeze, version bump, validation, ship with PR review gate, and post-release verification. GitHub Release is the intended single trigger for PyPI publish and docs deploy (ID-028, ID-029 track the CI changes)

### Fixed

- **`streaming_io.py` example leaked file handles on Windows** -- `store.read()` streams were not closed before `TemporaryDirectory` cleanup, causing `PermissionError` on Windows due to file locking. Streams are now used as context managers

## [0.7.0] - 2026-02-27

### Added

- **`MemoryBackend` — in-memory backend** -- tree-indexed, zero dependencies, no filesystem access. Supports all 8 capabilities with zero conformance test skips. Primary use cases: unit testing, interactive exploration, documentation examples, CI speed. Registered as `"memory"` backend type, always available (no optional extra). Store test fixtures migrated from `LocalBackend` + `tempfile` to `MemoryBackend` (ID-017)
- **PyArrow FileSystemHandler adapter spec** -- drafted `sdd/specs/014-pyarrow-filesystem-adapter.md` for `StoreFileSystemHandler` wrapping any `Store` into a `pyarrow.fs.PyFileSystem`. Tiered read strategy (native fast path / BufferReader / PythonFile), spill-to-disk writes, complete error mapping (ID-016)
- **Backend `__repr__` with credential masking** -- all 6 backends now implement `__repr__()`. Secrets display as `'***'` when set and `None` when unset; identifiers (bucket, host, container) are shown in clear text (AF-008)

### Changed

- **S3/S3-PyArrow `get_folder_info()` on empty folders** -- no longer raises `NotFound`; the `exists()` check already gates non-existent paths. Azure non-HNS retains current behavior since virtual folders can't be empty (AF-004)
- **`Registry.close()` error handling** -- now closes all backends even if one raises, always clears the cache, and re-raises the first error (AF-009)

### Removed

- **`RemoteFile` / `RemoteFolder` model classes** -- removed dead code from models, `__all__`, tests, docs, and specs (AF-011)

### Fixed

- **README Azure SDK name** -- corrected from wrong package name to `azure-storage-file-datalake` (AF-015)
- **CONTRIBUTING.md** -- added spec 012 reference (AF-015)
- **Azure configuration example** -- added to `examples/configuration.py` (AF-015)

## [0.6.0] - 2026-02-25

### Added

- **`DirectoryNotEmpty` error type** -- new `RemoteStoreError` subclass raised when a non-recursive folder delete targets a non-empty folder. Replaces generic `NotFound` with a descriptive error (AF-005)
- **`_ErrorMappingStream`** -- `io.RawIOBase` proxy that wraps streams returned by `Backend.read()`, catching `OSError` during lazy reads and mapping them through each backend's error classifier. Prevents native exceptions from leaking after `_errors()` context manager exits (AF-006)
- **Auto-registration of all backends** -- `_register_builtin_backends()` now registers S3, SFTP, and S3-PyArrow backends (in addition to local and Azure) when their dependencies are installed (AF-001)
- **SFTP `_map_exception()` method** -- single source of truth for SFTP error classification, used by both `_errors()` and `_ErrorMappingStream` (AF-006)
- **SFTP empty folder support** -- `get_folder_info()` on an empty SFTP directory now returns `FolderInfo(file_count=0)` instead of raising `NotFound` (AF-004)

### Changed

- **BREAKING**: Removed `Capability.GLOB` and `Capability.RECURSIVE_LIST` enum members that had no corresponding backend methods (AF-002)
- **S3/S3-PyArrow `close()`** -- no longer calls `clear_instance_cache()`, which was a global side-effect affecting all s3fs instances in the process (AF-003)
- **Azure/S3-PyArrow `read()`** -- eliminated double-buffering by wrapping `_ErrorMappingStream` directly in `BufferedReader` instead of nesting two `BufferedReader` layers

### Fixed

- **Lazy stream error mapping** -- `OSError` raised during `stream.read()` after `Backend.read()` returns is now properly mapped to `RemoteStoreError` subtypes instead of leaking as raw exceptions (AF-006)
- **Exception chaining** -- stream error mapping uses `from exc` to preserve original traceback for debugging

---

## [0.5.0] - 2026-02-23

### Added

- **Azure backend** (`AzureBackend`) -- new built-in backend for Azure Blob Storage and ADLS Gen2 using `azure-storage-file-datalake` directly. Adapts at runtime to Hierarchical Namespace (HNS) accounts for atomic rename and real directories, while remaining fully functional on plain Blob Storage. Install with `pip install "remote-store[azure]"`. (BK-001, spec 012)
- **Streaming reads for Azure** -- `read()` returns a forward-only streaming `BinaryIO` via `_AzureBinaryIO` adapter wrapping `StorageStreamDownloader.chunks()`, consistent with other backends
- **Azurite CI integration** -- Azure backend tests run against Azurite Docker emulator in CI
- **Azure backend guide** -- `guides/backends/azure.md` with installation, auth options, HNS vs non-HNS behavior, and Azurite local development

### Changed

- **SIO-001 seekability clarification** -- `read()` streams are not guaranteed to be seekable; seekability is a backend-level property. Callers needing seekability should use `read_bytes()` + `BytesIO`
- **AZ-020 spec updated** -- changed from BytesIO wrapper to streaming adapter

---

## [0.4.4] - 2026-02-23

### Added

- **Community standards** -- CODE_OF_CONDUCT.md (Contributor Covenant v2.1), SECURITY.md (vulnerability reporting policy), issue templates (bug report + feature request), PR template, and CODEOWNERS
- **Dependabot** -- automated dependency updates for pip and GitHub Actions (weekly, Mondays)
- **CodeQL** -- GitHub code scanning workflow for Python on push/PR and weekly schedule
- Security section in README linking to vulnerability reporting
- **Streaming conformance tests** -- 5 tests (x4 backends) that prevent regression of v0.4.3 streaming fixes: not-BytesIO assertion, chunked reads, stream position, BinaryIO write, and write-from-current-position (SIO-001, SIO-003)

---

## [0.4.3] - 2026-02-19

### Fixed

- **Streaming read/write loaded entire files into memory** -- all four backends (Local, S3, S3-PyArrow, SFTP) now use true streaming for `read()` and `write()` with `BinaryIO` content, matching the spec's streaming-first intent
- **SFTP copy/move buffered entire files** -- `copy()` and `move()` fallback now stream chunks using `_CHUNK_SIZE` instead of loading source into memory
- **Broken API reference link in README** -- ReadTheDocs URL was missing `/en/latest/` prefix, causing 404 on PyPI

### Changed

- **Versioning docs consolidated** -- removed outdated duplicate from `sdd/000-process.md`, canonical source is now `CONTRIBUTING.md`

---

## [0.4.2] - 2026-02-19

### Fixed

- **PyPI relative links broken** -- README example scripts, notebooks, and CONTRIBUTING.md links used relative paths (`examples/quickstart.py`, `CONTRIBUTING.md`, etc.) which resolve to 404 on PyPI; converted all to absolute GitHub URLs

---

## [0.4.1] - 2026-02-19

### Fixed

- **PyPI logo broken** -- README image used relative path (`assets/logo.png`) which doesn't resolve on PyPI's CDN; changed to absolute raw GitHub URL
- **Documentation site out of date** -- specs 010 (native path resolution) and 011 (S3-PyArrow backend) and ADR-0005 were missing from the MkDocs site and navigation
- **Navigation on RTD** -- added `navigation.instant` to MkDocs Material config so sidebar stays visible across page loads

### Added

- PyPI version, Python versions, Read the Docs, and license badges in README
- Read the Docs publishing (`remote-store.readthedocs.io`)
- "Going Public" section in DEVELOPMENT_STORY.md

### Changed

- `Documentation` URL in `pyproject.toml` now points to Read the Docs instead of GitHub Pages
- `CITATION.cff` URL updated to Read the Docs
- `.readthedocs.yaml` build OS bumped to ubuntu-24.04

---

## [0.4.0] - 2026-02-19

### Added

- **S3-PyArrow hybrid backend** -- uses PyArrow's C++ S3 filesystem for reads/writes/copies (higher throughput for large files) and s3fs for listing/metadata/deletion. Drop-in alternative to `S3Backend` with the same constructor signature.
  - Install via `pip install "remote-store[s3-pyarrow]"`
  - Spec: `sdd/specs/011-s3-pyarrow-backend.md`
- New optional extra: `s3-pyarrow` (requires `s3fs>=2024.2.0` and `pyarrow>=14.0.0`)
- Dual `unwrap()` support: returns either `pyarrow.fs.S3FileSystem` or `s3fs.S3FileSystem`

---

## [0.3.0] - 2026-02-18

### Added

- **`Store.to_key(path)`** — public method to convert backend-native paths to store-relative keys
- **`Backend.to_key()`** — backend-level native-path-to-key conversion
- Python 3.14 support — added to CI test matrix and PyPI classifiers
- **PyPI publish workflow** — trusted publishing (OIDC) via GitHub Actions on `v*` tags (BL-001)
- **SFTP backend documentation** — `docs/backends/sftp.md` with installation, usage, and API reference (BL-002)
- **CITATION.cff** — enables GitHub's "Cite this repository" button (BL-005)
- **Development backlog** — `sdd/BACKLOG.md` for tracking release blockers, prioritized work, and ideas
- Versioning policy added to SDD process doc (`sdd/000-process.md`)
- Set up GitHub Pages docs hosting via `actions/deploy-pages` (BL-008)

### Fixed

- Store round-trip bug: `list()` returned backend-relative paths that included `root_path`, breaking re-use as input to `read()`/`delete()`
- CI: fixed cross-platform `type: ignore` comments for S3 backend

### Changed

- **README rewritten** — approachable, dev-friendly tone with scannable layout (BL-003, BL-004)
- Pinned minimum versions on public extras: `s3fs>=2024.2.0`, `paramiko>=2.2`, `tenacity>=4.0`
- Removed `typing-extensions` from core dependencies (unused -- Python 3.10+ covers all needs)
- Removed `azure` extra (`adlfs`) -- no Azure backend exists yet; will be re-added with the backend

---

## [0.2.0] - 2026-02-17

### Added

- **SFTP backend** via pure paramiko with host key policies (STRICT / TOFU / AUTO_ADD), PEM key sanitization, and tenacity retry on transient SSH errors
- Simulated atomic writes (temp file + rename) with documented orphan-file caveat
- `HostKeyPolicy` enum and `load_private_key()` utility for key management
- `_sanitize_pem()` for Azure Key Vault PEM compatibility

### Changed

- `sftp` optional dependency changed from `paramiko + sshfs` to `paramiko + tenacity`
- Version bumped to 0.2.0

---

## [0.1.0] - 2026-02-14

### Added

- **Store** — primary user-facing abstraction for folder-scoped file operations
- **Registry** — backend lifecycle management with lazy instantiation and context manager support
- **RegistryConfig / BackendConfig / StoreProfile** — declarative, immutable configuration with `from_dict()` for TOML/JSON parsing
- **RemotePath** — immutable, validated path value object with normalization and safety checks
- **Local backend** — stdlib-only reference implementation with full capability support
- **Capability system** — backends declare supported features; unsupported operations fail explicitly
- **Normalized error hierarchy** — `NotFound`, `AlreadyExists`, `InvalidPath`, `PermissionDenied`, `CapabilityNotSupported`, `BackendUnavailable`
- **Streaming-first I/O** — `read()` returns `BinaryIO`, `write()` accepts `bytes | BinaryIO`
- **Atomic writes** — `write_atomic()` via temp-file-and-rename
- **Empty path support** — `""` resolves to store root for folder/query operations (see ADR-0004)
- **Full type safety** — mypy strict mode, `py.typed` marker
- **Spec-driven development** — 7 specifications, 4 ADRs, full test traceability with `@pytest.mark.spec`
- **Examples** — 6 runnable Python scripts and 3 Jupyter notebooks
- **CI** — ruff, mypy, pytest (Python 3.10–3.13), example validation

### Known Limitations

- Only the local filesystem backend is implemented. S3, Azure, and SFTP backends are planned.
- No glob/pattern matching support yet (`Capability.GLOB` is declared but unused).
- No async API (sync-only by design; compatible with structured concurrency).
