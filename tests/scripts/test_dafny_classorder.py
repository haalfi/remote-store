"""Unit tests for scripts/_dafny_classorder.py.

Guards against regex / ``_SPECIAL``-set regressions when Dafny upgrades
rename generated classes.  The helper is pure, so we exercise ``reorder``
directly rather than spawning the script.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "_dafny_classorder.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_dafny_classorder", _SCRIPTS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_dafny_classorder", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
reorder = _mod.reorder


_SCRAMBLED = '''\
"""preamble docstring"""

import foo

class MemoryBackendMinimal(Backend):
    pass

class default__:
    pass

class MemoryBackend(Backend):
    pass

class Option_None:
    pass

class Backend:
    pass

class Result_Ok:
    pass
'''


def test_reorder_canonical_order() -> None:
    """ADT classes come first, then Backend, default__, MemoryBackend, MemoryBackendMinimal."""
    result = reorder(_SCRAMBLED)
    positions = {
        name: result.index(f"class {name}")
        for name in (
            "Option_None",
            "Result_Ok",
            "Backend",
            "default__",
            "MemoryBackend",
            "MemoryBackendMinimal",
        )
    }
    assert positions["Option_None"] < positions["Backend"]
    assert positions["Result_Ok"] < positions["Backend"]
    assert positions["Backend"] < positions["default__"]
    assert positions["default__"] < positions["MemoryBackend"]
    assert positions["MemoryBackend"] < positions["MemoryBackendMinimal"]
    assert result.startswith('"""preamble docstring"""')


def test_reorder_idempotent() -> None:
    once = reorder(_SCRAMBLED)
    twice = reorder(once)
    assert once == twice


def test_reorder_no_classes_passes_through() -> None:
    source = '"""just a docstring"""\n\nimport os\n'
    assert reorder(source) == source


@pytest.mark.parametrize(
    "committed",
    [Path(__file__).resolve().parents[2] / "sdd" / "formal" / "MemoryBackend-py" / "module_.py"],
)
def test_committed_module_is_canonically_ordered(committed: Path) -> None:
    """The checked-in oracle must already be in canonical order so a reviewer
    running the translate wrapper sees no diff from the reorder step."""
    if not committed.exists():
        pytest.skip(f"{committed} not present in this checkout")
    source = committed.read_text(encoding="utf-8")
    assert reorder(source) == source
