"""The kernel against the compiled BE-033 model, over an enumerated set of the protocol's exits.

``sdd/formal/KernelProtocol-py/`` is ``KernelProtocol.dfy`` compiled by Dafny,
so ``KernelExit`` and ``KernelStep`` here are the verified functions whose
lemmas are BE-033's invariants, not a transcription of them. Each cell drives
the kernel over the fake driver to one exit, maps what the fake recorded onto
the model's datatypes, and requires the state the kernel left to equal the
state the model computes from the state at the exit. Nothing is sampled: the
cells are the products the case builders below enumerate, and every call
sequence up to ``_DEPTH`` calls, per runtime and close posture. Which exits
they leave out is spec 003 BE-033's "The model is the oracle".

**The mapping is what a pass is worth**, so it is stated here once:

- ``before`` is taken at the exit itself, by a hook on the fake's fault point
  (or, for a refused chunk, by the caller's iterator as it hands the chunk
  over). A gate refusal has no exit point: nothing is open and the iterator is
  unstarted, which is what "refused before the kernel takes it" means.
- A write handle is ``HOpen`` if any ``_Handle`` the fake recorded is still
  open, else the last one's ``committed`` or ``aborted`` (``HCommitted``,
  ``HAborted``); no handle is ``HNone``.
- The caller's async iterator is closed (``aclose`` called), exhausted (it
  raised ``StopAsyncIteration``), suspended (it handed out a chunk and was
  neither) or unstarted. ``closable`` is whether it has ``aclose``.
- A read stream is closed when the fake logged its explicit close, else
  released: the model's ``SReleased``, so a stream the kernel forgot to close
  reads as released and fails every cell whose model answer is ``SClosed``.
  A sync stream's exit is its caller's close: the kernel hands it over open,
  and the wrapper it returns closes or releases the inner stream then.
  ``read_bytes`` drains its stream and closes or releases it before it returns,
  in both runtimes.
- A write opens no stream, so its stream is ``SClosed`` throughout.

**Bounds.** The sync runtime's content is a caller stream with no state in the
model (BE-033: it stays the caller's), so its cells compare the stream and the
handle and leave the iterator out; ``test_protocol.py`` pins that the stream is
never closed. A ``Session``, and the driver duties BE-033 states, are outside
the model and outside this suite.
"""

from __future__ import annotations

import asyncio
import io
import itertools
import sys
from pathlib import Path
from typing import Any

import pytest

from remote_store._errors import BackendUnavailable, InvalidPath, RemoteStoreError
from tests._kernel._fake import RUNTIMES, FakeDown, FakeOdd, FakeStore, _AsyncBase, make_kernel, run_async

# Imported without leaving a trace a later import could find. The directory holds
# Dafny's stub `module_.py`, and `KernelProtocol.py` runs `import module_` (and never uses
# it): left on sys.path or in sys.modules, that stub shadows MemoryBackend-py's `module_`
# for every later import in the process. The runtime (`_dafny`, `System_`) stays cached,
# byte-identical to the other oracle's under the one Dafny pin.
_ORACLE_DIR = str(Path(__file__).resolve().parents[2] / "sdd" / "formal" / "KernelProtocol-py")
_prior_module_ = sys.modules.get("module_")
sys.path.insert(0, _ORACLE_DIR)
try:
    import KernelProtocol as KP
finally:
    sys.path.remove(_ORACLE_DIR)
    if _prior_module_ is None:
        sys.modules.pop("module_", None)
    else:
        sys.modules["module_"] = _prior_module_

_MODEL = KP.default__


@pytest.mark.spec("BE-033")
def test_importing_the_oracle_leaves_no_stub_for_a_later_import() -> None:
    # Before this guard, MemoryBackend-py's oracle failed to import when this module was collected first.
    assert _ORACLE_DIR not in sys.path
    assert _ORACLE_DIR not in str(getattr(sys.modules.get("module_"), "__file__", ""))


# --- the model's values ----------------------------------------------------------

_HANDLE = {
    None: KP.WriteHandleState_HNone(),
    "open": KP.WriteHandleState_HOpen(),
    "committed": KP.WriteHandleState_HCommitted(),
    "aborted": KP.WriteHandleState_HAborted(),
}
_UNSTARTED = KP.CallerIterState_IUnstarted()
_NO_STREAM = KP.KernelStreamState_SClosed()

# --- the caller's async content ---------------------------------------------------


class _Source:
    """A caller's async iterator with no ``aclose``, recording how far the kernel took it."""

    def __init__(self, *chunks: Any, on_bad: Any = None) -> None:
        self._chunks = list(chunks)
        self._on_bad = on_bad
        self.taken = 0
        self.exhausted = self.closed = False

    def __aiter__(self) -> _Source:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            self.exhausted = True
            raise StopAsyncIteration
        chunk = self._chunks.pop(0)
        self.taken += 1
        if not isinstance(chunk, bytes) and self._on_bad is not None:
            self._on_bad()  # the refused chunk's exit: the state as the kernel refuses it
        return chunk


