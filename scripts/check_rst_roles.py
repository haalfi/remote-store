r"""Fail if any Python file under src/ contains an RST inline role.

RST roles (:class:`Foo`, :func:`bar`, :meth:`baz`, etc.) are RST-specific
syntax incompatible with the Google-style docstrings used in this project.
This check prevents Audit-013-class violations from silently re-entering.

Pattern: :\w+:` (colon, word, colon, single backtick).
Double-backtick code like :class:`` is allowed — that is inline code, not a role.
"""

import re
import sys
from pathlib import Path

# :\w+:` where the backtick is NOT immediately followed by another backtick.
RST_ROLE = re.compile(r":\w+:`(?!`)")

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

if not SRC_DIR.is_dir():
    sys.exit(f"error: {SRC_DIR} not found")

violations: list[str] = []

for py_file in sorted(SRC_DIR.glob("**/*.py")):
    try:
        text = py_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {py_file}: {type(exc).__name__}\n")
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        if RST_ROLE.search(line):
            violations.append(f"{py_file}:{lineno}: RST role found")

if violations:
    for v in violations:
        sys.stderr.write(f"error: {v}\n")
    sys.stderr.write(
        "\nRST inline roles (:word:`...`) conflict with Google-style docstrings.\n"
        "Use plain text or ``double backticks`` for inline code instead.\n"
    )
    sys.exit(1)
