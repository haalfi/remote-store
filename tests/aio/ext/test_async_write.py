"""Tests for aio.ext.write.write_with_hash -- async sibling of ext.write."""

from __future__ import annotations

import hashlib

import pytest

from remote_store._models import WriteResult
from remote_store.aio._async_memory import AsyncMemoryBackend
from remote_store.aio._async_store import AsyncStore
from remote_store.aio.ext.write import write_with_hash


@pytest.fixture
def store() -> AsyncStore:
    return AsyncStore(AsyncMemoryBackend())


class TestWriteWithHash:
    """write_with_hash computes a content digest alongside the write."""

    @pytest.mark.spec("WR-006")
    async def test_write_with_hash_bytes(self, store: AsyncStore) -> None:
        content = b"hello world"
        result = await write_with_hash(store, "f.txt", content)
        assert isinstance(result, WriteResult)
        assert result.digest is not None
        assert result.digest.algorithm == "sha256"
        assert result.digest.value == hashlib.sha256(content).hexdigest()

    @pytest.mark.spec("WR-006")
    async def test_write_with_hash_async_iter(self, store: AsyncStore) -> None:
        chunks = [b"hello ", b"world"]

        async def _gen():
            for chunk in chunks:
                yield chunk

        result = await write_with_hash(store, "f.txt", _gen())
        assert result.digest is not None
        assert result.digest.algorithm == "sha256"
        assert result.digest.value == hashlib.sha256(b"hello world").hexdigest()

    @pytest.mark.spec("WR-004")
    async def test_write_with_hash_preserves_underlying_source(self, store: AsyncStore) -> None:
        result = await write_with_hash(store, "f.txt", b"data")
        assert result.source == "native"

    @pytest.mark.spec("WR-006")
    async def test_write_with_hash_custom_algorithm(self, store: AsyncStore) -> None:
        content = b"test"
        result = await write_with_hash(store, "f.txt", content, algorithm="sha512")
        assert result.digest is not None
        assert result.digest.algorithm == "sha512"
        assert result.digest.value == hashlib.sha512(content).hexdigest()
