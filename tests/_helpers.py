"""Shared test helpers."""

from __future__ import annotations

import asyncio
import asyncio.base_events
import gc
import io
import weakref
from typing import TYPE_CHECKING

# Re-export from infra._settings so MinIO credentials change in exactly
# one place (infra/.env). Names kept stable for existing callers.
from infra._settings import MINIO_ACCESS_KEY as MINIO_KEY
from infra._settings import MINIO_SECRET_KEY as MINIO_SECRET
from remote_store._stream import _ErrorMappingStream

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "KNOWN_STREAM_WRAPPERS",
    "MINIO_KEY",
    "MINIO_SECRET",
    "PEEL_STOPPED_ON_WRAPPER",
    "FailingContentReader",
    "close_all_abandoned_event_loops",
    "install_event_loop_tracker",
    "peel_to_body",
    "pyarrow_ge_24",
    "sweep_tracked_event_loops",
    "uninstall_event_loop_tracker",
]

# ---------------------------------------------------------------------------
# Event-loop leak guard (BK-276)
# ---------------------------------------------------------------------------
#
# pytest-asyncio 1.3 on Python 3.13 (Windows ``ProactorEventLoop``) leaves the
# per-test event loop unclosed after teardown. Its self-pipe loopback socket
# pair fires ``ResourceWarning`` whenever the cyclic GC next runs; under
# ``pytest -n auto`` that mid-run collection is cross-attributed by xdist to
# whichever test happens to be executing on the worker, and
# ``filterwarnings = error`` promotes the warning to a spurious hard failure.
# The blamed test varies run to run and always passes in isolation.
#
# Fix: close such loops at their source after every test, *before* any
# ``gc.collect`` can free their sockets. A whole-heap ``gc.get_objects()`` scan
# per test is correct but doubles the suite wall-time, so we instead track every
# event loop at construction (a ``BaseEventLoop.__init__`` patch — the one
# chokepoint every loop class and every supported Python funnels through) in a
# ``WeakSet`` and sweep only that tiny set per-test. The broad heap scan is kept
# as a once-per-session backstop (it also preserves ID-158's original guarantee
# for loops created before the tracker was installed).

_TRACKED_LOOPS: weakref.WeakSet[asyncio.AbstractEventLoop] = weakref.WeakSet()
_ORIG_LOOP_INIT: Callable[..., None] | None = None


def install_event_loop_tracker() -> None:
    """Patch ``BaseEventLoop.__init__`` so every event loop is weakly tracked.

    Idempotent. ``asyncio.base_events.BaseEventLoop.__init__`` is the single
    chokepoint every concrete loop runs through — Proactor/Selector,
    pytest-asyncio's ``asyncio.Runner`` loop, and the ID-158
    ``asyncio.get_event_loop()`` phantom alike — on every supported Python.

    An earlier version patched ``BaseDefaultEventLoopPolicy.new_event_loop``;
    that broke on Python 3.14, which removed the event-loop policy framework
    entirely (and where ``get_event_loop`` no longer auto-creates, so the
    phantom path does not exist). Patching the loop constructor is
    version-agnostic: ``BaseEventLoop`` exists everywhere. Closed and collected
    loops drop out of the ``WeakSet`` on their own, so it stays small.

    The sweep is deliberately scoped to *teardown* (see
    ``sweep_tracked_event_loops``): a loop is only safe to close once the test
    that owns it is finished. A GC-callback that closed loops mid-collection was
    tried and rejected — the cyclic GC fires while a test is mid-flight, when its
    loop is momentarily not running but still owned, and closing it there breaks
    the test.
    """
    global _ORIG_LOOP_INIT
    if _ORIG_LOOP_INIT is not None:
        return
    orig = asyncio.base_events.BaseEventLoop.__init__
    _ORIG_LOOP_INIT = orig

    def _tracking_init(self: asyncio.AbstractEventLoop, *args: object, **kwargs: object) -> None:
        orig(self, *args, **kwargs)
        _TRACKED_LOOPS.add(self)

    asyncio.base_events.BaseEventLoop.__init__ = _tracking_init  # type: ignore[method-assign]


def uninstall_event_loop_tracker() -> None:
    """Restore the original ``BaseEventLoop.__init__``. Idempotent."""
    global _ORIG_LOOP_INIT
    if _ORIG_LOOP_INIT is None:
        return
    asyncio.base_events.BaseEventLoop.__init__ = _ORIG_LOOP_INIT  # type: ignore[method-assign]
    _ORIG_LOOP_INIT = None


def _close_if_abandoned(loop: asyncio.AbstractEventLoop) -> None:
    try:
        if not loop.is_running() and not loop.is_closed():
            loop.close()
    except Exception:  # noqa: BLE001
        pass


