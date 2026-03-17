"""Checksum verification helpers over Store's public API.

Pure functions for computing and verifying file integrity.  These compose
``store.read()`` with :class:`~remote_store.ext.streams.ChecksumReader`
internally — users don't need to manage stream lifecycle.

Usage:

```python
from remote_store.ext.integrity import checksum, verify

digest = checksum(store, "data/file.bin")
print(digest.algorithm, digest.value)

ok = verify(store, "data/file.bin", expected="a3f2b8...", algorithm="sha256")
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._models import ContentDigest
from remote_store.ext.streams import ChecksumReader

if TYPE_CHECKING:
    from remote_store._store import Store

__all__ = ["checksum", "verify", "verify_digest"]

_CHUNK_SIZE = 1_048_576  # 1 MiB


def checksum(store: Store, path: str, algorithm: str = "sha256") -> ContentDigest:
    """Compute the checksum of a file in the store.

    Reads the file in chunks (never fully materialized in memory) and
    returns a :class:`~remote_store.ContentDigest`.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        algorithm: Hash algorithm name (default ``"sha256"``).

    Returns:
        ``ContentDigest`` with the computed digest.

    Raises:
        NotFound: If the file does not exist.
    """
    stream = store.read(path)
    try:
        reader = ChecksumReader(stream, algorithm=algorithm)
        while reader.read(_CHUNK_SIZE):
            pass
        return ContentDigest(algorithm=reader.algorithm, value=reader.hexdigest())
    finally:
        stream.close()


def verify(
    store: Store,
    path: str,
    expected: str,
    algorithm: str = "sha256",
) -> bool:
    """Verify a file's checksum against an expected hex value.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        expected: Expected hex digest (case-insensitive).
        algorithm: Hash algorithm name (default ``"sha256"``).

    Returns:
        ``True`` if the computed digest matches *expected*.

    Raises:
        NotFound: If the file does not exist.
    """
    computed = checksum(store, path, algorithm=algorithm)
    return computed.value == expected.lower()


def verify_digest(
    store: Store,
    path: str,
    expected: ContentDigest,
) -> bool:
    """Verify a file's checksum against an expected :class:`ContentDigest`.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        expected: Expected ``ContentDigest`` (algorithm + hex value).

    Returns:
        ``True`` if the computed digest matches *expected*.

    Raises:
        NotFound: If the file does not exist.
    """
    computed = checksum(store, path, algorithm=expected.algorithm)
    return computed == expected
