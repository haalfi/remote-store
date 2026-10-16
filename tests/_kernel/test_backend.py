"""The sync-only layer of ``DriverBackend``: ``read_seekable`` and ``open_atomic``.

``AsyncBackend`` has neither member (RFC-0017 D6), so these cells run on the
sync kernel only.
"""

from __future__ import annotations

import io
import tempfile

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from tests._kernel._fake import FakeDenied, FakeDown, FakeStore, make_kernel


def _store() -> FakeStore:
    return FakeStore().add("f", data=b"0123456789").add("d/x")


@pytest.mark.spec("SEEK-001")
def test_read_seekable_uses_ranged_reads_when_the_driver_has_them() -> None:
    run = make_kernel("sync", _store(), protocols=("remove_folder", "range"))
    with run.kernel.read_seekable("f") as stream:
        assert stream.seekable()
        stream.seek(4)
        assert stream.read(3) == b"456"
        stream.seek(-2, io.SEEK_END)
        assert stream.read() == b"89"
    assert run.store.called("get") == []
    assert run.store.called("get_range")


@pytest.mark.spec("SEEK-001")
def test_reading_the_rest_of_a_ranged_stream_is_one_request() -> None:
    store = FakeStore().add("big", data=bytes(range(256)) * 200)  # 51200 bytes, over six 8 KiB chunks
    run = make_kernel("sync", store, protocols=("remove_folder", "range"))
    with run.kernel.read_seekable("big") as stream:
        stream.seek(100)
        assert stream.read() == store.files["big"].data[100:]
        assert stream.read() == b""
    assert store.called("get_range") == [("get_range", "big")]


@pytest.mark.spec("SEEK-001")
def test_a_short_range_answer_is_completed_not_truncated() -> None:
    store = FakeStore().add("big", data=bytes(range(256)) * 40)  # 10240 bytes
    store.range_cap = 4096  # the wire answers at most 4 KiB per range
    run = make_kernel("sync", store, protocols=("remove_folder", "range"))
    with run.kernel.read_seekable("big") as stream:
        assert stream.read() == store.files["big"].data
    assert len(store.called("get_range")) == 3


@pytest.mark.spec("SEEK-001")
def test_read_seekable_spools_over_read_without_ranged_reads() -> None:
    run = make_kernel("sync", _store(), protocols=("remove_folder",))
    with run.kernel.read_seekable("f") as stream:
        stream.seek(7)
        assert stream.read() == b"789"
    assert run.store.called("get") == [("get", "f")]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("protocols", [("remove_folder", "range"), ("remove_folder",)])
def test_read_seekable_answers_the_wrong_type_and_absence(protocols: tuple[str, ...]) -> None:
    run = make_kernel("sync", _store(), protocols=protocols)
    with pytest.raises(InvalidPath):
        run.kernel.read_seekable("d")
    with pytest.raises(NotFound):
        run.kernel.read_seekable("nope")
    with pytest.raises(InvalidPath):
        run.kernel.read_seekable("./")


@pytest.mark.spec("BE-021")
def test_a_ranged_read_error_is_mapped() -> None:
    run = make_kernel("sync", _store(), protocols=("remove_folder", "range"))
    run.store.fault("get_range", FakeDown("range lost"))
    with run.kernel.read_seekable("f") as stream, pytest.raises(BackendUnavailable, match="range lost"):
        stream.read(2)


@pytest.mark.spec("BE-010")
@pytest.mark.parametrize(
    ("protocols", "put_is_atomic"),
    [(("remove_folder", "open_write"), False), (("remove_folder",), True), (("remove_folder", "rename"), False)],
)
def test_open_atomic_promotes_on_success(protocols: tuple[str, ...], put_is_atomic: bool) -> None:
    protocols = (*protocols, "ensure_parents")  # an explicit-parents store creates "n"
    run = make_kernel("sync", FakeStore(), protocols=protocols, put_is_atomic=put_is_atomic)
    with run.kernel.open_atomic("n/a") as handle:
        handle.write(b"he")
        handle.write(b"llo")
    assert run.store.files["n/a"].data == b"hello"
    assert sorted(run.store.files) == ["n/a"]


