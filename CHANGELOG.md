# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes.

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
