"""Unit tests for benchmarks/report.py --regression (BK-309).

The benchmark suite is now run on a schedule (``.github/workflows/benchmark.yml``)
and gated against a committed baseline. These tests protect the gate's own
logic — the threshold comparison and the sub-noise absolute floor — so a change
to the report tool cannot silently disable regression detection. Timing itself
is not asserted here (that belongs to the benchmark run); this pins the pure
compare-and-flag arithmetic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from benchmarks import report

if TYPE_CHECKING:
    import pytest


def test_regression_flags_when_ratio_exceeds_threshold() -> None:
    current = {"Write 1MB": {"local": 3.0}}
    baseline = {"Write 1MB": {"local": 1.0}}
    rows = report._regression_rows(current, baseline, threshold=2.0)
    assert len(rows) == 1
    label, backend, cur, base, ratio, regressed = rows[0]
    assert (label, backend) == ("Write 1MB", "local")
    assert ratio == 3.0
    assert regressed is True


def test_no_regression_within_threshold() -> None:
    current = {"Write 1MB": {"local": 1.5}}
    baseline = {"Write 1MB": {"local": 1.0}}
    rows = report._regression_rows(current, baseline, threshold=2.0)
    assert rows[0][5] is False


def test_absolute_floor_excludes_sub_noise_ops_from_gate() -> None:
    # A 3x blow-up on a 10us baseline is machine noise, not a regression:
    # with a 1ms floor it must be reported but never flagged.
    current = {"Exists": {"local": 30e-6}}
    baseline = {"Exists": {"local": 10e-6}}
    rows = report._regression_rows(current, baseline, threshold=2.0, min_abs=1e-3)
    ratio, regressed = rows[0][4], rows[0][5]
    assert ratio == 3.0
    assert regressed is False  # below the floor, so not gated


def test_floor_still_gates_ops_at_or_above_floor() -> None:
    current = {"Write 1MB": {"local": 6e-3}}
    baseline = {"Write 1MB": {"local": 2e-3}}
    rows = report._regression_rows(current, baseline, threshold=2.0, min_abs=1e-3)
    assert rows[0][5] is True


def test_missing_cells_are_skipped() -> None:
    # Backend present in current but absent from baseline is not comparable.
    current = {"Write 1MB": {"local": 1.0, "s3": 2.0}}
    baseline = {"Write 1MB": {"local": 1.0}}
    rows = report._regression_rows(current, baseline, threshold=2.0)
    assert {(r[0], r[1]) for r in rows} == {("Write 1MB", "local")}


def test_zero_baseline_is_skipped() -> None:
    current = {"Write 1MB": {"local": 1.0}}
    baseline = {"Write 1MB": {"local": 0.0}}
    rows = report._regression_rows(current, baseline, threshold=2.0)
    assert rows == []


def test_committed_baseline_is_self_consistent() -> None:
    # The shipped baseline loads and compares clean against itself (no false
    # positives from the real data the workflow gates on). Uses the full table —
    # the gate's actual comparison surface — so this also proves the baseline
    # carries more than the SUMMARY_ROWS subset.
    baseline_path = Path(__file__).resolve().parents[2] / "benchmarks" / "baseline" / "local-baseline.json"
    data = json.loads(baseline_path.read_text())
    table = report._build_full_table(data["benchmarks"])
    assert table, "baseline produced an empty comparison table"
    # More cells than the 14 SUMMARY_ROWS ops — read/stream/copy-move are covered.
    assert len(table) > len(report.SUMMARY_ROWS)
    rows = report._regression_rows(table, table, threshold=2.0)
    assert rows, "baseline self-comparison produced no rows"
    assert not any(r[5] for r in rows), "baseline regressed against itself"


def test_build_full_table_covers_non_summary_ops() -> None:
    # test_copy is not in SUMMARY_ROWS, so _build_table drops it; the full table
    # must keep it (that is the point of broadening the regression surface).
    benchmarks = [
        {
            "name": "test_copy[local-remote_store]",
            "params": {"bench_target": ["local", "remote_store"]},
            "stats": {"mean": 1.0},
        },
    ]
    assert "test_copy" in report._build_full_table(benchmarks)
    assert report._build_table(benchmarks) == {}


def _write_run(path: Path, entries: list[tuple[str, float]]) -> None:
    """Write a minimal run JSON: entries are (test_name, mean) local cells."""
    payload: dict[str, Any] = {
        "benchmarks": [
            {"name": name, "params": {"bench_backend": "local"}, "stats": {"mean": mean}} for name, mean in entries
        ]
    }
    path.write_text(json.dumps(payload))


def _run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """Invoke report.main() with argv; return the exit code (0 if it returns)."""
    monkeypatch.setattr(sys, "argv", ["report.py", *argv])
    try:
        report.main()
    except SystemExit as exc:  # noqa: PT012 - asserting the code, not just the raise
        return int(exc.code or 0)
    return 0


def test_main_exits_1_on_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    _write_run(base, [("test_x", 1.0)])
    _write_run(cur, [("test_x", 3.0)])  # 3x > 2x threshold, above 0 floor
    code = _run_main(["--regression", "--file", str(cur), "--baseline", str(base), "--threshold", "2.0"], monkeypatch)
    assert code == 1


def test_main_exits_0_on_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    _write_run(base, [("test_x", 1.0)])
    _write_run(cur, [("test_x", 1.1)])  # within threshold
    code = _run_main(["--regression", "--file", str(cur), "--baseline", str(base), "--threshold", "2.0"], monkeypatch)
    assert code == 0


def test_main_exits_2_on_missing_baseline_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cur = tmp_path / "cur.json"
    _write_run(cur, [("test_x", 1.0)])
    missing = tmp_path / "nope.json"
    code = _run_main(["--regression", "--file", str(cur), "--baseline", str(missing)], monkeypatch)
    assert code == 2


def test_main_exits_2_when_baseline_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cur = tmp_path / "cur.json"
    _write_run(cur, [("test_x", 1.0)])
    code = _run_main(["--regression", "--file", str(cur)], monkeypatch)
    assert code == 2
