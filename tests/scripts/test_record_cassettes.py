"""Guard tests for scripts/record_cassettes.py structural assumptions.

``record_cassettes.py`` embeds assumptions that can silently drift when tests
or fixtures change:

1. ``_PROFILES`` — every ``_BACKENDS`` key must map to the matching
   ``CassetteProfile`` (the single source for cassette dirs and scrub/audit
   knowledge, spec 049).
2. ``_CONFORMANCE`` — must be a real directory on disk.
3. k-filter fixture IDs — every fixture-name token in ``sync_k`` / ``async_k`` /
   ``replay_k`` must be a substring of at least one registered ``BackendFixture``
   name (else ``pytest -k`` selects nothing and exits 0 — silent zero-selection).

Plus the Step-4 gates: the forbidden-pattern byte scan and the named-rule
audit (REC-006) that fails a full recording when a required-to-fire rule
never fired.

The registration / profile guards are parametrized over **every**
``_BACKENDS`` key, so a future backend addition cannot drift silently.
"""

from __future__ import annotations

import dataclasses
import json
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

# pytest -k expression keywords that are not fixture-name tokens.
_K_KEYWORDS = frozenset({"and", "or", "not"})


@pytest.fixture(scope="module")
def rc():
    """Import ``record_cassettes`` from the scripts directory."""
    return _rc


def _redirect_profile_dir(monkeypatch: pytest.MonkeyPatch, backend: str, cassette_dir: Path) -> None:
    """Point *backend*'s profile at *cassette_dir* (frozen dataclass → replace)."""
    profile = dataclasses.replace(_rc._PROFILES[backend], cassette_dir=cassette_dir)
    monkeypatch.setitem(_rc._PROFILES, backend, profile)


def _k_fixture_tokens(expr: str) -> list[str]:
    """Identifier tokens in a ``-k`` expression, minus the and/or/not keywords."""
    return [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr) if t not in _K_KEYWORDS]


