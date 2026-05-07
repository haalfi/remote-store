"""Fail if any Python file in the scanned directories contains an RST inline role.

RST cross-reference syntax (colon-word-colon-single-backtick) is incompatible with
the Google-style docstrings used in this project.  Double-backtick literals like
``:class:``​`` `` are not flagged — those are inline code, not roles.

Wired into ``hatch run lint`` and the ``no-rst-roles`` pre-commit hook.

Usage:
    python scripts/check_rst_roles.py [dir ...]
    Defaults to src/, tests/, and scripts/ when no arguments are given.
"""

import re
import sys
from pathlib import Path

# Colon, one-or-more word chars, colon, single backtick NOT followed by another backtick.
RST_ROLE = re.compile(r":\w+:`(?!`)")

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DIRS = ["src", "tests", "scripts", "examples"]


def scan_file(path: Path) -> list[str]:
    """Return one violation string per RST-role match in *path*."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
        return []
    return [
        f"{path}:{lineno}: RST role found" for lineno, line in enumerate(text.splitlines(), 1) if RST_ROLE.search(line)
    ]


def main(dirs: list[str] | None = None) -> int:
    """Scan *dirs* for RST roles; return 0 if clean, 1 on violations."""
    targets = [_ROOT / d for d in _DEFAULT_DIRS] if dirs is None else [Path(d) for d in dirs]
    missing = [str(t) for t in targets if not t.is_dir()]
    if missing:
        for m in missing:
            sys.stderr.write(f"error: directory not found: {m}\n")
        return 1

    violations: list[str] = []
    for target in targets:
        for py_file in sorted(target.glob("**/*.py")):
            violations.extend(scan_file(py_file))

    if violations:
        for v in violations:
            sys.stderr.write(f"error: {v}\n")
        sys.stderr.write(
            "\nRST inline roles (colon-word-colon-backtick) conflict with Google-style docstrings.\n"
            "Use plain text or ``double backticks`` for inline code instead.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
