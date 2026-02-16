# Specifications

Every feature in `remote-store` is defined by a specification before implementation begins. Specs are the single source of truth for behavior.

| # | Spec | Description |
|---|------|-------------|
| 001 | [Store API](001-store-api.md) | Core file operations interface |
| 002 | [Registry & Config](002-registry-config.md) | Configuration and backend wiring |
| 003 | [Backend Contract](003-backend-adapter-contract.md) | Abstract backend interface |
| 004 | [Path Model](004-path-model.md) | Path validation and normalization |
| 005 | [Error Model](005-error-model.md) | Exception hierarchy |
| 006 | [Streaming I/O](006-streaming-io.md) | Stream-based reads and writes |
| 007 | [Atomic Writes](007-atomic-writes.md) | Atomic write operations |
| 008 | [S3 Backend](008-s3-backend.md) | Amazon S3 backend implementation |
