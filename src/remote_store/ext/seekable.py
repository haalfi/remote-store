"""Seekable read — portable seekable stream for any backend.

Delegates to ``Store.read()`` and returns the stream as-is when it is
already seekable.  For non-seekable backends (Azure, HTTP) the stream
is spooled into a ``SpooledTemporaryFile``: content up to *max_memory*
stays in RAM, beyond that spills to a temporary file on disk.

Usage:

```python
from remote_store.ext.seekable import seekable_read

with seekable_read(store, "report.csv") as f:
    header = f.read(128)
    f.seek(0)  # guaranteed to work on any backend
    full = f.read()
```
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import warnings
from typing import TYPE_CHECKING

from remote_store._capabilities import Capability

if TYPE_CHECKING:
    from typing import BinaryIO

    from remote_store._store import Store

__all__ = ["seekable_read"]

log = logging.getLogger(__name__)


class _SeekableSpool(tempfile.SpooledTemporaryFile):  # type: ignore[type-arg]
    """SpooledTemporaryFile subclass that exposes ``seekable()``.

    ``SpooledTemporaryFile`` gained ``seekable()`` in Python 3.11.
    This subclass adds it for Python 3.10 compatibility.
    """

    def seekable(self) -> bool:
        return True


def seekable_read(
    store: Store,
    path: str,
    *,
    max_memory: int = 8 * 1024 * 1024,
) -> BinaryIO:
    """Return a seekable stream for *path*.

    If the stream returned by ``store.read()`` is already seekable,
    returns it directly — zero overhead.  Otherwise, spools the stream
    into a ``SpooledTemporaryFile``: content up to *max_memory* bytes
    stays in RAM, beyond that spills to a temporary file on disk.
    The returned stream is always seekable and positioned at byte 0.

    Args:
        store: The Store to read from.
        path: Store-relative file path.
        max_memory: Maximum bytes to keep in RAM before spilling to
            disk.  Defaults to 8 MB (matching atomic-write default).

    Returns:
        A seekable ``BinaryIO`` stream.  The caller owns the stream
        and must close it.
    """
    stream = store.read(path)

    if stream.seekable():
        return stream

    if store.supports(Capability.SEEKABLE_READ):
        warnings.warn(
            "Backend declares SEEKABLE_READ but stream.seekable() is False; falling back to SpooledTemporaryFile",
            stacklevel=2,
        )

    spool: BinaryIO = _SeekableSpool(max_size=max_memory)  # type: ignore[assignment]
    try:
        shutil.copyfileobj(stream, spool)
    except BaseException:
        spool.close()
        raise
    finally:
        stream.close()

    spool.seek(0)
    return spool
