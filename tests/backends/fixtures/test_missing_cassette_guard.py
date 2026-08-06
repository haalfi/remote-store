"""Tests for the runtime missing-cassette guard (TEST-007, ID-241).

The guard replaces a collection-time skip keyed on the *test name* with one
keyed on what actually happened: a request vcrpy cannot play against a cassette
file that does not exist. A cell that issues no request therefore runs, on every
replay fixture where that is true of it.

Two things these tests are here to pin, because both are assumptions the design
rests on and neither is visible in the guard's own source:

* **Every transport we replay on routes through the method the guard wraps.**
  The three transport cells below drive real vcrpy stubs — urllib3 (sync Azure),
  aiohttp (async Azure), httpx (Graph) — rather than asserting the wrapper in
  isolation. If a vcrpy release stops consulting ``can_play_response_for`` on any
  of them, the guard would silently stop firing for that backend; these fail
  instead. They are the third private-vcrpy dependency the ``vcrpy>=8.2,<8.4``
  pin in ``pyproject.toml`` exists for.
* **The skip cannot be swallowed.** Backends map ``except Exception`` into
  library errors — ``AsyncAzureBackend`` was measured turning vcrpy's
  ``CannotOverwriteExistingCassetteException`` into ``RemoteStoreError`` — so a
  skip raised as an ordinary exception would be translated into a *passing*
  assertion by any cell expecting an error. ``Skipped`` derives from
  ``BaseException``, which is what makes the guard safe rather than merely
  convenient.

Real ``vcr.cassette.Cassette`` objects throughout (TESTING.md Rule 6): the
subject is our interaction with vcrpy, and a stub of it would assert only that
we agree with ourselves.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import vcr
from vcr.cassette import Cassette
from vcr.request import Request as VcrRequest

from tests.backends.fixtures._cassette_pytest import (
    _make_missing_cassette_guard,
    install_missing_cassette_guard,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_UNREACHABLE = "https://id-241.invalid/probe"


def _request() -> VcrRequest:
    return VcrRequest("GET", _UNREACHABLE, None, {})


def _cassette(path: Path, record_mode: str = "none") -> Cassette:
    """A real vcrpy cassette rooted at *path*, loaded as vcrpy would load it."""
    cassette = Cassette(str(path), record_mode=record_mode)
    cassette._load()
    return cassette


def _pristine() -> Callable[..., bool]:
    """vcrpy's own ``can_play_response_for``, whatever this session wrapped it with.

    A full-suite run has already installed the session guard by the time these
    tests execute, so building a second guard on top of the live attribute would
    test a stack of two. ``functools.wraps`` leaves ``__wrapped__`` behind, which
    is the thread back to the unwrapped method.
    """
    fn = Cassette.can_play_response_for
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


@pytest.fixture
def guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install the guard for one test; return the root it renders paths against.

    ``install_missing_cassette_guard`` is session-lifetime by design (it is
    called from ``pytest_configure``), so these tests apply the same wrapper
    through ``monkeypatch`` instead of installing it globally — the guard under
    test is the identical object either way.
    """
    guard = _make_missing_cassette_guard(_pristine(), tmp_path)
    monkeypatch.setattr(Cassette, "can_play_response_for", guard)
    return tmp_path


@pytest.mark.spec("TEST-007")
class TestMissingCassetteGuard:
    """An unplayable request skips only when the cassette file is absent."""

    def test_absent_cassette_skips_with_the_recording_instruction(self, guarded: Path) -> None:
        """The TEST-007 skip: no cassette to play from, and the message says how to make one."""
        cassette = _cassette(guarded / "cassettes" / "azure" / "TestFoo.test_bar[azure].yaml")
        with pytest.raises(pytest.skip.Exception) as exc_info:
            cassette.can_play_response_for(_request())
        message = str(exc_info.value)
        assert "replay cassette missing" in message
        assert "cassettes/azure/TestFoo.test_bar[azure].yaml" in message
        assert "--stage=3 --record" in message

    def test_present_cassette_with_no_match_does_not_skip(self, guarded: Path) -> None:
        """A recorded-but-stale cassette is a failure, not a skip.

        This is the distinction the old name-keyed hook could not draw at all
        and the one that keeps the guard from hiding a real regression: the
        cassette exists, so somebody recorded it, so a request it cannot serve
        means the recording no longer matches the code.
        """
        path = guarded / "cassettes" / "azure" / "recorded.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("interactions: []\nversion: 1\n", encoding="utf-8")
        cassette = _cassette(path)
        assert cassette.can_play_response_for(_request()) is False

    def test_recording_mode_does_not_skip(self, guarded: Path) -> None:
        """For a cassette being written, an absent file is the expected state, not a gap.

        Record mode is refused twice over, at two different granularities, and
        this cell covers the inner one: even with the guard installed, a cassette
        that is not write-protected passes straight through. The outer one — the
        installer declining to arm at all in a recording session — is
        ``TestGuardInstallation`` below. Per-cassette rather than per-session
        because vcrpy's record mode is a property of the cassette: pytest's
        ``--record-mode`` is only its usual source.
        """
        cassette = _cassette(guarded / "cassettes" / "azure" / "fresh.yaml", record_mode="all")
        assert cassette.can_play_response_for(_request()) is False

    def test_playable_request_is_returned_untouched(self, guarded: Path) -> None:
        """The wrapper is transparent on the hot path: a recorded request still plays."""
        path = guarded / "cassettes" / "azure" / "playable.yaml"
        path.parent.mkdir(parents=True)
        with vcr.use_cassette(str(path), record_mode="all") as recording:
            recording.append(
                _request(), {"status": {"code": 200, "message": "OK"}, "headers": {}, "body": {"string": b""}}
            )
        cassette = _cassette(path)
        assert cassette.can_play_response_for(_request()) is True
        assert cassette.play_response(_request())["status"]["code"] == 200

    def test_skip_is_a_base_exception(self) -> None:
        """``except Exception`` must not be able to swallow the skip.

        The guard raises through backend code that maps arbitrary exceptions
        into ``RemoteStoreError``; a cell asserting an error would then *pass*
        on a skip, which is the vacuous-green failure mode this design exists to
        avoid. Pinned as its own cell so a refactor to a plain exception fails
        here rather than silently in the conformance suite.
        """
        assert issubclass(pytest.skip.Exception, BaseException)
        assert not issubclass(pytest.skip.Exception, Exception)


