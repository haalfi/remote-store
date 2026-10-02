"""Assert the local gate runs on the primary Python (.python-version).

hatch cannot read ``.python-version``, so ``[tool.hatch.envs.default] python``
in ``pyproject.toml`` is a literal copy of it; without one, hatch builds
``.venv`` from whatever ``python`` is first on PATH. Two checks, both on
major.minor:

1. the pin equals ``.python-version``;
2. the interpreter running this script does too. hatch keeps an existing env's
   interpreter when the pin changes (measured: a 3.11 ``.venv`` stayed 3.11
   under a 3.13 pin until removed), so a stale env passes check 1 and still
   gates on the wrong Python. It runs only once check 1 passes.

Wired into ``hatch run preflight`` (and so ``all``, and CI's ``lint`` job,
which runs on the primary Python). Its tests run in CI only on the primary
Python (``tooling-tests``), so the mismatch path is pinned through ``main``
with an injected version. Bounds: only the ``default`` env is
checked, not the ``hatch-test.*`` matrix envs; check 2 speaks only for the
env that runs it; a malformed ``pyproject.toml`` raises, which is itself a
failure.

Drift-gate::

    kind:       pair
    compares:   .python-version ↔ pyproject.toml [tool.hatch.envs.default] python, and ↔ the running interpreter
    domain:     process
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _major_minor(version: str) -> str:
    return ".".join(version.strip().split(".")[:2])


def read_primary() -> str:
    """Return the version string in ``.python-version``."""
    return (_ROOT / ".python-version").read_text(encoding="utf-8").split()[0]


def pin_from_toml(text: str) -> str | None:
    """Return ``[tool.hatch.envs.default] python`` from pyproject TOML text, or ``None``."""
    pin = tomllib.loads(text)["tool"]["hatch"]["envs"]["default"].get("python")
    return None if pin is None else str(pin)


def read_pin() -> str | None:
    """Return the repo's hatch default-env ``python`` pin, or ``None``."""
    return pin_from_toml((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def check_pin(pin: str | None, primary: str) -> str | None:
    """Return an error message if the pin is absent or disagrees with *primary*."""
    if pin is None:
        return f"pyproject.toml [tool.hatch.envs.default] sets no python; .python-version is {primary!r}"
    if _major_minor(pin) != _major_minor(primary):
        return f"pyproject.toml [tool.hatch.envs.default] python {pin!r} != .python-version {primary!r}"
    return None


def check_interpreter(running: tuple[int, int], primary: str) -> str | None:
    """Return an error message, with the remedy, if *running* is not *primary*."""
    if f"{running[0]}.{running[1]}" == _major_minor(primary):
        return None
    return (
        f"running on Python {running[0]}.{running[1]}, .python-version is {primary!r}: "
        "run this in the hatch env; if that env predates the pin, rebuild it with `hatch env remove default`"
    )


def main(running: tuple[int, int]) -> int:
    """Run the checks for interpreter *running*; print the error to stderr and return the exit code.

    Check 2 runs only once the pin is right: its remedy rebuilds the env on the
    pin, which fixes nothing while the pin itself is wrong.
    """
    primary = read_primary()
    error = check_pin(read_pin(), primary) or check_interpreter(running, primary)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main(sys.version_info[:2]))
