"""Tests for AsyncBackendSyncAdapter.

Derived from sdd/specs/029-async-store-backend-api.md § AsyncBackendSyncAdapter,
invariants ASYNC-080..093.
"""

from __future__ import annotations

import asyncio
import gc
import io
import logging
import threading
from typing import Any

import pytest

from remote_store._async_to_sync_adapter import (
    AsyncBackendSyncAdapter,
    _AsyncIteratorBridge,
    _SyncSafeHandleProvider,
)
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import BackendUnavailable, CapabilityNotSupported, NotFound
from remote_store._models import FileInfo, FolderEntry, WriteResult
from remote_store.aio.backends._memory import AsyncMemoryBackend
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


def _reap_adapter(adapter: AsyncBackendSyncAdapter) -> None:
    """Join the daemon thread so the adapter's private loop is closed before the test returns.

    A timed-out ``close()`` returns before the daemon thread runs its
    ``finally: loop.close()``, leaving the loop to close asynchronously; tests that
    drive that path on a hanging backend must call this so the close is
    deterministic instead of racing the cyclic GC (BK-281).
    """
    adapter._thread.join(timeout=5.0)
    assert not adapter._thread.is_alive(), "adapter daemon thread did not exit after close()"
    assert adapter._loop.is_closed(), "adapter private loop not closed after thread join"


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

    @pytest.mark.parametrize(
        ("method", "arg", "expected"),
        [
            ("to_key", "some/path", "some/path"),
            ("native_path", "some/path", "some/path"),
        ],
    )
    def test_path_methods_forwarded(self, method: str, arg: str, expected: str) -> None:
        adapter, _ = _make_adapter()
        assert getattr(adapter, method)(arg) == expected
        adapter.close()

    def test_name_forwarded(self) -> None:
        adapter, _ = _make_adapter(name="my-async")
        assert adapter.name == "my-async"
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
    @pytest.mark.parametrize(
        ("method", "path", "expected"),
        [
            ("exists", "a.txt", True),
            ("exists", "nope.txt", False),
            ("is_file", "a.txt", True),
            ("is_file", "sub", False),
            ("is_folder", "sub", True),
            ("is_folder", "a.txt", False),
            ("read_bytes", "a.txt", b"alpha"),
        ],
    )
    def test_scalar_query(self, method: str, path: str, expected: Any) -> None:
        assert getattr(self.adapter, method)(path) == expected

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
    def test_fileno_raises_unsupported(self) -> None:
        # _ChunkPullReader subclasses io.RawIOBase, so fileno() exists but
        # raises io.UnsupportedOperation -- no file descriptor is backed.
        with self.adapter.read("f.txt") as stream, pytest.raises(io.UnsupportedOperation):
            stream.fileno()  # type: ignore[union-attr]

    @pytest.mark.spec("ASYNC-081")
    def test_read_after_close_raises_valueerror(self) -> None:
        stream = self.adapter.read("f.txt")
        stream.close()
        with pytest.raises(ValueError, match="I/O operation on closed file"):
            stream.read()
        with pytest.raises(ValueError, match="I/O operation on closed file"):
            stream.read(5)

    @pytest.mark.spec("ASYNC-081")
    def test_readinto_after_close_raises_valueerror(self) -> None:
        stream = self.adapter.read("f.txt")
        stream.close()
        buf = bytearray(8)
        with pytest.raises(ValueError, match="I/O operation on closed file"):
            stream.readinto(buf)

    @pytest.mark.spec("ASYNC-081")
    def test_close_race_stream_subsequent_read_returns_empty(self) -> None:
        # Simulate the _pull_chunk RuntimeError close-race: close the adapter's loop
        # directly (without setting _closed) so _guard() passes but
        # run_coroutine_threadsafe raises RuntimeError (loop closed). This is the
        # TOCTOU window described in adapter.close() docstring.
        adapter, _ = _make_memory_adapter()
        adapter.write("f.txt", b"data")
        stream = adapter.read("f.txt")
        loop = adapter._loop  # internal: no public observable
        loop.call_soon_threadsafe(loop.stop)
        adapter._thread.join(timeout=5.0)  # internal: no public observable
        loop.close()
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            stream.read(1)
        # _closed_on_error = True: error-close contract returns empty/0, not ValueError
        assert stream.read() == b""
        buf = bytearray(8)
        assert stream.readinto(buf) == 0
        adapter.close()


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
        # Post-error state: stream is closed, subsequent reads return b"".
        assert stream.read(1) == b""
        assert stream.read(-1) == b""
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
    def test_subsequent_readinto_after_error_returns_zero(self) -> None:
        double = _RaisingAsyncBackend(read_chunks_before_raise=0)
        adapter = AsyncBackendSyncAdapter(double)
        stream = adapter.read("f.txt")
        with pytest.raises(NotFound):
            stream.read(1)
        buf = bytearray(8)
        assert stream.readinto(buf) == 0
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

    @pytest.mark.spec("ASYNC-085")
    def test_open_atomic_raises_capability_not_supported(self) -> None:
        """ASYNC-085: CapabilityNotSupported from write_atomic surfaces on __exit__."""
        err = CapabilityNotSupported(capability=Capability.ATOMIC_WRITE, backend="raising-async")
        double = _RaisingAsyncBackend(error=err)
        adapter = AsyncBackendSyncAdapter(double)

        def _write_and_exit() -> None:
            with adapter.open_atomic("out.txt") as spool:
                spool.write(b"data")

        with pytest.raises(CapabilityNotSupported):
            _write_and_exit()
        adapter.close()


