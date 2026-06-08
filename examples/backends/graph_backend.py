"""Graph backend — Microsoft Graph over OneDrive / SharePoint / Teams files.

Demonstrates:
- Authenticating with ``GraphAuth`` (device-code or client-credentials)
- Resolving a ``drive_id`` with ``GraphUtils.resolve_drive_id``
- Driving the async-only ``GraphBackend`` through ``AsyncStore``
- File operations: write, read, list, copy, move, delete
- Streaming read (forward-only async iterator)
- Escape hatch: ``unwrap()`` to reach the underlying ``httpx.AsyncClient``

The Graph backend is **async-only** — there is no sync ``Store`` wrapper, so
this example is an ``asyncio`` program.

Prerequisites:
- pip install "remote-store[graph]"
- An Entra app registration (see the Graph setup guide) and a target drive

Environment variables:
    GRAPH_TENANT_ID      Entra tenant id, or "consumers" for device-code (required)
    GRAPH_CLIENT_ID      Application (client) id (required)
    GRAPH_CLIENT_SECRET  Client secret -> selects client-credentials (optional;
                         omit for interactive device-code auth)
    GRAPH_DRIVE_ID       Target drive id (optional; resolves "me" when unset)

---
see_also:
  - label: Graph Backend
    url: ../../guides/backends/graph.md
    note: backend guide
  - label: Microsoft Graph Access Setup
    url: ../../guides/backends/graph-setup.md
    note: app registration + auth
"""

from __future__ import annotations

import asyncio
import os
import sys

from remote_store.aio import AsyncStore, GraphAuth, GraphBackend, GraphUtils

TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "")
CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")

if not TENANT_ID or not CLIENT_ID:
    print(
        "Set GRAPH_TENANT_ID and GRAPH_CLIENT_ID to run this example.\n"
        'Device-code auth (personal OneDrive): GRAPH_TENANT_ID="consumers"\n'
        "App-only auth (work/school tenant): also set GRAPH_CLIENT_SECRET\n"
        "Optional: GRAPH_DRIVE_ID to target a specific drive (else resolves 'me').\n\n"
        "See the Graph setup guide for app registration:\n"
        "  docs-src/guides/backends/graph-setup.md"
    )
    sys.exit(1)


async def main() -> None:
    # --- Token provider: a client_secret selects client-credentials (app-only);
    #     its absence selects interactive device-code. ---
    auth = GraphAuth(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=os.environ.get("GRAPH_CLIENT_SECRET") or None,
    )

    # --- Resolve the target drive. Use GRAPH_DRIVE_ID when supplied, otherwise
    #     resolve the signed-in user's OneDrive ("me"). ---
    drive_id = os.environ.get("GRAPH_DRIVE_ID")
    if not drive_id:
        drive_id = await GraphUtils.aresolve_drive_id("me", token_provider=auth)
    print(f"Target drive: {drive_id}")

    backend = GraphBackend(drive_id, token_provider=auth)
    async with AsyncStore(backend, root_path="remote-store-example") as store:
        # --- Write ---
        await store.write("report.csv", b"revenue,profit\n100,20\n200,40\n", overwrite=True)
        await store.write("notes/todo.txt", b"Ship v1.0", overwrite=True)
        print("Wrote 2 files.")

        # --- Read ---
        content = await store.read_bytes("report.csv")
        print(f"\nreport.csv:\n{content.decode()}")

        # --- Metadata ---
        info = await store.get_file_info("report.csv")
        print(f"report.csv  size={info.size}  modified={info.modified_at}")

        # --- List files (recursive) ---
        print("\nlisting (recursive):")
        async for entry in store.list_files("", recursive=True):
            print(f"  {entry.path}  ({entry.size} bytes)")

        # --- Copy (server-side; async monitor poll on large items) ---
        await store.copy("report.csv", "report_backup.csv", overwrite=True)
        print(f"\nCopied report.csv -> report_backup.csv (exists: {await store.exists('report_backup.csv')})")

        # --- Move ---
        await store.move("report_backup.csv", "archive_report.csv", overwrite=True)
        print(f"Moved to archive_report.csv (original exists: {await store.exists('report_backup.csv')})")

        # --- Streaming read (forward-only async iterator) ---
        print("\nStreaming read (line by line):")
        buffer = b""
        async for chunk in store.read("report.csv"):
            buffer += chunk
        for line in buffer.decode().splitlines():
            if line:
                print(f"  {line}")

        # --- Escape hatch: the underlying httpx.AsyncClient ---
        import httpx

        client = backend.unwrap(httpx.AsyncClient)
        print(f"\nUnderlying client: {type(client).__name__}")

        # --- Cleanup ---
        async for entry in store.list_files("", recursive=True):
            await store.delete(str(entry.path))
        print("\nCleaned up all example files.")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
