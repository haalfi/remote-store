"""Generate a summary table from saved pytest-benchmark JSON files.

Usage::

    hatch run bench-report                  # latest run
    hatch run bench-report --compare        # latest vs previous run
    hatch run bench-report --json           # machine-readable output
    hatch run bench-report-comparative      # remote-store vs raw SDK vs fsspec
    hatch run bench-report-comparative-md   # same, as Markdown to file
"""

from __future__ import annotations

import argparse
import datetime
import json
import platform
import sys
from pathlib import Path
from typing import Any

# ---- Configuration: which benchmarks appear in the summary table -----------

# (test_name_prefix, param_filter, display_label)
# param_filter is a dict matched against the benchmark's "params".
# For bench_target tests, we only show remote_store results.
SUMMARY_ROWS: list[tuple[str, dict[str, Any], str]] = [
    ("test_write_bytes", {"payload": 1024}, "Write 1KB"),
    ("test_write_bytes", {"payload": 65536}, "Write 64KB"),
    ("test_write_bytes", {"payload": 1048576}, "Write 1MB"),
    ("test_read_bytes", {"payload": 1024}, "Read 1KB"),
    ("test_read_bytes", {"payload": 65536}, "Read 64KB"),
    ("test_read_bytes", {"payload": 1048576}, "Read 1MB"),
    ("test_exists_hit", {}, "Exists (hit)"),
    ("test_exists_miss", {}, "Exists (miss)"),
    ("test_list_files", {}, "List 50 files"),
    ("test_list_1000_files", {}, "List 1000 files"),
    ("test_delete", {}, "Delete"),
    ("test_write_latency", {}, "TTFB write"),
    ("test_ttfb_read", {}, "TTFB read"),
    ("test_ttfb_exists", {}, "TTFB exists"),
]

BACKEND_ORDER = ["local", "s3", "s3-pyarrow", "sftp", "azure"]

BACKEND_LABELS = {
    "local": "Local",
    "s3": "S3 (MinIO)",
    "s3-pyarrow": "S3-PyArrow",
    "sftp": "SFTP",
    "azure": "Azure",
}

# ---- Comparative configuration: key ops across all three targets ----------

# (test_name, param_filter, display_label) -- subset of SUMMARY_ROWS for
# the comparative view (remote-store vs raw SDK vs fsspec).
COMPARATIVE_ROWS: list[tuple[str, dict[str, Any], str]] = [
    ("test_write_bytes", {"payload": 1048576}, "Write 1MB"),
    ("test_read_bytes", {"payload": 1048576}, "Read 1MB"),
    ("test_exists_hit", {}, "Exists (hit)"),
    ("test_list_files", {}, "List 50 files"),
    ("test_delete", {}, "Delete"),
]

# Map target_kind in bench_target params to display column headers.
TARGET_LABELS: dict[str, dict[str, str]] = {
    "local": {"remote_store": "remote-store", "pathlib_raw": "pathlib", "fsspec_local": "fsspec"},
    "s3": {"remote_store": "remote-store", "boto3_raw": "boto3", "s3fs": "s3fs"},
    "s3-pyarrow": {"remote_store": "remote-store", "boto3_raw": "boto3"},
    "sftp": {"remote_store": "remote-store", "paramiko_raw": "paramiko", "sshfs": "sshfs"},
    "azure": {"remote_store": "remote-store", "azure_blob_raw": "azure-blob", "adlfs": "adlfs"},
}

# ---------------------------------------------------------------------------


def _find_json_files(benchmarks_dir: Path) -> list[Path]:
    """Return saved benchmark JSONs sorted by name (oldest first)."""
    files = sorted(benchmarks_dir.rglob("*.json"))
    return files


def _parse_backend(bm: dict[str, Any]) -> str | None:
    """Extract backend type from a benchmark entry's params."""
    params = bm.get("params", {})
    # bench_target tests have params like {"bench_target": ["s3", "remote_store"]}
    if "bench_target" in params:
        target = params["bench_target"]
        if isinstance(target, list) and len(target) == 2:
            backend_type, target_kind = target
            # Only include remote_store targets in the summary
            if target_kind != "remote_store":
                return None
            return backend_type
        return None
    # bench_backend tests have params like {"bench_backend": "local"}
    if "bench_backend" in params:
        return params["bench_backend"]
    return None