# ---------------------------------------------------------------------------
# Fail-fast on running event loop (ASYNC-082)
# ---------------------------------------------------------------------------


class TestRunningLoopFailFast:
    """ASYNC-082: adapter methods raise RuntimeError when called from a running loop."""

    @pytest.mark.spec("ASYNC-082")
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
            ("write", {"path": "x", "content": b"d"}),
            ("write_atomic", {"path": "x", "content": b"d"}),
            ("check_health", {}),
        ],
    )
    def test_raises_from_running_loop(self, method: str, kwargs: dict) -> None:
        adapter, _ = _make_adapter()

        async def _probe() -> None:
            getattr(adapter, method)(**kwargs)

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
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

    @pytest.mark.spec("ASYNC-083")
    def test_closed_guard_does_not_leak_coroutine(self, recwarn: pytest.WarningsRecorder) -> None:
        # _submit must close the coroutine that the caller built before
        # _guard() ran; otherwise CPython emits "coroutine was never awaited".
        adapter, _ = _make_adapter()
        adapter.close()
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")
        gc.collect()
        leaks = [
            w for w in recwarn.list if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
        ]
        assert leaks == [], f"closed-guard leaked coroutine: {leaks[0].message if leaks else ''}"


# ---------------------------------------------------------------------------
# Sync context-manager protocol (ASYNC-092)
# ---------------------------------------------------------------------------


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
        # aclose_called is False after __enter__() because no async method ran.
        double = _HangingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        adapter.__enter__()
        assert double.aclose_called is False, "__enter__ must not call aclose (or any async method)"
        # Use explicit close with short timeout so the hanging aclose doesn't block.
        adapter.close(timeout=0.05)
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")
        _reap_adapter(adapter)


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
        adapter.close()  # must not raise
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

    @pytest.mark.spec("ASYNC-088")
    def test_close_timeout_none_completes_on_fast_backend(self) -> None:
        """timeout=None waits indefinitely; verify it completes and marks adapter closed."""
        adapter, double = _make_adapter()
        adapter.close(timeout=None)  # must not hang on a fast backend
        assert double.aclose_called is True
        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

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
    def test_loop_closed_after_close(self) -> None:
        # Regression for ID-158: the private loop must be *closed* (self-pipe
        # sockets released), not merely stopped.  A stopped-but-not-closed loop
        # emits ResourceWarning when the GC collects it.
        adapter, _ = _make_adapter()
        adapter.close()
        assert adapter._loop.is_closed()  # internal: no public observable for loop state

    @pytest.mark.spec("ASYNC-088")
    def test_thread_joined_after_close(self) -> None:
        adapter, _ = _make_adapter()
        adapter.close()
        assert not adapter._thread.is_alive()  # internal: no public observable for thread state

    @pytest.mark.spec("ASYNC-088")
    def test_close_does_not_leak_coroutine_when_loop_already_stopped(self, recwarn: pytest.WarningsRecorder) -> None:
        # close() builds aclose() and _drain_tasks() coroutines before submitting
        # them to the loop. If the loop is already stopped, run_coroutine_threadsafe
        # raises RuntimeError and those coroutines must be closed explicitly,
        # otherwise CPython emits "coroutine was never awaited".
        adapter, _ = _make_adapter()
        loop = adapter._loop  # internal: no public observable
        loop.call_soon_threadsafe(loop.stop)
        adapter._thread.join(timeout=5.0)  # internal: no public observable
        # internal: no public observable for thread state
        assert not adapter._thread.is_alive(), "loop thread did not stop within 5 s"
        adapter.close()
        gc.collect()
        leaks = [
            w for w in recwarn.list if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
        ]
        assert leaks == [], f"close() leaked coroutine after loop stop: {leaks[0].message if leaks else ''}"

    @pytest.mark.spec("ASYNC-088")
    def test_timeout_close_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        double = _HangingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        double.bind_loop(adapter._loop)

        with caplog.at_level(logging.WARNING, logger="remote_store._async_to_sync_adapter"):
            adapter.close(timeout=0.05)

        matched = [r for r in caplog.records if "close timed out" in r.message]
        assert matched, "expected a close-timeout log record"
        assert all(r.levelno == logging.WARNING for r in matched)
        _reap_adapter(adapter)

    @pytest.mark.spec("ASYNC-088")
    def test_timeout_close_loop_closes_on_thread_join(self) -> None:
        """Joining the daemon thread closes the loop a timed-out close() left winding down (BK-281).

        Pins the property ``_reap_adapter`` relies on: after a timed-out
        ``close()``, the daemon thread's ``finally: loop.close()`` does run once
        joined. This is a smoke check, not the leak guard — what actually catches a
        site that forgets to reap is the suite-wide ``filterwarnings=error``
        exercising every site under load, not this single-threaded assertion.
        """
        double = _HangingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        loop = adapter._loop
        adapter.close(timeout=0.05)
        adapter._thread.join(timeout=5.0)
        assert loop.is_closed()


