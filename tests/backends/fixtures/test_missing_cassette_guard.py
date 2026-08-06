"""Tests for the runtime missing-cassette guard (TEST-007, ID-241).

The guard replaces a collection-time skip keyed on the *test name* with one
keyed on what actually happened: a request vcrpy cannot play against a cassette
file that does not exist. A cell that issues no request therefore runs, on every
replay fixture where that is true of it.

Three things these tests are here to pin, because each is an assumption the
design rests on and none is visible in the guard's own source:

* **Every transport we replay on routes through the method the guard wraps.**
  The transport cells below drive the real vcrpy stubs this repo replays
  through, rather than asserting the wrapper in isolation. If a vcrpy release
  stops consulting ``can_play_response_for`` on one of them, the guard would
  silently stop firing for that backend; these fail instead. They are among the
  private-vcrpy dependencies the ``vcrpy>=8.2,<8.4`` pin in ``pyproject.toml``
  exists for.

  Which stubs those are is not obvious and is easy to get wrong: **no fixture
  here replays on aiohttp.** The sync Azure fixtures ride azure-core's default
  ``RequestsTransport``; the async pair inject ``AsyncioRequestsTransport``,
  which runs ``requests``/urllib3 in a thread pool, because vcrpy's aiohttp
  stub deadlocks on a streamed body (see ``azure_replay_async.py``). Either
  route lands on urllib3, so the stubs that matter are urllib3 (all Azure) and
  httpx (Graph) — and for async Azure the extra hop is a *thread*, not a
  different stub, which is why the third cell drives the skip across an
  executor boundary instead.
* **The skip cannot be swallowed.** Backends map ``except Exception`` into
  library errors — ``AsyncAzureBackend`` was measured turning vcrpy's
  ``CannotOverwriteExistingCassetteException`` into ``RemoteStoreError`` — so a
  skip raised as an ordinary exception would be translated into a *passing*
  assertion by any cell expecting an error. ``Skipped`` derives from
  ``BaseException``, which is what makes the guard safe rather than merely
  convenient.
* **The bound is the registered cassette directories**, and it can only fail
  silently in one direction: a bound that narrows turns skips into loud vcrpy
  errors, while a bound that widens turns real replay failures into green
  skips. Both directions are asserted.

Real ``vcr.cassette.Cassette`` objects throughout (TESTING.md Rule 6): the
subject is our interaction with vcrpy, and a stub of it would assert only that
we agree with ourselves.

``os_sensitive`` because the guard compares ``path.parent.resolve()`` against
resolved directories and renders its message with ``os.path.relpath`` — both
separator- and casing-sensitive, and both armed in every Windows developer's
replay run, so the Windows CI leg should execute them.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import vcr
from vcr.cassette import Cassette
from vcr.request import Request as VcrRequest

from tests.backends.fixtures._cassette_pytest import (
    _guarded_cassette_dirs,
    _make_missing_cassette_guard,
    install_missing_cassette_guard,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.os_sensitive

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

    The guarded directories stand in for the registered profiles' cassette
    dirs. ``tmp_path / "cassettes" / "azure"`` mirrors the real layout closely
    enough for the rendered skip message to read like a real one; ``tmp_path``
    itself is guarded so the transport cells can drop a cassette at the root.
    ``tmp_path / "unregistered"`` is deliberately *not* guarded.
    """
    dirs = frozenset({tmp_path.resolve(), (tmp_path / "cassettes" / "azure").resolve()})
    guard = _make_missing_cassette_guard(_pristine(), tmp_path, lambda: dirs)
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
        # ``os.path.relpath`` renders the native separator, so the expected
        # string is built the same way rather than spelled with "/".
        assert os.path.join("cassettes", "azure", "TestFoo.test_bar[azure].yaml") in message
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

    def test_cassette_outside_the_registered_dirs_is_not_skipped(self, guarded: Path) -> None:
        """The skip means "a recording is owed", which is only true of registered cassettes.

        A test that manages its own cassette — ``vcr.use_cassette`` with a path
        of its own choosing, as ``test_httpx_streaming_replay.py`` does — keeps
        vcrpy's native failure when that file is missing, because no recording
        session will ever supply it and swallowing it would hide the author's
        own omission.

        This bound is the one thing the class-level patch does not get for
        free. The hook it replaced reached a test only through its parametrize
        id, so an unregistered cassette was never a candidate; the guard has to
        re-derive that from the profiles' ``cassette_dir`` set.
        """
        path = guarded / "unregistered" / "own.yaml"
        path.parent.mkdir(parents=True)
        cassette = _cassette(path)
        assert cassette.can_play_response_for(_request()) is False

    def test_skip_escapes_an_except_exception_mapping_layer(self, guarded: Path) -> None:
        """``except Exception`` must not be able to swallow the guard's skip.

        Every backend wraps its transport in a mapping layer that turns
        arbitrary exceptions into library errors — ``AsyncAzureBackend`` was
        measured turning vcrpy's own exception into ``RemoteStoreError``. A cell
        asserting *some* error would then pass on what is really a skip, which
        is the vacuous-green failure this design exists to avoid.

        This drives the guard through a stand-in for that layer rather than
        asserting ``Skipped``'s ancestry: `issubclass(pytest.skip.Exception,
        BaseException)` is a fact about pytest and stays true however this
        module is rewritten, so it could not fail if the guard were changed to
        raise a plain exception. This can.
        """
        cassette = _cassette(guarded / "cassettes" / "azure" / "swallow.yaml")
        mapped: Exception | None = None
        escaped = False
        try:
            cassette.can_play_response_for(_request())
        # `except Exception` comes *first*, matching a real mapping layer, which
        # has no skip-specific clause. Ordered the other way this cell could
        # never fail on the pytest-side half: if `Skipped` stopped being
        # BaseException-only, a leading `except pytest.skip.Exception` would
        # still intercept it while every backend began swallowing skips.
        except Exception as exc:  # noqa: BLE001 -- stands in for a backend's error mapping
            mapped = exc
        except pytest.skip.Exception:
            escaped = True
        assert mapped is None, f"the guard's skip was swallowed as {type(mapped).__name__}"
        assert escaped, "the guard did not raise at all"

    def test_guarded_dirs_are_the_registered_cassette_dirs(self) -> None:
        """The shipped bound, not the one the other cells inject.

        Every other cell passes ``guarded_dirs`` explicitly, so
        ``_guarded_cassette_dirs`` — the default the guard actually runs with —
        is otherwise reached but never asserted. The asymmetry is what makes
        that worth a cell: a bound that *narrows* fails loudly, because vcrpy
        raises where a skip was expected, but a bound that *widens* is silent.
        Point a profile's ``cassette_dir`` somewhere broader and every sibling
        of a registered cassette becomes skippable, converting real replay
        failures into green skips.

        The assertion is **structural**, against the on-disk layout TEST-007
        mandates, rather than a set equality against the registry. Recomputing
        the implementation's own expression and comparing would be tautological:
        it could only fail if the helper were rewritten to disagree with itself,
        never on a registry-side widening, which is the direction that matters.
        The cassettes root is derived from this file's location, so nothing here
        comes from the code under test.
        """
        cassettes_root = (Path(__file__).resolve().parent.parent / "cassettes").resolve()
        guarded = _guarded_cassette_dirs()
        assert guarded, "no cassette profiles registered"
        for directory in guarded:
            assert directory.parent == cassettes_root, (
                f"{directory} is not a direct child of {cassettes_root}; a guarded directory "
                "that broad makes every cassette under it skippable"
            )
            assert directory.is_dir(), f"{directory} is guarded but does not exist"


