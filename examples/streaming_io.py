"""Streaming I/O — write from BytesIO, read as stream, chunked processing.

Demonstrates streaming-first I/O patterns with remote-store.
"""

from __future__ import annotations

import io
import tempfile

from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        config = RegistryConfig(
            backends={"local": BackendConfig(type="local", options={"root": tmp})},
            stores={"files": StoreProfile(backend="local")},
        )

        with Registry(config) as registry:
            store = registry.get_store("files")

            # --- Write from a BytesIO stream ---
            data = b"line1\nline2\nline3\nline4\nline5\n"
            stream = io.BytesIO(data)
            store.write("streamed.txt", stream)
            print("Wrote file from BytesIO stream.")

            # --- Read as a stream ---
            reader = store.read("streamed.txt")
            print(f"\nStreaming read (type: {type(reader).__name__}):")
            newline = b"\n"
            for line in reader:
                print(f"  {line.rstrip(newline)}")

            # --- Chunked processing ---
            # Write a larger file
            large_data = b"X" * 10_000
            store.write("large.bin", large_data)

            reader = store.read("large.bin")
            total = 0
            chunk_count = 0
            while True:
                chunk = reader.read(4096)
                if not chunk:
                    break
                total += len(chunk)
                chunk_count += 1
            print(f"\nRead large.bin in {chunk_count} chunk(s), {total} bytes total.")

            # --- Write bytes directly ---
            store.write("direct.txt", b"Written as raw bytes")
            print(f"\nDirect write: {store.read_bytes('direct.txt').decode()}")

    print("\nDone!")