# ---------------------------------------------------------------------------
# Concurrent-callers no-deadlock invariant (ASYNC-089)
# ---------------------------------------------------------------------------


class TestConcurrency:
    """ASYNC-089: N=32 threads, M≥16 iterations each, no deadlock.

    Also pins ASYNC-094's safe half: funnelling N concurrent sync callers onto
    the adapter's single private loop serializes them deadlock-free, so an
    ``AsyncBackendSyncAdapter`` wrapping an async backend is safe to share.
    """

    @pytest.mark.spec("ASYNC-089")
    @pytest.mark.spec("ASYNC-094")
    def test_concurrent_calls_no_deadlock(self) -> None:
        """Mixed read/write/list/delete with per-thread payload tagging.

        Each thread owns a unique path and writes a unique payload on
        every iteration; the read-back must match exactly (no cross-thread
        result crossover).  delete + write + list + exists exercises the
        mixed-ops requirement of ASYNC-089.
        """
        N_THREADS = 32
        M_ITERS = 16

        adapter, _ = _make_memory_adapter()

        errors: list[BaseException] = []
        errors_lock = threading.Lock()
        barrier = threading.Barrier(N_THREADS)

        def _worker(tid: int) -> None:
            path = f"thread-{tid}.txt"
            barrier.wait()
            for i in range(M_ITERS):
                try:
                    payload = f"tid={tid} iter={i}".encode()
                    adapter.write(path, payload, overwrite=True)
                    got = adapter.read_bytes(path)
                    if got != payload:
                        with errors_lock:
                            errors.append(AssertionError(f"crossover: tid={tid} got {got!r}"))
                    list(adapter.list_files(""))
                    adapter.exists(path)
                    adapter.delete(path)
                    adapter.write(path, payload, overwrite=False)
                except Exception as exc:  # noqa: BLE001
                    with errors_lock:
                        errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        adapter.close()

        alive = [t for t in threads if t.is_alive()]
        assert not alive, f"{len(alive)} threads still alive -- deadlock suspected"
        assert not errors, f"Errors during concurrent calls: {errors[:3]}"


