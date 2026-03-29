"""Tests for Store.open_atomic() and Backend.open_atomic() — SAW-001 through SAW-015."""

from __future__ import annotations

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import AlreadyExists, CapabilityNotSupported, InvalidPath
from remote_store._store import Store
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

from .conftest import make_restricted_store

pytestmark = pytest.mark.os_sensitive


@pytest.fixture
def local_store(tmp_path: object) -> Store:
    return Store(LocalBackend(str(tmp_path)))


@pytest.fixture
def memory_store() -> Store:
    return Store(MemoryBackend())


class TestStoreOpenAtomicLocal:
    """SAW-001 through SAW-008: Store.open_atomic() with LocalBackend."""

    @pytest.mark.spec("SAW-002")
    def test_gates_on_capability(self) -> None:
        """open_atomic requires ATOMIC_WRITE capability."""
        store = make_restricted_store(exclude={Capability.ATOMIC_WRITE})
        with pytest.raises(CapabilityNotSupported), store.open_atomic("test.txt"):
            pass

    @pytest.mark.spec("SAW-003")
    @pytest.mark.parametrize(
        ("chunks", "expected"),
        [
            pytest.param([b"hello world"], b"hello world", id="single_write"),
            pytest.param([b"chunk1-", b"chunk2-", b"chunk3"], b"chunk1-chunk2-chunk3", id="multi_chunk"),
        ],
    )
    def test_success_path(self, local_store: Store, chunks: list[bytes], expected: bytes) -> None:
        with local_store.open_atomic("out.txt") as f:
            for chunk in chunks:
                f.write(chunk)
        assert local_store.read_bytes("out.txt") == expected

    @pytest.mark.spec("SAW-004")
    def test_exception_path_no_partial_file(self, local_store: Store) -> None:
        """On exception, target path is unchanged (no partial file)."""
        with pytest.raises(RuntimeError, match="deliberate"), local_store.open_atomic("fail.txt") as f:  # noqa: PT012
            f.write(b"partial data")
            raise RuntimeError("deliberate failure")
        assert local_store.exists("fail.txt") is False

    @pytest.mark.spec("SAW-004")
    def test_exception_path_preserves_existing(self, local_store: Store) -> None:
        """On exception, existing file at target path is unchanged."""
        local_store.write("existing.txt", b"original")
        with (  # noqa: PT012
            pytest.raises(RuntimeError, match="deliberate"),
            local_store.open_atomic("existing.txt", overwrite=True) as f,
        ):
            f.write(b"new data")
            raise RuntimeError("deliberate failure")
        assert local_store.read_bytes("existing.txt") == b"original"

    @pytest.mark.spec("SAW-006")
    def test_already_exists(self, local_store: Store) -> None:
        local_store.write("exists.txt", b"data")
        with pytest.raises(AlreadyExists), local_store.open_atomic("exists.txt"):
            pass

    @pytest.mark.spec("SAW-006")
    def test_overwrite_replaces(self, local_store: Store) -> None:
        local_store.write("replace.txt", b"old")
        with local_store.open_atomic("replace.txt", overwrite=True) as f:
            f.write(b"new")
        assert local_store.read_bytes("replace.txt") == b"new"

    @pytest.mark.spec("SAW-007")
    @pytest.mark.parametrize(
        "path",
        [
            pytest.param("", id="empty"),
            pytest.param(".", id="root"),
        ],
    )
    def test_invalid_path(self, local_store: Store, path: str) -> None:
        with pytest.raises(InvalidPath), local_store.open_atomic(path):
            pass

    @pytest.mark.spec("SAW-008")
    def test_local_creates_parent_dirs(self, local_store: Store) -> None:
        with local_store.open_atomic("deep/nested/file.txt") as f:
            f.write(b"nested")
        assert local_store.read_bytes("deep/nested/file.txt") == b"nested"

    @pytest.mark.spec("SAW-013")
    def test_yielded_file_supports_write_and_tell(self, local_store: Store) -> None:
        with local_store.open_atomic("tell.txt") as f:
            assert f.tell() == 0
            f.write(b"hello")
            assert f.tell() == 5


class TestStoreOpenAtomicMemory:
    """SAW-012: MemoryBackend open_atomic()."""

    @pytest.mark.spec("SAW-012")
    def test_success_path(self, memory_store: Store) -> None:
        with memory_store.open_atomic("out.txt") as f:
            f.write(b"memory data")
        assert memory_store.read_bytes("out.txt") == b"memory data"

    @pytest.mark.spec("SAW-004")
    def test_exception_path(self, memory_store: Store) -> None:
        with pytest.raises(RuntimeError, match="boom"), memory_store.open_atomic("fail.txt") as f:  # noqa: PT012
            f.write(b"partial")
            raise RuntimeError("boom")
        assert memory_store.exists("fail.txt") is False

    @pytest.mark.spec("SAW-006")
    @pytest.mark.parametrize(
        ("overwrite", "expect_error"),
        [
            pytest.param(False, True, id="already_exists"),
            pytest.param(True, False, id="overwrite"),
        ],
    )
    def test_exists_handling(self, memory_store: Store, overwrite: bool, expect_error: bool) -> None:
        memory_store.write("target.txt", b"old")
        if expect_error:
            with pytest.raises(AlreadyExists), memory_store.open_atomic("target.txt"):
                pass
        else:
            with memory_store.open_atomic("target.txt", overwrite=True) as f:
                f.write(b"new")
            assert memory_store.read_bytes("target.txt") == b"new"

    @pytest.mark.spec("SAW-007")
    def test_invalid_path_empty(self, memory_store: Store) -> None:
        with pytest.raises(InvalidPath), memory_store.open_atomic(""):
            pass


class TestObserveOpenAtomic:
    """SAW-014: ext.observe fires on_write hook after successful promotion."""

    @pytest.mark.spec("SAW-014")
    @pytest.mark.parametrize(
        "raise_error",
        [
            pytest.param(False, id="success"),
            pytest.param(True, id="failure"),
        ],
    )
    def test_on_write_fires(self, memory_store: Store, raise_error: bool) -> None:
        from remote_store.ext.observe import StoreEvent, observe

        events: list[StoreEvent] = []
        error_events: list[StoreEvent] = []
        observed = observe(
            memory_store,
            on_write=events.append,
            on_error=error_events.append,
        )
        if raise_error:
            with pytest.raises(RuntimeError, match="boom"), observed.open_atomic("fail.txt") as f:  # noqa: PT012
                f.write(b"fail")
                raise RuntimeError("boom")
            assert len(events) == 1
            assert events[0].error is not None
            assert len(error_events) == 1
        else:
            with observed.open_atomic("obs.txt") as f:
                f.write(b"observed")
            assert len(events) == 1
            assert events[0].operation == "open_atomic"
            assert events[0].path == "obs.txt"
            assert events[0].error is None
