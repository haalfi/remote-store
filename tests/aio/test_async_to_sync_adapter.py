"""Tests for AsyncBackendSyncAdapter.

Derived from sdd/specs/029-async-store-backend-api.md § AsyncBackendSyncAdapter,
invariants ASYNC-080..093.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
from typing import Any

import pytest

from remote_store._async_to_sync_adapter import AsyncBackendSyncAdapter, _SyncSafeHandleProvider
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import BackendUnavailable, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderEntry
from remote_store.aio._async_memory import AsyncMemoryBackend
from tests.aio._doubles import _HangingAsyncBackend, _RaisingAsyncBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(*, name: str = "raising-async") -> tuple[AsyncBackendSyncAdapter, _RaisingAsyncBackend]:
    double = _RaisingAsyncBackend(name=name)
    return AsyncBackendSyncAdapter(double), double


def _make_memory_adapter() -> tuple[AsyncBackendSyncAdapter, AsyncMemoryBackend]:
    backend = AsyncMemoryBackend()
    return AsyncBackendSyncAdapter(backend), backend


def _populated_adapter() -> tuple[AsyncBackendSyncAdapter, AsyncMemoryBackend]:
    adapter, backend = _make_memory_adapter()
    adapter.write("a.txt", b"alpha")
    adapter.write("b.txt", b"bravo")
    adapter.write("sub/c.txt", b"charlie")
    return adapter, backend


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Adapter wraps an AsyncBackend; rejects non-AsyncBackend."""

    def test_wraps_valid_async_backend(self) -> None:
        adapter = AsyncBackendSyncAdapter(AsyncMemoryBackend())
        assert adapter.name == "async-memory"
        adapter.close()

    def test_rejects_non_async_backend(self) -> None:
        from remote_store.backends._memory import MemoryBackend

        with pytest.raises(TypeError, match="AsyncBackend"):
            AsyncBackendSyncAdapter(MemoryBackend())  # type: ignore[arg-type]

    def test_spawns_background_thread(self) -> None:
        adapter = AsyncBackendSyncAdapter(AsyncMemoryBackend())
        assert adapter._thread.is_alive()  # internal: no public observable for thread status
        adapter.close()

    def test_loop_is_running_after_init(self) -> None:
        adapter = AsyncBackendSyncAdapter(AsyncMemoryBackend())
        assert adapter._loop.is_running()  # internal: no public observable for loop status
        adapter.close()


# ---------------------------------------------------------------------------
# Capability translation (ASYNC-084)
# ---------------------------------------------------------------------------


class TestCapabilityTranslation:
    """ASYNC-084: SEEKABLE_READ masked off; all other capabilities preserved."""

    @pytest.mark.spec("ASYNC-084")
    def test_seekable_read_masked(self) -> None:
        double = _RaisingAsyncBackend()
        assert double.capabilities.supports(Capability.SEEKABLE_READ)
        adapter = AsyncBackendSyncAdapter(double)
        assert not adapter.capabilities.supports(Capability.SEEKABLE_READ)
        adapter.close()

    @pytest.mark.spec("ASYNC-084")
    def test_lazy_read_preserved(self) -> None:
        double = _RaisingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        assert adapter.capabilities.supports(Capability.LAZY_READ)
        adapter.close()

    @pytest.mark.spec("ASYNC-084")
    def test_remaining_flags_preserved(self) -> None:
        double = _RaisingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        for cap in (
            Capability.READ,
            Capability.WRITE,
            Capability.DELETE,
            Capability.LIST,
            Capability.GLOB,
            Capability.MOVE,
            Capability.COPY,
            Capability.ATOMIC_WRITE,
            Capability.ATOMIC_MOVE,
            Capability.METADATA,
        ):
            assert adapter.capabilities.supports(cap), f"Expected {cap!r} to be preserved"
        adapter.close()

    @pytest.mark.spec("ASYNC-084")
    def test_seekable_not_added_when_absent(self) -> None:
        caps = CapabilitySet({Capability.READ, Capability.WRITE})
        double = _RaisingAsyncBackend(capabilities=caps)
        adapter = AsyncBackendSyncAdapter(double)
        assert not adapter.capabilities.supports(Capability.SEEKABLE_READ)
        adapter.close()


# ---------------------------------------------------------------------------
# Property and path passthrough
# ---------------------------------------------------------------------------