# ---------------------------------------------------------------------------
# Concurrent close vs in-flight submit
# ---------------------------------------------------------------------------


class TestConcurrentClose:
    """Adapter closed while an operation is in-flight does not deadlock or hang."""

    def test_close_while_inflight_submit(self) -> None:
        """Thread A submits a slow op; thread B closes concurrently.

        Neither thread must deadlock.  The in-flight call either completes
        or raises RuntimeError (closed); both outcomes are valid.
        """
        double = _HangingAsyncBackend()
        adapter = AsyncBackendSyncAdapter(double)
        double.bind_loop(adapter._loop)

        outcome: list[BaseException | None] = []
        outcome_lock = threading.Lock()

        def _worker() -> None:
            try:
                adapter.exists("x")
                with outcome_lock:
                    outcome.append(None)
            except RuntimeError:
                with outcome_lock:
                    outcome.append(None)  # expected: closed or running-loop
            except Exception as exc:  # noqa: BLE001
                with outcome_lock:
                    outcome.append(exc)

        worker = threading.Thread(target=_worker)
        worker.start()
        # Give the worker a moment to reach the submit point, then close.
        import time as _time

        _time.sleep(0.02)
        double.release()
        adapter.close(timeout=5.0)
        worker.join(timeout=10)

        assert not worker.is_alive(), "worker thread hung -- possible deadlock"
        assert not [e for e in outcome if e is not None], f"unexpected error: {outcome}"


# ---------------------------------------------------------------------------
# Abandoned-iterator GC path
# ---------------------------------------------------------------------------


class TestAbandonedIteratorGC:
    """_AsyncIteratorBridge.__del__ submits aclose() when GC'd before exhaustion."""

    def test_del_submits_aclose_on_gc(self) -> None:
        """Dropping a listing iterator triggers a best-effort aclose()."""
        aclose_called = threading.Event()

        class _TrackingBackend(_RaisingAsyncBackend):
            """Yields one item then suspends; tracks aclose() via a threading.Event."""

            async def list_files(self, path: str, *, recursive: bool = False, max_depth: int | None = None):  # type: ignore[override]
                from datetime import datetime, timezone

                from remote_store._models import FileInfo

                try:
                    yield FileInfo(
                        name="x.txt",
                        path="x.txt",
                        size=1,
                        modified_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    )
                    # Suspend indefinitely -- caller will drop the bridge.
                    import asyncio as _asyncio

                    await _asyncio.Event().wait()
                finally:
                    aclose_called.set()

        backend = _TrackingBackend()
        adapter = AsyncBackendSyncAdapter(backend)

        bridge = adapter.list_files("")
        # Pull one item -- the generator is now suspended at the second yield.
        next(bridge)
        # Abandon the bridge (simulate early loop break).
        del bridge
        gc.collect()

        # __del__ fire-and-forgets aclose(); give the loop a moment to run it.
        aclose_called.wait(timeout=2.0)
        adapter.close(timeout=1.0)
        assert aclose_called.is_set(), "__del__ did not trigger aclose() on abandoned iterator"

    def test_aclose_best_effort_direct(self) -> None:
        """Calling _aclose_best_effort() directly submits aclose() without GC."""
        aclose_called = threading.Event()

        class _TrackingBackend(_RaisingAsyncBackend):
            async def list_files(self, path: str, *, recursive: bool = False, max_depth: int | None = None):  # type: ignore[override]
                from datetime import datetime, timezone

                from remote_store._models import FileInfo

                try:
                    yield FileInfo(
                        name="x.txt",
                        path="x.txt",
                        size=1,
                        modified_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    )
                    import asyncio as _asyncio

                    await _asyncio.Event().wait()
                finally:
                    aclose_called.set()

        backend = _TrackingBackend()
        adapter = AsyncBackendSyncAdapter(backend)

        bridge = adapter.list_files("")
        next(bridge)  # suspend the generator at the second yield

        bridge._aclose_best_effort()  # call directly, not via GC

        aclose_called.wait(timeout=2.0)
        adapter.close(timeout=1.0)
        assert aclose_called.is_set(), "_aclose_best_effort() did not submit aclose()"


