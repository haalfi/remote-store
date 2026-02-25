"""Generate a summary table from saved pytest-benchmark JSON files.

Usage::

    hatch run bench-report              # latest run
    hatch run bench-report --compare    # latest vs previous run
    hatch run bench-report --json       # machine-readable output
"""

from __future__ import annotations

import argparse
import json
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
        "--dir",
        type=Path,
        default=Path(".benchmarks"),
        help="Benchmarks directory (default: .benchmarks)",
    )
    args = parser.parse_args()

    files = _find_json_files(args.dir)
    if not files:
        print(f"No benchmark files found in {args.dir}", file=sys.stderr)
        sys.exit(1)

    # Load latest
    latest = json.loads(files[-1].read_text())
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
