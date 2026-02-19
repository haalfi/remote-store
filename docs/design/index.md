# Design

`remote-store` follows **Spec-Driven Development (SDD)**: every feature starts as a specification before any code is written. Architecture decisions are recorded as ADRs.

## Documents

- [Design Document](design-spec.md) -- the overall design and conventions
- [Process](process.md) -- the SDD methodology

## Specifications

Eleven specs define the full public API:

- [001: Store API](specs/001-store-api.md)
- [002: Registry & Config](specs/002-registry-config.md)
- [003: Backend Contract](specs/003-backend-adapter-contract.md)
- [004: Path Model](specs/004-path-model.md)
- [005: Error Model](specs/005-error-model.md)
- [006: Streaming I/O](specs/006-streaming-io.md)
- [007: Atomic Writes](specs/007-atomic-writes.md)
- [008: S3 Backend](specs/008-s3-backend.md)
- [009: SFTP Backend](specs/009-sftp-backend.md)
- [010: Native Path Resolution](specs/010-native-path-resolution.md)
- [011: S3-PyArrow Backend](specs/011-s3-pyarrow-backend.md)

## Architecture Decision Records

- [0001: Architecture -- Store, Registry, Backends](adrs/0001-architecture-store-registry-backends.md)
- [0002: Config Resolution -- No Merge](adrs/0002-config-resolution-no-merge.md)
- [0003: fsspec is an Implementation Detail](adrs/0003-fsspec-is-implementation-detail.md)
- [0004: Empty Path Semantics](adrs/0004-empty-path-semantics.md)
- [0005: Native Path Resolution](adrs/0005-native-path-resolution.md)