class TestPropertyPassthrough:
    """name, to_key, native_path, resolve forwarded without entering the loop."""

    def test_name_forwarded(self) -> None:
        adapter, _ = _make_adapter(name="my-async")
        assert adapter.name == "my-async"
        adapter.close()

    def test_to_key_forwarded(self) -> None:
        adapter, _ = _make_adapter()
        assert adapter.to_key("some/path") == "some/path"
        adapter.close()

    def test_native_path_forwarded(self) -> None:
        adapter, _ = _make_adapter()
        assert adapter.native_path("some/path") == "some/path"
        adapter.close()

    def test_resolve_forwarded(self) -> None:
        adapter, _ = _make_adapter()
        plan = adapter.resolve("data.csv")
        assert plan.key == "data.csv"
        adapter.close()


# ---------------------------------------------------------------------------
# unwrap() (ASYNC-086)
# ---------------------------------------------------------------------------


class TestUnwrap:
    """ASYNC-086: default raises CapabilityNotSupported; _SyncSafeHandleProvider exemption."""

    @pytest.mark.spec("ASYNC-086")
    def test_default_raises_capability_not_supported(self) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(CapabilityNotSupported, match="AsyncBackendSyncAdapter"):
            adapter.unwrap(object)
        adapter.close()

    @pytest.mark.spec("ASYNC-086")
    def test_sync_safe_handle_provider_forwarded(self) -> None:
        class _SafeBackend(_RaisingAsyncBackend, _SyncSafeHandleProvider):
            def sync_safe_unwrap(self, type_hint: type[Any]) -> Any:
                return "sync-safe-handle"

        adapter = AsyncBackendSyncAdapter(_SafeBackend())
        assert adapter.unwrap(str) == "sync-safe-handle"
        adapter.close()


# ---------------------------------------------------------------------------
# Scalar I/O delegation (ASYNC-087)
# ---------------------------------------------------------------------------


class TestScalarIODelegation:
    """ASYNC-087: scalar I/O methods delegate to the wrapped async backend."""

    def setup_method(self) -> None:
        self.adapter, _ = _populated_adapter()

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-087")
    def test_exists_true(self) -> None:
        assert self.adapter.exists("a.txt") is True

    @pytest.mark.spec("ASYNC-087")
    def test_exists_false(self) -> None:
        assert self.adapter.exists("nope.txt") is False

    @pytest.mark.spec("ASYNC-087")
    def test_is_file(self) -> None:
        assert self.adapter.is_file("a.txt") is True
        assert self.adapter.is_file("sub") is False

    @pytest.mark.spec("ASYNC-087")
    def test_is_folder(self) -> None:
        assert self.adapter.is_folder("sub") is True
        assert self.adapter.is_folder("a.txt") is False

    @pytest.mark.spec("ASYNC-087")
    def test_read_bytes(self) -> None:
        assert self.adapter.read_bytes("a.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-087")
    def test_get_file_info(self) -> None:
        info = self.adapter.get_file_info("a.txt")
        assert info.name == "a.txt"
        assert info.size == 5

    @pytest.mark.spec("ASYNC-087")
    def test_get_folder_info(self) -> None:
        info = self.adapter.get_folder_info("")
        assert info.file_count == 3

    @pytest.mark.spec("ASYNC-087")
    def test_delete(self) -> None:
        self.adapter.delete("a.txt")
        assert self.adapter.exists("a.txt") is False

    @pytest.mark.spec("ASYNC-087")
    def test_delete_missing_ok(self) -> None:
        assert self.adapter.delete("ghost.txt", missing_ok=True) is None

    @pytest.mark.spec("ASYNC-087")
    def test_move(self) -> None:
        self.adapter.move("a.txt", "moved.txt")
        assert self.adapter.exists("a.txt") is False
        assert self.adapter.read_bytes("moved.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-087")
    def test_copy(self) -> None:
        self.adapter.copy("a.txt", "copied.txt")
        assert self.adapter.read_bytes("a.txt") == b"alpha"
        assert self.adapter.read_bytes("copied.txt") == b"alpha"

    @pytest.mark.spec("ASYNC-087")
    def test_delete_folder(self) -> None:
        self.adapter.delete_folder("sub", recursive=True)
        assert self.adapter.exists("sub") is False


