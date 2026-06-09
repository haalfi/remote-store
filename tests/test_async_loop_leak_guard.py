"""Regression for the per-test event-loop sweep (BK-276 / ID-217).

pytest-asyncio 1.3 on Python 3.13 (Windows ``ProactorEventLoop``) leaves the
per-test event loop unclosed after teardown. Its self-pipe loopback socket pair
fires ``ResourceWarning`` on the next cyclic GC; under ``pytest -n auto`` that
mid-run collection is cross-attributed by xdist to an innocent test, and
``filterwarnings = error`` turns it into a spurious hard failure.

The helpers in ``tests/_helpers.py`` close such loops at their source:
``install_event_loop_tracker`` records every loop created via ``new_event_loop``,
``sweep_tracked_event_loops`` (the fast per-test path) closes the abandoned ones,
and ``close_all_abandoned_event_loops`` is the broad session backstop.
``tests/conftest.py`` wires them in. These tests pin the behaviour
deterministically — no xdist, no flake.
"""

from __future__ import annotations

import asyncio
import gc
import warnings

from tests._helpers import (
    close_all_abandoned_event_loops,
    install_event_loop_tracker,
    sweep_tracked_event_loops,
)


def test_tracked_sweep_closes_an_abandoned_loop() -> None:
    """A tracked, non-running, unclosed loop is closed by the fast sweep."""
    install_event_loop_tracker()  # idempotent; conftest already installed it
    loop = asyncio.new_event_loop()
    try:
        assert not loop.is_closed()
        sweep_tracked_event_loops()
        assert loop.is_closed(), "fast sweep must close a tracked abandoned loop"
    finally:
        if not loop.is_closed():
            loop.close()


def test_broad_sweep_closes_an_abandoned_loop() -> None:
    """The broad session backstop closes an abandoned loop via the heap scan."""
    loop = asyncio.new_event_loop()
    try:
        close_all_abandoned_event_loops()
        assert loop.is_closed(), "broad sweep must close an abandoned loop"
    finally:
        if not loop.is_closed():
            loop.close()


def test_sweep_leaves_running_loop_untouched() -> None:
    """A loop the sweep finds *running* must not be closed.

    Models the safety property the per-test hookwrapper relies on: it runs after
    pytest-asyncio's teardown but must never close a loop still in use.
    """
    loop = asyncio.new_event_loop()
    try:

        async def _probe() -> bool:
            sweep_tracked_event_loops()
            return asyncio.get_running_loop().is_closed()

        assert loop.run_until_complete(_probe()) is False
        assert not loop.is_closed()
    finally:
        loop.close()


def test_swept_loop_emits_no_resourcewarning_on_gc() -> None:
    """After the sweep closes a loop, collecting it raises no ResourceWarning.

    Closing the loop releases its self-pipe sockets, so the socket ``__del__``
    that would otherwise warn at GC has nothing to report.
    """
    install_event_loop_tracker()
    loop = asyncio.new_event_loop()
    sweep_tracked_event_loops()
    assert loop.is_closed()
    del loop
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        gc.collect()
