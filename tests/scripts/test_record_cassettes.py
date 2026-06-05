"""Guard tests for scripts/record_cassettes.py structural assumptions.

``record_cassettes.py`` embeds assumptions that can silently drift when tests
or fixtures change:

1. ``cassette_dir`` — must resolve to the same path as the matching
   ``CASSETTE_DIR_<BACKEND>`` constant in ``tests/backends/fixtures/_cassettes.py``.
2. ``_CONFORMANCE`` — must be a real directory on disk.
3. k-filter fixture IDs — every fixture-name token in ``sync_k`` / ``async_k`` /
   ``replay_k`` must be a substring of at least one registered ``BackendFixture``
   name (else ``pytest -k`` selects nothing and exits 0 — silent zero-selection).

The registration / cassette-dir guards are parametrized over **every**
``_BACKENDS`` key, so a future backend addition cannot drift silently.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"

# Module-level import so the per-backend parametrize lists derive from the live
# _BACKENDS table (drift-proof: a new backend is covered automatically).
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import record_cassettes as _rc  # noqa: E402

_ALL_BACKENDS = sorted(_rc._BACKENDS)

# Each backend's cassette_dir must equal this constant from _cassettes.py.
_CASSETTE_DIR_CONSTANT = {"azure": "CASSETTE_DIR_AZURE", "graph": "CASSETTE_DIR_GRAPH"}

# pytest -k expression keywords that are not fixture-name tokens.
_K_KEYWORDS = frozenset({"and", "or", "not"})


@pytest.fixture(scope="module")
def rc():
    """Import ``record_cassettes`` from the scripts directory."""
    return _rc


def _k_fixture_tokens(expr: str) -> list[str]:
    """Identifier tokens in a ``-k`` expression, minus the and/or/not keywords."""
    return [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr) if t not in _K_KEYWORDS]


class TestBackendConfigTable:
    """Structural guards parametrized over every _BACKENDS entry."""

    @pytest.mark.parametrize("backend", _ALL_BACKENDS)
    def test_cassette_dir_matches_canonical_constant(self, rc, backend: str) -> None:
        """_BACKENDS cassette_dir must equal the backend's CASSETTE_DIR_* constant."""
        import tests.backends.fixtures._cassettes as cassettes

        constant_name = _CASSETTE_DIR_CONSTANT.get(backend)
        assert constant_name is not None, (
            f"no cassette-dir constant mapped for backend {backend!r}; "
            "add it to _CASSETTE_DIR_CONSTANT when registering a new backend"
        )
        expected = getattr(cassettes, constant_name).resolve()
        script_dir = rc._BACKENDS[backend]["cassette_dir"].resolve()
        assert script_dir == expected, (
            f"record_cassettes._BACKENDS[{backend!r}]['cassette_dir'] ({script_dir}) "
            f"diverges from {constant_name} ({expected}); keep them in sync"
        )

    @pytest.mark.parametrize("backend", _ALL_BACKENDS)
    def test_k_filter_fixture_ids_are_registered(self, rc, backend: str) -> None:
        """Every fixture token in a backend's k-filters resolves to a registered fixture.

        ``pytest -k`` matches fixture names by substring, so each token must be a
        substring of at least one registered ``BackendFixture`` name. A renamed
        or removed fixture makes its token match nothing — the silent
        zero-selection failure this guard exists to catch.
        """
        from tests.backends.fixtures import _load_all, all_fixtures

        _load_all()
        registered = [f.name for f in all_fixtures()]
        cfg = rc._BACKENDS[backend]
        for key in ("sync_k", "async_k", "replay_k"):
            expr = cfg[key]
            if not expr:  # sync_k is None for async-only backends
                continue
            for token in _k_fixture_tokens(expr):
                assert any(token in name for name in registered), (
                    f"record_cassettes._BACKENDS[{backend!r}][{key!r}] token {token!r} "
                    f"matches no registered fixture; update the script or the fixture registration"
                )

    @pytest.mark.parametrize("backend", _ALL_BACKENDS)
    def test_setup_doc_exists(self, rc, backend: str) -> None:
        """Each backend's preflight setup_doc must point at a real guide on disk."""
        doc = ROOT / rc._BACKENDS[backend]["setup_doc"]
        assert doc.is_file(), f"_BACKENDS[{backend!r}]['setup_doc'] = {doc} does not exist"

    def test_conformance_path_is_directory(self, rc) -> None:
        """_CONFORMANCE must point at a real directory."""
        path = ROOT / rc._CONFORMANCE
        assert path.is_dir(), f"record_cassettes._CONFORMANCE = {rc._CONFORMANCE!r} is not a directory ({path})"


class TestAzureSyncExclusion:
    """Azure-specific: the sync/async k-filter split relies on a 'not async' clause."""

    def test_sync_k_async_exclusion_relies_on_async_substring(self, rc) -> None:
        """sync_k uses 'not async' to exclude the async fixture (azure has both lanes).

        (a) async_k must contain 'async' (fixture rename would break exclusion).
        (b) sync_k must contain 'not async' (clause edit would silently re-include async).
        """
        cfg = rc._BACKENDS["azure"]
        async_name = cfg["async_k"]
        sync_expr = cfg["sync_k"]
        assert "async" in async_name, (
            f"sync_k = {sync_expr!r} excludes async fixtures via 'not async', but "
            f"async_k = {async_name!r} does not contain 'async'; exclusion would silently break on rename"
        )
        assert "not async" in sync_expr, (
            f"sync_k = {sync_expr!r} no longer contains 'not async'; async fixtures would be included in sync recording"
        )


