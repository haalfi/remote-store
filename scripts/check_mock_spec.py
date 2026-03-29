#!/usr/bin/env python3
"""AST check: every MagicMock() / Mock() call must use spec= or spec_set=.

CI enforcement for Testing Rule 4 (see sdd/TESTING.md).
create_autospec() is always OK.
Exit code 0 = no violations; 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_MOCK_NAMES = {"MagicMock", "Mock"}


class _MockSpecVisitor(ast.NodeVisitor):
    """Walk AST looking for Mock/MagicMock calls without spec=."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if self._is_unspec_mock(node):
            src = ast.get_source_segment(self._source, node) or ""
            self.violations.append(f"{self.path}:{node.lineno}: {src.split(chr(10))[0]}")
        self.generic_visit(node)

    def check(self, source: str) -> list[str]:
        self._source = source
        tree = ast.parse(source, filename=str(self.path))
        self.visit(tree)
        return self.violations

    @staticmethod
    def _is_unspec_mock(node: ast.Call) -> bool:
        """Return True if this is a Mock/MagicMock call without spec=."""
        func = node.func

        # Direct call: MagicMock(...) or Mock(...)
        if isinstance(func, ast.Name) and func.id in _MOCK_NAMES:
            return not _has_spec_kwarg(node)

        # Qualified call: mock.MagicMock(...) or unittest.mock.Mock(...)
        if isinstance(func, ast.Attribute) and func.attr in _MOCK_NAMES:
            return not _has_spec_kwarg(node)

        return False


def _has_spec_kwarg(node: ast.Call) -> bool:
    """Check if a Call node has spec=, spec_set=, or wraps= keyword."""
    return any(kw.arg in {"spec", "spec_set", "wraps"} for kw in node.keywords)


def _check_file(path: Path) -> list[str]:
    """Return list of violation messages for a single file."""
    source = path.read_text(encoding="utf-8")
    visitor = _MockSpecVisitor(path)
    return visitor.check(source)


def main(directories: list[str] | None = None) -> int:
    if directories is None:
        directories = ["tests"]

    all_violations: list[str] = []
    for directory in directories:
        root = Path(directory)
        for path in sorted(root.rglob("test_*.py")):
            all_violations.extend(_check_file(path))
        # Also check conftest files
        for path in sorted(root.rglob("conftest.py")):
            all_violations.extend(_check_file(path))

    if all_violations:
        print(f"Found {len(all_violations)} Mock() call(s) without spec=:\n")
        for v in all_violations:
            print(f"  {v}")
        return 1

    print("All Mock() calls use spec= or spec_set=.")
    return 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or None
    raise SystemExit(main(dirs))
