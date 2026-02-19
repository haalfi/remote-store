# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes.

## [Unreleased]

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
