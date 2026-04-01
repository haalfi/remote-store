"""Tests for AsyncBackend ABC -- derived from sdd/specs/029-async-store-backend-api.md."""

from __future__ import annotations

import pytest

from remote_store._errors import CapabilityNotSupported
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio._async_memory import AsyncMemoryBackend


class TestAsyncBackendABC:
    """ASYNC-001: AsyncBackend cannot be instantiated directly."""

    @pytest.mark.spec("ASYNC-001")
    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            AsyncBackend()  # type: ignore[abstract]

    @pytest.mark.spec("ASYNC-001")
    def test_concrete_subclass_instantiates(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.name == "async-memory"


class TestAsyncBackendDefaults:
    """ASYNC-022/023/028/029: Default implementations of concrete methods."""

    @pytest.mark.spec("ASYNC-022")
    async def test_aclose_noop(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.aclose()
        # Backend still functional after aclose (no-op)
        assert backend.name == "async-memory"

    @pytest.mark.spec("ASYNC-022", "ASYNC-057")
    async def test_check_health_noop(self) -> None:
        backend = AsyncMemoryBackend()
        result = await backend.check_health()
        assert result is None

    @pytest.mark.spec("ASYNC-028")
    async def test_glob_raises_capability_not_supported(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(CapabilityNotSupported, match="does not support glob"):
            async for _ in backend.glob("*.txt"):
                pass

    @pytest.mark.spec("ASYNC-029")
    async def test_iter_children_chains_files_and_folders(self) -> None:
        backend = AsyncMemoryBackend()
        await backend.write("a.txt", b"a")
        await backend.write("sub/b.txt", b"b")
        children = [item async for item in backend.iter_children("")]
        names = {c.name for c in children}
        assert "a.txt" in names
        assert "sub" in names
        assert len(children) == 2


class TestAsyncBackendContextManager:
    """ASYNC-023: __aenter__/__aexit__ protocol."""

    @pytest.mark.spec("ASYNC-023")
    async def test_context_manager_returns_self(self) -> None:
        backend = AsyncMemoryBackend()
        async with backend as b:
            assert b is backend

    @pytest.mark.spec("ASYNC-023")
    async def test_context_manager_calls_aclose(self) -> None:
        backend = AsyncMemoryBackend()
        async with backend:
            await backend.write("f.txt", b"data")
        # Backend is still usable (aclose is a no-op for memory)
        assert await backend.read_bytes("f.txt") == b"data"


class TestAsyncBackendSyncMethods:
    """ASYNC-025/026/027: Sync methods -- to_key, native_path, resolve, unwrap."""

    @pytest.mark.spec("ASYNC-026")
    def test_to_key_identity(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.to_key("some/path") == "some/path"

    @pytest.mark.spec("ASYNC-027")
    def test_native_path_identity(self) -> None:
        backend = AsyncMemoryBackend()
        assert backend.native_path("some/path") == "some/path"

    @pytest.mark.spec("ASYNC-025", "ASYNC-058")
    def test_resolve_returns_plan(self) -> None:
        backend = AsyncMemoryBackend()
        plan = backend.resolve("some/path")
        assert plan.kind == "async-memory"
        assert plan.key == "some/path"
        assert plan.native_path == "some/path"

    @pytest.mark.spec("ASYNC-025")
    def test_unwrap_raises(self) -> None:
        backend = AsyncMemoryBackend()
        with pytest.raises(CapabilityNotSupported, match="does not expose native handle"):
            backend.unwrap(dict)
