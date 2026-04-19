"""End-to-end tests for ext.write helpers across real backends.

Verifies that ``write_with_hash`` and ``open_atomic_with_hash`` return a
``WriteResult`` with the correct ``digest`` when the underlying backend is
S3, Azure, SFTP, S3-PyArrow, SQLBlob, or Memory.

Spec: EW-001..EW-004 in ``sdd/specs/046-ext-write.md``.

Requires: ``docker compose -f benchmarks/infra/docker-compose.yml up -d``
Run with: ``pytest -m integration tests/e2e/test_ext_write_e2e.py -s``
"""

from __future__ import annotations

import hashlib
import io
import random
import uuid
from typing import TYPE_CHECKING

import pytest

from remote_store import Capability, CapabilityNotSupported
from remote_store.ext.streams import ChecksumReader
from remote_store.ext.write import open_atomic_with_hash, write_with_hash

if TYPE_CHECKING:
    from remote_store import Store

# ---------------------------------------------------------------------------
# Fixed payload — small enough to be fast, exercises the full write path.
# ---------------------------------------------------------------------------

_PAYLOAD_SIZE = 4096  # 4 KiB
_PAYLOAD: bytes = random.Random(42).randbytes(_PAYLOAD_SIZE)  # noqa: S311
_EXPECTED_SHA256: str = hashlib.sha256(_PAYLOAD).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DRAIN_CHUNK = 65536  # 64 KiB


def _verify_readback(store: Store, path: str, expected_sha256: str, label: str) -> str | None:
    """Read *path* back through ChecksumReader; return failure message or None."""
    raw = store.read(path)
    reader = ChecksumReader(raw, algorithm="sha256")
    try:
        while reader.read(_DRAIN_CHUNK):
            pass
        actual = reader.hexdigest()
    finally:
        reader.close()
    if actual != expected_sha256:
        return f"{label}: readback digest mismatch — got {actual[:16]}..., want {expected_sha256[:16]}..."
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("EW-001")
@pytest.mark.spec("EW-002")
class TestWriteWithHash:
    """``write_with_hash`` returns correct digest on every real backend."""

    def test_all_backends(self, store_chain: list[tuple[str, Store]]) -> None:
        """Write a known 4 KiB payload and assert digest + readback match pre-computed SHA-256.

        Two content variants per backend exercise both internal branches of ``write_with_hash``
        (EW-001): ``bytes`` uses the ``hashlib`` fast-path; ``BytesIO`` triggers the
        ``ChecksumReader`` streaming path (the incremental hash as the backend reads).
        EW-002: every backend declaring WRITE is exercised — no additional capability required.
        Readback via ``ChecksumReader`` closes the "correct digest, wrong bytes" gap.
        """
        failures: list[str] = []
        names = [name for name, _ in store_chain]
        docker_backends = {n for n in names} - {"memory", "sql-blob"}
        if not docker_backends:
            pytest.skip("no Docker backend reachable")
        print(f"\n  Backends: {', '.join(names)}")  # noqa: T201

        for name, store in store_chain:
            for variant_label, make_content in [
                ("bytes", lambda: _PAYLOAD),
                ("stream", lambda: io.BytesIO(_PAYLOAD)),
            ]:
                label = f"{name}[{variant_label}]"
                path = f"ext-write-e2e-{uuid.uuid4().hex[:8]}.bin"
                try:
                    result = write_with_hash(store, path, make_content())
                    if result.digest is None:
                        failures.append(f"{label}: digest is None")
                    elif result.digest.algorithm != "sha256":
                        failures.append(f"{label}: algorithm={result.digest.algorithm!r}, want 'sha256'")
                    elif result.digest.value != _EXPECTED_SHA256:
                        failures.append(
                            f"{label}: digest mismatch — got {result.digest.value[:16]}..., "
                            f"want {_EXPECTED_SHA256[:16]}..."
                        )
                    else:
                        err = _verify_readback(store, path, _EXPECTED_SHA256, label)
                        if err:
                            failures.append(err)
                        else:
                            print(f"  {label}: OK ({result.digest.value[:16]}...)")  # noqa: T201
                except (CapabilityNotSupported, OSError) as exc:
                    failures.append(f"{label}: unexpected exception — {exc!r}")
                finally:
                    try:
                        if store.exists(path):
                            store.delete(path)
                    except Exception:  # noqa: BLE001
                        pass

        assert not failures, "write_with_hash digest failures:\n" + "\n".join(f"  {f}" for f in failures)