_ROUTES = pytest.mark.parametrize(
    ("protocols", "put_is_atomic"),
    [(("remove_folder", "open_write"), False), (("remove_folder",), True), (("remove_folder", "rename"), False)],
    ids=["handle", "spool-put", "spool-rename"],
)


@pytest.mark.spec("SAW-013")
@_ROUTES
@pytest.mark.parametrize("bad", [3, [1, 2], "text"], ids=["int", "list", "str"])
def test_open_atomic_refuses_a_write_that_is_not_bytes(
    protocols: tuple[str, ...], put_is_atomic: bool, bad: object
) -> None:
    # bytes(3) is three NUL bytes: accepting it would commit garbage atomically.
    store = FakeStore().add("a", data=b"old")
    run = make_kernel("sync", store, protocols=protocols, put_is_atomic=put_is_atomic)

    def write_bad() -> None:
        with run.kernel.open_atomic("a", overwrite=True) as handle:
            handle.write(bad)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="bytes-like object is required"):
        write_bad()
    assert store.files["a"].data == b"old"


@pytest.mark.spec("SAW-013")
@_ROUTES
def test_open_atomic_refuses_a_write_after_close(protocols: tuple[str, ...], put_is_atomic: bool) -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel("sync", store, protocols=protocols, put_is_atomic=put_is_atomic)

    def write_after_close() -> None:
        with run.kernel.open_atomic("a", overwrite=True) as handle:
            handle.write(b"xy")
            handle.close()
            handle.write(b"z")

    with pytest.raises(ValueError, match="closed"):
        write_after_close()
    assert store.files["a"].data == b"old"


@pytest.mark.spec("BE-021", "ASYNC-091")
@pytest.mark.parametrize(
    ("protocols", "put_is_atomic"),
    [(("remove_folder",), True), (("remove_folder", "rename"), False)],
    ids=["spool-put", "spool-rename"],
)
def test_a_native_error_reading_the_kernels_own_spool_is_mapped(
    protocols: tuple[str, ...], put_is_atomic: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The spool is the kernel's, not the caller's content: its failure is a
    # native error like any other, and must not pass the choke point verbatim.
    run = make_kernel("sync", FakeStore(), protocols=protocols, put_is_atomic=put_is_atomic)

    def failing_read(self: object, *args: object) -> bytes:
        raise OSError(5, "EIO on the spilled spool")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "read", failing_read)

    def write() -> None:
        with run.kernel.open_atomic("k") as handle:
            handle.write(b"abc")

    with pytest.raises(RemoteStoreError, match="EIO on the spilled spool") as caught:
        write()
    assert caught.value.path == "k"
    assert "k" not in run.store.files


@pytest.mark.spec("SAW-013")
@_ROUTES
def test_open_atomic_tells_only_what_was_written(protocols: tuple[str, ...], put_is_atomic: bool) -> None:
    run = make_kernel("sync", FakeStore(), protocols=protocols, put_is_atomic=put_is_atomic)
    with run.kernel.open_atomic("t") as handle:
        assert handle.tell() == 0
        handle.write(bytearray(b"ab"))
        handle.write(memoryview(b"cde"))
        assert handle.tell() == 5
    assert run.store.files["t"].data == b"abcde"


@pytest.mark.spec("BE-010")
@pytest.mark.parametrize(
    ("protocols", "put_is_atomic"),
    [(("remove_folder", "open_write"), False), (("remove_folder",), True)],
)
def test_open_atomic_leaves_the_target_untouched_on_a_caller_error(
    protocols: tuple[str, ...], put_is_atomic: bool
) -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel("sync", store, protocols=protocols, put_is_atomic=put_is_atomic)

    def write_then_fail() -> None:
        with run.kernel.open_atomic("a", overwrite=True) as handle:
            handle.write(b"new")
            raise RuntimeError("caller")

    with pytest.raises(RuntimeError, match="caller"):
        write_then_fail()
    assert store.files["a"].data == b"old"
    assert [h.state for h in store.handles] in ([], ["aborted"])


@pytest.mark.spec("BE-010")
def test_open_atomic_refuses_an_existing_file_without_overwrite() -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel("sync", store, protocols=("remove_folder", "open_write"))
    with pytest.raises(AlreadyExists), run.kernel.open_atomic("a") as handle:
        handle.write(b"new")
    assert store.files["a"].data == b"old"
    assert [h.state for h in store.handles] == ["aborted"]


