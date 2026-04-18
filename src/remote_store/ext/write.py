"""Write helpers with client-side content hashing.

Provides two utilities that guarantee a populated ``WriteResult.digest``
regardless of whether the backend declares ``WRITE_RESULT_NATIVE``:

- ``write_with_hash`` — write bytes or a stream and return a
  ``WriteResult`` with ``digest`` computed client-side.
- ``open_atomic_with_hash`` — context manager variant for streaming
  atomic writes, yielding a ``HashingAtomicWriter`` whose ``.result``
  is populated after successful exit.

Spec: WR-014..WR-017 in ``sdd/specs/045-write-result.md``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
from typing import TYPE_CHECKING

from remote_store._models import ContentDigest, WriteResult
from remote_store.ext.streams import ChecksumWriter

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._store import Store
    from remote_store._types import WritableContent

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

    def __init__(self, inner: object, algorithm: str = "sha256") -> None:
        super().__init__(inner, algorithm=algorithm)  # type: ignore[arg-type]
        self.result = None


def write_with_hash(
    store: Store,
    path: str,
    content: WritableContent,
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult:
    """Write *content* to *path* and return a ``WriteResult`` with a client-computed digest.

    Works on every backend declaring ``Capability.WRITE`` (WR-015).
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
        readable: WritableContent = io.BytesIO(content)
    else:
        buf = io.BytesIO(content.read())
        digest_value = hashlib.new(algorithm, buf.getvalue()).hexdigest()
        buf.seek(0)
        readable = buf

    result = store.write(path, readable, overwrite=overwrite, metadata=metadata)
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
    writer: HashingAtomicWriter | None = None
    if metadata:
        # Accumulate bytes so metadata can be forwarded to write_atomic (WR-016).
        buf = io.BytesIO()
        writer = HashingAtomicWriter(buf, algorithm=algorithm)
        yield writer
        buf.seek(0)
        result = store.write_atomic(path, buf.read(), overwrite=overwrite, metadata=metadata)
        writer.result = dataclasses.replace(result, digest=ContentDigest(algorithm=algorithm, value=writer.hexdigest()))
    else:
        with store.open_atomic(path, overwrite=overwrite) as f:
            writer = HashingAtomicWriter(f, algorithm=algorithm)
            yield writer
        result = store.head(path)
        writer.result = dataclasses.replace(result, digest=ContentDigest(algorithm=algorithm, value=writer.hexdigest()))