def sweep_tracked_event_loops() -> None:
    """Close every tracked loop that is neither running nor closed.

    Fast path used after every test: iterates only ``_TRACKED_LOOPS`` (a handful
    of entries), never the whole heap. A *running* loop is left untouched.

    "Non-running ⇒ abandoned" holds because of two scope assumptions, both true
    today; revisit this sweep if either changes:

    * **Function-scoped loops only.** ``asyncio_mode = auto`` with the default
      function loop scope means pytest-asyncio tears its loop down per test, so a
      loop found non-running at *that test's* teardown is finished with. A
      ``@pytest.mark.asyncio(loop_scope="module"|"session")`` test — or any
      module/session fixture holding an idle ``new_event_loop()`` between tests —
      would own a non-running loop *between* tests in its scope, and this sweep
      would close it mid-scope. No such usage exists in the suite.
    * **The adapter daemon loop is spared while it runs.** The class-level patch
      also tracks ``AsyncBackendSyncAdapter``'s private loop
      (``src/remote_store/_async_to_sync_adapter.py``); ``is_running()`` is
      ``True`` for its whole ``run_forever()`` lifetime, so it is never swept.
      There is a sub-millisecond ``thread.start()`` → ``run_forever()`` window
      where ``is_running()`` is briefly ``False``, but a test cannot reach its own
      teardown inside that window, so it is theoretical.
    """
    for loop in list(_TRACKED_LOOPS):
        _close_if_abandoned(loop)


def close_all_abandoned_event_loops() -> None:
    """Broad heap sweep: close *any* reachable abandoned loop. Session backstop.

    Runs once at session teardown. Catches loops created before the tracker was
    installed (preserving ID-158's guarantee). Must **not** call ``gc.collect``
    first — that would free the cyclic garbage whose socket finalization we are
    racing to prevent.
    """
    sweep_tracked_event_loops()
    for obj in gc.get_objects():
        try:
            if isinstance(obj, asyncio.AbstractEventLoop):
                _close_if_abandoned(obj)
        except Exception:  # noqa: BLE001
            pass


class FailingContentReader(io.RawIOBase):
    """Content source that delivers ``fill`` NUL bytes then raises mid-stream.

    Models a content producer (socket, generator, upstream stream) that fails
    partway through a write. Used by the BUG-214 atomicity tests to assert that
    ``write`` / ``write_atomic`` do not commit a truncated object when the
    source raises. ``buffered()`` wraps it in a ``BufferedReader`` so callers
    that read in fixed chunks get the standard buffered interface.
    """

    def __init__(self, fill: int) -> None:
        super().__init__()
        self._remaining = fill

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        if self._remaining <= 0:
            raise ConnectionResetError("simulated mid-stream content failure")
        n = min(len(b), self._remaining)
        b[:n] = bytes(n)
        self._remaining -= n
        return n

    @classmethod
    def buffered(cls, fill: int) -> io.BufferedReader:
        """Return a ``BufferedReader`` wrapping a ``FailingContentReader``."""
        return io.BufferedReader(cls(fill))


def pyarrow_ge_24() -> bool:
    """Return True if pyarrow is installed and its major version is >= 24."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return int(version("pyarrow").split(".")[0]) >= 24
    except PackageNotFoundError:
        return False


# ---------------------------------------------------------------------------
# SIO-009 stream peeling (BUG-244)
# ---------------------------------------------------------------------------
#
# Lives here, not beside either caller, because the duplication is what caused
# the defect. The cross-backend cell and the HTTP-specific cell each had their
# own copy of this walk; BUG-244 was fixed in one and the other kept the broken
# form through a further review round. One implementation, two importers.

KNOWN_STREAM_WRAPPERS: tuple[type, ...] = (io.BufferedReader, _ErrorMappingStream)
"""Wrapping layers ``peel_to_body`` knows how to see through.

Terminating on one of these means the walk lost an accessor it is supposed to
follow, which is the BUG-244 failure mode.
"""

PEEL_STOPPED_ON_WRAPPER = (
    "peel terminated on a known wrapping layer instead of the body, so this "
    "cell inspected the wrapper and would pass for any content underneath it. "
    "The layer's accessor is no longer reachable from peel_to_body (BUG-244)."
)


def peel_to_body(stream: object) -> object:
    """Unwrap *stream* down to the object actually producing bytes.

    Two wrapping layers exist and they expose the wrapped object under
    **different names**, which is the whole reason this helper exists:

    * buffering (``io.BufferedReader``) exposes ``.raw``;
    * error mapping (``remote_store._stream._ErrorMappingStream``) exposes
      ``._inner`` and has **no** ``.raw``.

    A ``.raw``-only walk therefore terminates *on* an ``_ErrorMappingStream``,
    and ``isinstance(wrapper, io.BytesIO)`` is false whatever the wrapper
    contains — so the SIO-009 laziness assertion passed without ever inspecting
    a body (BUG-244).

    An **unwrapped** stream is returned unchanged, and that is deliberate: a
    backend handing back a bare body has nothing to peel, and a bare
    ``io.BytesIO`` — the exact SIO-009 violation callers look for — must reach
    the caller's own assertion rather than being intercepted here. Callers
    therefore assert the BytesIO contract *first* and
    ``KNOWN_STREAM_WRAPPERS`` second.

    **Bound** (DRIFT-RULES Rule 7): the wrapper guard catches the walk losing an
    accessor it already knows about. It does **not** detect a *new* wrapper type
    introduced later — that object is indistinguishable from a body here, and no
    general test separates the two. Adding a wrapping layer means adding it to
    ``KNOWN_STREAM_WRAPPERS`` and to the walk below.
    """
    while True:
        if hasattr(stream, "raw"):
            stream = stream.raw
        elif hasattr(stream, "_inner"):
            stream = stream._inner
        else:
            return stream