class TestResolveGraphDriveId:
    """The graph account_fn resolves GRAPH_DRIVE_ID for the scrub-leak check."""

    def test_returns_drive_id_when_set(self, rc, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GRAPH_DRIVE_ID", "b!drive-xyz")
        assert rc._resolve_graph_drive_id() == "b!drive-xyz"

    def test_dies_when_missing(self, rc, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GRAPH_DRIVE_ID", raising=False)
        with pytest.raises(SystemExit) as exc:
            rc._resolve_graph_drive_id()
        assert exc.value.code == 1


class TestMainAsyncOnlyBackend:
    """An async-only backend (sync_k=None) skips the Step-2 sync recording in main()."""

    def test_sync_record_step_is_skipped(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # Drive main() down the full record path for graph, capturing each
        # pytest invocation so we can assert the sync record step never runs.
        monkeypatch.setattr(sys, "argv", ["record_cassettes.py", "--backend", "graph"])
        monkeypatch.setenv("GRAPH_DRIVE_ID", "b!drive-xyz")
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        runs: list[tuple[str, ...]] = []
        monkeypatch.setattr(rc, "_run", lambda *args: runs.append(args))
        graph_cfg = dict(rc._BACKENDS["graph"])
        graph_cfg["cassette_dir"] = tmp_path  # empty → min_cassettes=0 passes, scrub-verify clean
        monkeypatch.setitem(rc._BACKENDS, "graph", graph_cfg)

        rc.main()

        k_values = [args[args.index("-k") + 1] for args in runs if "-k" in args]
        # Async record (Step 3) + replay smoke (Step 5) only — no sync record (Step 2).
        assert k_values == ["graph_live", "graph_replay"]
        assert all("not async" not in k for k in k_values)


class TestPreflightEnvGuard:
    """BUG-212: env validation must precede the destructive Step 1 delete.

    Before the guard landed, ``record_cassettes.py`` would unlink every
    cassette under ``tests/backends/cassettes/<backend>/`` before pytest
    failed on the missing opt-in flag. Recovery relied on the cassettes
    being checked in.
    """

    def test_preflight_fails_when_opt_in_missing(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """No RS_TEST_LIVE_HNS → _preflight_env exits non-zero; cassettes intact."""
        cassette_dir = tmp_path / "cassettes"
        cassette_dir.mkdir()
        sentinel = cassette_dir / "sentinel.yaml"
        sentinel.write_bytes(b"interactions: []\n")

        cfg = dict(rc._BACKENDS["azure"])
        cfg["cassette_dir"] = cassette_dir

        monkeypatch.delenv("RS_TEST_LIVE_HNS", raising=False)

        with pytest.raises(SystemExit) as exc:
            rc._preflight_env(cfg, verify_only=False)
        assert exc.value.code == 1
        assert sentinel.exists(), "preflight must not touch cassettes on failure"

    def test_preflight_noop_in_verify_only(self, rc, monkeypatch: pytest.MonkeyPatch) -> None:
        """--verify-only must not require live creds: no delete to protect, Step 4 calls account_fn itself.

        Regression guard for the PR #645 review finding: making preflight
        unconditional broke the documented "skip recording; run only
        scrub-verify + replay smoke" workflow.
        """
        monkeypatch.delenv("RS_TEST_LIVE_HNS", raising=False)
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
        cfg = dict(rc._BACKENDS["azure"])
        # account_fn should NOT be invoked in verify_only mode; replace it
        # with a sentinel that flips a flag iff called.
        called = {"count": 0}

        def _sentinel_account_fn() -> str:
            called["count"] += 1
            return "should-not-be-reached"

        cfg["account_fn"] = _sentinel_account_fn

        result = rc._preflight_env(cfg, verify_only=True)
        assert result is None, "_preflight_env returns None on the no-op path"
        assert called["count"] == 0, "account_fn must not run in verify_only (Step 4 calls it itself)"

    def test_preflight_runs_before_delete_step_in_main(self, rc) -> None:
        """main() calls _preflight_env BEFORE the Step 1 delete loop.

        Pins the source order: a future edit that moves the delete back
        above the preflight would re-introduce BUG-212.

        Targets the full ``"Step 1 — delete"`` section marker, not a bare
        ``"Step 1"`` substring: the ``--node`` help text and the single-mode
        ``"Step 1-3"`` section header both contain ``"Step 1"`` and appear
        before the preflight call, so the loose substring would match those
        instead of the destructive delete loop.
        """
        import inspect

        src = inspect.getsource(rc.main)
        preflight_pos = src.find("_preflight_env(")
        delete_pos = src.find("Step 1 — delete")
        assert preflight_pos >= 0, "main() must call _preflight_env"
        assert delete_pos >= 0, "main() must contain the 'Step 1 — delete' section marker"
        assert preflight_pos < delete_pos, (
            "_preflight_env must run BEFORE Step 1 delete (BUG-212); "
            "putting it after re-introduces the wipe-on-misconfig regression"
        )
