"""ci-full.yml's test-full matrix must equal ci.yml's ALL_PYTHONS (BK-319).

The gate keeps the two executable copies of the supported-interpreter matrix
honest. The live repo must pass its own gate; synthetic pass/fail cases feed
crafted workflow files through ``check(ci, ci_full)`` so the tests stay stable
as interpreters are added or dropped.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "check_ci_full_matrix.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_ci_full_matrix", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_ci_full_matrix", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _write_ci(directory: Path, all_pythons: str) -> Path:
    """A minimal ci.yml whose setup job carries an ALL_PYTHONS env step."""
    path = directory / "ci.yml"
    path.write_text(
        "name: CI\n"
        "on:\n  push:\n"
        "jobs:\n"
        "  setup:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "      - name: Resolve Python versions\n"
        "        env:\n"
        f"          ALL_PYTHONS: '{all_pythons}'\n"
        '          MIN_PYTHON: "3.10"\n'
        "        run: echo hi\n",
        encoding="utf-8",
    )
    return path


def _write_ci_full(directory: Path, versions: str) -> Path:
    """A minimal ci-full.yml whose test-full job carries a python-version matrix."""
    path = directory / "ci-full.yml"
    path.write_text(
        "name: CI Full\n"
        "on:\n  schedule:\n    - cron: '0 5 * * 6'\n"
        "jobs:\n"
        "  test-full:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      matrix:\n"
        f"        python-version: {versions}\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


class TestParsing:
    def test_all_pythons_json_array_is_parsed(self, tmp_path):
        ci = _write_ci(tmp_path, '["3.10", "3.11", "3.12"]')
        assert _mod._all_pythons(ci) == {"3.10", "3.11", "3.12"}

    def test_test_full_matrix_yaml_list_is_parsed(self, tmp_path):
        ci_full = _write_ci_full(tmp_path, '["3.10", "3.11", "3.12"]')
        assert _mod._test_full_matrix(ci_full) == {"3.10", "3.11", "3.12"}

    def test_missing_all_pythons_env_raises(self, tmp_path):
        # A setup job with no ALL_PYTHONS env is an unparseable copy: raising is
        # itself a lint failure (precedent: check_readthedocs_python.py).
        path = tmp_path / "ci.yml"
        path.write_text(
            "on:\n  push:\njobs:\n  setup:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
            encoding="utf-8",
        )
        with pytest.raises(KeyError, match="ALL_PYTHONS"):
            _mod._all_pythons(path)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


class TestCheck:
    def test_matching_sets_pass(self, tmp_path):
        ci = _write_ci(tmp_path, '["3.10", "3.11", "3.12"]')
        ci_full = _write_ci_full(tmp_path, '["3.10", "3.11", "3.12"]')
        assert _mod.check(ci, ci_full) is None

    def test_order_insensitive(self, tmp_path):
        ci = _write_ci(tmp_path, '["3.10", "3.11", "3.12"]')
        ci_full = _write_ci_full(tmp_path, '["3.12", "3.10", "3.11"]')
        assert _mod.check(ci, ci_full) is None

    def test_dropped_interpreter_in_ci_full_fails(self, tmp_path):
        ci = _write_ci(tmp_path, '["3.10", "3.11", "3.12", "3.13", "3.14"]')
        ci_full = _write_ci_full(tmp_path, '["3.10", "3.11", "3.12", "3.13"]')
        error = _mod.check(ci, ci_full)
        assert error is not None
        assert "ci.yml" in error
        assert "ci-full.yml" in error
        assert "3.14" in error

    def test_added_interpreter_in_ci_full_fails(self, tmp_path):
        ci = _write_ci(tmp_path, '["3.10", "3.11"]')
        ci_full = _write_ci_full(tmp_path, '["3.10", "3.11", "3.12"]')
        error = _mod.check(ci, ci_full)
        assert error is not None
        assert "3.12" in error


# --------------------------------------------------------------------------- #
# The live repo must pass its own gate
# --------------------------------------------------------------------------- #


def test_repo_matrix_is_honest():
    assert _mod.check() is None