class TestBackendConfigTable:
    """Structural guards parametrized over every _BACKENDS entry."""

    @pytest.mark.parametrize("backend", _ALL_BACKENDS)
    def test_backend_has_matching_profile(self, rc, backend: str) -> None:
        """Every _BACKENDS key maps to the profile of the same backend family.

        The profile is the single source for the cassette directory and the
        Step-4 gate set; a key without one would crash main() at lookup.
        """
        profile = rc._PROFILES.get(backend)
        assert profile is not None, (
            f"no cassette profile mapped for backend {backend!r}; add it to _PROFILES when registering a new backend"
        )
        assert profile.backend == backend
        assert profile.cassette_dir.is_dir(), f"{profile.cassette_dir} does not exist"

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
        # The resolver lazily loads .env (so --verify-only resolves the drive id
        # without the recording preflight); no-op it so a developer's real .env
        # cannot repopulate GRAPH_DRIVE_ID and mask the missing-var death path.
        monkeypatch.setattr("dotenv.load_dotenv", lambda **_: None)
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
        monkeypatch.setattr(rc, "_audit_named_rules", lambda profile, manifest_base: None)
        monkeypatch.chdir(tmp_path)  # manifest files land in tmp_path/tmp/
        runs: list[tuple[str, ...]] = []
        monkeypatch.setattr(rc, "_run", lambda *args: runs.append(args))
        _redirect_profile_dir(monkeypatch, "graph", tmp_path)  # empty dir → scrub-verify clean
        # _run is mocked, so no cassettes are written; pin the floor to 0 here so
        # this test exercises the Step-2-skip path independent of the production
        # min_cassettes value (which the count-guard test owns).
        graph_cfg = dict(rc._BACKENDS["graph"])
        graph_cfg["min_cassettes"] = 0
        monkeypatch.setitem(rc._BACKENDS, "graph", graph_cfg)

        rc.main()

        k_values = [args[args.index("-k") + 1] for args in runs if "-k" in args]
        # Async record (Step 3) + replay smoke (Step 5) only — no sync record (Step 2).
        assert k_values == ["graph_live", "graph_replay"]
        assert all("not async" not in k for k in k_values)

    def test_count_guard_fails_when_fewer_than_min_recorded(
        self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A non-zero ``min_cassettes`` floor makes a zero-selection record run
        fail loudly (audit-016 H2): with ``_run`` mocked nothing is written, so the
        empty cassette dir falls below the floor and ``main()`` exits non-zero
        rather than printing "All steps passed". Uses its own floor so the guard
        mechanism is tested independent of the production graph value."""
        monkeypatch.setattr(sys, "argv", ["record_cassettes.py", "--backend", "graph"])
        monkeypatch.setenv("GRAPH_DRIVE_ID", "b!drive-xyz")
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        monkeypatch.setattr(rc, "_run", lambda *args: None)
        monkeypatch.chdir(tmp_path)
        _redirect_profile_dir(monkeypatch, "graph", tmp_path)  # empty → 0 recorded
        graph_cfg = dict(rc._BACKENDS["graph"])
        graph_cfg["min_cassettes"] = 5
        monkeypatch.setitem(rc._BACKENDS, "graph", graph_cfg)

        with pytest.raises(SystemExit) as exc:
            rc.main()
        assert exc.value.code == 1

    def test_step4_fails_on_forbidden_pii_marker(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Step-4 enforces the scrub layer's broader PII guarantee, not just the
        drive id. A cassette carrying the pre-signed ``docID`` site GUID (a
        Graph forbidden-pattern addition) makes ``main()`` exit non-zero even
        though the account name itself is absent — so a re-record cannot
        silently reintroduce it."""
        # --verify-only skips the Step-1 delete (and Steps 2-3 / count guard), so
        # the seeded leaky cassette survives to Step 4 — the gate under test.
        monkeypatch.setattr(sys, "argv", ["record_cassettes.py", "--backend", "graph", "--verify-only"])
        monkeypatch.setenv("GRAPH_DRIVE_ID", "b!drive-xyz")
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        monkeypatch.setattr(rc, "_run", lambda *args: None)
        leaky = tmp_path / "leaky.yaml"
        # docID site-collection GUID, no drive id → only the forbidden marker trips.
        leaky.write_bytes(
            b"headers:\n  docID:\n  - my.microsoftpersonalcontent.com_"
            b"52b575dd-9200-466f-a853-18401ad957cb_6a30444f-3aac-4f4c-a049-deadbeef\n"
        )
        _redirect_profile_dir(monkeypatch, "graph", tmp_path)

        with pytest.raises(SystemExit) as exc:
            rc.main()
        assert exc.value.code == 1


class TestNamedRuleAudit:
    """REC-006: the Step-4 named-rule audit gates required-to-fire rules at zero."""

    def test_aggregate_manifest_sums_step_and_worker_files(self, rc, tmp_path: Path) -> None:
        base = tmp_path / "scrub-manifest-graph"
        (tmp_path / "scrub-manifest-graph-sync.json").write_text(json.dumps({"graph.drive-id": 2}))
        (tmp_path / "scrub-manifest-graph-async.json.gw0").write_text(
            json.dumps({"graph.drive-id": 3, "graph.body.download-url": 1})
        )
        assert rc._aggregate_manifest(base) == {"graph.drive-id": 5, "graph.body.download-url": 1}

    def test_aggregate_manifest_returns_none_without_files(self, rc, tmp_path: Path) -> None:
        assert rc._aggregate_manifest(tmp_path / "scrub-manifest-graph") is None

    def test_audit_dies_when_required_rule_never_fired(self, rc, tmp_path: Path) -> None:
        """Zero fires on a required-to-fire rule means the scrub layer silently
        stopped seeing the value it owns — the audit must refuse the corpus."""
        base = tmp_path / "scrub-manifest-graph"
        counts = {name: 1 for name, _ in rc._PROFILES["graph"].named_rules()}
        counts["graph.drive-id"] = 0  # required rule at zero
        (tmp_path / "scrub-manifest-graph-async.json").write_text(json.dumps(counts))
        with pytest.raises(SystemExit) as exc:
            rc._audit_named_rules(rc._PROFILES["graph"], base)
        assert exc.value.code == 1

    def test_audit_passes_when_required_rules_fired(
        self, rc, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Opportunistic rules at zero never gate; required rules >= 1 pass."""
        base = tmp_path / "scrub-manifest-graph"
        counts = {
            name: (1 if expectation == "required-to-fire" else 0)
            for name, expectation in rc._PROFILES["graph"].named_rules()
        }
        (tmp_path / "scrub-manifest-graph-async.json").write_text(json.dumps(counts))
        rc._audit_named_rules(rc._PROFILES["graph"], base)  # must not raise
        out = capsys.readouterr().out
        # Every rule's fire count is printed for the review record.
        assert "graph.drive-id: 1 (required-to-fire)" in out

    def test_audit_dies_when_manifest_missing(self, rc, tmp_path: Path) -> None:
        """A full recording with no manifest is a wiring defect, not a pass."""
        with pytest.raises(SystemExit) as exc:
            rc._audit_named_rules(rc._PROFILES["graph"], tmp_path / "scrub-manifest-graph")
        assert exc.value.code == 1

    def test_verify_only_skips_named_audit(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Fire counts are workload-dependent: without a full recording the
        audit cannot assert anything, so --verify-only (and --node) skip it."""
        monkeypatch.setattr(sys, "argv", ["record_cassettes.py", "--backend", "graph", "--verify-only"])
        monkeypatch.setenv("GRAPH_DRIVE_ID", "b!drive-xyz")
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        monkeypatch.setattr(rc, "_run", lambda *args: None)
        calls = {"count": 0}
        monkeypatch.setattr(
            rc, "_audit_named_rules", lambda profile, manifest_base: calls.__setitem__("count", calls["count"] + 1)
        )
        _redirect_profile_dir(monkeypatch, "graph", tmp_path)  # empty dir → byte scan clean

        rc.main()
        assert calls["count"] == 0


class TestUnraisableScopedToRecording:
    """BK-304: recording subprocesses disable the unraisableexception plugin.

    vcrpy's record-mode transport interception orphans the live SSL sockets it
    wraps; the ``ResourceWarning`` they raise at GC, escalated by pytest's
    ``unraisableexception`` plugin under ``filterwarnings = error``, aborts an
    otherwise-green recording. The recording ``pytest`` invocations carry
    ``-p no:unraisableexception``; the Step-5 replay run (no live sockets) and
    the wider suite must not.
    """

    @staticmethod
    def _has_disable_flag(args: tuple[str, ...]) -> bool:
        """True iff *args* contains the ``-p no:unraisableexception`` pair, in order."""
        for i, tok in enumerate(args):
            if tok == "-p" and i + 1 < len(args) and args[i + 1] == "no:unraisableexception":
                return True
        return False

    def _capture_runs(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, ...]]:
        """Drive a full azure record through main() with _run mocked; return captured argv."""
        monkeypatch.setattr(sys, "argv", ["record_cassettes.py", "--backend", "azure"])
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        monkeypatch.setattr(rc, "_audit_named_rules", lambda profile, manifest_base: None)
        monkeypatch.chdir(tmp_path)
        runs: list[tuple[str, ...]] = []
        monkeypatch.setattr(rc, "_run", lambda *args: runs.append(args))
        _redirect_profile_dir(monkeypatch, "azure", tmp_path)  # empty dir → scrub-verify clean
        # _run is mocked so nothing is written; pin the floor to 0 so the count
        # guard does not exit before Step 5 (the count guard is tested elsewhere).
        azure_cfg = dict(rc._BACKENDS["azure"])
        azure_cfg["min_cassettes"] = 0
        monkeypatch.setitem(rc._BACKENDS, "azure", azure_cfg)
        rc.main()
        return runs

    def test_record_steps_disable_unraisable_but_replay_keeps_it(
        self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Every ``--record`` invocation carries the flag; the replay run does not."""
        runs = self._capture_runs(rc, monkeypatch, tmp_path)

        record_runs = [args for args in runs if "--record" in args]
        replay_runs = [args for args in runs if "--stage=1" in args]
        # Azure has both lanes → two record steps (sync + async); one replay smoke.
        assert len(record_runs) == 2, f"expected sync+async record steps, got {runs}"
        assert len(replay_runs) == 1, f"expected one replay smoke step, got {runs}"
        assert all(self._has_disable_flag(args) for args in record_runs), (
            f"every recording subprocess must disable unraisableexception (BK-304); got {record_runs}"
        )
        assert not self._has_disable_flag(replay_runs[0]), (
            "the Step-5 replay smoke test has no live sockets and must keep the "
            f"unraisableexception guard; got {replay_runs[0]}"
        )

    def test_single_node_record_disables_unraisable(self, rc, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """``--node`` single-cassette recording also records live → must disable the plugin."""
        monkeypatch.setattr(
            sys, "argv", ["record_cassettes.py", "--backend", "azure", "--node", "x::test_y[azure_live]"]
        )
        monkeypatch.setattr(rc, "_preflight_env", lambda cfg, *, verify_only: None)
        monkeypatch.chdir(tmp_path)
        runs: list[tuple[str, ...]] = []
        monkeypatch.setattr(rc, "_run", lambda *args: runs.append(args))
        _redirect_profile_dir(monkeypatch, "azure", tmp_path)

        rc.main()

        record_runs = [args for args in runs if "--record" in args]
        assert len(record_runs) == 1, f"expected one single-node record run, got {runs}"
        assert self._has_disable_flag(record_runs[0]), (
            f"--node recording records live and must disable unraisableexception (BK-304); got {record_runs[0]}"
        )


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
