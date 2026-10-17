"""BE-033's interaction protocol on the kernel: one cell per transition, both runtimes.

The backend's close posture, the read stream's close, the write handle's exits
and the caller's content, each from the state BE-033's tables name, over the
fake driver. Each cell asserts the next state through what the fake records:
the calls that reached the wire, the handle's state, whether the caller's
iterator or stream was closed.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import pytest

from remote_store._errors import BackendUnavailable, CapabilityNotSupported, RemoteStoreError
from tests._kernel._fake import RUNTIMES, FakeDenied, FakeDown, FakeOdd, FakeStore, make_kernel

# write: put; the three write_atomic routes: atomic put, wire temporary, temp and rename.
_ROUTES = {
    "write": {"put_is_atomic": False},
    "write_atomic-put": {"put_is_atomic": True},
    "write_atomic-open_write": {"put_is_atomic": False},
    "write_atomic-rename": {"put_is_atomic": False, "protocols": ("remove_folder", "rename")},
}


def _store() -> FakeStore:
    return FakeStore().add("f", data=b"F")


def _write(run: Any, route: str, content: Any) -> Any:
    method = "write" if route == "write" else "write_atomic"
    return getattr(run, method)("g", content, overwrite=True)


# --- the backend: close posture (BE-020), repeated close, unwrap ----------------


@pytest.mark.spec("BE-033", "BE-022")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_unwrap_after_a_terminal_close_is_backend_unavailable(runtime: str) -> None:
    run = make_kernel(runtime, _store(), close_is_terminal=True)
    assert run.unwrap(FakeStore) is run.store
    run.close()
    with pytest.raises(BackendUnavailable):
        run.unwrap(FakeStore)
    # The closed guard outranks the driver's own refusal of the type.
    with pytest.raises(BackendUnavailable):
        run.unwrap(int)


@pytest.mark.spec("BE-033", "BE-022")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_unwrap_after_a_non_terminal_close_is_the_drivers_answer(runtime: str) -> None:
    run = make_kernel(runtime, _store(), close_is_terminal=False)
    run.close()
    assert run.unwrap(FakeStore) is run.store
    with pytest.raises(CapabilityNotSupported):
        run.unwrap(int)


@pytest.mark.spec("BE-033", "BE-020")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("terminal", [False, True], ids=["non-terminal", "terminal"])
def test_every_close_reaches_the_driver(runtime: str, terminal: bool) -> None:
    # Idempotence is the driver's duty; the kernel forwards every call (I2).
    run = make_kernel(runtime, _store(), close_is_terminal=terminal)
    run.close()
    run.close()
    assert run.store.called("close") == [("close", ""), ("close", "")]


@pytest.mark.spec("BE-033", "BE-020")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_non_terminal_backend_is_reused_between_closes(runtime: str) -> None:
    run = make_kernel(runtime, _store(), close_is_terminal=False)
    run.close()
    run.write("g", b"G")
    assert run.read("g") == b"G"
    run.close()
    assert len(run.store.called("close")) == 2


@pytest.mark.spec("BE-033", "BE-020")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_terminal_close_absorbs_every_later_operation(runtime: str) -> None:
    # I1: Closed is absorbing; only close itself stays callable.
    run = make_kernel(runtime, _store(), close_is_terminal=True)
    run.close()
    run.store.calls.clear()
    with pytest.raises(BackendUnavailable):
        run.write("g", b"G")
    with pytest.raises(BackendUnavailable):
        run.read("f")
    run.close()
    assert run.store.calls == [("close", "")]


# --- the read stream (SIO-010 in both runtimes) ----------------------------------


@pytest.mark.spec("BE-033", "SIO-010")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_stream_its_failure_condemned_is_not_closed_again(runtime: str) -> None:
    store = FakeStore().add("f", data=b"0123")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.fault("stream.read", FakeDown("dead"), key="f")  # connection_dead says yes
    with pytest.raises(BackendUnavailable):
        run.read("f")
    assert ("stream.close", "f") not in store.calls


@pytest.mark.spec("BE-033", "SIO-010")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_stream_whose_failure_left_the_connection_alive_is_closed(runtime: str) -> None:
    store = FakeStore().add("f", data=b"0123")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.fault("stream.read", FakeDenied("denied"), key="f")
    with pytest.raises(RemoteStoreError):
        run.read("f")
    assert store.called("stream.close") == [("stream.close", "f")]


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_stream_read_to_its_end_is_closed_once(runtime: str) -> None:
    store = FakeStore().add("f", data=b"01234")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    assert run.read("f") == b"01234"
    assert store.called("stream.close") == [("stream.close", "f")]


# --- the write handle: abort on every failure, a failed abort logged -------------


def _abort_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "remote_store._kernel" and r.levelno == logging.WARNING and "cleanup" in r.getMessage()
    ]


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("at", ["handle.write", "handle.commit"])
def test_a_failed_handle_write_is_aborted(runtime: str, at: str) -> None:
    store = _store()
    run = make_kernel(runtime, store)
    store.fault(at, FakeOdd("boom"))
    with pytest.raises(RemoteStoreError):
        run.write_atomic("g", b"G")
    assert [h.state for h in store.handles] == ["aborted"]  # type: ignore[attr-defined]
    assert "g" not in store.files


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("at", ["handle.write", "handle.commit"])
def test_a_cancelled_handle_write_is_aborted(runtime: str, at: str) -> None:
    store = _store()
    run = make_kernel(runtime, store)
    store.fault(at, asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        run.write_atomic("g", b"G")
    assert [h.state for h in store.handles] == ["aborted"]  # type: ignore[attr-defined]


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("dead", [True, False], ids=["dead", "alive"])
def test_a_failed_abort_is_logged_and_the_commit_error_raised(
    runtime: str, dead: bool, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store()
    run = make_kernel(runtime, store)
    commit_failure = FakeOdd("commit refused")
    store.fault("handle.commit", commit_failure)
    store.fault("handle.abort", FakeDown("gone") if dead else FakeDenied("no"))
    with caplog.at_level("WARNING", logger="remote_store._kernel"), pytest.raises(RemoteStoreError) as caught:
        run.write_atomic("g", b"G")
    assert caught.value.__cause__ is commit_failure  # the abort's failure never masks it
    (warning,) = _abort_warnings(caplog)
    assert "'g'" in warning
    assert f"connection dead: {dead}" in warning


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_a_failed_temporary_delete_is_logged_and_the_rename_error_raised(
    runtime: str, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store()
    run = make_kernel(runtime, store, **_ROUTES["write_atomic-rename"])
    rename_failure = FakeOdd("rename refused")
    store.fault("rename", rename_failure)
    store.fault("delete", FakeDown("gone"))
    with caplog.at_level("WARNING", logger="remote_store._kernel"), pytest.raises(RemoteStoreError) as caught:
        run.write_atomic("g", b"G")
    assert caught.value.__cause__ is rename_failure
    (warning,) = _abort_warnings(caplog)
    assert "connection dead: True" in warning


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("failure", ["body", "commit"])
def test_open_atomic_logs_a_failed_abort_and_raises_the_first_error(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store()
    run = make_kernel("sync", store)
    store.fault("handle.abort", FakeDown("gone"))
    if failure == "commit":
        store.fault("handle.commit", FakeOdd("commit refused"))
    first: type[BaseException] = ValueError if failure == "body" else RemoteStoreError
    with (  # noqa: PT012 - the body is the caller's code inside open_atomic
        caplog.at_level("WARNING", logger="remote_store._kernel"),
        pytest.raises(first),
        run.kernel.open_atomic("g", overwrite=True) as handle,
    ):
        handle.write(b"G")
        if failure == "body":
            raise ValueError("caller")
    (warning,) = _abort_warnings(caplog)
    assert "connection dead: True" in warning


# --- the caller's content --------------------------------------------------------


class _CallerChunks:
    """A caller's async iterator that is not a generator, recording its ``aclose``."""

    def __init__(self, *chunks: Any, has_aclose: bool = True) -> None:
        self._chunks = list(chunks)
        self.closed = False
        if not has_aclose:
            self.aclose = None  # type: ignore[assignment]

    def __aiter__(self) -> _CallerChunks:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:  # type: ignore[no-redef]
        self.closed = True


