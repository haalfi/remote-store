"""Observe hooks -- callback-based instrumentation for Store operations.

Demonstrates:
- observe(): wrapping a Store with callbacks
- on_write / on_read / on_any: per-operation and catch-all hooks
- StoreEvent: inspecting operation details
- around: context-manager hook for before/after instrumentation
- BufferedObserver: batched async event delivery
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from remote_store import (
    BackendConfig,
    BufferedObserver,
    Registry,
    RegistryConfig,
    StoreEvent,
    StoreProfile,
    observe,
)

if __name__ == "__main__":
    config = RegistryConfig(
        backends={"mem": BackendConfig(type="memory", options={})},
        stores={"data": StoreProfile(backend="mem", root_path="data")},
    )

    with Registry(config) as registry:
        store = registry.get_store("data")

        # --- Basic hooks ---
        print("=== Per-operation hooks ===")

        def on_write(event: StoreEvent) -> None:
            print(f"  [on_write] {event.operation} {event.path} ({event.duration_ms:.2f}ms)")

        def on_read(event: StoreEvent) -> None:
            print(f"  [on_read] {event.operation} {event.path} ({event.duration_ms:.2f}ms)")

        observed = observe(store, on_write=on_write, on_read=on_read)

        observed.write("hello.txt", b"Hello, world!")
        observed.write("data.csv", b"a,b,c\n1,2,3", overwrite=False)
        _ = observed.read_bytes("hello.txt")
        print()

        # --- Catch-all hook ---
        print("=== Catch-all (on_any) ===")

        def on_any(event: StoreEvent) -> None:
            status = "OK" if event.error is None else f"ERR: {event.error}"
            print(f"  [{event.operation}] path={event.path!r} {status} ({event.duration_ms:.2f}ms)")

        observed = observe(store, on_any=on_any)
        observed.exists("hello.txt")
        observed.copy("hello.txt", "hello_copy.txt")
        observed.delete("hello_copy.txt")
        print()

        # --- Around hook ---
        print("=== Around hook (before/after) ===")

        @contextlib.contextmanager
        def trace(op: str, path: str, backend: str) -> Iterator[None]:
            print(f"  >> BEFORE {op}({path!r}) on {backend}")
            yield
            print(f"  << AFTER  {op}({path!r}) on {backend}")

        observed = observe(store, around=trace)
        observed.is_file("hello.txt")
        print()

        # --- BufferedObserver ---
        print("=== BufferedObserver ===")
        batches_received: list[list[StoreEvent]] = []

        def handle_batch(events: list[StoreEvent]) -> None:
            batches_received.append(events)
            print(f"  Flushed batch of {len(events)} events:")
            for e in events:
                print(f"    - {e.operation} {e.path}")

        observer = BufferedObserver(handle_batch, flush_interval=60.0)
        observed = observe(store, on_any=observer.on_event)

        observed.write("batch1.txt", b"one", overwrite=True)
        observed.write("batch2.txt", b"two", overwrite=True)
        observed.exists("batch1.txt")

        observer.flush()  # manual flush
        observer.close()  # final flush + stop thread

    print("\nDone!")
