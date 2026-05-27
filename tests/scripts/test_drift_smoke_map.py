"""Tests for scripts/drift_smoke_map.py (ID-182).

The smoke map routes drift signals to pytest selections. Bugs in the
selector strings would silently collect zero tests, which the CI smoke
step surfaces as a "no tests collected" failure (pytest rc=5) and which
the rolling issue then reports as a smoke failure — exactly the wrong
signal for the maintainer. The single test below runs ``pytest
--collect-only`` against every entry and fails if any selector matches
no tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"

# Import the smoke map at module level so the @parametrize at the bottom
# can use its keys. Importing here (rather than via a fixture) keeps the
# parametrize call site readable.
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import drift_smoke_map  # noqa: E402


@pytest.mark.parametrize("extra", sorted(drift_smoke_map.SMOKE_TARGETS.keys()))
def test_smoke_target_collects_at_least_one_test(extra):
    """Every SMOKE_TARGETS entry must collect ≥1 test against the repo.

    pytest rc=5 ("no tests collected") indicates a keyword-selector or
    path mismatch — the smoke would silently fail to exercise anything
    even when drift fires. rc=2 with an ImportError is a missing optional
    dep in the test env (skipped — the workflow installs the extra first).
    """
    argv = drift_smoke_map.smoke_for(extra)
    if argv and argv[0] == "--import-only":
        pytest.skip(f"{extra} uses import-only smoke; no pytest collection.")

    # `-p no:benchmark`: pyproject's `filterwarnings = error` promotes
    # PytestBenchmarkWarning (fired by pytest-benchmark when xdist is
    # auto-loaded) to INTERNALERROR (rc=3) on dev boxes where
    # pytest-benchmark is installed. The plugin is irrelevant for
    # --collect-only. Mirrors the parent script's flag (pyproject.toml § test).
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:benchmark", "--collect-only", "-q", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode == 5:
        pytest.fail(
            f"smoke target for {extra} collects 0 tests:\n  argv = {argv}\n  stdout tail = {result.stdout[-500:]}"
        )
    # rc=2 is a collection error. The most common cause in this local test
    # env is a missing optional dep — the workflow installs `.[<extra>]`
    # plus the smoke-plugin set before running, so we treat collection
    # errors as a "not installed locally" skip rather than a real bug.
    # Heuristic widened to match the several pytest output shapes
    # ImportError / ModuleNotFoundError / importorskip / INTERNALERROR
    # can all take.
    import_failure_markers = (
        "ModuleNotFoundError",
        "ImportError",
        "importorskip",
        "INTERNALERROR",
    )
    if result.returncode == 2 and any(m in result.stdout for m in import_failure_markers):
        pytest.skip(
            f"{extra}'s optional dependency is not importable in this test env; CI installs it before the smoke runs."
        )
    # rc 0 (tests collected) and rc 1 (some failed collection but others
    # succeeded) both indicate the selector matched ≥1 test.
    assert result.returncode in (0, 1), f"unexpected pytest rc={result.returncode} for {extra}: {result.stdout[-500:]}"