@pytest.mark.spec("TEST-007")
class TestGuardCoversEveryReplayTransport:
    """Each path a registered replay fixture actually takes must reach the guard.

    Two stubs and one boundary, which is not the same list as "the transports
    vcrpy supports":

    * **urllib3** — every Azure replay fixture, sync *and* async, by two
      different routes: the sync pair ride azure-core's default
      ``RequestsTransport``, while the async pair inject
      ``AsyncioRequestsTransport`` (``requests``/urllib3 in a thread pool)
      because vcrpy's aiohttp stub deadlocks on a streamed body;
      ``azure_replay_async.py`` records the measurement and says to re-check
      before removing the shim.
    * **httpx** — ``graph_replay``.
    * **an executor boundary** — the extra hop async Azure takes. The stub is
      still urllib3; what is load-bearing is that ``Skipped`` survives the
      worker-thread → future handoff, which nothing else here would catch.

    **No cell drives aiohttp, deliberately.** Nothing in this repo replays
    through it, so a cell there would be a standing false alarm on the one stub
    vcrpy has broken twice (8.1.1, 8.2.0) while telling a maintainer reading
    the pin comment that the stub is load-bearing for us.
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

    def test_skip_crosses_the_executor_boundary(self, guarded: Path) -> None:
        """The async Azure path: raised in a worker thread, awaited on the loop.

        ``AsyncioRequestsTransport`` runs the blocking request in a thread pool
        and awaits the future. ``Skipped`` is a ``BaseException``, and a future
        is free to treat those differently from ordinary exceptions, so the
        handoff is worth asserting rather than assuming — it is the whole async
        Azure replay tier.
        """
        import urllib3

        def _blocking_get() -> None:
            urllib3.PoolManager().request("GET", _UNREACHABLE)

        async def _drive() -> None:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(pool, _blocking_get)

        with (
            pytest.raises(pytest.skip.Exception, match="replay cassette missing"),
            vcr.use_cassette(str(guarded / "threaded.yaml"), record_mode="none"),
        ):
            asyncio.run(_drive())


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
