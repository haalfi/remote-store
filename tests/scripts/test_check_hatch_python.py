"""The local gate must run on the primary Python (.python-version)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "check_hatch_python.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_hatch_python", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_hatch_python", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_PYPROJECT = '[tool.hatch.envs.default]\ninstaller = "uv"\npython = "{v}"\n'


def test_repo_pin_matches_python_version():
    mod = _load()
    assert mod.check_pin(mod.read_pin(), mod.read_primary()) is None


def test_pin_mismatch_names_both_values():
    mod = _load()
    pin = mod.pin_from_toml(_PYPROJECT.format(v="3.12"))
    assert (
        mod.check_pin(pin, "3.13") == "pyproject.toml [tool.hatch.envs.default] python '3.12' != .python-version '3.13'"
    )


def test_pin_compares_major_minor_only():
    mod = _load()
    assert mod.check_pin(mod.pin_from_toml(_PYPROJECT.format(v="3.13")), "3.13.5") is None


def test_missing_pin_is_reported():
    mod = _load()
    pin = mod.pin_from_toml('[tool.hatch.envs.default]\ninstaller = "uv"\n')
    assert (
        mod.check_pin(pin, "3.13")
        == "pyproject.toml [tool.hatch.envs.default] sets no python; .python-version is '3.13'"
    )


def test_interpreter_mismatch_names_remedy():
    """A stale env keeps its old interpreter after the pin changes (measured with hatch)."""
    mod = _load()
    msg = mod.check_interpreter((3, 11), "3.13")
    assert msg is not None
    assert "running on Python 3.11, .python-version is '3.13'" in msg
    assert "hatch env remove default" in msg


def test_interpreter_match_passes():
    mod = _load()
    assert mod.check_interpreter((3, 13), "3.13") is None


def test_main_fails_off_the_primary(capsys):
    """``main`` runs both checks on the real pin and exits 1 with the remedy for a stale interpreter.

    In-process with an injected version, because CI runs ``tests/scripts/`` only on
    the primary Python (``tooling-tests``), where a subprocess never takes this path.
    """
    mod = _load()
    assert mod.main((2, 7)) == 1  # never a primary
    err = capsys.readouterr().err
    assert f"error: running on Python 2.7, .python-version is {mod.read_primary()!r}" in err
    assert "hatch env remove default" in err


def test_main_pin_mismatch_does_not_prescribe_a_rebuild(capsys, monkeypatch):
    """A wrong pin is the fault to fix: rebuilding the env on it would change nothing."""
    mod = _load()
    major, minor = (int(p) for p in mod.read_pin().split(".")[:2])
    primary = f"{major}.{minor + 1}"  # differs from any real pin; the env runs on the pin
    monkeypatch.setattr(mod, "read_primary", lambda: primary)
    assert mod.main((major, minor)) == 1
    err = capsys.readouterr().err
    assert f"!= .python-version {primary!r}" in err
    assert "running on Python" not in err
    assert "hatch env remove default" not in err


def test_main_passes_on_the_primary(capsys):
    mod = _load()
    major, minor = (int(p) for p in mod.read_primary().split(".")[:2])
    assert mod.main((major, minor)) == 0
    assert capsys.readouterr().err == ""


def test_entry_point_gates_on_the_running_interpreter():
    """End to end: ``__main__`` passes the real interpreter to ``main`` and exits with its code.

    CI runs this only on the primary Python (``tooling-tests``), so there it pins the
    exit-0 path; the mismatch path is pinned in-process by ``test_main_fails_off_the_primary``.
    Run on another interpreter, it checks the exit-1 path end to end.
    """
    primary = _load().read_primary()
    on_primary = f"{sys.version_info[0]}.{sys.version_info[1]}" == ".".join(primary.split(".")[:2])
    result = subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=False)  # noqa: S603
    if on_primary:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
    else:
        assert result.returncode == 1
        assert f"running on Python {sys.version_info[0]}.{sys.version_info[1]}" in result.stderr
        assert "hatch env remove default" in result.stderr
