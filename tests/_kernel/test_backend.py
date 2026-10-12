"""The sync-only layer of ``DriverBackend``: ``read_seekable`` and ``open_atomic``.

``AsyncBackend`` has neither member (RFC-0017 D6), so these cells run on the
sync kernel only.
"""

from __future__ import annotations

import io

import pytest

from remote_store._capabilities import Capability
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    InvalidPath,
    NotFound,
    PermissionDenied,
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


@pytest.mark.spec("BE-011")
def test_open_atomic_without_a_route_is_capability_not_supported() -> None:
    run = make_kernel("sync", FakeStore(), protocols=("remove_folder",), caps=(Capability.WRITE,))
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.kernel.open_atomic("a")
