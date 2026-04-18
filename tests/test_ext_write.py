"""Tests for ext.write — write_with_hash and open_atomic_with_hash.

Spec refs: EW-001..EW-004 (sdd/specs/046-ext-write.md).
"""

from __future__ import annotations

import hashlib
import io

import pytest

from remote_store._models import ContentDigest, WriteResult
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend


@pytest.fixture
def store() -> Store:
    return Store(backend=MemoryBackend(), root_path="data")


class TestWriteWithHash:
    """EW-001, EW-002: write_with_hash computes client-side digest."""

    @pytest.mark.spec("EW-001")
    def test_returns_write_result_with_digest(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        result = write_with_hash(store, "f.bin", b"hello")
        assert isinstance(result, WriteResult)
        assert isinstance(result.digest, ContentDigest)
        assert result.size == 5

    @pytest.mark.spec("EW-001")
    def test_digest_algorithm_default_sha256(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        result = write_with_hash(store, "f.bin", b"hello")
        assert result.digest is not None
        assert result.digest.algorithm == "sha256"

    @pytest.mark.spec("EW-001")
    def test_digest_value_correct(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        content = b"test content for hashing"
        expected = hashlib.sha256(content).hexdigest()
        result = write_with_hash(store, "f.bin", content)
        assert result.digest is not None
        assert result.digest.value == expected

    @pytest.mark.spec("EW-001")
    def test_custom_algorithm(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        content = b"abc"
        expected = hashlib.md5(content).hexdigest()  # noqa: S324
        result = write_with_hash(store, "f.bin", content, algorithm="md5")
        assert result.digest is not None
        assert result.digest.algorithm == "md5"
        assert result.digest.value == expected

    @pytest.mark.spec("EW-001")
    def test_content_written_to_store(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        write_with_hash(store, "f.bin", b"stored")
        assert store.read_bytes("f.bin") == b"stored"

    @pytest.mark.spec("EW-001")
    def test_works_with_binary_io_content(self, store: Store) -> None:
        from remote_store.ext.write import write_with_hash

        content = b"stream content"
        stream = io.BytesIO(content)
        result = write_with_hash(store, "f.bin", stream)
        expected = hashlib.sha256(content).hexdigest()
        assert result.digest is not None
        assert result.digest.value == expected
        assert store.read_bytes("f.bin") == content

    @pytest.mark.spec("EW-001")
    def test_source_passthrough(self) -> None:
        """EW-001: source from the inner write is preserved, digest is added."""
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import Capability, CapabilitySet
        from remote_store._path import RemotePath
        from remote_store.ext.write import write_with_hash

        mock_backend = MagicMock(spec=Backend)
        mock_backend.name = "mock"
        mock_backend.capabilities = CapabilitySet({Capability.WRITE, Capability.READ, Capability.METADATA})
        mock_backend.write.return_value = WriteResult(
            path=RemotePath("data/f.bin"),
            size=5,
            source="basic",
            digest=None,
        )
        s = Store(backend=mock_backend)
        result = write_with_hash(s, "f.bin", b"basic")
        assert result.source == "basic"
        assert result.digest is not None

    @pytest.mark.spec("EW-002")
    def test_works_on_basic_write_backend(self) -> None:
        """EW-002: only Capability.WRITE is required; digest is always added."""
        from unittest.mock import MagicMock

        from remote_store._backend import Backend
        from remote_store._capabilities import Capability, CapabilitySet
        from remote_store._path import RemotePath
        from remote_store.ext.write import write_with_hash

        mock_backend = MagicMock(spec=Backend)
        mock_backend.name = "mock"
        mock_backend.capabilities = CapabilitySet({Capability.WRITE, Capability.READ, Capability.METADATA})
        mock_backend.write.return_value = WriteResult(
            path=RemotePath("data/f.bin"),
            size=5,
            source="basic",
            digest=None,
        )
        s = Store(backend=mock_backend)
        result = write_with_hash(s, "f.bin", b"basic")
        assert result.digest is not None
        assert result.source == "basic"


class TestOpenAtomicWithHash:
    """EW-003, EW-004: open_atomic_with_hash context manager."""

    @pytest.mark.spec("EW-003")
    def test_yields_hashing_atomic_writer(self, store: Store) -> None:
        from remote_store.ext.write import HashingAtomicWriter, open_atomic_with_hash

        with open_atomic_with_hash(store, "f.bin") as writer:
            assert isinstance(writer, HashingAtomicWriter)
            writer.write(b"data")

        assert store.read_bytes("f.bin") == b"data"

    @pytest.mark.spec("EW-004")
    def test_result_populated_after_exit(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        with open_atomic_with_hash(store, "f.bin") as writer:
            writer.write(b"hello world")

        assert isinstance(writer.result, WriteResult)
        assert writer.result.digest is not None

    @pytest.mark.spec("EW-004")
    def test_result_size_matches_bytes_written(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        with open_atomic_with_hash(store, "f.bin") as writer:
            writer.write(b"twelve bytes")

        assert writer.result is not None
        assert writer.result.size == 12

    @pytest.mark.spec("EW-004")
    def test_result_digest_correct(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        content = b"integrity check"
        expected = hashlib.sha256(content).hexdigest()
        with open_atomic_with_hash(store, "f.bin") as writer:
            writer.write(content)

        assert writer.result is not None
        assert writer.result.digest is not None
        assert writer.result.digest.value == expected

    @pytest.mark.spec("EW-004")
    def test_result_none_on_exception(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        captured: list[object] = []

        def _run() -> None:
            with open_atomic_with_hash(store, "f.bin") as writer:
                captured.append(writer)
                writer.write(b"partial")
                raise RuntimeError("abort")

        with pytest.raises(RuntimeError, match="abort"):
            _run()

        assert captured
        assert getattr(captured[0], "result", None) is None

    @pytest.mark.spec("EW-003")
    def test_raises_without_atomic_write_capability(self) -> None:
        from unittest.mock import patch

        from remote_store._capabilities import Capability, CapabilitySet
        from remote_store._errors import CapabilityNotSupported
        from remote_store.ext.write import open_atomic_with_hash

        backend = MemoryBackend()
        caps = CapabilitySet({Capability.READ, Capability.WRITE, Capability.METADATA, Capability.LIST})
        with patch.object(type(backend), "capabilities", new_callable=lambda: property(lambda _: caps)):
            s = Store(backend=backend, root_path="data")

            def _run() -> None:
                with open_atomic_with_hash(s, "f.bin") as w:
                    w.write(b"x")

            with pytest.raises(CapabilityNotSupported, match="atomic_write"):
                _run()

    @pytest.mark.spec("EW-003")
    def test_content_written_to_store(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        with open_atomic_with_hash(store, "f.bin") as writer:
            writer.write(b"committed")

        assert store.read_bytes("f.bin") == b"committed"

    @pytest.mark.spec("EW-003")
    def test_metadata_branch_writes_and_sets_digest(self, store: Store) -> None:
        """Metadata path buffers to BytesIO then calls write_atomic."""
        from remote_store.ext.write import open_atomic_with_hash

        content = b"meta content"
        expected = hashlib.sha256(content).hexdigest()
        with open_atomic_with_hash(store, "f.bin", metadata={"k": "v"}) as writer:
            writer.write(content)

        assert writer.result is not None
        assert writer.result.digest is not None
        assert writer.result.digest.value == expected
        assert store.read_bytes("f.bin") == content

    @pytest.mark.spec("EW-004")
    def test_metadata_branch_result_none_on_exception(self, store: Store) -> None:
        from remote_store.ext.write import open_atomic_with_hash

        captured: list[object] = []

        def _run() -> None:
            with open_atomic_with_hash(store, "f.bin", metadata={"k": "v"}) as writer:
                captured.append(writer)
                writer.write(b"partial")
                raise RuntimeError("abort")

        with pytest.raises(RuntimeError, match="abort"):
            _run()

        assert captured
        assert getattr(captured[0], "result", None) is None