# ---------------------------------------------------------------------------
# write_atomic mid-BinaryIO error path
# ---------------------------------------------------------------------------


class TestWriteAtomicMidBinaryIO:
    """write_atomic with a BinaryIO that raises mid-read surfaces the error."""

    @pytest.mark.spec("ASYNC-091")
    def test_write_atomic_binaryio_read_error_propagates(self) -> None:
        class _FailingStream:
            def read(self, n: int = -1) -> bytes:
                raise OSError("disk full")

        adapter, _ = _make_memory_adapter()
        with pytest.raises(OSError, match="disk full"):
            adapter.write_atomic("f.txt", _FailingStream())  # type: ignore[arg-type]
        adapter.close()


# ---------------------------------------------------------------------------
# Capability masking — WRITE_RESULT_NATIVE / USER_METADATA (WR-004, WR-010)
# ---------------------------------------------------------------------------


class TestCapabilityMasking:
    """Adapter preserves WRITE_RESULT_NATIVE and USER_METADATA from inner backend."""

    def _adapter_with_caps(self, caps: set[Capability], caplog: pytest.LogCaptureFixture) -> AsyncBackendSyncAdapter:
        double = _HangingAsyncBackend(capabilities=CapabilitySet(caps))
        adapter = AsyncBackendSyncAdapter(double)
        with caplog.at_level(logging.CRITICAL, logger="remote_store._async_to_sync_adapter"):
            adapter.close(timeout=0.05)  # not doing I/O — close immediately
        _reap_adapter(adapter)
        return adapter

    @pytest.mark.spec("WR-004")
    def test_write_result_native_preserved_when_inner_declares_it(self, caplog: pytest.LogCaptureFixture) -> None:
        adapter = self._adapter_with_caps({Capability.READ, Capability.WRITE, Capability.WRITE_RESULT_NATIVE}, caplog)
        assert adapter.capabilities.supports(Capability.WRITE_RESULT_NATIVE)

    @pytest.mark.spec("WR-010")
    def test_user_metadata_preserved_when_inner_declares_it(self, caplog: pytest.LogCaptureFixture) -> None:
        adapter = self._adapter_with_caps({Capability.READ, Capability.WRITE, Capability.USER_METADATA}, caplog)
        assert adapter.capabilities.supports(Capability.USER_METADATA)

    def test_other_capabilities_pass_through_unchanged(self, caplog: pytest.LogCaptureFixture) -> None:
        adapter = self._adapter_with_caps({Capability.READ, Capability.WRITE, Capability.COPY}, caplog)
        assert adapter.capabilities.supports(Capability.READ)
        assert adapter.capabilities.supports(Capability.WRITE)
        assert adapter.capabilities.supports(Capability.COPY)


# ---------------------------------------------------------------------------
# WriteResult from write / write_atomic (WR-001, WR-003, WR-004)
# ---------------------------------------------------------------------------