@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("spelling", ["", ".", "./", "/"])
def test_open_atomic_refuses_the_root_before_anything(spelling: str) -> None:
    run = make_kernel("sync", FakeStore(), protocols=("remove_folder", "open_write"))
    with pytest.raises(InvalidPath):
        run.kernel.open_atomic(spelling)
    assert run.store.calls == []


@pytest.mark.spec("BE-010")
@pytest.mark.parametrize(
    ("protocols", "put_is_atomic"),
    [(("remove_folder", "open_write"), False), (("remove_folder",), True), (("remove_folder", "rename"), False)],
)
def test_open_atomic_onto_a_folder_is_invalid_path_on_every_route(
    protocols: tuple[str, ...], put_is_atomic: bool
) -> None:
    store = FakeStore().add("d/x")
    run = make_kernel("sync", store, protocols=protocols, put_is_atomic=put_is_atomic)
    with pytest.raises(InvalidPath), run.kernel.open_atomic("d", overwrite=True) as handle:
        handle.write(b"new")
    assert sorted(store.files) == ["d/x"]


@pytest.mark.spec("SIO-010")
def test_a_stream_whose_failure_condemned_the_connection_is_not_closed_again() -> None:
    store = FakeStore().add("f", data=b"0123")
    run = make_kernel("sync", store, protocols=("remove_folder",))
    store.fault("stream.read", FakeDown("dead"), key="f")  # connection_dead says yes
    with pytest.raises(BackendUnavailable):
        run.read("f")
    assert ("stream.close", "f") not in store.calls
    store.faults.clear()
    store.fault("stream.read", FakeDenied("denied"), key="f")  # a failure a close survives
    with pytest.raises(PermissionDenied):
        run.read("f")
    assert ("stream.close", "f") in store.calls


SYNC_ONLY = {
    "read_seekable-range": (("remove_folder", "range"), lambda k, r: r.kernel.read_seekable(k)),
    "read_seekable-spool": (("remove_folder",), lambda k, r: r.kernel.read_seekable(k)),
    "open_atomic-handle": (("remove_folder", "open_write"), lambda k, r: r.kernel.open_atomic(k).__enter__()),
    "open_atomic-spool": (("remove_folder", "rename"), lambda k, r: _spool_and_exit(r, k)),
}
REFUSED = ["/", "/./", "/f", "d/../f", "..", "f\0", "d\\f", "\\"]


def _spool_and_exit(run: object, key: str) -> None:
    with run.kernel.open_atomic(key) as handle:  # type: ignore[attr-defined]
        handle.write(b"x")


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("key", REFUSED)
@pytest.mark.parametrize("member", sorted(SYNC_ONLY))
def test_a_refused_key_never_reaches_the_driver_on_the_sync_only_members(member: str, key: str) -> None:
    protocols, call = SYNC_ONLY[member]
    run = make_kernel("sync", _store(), protocols=protocols)
    run.store.calls.clear()
    with pytest.raises(InvalidPath):
        call(key, run)
    assert run.store.calls == []


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("key", ["f", "", "/f"])
@pytest.mark.parametrize("member", sorted(SYNC_ONLY))
def test_a_terminal_close_ranks_first_on_the_sync_only_members(member: str, key: str) -> None:
    protocols, call = SYNC_ONLY[member]
    run = make_kernel("sync", _store(), protocols=protocols, close_is_terminal=True)
    run.close()
    run.store.calls.clear()
    with pytest.raises(BackendUnavailable):
        call(key, run)
    assert run.store.calls == []


@pytest.mark.spec("BE-011")
@pytest.mark.parametrize("key", ["a", "", "/x"])
def test_open_atomic_without_a_route_is_capability_not_supported(key: str) -> None:
    # Ranked ahead of the closed guard and the key rule (BE-030), as glob's gate is.
    run = make_kernel("sync", FakeStore(), protocols=("remove_folder",), caps=(Capability.WRITE,))
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.kernel.open_atomic(key)
    run.close()
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.kernel.open_atomic(key)
