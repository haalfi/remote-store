"""Tests for aio.ext.write.write_with_hash -- async sibling of ext.write."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from remote_store import CapabilityNotSupported
from remote_store._models import WriteResult
from remote_store.aio._async_memory import AsyncMemoryBackend
from remote_store.aio._async_store import AsyncStore
from remote_store.aio.ext.write import write_with_hash


@pytest.fixture
def store() -> AsyncStore:
    return AsyncStore(AsyncMemoryBackend())


class TestWriteWithHash:
    """write_with_hash computes a content digest alongside the write."""

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_bytes(self, store: AsyncStore) -> None:
        content = b"hello world"
        result = await write_with_hash(store, "f.txt", content)
        assert isinstance(result, WriteResult)
        assert result.digest is not None
        assert result.digest.algorithm == "sha256"
        assert result.digest.value == hashlib.sha256(content).hexdigest()

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_async_iter(self, store: AsyncStore) -> None:
        chunks = [b"hello ", b"world"]

        async def _gen():
            for chunk in chunks:
                yield chunk

        result = await write_with_hash(store, "f.txt", _gen())
        assert result.digest is not None
        assert result.digest.algorithm == "sha256"
        assert result.digest.value == hashlib.sha256(b"hello world").hexdigest()

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_source_is_native_on_memory(self, store: AsyncStore) -> None:
        result = await write_with_hash(store, "f.txt", b"data")
        assert result.source == "native"

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_preserves_basic_source(self) -> None:
        class _BasicSourceBackend(AsyncMemoryBackend):
            async def write(self, path, content, *, overwrite=False, metadata=None):
                result = await super().write(path, content, overwrite=overwrite, metadata=metadata)
                return dataclasses.replace(result, source="basic")

        store = AsyncStore(_BasicSourceBackend())
        result = await write_with_hash(store, "f.txt", b"data")
        assert result.source == "basic"

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_custom_algorithm(self, store: AsyncStore) -> None:
        content = b"test"
        result = await write_with_hash(store, "f.txt", content, algorithm="sha512")
        assert result.digest is not None
        assert result.digest.algorithm == "sha512"
        assert result.digest.value == hashlib.sha512(content).hexdigest()

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_metadata_forwarded(self, store: AsyncStore) -> None:
        result = await write_with_hash(store, "f.txt", b"data", metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_no_user_metadata_raises(self) -> None:
        from remote_store import Capability
        from tests.aio.conftest import RestrictedAsyncBackend

        backend = RestrictedAsyncBackend(AsyncMemoryBackend(), exclude={Capability.USER_METADATA})
        restricted_store = AsyncStore(backend, root_path="data")
        with pytest.raises(CapabilityNotSupported, match="user_metadata"):
            await write_with_hash(restricted_store, "f.txt", b"x", metadata={"k": "v"})

    @pytest.mark.spec("EW-001")
    async def test_write_with_hash_bad_algorithm_raises(self, store: AsyncStore) -> None:
        with pytest.raises(ValueError, match="nonesuch"):
            await write_with_hash(store, "f.txt", b"x", algorithm="nonesuch")