class TestAdapterWriteResult:
    """AsyncBackendSyncAdapter.write/write_atomic return a valid WriteResult."""

    @pytest.mark.spec("WR-001")
    @pytest.mark.spec("WR-004")
    def test_write_bytes_returns_write_result(self) -> None:
        from remote_store._path import RemotePath

        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", b"hello")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 5
        adapter.close()

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"hello world", 11), (b"", 0)])
    def test_write_bytes_size_matches_payload(self, payload: bytes, expected_size: int) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", payload)
        assert result.size == expected_size
        adapter.close()

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"streamed", 8), (b"", 0)])
    def test_write_binaryio_size_counted_without_materialising(self, payload: bytes, expected_size: int) -> None:
        import io as _io

        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", _io.BytesIO(payload))
        assert result.size == expected_size
        adapter.close()

    @pytest.mark.spec("WR-001")
    def test_write_atomic_returns_write_result(self) -> None:
        from remote_store._path import RemotePath

        adapter, _ = _make_memory_adapter()
        result = adapter.write_atomic("f.txt", b"data")
        assert isinstance(result, WriteResult)
        assert result.source == "native"
        assert result.path == RemotePath("f.txt")
        assert result.size == 4
        adapter.close()

    @pytest.mark.spec("WR-003")
    @pytest.mark.parametrize(("payload", "expected_size"), [(b"atomic-stream", 13), (b"", 0)])
    def test_write_atomic_binaryio_size(self, payload: bytes, expected_size: int) -> None:
        import io as _io

        adapter, _ = _make_memory_adapter()
        result = adapter.write_atomic("f.txt", _io.BytesIO(payload))
        assert result.size == expected_size
        adapter.close()

    @pytest.mark.spec("WR-001")
    def test_write_with_none_metadata_returns_write_result_metadata_none(self) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", b"x", metadata=None)
        assert result.metadata is None
        adapter.close()

    @pytest.mark.spec("WR-010")
    def test_write_with_nonempty_metadata_succeeds(self) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", b"x", metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}
        adapter.close()

    @pytest.mark.spec("WR-010")
    def test_write_atomic_with_nonempty_metadata_succeeds(self) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write_atomic("f.txt", b"x", metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}
        adapter.close()

    @pytest.mark.spec("WR-010")
    def test_write_binaryio_metadata_forwarded(self) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write("f.txt", io.BytesIO(b"hello"), metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}
        adapter.close()

    @pytest.mark.spec("WR-010")
    def test_write_atomic_binaryio_metadata_forwarded(self) -> None:
        adapter, _ = _make_memory_adapter()
        result = adapter.write_atomic("f.txt", io.BytesIO(b"hello"), metadata={"k": "v"})
        assert isinstance(result, WriteResult)
        assert result.metadata == {"k": "v"}
        adapter.close()


# ---------------------------------------------------------------------------
# BK-258 — coverage hardening for residual adapter branches
#
# These exercise behavioural branches the original suite left untested:
# the _submit / listing-bridge close-race, the readinto() data path, stream
# close idempotency + aclose-error swallowing, _aclose_best_effort's failure
# handler, _SpoolAndFlush re-exit, and the close() drain loop when the private
# loop still has pending tasks. The remaining gaps (Protocol stub, _pull_chunk's
# redundant _eof guard, _snapshot_tasks' iteration-race except, and the two
# drain-loop race/dead branches) are marked `# pragma: no cover` in the source
# with a justification rather than propped up by brittle stdlib monkeypatching.
# ---------------------------------------------------------------------------


def _stop_loop_without_closing_flag(adapter: AsyncBackendSyncAdapter) -> None:
    """Stop and close the adapter's private loop while leaving ``_closed`` False.

    Reproduces the TOCTOU window in the adapter's ``close()`` docstring: a
    caller that passes ``_guard()`` (closed flag still False, no running loop on
    its own thread) but then hits ``run_coroutine_threadsafe`` on a loop that
    has already stopped. Mirrors the setup of
    ``TestStreamingRead::test_close_race_stream_subsequent_read_returns_empty``.
    """
    loop = adapter._loop  # internal: no public observable for the private loop
    loop.call_soon_threadsafe(loop.stop)
    adapter._thread.join(timeout=5.0)  # internal: no public observable for the loop thread
    loop.close()


