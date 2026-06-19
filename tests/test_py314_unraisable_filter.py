"""Regression guard for the BUG-224 `_wait_for_close` filterwarnings entry.

Python 3.14 escalates an unawaited aiohttp connector-close coroutine
(`_wait_for_close`, defined in ``aiohttp/connector.py``) into a
``PytestUnraisableExceptionWarning`` at GC time, which ``filterwarnings = error``
turns into a hard, non-deterministically-attributed CI failure. The coroutine
originates from aiobotocore's aiohttp ``ClientSession``, which the sync S3
backend closes via s3fs's ``weakref.finalize`` at GC (BK-306's by-design
release) — so the session *is* closed, just at a GC point py3.14 reports
aggressively. BUG-224 suppresses exactly that one warning via a `filterwarnings`
ignore in ``pyproject.toml``.

The suppression's efficacy hinges on a ``re.match``-anchored message regex
matching the real warning text. To avoid resting on one hand-transcribed prefix
(which would make the guard self-referential — a transcription error would pass
the guard yet silently fail in CI), the filter anchors on the stable
``<coroutine object _wait_for_close`` coroutine-repr with a ``.*`` lead-in, and
this guard asserts suppression across **both** unraisable lead-in forms CPython
can emit:

* ``Exception ignored while finalizing coroutine <coroutine object _wait_for_close at 0x...>: None``
  — the wrapped-Task finalization form, captured verbatim from a real failing
  ``test (3.14)`` CI log (job 82411660992); and
* ``Exception ignored in: <coroutine object _wait_for_close at 0x...>``
  — the top-level never-awaited form CPython emits when the coroutine is not
  wrapped in a Task.

Matching both proves robustness to lead-in wording / CPython-pytest message
drift, not just to one transcribed string. Prior art: BK-304 shipped a test
asserting its ``-p no:unraisableexception`` mitigation is applied rather than
trusting CI. (A green ``test (3.14)`` run is not proof for a ~50% flake; this
deterministic, version-independent guard is.)
"""

from __future__ import annotations

import warnings

import pytest
from _pytest.config import parse_warning_filter

PytestUnraisableExceptionWarning = pytest.PytestUnraisableExceptionWarning

# Both real outer `PytestUnraisableExceptionWarning` lead-in forms for the
# `_wait_for_close` coroutine; only the hex address varies run-to-run. The first
# is the verbatim text from a real `test (3.14)` failure; the second is the
# alternative form CPython emits for an unwrapped never-awaited coroutine.
_REAL_MSGS = (
    "Exception ignored while finalizing coroutine <coroutine object _wait_for_close at 0x7f9409f2f3d0>: None",
    "Exception ignored in: <coroutine object _wait_for_close at 0x55d0e1>",
)
# A structurally identical unraisable for a *different* coroutine: must still
# fail, proving the ignore is scoped and genuine leak detection is preserved.
_CONTROL_MSG = "Exception ignored while finalizing coroutine <coroutine object some_other_coro at 0x1>: None"


def _wait_for_close_filter(pytestconfig: pytest.Config) -> tuple[str, str, type[Warning], str, int]:
    """The configured BUG-224 ignore, parsed exactly as pytest parses it.

    Pulls the live ``filterwarnings`` list from the active pytest config (the
    single source of truth in ``pyproject.toml``), so a removed or reworded
    entry fails this test rather than silently becoming a no-op.
    """
    filters = pytestconfig.getini("filterwarnings")
    matching = [f for f in filters if "_wait_for_close" in f]
    assert matching, (
        "BUG-224 `_wait_for_close` filterwarnings entry is missing from "
        "pyproject.toml [tool.pytest.ini_options].filterwarnings"
    )
    assert len(matching) == 1, f"expected exactly one `_wait_for_close` filter, found {len(matching)}: {matching}"
    return parse_warning_filter(matching[0], escape=False)


@pytest.mark.parametrize("real_msg", _REAL_MSGS)
def test_wait_for_close_filter_suppresses_real_py314_message(pytestconfig: pytest.Config, real_msg: str) -> None:
    """The configured ignore must suppress every real py3.14 lead-in form."""
    parsed = _wait_for_close_filter(pytestconfig)
    # The entry must target PytestUnraisableExceptionWarning (the outer wrapper),
    # not the inner RuntimeWarning — anchoring on the wrong layer is a silent no-op.
    assert parsed[2] is PytestUnraisableExceptionWarning
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings(*parsed)
        # Must NOT raise: the ignore matches the real message.
        warnings.warn(PytestUnraisableExceptionWarning(real_msg), stacklevel=1)


def test_wait_for_close_filter_does_not_mask_other_unraisables(pytestconfig: pytest.Config) -> None:
    """A different orphaned coroutine must still fail — leak detection preserved."""
    parsed = _wait_for_close_filter(pytestconfig)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings(*parsed)
        with pytest.raises(PytestUnraisableExceptionWarning):
            warnings.warn(PytestUnraisableExceptionWarning(_CONTROL_MSG), stacklevel=1)