class _ClosableSource(_Source):
    async def aclose(self) -> None:
        self.closed = True


def _iter_state(source: _Source | None) -> Any:
    if source is None or not (source.taken or source.exhausted or source.closed):
        return _UNSTARTED
    if source.closed:
        return KP.CallerIterState_IClosed()
    if source.exhausted:
        return KP.CallerIterState_IExhausted()
    return KP.CallerIterState_ISuspended()


def _handle_state(store: FakeStore) -> Any:
    # Any handle still open is HOpen, whichever was opened last: a leaked one must not hide behind a later one.
    states = [h.state for h in store.handles]  # type: ignore[attr-defined]
    if "open" in states:
        return _HANDLE["open"]
    return _HANDLE[states[-1] if states else None]


def _observe(store: FakeStore, source: _Source | None) -> Any:
    return KP.KernelResources_KernelResources(_NO_STREAM, _handle_state(store), _iter_state(source))


# --- the write exits --------------------------------------------------------------

_ROUTES: dict[str, dict[str, Any]] = {
    "write": {"put_is_atomic": False},
    "write_atomic-put": {"put_is_atomic": True},
    "write_atomic-open_write": {"put_is_atomic": False},
    "write_atomic-rename": {"put_is_atomic": False, "protocols": ("remove_folder", "rename")},
}
# Each route's driver steps after the gates, in the order the kernel reaches them.
_POINTS = {
    "write": ("put",),
    "write_atomic-put": ("put",),
    "write_atomic-open_write": ("open_write", "handle.write", "handle.commit"),
    "write_atomic-rename": ("put", "rename"),
}
# A fault: the exception it raises, and the exit the model sees.
_FAULTS: dict[str, tuple[type[BaseException] | None, Any]] = {
    "faulted-dead": (FakeDown, KP.KernelExitPath_Faulted(True)),
    "faulted-alive": (FakeOdd, KP.KernelExitPath_Faulted(False)),
    "cancelled": (asyncio.CancelledError, KP.KernelExitPath_Cancelled()),
}


def _write_cases() -> list[Any]:
    cases = []
    for route, points in _POINTS.items():
        cases.append(pytest.param(route, points[-1], "success", id=f"{route}-success"))
        cases.append(pytest.param(route, None, "refused-chunk", id=f"{route}-refused-chunk"))
        cases += [pytest.param(route, None, gate, id=f"{route}-{gate}") for gate in ("gate-closed", "gate-key")]
        cases += [
            pytest.param(route, point, fault, id=f"{route}-{point}-{fault}") for point in points for fault in _FAULTS
        ]
    return cases


def _run_write(runtime: str, route: str, point: str | None, kind: str, closable: bool) -> tuple[Any, Any, Any]:
    """Drive one write to its exit; return (before, after, model's after)."""
    store = FakeStore().add("f", data=b"F")
    run = make_kernel(runtime, store, close_is_terminal=kind == "gate-closed", **_ROUTES[route])
    snap: dict[str, Any] = {}
    source: _Source | None = None

    def at_exit() -> None:
        snap["before"] = _observe(store, source)

    if runtime == "async":
        chunks: tuple[Any, ...] = (b"ab", "text", b"cd") if kind == "refused-chunk" else (b"ab", b"cd")
        cls = _ClosableSource if closable else _Source
        source = cls(*chunks, on_bad=at_exit if kind == "refused-chunk" else None)
        content: Any = source
    else:
        content = _TextStream(at_exit) if kind == "refused-chunk" else io.BytesIO(b"abcd")
    if point is not None:
        exc = _FAULTS[kind][0] if kind in _FAULTS else None
        store.fault(point, exc("boom") if exc is not None else None, hook=at_exit)
    if kind == "gate-closed":
        run.close()

    method = run.write if route == "write" else run.write_atomic
    path = "/g" if kind == "gate-key" else "g"
    expected: type[BaseException] | None = {
        "success": None,
        "refused-chunk": TypeError,
        "gate-closed": BackendUnavailable,
        "gate-key": InvalidPath,
        "faulted-dead": RemoteStoreError,
        "faulted-alive": RemoteStoreError,
        "cancelled": asyncio.CancelledError,
    }[kind]
    if expected is None:
        method(path, content, overwrite=True)
    else:
        with pytest.raises(expected):
            method(path, content, overwrite=True)

    if kind.startswith("gate"):
        before = KP.KernelResources_KernelResources(_NO_STREAM, _HANDLE[None], _UNSTARTED)
        exit_path = KP.KernelExitPath_GateRefused()
    else:
        before = snap["before"]
        exit_path = {"success": KP.KernelExitPath_Success(), "refused-chunk": KP.KernelExitPath_Faulted(False)}.get(
            kind, _FAULTS.get(kind, (None, None))[1]
        )
    after = _observe(store, source)
    return before, after, _MODEL.KernelExit(exit_path, before, closable)


