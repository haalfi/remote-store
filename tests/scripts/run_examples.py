"""Run all example scripts that need no external services or optional deps.

Discovers and executes every ``*.py`` in the example subdirectories that
are safe to run locally (no cloud credentials, no optional extras).
Backends and integrations are excluded — they need live services or
packages like PyArrow / Dagster.

Usage:

    python tests/scripts/run_examples.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples"

# Subdirectories whose scripts run without credentials or optional deps
AUTO_SUBDIRS = [
    "getting_started",
    "configuration",
    "errors",
    "advanced",
    "extensions",
]

# Scripts to skip (need optional deps, have known platform issues, etc.)
SKIP: set[str] = set()

# Individual scripts outside the auto-discovered subdirs
EXTRA_SCRIPTS = [
    EXAMPLES_ROOT / "snippets" / "homepage.py",
    EXAMPLES_ROOT / "snippets" / "core_operations.py",
    EXAMPLES_ROOT / "snippets" / "custom_backend_guide.py",
]


def discover() -> list[Path]:
    """Return all example scripts to run, in deterministic order."""
    scripts: list[Path] = []
    for subdir in AUTO_SUBDIRS:
        d = EXAMPLES_ROOT / subdir
        if d.is_dir():
            scripts.extend(sorted(d.glob("*.py")))
    scripts = [s for s in scripts if s.name != "__init__.py" and s.name not in SKIP]
    scripts.extend(s for s in EXTRA_SCRIPTS if s.exists())
    return scripts


def main() -> int:
    scripts = discover()
    failed: list[tuple[Path, int]] = []
    for i, script in enumerate(scripts, 1):
        rel = script.relative_to(EXAMPLES_ROOT.parent)
        print(f"cmd [{i}/{len(scripts)}] | python {rel}")
        result = subprocess.run([sys.executable, str(script)], timeout=60)
        if result.returncode != 0:
            failed.append((script, result.returncode))
    if failed:
        print(f"\n{len(failed)} example(s) FAILED:")
        for script, rc in failed:
            print(f"  {script.name} (exit {rc})")
        return 1
    print(f"\nAll {len(scripts)} examples passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
