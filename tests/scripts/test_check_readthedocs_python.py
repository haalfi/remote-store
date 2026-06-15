"""The repo's .readthedocs.yaml must build docs on the primary Python."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_readthedocs_python.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_readthedocs_python", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_readthedocs_python", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_repo_config_is_consistent():
    assert _load().check() is None