@pytest.mark.integration
@pytest.mark.spec("EW-004")
class TestOpenAtomicWithHash:
    """``open_atomic_with_hash`` returns correct digest on every real backend."""

    def test_all_backends(self, store_chain: list[tuple[str, Store]]) -> None:
        """Stream-write a known 4 KiB payload in two chunks and assert digest + readback.

        Writing in two chunks (``_PAYLOAD[:2048]``, ``_PAYLOAD[2048:]``) exercises
        multi-update digest accumulation in ``HashingAtomicWriter`` — the more
        interesting failure mode for a checksum wrapper than a single write call.
        EW-004: ``writer.result`` is None before exit, populated after.
        Readback via ``ChecksumReader`` closes the "correct digest, wrong bytes" gap.
        """
        failures: list[str] = []
        names = [name for name, _ in store_chain]
        docker_backends = {n for n in names} - {"memory", "sql-blob"}
        if not docker_backends:
            pytest.skip("no Docker backend reachable")
        print(f"\n  Backends: {', '.join(names)}")  # noqa: T201

        for name, store in store_chain:
            if not store.supports(Capability.ATOMIC_WRITE):
                print(f"  {name}: skipped (no ATOMIC_WRITE)")  # noqa: T201
                continue

            path = f"ext-write-e2e-atomic-{uuid.uuid4().hex[:8]}.bin"
            try:
                with open_atomic_with_hash(store, path) as writer:
                    # EW-004: result must be None before the block exits.
                    if writer.result is not None:
                        failures.append(f"{name}: writer.result is not None before exit")
                    # Two chunks — exercises multi-update digest accumulation.
                    writer.write(_PAYLOAD[:2048])
                    writer.write(_PAYLOAD[2048:])

                # EW-004: result must be populated after successful exit.
                if writer.result is None:
                    failures.append(f"{name}: writer.result is None after exit")
                elif writer.result.digest is None:
                    failures.append(f"{name}: writer.result.digest is None")
                elif writer.result.digest.algorithm != "sha256":
                    failures.append(f"{name}: algorithm={writer.result.digest.algorithm!r}, want 'sha256'")
                elif writer.result.digest.value != _EXPECTED_SHA256:
                    failures.append(
                        f"{name}: digest mismatch — got {writer.result.digest.value[:16]}..., "
                        f"want {_EXPECTED_SHA256[:16]}..."
                    )
                else:
                    err = _verify_readback(store, path, _EXPECTED_SHA256, name)
                    if err:
                        failures.append(err)
                    else:
                        print(f"  {name}: OK ({writer.result.digest.value[:16]}...)")  # noqa: T201
            except (CapabilityNotSupported, OSError) as exc:
                failures.append(f"{name}: unexpected exception — {exc!r}")
            finally:
                try:
                    if store.exists(path):
                        store.delete(path)
                except Exception:  # noqa: BLE001
                    pass

        assert not failures, "open_atomic_with_hash digest failures:\n" + "\n".join(f"  {f}" for f in failures)

    def test_metadata_branch(self, store_chain: list[tuple[str, Store]]) -> None:
        """metadata= path of open_atomic_with_hash on backends declaring USER_METADATA.

        Exercises the buffering branch (EW-004): the payload is buffered in memory and
        ``store.write_atomic()`` is called on context-manager exit.  Digest must match
        whether or not metadata is present — the checksum wraps the payload, not the
        metadata.  Skipped when no backend with both ATOMIC_WRITE and USER_METADATA is
        reachable (Memory and SQLBlob always qualify).
        """
        failures: list[str] = []
        ran = False

        for name, store in store_chain:
            if not store.supports(Capability.ATOMIC_WRITE):
                continue
            if not store.supports(Capability.USER_METADATA):
                continue
            ran = True

            path = f"ext-write-e2e-meta-{uuid.uuid4().hex[:8]}.bin"
            try:
                with open_atomic_with_hash(store, path, metadata={"source": "e2e"}) as writer:
                    writer.write(_PAYLOAD)

                if writer.result is None:
                    failures.append(f"{name}: writer.result is None after exit")
                elif writer.result.digest is None:
                    failures.append(f"{name}: writer.result.digest is None")
                elif writer.result.digest.value != _EXPECTED_SHA256:
                    failures.append(
                        f"{name}: digest mismatch — got {writer.result.digest.value[:16]}..., "
                        f"want {_EXPECTED_SHA256[:16]}..."
                    )
                else:
                    err = _verify_readback(store, path, _EXPECTED_SHA256, name)
                    if err:
                        failures.append(err)
                    else:
                        print(f"  {name}[metadata]: OK ({writer.result.digest.value[:16]}...)")  # noqa: T201
            except (CapabilityNotSupported, OSError) as exc:
                failures.append(f"{name}: unexpected exception — {exc!r}")
            finally:
                try:
                    if store.exists(path):
                        store.delete(path)
                except Exception:  # noqa: BLE001
                    pass

        if not ran:
            pytest.skip("no backend with ATOMIC_WRITE + USER_METADATA reachable")
        assert not failures, "open_atomic_with_hash[metadata] failures:\n" + "\n".join(f"  {f}" for f in failures)
