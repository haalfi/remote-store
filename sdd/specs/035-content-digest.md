# ContentDigest — Structured File Digest Model

## Overview

`ContentDigest` is a frozen dataclass representing a verified content
digest with a known algorithm. It replaces the underspecified
`FileInfo.checksum: str | None` field with two structured fields:
`FileInfo.digest: ContentDigest | None` (verified content hash) and
`FileInfo.etag: str | None` (opaque backend tag). This separates
comparable content hashes from opaque change-detection tokens.

See [middleware architecture research](../research/research-store-middleware-architecture.md) §5
for the full problem analysis and design rationale.

## CDG-001: ContentDigest Dataclass

**Invariant:** `ContentDigest` is a frozen dataclass with two required
fields: `algorithm` (`str`) and `value` (`str`).

**Postconditions:**
- Attribute assignment raises `FrozenInstanceError`.
- `algorithm` is always stored lowercase (e.g., `"sha256"`, not `"SHA-256"`).
- `value` is always stored as lowercase hexadecimal, no prefix, no separators.
- Construction with uppercase `algorithm` or `value` normalizes to lowercase.

## CDG-002: ContentDigest Equality

**Invariant:** Two `ContentDigest` values are equal iff both `algorithm`
and `value` match (after normalization). Standard dataclass equality
applies — no custom `__eq__`.

**Postconditions:**
- `ContentDigest("sha256", "abc") == ContentDigest("SHA256", "ABC")` is `True`
  (both normalized at construction time).
- `ContentDigest` is hashable (frozen dataclass default).

## CDG-003: ContentDigest Validation

**Invariant:** `ContentDigest.__post_init__` validates inputs.

**Raises:**
- `ValueError` if `algorithm` is empty.
- `ValueError` if `value` is empty.
- `ValueError` if `value` contains non-hex characters after stripping whitespace.

## CDG-004: FileInfo.digest and FileInfo.etag

**Invariant:** `FileInfo` has two optional fields replacing `checksum`:
- `digest` (`ContentDigest | None`, default `None`) — verified content
  hash with known algorithm. Populated only when the backend guarantees
  the value represents actual file content.
- `etag` (`str | None`, default `None`) — opaque backend-provided tag
  for change detection. Not comparable across backends, not guaranteed
  to be a content hash.

**Postconditions:**
- `FileInfo.checksum` is removed.
- Field ordering: `digest` and `etag` appear after `modified_at`,
  before `content_type`.

## CDG-005: Module Exports

**Invariant:** `ContentDigest` is exported from `remote_store._models`
and re-exported in `remote_store.__init__.__all__`.
