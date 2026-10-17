"""BE-033's invariants under random interleavings: a state machine over the fake driver.

Rules open and read streams, write through every route with a failure or a
cancel injected or none, close the backend and ``unwrap`` it, in any order,
on both runtimes and both close postures. After every rule:

- I1: after a terminal close every operation but ``close`` is
  ``BackendUnavailable`` and reaches no wire primitive;
- I2: every kernel ``close`` reached the driver, so the driver's count is the
  kernel's (``close ∘ close = close`` is the driver's own duty);
- I3: every exit the kernel observed was cleaned up: no write handle is left
  open, every stream opened is closed unless its failure condemned the
  connection, every async caller iterator is exhausted or closed, and no sync
  caller stream is closed.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from remote_store._errors import BackendUnavailable, RemoteStoreError
from tests._kernel._fake import FakeDenied, FakeDown, FakeOdd, FakeStore, make_kernel

_PATHS = st.sampled_from(["a", "b", "c/d"])
_DATA = st.binary(min_size=0, max_size=7)
# Where a write fails: nowhere, a wire refusal at a handle step, a cancel, the caller's own chunk.
_FAULTS = st.sampled_from(["none", "handle.write", "handle.commit", "cancel", "content"])


class _Chunks:
    """An async caller iterator recording how it ended."""

    def __init__(self, data: bytes, refuse: bool) -> None:
        self._chunks: list[Any] = [data[i : i + 2] for i in range(0, len(data), 2)]
        if refuse:
            self._chunks.insert(1, "text")
        self.exhausted = self.closed = False

    def __aiter__(self) -> _Chunks:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            self.exhausted = True
            raise StopAsyncIteration
        return self._chunks.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class _TextStream(io.BytesIO):
    """A sync caller stream whose read answers ``str``: the caller's error."""

    def read(self, size: int | None = -1) -> Any:
        return "text"


class ProtocolModel(RuleBasedStateMachine):
    runtime = "sync"
    terminal = False

    def __init__(self) -> None:
        super().__init__()
        self.store = FakeStore()
        self.run = make_kernel(self.runtime, self.store, close_is_terminal=self.terminal)
        self.files: dict[str, bytes] = {}
        self.closes = 0
        self.closed = False
        self.condemned = 0
        self.iterators: list[_Chunks] = []
        self.streams: list[io.BytesIO] = []

    @property
    def absorbed(self) -> bool:
        return self.closed and self.terminal

    def _refused_untouched(self, call: Any) -> None:
        """I1: the call is ``BackendUnavailable`` and reaches no wire primitive."""
        before = len(self.store.calls)
        with pytest.raises(BackendUnavailable):
            call()
        assert self.store.calls[before:] == []

    # --- rules -------------------------------------------------------------------

    @rule(path=_PATHS, data=_DATA, atomic=st.booleans(), fault=_FAULTS)
    def write(self, path: str, data: bytes, atomic: bool, fault: str) -> None:
        if self.runtime == "async":
            content: Any = _Chunks(data, refuse=fault == "content")
        else:
            content = _TextStream() if fault == "content" else io.BytesIO(data)
            self.streams.append(content)
        method = self.run.write_atomic if atomic else self.run.write
        if self.absorbed:
            # Refused at the gates: the kernel never took the caller's content.
            self._refused_untouched(lambda: method(path, content, overwrite=True))
            assert not getattr(content, "closed", False)
            return
        if self.runtime == "async":
            self.iterators.append(content)
        # Empty content is never written to a handle, so a fault there never fires.
        handle_step = atomic and (fault == "handle.commit" or (fault == "handle.write" and bool(data)))
        cancels = fault == "cancel" and (not atomic or bool(data))
        if handle_step:
            self.store.fault(fault, FakeOdd("boom"))
        elif cancels:
            self.store.fault("handle.write" if atomic else "put", asyncio.CancelledError())
        expected: type[BaseException] | None = None
        if fault == "content":
            expected = TypeError
        elif cancels:
            expected = asyncio.CancelledError
        elif handle_step:
            expected = RemoteStoreError
        try:
            if expected is None:
                method(path, content, overwrite=True)
                self.files[path] = data
            else:
                with pytest.raises(expected):
                    method(path, content, overwrite=True)
        finally:
            self.store.faults.clear()

    @precondition(lambda self: bool(self.files))
    @rule(data=st.data())
    def read(self, data: st.DataObject) -> None:
        path = data.draw(st.sampled_from(sorted(self.files)))
        if self.absorbed:
            self._refused_untouched(lambda: self.run.read(path))
            return
        assert self.run.read(path) == self.files[path]

    @precondition(lambda self: any(self.files.values()))
    @rule(data=st.data(), dead=st.booleans())
    def read_fails(self, data: st.DataObject, dead: bool) -> None:
        path = data.draw(st.sampled_from(sorted(k for k, v in self.files.items() if v)))
        if self.absorbed:
            self._refused_untouched(lambda: self.run.read(path))
            return
        self.store.fault("stream.read", FakeDown("dead") if dead else FakeDenied("no"), key=path)
        try:
            with pytest.raises(RemoteStoreError):
                self.run.read(path)
        finally:
            self.store.faults.clear()
        self.condemned += dead

    @rule()
    def close(self) -> None:
        self.run.close()
        self.closes += 1
        self.closed = True

    @rule()
    def unwrap(self) -> None:
        if self.absorbed:
            self._refused_untouched(lambda: self.run.unwrap(FakeStore))
        else:
            assert self.run.unwrap(FakeStore) is self.store

    # --- invariants --------------------------------------------------------------

    @invariant()
    def every_close_reaches_the_driver(self) -> None:  # I2
        assert len(self.store.called("close")) == self.closes

    @invariant()
    def no_write_handle_is_left_open(self) -> None:  # I3
        assert all(h.state != "open" for h in self.store.handles)  # type: ignore[attr-defined]

    @invariant()
    def every_stream_opened_is_closed_unless_condemned(self) -> None:  # I3
        opened = len(self.store.called("get"))
        assert len(self.store.called("stream.close")) == opened - self.condemned

    @invariant()
    def the_callers_content_is_left_as_the_protocol_says(self) -> None:  # I3
        assert all(it.exhausted or it.closed for it in self.iterators)
        assert not any(s.closed for s in self.streams)


def _case(runtime: str, terminal: bool) -> Any:
    machine = type(
        f"ProtocolModel_{runtime}_{'terminal' if terminal else 'reusable'}",
        (ProtocolModel,),
        {"runtime": runtime, "terminal": terminal},
    )
    case = machine.TestCase
    case.settings = settings(max_examples=60, stateful_step_count=25, deadline=None)
    case.__module__ = __name__
    return pytest.mark.spec("BE-033", "BE-020", "SIO-010")(pytest.mark.pbt(case))


TestProtocolSyncReusable = _case("sync", terminal=False)
TestProtocolSyncTerminal = _case("sync", terminal=True)
TestProtocolAsyncReusable = _case("async", terminal=False)
TestProtocolAsyncTerminal = _case("async", terminal=True)
