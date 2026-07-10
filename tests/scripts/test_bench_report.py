"""Unit tests for benchmarks/report.py --regression (BK-309).

The benchmark suite is now run on a schedule (``.github/workflows/benchmark.yml``)
and gated against a committed baseline. These tests protect the gate's own
logic — the threshold comparison and the sub-noise absolute floor — so a change
to the report tool cannot silently disable regression detection. Timing itself
is not asserted here (that belongs to the benchmark run); this pins the pure
compare-and-flag arithmetic.
"""

from __future__ import annotations

from benchmarks import report


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
    # positives from the real data the workflow gates on).
    import json
    from pathlib import Path

    baseline_path = Path(__file__).resolve().parents[2] / "benchmarks" / "baseline" / "local-baseline.json"
    data = json.loads(baseline_path.read_text())
    table = report._build_table(data["benchmarks"])
    assert table, "baseline produced an empty comparison table"
    rows = report._regression_rows(table, table, threshold=2.0)
    assert rows, "baseline self-comparison produced no rows"
    assert not any(r[5] for r in rows), "baseline regressed against itself"
