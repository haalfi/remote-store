"""Async write helpers with client-side content hashing.

Guarantees a populated ``WriteResult.digest`` regardless of whether the
backend declares ``WRITE_RESULT_NATIVE``. The hash is always computed
client-side over the bytes as they flow to the backend.

Spec: EW-001..EW-004 in ``sdd/specs/046-ext-write.md``.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from remote_store import WriteResult
    from remote_store.aio import AsyncStore


async def write_with_hash(
    store: AsyncStore,
    path: str,
    content: bytes | AsyncIterator[bytes],
    *,
    algorithm: str = "sha256",
    overwrite: bool = False,
    metadata: Mapping[str, str] | None = None,
) -> WriteResult:
    """Write *content* and return a ``WriteResult`` with ``digest`` populated.

    Hash is computed client-side as data flows to the backend -- zero extra
    round trips, no buffering for async-iterator input.  ``source`` is
    preserved from the underlying ``store.write()`` result.

    Args:
        store: Target async store.
        path: Destination path.
        content: ``bytes`` or ``AsyncIterator[bytes]``.
        algorithm: ``hashlib`` algorithm name.  Default ``"sha256"``.
        overwrite: Same semantics as ``AsyncStore.write``.
        metadata: Optional user metadata; subject to ``USER_METADATA`` gate.

    Returns:
        ``WriteResult`` with ``digest`` populated from the client-side hash.
    """
    from remote_store import ContentDigest

    h = hashlib.new(algorithm)

    if isinstance(content, bytes):
        h.update(content)
        result = await store.write(path, content, overwrite=overwrite, metadata=metadata)
    else:

        async def _hashing_iter(src: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
            async for chunk in src:
                h.update(chunk)
                yield chunk

        result = await store.write(path, _hashing_iter(content), overwrite=overwrite, metadata=metadata)

    return dataclasses.replace(result, digest=ContentDigest(algorithm, h.hexdigest()))