class TestSubmitCloseRace:
    """``_submit`` re-raises the canonical closed message on the close-race."""

    @pytest.mark.spec("ASYNC-083")
    def test_scalar_submit_close_race_raises_closed(self, recwarn: pytest.WarningsRecorder) -> None:
        adapter, _ = _make_memory_adapter()
        _stop_loop_without_closing_flag(adapter)

        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            adapter.exists("x")

        # The coroutine built before the guard must be closed on the race path,
        # otherwise CPython emits "coroutine was never awaited".
        gc.collect()
        leaks = [
            w for w in recwarn.list if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
        ]
        assert leaks == [], f"close-race leaked coroutine: {leaks[0].message if leaks else ''}"
        adapter.close()


class TestListingBridgeCloseRace:
    """``_AsyncIteratorBridge.__next__`` close-race raises closed, then stops."""

    @pytest.mark.spec("ASYNC-080", "ASYNC-083")
    def test_next_close_race_raises_then_stop_iteration(self) -> None:
        adapter, _ = _populated_adapter()
        bridge = adapter.list_files("")
        _stop_loop_without_closing_flag(adapter)

        with pytest.raises(RuntimeError, match="AsyncBackendSyncAdapter is closed"):
            next(bridge)
        # The race handler sets _done, so the iterator is exhausted afterwards.
        with pytest.raises(StopIteration):
            next(bridge)
        adapter.close()


class TestReadIntoDataPath:
    """``_ChunkPullReader.readinto`` fills caller buffers across pull + buffer."""

    def setup_method(self) -> None:
        self.adapter, _ = _make_memory_adapter()
        self.adapter.write("f.txt", b"hello world")

    def teardown_method(self) -> None:
        self.adapter.close()

    @pytest.mark.spec("ASYNC-081")
    def test_readinto_reconstructs_content_in_small_buffers(self) -> None:
        # 4-byte buffers force both the "pull a fresh chunk" and the
        # "serve the buffered remainder" branches, plus the EOF zero-return.
        out = bytearray()
        with self.adapter.read("f.txt") as stream:
            while True:
                buf = bytearray(4)
                n = stream.readinto(buf)
                if not n:
                    break
                out.extend(buf[:n])
        assert bytes(out) == b"hello world"

    @pytest.mark.spec("ASYNC-081")
    def test_readinto_zero_length_buffer_returns_zero(self) -> None:
        with self.adapter.read("f.txt") as stream:
            assert stream.readinto(bytearray(0)) == 0

    @pytest.mark.spec("ASYNC-081")
    def test_readinto_via_buffered_reader(self) -> None:
        # io.BufferedReader is the canonical consumer of RawIOBase.readinto.
        with self.adapter.read("f.txt") as raw:
            reader = io.BufferedReader(raw)
            assert reader.read() == b"hello world"


class TestStreamCloseEdges:
    """Stream ``close()`` is idempotent and swallows a raising ``aclose()``."""

    @pytest.mark.spec("ASYNC-081")
    def test_close_is_idempotent(self) -> None:
        adapter, _ = _make_memory_adapter()
        adapter.write("f.txt", b"data")
        stream = adapter.read("f.txt")
        stream.close()
        stream.close()  # second close hits the already-closed fast path
        assert stream.closed is True
        adapter.close()

    @pytest.mark.spec("ASYNC-081")
    def test_close_swallows_and_logs_aclose_error(self, caplog: pytest.LogCaptureFixture) -> None:
        class _AcloseRaisingBackend(AsyncMemoryBackend):
            async def read(self, path: str):  # type: ignore[override]
                try:
                    yield b"data"
                finally:
                    raise RuntimeError("aclose boom")

        adapter = AsyncBackendSyncAdapter(_AcloseRaisingBackend())
        adapter.write("f.txt", b"data")
        stream = adapter.read("f.txt")
        # Pull one byte so the generator is suspended at its yield; aclose()
        # then throws GeneratorExit into it and the finally raises.
        assert stream.read(1) == b"d"
        with caplog.at_level(logging.DEBUG, logger="remote_store._async_to_sync_adapter"):
            stream.close()  # must not raise even though aclose() does
        assert stream.closed is True
        assert any("stream aclose raised" in r.message for r in caplog.records)
        adapter.close()


