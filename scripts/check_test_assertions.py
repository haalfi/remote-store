#!/usr/bin/env python3
"""AST check: every test function must have at least one assert or pytest.raises.

CI enforcement for Testing Rule 1 (see sdd/TESTING.md).
Exit code 0 = all tests have assertions; 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class _AssertVisitor(ast.NodeVisitor):
    """Walk a function body looking for assert statements or pytest.raises."""

    def __init__(self) -> None:
        self.found = False

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self.found = True

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        for item in node.items:
            if self._is_pytest_assertion_cm(item.context_expr):
                self.found = True
                return
        self.generic_visit(node)

    @staticmethod
    def _is_pytest_assertion_cm(node: ast.expr) -> bool:
        """Match ``pytest.raises(...)`` and ``pytest.warns(...)``."""
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {"raises", "warns"}
                and isinstance(func.value, ast.Name)
                and func.value.id == "pytest"
            ):
                return True
        return False


def _check_file(path: Path) -> list[str]:
    """Return list of violation messages for a single file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue

        visitor = _AssertVisitor()
        for child in ast.walk(node):
            visitor.visit(child)

        if not visitor.found:
            violations.append(f"{path}:{node.lineno}: {node.name} — no assert or pytest.raises")

    return violations


def main(directories: list[str] | None = None) -> int:
    if directories is None:
        directories = ["tests"]

    # Exclude POC/experimental test files from assertion checks
    excluded_files = {"test_dafny_oracle.py"}

    all_violations: list[str] = []
    for directory in directories:
        root = Path(directory)
        for path in sorted(root.rglob("test_*.py")):
            if path.name in excluded_files:
                continue
            all_violations.extend(_check_file(path))

    if all_violations:
        print(f"Found {len(all_violations)} test(s) without assertions:\n")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("All test functions have assertions.")
    return 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or None
    raise SystemExit(main(dirs))
