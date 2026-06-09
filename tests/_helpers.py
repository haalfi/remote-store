"""Shared test helpers."""

from __future__ import annotations

import asyncio
import asyncio.events
import gc
import io
import weakref
from typing import TYPE_CHECKING

# Re-export from infra._settings so MinIO credentials change in exactly
# one place (infra/.env). Names kept stable for existing callers.
from infra._settings import MINIO_ACCESS_KEY as MINIO_KEY
from infra._settings import MINIO_SECRET_KEY as MINIO_SECRET

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "MINIO_KEY",
    "MINIO_SECRET",
    "FailingContentReader",
    "close_all_abandoned_event_loops",
    "install_event_loop_tracker",
    "pyarrow_ge_24",
    "sweep_tracked_event_loops",
    "uninstall_event_loop_tracker",
]

# ---------------------------------------------------------------------------
# Event-loop leak guard (BK-276 / ID-217)
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
# loop created via ``new_event_loop`` in a ``WeakSet`` and sweep only that tiny
# set per-test. The broad heap scan is kept as a once-per-session backstop (it
# also preserves ID-158's original guarantee for loops created before the
# tracker was installed).

_TRACKED_LOOPS: weakref.WeakSet[asyncio.AbstractEventLoop] = weakref.WeakSet()
_ORIG_POLICY_NEW_EVENT_LOOP: Callable[..., asyncio.AbstractEventLoop] | None = None


def install_event_loop_tracker() -> None:
    """Patch the policy's ``new_event_loop`` so every loop created is weakly tracked.

    Idempotent. We patch ``BaseDefaultEventLoopPolicy.new_event_loop`` at the
    *class* level rather than the module-level ``asyncio.new_event_loop``
    function, because every creation path funnels through the policy method:

    * ``asyncio.new_event_loop()`` → ``get_event_loop_policy().new_event_loop()``
    * pytest-asyncio's ``asyncio.Runner`` → ``events.new_event_loop()`` → ditto
    * ``asyncio.get_event_loop()`` auto-create (the ID-158 phantom path) →
      ``self.set_event_loop(self.new_event_loop())`` — calls the policy *method*
      directly, which a module-function patch misses.

    Patching the class also survives pytest-asyncio's temporary policy swaps
    (its replacement policy subclasses ``BaseDefaultEventLoopPolicy``). Closed
    and collected loops drop out of the ``WeakSet`` on their own, so it stays
    small.

    The sweep is deliberately scoped to *teardown* (see
    ``sweep_tracked_event_loops``): a loop is only safe to close once the test
    that owns it is finished. A GC-callback that closed loops mid-collection was
    tried and rejected — the cyclic GC fires while a test is mid-flight, when its
    loop is momentarily not running but still owned, and closing it there breaks
    the test.
    """
    global _ORIG_POLICY_NEW_EVENT_LOOP
    if _ORIG_POLICY_NEW_EVENT_LOOP is not None:
        return
    orig = asyncio.events.BaseDefaultEventLoopPolicy.new_event_loop
    _ORIG_POLICY_NEW_EVENT_LOOP = orig

    def _tracking_new_event_loop(self: asyncio.AbstractEventLoopPolicy) -> asyncio.AbstractEventLoop:
        loop = orig(self)
        _TRACKED_LOOPS.add(loop)
        return loop

    asyncio.events.BaseDefaultEventLoopPolicy.new_event_loop = _tracking_new_event_loop  # type: ignore[method-assign]


def uninstall_event_loop_tracker() -> None:
    """Restore the original policy ``new_event_loop``. Idempotent."""
    global _ORIG_POLICY_NEW_EVENT_LOOP
    if _ORIG_POLICY_NEW_EVENT_LOOP is None:
        return
    asyncio.events.BaseDefaultEventLoopPolicy.new_event_loop = _ORIG_POLICY_NEW_EVENT_LOOP  # type: ignore[method-assign]
    _ORIG_POLICY_NEW_EVENT_LOOP = None


def _close_if_abandoned(loop: asyncio.AbstractEventLoop) -> None:
    try:
        if not loop.is_running() and not loop.is_closed():
            loop.close()
    except Exception:  # noqa: BLE001
        pass


def sweep_tracked_event_loops() -> None:
    """Close every tracked loop that is neither running nor closed.

    Fast path used after every test: iterates only ``_TRACKED_LOOPS`` (a handful
    of entries), never the whole heap. A *running* loop is the one in active use,
    so it is left untouched — the per-test hookwrapper runs after pytest-asyncio's
    own teardown, so any loop it finds non-running here is genuinely abandoned.
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