# ---------------------------------------------------------------------------
# Error propagation (ASYNC-087)
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """ASYNC-087: exceptions from the wrapped async coroutine propagate verbatim."""

    @pytest.mark.spec("ASYNC-087")
    def test_same_exception_object_propagates(self) -> None:
        err = NotFound("gone", path="/gone")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)
        try:
            with pytest.raises(NotFound) as exc_info:
                adapter.exists("any")
            assert exc_info.value is err
        finally:
            adapter.close()

    @pytest.mark.spec("ASYNC-087")
    def test_custom_error_type_preserved(self) -> None:
        err = BackendUnavailable("down", backend="test")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)
        try:
            with pytest.raises(BackendUnavailable):
                adapter.read_bytes("f.txt")
        finally:
            adapter.close()

    @pytest.mark.spec("ASYNC-087")
    @pytest.mark.parametrize(
        ("method", "kwargs"),
        [
            ("exists", {"path": "x"}),
            ("is_file", {"path": "x"}),
            ("is_folder", {"path": "x"}),
            ("read_bytes", {"path": "x"}),
            ("delete", {"path": "x"}),
            ("delete_folder", {"path": "x"}),
            ("move", {"src": "x", "dst": "y"}),
            ("copy", {"src": "x", "dst": "y"}),
            ("write", {"path": "x", "content": b"data"}),
            ("write_atomic", {"path": "x", "content": b"data"}),
        ],
    )
    def test_error_propagates_from_scalar(self, method: str, kwargs: dict) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(NotFound):
            getattr(adapter, method)(**kwargs)
        adapter.close()


# ---------------------------------------------------------------------------
# check_health (ASYNC-093)
# ---------------------------------------------------------------------------


class TestCheckHealth:
    """ASYNC-093: check_health() is not a no-op; propagates errors verbatim."""

    @pytest.mark.spec("ASYNC-093")
    def test_successful_check_health_returns_none(self) -> None:
        adapter, _ = _make_memory_adapter()
        assert adapter.check_health() is None
        adapter.close()

    @pytest.mark.spec("ASYNC-093")
    def test_health_error_propagates_verbatim(self) -> None:
        err = BackendUnavailable("host unreachable", backend="remote")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)
        try:
            with pytest.raises(BackendUnavailable) as exc_info:
                adapter.check_health()
            assert exc_info.value is err
        finally:
            adapter.close()

    @pytest.mark.spec("ASYNC-093")
    def test_check_health_actually_calls_backend(self) -> None:
        called = threading.Event()

        class _TrackedBackend(AsyncMemoryBackend):
            async def check_health(self) -> None:
                called.set()

        adapter = AsyncBackendSyncAdapter(_TrackedBackend())
        adapter.check_health()
        assert called.is_set()
        adapter.close()


# ---------------------------------------------------------------------------
# Streaming read (ASYNC-080, ASYNC-081)
# ---------------------------------------------------------------------------


