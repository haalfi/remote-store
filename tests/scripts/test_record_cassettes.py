"""Guard tests for scripts/record_cassettes.py structural assumptions.

``record_cassettes.py`` embeds three kinds of assumptions that can silently
drift when tests or fixtures change:

1. ``cassette_dir`` — must resolve to the same path as ``CASSETTE_DIR_AZURE``
   in ``tests/backends/fixtures/_cassettes.py``.
2. ``_CONFORMANCE`` — must be a real directory on disk.
3. k-filter fixture IDs — each fixture name referenced in ``sync_k`` /
   ``async_k`` / ``replay_k`` must exist as a registered ``BackendFixture``
   name.

Drift in any of these causes the script to silently record or replay against
zero tests (pytest selects nothing and exits 0), which is the hardest class
of failure to notice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def rc():
    """Import ``record_cassettes`` from the scripts directory."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import record_cassettes

    return record_cassettes


class TestAzureBackendConfig:
    def test_cassette_dir_matches_canonical_constant(self, rc):
        """_BACKENDS cassette_dir must equal CASSETTE_DIR_AZURE from _cassettes.py."""
        from tests.backends.fixtures._cassettes import CASSETTE_DIR_AZURE

        script_dir = rc._BACKENDS["azure"]["cassette_dir"].resolve()
        assert script_dir == CASSETTE_DIR_AZURE.resolve(), (
            f"record_cassettes._BACKENDS['azure']['cassette_dir'] ({script_dir}) "
            f"diverges from CASSETTE_DIR_AZURE ({CASSETTE_DIR_AZURE.resolve()}); "
            "keep them in sync"
        )

    def test_conformance_path_is_directory(self, rc):
        """_CONFORMANCE must point at a real directory."""
        path = ROOT / rc._CONFORMANCE
        assert path.is_dir(), f"record_cassettes._CONFORMANCE = {rc._CONFORMANCE!r} is not a directory ({path})"

    def test_sync_k_async_exclusion_relies_on_async_substring(self, rc):
        """sync_k uses 'not async' to exclude the async fixture.

        Two sides of the same invariant are pinned:
        (a) async_k must contain 'async' (fixture rename would break exclusion).
        (b) sync_k must contain 'not async' (clause edit would silently re-include async).
        """
        cfg = rc._BACKENDS["azure"]
        async_name = cfg["async_k"]
        sync_expr = cfg["sync_k"]
        assert "async" in async_name, (
            f"sync_k = {sync_expr!r} excludes async fixtures "
            f"via 'not async', but async_k = {async_name!r} does not contain 'async'; "
            "the exclusion would silently stop working if the fixture is renamed"
        )
        assert "not async" in sync_expr, (
            f"sync_k = {sync_expr!r} no longer contains 'not async'; async fixtures would be included in sync recording"
        )

    def test_k_filter_fixture_ids_are_registered(self, rc):
        """Fixture IDs referenced by k-filters must be in the fixture registry.

        Checked names and which filter they come from:
          - ``azure_live``       : sync_k  (``"azure_live and not async"``)
          - ``azure_live_async`` : async_k (``"azure_live_async"``)
          - ``azure_replay``     : replay_k (``"azure_replay"``, substring-
                                   matches ``azure_replay_async`` too)
        """
        from tests.backends.fixtures import _load_all, all_fixtures

        _load_all()
        registered = {f.name for f in all_fixtures()}
        expected = {"azure_live", "azure_live_async", "azure_replay"}
        missing = expected - registered
        assert not missing, (
            f"Fixture ID(s) referenced by record_cassettes._BACKENDS['azure'] "
            f"k-filters are not in the fixture registry: {sorted(missing)}. "
            "Update scripts/record_cassettes.py or the fixture registration."
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
        cfg["cassette_dir"] = cassette_dir

        monkeypatch.delenv("RS_TEST_LIVE_HNS", raising=False)

        with pytest.raises(SystemExit) as exc:
            rc._preflight_env(cfg)
        assert exc.value.code == 1
        assert sentinel.exists(), "preflight must not touch cassettes on failure"

    def test_preflight_runs_before_delete_step_in_main(self, rc) -> None:
        """main() calls _preflight_env BEFORE the Step 1 delete loop.

        Pins the source order: a future edit that moves the delete back
        above the preflight would re-introduce BUG-212.
        """
        import inspect

        src = inspect.getsource(rc.main)
        preflight_pos = src.find("_preflight_env(")
        delete_pos = src.find("Step 1")
        assert preflight_pos >= 0, "main() must call _preflight_env"
        assert delete_pos >= 0, "main() must contain 'Step 1' section marker"
        assert preflight_pos < delete_pos, (
            "_preflight_env must run BEFORE Step 1 delete (BUG-212); "
            "putting it after re-introduces the wipe-on-misconfig regression"
        )