def _matches_filter(bm: dict[str, Any], param_filter: dict[str, Any]) -> bool:
    """Check if a benchmark's params match the given filter."""
    params = bm.get("params", {})
    return all(params.get(key) == value for key, value in param_filter.items())


def _test_name(bm: dict[str, Any]) -> str:
    """Extract bare test name (before the [ parametrize bracket)."""
    name = bm["name"]
    bracket = name.find("[")
    return name[:bracket] if bracket != -1 else name


def _build_table(
    benchmarks: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Build {display_label: {backend: mean_seconds}} from benchmark list."""
    table: dict[str, dict[str, float]] = {}
    for test_prefix, param_filter, label in SUMMARY_ROWS:
        row: dict[str, float] = {}
        for bm in benchmarks:
            if _test_name(bm) != test_prefix:
                continue
            if not _matches_filter(bm, param_filter):
                continue
            backend = _parse_backend(bm)
            if backend is None:
                continue
            row[backend] = bm["stats"]["mean"]
        if row:
            table[label] = row
    return table


def _op_key(bm: dict[str, Any]) -> str:
    """Stable identifier for a benchmark: test name + non-selector params.

    The ``bench_target`` / ``bench_backend`` params select *which* backend runs,
    not *which operation* — they are stripped so the same operation across
    backends shares one key. Remaining params (payload size, etc.) disambiguate.
    """
    name = _test_name(bm)
    params = {k: v for k, v in bm.get("params", {}).items() if k not in ("bench_target", "bench_backend")}
    if params:
        sig = ",".join(f"{k}={params[k]}" for k in sorted(params))
        return f"{name}[{sig}]"
    return name


def _build_full_table(
    benchmarks: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Build ``{op_key: {backend: mean_seconds}}`` for **every** remote_store cell.

    Unlike :func:`_build_table`, which is scoped to the ``SUMMARY_ROWS`` display
    set, this keeps every remote_store operation in the run — large-payload,
    streaming, copy/move, seekable, cache — so the regression gate compares the
    full baseline, not just the summary ops.
    """
    table: dict[str, dict[str, float]] = {}
    for bm in benchmarks:
        backend = _parse_backend(bm)
        if backend is None:
            continue
        table.setdefault(_op_key(bm), {})[backend] = bm["stats"]["mean"]
    return table


def _format_time(seconds: float) -> str:
    """Format seconds as human-readable latency."""
    us = seconds * 1_000_000
    if us < 1000:
        return f"{us:.0f}us"
    ms = us / 1000
    if ms < 100:
        return f"{ms:.1f}ms"
    return f"{ms:.0f}ms"


def _format_delta(current: float, previous: float) -> str:
    """Format relative change as a percentage string."""
    if previous == 0:
        return "new"
    pct = ((current - previous) / previous) * 100
    if abs(pct) < 1:
        return "  --"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0f}%"


def _print_table(
    table: dict[str, dict[str, float]],
    previous: dict[str, dict[str, float]] | None = None,
) -> None:
    """Print a formatted summary table to stdout."""
    # Determine which backends have data
    backends_present = []
    for backend in BACKEND_ORDER:
        if any(backend in row for row in table.values()):
            backends_present.append(backend)

    if not backends_present:
        print("No benchmark data found.")
        return

    # Column widths
    label_w = max(len(label) for label in table)
    col_w = 14 if previous else 10

    # Header
    header = f"{'Operation':<{label_w}}"
    for backend in backends_present:
        header += f"  {BACKEND_LABELS.get(backend, backend):>{col_w}}"
    print(header)
    print("-" * len(header))

    # Rows
    for label, row in table.items():
        line = f"{label:<{label_w}}"
        for backend in backends_present:
            if backend in row:
                cell = _format_time(row[backend])
                if previous and label in previous and backend in previous[label]:
                    delta = _format_delta(row[backend], previous[label][backend])
                    cell = f"{cell} ({delta})"
                line += f"  {cell:>{col_w}}"
            else:
                line += f"  {'--':>{col_w}}"
        print(line)


