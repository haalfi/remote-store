#!/usr/bin/env python3
"""Grep check: every MagicMock() call must use spec= or spec_set=.

CI enforcement for Testing Rule 4 (see sdd/TESTING.md).
Also catches Mock() without spec. create_autospec() is always OK.
Exit code 0 = no violations; 1 = violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matches MagicMock( or Mock( — but NOT create_autospec(
_MOCK_CALL = re.compile(r"\b(?:Magic)?Mock\(")
# Matches spec= or spec_set= anywhere on the same line
_HAS_SPEC = re.compile(r"\bspec(?:_set)?\s*=")
# Skip comment-only lines
_COMMENT = re.compile(r"^\s*#")


def _check_file(path: Path) -> list[str]:
    """Return list of violation messages for a single file."""
    violations: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    for lineno, line in enumerate(lines, start=1):
        if _COMMENT.match(line):
            continue
        if not _MOCK_CALL.search(line):
            continue
        # Allow lines that have spec= or spec_set=
        if _HAS_SPEC.search(line):
            continue
        # Allow create_autospec on the same line
        if "create_autospec" in line:
            continue
        # Allow MagicMock used as a type annotation or spec target
        # e.g. spec=MagicMock or isinstance(..., MagicMock)
        stripped = line.strip()
        if stripped.startswith("spec") or "isinstance" in stripped:
            continue

        violations.append(f"{path}:{lineno}: {stripped}")

    return violations


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