def _generator(log: list[str], *chunks: Any) -> Any:
    async def gen() -> Any:
        try:
            for chunk in chunks:
                yield chunk
        finally:
            log.append("finally")

    return gen()


# Each way the kernel stops consuming: (route, fault, expected error), chunks b"ab", b"cd", b"ef".
_ABANDONED = {
    "refusal-write": ("write", None, TypeError),
    "refusal-put": ("write_atomic-put", None, TypeError),
    "refusal-open_write": ("write_atomic-open_write", None, TypeError),
    "refusal-rename": ("write_atomic-rename", None, TypeError),
    "handle-failure": ("write_atomic-open_write", ("handle.write", FakeOdd("boom")), RemoteStoreError),
    "cancel": ("write_atomic-open_write", ("handle.write", asyncio.CancelledError()), asyncio.CancelledError),
    "open-refused": ("write_atomic-open_write", ("open_write", FakeOdd("boom")), RemoteStoreError),
}


def _abandon(case: str, content: Any) -> None:
    route, fault, expected = _ABANDONED[case]
    run = make_kernel("async", _store(), **_ROUTES[route])
    if fault is not None:
        run.store.fault(*fault)
    with pytest.raises(expected):
        _write(run, route, content)


@pytest.mark.spec("BE-033", "ASYNC-091")
@pytest.mark.parametrize("case", sorted(_ABANDONED))
def test_the_kernel_closes_a_caller_iterator_it_abandons(case: str) -> None:
    refused = case.startswith("refusal")
    content = _CallerChunks(b"ab", "text" if refused else b"cd", b"ef")
    _abandon(case, content)
    assert content.closed


