"""Assert .readthedocs.yaml builds docs on the primary Python (.python-version).

RTD's ``build.tools.python`` must be a literal (it has no
``python-version-file`` equivalent), so the value is duplicated from
``.python-version``. This gate keeps the copy honest by comparing major.minor.
Wired into ``hatch run lint``. A malformed config raises here, which is itself
a lint failure — no defensive parsing needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent


def _major_minor(version: str) -> str:
    return ".".join(version.strip().split(".")[:2])


def check() -> str | None:
    """Return an error message if the two versions disagree, else ``None``."""
    rtd = yaml.safe_load((_ROOT / ".readthedocs.yaml").read_text(encoding="utf-8"))["build"]["tools"]["python"]
    pyver = (_ROOT / ".python-version").read_text(encoding="utf-8").split()[0]
    if _major_minor(str(rtd)) != _major_minor(pyver):
        return f".readthedocs.yaml python {rtd!r} does not match .python-version {pyver!r}"
    return None


if __name__ == "__main__":
    error = check()
    if error:
        sys.exit(f"error: {error}")
