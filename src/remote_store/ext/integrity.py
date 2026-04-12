"""Checksum verification helpers over Store's public API.

Pure functions for computing and verifying file integrity.  These compose
``store.read()`` with [ChecksumReader][remote_store.ext.streams.ChecksumReader]
internally — users don't need to manage stream lifecycle.

!!! example

    ```python
    from remote_store.ext.integrity import checksum, verify

    algorithm, hex_digest = checksum(store, "data/file.bin")
    print(algorithm, hex_digest)

    ok = verify(store, "data/file.bin", expected="a3f2b8...", algorithm="sha256")
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from remote_store._models import ContentDigest
from remote_store.ext.streams import ChecksumReader

if TYPE_CHECKING:
    from remote_store._store import Store

__all__ = ["checksum", "content_digest", "verify", "verify_hex"]

_CHUNK_SIZE = 1_048_576  # 1 MiB


def checksum(store: Store, path: str, algorithm: str = "sha256") -> tuple[str, str]:
    """Compute the checksum of a file in the store.

    Reads the file in chunks (never fully materialized in memory) and
    returns a ``(algorithm, hex_digest)`` tuple.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        algorithm: Hash algorithm name (default ``"sha256"``).

    Returns:
        Tuple of ``(algorithm, hex_digest)`` with lowercase values.

    Raises:
        NotFound: If the file does not exist.
        ValueError: If the algorithm is not supported by ``hashlib``.
    """
    stream = store.read(path)
    try:
        reader = ChecksumReader(stream, algorithm=algorithm)
        while reader.read(_CHUNK_SIZE):
            pass
        return (reader.algorithm, reader.hexdigest())
    finally:
        stream.close()


def content_digest(store: Store, path: str, algorithm: str = "sha256") -> ContentDigest:
    """Compute the content digest of a file in the store.

    Like [checksum][remote_store.ext.integrity.checksum], but returns a
    [ContentDigest][remote_store._models.ContentDigest] instead of a raw tuple.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        algorithm: Hash algorithm name (default ``"sha256"``).

    Returns:
        A [ContentDigest][remote_store._models.ContentDigest] with normalized algorithm and hex value.

    Raises:
        NotFound: If the file does not exist.
        ValueError: If the algorithm is not supported by ``hashlib``.
    """
    algo, hex_digest = checksum(store, path, algorithm=algorithm)
    return ContentDigest(algo, hex_digest)


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
        ValueError: If the algorithm is not supported by ``hashlib``.
    """
    _, hex_digest = checksum(store, path, algorithm=algorithm)
    return hex_digest == expected.lower()


def verify_hex(
    store: Store,
    path: str,
    algorithm: str,
    expected_hex: str,
) -> bool:
    """Verify a file's checksum given an algorithm and expected hex value.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        algorithm: Hash algorithm name.
        expected_hex: Expected hex digest (case-insensitive).

    Returns:
        ``True`` if the computed digest matches *expected_hex*.

    Raises:
        NotFound: If the file does not exist.
        ValueError: If the algorithm is not supported by ``hashlib``.
    """
    _, hex_digest = checksum(store, path, algorithm=algorithm)
    return hex_digest == expected_hex.lower()
