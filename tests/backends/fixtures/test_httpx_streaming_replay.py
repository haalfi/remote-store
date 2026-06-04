"""Proof that vcrpy records and replays ``httpx.AsyncClient.stream()`` (ID-127).

RFC-0010 flags httpx streaming-replay as an *unproven* path: the Azure
async replay fixture (``azure_replay_async.py``) had to swap in an
``azure.core`` transport because vcrpy's aiohttp stub deadlocks on a
streamed body, and whether vcrpy can capture/replay a bare
``httpx.AsyncClient.stream()`` was open. The Graph backend (ID-127)
downloads file content over exactly that path (GR-012 / GR-015), so the
mechanism has to be proven before those ops depend on it.

This test records a streamed GET against a throwaway loopback server into
a temp cassette, **shuts the server down**, then replays from the cassette
and asserts the chunked round-trip. It passing means the Graph backend's
streaming downloads can be replayed at Stage-1 with **plain vcrpy** — no
transport shim like the Azure async fixture needed.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import httpx
import pytest
import vcr

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# 64 KiB of non-text bytes: large enough that aiter_bytes yields many
# chunks, binary enough to catch any UTF-8-decode assumption in the path.
_PAYLOAD = bytes(range(256)) * 256


class _StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(_PAYLOAD)))
        self.end_headers()
        for i in range(0, len(_PAYLOAD), 4096):
            self.wfile.write(_PAYLOAD[i : i + 4096])

    def log_message(self, *args: object) -> None:  # silence the default stderr log
        pass


@pytest.fixture
def loopback_server() -> Iterator[ThreadingHTTPServer]:
    """A 127.0.0.1 HTTP server streaming ``_PAYLOAD`` on any GET.

    Bound to 127.0.0.1 (not 0.0.0.0): the wildcard host is unconnectable on
    Windows. The caller shuts it down mid-test to prove offline replay.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


async def _stream_chunks(url: str) -> tuple[bytes, int]:
    """GET ``url`` as a stream; return (reassembled body, chunk count)."""
    chunks: list[bytes] = []
    async with httpx.AsyncClient() as client, client.stream("GET", url) as resp:
        async for chunk in resp.aiter_bytes(chunk_size=1024):
            chunks.append(chunk)
    return b"".join(chunks), len(chunks)


@pytest.mark.spec("TEST-007")
def test_httpx_stream_records_then_replays_offline(
    loopback_server: ThreadingHTTPServer,
    tmp_path: Path,
) -> None:
    """Record a streamed GET, kill the server, replay from the cassette.

    Proves vcrpy captures and replays an ``httpx.AsyncClient.stream()``
    chunked body with no transport shim — the GR-012 / GR-015 prerequisite.
    """
    url = f"http://127.0.0.1:{loopback_server.server_address[1]}/file"
    cassette = tmp_path / "stream.yaml"

    # Record: vcrpy passes through to the loopback server and writes the cassette.
    with vcr.use_cassette(str(cassette), record_mode="once"):
        recorded, recorded_chunks = asyncio.run(_stream_chunks(url))
    assert recorded == _PAYLOAD
    assert recorded_chunks > 1  # the body really was delivered in chunks
    assert cassette.exists()

    # Kill the server so a replay that hit the network would fail loudly.
    loopback_server.shutdown()
    loopback_server.server_close()

    # Replay: served entirely from the cassette, no network.
    with vcr.use_cassette(str(cassette), record_mode="none"):
        replayed, replayed_chunks = asyncio.run(_stream_chunks(url))
    assert replayed == _PAYLOAD
    assert replayed_chunks > 1
