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

The suppression's whole efficacy hinges on a single ``re.match``-anchored
message regex matching the real warning text. This guard pins that regex against
CPython / pytest message drift and proves the entry actually suppresses the
warning — verification the flaky py3.14-only CI run cannot provide
deterministically. Prior art: BK-304 shipped a test asserting its
``-p no:unraisableexception`` mitigation is applied rather than trusting CI.

The ``real_msg`` below is the **verbatim** outer ``PytestUnraisableExceptionWarning``
text captured from an actual failing ``test (3.14)`` CI log (the wrapped-Task
finalization form — *not* the inner ``RuntimeWarning: coroutine ... was never
awaited`` form, and *not* the top-level ``Exception ignored in:`` form).
"""

from __future__ import annotations

import warnings

import pytest
from _pytest.config import parse_warning_filter

PytestUnraisableExceptionWarning = pytest.PytestUnraisableExceptionWarning

# Verbatim outer message from a real `test (3.14)` failure (only the hex address
# of the coroutine object varies run-to-run; the regex stops before it).
_REAL_MSG = "Exception ignored while finalizing coroutine <coroutine object _wait_for_close at 0x7f9409f2f3d0>: None"
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


def test_wait_for_close_filter_suppresses_real_py314_message(pytestconfig: pytest.Config) -> None:
    """The configured ignore must suppress the verbatim py3.14 warning text."""
    parsed = _wait_for_close_filter(pytestconfig)
    # The entry must target PytestUnraisableExceptionWarning (the outer wrapper),
    # not the inner RuntimeWarning — anchoring on the wrong layer is a silent no-op.
    assert parsed[2] is PytestUnraisableExceptionWarning
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings(*parsed)
        # Must NOT raise: the ignore matches the real message.
        warnings.warn(PytestUnraisableExceptionWarning(_REAL_MSG), stacklevel=1)


def test_wait_for_close_filter_does_not_mask_other_unraisables(pytestconfig: pytest.Config) -> None:
    """A different orphaned coroutine must still fail — leak detection preserved."""
    parsed = _wait_for_close_filter(pytestconfig)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings(*parsed)
        with pytest.raises(PytestUnraisableExceptionWarning):
            warnings.warn(PytestUnraisableExceptionWarning(_CONTROL_MSG), stacklevel=1)