@pytest.mark.spec("BE-033", "ASYNC-091")
@pytest.mark.parametrize("case", sorted(_ABANDONED))
def test_an_abandoned_caller_generator_is_finalised_before_the_call_returns(case: str) -> None:
    # Not at GC, on whatever loop is then current (BUG-335).
    log: list[str] = []
    refused = case.startswith("refusal")
    content = _generator(log, b"ab", "text" if refused else b"cd", b"ef")
    _abandon(case, content)
    assert content.ag_frame is None  # closed, not suspended
    started = case != "open-refused"  # a generator never started has no finally to run
    assert log == (["finally"] if started else [])


@pytest.mark.spec("BE-033", "ASYNC-091")
def test_a_caller_iterator_without_aclose_is_left_as_it_is() -> None:
    content = _CallerChunks(b"ab", "text", b"cd", has_aclose=False)
    _abandon("refusal-write", content)  # the refusal, not an AttributeError
    assert content._chunks == [b"cd"]  # left where the refusal stopped it


@pytest.mark.spec("BE-033", "ASYNC-091")
def test_a_failing_aclose_never_masks_the_refusal(caplog: pytest.LogCaptureFixture) -> None:
    class _BadClose(_CallerChunks):
        async def aclose(self) -> None:
            raise OSError("caller's close")

    with caplog.at_level("WARNING", logger="remote_store._kernel"):
        _abandon("refusal-write", _BadClose(b"ab", "text"))
    assert _abort_warnings(caplog)


@pytest.mark.spec("BE-033", "ASYNC-091")
@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_an_exhausted_caller_iterator_is_written_whole(route: str) -> None:
    run = make_kernel("async", _store(), **_ROUTES[route])
    content = _CallerChunks(b"ab", b"cd")
    _write(run, route, content)
    assert run.store.files["g"].data == b"abcd"


@pytest.mark.spec("BE-033", "ASYNC-091")
@pytest.mark.parametrize("route", sorted(_ROUTES))
@pytest.mark.parametrize("fails", [False, True], ids=["success", "failure"])
def test_the_kernel_never_closes_a_sync_caller_stream(route: str, fails: bool) -> None:
    # Sync content is the caller's stream: it may seek it or retry with it.
    run = make_kernel("sync", _store(), **_ROUTES[route])
    if fails:
        run.store.fault("put" if route != "write_atomic-open_write" else "handle.commit", FakeOdd("boom"))
    content = io.BytesIO(b"abcd")
    if fails:
        with pytest.raises(RemoteStoreError):
            _write(run, route, content)
    else:
        _write(run, route, content)
    assert not content.closed


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("runtime", RUNTIMES)
def test_cancel_inside_the_put_route_takes_the_failure_exit(runtime: str) -> None:
    store = _store()
    run = make_kernel(runtime, store, **_ROUTES["write_atomic-rename"])
    store.fault("rename", asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        run.write_atomic("g", b"G")
    assert sorted(store.files) == ["f"]  # the temporary removed, the target untouched
