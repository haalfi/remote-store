"""Write helpers with client-side content hashing.

Guarantees a populated ``WriteResult.digest`` regardless of whether the
backend declares ``WRITE_RESULT_NATIVE``. The hash is always computed
client-side over the bytes as they are written.

Spec: EW-001..EW-004 in ``sdd/specs/046-ext-write.md``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
from typing import TYPE_CHECKING

from remote_store import ContentDigest, RemotePath, WriteResult
from remote_store._store import (
    _validate_metadata,  # private: no public equivalent; ext.write needs this validation helper
)
from remote_store.ext.streams import ChecksumReader, ChecksumWriter

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from typing import BinaryIO

    from remote_store import Store

__all__ = [
    "HashingAtomicWriter",
    "open_atomic_with_hash",
    "write_with_hash",
]


class HashingAtomicWriter(ChecksumWriter):
    """Writable stream wrapper used by ``open_atomic_with_hash``.

    Subclasses ``ChecksumWriter`` to add a ``.result`` attribute that
    is populated with a ``WriteResult`` after the context manager exits
    successfully.  ``result`` is ``None`` if the block raised.
    """

    result: WriteResult | None
    _bytes_written: int

    def __init__(self, inner: BinaryIO, algorithm: str = "sha256") -> None:
        super().__init__(inner, algorithm=algorithm)
        self.result = None
        self._bytes_written = 0

    def write(self, data: bytes | bytearray) -> int:
        n = super().write(data)
        self._bytes_written += len(data)
        return n


def write_with_hash(
    store: Store,
    path: str,
    content: BinaryIO | bytes,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult:
    """Write *content* to *path* and return a ``WriteResult`` with a client-computed digest.

    Works on every backend declaring ``Capability.WRITE`` (EW-002).
    The hash is always computed client-side regardless of
    ``WRITE_RESULT_NATIVE``.

    Args:
        store: The Store to write to.
        path: Store-relative file path.
        content: ``bytes`` or readable binary stream.
        algorithm: Hash algorithm name (default ``"sha256"``).
        overwrite: If ``False``, raises ``AlreadyExists`` when *path* exists.
        metadata: Optional user metadata (see ``Store.write()``).

    Returns:
        ``WriteResult`` with ``digest`` populated from the client-side hash.
    """
    if isinstance(content, (bytes, bytearray)):
        digest_value = hashlib.new(algorithm, content).hexdigest()
        result = store.write(path, io.BytesIO(content), overwrite=overwrite, metadata=metadata)
    else:
        reader = ChecksumReader(content, algorithm=algorithm)
        result = store.write(path, reader, overwrite=overwrite, metadata=metadata)  # type: ignore[arg-type]
        digest_value = reader.hexdigest()

    return dataclasses.replace(result, digest=ContentDigest(algorithm=algorithm, value=digest_value))


@contextlib.contextmanager
def open_atomic_with_hash(
    store: Store,
    path: str,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> Iterator[HashingAtomicWriter]:
    """Context manager for streaming atomic writes with client-side hashing.

    Requires ``Capability.ATOMIC_WRITE``.  On successful exit, the
    yielded ``HashingAtomicWriter.result`` is a ``WriteResult`` with
    ``digest`` populated.  On exception ``result`` remains ``None``.

    **Metadata branch:** When *metadata* is non-empty, the implementation
    buffers all written bytes in memory (``io.BytesIO``) and then calls
    ``store.write_atomic()`` on exit.  This means (a) the full payload is
    held in RAM, and (b) validation errors (``ValueError``) and capability
    checks (``CapabilityNotSupported``) are raised after the caller has
    finished writing — not before.  For large payloads, prefer calling
    ``store.write()`` directly with ``metadata=``.

    **``source`` field:** Both branches always set ``source="basic"`` on
    the returned ``WriteResult``.  The metadata branch discards the
    ``source`` returned by ``store.write_atomic()`` because EW-004 cannot
    be honored for the no-metadata branch (``open_atomic`` returns only a
    stream, not a ``WriteResult``), so both branches use the same value
    for consistency.

    Args:
        store: The Store to write to.
        path: Store-relative file path.
        algorithm: Hash algorithm name (default ``"sha256"``).
        overwrite: If ``False``, raises ``AlreadyExists`` when *path* exists.
        metadata: Optional user metadata forwarded to ``Store.write_atomic()``
            on backends that declare ``USER_METADATA``.

    Yields:
        ``HashingAtomicWriter`` — write to it as a binary stream.

    Raises:
        CapabilityNotSupported: If the backend lacks ``ATOMIC_WRITE``.
        AlreadyExists: If *path* exists and *overwrite* is ``False``.
    """
    _validate_metadata(metadata)
    writer: HashingAtomicWriter | None = None
    if metadata:
        buf = io.BytesIO()
        writer = HashingAtomicWriter(buf, algorithm=algorithm)
        yield writer
        buf.seek(0)
        result = store.write_atomic(path, buf.read(), overwrite=overwrite, metadata=metadata)
        writer.result = WriteResult(
            path=result.path,
            size=writer._bytes_written,
            source="basic",
            digest=ContentDigest(algorithm=algorithm, value=writer.hexdigest()),
        )
    else:
        with store.open_atomic(path, overwrite=overwrite) as f:
            writer = HashingAtomicWriter(f, algorithm=algorithm)
            yield writer
        writer.result = WriteResult(
            path=RemotePath(path),
            size=writer._bytes_written,
            source="basic",
            digest=ContentDigest(algorithm=algorithm, value=writer.hexdigest()),
        )
