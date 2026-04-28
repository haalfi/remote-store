"""Fail if any TLA+ file under sdd/formal/tla/ contains an em dash (U+2014).

TLC rejects non-ASCII characters in string literals with a lexical error.
Running this check before TLC gives a clearer error message and catches
em dashes in comments too, preventing silent accumulation.
"""

import sys
from pathlib import Path

EM_DASH = "—"
TLA_DIR = Path(__file__).resolve().parent.parent / "sdd" / "formal" / "tla"

if not TLA_DIR.is_dir():
    sys.exit(f"error: {TLA_DIR} not found")

violations: list[str] = []

for tla_file in sorted(TLA_DIR.glob("**/*.tla")):
    try:
        text = tla_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {tla_file}: {type(exc).__name__}\n")
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        if EM_DASH in line:
            violations.append(f"{tla_file}:{lineno}: em dash (U+2014) in TLA+ file")

if violations:
    for v in violations:
        sys.stderr.write(f"error: {v}\n")
    sys.exit(1)