class TestStreamingRead:
    """ASYNC-080, ASYNC-081: read() returns a forward-only BinaryIO-like stream."""

    def setup_method(self) -> None:
        self.adapter, _ = _make_memory_adapter()
        self.adapter.write("f.txt", b"hello world")

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-080", "ASYNC-081")
    def test_read_all_returns_content(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert stream.read() == b"hello world"

    @pytest.mark.spec("ASYNC-081")
    def test_read_minus_one_drains_to_eof(self) -> None:
        self.adapter.write("big.txt", b"X" * 200_000)
        with self.adapter.read("big.txt") as stream:
            data = stream.read(-1)
        assert data == b"X" * 200_000

    @pytest.mark.spec("ASYNC-081")
    def test_read_n_short_read_semantics(self) -> None:
        with self.adapter.read("f.txt") as stream:
            first = stream.read(5)
            rest = stream.read(-1)
        assert len(first) <= 5
        assert first + rest == b"hello world"

    @pytest.mark.spec("ASYNC-081")
    def test_read_zero_returns_empty(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert stream.read(0) == b""

    @pytest.mark.spec("ASYNC-081")
    def test_seekable_is_false(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert stream.seekable() is False

    @pytest.mark.spec("ASYNC-081")
    def test_readable_is_true(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert stream.readable() is True

    @pytest.mark.spec("ASYNC-081")
    def test_fileno_not_provided(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert not hasattr(stream, "fileno")

    @pytest.mark.spec("ASYNC-081")
    def test_read_after_close_returns_empty(self) -> None:
        stream = self.adapter.read("f.txt")
        stream.close()
        assert stream.read() == b""
        assert stream.read(5) == b""


# ---------------------------------------------------------------------------
# Mid-stream read failure (ASYNC-090)
# ---------------------------------------------------------------------------


class TestMidStreamReadFailure:
    """ASYNC-090: __anext__ failure transitions stream to closed-on-error state."""

    @pytest.mark.spec("ASYNC-090")
    def test_mid_stream_error_propagates_verbatim(self) -> None:
        err = NotFound("mid-stream", path="/f")
        double = _RaisingAsyncBackend(error=err, read_chunks_before_raise=2)
        adapter = AsyncBackendSyncAdapter(double)
        stream = adapter.read("f.txt")
        # Two successful single-byte reads from the two pre-raise chunks.
        assert stream.read(1) == b"x"
        assert stream.read(1) == b"x"
        with pytest.raises(NotFound) as exc_info:
            stream.read(1)
        assert exc_info.value is err
        adapter.close()

    @pytest.mark.spec("ASYNC-090")
    def test_subsequent_read_after_error_returns_empty(self) -> None:
        double = _RaisingAsyncBackend(read_chunks_before_raise=0)
        adapter = AsyncBackendSyncAdapter(double)
        stream = adapter.read("f.txt")
        with pytest.raises(NotFound):
            stream.read(1)
        assert stream.read(1) == b""
        assert stream.read(-1) == b""
        adapter.close()

    @pytest.mark.spec("ASYNC-090")
    def test_listing_error_transitions_to_done(self) -> None:
        double = _RaisingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        bridge = adapter.list_files("dir")
        with pytest.raises(NotFound):
            next(bridge)
        with pytest.raises(StopIteration):
            next(bridge)
        adapter.close()


# ---------------------------------------------------------------------------
# Listing bridge (ASYNC-080)
# ---------------------------------------------------------------------------


class TestListingBridge:
    """ASYNC-080: listing iterators bridge async items one at a time."""

    def setup_method(self) -> None:
        self.adapter, _ = _populated_adapter()

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-080")
    def test_list_files_root(self) -> None:
        files = list(self.adapter.list_files(""))
        assert len(files) == 2
        assert {f.name for f in files} == {"a.txt", "b.txt"}

    @pytest.mark.spec("ASYNC-080")
    def test_list_files_recursive(self) -> None:
        files = list(self.adapter.list_files("", recursive=True))
        assert len(files) == 3

    @pytest.mark.spec("ASYNC-080")
    def test_list_folders(self) -> None:
        folders = list(self.adapter.list_folders(""))
        assert len(folders) == 1
        assert folders[0].name == "sub"

    @pytest.mark.spec("ASYNC-080")
    def test_iter_children_yields_files_and_folders(self) -> None:
        children = list(self.adapter.iter_children(""))
        files = [c for c in children if isinstance(c, FileInfo)]
        folders = [c for c in children if isinstance(c, FolderEntry)]
        assert {f.name for f in files} == {"a.txt", "b.txt"}
        assert {f.name for f in folders} == {"sub"}

    @pytest.mark.spec("ASYNC-080")
    def test_listing_error_propagates(self) -> None:
        err = NotFound("folder", path="/dir")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)
        with pytest.raises(NotFound) as exc_info:
            next(adapter.list_files("dir"))
        assert exc_info.value is err
        adapter.close()

    @pytest.mark.spec("ASYNC-080")
    def test_glob_error_propagates_through_bridge(self) -> None:
        # Default glob raises CapabilityNotSupported on first pull.
        double = _RaisingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        with pytest.raises(CapabilityNotSupported):
            next(adapter.glob("*.txt"))
        adapter.close()


# ---------------------------------------------------------------------------
# Write bridge (ASYNC-091)
# ---------------------------------------------------------------------------


class TestWriteBridge:
    """ASYNC-091: write/write_atomic accept bytes and BinaryIO; BinaryIO errors surface."""

    def setup_method(self) -> None:
        self.adapter, _ = _make_memory_adapter()

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-091")
    def test_write_bytes(self) -> None:
        self.adapter.write("out.txt", b"hello")
        assert self.adapter.read_bytes("out.txt") == b"hello"

    @pytest.mark.spec("ASYNC-091")
    def test_write_binaryio(self) -> None:
        self.adapter.write("out.txt", io.BytesIO(b"streaming write"))
        assert self.adapter.read_bytes("out.txt") == b"streaming write"

    @pytest.mark.spec("ASYNC-091")
    def test_write_atomic_bytes(self) -> None:
        self.adapter.write_atomic("at.txt", b"atomic")
        assert self.adapter.read_bytes("at.txt") == b"atomic"

    @pytest.mark.spec("ASYNC-091")
    def test_write_atomic_binaryio(self) -> None:
        self.adapter.write_atomic("at.txt", io.BytesIO(b"atomic-stream"))
        assert self.adapter.read_bytes("at.txt") == b"atomic-stream"

    @pytest.mark.spec("ASYNC-091")
    def test_binaryio_read_error_propagates(self) -> None:
        """Mid-write BinaryIO read failure surfaces from the blocking write() call."""

        class _FailingStream:
            def read(self, n: int = -1) -> bytes:
                raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            self.adapter.write("f.txt", _FailingStream())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# open_atomic synthesis (ASYNC-085)
# ---------------------------------------------------------------------------


class TestOpenAtomic:
    """ASYNC-085: spool-and-flush context manager."""

    def setup_method(self) -> None:
        self.adapter, _ = _make_memory_adapter()

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-085")
    def test_clean_exit_writes_content(self) -> None:
        with self.adapter.open_atomic("out.txt") as spool:
            spool.write(b"spooled content")
        assert self.adapter.read_bytes("out.txt") == b"spooled content"

    @pytest.mark.spec("ASYNC-085")
    def test_exception_in_body_leaves_existing_path_untouched(self) -> None:
        self.adapter.write("existing.txt", b"original")

        def _write_and_raise() -> None:
            with self.adapter.open_atomic("existing.txt") as spool:
                spool.write(b"partial overwrite")
                raise ValueError("intentional")

        with pytest.raises(ValueError, match="intentional"):
            _write_and_raise()
        assert self.adapter.read_bytes("existing.txt") == b"original"

    @pytest.mark.spec("ASYNC-085")
    def test_exception_in_body_does_not_create_new_path(self) -> None:
        def _write_and_raise() -> None:
            with self.adapter.open_atomic("new.txt") as spool:
                spool.write(b"data")
                raise RuntimeError("abort")

        with pytest.raises(RuntimeError, match="abort"):
            _write_and_raise()
        assert self.adapter.exists("new.txt") is False

    @pytest.mark.spec("ASYNC-085")
    def test_write_atomic_error_propagates_on_exit(self) -> None:
        err = NotFound("backend error", path="/")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)

        def _write_and_exit() -> None:
            with adapter.open_atomic("out.txt") as spool:
                spool.write(b"data")

        with pytest.raises(NotFound):
            _write_and_exit()
        adapter.close()


# ---------------------------------------------------------------------------
# Fail-fast on running event loop (ASYNC-082)
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
class TestRunningLoopFailFast:
    """ASYNC-082: adapter methods raise RuntimeError when called from a running loop."""

    @pytest.mark.spec("ASYNC-082")
    def test_exists_raises_from_running_loop(self) -> None:
        adapter, _ = _make_adapter()

        async def _probe() -> None:
            adapter.exists("x")

        with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
            asyncio.run(_probe())
        adapter.close()

    @pytest.mark.spec("ASYNC-082")
    def test_read_raises_from_running_loop(self) -> None:
        adapter, _ = _make_adapter()

        async def _probe() -> None:
            adapter.read("x")

        with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
            asyncio.run(_probe())
        adapter.close()

    @pytest.mark.spec("ASYNC-082")
    def test_list_files_raises_from_running_loop(self) -> None:
        adapter, _ = _make_adapter()

        async def _probe() -> None:
            adapter.list_files("")

        with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
            asyncio.run(_probe())
        adapter.close()

    @pytest.mark.spec("ASYNC-082")
    def test_message_stem_exact(self) -> None:
        adapter, _ = _make_adapter()

        async def _probe() -> None:
            adapter.exists("x")

        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter cannot be called from a running event loop"):
            asyncio.run(_probe())
        adapter.close()


# ---------------------------------------------------------------------------
# Closed-adapter reuse (ASYNC-083)
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
class TestClosedAdapterReuse:
    """ASYNC-083: after close(), any sync I/O method raises RuntimeError."""

    @pytest.mark.spec("ASYNC-083")
    @pytest.mark.parametrize(
        ("method", "kwargs"),
        [
            ("exists", {"path": "x"}),
            ("is_file", {"path": "x"}),
            ("is_folder", {"path": "x"}),
            ("read_bytes", {"path": "x"}),
            ("read", {"path": "x"}),
            ("list_files", {"path": ""}),
            ("list_folders", {"path": ""}),
            ("write", {"path": "x", "content": b"data"}),
            ("write_atomic", {"path": "x", "content": b"data"}),
            ("open_atomic", {"path": "x"}),
            ("check_health", {}),
        ],
    )
    def test_raises_after_close(self, method: str, kwargs: dict) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            getattr(adapter, method)(**kwargs)

    @pytest.mark.spec("ASYNC-083")
    def test_close_is_idempotent(self) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        adapter.close()  # must not raise


# ---------------------------------------------------------------------------
# Sync context-manager protocol (ASYNC-092)
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
class TestSyncContextManager:
    """ASYNC-092: __enter__ returns self; __exit__ calls close(); no async touch."""

    @pytest.mark.spec("ASYNC-092")
    def test_enter_returns_self(self) -> None:
        adapter, _ = _make_adapter()
        with adapter as ctx:
            assert ctx is adapter

    @pytest.mark.spec("ASYNC-092")
    def test_exit_closes_adapter(self) -> None:
        adapter, _ = _make_adapter()
        with adapter:
            pass
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

    @pytest.mark.spec("ASYNC-092")
    def test_body_exception_propagates_and_adapter_closed(self) -> None:
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError, match="boom"), adapter:
            raise ValueError("boom")
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

    @pytest.mark.spec("ASYNC-092")
    def test_aenter_of_wrapped_backend_not_called(self) -> None:
        # _HangingAsyncBackend would block any awaited call; __enter__ must be
        # instant -- no aenter/aexit on the wrapped backend is invoked.
        adapter = AsyncBackendSyncAdapter(_HangingAsyncBackend())
        with adapter:
            pass
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")


# ---------------------------------------------------------------------------
# Close semantics and drain order (ASYNC-088)
# ---------------------------------------------------------------------------


class TestCloseSemantics:
    """ASYNC-088: drain order, idempotency, aclose propagation, timeout warning."""

    @pytest.mark.spec("ASYNC-088")
    def test_aclose_called_on_wrapped_backend(self) -> None:
        double = _RaisingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        adapter.close()
        assert double.aclose_called is True

    @pytest.mark.spec("ASYNC-088")
    def test_close_is_idempotent(self) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        adapter.close()

    @pytest.mark.spec("ASYNC-088")
    def test_aclose_error_swallowed_not_propagated(self) -> None:
        double = _RaisingAsyncBackend(aclose_error=RuntimeError("aclose exploded"))
        adapter = AsyncBackendSyncAdapter(double)
        adapter.close()  # must not raise
        assert double.aclose_called is True

    @pytest.mark.spec("ASYNC-088")
    def test_loop_stopped_after_close(self) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        assert not adapter._loop.is_running()  # internal: no public observable for loop state

    @pytest.mark.spec("ASYNC-088")
    def test_thread_joined_after_close(self) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        assert not adapter._thread.is_alive()  # internal: no public observable for thread state

    @pytest.mark.spec("ASYNC-088")
    def test_timeout_close_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        double = _HangingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        double.bind_loop(adapter._loop)

        with caplog.at_level(logging.WARNING, logger="remote_store._async_to_sync_adapter"):
            adapter.close(timeout=0.05)

        assert "close timed out" in caplog.text


# ---------------------------------------------------------------------------
# Concurrent-callers no-deadlock invariant (ASYNC-089)
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
class TestConcurrency:
    """ASYNC-089: N=32 threads, M≥16 iterations each, no deadlock."""

    @pytest.mark.spec("ASYNC-089")
    def test_concurrent_calls_no_deadlock(self) -> None:
        N_THREADS = 32
        M_ITERS = 16

        adapter, _ = _make_memory_adapter()
        adapter.write("shared.txt", b"concurrent-data")

        errors: list[BaseException] = []
        barrier = threading.Barrier(N_THREADS)

        def _worker() -> None:
            barrier.wait()
            for _ in range(M_ITERS):
                try:
                    adapter.exists("shared.txt")
                    adapter.read_bytes("shared.txt")
                    list(adapter.list_files(""))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        adapter.close()

        alive = [t for t in threads if t.is_alive()]
        assert not alive, f"{len(alive)} threads still alive -- deadlock suspected"
        assert not errors, f"Errors during concurrent calls: {errors[:3]}"