class _TextStream(io.BytesIO):
    """A sync caller stream whose read answers ``str``, the caller's error, taking the exit's snapshot as it does."""

    def __init__(self, at_exit: Any) -> None:
        super().__init__()
        self._at_exit = at_exit

    def read(self, size: int | None = -1) -> Any:
        self._at_exit()
        return "text"


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("closable", [True, False], ids=["aclose", "no-aclose"])
@pytest.mark.parametrize(("route", "point", "kind"), _write_cases())
def test_every_async_write_exit_leaves_the_state_the_model_computes(
    route: str, point: str | None, kind: str, closable: bool
) -> None:
    before, after, model = _run_write("async", route, point, kind, closable)
    assert after == model, f"before {before}: kernel left {after}, model {model}"


# The routes whose driver is handed the caller's iterator; on `open_write` the kernel feeds it itself.
_UNDRAINED_ROUTES = ("write", "write_atomic-put", "write_atomic-rename")


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize("closable", [True, False], ids=["aclose", "no-aclose"])
@pytest.mark.parametrize("route", _UNDRAINED_ROUTES)
def test_a_success_whose_driver_left_the_iterator_suspended_leaves_the_state_the_model_computes(
    route: str, closable: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A driver `put` that takes one chunk and returns: the success exit meets a suspended iterator.
    async def put_one_chunk(self: Any, key: str, content: Any, *, overwrite: bool, metadata: Any) -> Any:
        chunk = await anext(aiter(content))
        return self.store.put(key, chunk, overwrite=overwrite, metadata=metadata)

    monkeypatch.setattr(_AsyncBase, "put", put_one_chunk)  # make_kernel builds a fresh subclass per call
    before, after, model = _run_write("async", route, _POINTS[route][-1], "success", closable)
    assert before.iter_ == KP.CallerIterState_ISuspended()
    assert after == model, f"before {before}: kernel left {after}, model {model}"


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize(("route", "point", "kind"), _write_cases())
def test_every_sync_write_exit_leaves_the_handle_the_model_computes(route: str, point: str | None, kind: str) -> None:
    # Sync content is the caller's stream, outside the model: compare the handle and the stream.
    before, after, model = _run_write("sync", route, point, kind, closable=False)
    assert (after.stream, after.handle) == (model.stream, model.handle), f"before {before}: {after} vs {model}"


_OPEN_ATOMIC_POINTS = ("open_write", "handle.write", "handle.commit")


def _open_atomic_cases() -> list[Any]:
    cases = [pytest.param("handle.commit", "success", id="success"), pytest.param(None, "body", id="body-raises")]
    cases += [pytest.param(None, gate, id=gate) for gate in ("gate-closed", "gate-key")]
    cases += [pytest.param(p, f, id=f"{p}-{f}") for p in _OPEN_ATOMIC_POINTS for f in _FAULTS]
    return cases


@pytest.mark.spec("BE-033")
@pytest.mark.parametrize(("point", "kind"), _open_atomic_cases())
def test_every_open_atomic_exit_leaves_the_handle_the_model_computes(point: str | None, kind: str) -> None:
    # Sync only: the async runtime has no open_atomic. The caller's body raising is a failure exit.
    store = FakeStore().add("f", data=b"F")
    run = make_kernel("sync", store, close_is_terminal=kind == "gate-closed")
    snap: dict[str, Any] = {}

    def at_exit() -> None:
        snap["before"] = _observe(store, None)

    if point is not None:
        exc = _FAULTS[kind][0] if kind in _FAULTS else None
        store.fault(point, exc("boom") if exc is not None else None, hook=at_exit)
    if kind == "gate-closed":
        run.close()
    expected: type[BaseException] | None = {
        "success": None,
        "body": ValueError,
        "gate-closed": BackendUnavailable,
        "gate-key": InvalidPath,
        "cancelled": asyncio.CancelledError,
    }.get(kind, RemoteStoreError)

    def write() -> None:
        with run.kernel.open_atomic("/g" if kind == "gate-key" else "g", overwrite=True) as handle:
            handle.write(b"G")
            if kind == "body":
                at_exit()
                raise ValueError("the caller's body")

    if expected is None:
        write()
    else:
        with pytest.raises(expected):
            write()
    if kind.startswith("gate"):
        before, exit_path = _observe(store, None), KP.KernelExitPath_GateRefused()
        assert before.handle == _HANDLE[None]
    else:
        before = snap["before"]
        exit_path = {"success": KP.KernelExitPath_Success(), "body": KP.KernelExitPath_Faulted(False)}.get(
            kind, _FAULTS.get(kind, (None, None))[1]
        )
    model = _MODEL.KernelExit(exit_path, before, False)
    assert _handle_state(store) == model.handle, f"before {before}: model {model}"


# --- the read exits ---------------------------------------------------------------


def _read_cases() -> list[Any]:
    cases = []
    for how in ("read", "read_bytes"):
        cases += [pytest.param(r, how, None, "success", id=f"{r}-{how}-success") for r in RUNTIMES]
        for runtime in RUNTIMES:
            for nth in (1, 2) if runtime == "async" else (1,):  # the sync stream is read in one call
                cases += [
                    pytest.param(runtime, how, nth, fault, id=f"{runtime}-{how}{nth}-{fault}") for fault in _FAULTS
                ]
        cases += [pytest.param(r, how, None, "gate-closed", id=f"{r}-{how}-gate-closed") for r in RUNTIMES]
    return cases


def _read_bytes(run: Any, path: str) -> bytes:
    if run.runtime == "sync":
        return run.kernel.read_bytes(path)
    return run_async(run.kernel.read_bytes(path))


@pytest.mark.spec("BE-033", "SIO-010")
@pytest.mark.parametrize(("runtime", "how", "nth", "kind"), _read_cases())
def test_every_read_exit_leaves_the_stream_the_model_computes(
    runtime: str, how: str, nth: int | None, kind: str
) -> None:
    # `read` hands the stream on; `read_bytes` drains and closes (or releases) it inside the kernel.
    store = FakeStore().add("f", data=b"0123")
    run = make_kernel(runtime, store, protocols=("remove_folder",), close_is_terminal=kind == "gate-closed")
    read = run.read if how == "read" else (lambda path: _read_bytes(run, path))
    if nth is not None:
        store.fault("stream.read", _FAULTS[kind][0]("boom"), key="f", nth=nth)  # type: ignore[misc]
    if kind == "gate-closed":
        run.close()
        with pytest.raises(BackendUnavailable):
            read("f")
        assert store.called("get") == []  # nothing opened: no stream to model
        return
    expected = {"success": None, "cancelled": asyncio.CancelledError}.get(kind, RemoteStoreError)
    if expected is None and runtime == "sync" and how == "read":
        # The kernel hands the stream over open; its exit is the caller's close, which the
        # kernel's wrapper turns into the inner close or, when condemned, a release.
        with run.kernel.read("f") as stream:
            assert stream.read() == b"0123"
            assert store.called("stream.close") == []
    elif expected is None:
        assert read("f") == b"0123"
    else:
        with pytest.raises(expected):
            read("f")
    after_stream = KP.KernelStreamState_SClosed() if store.called("stream.close") else KP.KernelStreamState_SReleased()
    before = KP.KernelResources_KernelResources(KP.KernelStreamState_SOpen(), _HANDLE[None], _UNSTARTED)
    exit_path = KP.KernelExitPath_Success() if kind == "success" else _FAULTS[kind][1]
    model = _MODEL.KernelExit(exit_path, before, False)
    assert after_stream == model.stream


# --- the backend: every call sequence ---------------------------------------------

_DEPTH = 4
_CALLS = ("close", "write", "unwrap")


def _sequences() -> list[tuple[str, ...]]:
    return [seq for n in range(1, _DEPTH + 1) for seq in itertools.product(_CALLS, repeat=n)]


@pytest.mark.spec("BE-033", "BE-020", "BE-022")
@pytest.mark.parametrize("runtime", RUNTIMES)
@pytest.mark.parametrize("terminal", [False, True], ids=["reusable", "terminal"])
def test_every_call_sequence_answers_as_the_model_steps(runtime: str, terminal: bool) -> None:
    posture = KP.ClosePosture_Terminal() if terminal else KP.ClosePosture_Reusable()
    for seq in _sequences():
        store = FakeStore().add("f", data=b"F")
        run = make_kernel(runtime, store, close_is_terminal=terminal)
        model = KP.KernelBackend_KernelBackend(posture, KP.KernelBackendState_BOpen(), 0)
        for call in seq:
            model, answer = _MODEL.KernelStep(
                model, KP.KernelCall_CloseCall() if call == "close" else KP.KernelCall_LiveCall()
            )
            try:
                if call == "close":
                    run.close()
                elif call == "write":
                    run.write("g", b"G", overwrite=True)
                else:
                    assert run.unwrap(FakeStore) is store
                observed = KP.KernelAnswer_Done()
            except BackendUnavailable:
                observed = KP.KernelAnswer_Unavailable()
            assert observed == answer, f"{seq}: {call} answered {observed}, model {answer}"
        assert len(store.called("close")) == model.driverCloses, seq
