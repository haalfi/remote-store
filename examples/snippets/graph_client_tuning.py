"""Graph httpx connection-pool tuning snippet — sourced by the Graph backend guide.

The named region is included into ``docs-src/guides/backends/graph.md`` via
pymdownx.snippets ``--8<--`` syntax. Running it (``hatch run examples``) proves
the documented call shape — passing an ``httpx.Limits`` through
``client_options`` — actually constructs a working client, without performing
any network I/O.

``GraphBackend`` builds its internal ``httpx.AsyncClient`` lazily from
``client_options`` (spec GR-052), so triggering the lazy build via ``unwrap``
exercises the passthrough end to end. The default pool ceiling is httpx's silent
100 connections; raising it here is how a caller lifts the cap so very high
fan-out does not surface as an opaque ``BackendUnavailable``.
"""

from __future__ import annotations

import asyncio

import httpx

from remote_store.aio import GraphBackend


async def _demo() -> None:
    # --8<-- [start:pool-limits]
    backend = GraphBackend(
        drive_id="b!example-drive-id",
        token_provider=lambda: "token",
        client_options={
            "limits": httpx.Limits(
                max_connections=200,
                max_keepalive_connections=50,
            ),
        },
    )
    # --8<-- [end:pool-limits]
    try:
        # Triggers the lazy httpx.AsyncClient build from client_options — proving
        # the limits kwarg is accepted and wired through (no network I/O).
        client = backend.unwrap(httpx.AsyncClient)
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
    finally:
        await backend.aclose()


def demo() -> None:
    """Execute the Graph connection-pool tuning snippet."""
    asyncio.run(_demo())


if __name__ == "__main__":
    demo()
