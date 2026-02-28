"""Tests verifying the ext.* namespace contract (ADR-0008).

Ensures all extension modules define ``__all__`` and do not access
private Store/Backend attributes.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

# All extension modules (not __init__.py)
_EXT_DIR = Path(__file__).resolve().parent.parent / "src" / "remote_store" / "ext"
_EXT_MODULES = sorted(p.stem for p in _EXT_DIR.glob("*.py") if p.stem != "__init__" and not p.name.startswith("_"))


@pytest.mark.parametrize("module_name", _EXT_MODULES)
class TestExtensionContract:
    """Verify structural rules for every ext.* module."""

    def test_defines_all(self, module_name: str) -> None:
        """Every extension module must define __all__."""
        try:
            mod = importlib.import_module(f"remote_store.ext.{module_name}")
        except ImportError:
            pytest.skip(f"Optional dependency for ext.{module_name} not installed")
        assert hasattr(mod, "__all__"), f"ext.{module_name} must define __all__"
        assert isinstance(mod.__all__, list | tuple)
        assert len(mod.__all__) > 0, f"ext.{module_name}.__all__ must not be empty"

    def test_no_private_store_access(self, module_name: str) -> None:
        """Extension source must not access private Store/Backend attributes."""
        source_path = _EXT_DIR / f"{module_name}.py"
        tree = ast.parse(source_path.read_text())
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.attr, str) and node.attr.startswith("_"):
                # Allow dunder methods, private helper names within the module,
                # and TYPE_CHECKING-guarded imports (e.g. _store, _errors)
                if node.attr.startswith("__"):
                    continue
                # Check if it's accessing store._backend or similar
                if isinstance(node.value, ast.Name) and node.value.id in ("store", "src_store", "dst_store"):
                    violations.append(f"line {node.lineno}: {node.value.id}.{node.attr}")
        assert not violations, f"ext.{module_name} accesses private Store attributes:\n" + "\n".join(
            f"  {v}" for v in violations
        )
