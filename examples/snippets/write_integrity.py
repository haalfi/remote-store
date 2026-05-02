"""Write-integrity snippets — sourced by docs-src/guides/write-integrity.md.

Named regions are included via pymdownx.snippets ``--8<--`` syntax.
Run directly or via ``hatch run examples`` to verify snippets.
"""

from __future__ import annotations

from remote_store import Store
from remote_store.backends import MemoryBackend


def demo() -> None:
    """Execute all write-integrity snippets."""
    _write_with_hash()
    _open_atomic_with_hash()
    _head_after_write()


def _write_with_hash() -> None:
    # --8<-- [start:write-with-hash]
    from remote_store.ext.write import write_with_hash

    store = Store(MemoryBackend())
    result = write_with_hash(store, "report.csv", b"col1,col2\n1,2\n")

    print(result.digest.algorithm)  # sha256
    print(result.digest.value)  # hex digest
    # --8<-- [end:write-with-hash]
    assert result.digest is not None
    assert result.digest.algorithm == "sha256"
    assert len(result.digest.value) == 64


def _open_atomic_with_hash() -> None:
    # --8<-- [start:open-atomic-with-hash]
    from remote_store.ext.write import open_atomic_with_hash

    store = Store(MemoryBackend())
    with open_atomic_with_hash(store, "data.bin") as writer:
        writer.write(b"chunk one ")
        writer.write(b"chunk two")

    result = writer.result
    print(result.digest.value)  # sha256 of "chunk one chunk two"
    # --8<-- [end:open-atomic-with-hash]
    assert result is not None
    assert result.digest is not None
    assert result.size == len(b"chunk one chunk two")


def _head_after_write() -> None:
    # --8<-- [start:head-after-write]
    from remote_store.ext.write import write_with_hash

    store = Store(MemoryBackend())
    write_result = write_with_hash(store, "archive.bin", b"payload")

    head = store.head("archive.bin")
    print(head.size)  # 7
    print(head.source)  # "sidecar"

    # Compare digests if the backend echoed one back natively:
    if write_result.digest and head.digest:
        assert write_result.digest.value == head.digest.value
    # --8<-- [end:head-after-write]
    assert head.size == 7


if __name__ == "__main__":
    demo()
