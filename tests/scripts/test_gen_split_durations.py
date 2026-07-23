"""Unit tests for scripts/gen_split_durations.py (BK-319 shard-balancing tool).

The generator records ``setup + call + teardown`` wall time per test and
writes it in the pytest-split durations format (``{nodeid: seconds}``).
Two behaviours carry the whole point of the script and are guarded here:

  * **Phase summation.** ``_TotalDurations`` accumulates every phase's
    ``report.duration`` with ``+=``. A regression to ``=`` would silently
    degrade the file to *teardown-only* weights — the exact call/teardown
    mis-balance BK-319 exists to correct. ``TestPhaseSummation`` fails if
    that ``+=`` ever becomes ``=``.
  * **Output contract.** The written JSON is exactly ``{nodeid: float}``,
    the shape pytest-split's ``--durations-path`` loader consumes.

The script carries no spec ID, so — like ``test_check_no_tracker_refs.py``
and ``test_check_ci_inventory.py`` — these tests carry no ``@pytest.mark.spec``.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_split_durations.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_split_durations", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gen_split_durations", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _report(nodeid: str, when: str, duration: float) -> types.SimpleNamespace:
    """A stand-in for ``pytest.TestReport`` — the plugin reads only these two
    attributes, so a namespace is a truthful (spec-free, Rule 6) fixture."""
    return types.SimpleNamespace(nodeid=nodeid, when=when, duration=duration)


def _session(*, worker: bool) -> types.SimpleNamespace:
    """A stand-in for ``pytest.Session``. The plugin's only decision is
    ``hasattr(session.config, "workerinput")`` — present on an xdist worker,
    absent on the controller. Model exactly that surface."""
    config = types.SimpleNamespace(workerinput={}) if worker else types.SimpleNamespace()
    return types.SimpleNamespace(config=config)


def _run_plugin(out_path: Path, reports, *, worker: bool = False) -> None:
    """Feed a sequence of phase reports through the plugin and finish the session."""
    plugin = _mod._TotalDurations(str(out_path))
    for rep in reports:
        plugin.pytest_runtest_logreport(rep)
    plugin.pytest_sessionfinish(_session(worker=worker), 0)


# ---------------------------------------------------------------------------
# Phase summation — the BK-319 invariant (guards += vs =)
# ---------------------------------------------------------------------------


class TestPhaseSummation:
    """A node's recorded weight must be setup + call + teardown, never one phase."""

    def test_duration_is_sum_of_all_three_phases(self, tmp_path):
        out = tmp_path / "durations.json"
        node = "tests/test_x.py::test_thing"
        # Deliberately asymmetric so no single phase equals the sum, and the
        # call phase (0.20) is NOT the largest — a =-mutation would keep only
        # teardown (0.04) and miss the sum by an order of magnitude.
        _run_plugin(
            out,
            [
                _report(node, "setup", 0.10),
                _report(node, "call", 0.20),
                _report(node, "teardown", 0.04),
            ],
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert math.isclose(data[node], 0.34, rel_tol=0, abs_tol=1e-9)  # 0.10 + 0.20 + 0.04
        # Strictly greater than the largest single phase (0.20): proves the
        # value is a SUM, not any one phase left standing by a `=` regression.
        assert data[node] > 0.20

    def test_nodes_accumulate_independently(self, tmp_path):
        out = tmp_path / "durations.json"
        _run_plugin(
            out,
            [
                _report("t::a", "setup", 0.01),
                _report("t::a", "call", 0.02),
                _report("t::a", "teardown", 0.03),
                _report("t::b", "setup", 0.10),
                _report("t::b", "call", 0.20),
                _report("t::b", "teardown", 0.30),
            ],
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert math.isclose(data["t::a"], 0.06, abs_tol=1e-9)
        assert math.isclose(data["t::b"], 0.60, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Output contract — {nodeid: float}, controller-only write
# ---------------------------------------------------------------------------


class TestOutputContract:
    def test_written_file_is_json_mapping_nodeid_to_float(self, tmp_path):
        out = tmp_path / "durations.json"
        _run_plugin(
            out,
            [
                _report("tests/test_a.py::test_one", "call", 1.5),
                _report("tests/test_b.py::test_two", "call", 2.0),
            ],
        )
        raw = out.read_text(encoding="utf-8")
        data = json.loads(raw)  # must be valid JSON
        assert isinstance(data, dict)
        assert set(data) == {"tests/test_a.py::test_one", "tests/test_b.py::test_two"}
        assert all(isinstance(k, str) and "::" in k for k in data)
        assert all(isinstance(v, float) for v in data.values())

    def test_empty_run_writes_empty_object(self, tmp_path):
        # No reports at all (nothing collected) still yields a valid, loadable
        # file — pytest-split's loader must not choke on the no-match case.
        out = tmp_path / "durations.json"
        _run_plugin(out, [])
        assert json.loads(out.read_text(encoding="utf-8")) == {}

    def test_xdist_worker_does_not_write(self, tmp_path):
        # Only the controller (no ``workerinput``) writes the merged file; a
        # worker writing would race and clobber the controller's output.
        out = tmp_path / "durations.json"
        _run_plugin(out, [_report("t::a", "call", 0.5)], worker=True)
        assert not out.exists()

    def test_controller_writes(self, tmp_path):
        out = tmp_path / "durations.json"
        _run_plugin(out, [_report("t::a", "call", 0.5)], worker=False)
        assert out.exists()


# ---------------------------------------------------------------------------
# main() — argv handling and exit-code propagation
# ---------------------------------------------------------------------------


class TestMainArgHandling:
    @pytest.mark.parametrize("argv", [["prog"], []])
    def test_too_few_args_returns_2(self, argv, capsys):
        # Missing output path (or missing everything) is a usage error, not a
        # pytest run — it must not fall through to pytest.main.
        assert _mod.main(argv) == 2
        assert "durations" in capsys.readouterr().err.lower()

    @pytest.mark.parametrize("exit_code", [0, 1, 2, 5])
    def test_propagates_pytest_exit_code(self, exit_code, tmp_path, monkeypatch):
        # main returns whatever pytest.main returned (5 = no tests collected).
        captured: dict[str, object] = {}

        def _fake_main(args, plugins):
            captured["args"] = args
            captured["plugins"] = plugins
            return exit_code

        monkeypatch.setattr(_mod.pytest, "main", _fake_main)
        rc = _mod.main(["prog", str(tmp_path / "d.json"), "tests/"])
        assert rc == exit_code
        assert isinstance(rc, int)
        # The plugin the run installs is our summing plugin.
        assert isinstance(captured["plugins"][0], _mod._TotalDurations)

    def test_strips_leading_double_dash_separator(self, tmp_path, monkeypatch):
        # ``main([prog, out, '--', ...pytestargs])`` forwards pytest args with
        # the ``--`` separator removed, so pytest never sees a stray ``--``.
        captured: dict[str, object] = {}

        def _fake_main(args, plugins):
            captured["args"] = args
            return 0

        monkeypatch.setattr(_mod.pytest, "main", _fake_main)
        _mod.main(["prog", str(tmp_path / "d.json"), "--", "-k", "foo", "tests/"])
        assert captured["args"] == ["-k", "foo", "tests/"]

    def test_forwards_pytest_args_without_separator_unchanged(self, tmp_path, monkeypatch):
        # A leading arg that is not ``--`` is passed through verbatim.
        captured: dict[str, object] = {}

        def _fake_main(args, plugins):
            captured["args"] = args
            return 0

        monkeypatch.setattr(_mod.pytest, "main", _fake_main)
        _mod.main(["prog", str(tmp_path / "d.json"), "-k", "foo"])
        assert captured["args"] == ["-k", "foo"]


# ---------------------------------------------------------------------------
# Integration — a real nested pytest run through main()
# ---------------------------------------------------------------------------


_SLEEP_TEST = """
import time
import pytest


@pytest.fixture
def slow():
    time.sleep(0.05)   # setup phase
    yield
    time.sleep(0.05)   # teardown phase


def test_body(slow):
    time.sleep(0.05)   # call phase
"""


# The nested pytest session runs in-process, so it re-loads whatever plugins
# are installed (pytest-asyncio, pytest-randomly, ...). Disable the ones that
# only add noise, and reset the warnings posture to ``default`` so a plugin's
# configure-time DeprecationWarning is not turned into an error by the OUTER
# session's ``filterwarnings = error`` (which would abort the nested run).
_NESTED_ARGS = ["-p", "no:cacheprovider", "-p", "no:asyncio", "-p", "no:randomly", "-W", "default", "-q"]


class TestIntegration:
    """Drive ``main()`` end to end against a throwaway test module. tmp_path is
    outside the repo, so the nested pytest session gets its own rootdir and does
    not inherit this project's addopts/conftest."""

    def test_real_run_records_summed_wall_time_and_valid_contract(self, tmp_path):
        test_file = tmp_path / "test_throwaway.py"
        test_file.write_text(_SLEEP_TEST, encoding="utf-8")
        out = tmp_path / "durations.json"

        rc = _mod.main(["prog", str(out), "--", *_NESTED_ARGS, str(test_file)])

        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        # Exactly one collected test, keyed by its nodeid, valued by a float.
        assert len(data) == 1
        ((nodeid, seconds),) = data.items()
        assert nodeid.endswith("::test_body")
        assert isinstance(seconds, float)
        # setup(0.05) + call(0.05) + teardown(0.05) = 0.15 wall-clock floor.
        # A `=`-mutation would record teardown only (~0.05) and fall below 0.12.
        assert seconds >= 0.13

    def test_no_match_propagates_exit_5_and_writes_valid_json(self, tmp_path):
        # A run that collects nothing (empty directory) still writes a loadable
        # file and propagates pytest's EXIT_NOTESTSCOLLECTED (5).
        empty = tmp_path / "empty"
        empty.mkdir()
        out = tmp_path / "durations.json"

        rc = _mod.main(["prog", str(out), "--", *_NESTED_ARGS, str(empty)])

        assert rc == 5  # pytest EXIT_NOTESTSCOLLECTED
        assert json.loads(out.read_text(encoding="utf-8")) == {}
