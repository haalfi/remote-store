"""Two tests that probe whether vcrpy can record + replay s3fs traffic.

Run order is independent: each test seeds and reads its own key.

Decision gate (see README.md):

* Both tests record cleanly with a non-empty body in the cassette **and**
  replay cleanly with bytes matching what was written → vcrpy works for
  s3fs; proceed to PR 2 production wiring.
* Either test drops the body on record, deadlocks on replay, or returns
  mismatched bytes → vcrpy's aiohttp stub bites s3fs; PR 2 shrinks to an
  infeasibility doc + new BK item.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from remote_store._backend import Backend


SMALL_PAYLOAD = b"hello s3 cassette spike\n"

# 1 MiB. Below s3fs's default 5 MiB single-part PUT threshold (so the
# spike does not exercise multipart upload), but well above any single
# TCP frame and the aiohttp default chunk size — large enough that any
# streaming-body bug in vcrpy's aiohttp stub will surface.
LARGE_PAYLOAD = b"x" * (1 << 20)


@pytest.mark.vcr
def test_spike_s3_write_read_small(s3_backend: Backend) -> None:
    """Tiny round trip — catches catastrophic body-drop on the non-streaming path."""
    key = "spike/small.bin"
    s3_backend.write(key, SMALL_PAYLOAD, overwrite=True)
    got = s3_backend.read_bytes(key)
    assert got == SMALL_PAYLOAD


@pytest.mark.vcr
def test_spike_s3_read_streaming(s3_backend: Backend) -> None:
    """1 MiB streaming read — catches body-drop / deadlock on the streaming path.

    Uses ``S3Backend.read()`` which returns a ``BinaryIO`` backed by an
    ``s3fs`` file object. Reading it in chunks exercises the same
    aiobotocore → aiohttp streaming code path that broke for Azure's
    ``AioHttpTransport.__anext__`` in vcrpy 8.1.1.
    """
    key = "spike/large.bin"
    s3_backend.write(key, LARGE_PAYLOAD, overwrite=True)
    chunks: list[bytes] = []
    with s3_backend.read(key) as stream:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    got = b"".join(chunks)
    assert got == LARGE_PAYLOAD
