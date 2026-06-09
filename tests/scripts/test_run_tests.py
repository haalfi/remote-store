"""Unit tests for scripts/run_tests.py (BK-277).

Pins the resource-bounded worker formula and the explicit-``-n`` passthrough so
a future edit cannot silently restore ``-n auto`` behaviour or break the
``RS_TEST_WORKERS`` override.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_tests", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("run_tests", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
compute_workers = _mod.compute_workers
_has_explicit_n = _mod._has_explicit_n
main = _mod.main


@pytest.mark.parametrize(
    ("cpus", "expected"),
    [
        (1, 1),  # max(1, floor(0.75) - 1) = max(1, -1)
        (2, 1),  # floor(1.5) - 1 = 0 -> clamped to 1
        (4, 2),  # floor(3.0) - 1
        (8, 5),  # floor(6.0) - 1
        (16, 11),  # floor(12.0) - 1
        (32, 23),  # floor(24.0) - 1
        (None, 1),  # unknown CPU count -> single worker
    ],
)
def test_default_formula_leaves_headroom(cpus: int | None, expected: int) -> None:
    assert compute_workers(cpus, None) == expected


def test_default_formula_never_exceeds_cpus() -> None:
    for cpus in range(1, 65):
        assert 1 <= compute_workers(cpus, None) <= cpus


@pytest.mark.parametrize("override", ["auto", "AUTO", " auto "])
def test_override_auto_uses_all_cpus(override: str) -> None:
    assert compute_workers(8, override) == 8
    assert compute_workers(1, override) == 1


@pytest.mark.parametrize(
    ("override", "expected"),
    [("4", 4), (" 3 ", 3), ("1", 1), ("16", 16)],  # explicit count may exceed cpus
)
def test_override_integer_is_respected(override: str, expected: int) -> None:
    assert compute_workers(8, override) == expected


def test_empty_override_falls_back_to_formula() -> None:
    assert compute_workers(8, "") == 5
    assert compute_workers(8, "   ") == 5


@pytest.mark.parametrize("override", ["abc", "0", "-2", "2.5"])
def test_invalid_override_raises(override: str) -> None:
    with pytest.raises(ValueError, match="RS_TEST_WORKERS"):
        compute_workers(8, override)


@pytest.mark.parametrize(
    "args",
    [["-n", "4"], ["-n0"], ["--numprocesses=2"], ["--numprocesses", "auto"], ["-p", "x", "-n", "2"]],
)
def test_explicit_n_detected(args: list[str]) -> None:
    assert _has_explicit_n(args) is True


@pytest.mark.parametrize("args", [[], ["-p", "no:benchmark"], ["tests/aio"], ["--cov=remote_store"]])
def test_no_explicit_n(args: list[str]) -> None:
    assert _has_explicit_n(args) is False


def _stub_run(monkeypatch: pytest.MonkeyPatch, cpu_count: int = 8) -> dict:
    """Stub subprocess.run / os.cpu_count / RS_TEST_WORKERS; capture the argv."""
    captured: dict = {}

    class _Result:
        returncode = 7

    def _fake_run(argv, check):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        captured["argv"] = argv
        captured["check"] = check
        return _Result()

    monkeypatch.setattr(_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(_mod.os, "cpu_count", lambda: cpu_count)
    monkeypatch.delenv("RS_TEST_WORKERS", raising=False)
    return captured


def test_main_injects_bounded_workers_and_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() injects the computed -n and forwards the rest, propagating exit code."""
    captured = _stub_run(monkeypatch, cpu_count=8)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py", "-p", "no:benchmark", "tests/x"])
    rc = main()
    assert rc == 7  # subprocess returncode propagated
    argv = captured["argv"]
    assert argv[:3] == [_mod.sys.executable, "-m", "pytest"]
    assert argv[3:5] == ["-n", "5"]  # floor(8*0.75) - 1
    assert argv[5:] == ["-p", "no:benchmark", "tests/x"]
    assert captured["check"] is False


def test_main_respects_explicit_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() does not inject -n when the caller already passed one."""
    captured = _stub_run(monkeypatch, cpu_count=8)
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py", "-n", "2", "tests/x"])
    main()
    argv = captured["argv"]
    assert argv == [_mod.sys.executable, "-m", "pytest", "-n", "2", "tests/x"]
    assert argv.count("-n") == 1  # no second -n injected


def test_main_invalid_override_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid RS_TEST_WORKERS makes main() exit 2 without invoking pytest."""
    captured = _stub_run(monkeypatch)
    monkeypatch.setenv("RS_TEST_WORKERS", "nope")
    monkeypatch.setattr(_mod.sys, "argv", ["run_tests.py"])
    assert main() == 2
    assert "argv" not in captured  # subprocess.run never called