def _print_json(
    table: dict[str, dict[str, float]],
    previous: dict[str, dict[str, float]] | None = None,
) -> None:
    """Print machine-readable JSON output."""
    output: dict[str, Any] = {"current": {}}
    for label, row in table.items():
        output["current"][label] = {
            backend: {"mean_s": mean, "display": _format_time(mean)} for backend, mean in row.items()
        }
    if previous:
        output["previous"] = {}
        output["delta"] = {}
        for label, row in table.items():
            if label in previous:
                output["previous"][label] = {
                    backend: {"mean_s": mean, "display": _format_time(mean)}
                    for backend, mean in previous[label].items()
                }
                output["delta"][label] = {}
                for backend, mean in row.items():
                    if backend in previous[label]:
                        prev_mean = previous[label][backend]
                        pct = ((mean - prev_mean) / prev_mean) * 100 if prev_mean else 0
                        output["delta"][label][backend] = {
                            "pct": round(pct, 1),
                            "display": _format_delta(mean, prev_mean),
                        }
    json.dump(output, sys.stdout, indent=2)
    print()


def _parse_backend_and_target(bm: dict[str, Any]) -> tuple[str, str] | None:
    """Extract (backend_type, target_kind) from a bench_target benchmark."""
    params = bm.get("params", {})
    if "bench_target" not in params:
        return None
    target = params["bench_target"]
    if isinstance(target, list) and len(target) == 2:
        return (target[0], target[1])
    return None


