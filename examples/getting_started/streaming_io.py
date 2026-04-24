"""Streaming I/O — Streaming writes and reads with `BytesIO`.

Demonstrates streaming-first I/O patterns with remote-store.
"""

from __future__ import annotations

import io
import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile


def demo(store):
    """Streaming write, line-by-line read, and chunked read."""
    # --- Write from a BytesIO stream ---
    data = b"line1\nline2\nline3\nline4\nline5\n"
    stream = io.BytesIO(data)
    result = store.write("streamed.txt", stream)
    print(f"Wrote {result.size} bytes from BytesIO stream.")

    # --- Read as a stream ---
    with store.read("streamed.txt") as reader:
        print(f"\nStreaming read (type: {type(reader).__name__}):")
        newline = b"\n"
        for line in reader:
            print(f"  {line.rstrip(newline)}")

    # --- Chunked processing ---
    large_data = b"X" * 10_000
    result = store.write("large.bin", large_data)

    with store.read("large.bin") as reader:
        total = 0
        chunk_count = 0
        while True:
            chunk = reader.read(4096)
            if not chunk:
                break
            total += len(chunk)
            chunk_count += 1
    print(f"\nRead large.bin in {chunk_count} chunk(s), {total}/{result.size} bytes total.")

    # --- Write bytes directly ---
    result = store.write("direct.txt", b"Written as raw bytes")
    print(f"\nDirect write ({result.size} bytes): {store.read_bytes('direct.txt').decode()}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")
            demo(store)

    print("\nDone!")