@pytest.mark.spec("TEST-007")
class TestGuardCoversEveryReplayTransport:
    """Each stub we replay through must consult the wrapped method.

    One cell per transport that a registered replay fixture actually uses:
    urllib3 (``azure_replay``), aiohttp (``azure_replay_async``) and httpx
    (``graph_replay``). Each issues a real request under a cassette that does
    not exist and asserts the guard converted it into a skip — end to end,
    through vcrpy's own patching, not through our wrapper alone.
    """

    def test_urllib3_transport_skips(self, guarded: Path) -> None:
        import urllib3

        with (
            pytest.raises(pytest.skip.Exception, match="replay cassette missing"),
            vcr.use_cassette(str(guarded / "urllib3.yaml"), record_mode="none"),
        ):
            urllib3.PoolManager().request("GET", _UNREACHABLE)

    def test_httpx_transport_skips(self, guarded: Path) -> None:
        httpx = pytest.importorskip("httpx", reason="graph extra not installed")

        with (
            pytest.raises(pytest.skip.Exception, match="replay cassette missing"),
            vcr.use_cassette(str(guarded / "httpx.yaml"), record_mode="none"),
        ):
            httpx.get(_UNREACHABLE)

    def test_aiohttp_transport_skips(self, guarded: Path) -> None:
        aiohttp = pytest.importorskip("aiohttp", reason="aiohttp not installed")

        async def _get() -> None:
            async with aiohttp.ClientSession() as session, session.get(_UNREACHABLE):
                pass

        with (
            pytest.raises(pytest.skip.Exception, match="replay cassette missing"),
            vcr.use_cassette(str(guarded / "aiohttp.yaml"), record_mode="none"),
        ):
            asyncio.run(_get())


class _FakeConfig:
    """A stand-in for ``pytest.Config`` carrying just the two flags the installer reads.

    Deliberately not the live ``pytestconfig``: these cells assert what the
    installer does *per flag combination*, and reading the flags of whichever
    session happens to be running would make the answer depend on how the suite
    was invoked. That is the same class of accident the guard's own
    hook-ordering bug was.
    """

    rootpath = Path("/repo")

    def __init__(self, *, record: bool = False, record_mode: str | None = None) -> None:
        self._options: dict[str, object] = {"--record": record, "--record-mode": record_mode}

    def getoption(self, name: str, default: object = None) -> object:
        return self._options.get(name, default)


@pytest.mark.spec("TEST-007")
class TestGuardInstallation:
    """``install_missing_cassette_guard`` is the conftest-facing entry point."""

    def test_install_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two conftests call it over one session; the second must not double-wrap.

        A second wrap would still behave correctly, so nothing observable would
        break — which is precisely why it needs a cell: the cost is silent.
        """
        original = _pristine()
        monkeypatch.setattr(Cassette, "can_play_response_for", original)
        replaying = _FakeConfig()
        install_missing_cassette_guard(replaying)  # type: ignore[arg-type]
        once = Cassette.can_play_response_for
        install_missing_cassette_guard(replaying)  # type: ignore[arg-type]
        assert Cassette.can_play_response_for is once
        assert once is not original

    @pytest.mark.parametrize(
        "config",
        [
            pytest.param(_FakeConfig(record=True), id="record-flag-only"),
            pytest.param(_FakeConfig(record_mode="rewrite"), id="record-mode-only"),
            pytest.param(_FakeConfig(record=True, record_mode="rewrite"), id="both"),
        ],
    )
    def test_recording_session_is_left_unguarded(self, monkeypatch: pytest.MonkeyPatch, config: _FakeConfig) -> None:
        """A recording session must be untouched, whichever flag says so.

        Under recording, a replay fixture with a missing cassette fails loudly
        today and continues to; converting that into a skip would let
        ``record_cassettes.py`` report success over cassettes it never wrote.

        The ``record-flag-only`` case is the one that matters and the reason
        both options are read. ``record_cassettes.py`` passes ``--record``, never
        ``--record-mode``; the root conftest maps the former onto
        ``record_mode="rewrite"`` in *its* ``pytest_configure``, and pluggy calls
        historic-hook impls in reverse registration order — so at the moment this
        function runs, ``--record-mode`` may still be unset. Keying on it alone
        would arm the guard inside every recording run.
        """
        original = _pristine()
        monkeypatch.setattr(Cassette, "can_play_response_for", original)
        install_missing_cassette_guard(config)  # type: ignore[arg-type]
        assert Cassette.can_play_response_for is original