class TestAcloseBestEffortFailure:
    """``_aclose_best_effort`` swallows a failed submit and closes the coroutine."""

    @pytest.mark.spec("ASYNC-080")
    def test_submit_failure_is_swallowed_and_coro_closed(self, recwarn: pytest.WarningsRecorder) -> None:
        # Drive the bridge at our own boundary with a degenerate loop whose
        # is_running() is True but which cannot accept a coroutine, so
        # run_coroutine_threadsafe raises and the handler must close the coro.
        class _FakeLoop:
            def is_running(self) -> bool:
                return True

        class _FakeAdapter:
            _loop = _FakeLoop()

        async def _gen():
            yield b"x"

        bridge = _AsyncIteratorBridge(_FakeAdapter(), _gen())  # type: ignore[arg-type]
        bridge._aclose_best_effort()  # must not raise

        gc.collect()
        leaks = [
            w for w in recwarn.list if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
        ]
        assert leaks == [], f"_aclose_best_effort leaked coroutine: {leaks[0].message if leaks else ''}"


class TestSpoolAndFlushReExit:
    """``_SpoolAndFlush.__exit__`` is a no-op once the spool is consumed."""

    @pytest.mark.spec("ASYNC-085")
    def test_second_exit_does_not_rewrite(self) -> None:
        adapter, _ = _make_memory_adapter()
        cm = adapter.open_atomic("out.txt")
        spool = cm.__enter__()
        spool.write(b"once")
        cm.__exit__(None, None, None)  # flushes spool -> backend, clears _spool
        cm.__exit__(None, None, None)  # _spool is None -> early return, no rewrite
        assert adapter.read_bytes("out.txt") == b"once"
        adapter.close()


class TestCloseDrainsPendingTasks:
    """``close()`` drains in-flight loop tasks before stopping the loop."""

    @pytest.mark.spec("ASYNC-088")
    def test_close_drains_quick_background_task(self) -> None:
        adapter, _ = _make_memory_adapter()
        done = threading.Event()

        async def _bg() -> None:
            await asyncio.sleep(0.1)
            done.set()

        # Schedule a task that is still pending when close() snapshots the loop,
        # so the drain loop runs _drain_tasks() and waits for it to finish.
        asyncio.run_coroutine_threadsafe(_bg(), adapter._loop)  # internal: private loop
        adapter.close(timeout=5.0)
        assert done.is_set(), "close() did not drain the pending background task"

    @pytest.mark.spec("ASYNC-088")
    def test_close_drain_timeout_logs_warning_with_hanging_task(self, caplog: pytest.LogCaptureFixture) -> None:
        adapter, _ = _make_memory_adapter()
        started = threading.Event()
        # Held by the test frame on purpose: it anchors the pending task's
        # reference chain (event -> waiter future -> task callback). With an
        # inline `asyncio.Event().wait()` the whole chain is an unreferenced
        # cycle — asyncio's task registry is a WeakSet, so a GC pass destroys
        # the pending task mid-test ("Task was destroyed but it is pending!"),
        # close() then sees a quiet loop, and the timeout warning never fires
        # (BUG-239: flaked on CI under xdist allocation pressure).
        release = asyncio.Event()

        async def _hang() -> None:
            started.set()
            await release.wait()  # never set -- hangs until reaped

        asyncio.run_coroutine_threadsafe(_hang(), adapter._loop)  # internal: private loop
        assert started.wait(timeout=2.0), "background task never started"
        gc.collect()  # deterministically exercise the GC pass that flaked on CI

        with caplog.at_level(logging.WARNING, logger="remote_store._async_to_sync_adapter"):
            adapter.close(timeout=0.2)

        matched = [r for r in caplog.records if "close timed out" in r.message]
        assert matched, "expected a close-timeout warning when the drain cannot finish"
        assert all(r.levelno == logging.WARNING for r in matched)

        # close() schedules loop.stop but its own join times out, leaving the
        # never-completing task on the loop. Reap the daemon thread so the loop
        # reaches its close() at a controlled point rather than deferring teardown
        # to GC / interpreter shutdown where it could leak across tests (BK-281).
        _reap_adapter(adapter)
