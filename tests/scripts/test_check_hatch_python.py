"""The local gate must run on the primary Python (.python-version)."""

from __future__ import annotations

import importlib.util
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
