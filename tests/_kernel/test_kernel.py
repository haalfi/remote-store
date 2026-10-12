"""The contract kernel over a fake driver, in both runtimes.

Every test takes ``runtime`` and builds its kernel with ``make_kernel``, so
each cell runs against the hand-written async kernel and its generated sync
twin with one body. The fake's ``classify`` maps its native exceptions the
way a wire classifier does; every typed error asserted here is produced by
the kernel's choke point or its own rules.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

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
from remote_store._kernel._model import Op
from remote_store._models import _UNKNOWN_MODIFIED_AT
from remote_store._path import RemotePath
from tests._kernel._fake import (
    RUNTIMES,
    FakeContainerGone,
    FakeDenied,
    FakeDown,
    FakeMissing,
    FakeOdd,
    FakeStore,
    keys_of,
    make_kernel,
)

pytestmark = pytest.mark.parametrize("runtime", RUNTIMES)

ROOT_SPELLINGS = ["", ".", "./", ".//", "./."]
REFUSED = ["/", "/./", "/f", "d/../f", "..", "f\0", "d\\f", "\\"]


def _store() -> FakeStore:
    store = FakeStore()
    store.add("f", data=b"F")
    store.add("d/f", data=b"DF")
    return store


def _calls_reaching_the_wire(store: FakeStore) -> list[tuple[str, str]]:
    return list(store.calls)


# ---------------------------------------------------------------------------
# BE-030: the key rule, every key class against every member group
# ---------------------------------------------------------------------------

PROBES = ["exists", "is_file", "is_folder"]

FILE_SHAPED: dict[str, Any] = {
    "read": lambda r, k: r.read(k),
    "read_bytes": lambda r, k: r.read_bytes(k),
    "get_file_info": lambda r, k: r.get_file_info(k),
    "delete": lambda r, k: r.delete(k),
    "move-src": lambda r, k: r.move(k, "z"),
    "copy-src": lambda r, k: r.copy(k, "z"),
}
WRITE_SHAPED: dict[str, Any] = {
    "write": lambda r, k: r.write(k, b"new", overwrite=True),
    "write_atomic": lambda r, k: r.write_atomic(k, b"new", overwrite=True),
    "move-dst": lambda r, k: r.move("f", k, overwrite=True),
    "copy-dst": lambda r, k: r.copy("f", k, overwrite=True),
}
FOLDER_SHAPED: dict[str, Any] = {
    "list_files": lambda r, k: r.list_files(k),
    "list_folders": lambda r, k: r.list_folders(k),
    "iter_children": lambda r, k: r.iter_children(k),
    "get_folder_info": lambda r, k: r.get_folder_info(k),
}
EVERY_MEMBER: dict[str, Any] = {
    **{p: (lambda name: lambda r, k: getattr(r, name)(k))(p) for p in PROBES},
    **FILE_SHAPED,
    **WRITE_SHAPED,
    **FOLDER_SHAPED,
    "delete_folder": lambda r, k: r.delete_folder(k, recursive=True),
}


def _kernel(runtime: str, **kwargs: Any) -> Any:
    caps = (
        Capability.READ,
        Capability.WRITE,
        Capability.LIST,
        Capability.DELETE,
        Capability.MOVE,
        Capability.COPY,
        Capability.ATOMIC_WRITE,
    )
    return make_kernel(runtime, _store(), caps=caps, **kwargs)


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("key", REFUSED)
@pytest.mark.parametrize("member", sorted(EVERY_MEMBER))
def test_a_refused_key_is_invalid_on_every_member_and_never_reaches_the_driver(
    runtime: str, member: str, key: str
) -> None:
    run = _kernel(runtime)
    before = dict(run.store.files)
    with pytest.raises(InvalidPath) as caught:
        EVERY_MEMBER[member](run, key)
    assert caught.value.backend == "fake"
    assert caught.value.path in (key, "f")  # the refused end of a move/copy names itself
    assert _calls_reaching_the_wire(run.store) == []
    assert run.store.files == before


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("key", ROOT_SPELLINGS)
def test_the_root_probes_answer_from_the_key(runtime: str, key: str) -> None:
    run = _kernel(runtime)
    assert (run.exists(key), run.is_file(key), run.is_folder(key)) == (True, False, True)
    assert _calls_reaching_the_wire(run.store) == []


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("key", ROOT_SPELLINGS)
@pytest.mark.parametrize("member", sorted([*FILE_SHAPED, *WRITE_SHAPED, "delete_folder"]))
def test_the_root_is_refused_by_file_write_and_delete_folder_members_before_the_driver(
    runtime: str, member: str, key: str
) -> None:
    run = _kernel(runtime)
    before = dict(run.store.files)
    with pytest.raises(InvalidPath):
        EVERY_MEMBER[member](run, key)
    assert _calls_reaching_the_wire(run.store) == []
    assert run.store.files == before


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("key", ROOT_SPELLINGS)
def test_the_root_is_the_root_folder_for_folder_members(runtime: str, key: str) -> None:
    run = _kernel(runtime)
    assert keys_of(run.list_files(key)) == ["f"]
    assert keys_of(run.list_files(key, recursive=True)) == ["d/f", "f"]
    assert keys_of(run.list_folders(key)) == ["d"]
    assert keys_of(run.iter_children(key)) == ["d", "f"]
    info = run.get_folder_info(key)
    assert (info.path, info.file_count, info.total_size) == (RemotePath.ROOT, 2, 3)
    assert {key for _prim, key in run.store.calls} == {""}


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize(("key", "canonical"), [("d//f", "d/f"), ("d/./f", "d/f"), ("./d/f", "d/f"), ("d/f/", "d/f")])
def test_a_non_canonical_file_key_is_answered_as_its_canonical_key(runtime: str, key: str, canonical: str) -> None:
    run = _kernel(runtime)
    assert run.read(key) == b"DF"
    assert (run.exists(key), run.is_file(key)) == (True, True)
    assert str(run.get_file_info(key).path) == canonical
    assert str(run.write(key, b"new", overwrite=True).path) == canonical
    assert run.store.files[canonical].data == b"new"
    assert {k for _prim, k in run.store.calls} == {canonical}


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("key", ["d/", "d//", "./d", "d/."])
def test_a_non_canonical_folder_key_is_answered_as_its_canonical_key(runtime: str, key: str) -> None:
    run = _kernel(runtime)
    assert keys_of(run.list_files(key)) == ["d/f"]
    assert run.is_folder(key) is True
    assert str(run.get_folder_info(key).path) == "d"
    run.delete_folder(key, recursive=True)
    assert "d/f" not in run.store.files
    assert {k for _prim, k in run.store.calls} <= {"d", "d/f"}


# ---------------------------------------------------------------------------
# BE-030 / BE-025: addressing stays total and passes a refused key raw
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-025")
@pytest.mark.parametrize(
    ("key", "to_driver"),
    [
        ("", ""),
        (".", ""),
        ("./", ""),
        ("d//f", "d/f"),
        ("d/", "d"),
        ("f", "f"),
        ("d/../f", "d/../f"),
        ("f\0", "f\0"),
        ("d\\f", "d\\f"),
        ("/f", "/f"),
    ],
)
def test_addressing_normalises_a_valid_key_and_passes_a_refused_one_raw(runtime: str, key: str, to_driver: str) -> None:
    run = _kernel(runtime, close_is_terminal=True)
    run.close()  # BE-029's named carve-out: addressing answers after close
    assert run.native_path(key) == f"fake://{to_driver}"
    plan = run.resolve(key)
    assert (plan.key, plan.native_path) == (key, f"fake://{to_driver}")
    assert run.to_key("fake://d//f") == "d//f"  # forwarded unchanged


# ---------------------------------------------------------------------------
# BE-030 § glob: the pattern rule and its order
# ---------------------------------------------------------------------------


def _glob_kernel(runtime: str, **kwargs: Any) -> Any:
    store = FakeStore()
    store.add("d/a.csv", "d/b.txt", "top.csv")
    return make_kernel(
        runtime,
        store,
        caps=(Capability.READ, Capability.LIST, Capability.GLOB),
        **kwargs,
    )


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-024")
@pytest.mark.parametrize(
    ("pattern", "to_driver"),
    [
        ("d/*.csv", "d/*.csv"),
        ("./d/*.csv", "d/*.csv"),
        ("d//*.csv", "d/*.csv"),
        ("d/./*.csv", "d/*.csv"),
        ("d/*/", "d/*/"),
        ("d/*//", "d/*/"),
        ("./d/*/", "d/*/"),
        ("d//", "d/"),
        ("d/*/.", "d/*"),
    ],
)
def test_a_glob_pattern_is_normalised_segment_wise(runtime: str, pattern: str, to_driver: str) -> None:
    run = _glob_kernel(runtime)
    run.glob(pattern)
    assert run.store.called("glob") == [("glob", to_driver)]


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-024")
@pytest.mark.parametrize("pattern", ["", ".", "./", ".//"])
def test_a_root_pattern_yields_nothing_without_a_driver_call(runtime: str, pattern: str) -> None:
    run = _glob_kernel(runtime)
    assert run.glob(pattern) == []
    assert run.store.calls == []


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-024")
@pytest.mark.parametrize("pattern", ["/", "/./", "/d/*.csv", "*/../x", "d/*\0", "d\\*.csv"])
def test_a_refused_pattern_is_invalid_before_the_driver(runtime: str, pattern: str) -> None:
    run = _glob_kernel(runtime)
    with pytest.raises(InvalidPath):
        run.glob(pattern)
    assert run.store.calls == []


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-024")
def test_glob_matches_files_through_the_driver(runtime: str) -> None:
    run = _glob_kernel(runtime)
    assert keys_of(run.glob("d/*.csv")) == ["d/a.csv"]


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-024")
def test_glob_without_the_protocol_is_capability_not_supported_even_when_closed(runtime: str) -> None:
    store = FakeStore().add("d/a.csv")
    run = make_kernel(runtime, store, protocols=("remove_folder",), close_is_terminal=True)
    run.close()
    with pytest.raises(CapabilityNotSupported, match="glob"):
        run.glob("d/*.csv")


@pytest.mark.spec("BE-021")
def test_glob_maps_a_failure_raised_when_the_driver_is_called(runtime: str) -> None:
    run = _glob_kernel(runtime)
    run.store.fault("glob", FakeDenied("glob denied"))
    with pytest.raises(PermissionDenied, match="glob denied") as caught:
        run.glob("d/*.csv")
    assert (caught.value.path, caught.value.backend) == ("d/*.csv", "fake")
    run.store.faults.clear()
    run.store.container = False
    assert run.glob("d/*.csv") == []


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-020")
def test_glob_after_a_terminal_close_is_unavailable_before_the_pattern_rule(runtime: str) -> None:
    run = _glob_kernel(runtime, close_is_terminal=True)
    run.close()
    with pytest.raises(BackendUnavailable, match="closed"):
        run.glob("/refused")


# ---------------------------------------------------------------------------
# BE-030: a listing omits a stored key the rule would refuse or rewrite
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-030")
def test_a_listed_non_canonical_key_is_omitted_and_logged(runtime: str, caplog: pytest.LogCaptureFixture) -> None:
    store = FakeStore(parents="none")
    store.add("d/a", "d/b\\c", "d/x\\")
    store.files["d/\\"] = store.files["d/a"]
    store.files["d//e"] = store.files["d/a"]
    # The kernel's own aggregate: a native folder_stats owes the omission itself.
    run = make_kernel(runtime, store, protocols=("glob",))
    with caplog.at_level("WARNING", logger="remote_store._kernel"):
        assert keys_of(run.list_files("d")) == ["d/a"]
        assert keys_of(run.list_files("", recursive=True)) == ["d/a"]
        assert run.get_folder_info("d").file_count == 1
    omissions = [r.getMessage().split(": ", 1)[1] for r in caplog.records if "omitted" in r.getMessage()]
    # One record per listing: its count, and its first omitted key. The flat
    # listing of "d" sees "d//e" as a folder prefix, which list_files skips.
    assert [m.split(" that ")[0] + m.split("e.g.")[1] for m in omissions] == [
        "omitted 3 listed key(s) under 'd' 'd/\\\\'",
        "omitted 4 listed key(s) under '' 'd//e'",
        "omitted 4 listed key(s) under 'd' 'd//e'",
    ]


@pytest.mark.spec("BE-030")
def test_glob_folder_listings_and_iter_children_omit_a_non_canonical_key(
    runtime: str, caplog: pytest.LogCaptureFixture
) -> None:
    store = FakeStore()
    store.add("d/a.csv", "d/s/x")
    store.files["d/b\\c.csv"] = store.files["d/a.csv"]
    store.folders.add("d/t\\u")  # a folder another tool named with a backslash
    store.files["d/t\\u/y"] = store.files["d/a.csv"]
    run = make_kernel(runtime, store, caps=(Capability.READ, Capability.LIST, Capability.GLOB))
    with caplog.at_level("WARNING", logger="remote_store._kernel"):
        assert keys_of(run.glob("d/*.csv")) == ["d/a.csv"]
        assert keys_of(run.list_folders("d")) == ["d/s"]
        assert keys_of(run.iter_children("d")) == ["d/a.csv", "d/s"]
    omissions = [r.getMessage() for r in caplog.records if "omitted" in r.getMessage()]
    assert len(omissions) == 3
    assert "'d/b\\\\c.csv'" in omissions[0]
    assert "'d/t\\\\u'" in omissions[1]
    assert "omitted 2 listed key(s)" in omissions[2]


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("member", ["list_files", "list_folders", "iter_children", "glob"])
def test_a_listing_stopped_early_still_logs_what_it_omitted(
    runtime: str, member: str, caplog: pytest.LogCaptureFixture
) -> None:
    store = FakeStore()
    store.add("d/a.csv", "d/b/x")
    store.files["d/\\x.csv"] = store.files["d/a.csv"]  # sorts before d/a.csv
    store.folders.add("d/\\y")  # and before d/b
    run = make_kernel(runtime, store, caps=(Capability.READ, Capability.LIST, Capability.GLOB))
    arg = "d/*.csv" if member == "glob" else "d"
    listing = getattr(run.kernel, member)(arg)

    async def first_then_stop() -> None:
        await listing.__anext__()
        await listing.aclose()

    with caplog.at_level("WARNING", logger="remote_store._kernel"):
        if runtime == "sync":
            next(listing)
            listing.close()
        else:
            asyncio.run(first_then_stop())
    assert [r.getMessage() for r in caplog.records if "omitted 1 listed key(s)" in r.getMessage()]


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-031")
def test_a_recursive_delete_cannot_empty_a_folder_holding_an_omitted_key(runtime: str) -> None:
    store = FakeStore()
    store.add("d/a")
    store.files["d/b\\c"] = store.files["d/a"]
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    with pytest.raises(RemoteStoreError) as caught:
        run.delete_folder("d", recursive=True)
    assert type(caught.value).__name__ == "DirectoryNotEmpty"
    assert "d/b\\c" in store.files
    assert "d/a" not in store.files
    assert ("delete", "d/b\\c") not in store.calls


# ---------------------------------------------------------------------------
# BE-020: the close posture, ranked first
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-020")
@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("key", ["", "f", "d/../f"])
@pytest.mark.parametrize("member", sorted(EVERY_MEMBER))
def test_a_terminal_close_outranks_the_key_rule_and_the_root(runtime: str, member: str, key: str) -> None:
    run = _kernel(runtime, close_is_terminal=True)
    run.close()
    with pytest.raises(BackendUnavailable, match="closed") as caught:
        EVERY_MEMBER[member](run, key)
    assert caught.value.backend == "fake"
    assert [c for c in run.store.calls if c[0] != "close"] == []


@pytest.mark.spec("BE-020")
def test_a_non_terminal_close_leaves_the_kernel_usable(runtime: str) -> None:
    run = _kernel(runtime)
    run.close()
    assert run.read("f") == b"F"
    assert ("close", "") in run.store.calls


@pytest.mark.spec("BE-020")
def test_check_health_after_a_terminal_close_is_unavailable(runtime: str) -> None:
    run = _kernel(runtime, close_is_terminal=True)
    run.check_health()
    assert run.store.called("probe") == [("probe", "")]
    run.close()
    with pytest.raises(BackendUnavailable):
        run.check_health()


# ---------------------------------------------------------------------------
# ERR-001, ERR-009, BE-021: the choke point
# ---------------------------------------------------------------------------


@pytest.mark.spec("ERR-001")
@pytest.mark.spec("ERR-009")
def test_an_unrecognised_error_is_mapped_untyped_with_path_backend_and_a_message(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.fault("get", FakeOdd(""), key="f")
    with pytest.raises(RemoteStoreError) as caught:
        run.read_bytes("f")
    err = caught.value
    assert type(err) is RemoteStoreError
    assert (err.path, err.backend) == ("f", "fake")
    assert str(err.args[0]) == "FakeOdd during read_bytes"
    assert isinstance(err.__cause__, FakeOdd)


@pytest.mark.spec("ERR-001")
@pytest.mark.spec("BE-021")
def test_a_typed_error_from_the_driver_keeps_its_type_and_gains_path_and_backend(runtime: str) -> None:
    run = _kernel(runtime)
    raised = PermissionDenied("nope")
    run.store.fault("get", raised, key="f")
    with pytest.raises(PermissionDenied, match="nope") as caught:
        run.read_bytes("f")
    assert caught.value is raised
    assert (raised.path, raised.backend) == ("f", "fake")
    assert run.driver.classified == []  # never re-typed (BUG-293's shape)


@pytest.mark.spec("ERR-009")
def test_a_blank_typed_error_gets_a_message(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.fault("get", PermissionDenied(""), key="f")
    with pytest.raises(PermissionDenied, match="PermissionDenied during read_bytes"):
        run.read_bytes("f")


@pytest.mark.spec("ERR-001")
def test_an_iteration_end_raised_by_a_driver_call_is_mapped(runtime: str) -> None:
    # Only glob's own iteration step may end on it; anywhere else it is a native error.
    run = _kernel(runtime)
    end = StopIteration if runtime == "sync" else StopAsyncIteration
    run.store.fault("stat", end(), key="f")
    with pytest.raises(RemoteStoreError) as caught:
        run.get_file_info("f")
    assert (type(caught.value), caught.value.path) == (RemoteStoreError, "f")
    run.store.fault("list_page", end(), key="d")
    with pytest.raises(RemoteStoreError) as caught:
        run.list_files("d")
    assert (type(caught.value), caught.value.path) == (RemoteStoreError, "d")


@pytest.mark.spec("ERR-001")
@pytest.mark.spec("BE-021")
def test_a_typed_error_is_never_retyped_by_the_absent_container_predicate(runtime: str) -> None:
    run = _kernel(runtime)
    run.driver.container_absent = lambda exc, *, op: True
    raised = PermissionDenied("denied")
    run.store.fault("stat", raised, key="f")
    with pytest.raises(PermissionDenied) as caught:
        run.get_file_info("f")
    assert caught.value is raised


@pytest.mark.spec("BE-021")
def test_a_classifier_that_raises_never_leaks_its_own_error(runtime: str) -> None:
    run = _kernel(runtime)

    def broken(exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        raise KeyError("classifier bug")

    run.driver.classify = broken
    run.store.fault("stat", FakeOdd("boom"), key="f")
    with pytest.raises(RemoteStoreError, match="classify raised KeyError") as caught:
        run.get_file_info("f")
    assert type(caught.value) is RemoteStoreError
    assert isinstance(caught.value.__cause__, FakeOdd)


@pytest.mark.spec("BE-021")
def test_a_base_exception_passes_the_choke_point_untouched(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.fault("stat", KeyboardInterrupt(), key="f")
    with pytest.raises(KeyboardInterrupt):
        run.get_file_info("f")
    assert run.driver.classified == []


@pytest.mark.spec("BE-021")
def test_an_error_mid_stream_is_mapped(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.add("big", data=b"0123456789")
    run.store.fault("stream.read", FakeDown("dropped"), key="big", nth=2 if runtime == "async" else 1)
    with pytest.raises(BackendUnavailable, match="dropped") as caught:
        run.read("big")
    assert caught.value.path == "big"


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize(
    ("raised", "escapes"),
    [
        (ConnectionResetError("reset"), BackendUnavailable),  # an OSError: always caught
        (FakeDown("dropped"), PermissionDenied),  # outside the base set: only through stream_catch
    ],
)
def test_a_streams_caught_set_is_the_same_in_both_runtimes(
    runtime: str, raised: Exception, escapes: type[Exception]
) -> None:
    run = _kernel(runtime)
    run.driver.stream_catch = ()
    run.driver.classify = lambda exc, *, op, key: (
        BackendUnavailable(str(exc)) if isinstance(exc, OSError) else PermissionDenied(str(exc))
    )
    run.store.add("big", data=b"0123456789")
    run.store.fault("stream.read", raised, key="big", nth=2 if runtime == "async" else 1)
    if escapes is BackendUnavailable:
        with pytest.raises(BackendUnavailable, match="reset"):
            run.read("big")
    else:
        # The bound SIO-012 states: outside the caught set an exception
        # propagates unmapped, in both runtimes alike.
        with pytest.raises(FakeDown, match="dropped"):
            run.read("big")


@pytest.mark.spec("BE-021")
def test_an_error_on_a_later_page_is_mapped(runtime: str) -> None:
    store = FakeStore(page_size=1)
    store.add("d/a", "d/b", "d/c")
    run = make_kernel(runtime, store)
    store.fault("list_page", FakeDenied("page 2 denied"), key="d", nth=2)
    with pytest.raises(PermissionDenied, match="page 2 denied"):
        run.list_files("d")


@pytest.mark.spec("BE-021")
def test_a_listing_follows_the_cursor_across_pages(runtime: str) -> None:
    store = FakeStore(page_size=2)
    store.add("d/a", "d/b", "d/c", "d/e/f", "d/g/h")
    run = make_kernel(runtime, store)
    assert keys_of(run.list_files("d")) == ["d/a", "d/b", "d/c"]
    assert keys_of(run.list_folders("d")) == ["d/e", "d/g"]
    assert keys_of(run.list_files("d", recursive=True)) == ["d/a", "d/b", "d/c", "d/e/f", "d/g/h"]
    assert len(store.called("list_page")) > 3


# ---------------------------------------------------------------------------
# BE-021 § Reach: an absent container reads as an absent path, per operation
# ---------------------------------------------------------------------------


def _absent(runtime: str, parents: str = "explicit") -> Any:
    store = FakeStore(parents=parents)
    store.add("d/f")
    store.container = False
    return make_kernel(runtime, store)


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("parents", ["explicit", "none"])
def test_an_absent_container_answers_each_operation_as_an_absent_path(runtime: str, parents: str) -> None:
    run = _absent(runtime, parents)
    assert (run.exists("d/f"), run.is_file("d/f"), run.is_folder("d")) == (False, False, False)
    assert run.list_files("d") == []
    assert run.list_files("", recursive=True) == []
    assert run.list_folders("") == []
    assert run.iter_children("d") == []
    run.delete("d/f", missing_ok=True)
    run.delete_folder("d", recursive=True, missing_ok=True)
    run.delete_folder("d", missing_ok=True)
    assert run.glob("d/*") == []
    for call in (
        lambda: run.delete("d/f"),
        lambda: run.delete_folder("d", recursive=True),
        lambda: run.read_bytes("d/f"),
        lambda: run.get_file_info("d/f"),
        lambda: run.get_folder_info("d"),
        lambda: run.move("d/f", "e"),
        lambda: run.copy("d/f", "e"),
    ):
        with pytest.raises(NotFound):
            call()
    root = run.get_folder_info("")
    assert (root.file_count, root.total_size, root.modified_at) == (0, 0, None)


@pytest.mark.spec("BE-029")
@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("spelling", ["", ".", "./", ".//", "./.", "/"])
@pytest.mark.parametrize("member", sorted(WRITE_SHAPED))
def test_against_an_absent_container_the_root_is_refused_before_the_driver(
    runtime: str, member: str, spelling: str
) -> None:
    # ID-261's cell: the order BE-029 fixes (closed, root, driver) is observable
    # only where a present root cannot answer correctly by itself.
    run = _absent(runtime)
    with pytest.raises(InvalidPath):
        WRITE_SHAPED[member](run, spelling)
    assert run.store.calls == []


@pytest.mark.spec("BE-029")
@pytest.mark.spec("BE-020")
def test_against_an_absent_container_a_terminal_close_still_ranks_first(runtime: str) -> None:
    store = FakeStore()
    store.container = False
    run = make_kernel(runtime, store, close_is_terminal=True)
    run.close()
    with pytest.raises(BackendUnavailable, match="closed"):
        run.write("", b"x")
    with pytest.raises(BackendUnavailable, match="closed"):
        run.get_folder_info("")


@pytest.mark.spec("BE-021")
def test_an_absent_container_on_write_keeps_the_classifiers_answer(runtime: str) -> None:
    run = _absent(runtime)
    with pytest.raises(BackendUnavailable, match="container gone"):
        run.write("d/g", b"x")


@pytest.mark.spec("BE-021")
def test_the_first_page_bound_holds_across_the_operations_pages(runtime: str) -> None:
    store = FakeStore(page_size=1)
    store.add("d/a", "d/b", "d/c")
    run = make_kernel(runtime, store)
    store.fault("list_page", FakeContainerGone("deleted under the scan"), key="d", nth=2)
    with pytest.raises(NotFound):
        run.list_files("d", recursive=True)
    store.faults.clear()
    store.fault("list_page", FakeContainerGone("gone at the start"), key="d", nth=1)
    assert run.list_files("d", recursive=True) == []


# ---------------------------------------------------------------------------
# BE-021: wrong-type probes on the error path only
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("member", ["read", "read_bytes", "get_file_info", "delete", "move-src", "copy-src"])
def test_a_file_operation_on_a_folder_is_invalid_path(runtime: str, member: str) -> None:
    run = _kernel(runtime)
    with pytest.raises(InvalidPath, match="d"):
        FILE_SHAPED[member](run, "d")


@pytest.mark.spec("BE-021")
def test_type_mismatch_outranks_missing_ok(runtime: str) -> None:
    run = _kernel(runtime)
    with pytest.raises(InvalidPath):
        run.delete("d", missing_ok=True)


@pytest.mark.spec("BE-021")
def test_a_raising_wrong_type_probe_leaves_the_original_not_found(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.fault("stat", FakeDown("probe down"), key="zz")
    with pytest.raises(NotFound):
        run.read_bytes("zz")
    run.delete("zz", missing_ok=True)


@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-018")
def test_a_flat_driver_finds_a_prefix_folder_by_one_listing_probe(runtime: str) -> None:
    # A flat wire's stat is a HEAD: it cannot see the prefix "d", so the kernel
    # asks one list_page(limit=1) instead, as the flat classes do today (BK-324).
    store = FakeStore(parents="none").add("d/x", "f")
    run = make_kernel(runtime, store, namespace="flat", protocols=("copy",))
    for call in (
        lambda: run.read_bytes("d"),
        lambda: run.get_file_info("d"),
        lambda: run.delete("d", missing_ok=True),
        lambda: run.copy("d", "e"),
        lambda: run.move("d", "e"),
    ):
        with pytest.raises(InvalidPath):
            call()
    assert (run.exists("d"), run.is_folder("d"), run.is_file("d")) == (True, True, False)
    assert (run.exists("zz"), run.is_folder("zz")) == (False, False)
    assert sorted(store.files) == ["d/x", "f"]
    probes = [c for c in store.calls if c == ("list_page", "d")]
    assert probes  # the prefix was found by listing, never by stat
    store.calls.clear()
    assert run.read_bytes("f") == b"x"
    assert store.called("list_page") == []  # a hit spends no probe


@pytest.mark.spec("BE-008")
@pytest.mark.spec("BE-010")
@pytest.mark.parametrize("protocols", [("rename",), ("copy",), ("atomic_move",)])
def test_a_flat_destination_may_shadow_a_prefix(runtime: str, protocols: tuple[str, ...]) -> None:
    # BE-008's flat exemption: a flat namespace skips the type-conflict check,
    # so a write or move onto a key that shadows a prefix succeeds, on every route.
    store = FakeStore(parents="none").add("s", data=b"S").add("k/x", "p/y", "w/z")
    run = make_kernel(runtime, store, namespace="flat", protocols=protocols)
    run.move("s", "k")
    assert (store.files["k"].data, "k/x" in store.files) == (b"S", True)
    run.write("w", b"W")
    assert store.files["w"].data == b"W"
    if protocols == ("rename",):  # the temp-and-rename write_atomic route
        run.write_atomic("p", b"P")
        assert store.files["p"].data == b"P"
    assert sorted(k for k in store.files if "/" in k) == ["k/x", "p/y", "w/z"]


@pytest.mark.spec("BE-021")
def test_a_hit_spends_no_probe(runtime: str) -> None:
    run = _kernel(runtime)
    assert run.read_bytes("f") == b"F"
    assert run.store.called("stat") == []


# ---------------------------------------------------------------------------
# DEPTH-003 and BE-017
# ---------------------------------------------------------------------------


@pytest.mark.spec("DEPTH-003")
@pytest.mark.parametrize(
    ("max_depth", "expected"),
    [
        (None, ["d/a", "d/x/b", "d/x/y/c", "d/x/y/z/e"]),
        (0, ["d/a"]),
        (1, ["d/a", "d/x/b"]),
        (2, ["d/a", "d/x/b", "d/x/y/c"]),
    ],
)
def test_max_depth_bounds_a_recursive_listing(runtime: str, max_depth: int | None, expected: list[str]) -> None:
    store = FakeStore().add("d/a", "d/x/b", "d/x/y/c", "d/x/y/z/e")
    run = make_kernel(runtime, store)
    assert keys_of(run.list_files("d", recursive=True, max_depth=max_depth)) == expected
    assert keys_of(run.list_files("d", max_depth=max_depth)) == ["d/a"]


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("push_down", [False, True])
def test_an_empty_folders_info_fails_closed_on_a_driver_with_folder_objects(runtime: str, push_down: bool) -> None:
    # The stat after an empty aggregate is the determinant here, not an error-path probe.
    store = FakeStore().add("e/")
    protocols = ("remove_folder", "folder_stats") if push_down else ("remove_folder",)
    run = make_kernel(runtime, store, protocols=protocols)
    store.fault("stat", FakeDenied("stat denied"), key="e")
    with pytest.raises(PermissionDenied, match="stat denied"):
        run.get_folder_info("e")


@pytest.mark.spec("BE-017")
@pytest.mark.parametrize("push_down", [False, True])
def test_folder_modified_at_is_the_latest_known_time(runtime: str, push_down: bool) -> None:
    later = datetime(2026, 5, 1, tzinfo=UTC)
    store = FakeStore()
    store.add("d/a", modified_at=later - timedelta(days=1))
    store.add("d/s/b", modified_at=later)
    store.add("d/s/c", modified_at=_UNKNOWN_MODIFIED_AT)
    store.add("u/x", modified_at=_UNKNOWN_MODIFIED_AT)
    store.add("e/")
    protocols = ("remove_folder", "folder_stats") if push_down else ("remove_folder",)
    run = make_kernel(runtime, store, protocols=protocols)
    info = run.get_folder_info("d")
    assert (info.file_count, info.total_size, info.modified_at) == (3, 3, later)
    assert run.get_folder_info("u").modified_at is None
    empty = run.get_folder_info("e")
    assert (empty.file_count, empty.modified_at) == (0, None)
    with pytest.raises(InvalidPath):
        run.get_folder_info("d/a")
    with pytest.raises(NotFound):
        run.get_folder_info("nope")


# ---------------------------------------------------------------------------
# BE-029 / BE-008: writes, the root write spellings and the opt-in ancestor walk
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("spelling", ["", ".", "./", ".//", "./.", "/"])
@pytest.mark.parametrize("member", sorted(WRITE_SHAPED))
def test_every_root_write_spelling_is_refused_with_nothing_transferred(
    runtime: str, member: str, spelling: str
) -> None:
    run = _kernel(runtime)
    before = dict(run.store.files)
    with pytest.raises(InvalidPath):
        WRITE_SHAPED[member](run, spelling)
    assert run.store.files == before
    assert run.store.called("put") == run.store.called("rename") == run.store.called("move") == []


@pytest.mark.spec("BE-008")
def test_write_creates_explicit_parents_and_returns_the_canonical_path(runtime: str) -> None:
    run = _kernel(runtime)
    result = run.write("n/m/k", b"abc")
    assert (str(result.path), result.size) == ("n/m/k", 3)
    assert run.store.called("ensure_parents") == [("ensure_parents", "n/m/k")]
    assert run.store.files["n/m/k"].data == b"abc"


@pytest.mark.spec("BE-008")
@pytest.mark.parametrize("parents", ["explicit", "implicit"])
def test_a_write_under_a_file_is_invalid_path_on_a_hierarchical_driver(runtime: str, parents: str) -> None:
    # explicit carries ensure_parents (construction requires it); implicit never calls it.
    store = FakeStore(parents=parents).add("f", data=b"F").add("d/f", data=b"DF")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    with pytest.raises(InvalidPath):
        run.write("f/x", b"x")
    assert "f/x" not in run.store.files


@pytest.mark.spec("BE-008")
def test_write_refuses_an_existing_file_without_overwrite(runtime: str) -> None:
    run = _kernel(runtime)
    with pytest.raises(AlreadyExists):
        run.write("f", b"x")
    assert run.store.files["f"].data == b"F"


@pytest.mark.spec("BE-008")
def test_the_ancestor_walk_refuses_a_write_under_a_file(runtime: str) -> None:
    store = FakeStore(parents="none").add("a/b")
    run = make_kernel(runtime, store, reject_write_under_file_ancestor=True)
    with pytest.raises(InvalidPath, match="a/b"):
        run.write("a/b/c", b"x")
    assert store.called("put") == []
    run.write("a/z/c", b"x")
    assert "a/z/c" in store.files


@pytest.mark.spec("BE-008")
def test_the_ancestor_walk_propagates_a_probe_error_other_than_a_miss(runtime: str) -> None:
    store = FakeStore(parents="none").add("a/x")
    run = make_kernel(runtime, store, reject_write_under_file_ancestor=True)
    store.fault("stat", FakeDenied("denied probe"), key="a")
    with pytest.raises(PermissionDenied, match="denied probe"):
        run.write("a/b", b"x")
    assert store.called("put") == []


# ---------------------------------------------------------------------------
# BE-010: write_atomic's syntheses
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-010")
@pytest.mark.parametrize(
    ("protocols", "put_is_atomic", "path_taken"),
    [
        (("remove_folder",), True, "put"),
        (("remove_folder", "open_write"), False, "handle.commit"),
        (("remove_folder", "rename"), False, "rename"),
    ],
)
def test_write_atomic_takes_the_strongest_route_the_driver_presents(
    runtime: str, protocols: tuple[str, ...], put_is_atomic: bool, path_taken: str
) -> None:
    store = FakeStore()
    run = make_kernel(runtime, store, protocols=protocols, put_is_atomic=put_is_atomic)
    result = run.write_atomic("a", b"hello")
    assert (str(result.path), result.size) == ("a", 5)
    assert store.files["a"].data == b"hello"
    assert store.called(path_taken)
    assert sorted(store.files) == ["a"]  # no temporary left behind


@pytest.mark.spec("BE-011")
@pytest.mark.spec("BE-024")
def test_an_undeclared_capability_is_refused_though_the_driver_could(runtime: str) -> None:
    # The declared capabilities decide (BE-011, BE-024), not the protocols behind them.
    store = FakeStore().add("d/a.csv")
    caps = (Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE)
    run = make_kernel(runtime, store, protocols=("remove_folder", "glob", "open_write"), caps=caps)
    with pytest.raises(CapabilityNotSupported, match="glob"):
        run.glob("d/*.csv")
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.write_atomic("b", b"x")
    assert run.store.calls == []


@pytest.mark.spec("BE-030")
@pytest.mark.spec("BE-011")
@pytest.mark.parametrize("key", ["a", "", "/x", "d/../x"])
def test_an_undeclared_atomic_write_outranks_the_closed_guard_and_the_key_rule(runtime: str, key: str) -> None:
    # Capability data is not a live operation: refused first, as glob's is.
    run = make_kernel(runtime, FakeStore(), protocols=("remove_folder",), close_is_terminal=True)
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.write_atomic(key, b"x")
    run.close()
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.write_atomic(key, b"x")
    assert [c for c in run.store.calls if c[0] != "close"] == []


@pytest.mark.spec("WR-010")
@pytest.mark.parametrize("member", ["write", "write_atomic"])
def test_metadata_without_user_metadata_is_refused_before_any_io(runtime: str, member: str) -> None:
    caps = (Capability.READ, Capability.WRITE, Capability.LIST, Capability.DELETE, Capability.ATOMIC_WRITE)
    run = make_kernel(runtime, FakeStore(), protocols=("remove_folder", "open_write"), caps=caps)
    with pytest.raises(CapabilityNotSupported, match="metadata"):
        getattr(run, member)("a", b"x", metadata={"k": "v"})
    assert run.store.calls == []
    getattr(run, member)("b", b"x", metadata={})  # the empty-mapping carve-out
    assert "b" in run.store.files


@pytest.mark.spec("BE-011")
def test_write_atomic_without_a_route_is_capability_not_supported(runtime: str) -> None:
    run = make_kernel(runtime, FakeStore(), protocols=("remove_folder",))
    with pytest.raises(CapabilityNotSupported, match="atomic"):
        run.write_atomic("a", b"x")
    assert run.store.calls == []


@pytest.mark.spec("BE-010")
def test_a_failed_promote_removes_the_temporary_and_keeps_the_target(runtime: str) -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"))
    store.fault("rename", FakeDown("promote lost"))
    with pytest.raises(BackendUnavailable, match="promote lost"):
        run.write_atomic("a", b"new", overwrite=True)
    assert sorted(store.files) == ["a"]
    assert store.files["a"].data == b"old"


@pytest.mark.spec("BE-010")
def test_a_failed_commit_aborts_the_wire_temporary(runtime: str) -> None:
    store = FakeStore()
    run = make_kernel(runtime, store, protocols=("remove_folder", "open_write"))
    store.fault("handle.commit", FakeDown("commit lost"))
    with pytest.raises(BackendUnavailable, match="commit lost"):
        run.write_atomic("a", b"new")
    assert [h.state for h in store.handles] == ["aborted"]
    assert "a" not in store.files


@pytest.mark.spec("BE-010")
def test_a_failed_put_of_the_temporary_removes_it(runtime: str) -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"))
    store.fault("put", FakeDown("upload lost"))
    with pytest.raises(BackendUnavailable, match="upload lost") as caught:
        run.write_atomic("a", b"new", overwrite=True)
    assert caught.value.path == "a"  # the caller's key, never the hidden temporary
    (temp,) = [k for p, k in store.calls if p == "put"]
    assert ("delete", temp) in store.calls  # a wire may leave a partial temporary
    assert store.files["a"].data == b"old"


@pytest.mark.spec("BE-010")
def test_write_atomic_by_rename_never_replaces_a_file_written_after_its_check(runtime: str) -> None:
    store = FakeStore()
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"))
    store.fault("rename", hook=lambda: store.add("a", data=b"theirs"))
    with pytest.raises(AlreadyExists):
        run.write_atomic("a", b"mine")
    assert store.files["a"].data == b"theirs"
    assert sorted(store.files) == ["a"]  # the temporary removed


@pytest.mark.spec("BE-010")
def test_write_atomic_by_rename_refuses_a_folder_target_and_removes_the_temporary(runtime: str) -> None:
    store = FakeStore().add("d/x")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"))
    with pytest.raises(InvalidPath):
        run.write_atomic("d", b"new", overwrite=True)
    assert sorted(store.files) == ["d/x"]
    assert run.is_folder("d") is True


@pytest.mark.spec("BE-018")
def test_a_rename_move_stats_its_source_once(runtime: str) -> None:
    store = FakeStore().add("s")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename", "ensure_parents"))
    run.move("s", "n/t")
    assert store.called("stat") == [("stat", "s"), ("stat", "n/t")]


@pytest.mark.spec("BE-010")
def test_write_atomic_by_rename_refuses_an_existing_file_without_overwrite(runtime: str) -> None:
    store = FakeStore().add("a", data=b"old")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"))
    with pytest.raises(AlreadyExists):
        run.write_atomic("a", b"new")
    assert store.called("put") == []


# ---------------------------------------------------------------------------
# BE-018 / BE-019: move and copy
# ---------------------------------------------------------------------------


@pytest.mark.spec("BE-018")
@pytest.mark.parametrize(
    ("protocols", "rename_replaces", "wire"),
    [
        (("remove_folder", "atomic_move"), True, ["move"]),
        (("remove_folder", "rename"), True, ["rename"]),
        (("remove_folder", "rename"), False, ["rename", "rename", "delete"]),
        (("remove_folder", "copy"), True, ["copy", "delete"]),
    ],
)
def test_move_over_an_existing_file_by_each_route(
    runtime: str, protocols: tuple[str, ...], rename_replaces: bool, wire: list[str]
) -> None:
    store = FakeStore().add("s", data=b"S").add("t", data=b"T")
    run = make_kernel(runtime, store, protocols=protocols, rename_replaces=rename_replaces)
    run.move("s", "t", overwrite=True)
    assert sorted(store.files) == ["t"]
    assert store.files["t"].data == b"S"
    mutating = [p for p, _k in store.calls if p in ("move", "rename", "copy", "delete")]
    assert mutating == wire


@pytest.mark.spec("BE-018")
def test_a_failed_restore_is_logged_with_where_the_old_file_lies(
    runtime: str, caplog: pytest.LogCaptureFixture
) -> None:
    store = FakeStore().add("s", data=b"S").add("t", data=b"T")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"), rename_replaces=False)
    store.fault("rename", FakeDown("move lost"), nth=2)  # the move itself
    # The restore: a fault counts only the calls that reach it, and the raise
    # on the move stopped the scan before this one, so it is its second.
    store.fault("rename", FakeDown("restore lost"), nth=2)
    with caplog.at_level("WARNING", logger="remote_store._kernel"), pytest.raises(BackendUnavailable):
        run.move("s", "t", overwrite=True)
    (parked,) = [k for k in store.files if k not in ("s", "t")]
    assert store.files[parked].data == b"T"
    assert any(repr(parked) in r.getMessage() and "'t'" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.parametrize(
    ("member", "protocols"),
    [("move", "atomic_move"), ("move", "copy"), ("move", "rename"), ("copy", "copy")],
)
def test_a_destination_refusal_names_the_destination(runtime: str, member: str, protocols: str) -> None:
    store = FakeStore().add("s", data=b"S").add("t", data=b"T").add("dir/x")
    caps = (Capability.READ, Capability.WRITE, Capability.COPY, Capability.MOVE) if protocols == "copy" else ()
    run = make_kernel(runtime, store, protocols=("remove_folder", protocols), caps=caps)
    with pytest.raises(AlreadyExists) as exists:
        getattr(run, member)("s", "t")
    assert exists.value.path == "t"
    with pytest.raises(InvalidPath) as folder:
        getattr(run, member)("s", "dir", overwrite=True)
    assert folder.value.path == "dir"
    with pytest.raises(InvalidPath) as under_file:  # BE-018's third InvalidPath: a file ancestor
        getattr(run, member)("s", "t/b", overwrite=True)
    assert under_file.value.path == "t/b"
    assert (store.files["s"].data, store.files["t"].data) == (b"S", b"T")
    assert sorted(store.files) == ["dir/x", "s", "t"]


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-011")
def test_a_refused_move_or_atomic_write_creates_no_destination_parents(runtime: str) -> None:
    store = FakeStore().add("src")
    run = make_kernel(runtime, store, protocols=("remove_folder", "ensure_parents"))
    with pytest.raises(CapabilityNotSupported):
        run.move("src", "a/b/c")
    with pytest.raises(CapabilityNotSupported):
        run.write_atomic("x/y/z", b"data")
    assert store.called("ensure_parents") == []
    assert sorted(store.folders) == []


@pytest.mark.spec("BE-018")
def test_displace_and_restore_puts_the_old_file_back_when_the_move_fails(runtime: str) -> None:
    store = FakeStore().add("s", data=b"S").add("t", data=b"T")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"), rename_replaces=False)
    store.fault("rename", FakeDown("lost"), key="s")
    with pytest.raises(BackendUnavailable, match="lost"):
        run.move("s", "t", overwrite=True)
    assert sorted(store.files) == ["s", "t"]
    assert (store.files["s"].data, store.files["t"].data) == (b"S", b"T")


@pytest.mark.spec("BE-018")
@pytest.mark.parametrize("rename_replaces", [True, False])
def test_a_rename_move_with_overwrite_replaces_what_its_check_missed(runtime: str, rename_replaces: bool) -> None:
    # overwrite=True never answers AlreadyExists: not for a file written after the
    # destination check, nor for a check whose stat answered NotFound. A rename
    # that cannot replace displaces the missed file as it would a seen one.
    store = FakeStore(parents="implicit").add("s", data=b"S")
    run = make_kernel(runtime, store, protocols=("remove_folder", "rename"), rename_replaces=rename_replaces)
    store.fault("rename", hook=lambda: store.add("t", data=b"OTHER"), key="s")
    run.move("s", "t", overwrite=True)
    assert (store.files["t"].data, "s" in store.files) == (b"S", False)
    store.add("s2", data=b"S2")
    store.fault("stat", FakeMissing("lost"), key="t")
    run.move("s2", "t", overwrite=True)
    assert (store.files["t"].data, "s2" in store.files) == (b"S2", False)
    assert sorted(store.files) == ["t"]  # nothing parked left behind


@pytest.mark.spec("BE-021")
@pytest.mark.spec("BE-030")
def test_a_write_target_probe_stops_once_the_answer_is_known(runtime: str) -> None:
    # A file at the key rules out a file above it; an absent ancestor rules out
    # every deeper one. Either ends the ancestor probes (BE-021's error-path cost).
    store = FakeStore(parents="implicit").add("a/b/c/d/e")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.calls.clear()
    with pytest.raises(AlreadyExists):
        run.write("a/b/c/d/e", b"N")
    assert store.called("stat") == [("stat", "a/b/c/d/e")]
    store.fault("put", FakeDenied("denied"), key="x/y/z")
    store.calls.clear()
    with pytest.raises(PermissionDenied):
        run.write("x/y/z", b"N")
    assert store.called("stat") == [("stat", "x/y/z"), ("stat", "x")]


@pytest.mark.spec("BE-018")
@pytest.mark.parametrize("protocols", [("remove_folder", "atomic_move"), ("remove_folder", "rename")])
def test_move_onto_an_existing_file_without_overwrite_is_already_exists(
    runtime: str, protocols: tuple[str, ...]
) -> None:
    store = FakeStore().add("s", data=b"S").add("t", data=b"T")
    run = make_kernel(runtime, store, protocols=protocols)
    with pytest.raises(AlreadyExists):
        run.move("s", "t")
    assert (store.files["s"].data, store.files["t"].data) == (b"S", b"T")


@pytest.mark.spec("BE-018")
@pytest.mark.parametrize("protocols", [("remove_folder", "atomic_move"), ("remove_folder", "rename")])
def test_move_onto_a_folder_is_invalid_path(runtime: str, protocols: tuple[str, ...]) -> None:
    store = FakeStore().add("s").add("t/x")
    run = make_kernel(runtime, store, protocols=protocols)
    with pytest.raises(InvalidPath, match="t"):
        run.move("s", "t", overwrite=True)
    assert "s" in store.files


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.parametrize("member", ["move", "copy"])
def test_the_root_destination_outranks_a_missing_source(runtime: str, member: str) -> None:
    run = _kernel(runtime)
    with pytest.raises(InvalidPath) as caught:
        getattr(run, member)("missing", "./")
    assert caught.value.path == "./"
    with pytest.raises(InvalidPath) as caught:
        getattr(run, member)("", "missing")
    assert caught.value.path == ""


@pytest.mark.spec("BE-018")
@pytest.mark.spec("BE-019")
@pytest.mark.parametrize("member", ["move", "copy"])
def test_a_self_operation_is_decided_on_canonical_keys(runtime: str, member: str) -> None:
    run = _kernel(runtime)
    getattr(run, member)("d/f", "d//f")
    assert run.store.files["d/f"].data == b"DF"
    with pytest.raises(InvalidPath):
        getattr(run, member)("d", "d/")
    with pytest.raises(NotFound):
        getattr(run, member)("zz", "./zz")


@pytest.mark.spec("BE-018")
def test_a_missing_source_creates_no_destination_parents(runtime: str) -> None:
    run = _kernel(runtime)
    with pytest.raises(NotFound):
        run.move("missing", "new/dir/t")
    assert run.store.called("ensure_parents") == []
    assert "new" not in run.store.folders


@pytest.mark.spec("BE-019")
def test_copy_without_the_protocol_is_capability_not_supported(runtime: str) -> None:
    run = make_kernel(runtime, _store(), protocols=("remove_folder",))
    with pytest.raises(CapabilityNotSupported, match="copy"):
        run.copy("f", "g")
    with pytest.raises(CapabilityNotSupported, match="move"):
        run.move("f", "g")


@pytest.mark.spec("BE-019")
def test_copy_keeps_the_source_and_its_bytes(runtime: str) -> None:
    run = _kernel(runtime)
    run.copy("d/f", "e/g")
    assert (run.store.files["d/f"].data, run.store.files["e/g"].data) == (b"DF", b"DF")


# ---------------------------------------------------------------------------
# PING-002, and construction (RFC-0017 D1)
# ---------------------------------------------------------------------------


@pytest.mark.spec("PING-002")
def test_check_health_runs_the_drivers_probe_through_the_choke_point(runtime: str) -> None:
    run = _kernel(runtime)
    run.store.fault("probe", FakeDown("unreachable"))
    with pytest.raises(BackendUnavailable, match="unreachable"):
        run.check_health()
    assert run.driver.classified == [("FakeDown", Op.PROBE, "")]


@pytest.mark.spec("BE-031")
def test_a_driver_with_folder_objects_and_no_remove_folder_is_refused(runtime: str) -> None:
    with pytest.raises(ValueError, match="remove_folder"):
        make_kernel(runtime, FakeStore(parents="implicit"), protocols=("delete_tree",))


@pytest.mark.spec("BE-020")
@pytest.mark.parametrize("terminal", [True, False])
def test_the_class_close_posture_must_be_the_drivers(runtime: str, terminal: bool) -> None:
    run = _kernel(runtime, close_is_terminal=terminal)
    assert run.kernel.close_is_terminal is terminal  # what the conformance lanes read
    base = type(run.kernel).__mro__[1]  # DriverBackend / AsyncDriverBackend, ClassVar False
    if terminal:
        with pytest.raises(ValueError, match="close_is_terminal"):
            base(run.driver)
    else:
        assert base(run.driver).close_is_terminal is False


@pytest.mark.spec("BE-003")
@pytest.mark.parametrize(
    ("caps", "protocols", "message"),
    [
        ((Capability.MOVE,), ("remove_folder",), "MOVE"),
        ((Capability.GLOB,), ("remove_folder",), "GLOB"),
        ((Capability.COPY,), ("remove_folder",), "COPY"),
        ((Capability.ATOMIC_MOVE,), ("remove_folder", "copy"), "ATOMIC_MOVE"),
        ((Capability.ATOMIC_WRITE,), ("remove_folder",), "ATOMIC_WRITE"),
    ],
)
def test_a_declared_capability_the_protocols_cannot_back_is_refused(
    runtime: str, caps: tuple[Capability, ...], protocols: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make_kernel(runtime, FakeStore(), caps=caps, protocols=protocols)


@pytest.mark.spec("BE-002")
def test_name_capabilities_and_unwrap_are_the_drivers(runtime: str) -> None:
    run = _kernel(runtime)
    assert run.kernel.name == "fake"
    assert run.kernel.capabilities.supports(Capability.COPY)
    assert run.unwrap(FakeStore) is run.store
