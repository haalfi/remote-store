#!/usr/bin/env python3
"""Placement check: tests for scripts/ utilities must live in tests/scripts/.

Any test file anywhere under the tests tree (except tests/scripts/) that loads
modules from scripts/ via sys.path manipulation belongs in tests/scripts/ instead.
See the placement rule in sdd/TESTING.md § Test Subpackage Placement.

CI enforcement for the placement rule.
Exit code 0 = ok; 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _names_referencing_scripts(tree: ast.Module) -> set[str]:
    """Collect variable names assigned to paths containing 'scripts'.

    Covers plain and annotated assignments:
        SCRIPTS = ROOT / "scripts"
        SCRIPTS: Path = ROOT / "scripts"
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            value = node.value
            targets = [node.target]
        else:
            continue
        for child in ast.walk(value):
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and "scripts" in child.value:
                for target in targets:
                    names.add(target.id)
                break
    return names


def _uses_scripts_sys_path(tree: ast.Module, scripts_names: set[str]) -> int | None:
    """Return the line number of the first sys.path manipulation that adds scripts/.

    Matches:
        sys.path.insert(N, str(SCRIPTS))
        sys.path.append(str(SCRIPTS))
        sys.path.insert(N, "…/scripts")

    Only inspects the path argument (index 1 for insert, 0 for append) to avoid
    false positives from variable names used as the index slot.

    Returns None if no such call is found.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in {"insert", "append"}
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
        ):
            continue
        # Select only the path argument to avoid false positives from the index slot.
        if func.attr == "insert":
            if len(node.args) < 2:
                continue
            path_arg = node.args[1]
        else:  # append
            if not node.args:
                continue
            path_arg = node.args[0]
        for arg in ast.walk(path_arg):
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "scripts" in arg.value:
                return node.lineno
            if isinstance(arg, ast.Name) and arg.id in scripts_names:
                return node.lineno
    return None


def _check_file(path: Path) -> str | None:
    """Return a violation message if the file belongs in tests/scripts/, else None."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
        return None
    if "sys.path" not in source or "scripts" not in source:
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        sys.stderr.write(f"Skipping {path}: SyntaxError\n")
        return None
    scripts_names = _names_referencing_scripts(tree)
    line = _uses_scripts_sys_path(tree, scripts_names)
    if line is not None:
        return f"{path}:{line}: loads scripts/ module via sys.path: move to tests/scripts/"
    return None


def main(directories: list[str] | None = None) -> int:
    if directories is None:
        directories = ["tests"]

    violations: list[str] = []
    for directory in directories:
        tests_dir = Path(directory)
        scripts_subpkg = tests_dir / "scripts"
        for path in sorted(tests_dir.rglob("test_*.py")):
            # Skip files already in the correct subpackage
            if path.is_relative_to(scripts_subpkg):
                continue
            msg = _check_file(path)
            if msg is not None:
                violations.append(msg)

    if violations:
        print(f"Found {len(violations)} misplaced script test(s):\n")
        for v in violations:
            print(f"  {v}")
        print("\nMove these files to tests/scripts/ (see sdd/TESTING.md § Test Subpackage Placement).")
        return 1

    print("All script tests are correctly placed under tests/scripts/.")
    return 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or None
    raise SystemExit(main(dirs))