def _build_comparative_table(
    benchmarks: list[dict[str, Any]],
    ops: list[tuple[str, dict[str, Any], str]] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Build {label: {backend: {target_kind: mean}}} for comparative view.

    Args:
        benchmarks: List of benchmark entries from saved JSON.
        ops: Operation definitions ``(test_prefix, param_filter, label)``.
            Defaults to ``COMPARATIVE_ROWS``.
    """
    table: dict[str, dict[str, dict[str, float]]] = {}
    for test_prefix, param_filter, label in ops or COMPARATIVE_ROWS:
        per_backend: dict[str, dict[str, float]] = {}
        for bm in benchmarks:
            if _test_name(bm) != test_prefix:
                continue
            if not _matches_filter(bm, param_filter):
                continue
            bt = _parse_backend_and_target(bm)
            if bt is None:
                continue
            backend_type, target_kind = bt
            per_backend.setdefault(backend_type, {})[target_kind] = bm["stats"]["mean"]
        if per_backend:
            table[label] = per_backend
    return table


# ---- Regression detection (CI gate) ---------------------------------------

# Default multiplier: flag an operation only when its mean is at least this many
# times the committed baseline. Deliberately generous — shared CI runners vary
# run-to-run, so a tight gate would flake. The point is to catch *gross*
# regressions (an accidental O(n^2), a 10x blow-up), not micro-drift.
DEFAULT_REGRESSION_THRESHOLD = 2.0


def _regression_rows(
    current: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
    threshold: float,
    min_abs: float = 0.0,
) -> list[tuple[str, str, float, float, float, bool]]:
    """Compare current vs baseline means per (operation, backend).

    Returns ``(label, backend, current_s, baseline_s, ratio, regressed)`` for
    every cell present in both tables. ``ratio`` is ``current / baseline``.

    ``regressed`` is ``ratio > threshold`` **and** ``baseline >= min_abs``. The
    ``min_abs`` floor keeps sub-millisecond operations — where machine-to-machine
    variance dwarfs any real signal — out of the pass/fail gate while still
    showing them in the report.
    """
    rows: list[tuple[str, str, float, float, float, bool]] = []
    for label, cur_backends in current.items():
        base_backends = baseline.get(label)
        if not base_backends:
            continue
        for backend, cur in cur_backends.items():
            base = base_backends.get(backend)
            if base is None or base <= 0:
                continue
            ratio = cur / base
            regressed = ratio > threshold and base >= min_abs
            rows.append((label, backend, cur, base, ratio, regressed))
    return rows


def _print_regression(
    rows: list[tuple[str, str, float, float, float, bool]],
    threshold: float,
    min_abs: float = 0.0,
) -> bool:
    """Print a regression table. Return True if any row regressed."""
    if not rows:
        print("No overlapping (operation, backend) cells between run and baseline.")
        return False

    label_w = max(len(r[0]) for r in rows)
    backend_w = max(len(r[1]) for r in rows)
    print(f"Regression check (threshold {threshold:.2f}x, floor {_format_time(min_abs)})\n")
    header = f"{'Operation':<{label_w}}  {'Backend':<{backend_w}}  {'current':>9}  {'baseline':>9}  {'ratio':>6}"
    print(header)
    print("-" * len(header))
    regressed = False
    for label, backend, cur, base, ratio, is_reg in sorted(rows, key=lambda r: r[4], reverse=True):
        flag = "  <-- REGRESSION" if is_reg else ""
        if is_reg:
            regressed = True
        print(
            f"{label:<{label_w}}  {backend:<{backend_w}}  "
            f"{_format_time(cur):>9}  {_format_time(base):>9}  {ratio:>5.2f}x{flag}"
        )
    return regressed


def _format_relative(value: float, baseline: float) -> str:
    """Format value relative to baseline (e.g., '1.2x slower')."""
    if baseline == 0:
        return ""
    ratio = value / baseline
    if ratio > 1.05:
        return f" ({ratio:.1f}x slower)"
    if ratio < 0.95:
        return f" ({1 / ratio:.1f}x faster)"
    return ""


# ---- Raw SDK targets per backend (for magnitude computation) --------------

RAW_SDK_TARGET: dict[str, str] = {
    "local": "pathlib_raw",
    "s3": "boto3_raw",
    "s3-pyarrow": "boto3_raw",
    "sftp": "paramiko_raw",
    "azure": "azure_blob_raw",
    "s3-latency": "boto3_raw",
    "sftp-latency": "paramiko_raw",
    "azure-latency": "azure_blob_raw",
}


def _magnitude(rs_seconds: float, raw_seconds: float) -> str:
    """Classify the size of the delta vs the raw SDK into a neutral band.

    This reports *how big* the measured delta is, never whether it is
    acceptable — acceptability depends on the reader's workload, latency
    budget, and alternatives, so it is the reader's call, not the suite's.
    Direction (faster / slower) is reported factually by the caller.

    | Band    | Criteria (on ``|delta|``)          |
    |---------|------------------------------------|
    | sub-ms  | < 1ms absolute                     |
    | <10%    | >= 1ms absolute and < 10% of raw   |
    | 10-50%  | >= 1ms absolute and 10-50% of raw  |
    | >50%    | >= 1ms absolute and > 50% of raw   |

    The 1ms floor keeps sub-millisecond deltas — where a percentage is
    noise — in their own band. Unlike the previous verdict scale, there is
    no secondary 5ms floor: a >50% delta reads as ">50%" whatever its
    absolute size, so a magnitude band describes the delta rather than
    gating it behind a second absolute threshold.
    """
    if raw_seconds <= 0:
        return ""
    delta_abs = abs(rs_seconds - raw_seconds) * 1000  # ms
    delta_pct = abs((rs_seconds - raw_seconds) / raw_seconds) * 100
    if delta_abs < 1:
        return "sub-ms"
    if delta_pct < 10:
        return "<10%"
    if delta_pct <= 50:
        return "10-50%"
    return ">50%"


def _print_user_report(
    table: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Print a condensed user-facing report: measured delta + magnitude band.

    Presents the remote-store time, the raw-SDK time, the factual direction
    (faster / slower), and a neutral magnitude band. It does not judge
    whether the overhead is acceptable — that is the reader's call.
    """
    for backend in BACKEND_ORDER:
        labels = TARGET_LABELS.get(backend, {})
        raw_key = RAW_SDK_TARGET.get(backend)
        if not raw_key or raw_key not in labels:
            continue
        has_data = any(backend in row for row in table.values())
        if not has_data:
            continue

        print(f"\n### {BACKEND_LABELS.get(backend, backend)}\n")

        for label, per_backend in table.items():
            if backend not in per_backend:
                continue
            targets = per_backend[backend]
            rs = targets.get("remote_store")
            raw = targets.get(raw_key)
            if rs is None or raw is None:
                continue

            rs_str = _format_time(rs)
            raw_str = _format_time(raw)
            band = _magnitude(rs, raw)
            delta_pct = ((rs - raw) / raw) * 100 if raw > 0 else 0
            direction = "faster" if delta_pct < 0 else "slower"

            print(f"  {label + ':':<16} {rs_str:>8} vs {raw_str:>8} raw -> {abs(delta_pct):.0f}% {direction} ({band})")


def _print_comparative_text(
    table: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Print comparative table as formatted text."""
    for backend in BACKEND_ORDER:
        labels = TARGET_LABELS.get(backend, {})
        if len(labels) < 2:
            continue
        has_data = any(backend in row for row in table.values())
        if not has_data:
            continue

        target_order = list(labels.keys())
        print(f"\n### {BACKEND_LABELS.get(backend, backend)}\n")

        label_w = max((len(lab) for lab in table), default=15)
        col_w = 16
        header = f"{'Operation':<{label_w}}"
        for tk in target_order:
            header += f"  {labels[tk]:>{col_w}}"
        print(header)
        print("-" * len(header))

        for label, per_backend in table.items():
            if backend not in per_backend:
                continue
            targets = per_backend[backend]
            baseline = targets.get("remote_store", 0)
            line = f"{label:<{label_w}}"
            for tk in target_order:
                if tk in targets:
                    cell = _format_time(targets[tk])
                    if tk != "remote_store" and baseline > 0:
                        cell += _format_relative(targets[tk], baseline)
                    line += f"  {cell:>{col_w}}"
                else:
                    line += f"  {'--':>{col_w}}"
            print(line)


def _render_comparative_markdown(
    table: dict[str, dict[str, dict[str, float]]],
    machine_info: dict[str, Any] | None = None,
) -> str:
    """Render comparative results as Markdown. Returns the full string."""
    lines: list[str] = []
    lines.append(f"<!-- Generated {datetime.datetime.now(tz=datetime.timezone.utc):%Y-%m-%d %H:%M} UTC -->")
    if machine_info:
        cpu = machine_info.get("cpu", {}).get("brand_raw", "unknown")
        py = machine_info.get("python_version", "?")
        lines.append(f"<!-- Hardware: {cpu}, Python {py}, {platform.system()} -->")
    # Placement marker so the generated file satisfies the docs-framework G-01
    # gate: this file is embedded into the published guide via --8<-- but is not
    # itself a rendered page. Without this, every regeneration drops the marker
    # and fails `check_docs_framework.py`.
    lines.append("<!-- doc: repo-only -->")
    lines.append("")

    for backend in BACKEND_ORDER:
        labels = TARGET_LABELS.get(backend, {})
        if len(labels) < 2:
            continue
        has_data = any(backend in row for row in table.values())
        if not has_data:
            continue

        target_order = list(labels.keys())
        lines.append(f"### {BACKEND_LABELS.get(backend, backend)}")
        lines.append("")

        header = "| Operation |"
        separator = "|-----------|"
        for tk in target_order:
            header += f" {labels[tk]} |"
            separator += "-------:|"
        lines.append(header)
        lines.append(separator)

        for label, per_backend in table.items():
            if backend not in per_backend:
                continue
            targets = per_backend[backend]
            baseline = targets.get("remote_store", 0)
            row = f"| {label} |"
            for tk in target_order:
                if tk in targets:
                    cell = _format_time(targets[tk])
                    if tk != "remote_store" and baseline > 0:
                        cell += _format_relative(targets[tk], baseline)
                    row += f" {cell} |"
                else:
                    row += " -- |"
            lines.append(row)
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark summary report")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare latest run against the previous one",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON",
    )
    parser.add_argument(
        "--comparative",
        action="store_true",
        help="Show remote-store vs raw SDK vs fsspec per backend",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output as Markdown tables (use with --comparative)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="Condensed user-facing report: measured delta + magnitude band (sub-ms/<10%/10-50%/>50%)",
    )
    parser.add_argument(
        "--regression",
        action="store_true",
        help="Compare the run against a committed baseline and exit non-zero on regressions",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline JSON to compare against (required with --regression)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD,
        help=f"Regression multiplier: flag ops slower than baseline x this (default {DEFAULT_REGRESSION_THRESHOLD})",
    )
    parser.add_argument(
        "--min-abs",
        type=float,
        default=0.0,
        dest="min_abs",
        help="Absolute floor in seconds: baselines below this are shown but never gate (default 0)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(".benchmarks"),
        help="Benchmarks directory (default: .benchmarks)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Explicit JSON file to load (overrides auto-detection from --dir)",
    )
    args = parser.parse_args()

    if args.file:
        if not args.file.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        target_file = args.file
        files = [args.file]
    else:
        files = _find_json_files(args.dir)
        if not files:
            print(f"No benchmark files found in {args.dir}", file=sys.stderr)
            sys.exit(1)
        target_file = files[-1]

    # Load target file
    latest = json.loads(target_file.read_text())

    # --- Regression mode ---
    if args.regression:
        if args.baseline is None:
            print("--regression requires --baseline <file>", file=sys.stderr)
            sys.exit(2)
        if not args.baseline.exists():
            print(f"Baseline file not found: {args.baseline}", file=sys.stderr)
            sys.exit(2)
        baseline = json.loads(args.baseline.read_text())
        # Full table (every remote_store cell), not the SUMMARY_ROWS subset, so
        # the whole committed baseline is compared — read/stream/copy-move paths
        # included, not just the summary write/list ops.
        current_table = _build_full_table(latest["benchmarks"])
        baseline_table = _build_full_table(baseline["benchmarks"])
        rows = _regression_rows(current_table, baseline_table, args.threshold, args.min_abs)
        regressed = _print_regression(rows, args.threshold, args.min_abs)
        if regressed:
            print("\nRegression detected: one or more operations exceeded the threshold.", file=sys.stderr)
            sys.exit(1)
        print("\nNo regressions above threshold.")
        return

    # --- Comparative mode ---
    if args.comparative:
        comp_table = _build_comparative_table(latest["benchmarks"])
        if args.markdown:
            md = _render_comparative_markdown(comp_table, latest.get("machine_info"))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(md, encoding="utf-8")
                print(f"Wrote comparative report to {args.output}")
            else:
                print(md)
        else:
            machine = latest.get("machine_info", {})
            cpu = machine.get("cpu", {}).get("brand_raw", "unknown")
            py = machine.get("python_version", "?")
            print(f"Comparative report -- {cpu}, Python {py}")
            print()
            _print_comparative_text(comp_table)
        return

    # --- User-facing magnitude mode ---
    if args.user:
        comp_table = _build_comparative_table(latest["benchmarks"])
        machine = latest.get("machine_info", {})
        cpu = machine.get("cpu", {}).get("brand_raw", "unknown")
        py = machine.get("python_version", "?")
        print(f"User report -- {cpu}, Python {py}")
        _print_user_report(comp_table)
        print()
        return

    # --- Standard summary mode ---
    table = _build_table(latest["benchmarks"])

    # Load previous if comparing
    previous_table = None
    if args.compare:
        if len(files) < 2:
            print("Only one benchmark file found -- nothing to compare.", file=sys.stderr)
        else:
            previous = json.loads(files[-2].read_text())
            previous_table = _build_table(previous["benchmarks"])

    # Print header
    if not args.json_output:
        machine = latest.get("machine_info", {})
        cpu = machine.get("cpu", {}).get("brand_raw", "unknown")
        py = machine.get("python_version", "?")
        ts = latest.get("datetime", "")
        print(f"Benchmark report -- {cpu}, Python {py}")
        if ts:
            print(f"Run: {ts}")
        if args.compare and previous_table:
            prev_ts = json.loads(files[-2].read_text()).get("datetime", "")
            print(f"vs:  {prev_ts}")
        print()

    if args.json_output:
        _print_json(table, previous_table)
    else:
        _print_table(table, previous_table)


if __name__ == "__main__":
    main()
