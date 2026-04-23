"""Tests verifying the ext.* namespace contract (ADR-0008, DESIGN.md § 12).

Ensures all extension modules (sync and async) define ``__all__``, do not
access private Store/Backend attributes, and do not bypass public import paths.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src" / "remote_store"


def _gather(ext_dir: Path, pkg: str) -> list[tuple[Path, str]]:
    """Return (source_path, import_path) for every public module in ext_dir."""
    return [
        (p, f"{pkg}.{p.stem}")
        for p in sorted(ext_dir.glob("*.py"))
        if p.stem != "__init__" and not p.name.startswith("_")
    ]


_ALL_EXT: list[tuple[Path, str]] = _gather(_SRC / "ext", "remote_store.ext") + _gather(
    _SRC / "aio" / "ext", "remote_store.aio.ext"
)
_MODULE_IDS = [imp.removeprefix("remote_store.") for _, imp in _ALL_EXT]


def _is_type_checking_guard(node: ast.If) -> bool:
    """True if this If node is 'if TYPE_CHECKING:'."""
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _collect_type_checking_imports(tree: ast.AST) -> frozenset[int]:
    """Return id() of every import node nested inside an if TYPE_CHECKING: block."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom | ast.Import):
                    guarded.add(id(child))
    return frozenset(guarded)


@pytest.mark.parametrize(("source_path", "module_import"), _ALL_EXT, ids=_MODULE_IDS)
class TestExtensionContract:
    """Verify structural rules for every ext.* and aio.ext.* module."""

    def test_defines_all(self, source_path: Path, module_import: str) -> None:
        """Every extension module must define __all__."""
        try:
            mod = importlib.import_module(module_import)
        except ImportError:
            pytest.skip(f"Optional dependency for {module_import} not installed")
        assert hasattr(mod, "__all__"), f"{module_import} must define __all__"
        assert isinstance(mod.__all__, list | tuple)
        assert len(mod.__all__) > 0, f"{module_import}.__all__ must not be empty"

    def test_no_private_module_imports(self, source_path: Path, module_import: str) -> None:
        """Extension must not use private import paths for public symbols (DESIGN.md § 12)."""
        import remote_store as _rs

        public_names: frozenset[str] = frozenset(_rs.__all__)
        tree = ast.parse(source_path.read_text())
        guarded = _collect_type_checking_imports(tree)
        violations: list[str] = []
        for node in ast.walk(tree):
            if id(node) in guarded:
                continue
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("remote_store._"):
                    bypassed = [a.name for a in node.names if a.name in public_names]
                    if bypassed:
                        names = ", ".join(bypassed)
                        violations.append(f"line {node.lineno}: from {module} import {names}")
        assert not violations, (
            f"{module_import} imports public symbols via private module paths:\n"
            + "\n".join(f"  {v}" for v in violations)
            + "\nUse 'from remote_store import ...' instead."
        )

    def test_no_private_store_access(self, source_path: Path, module_import: str) -> None:
        """Extension source must not access private Store/Backend attributes."""
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
        assert not violations, f"{module_import} accesses private Store attributes:\n" + "\n".join(
            f"  {v}" for v in violations
        )
