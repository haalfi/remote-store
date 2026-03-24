"""Generate SVG benchmark charts for the performance guide.

Reads saved pytest-benchmark JSON from ``.benchmarks/`` and produces
SVG charts in ``docs-src/img/benchmarks/``.

Usage::

    hatch run bench-charts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — must precede pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from benchmarks.report import BACKEND_LABELS as _REPORT_LABELS  # noqa: E402
from benchmarks.report import (  # noqa: E402
    RAW_SDK_TARGET,
    _build_comparative_table,
    _parse_backend_and_target,
    _test_name,
)

# ---------------------------------------------------------------------------
# Shared configuration
# ---------------------------------------------------------------------------

# Backends shown in comparative charts (must have raw SDK baseline).
COMPARATIVE_BACKENDS = ["s3", "sftp", "azure"]

# Extend report labels with emulator suffixes for chart clarity.
BACKEND_LABELS = {**_REPORT_LABELS, "azure": "Azure (Azurite)"}

# Operations for overhead chart.
OVERHEAD_OPS: list[tuple[str, dict[str, Any], str]] = [
    ("test_write_bytes", {"payload": 1048576}, "Write 1MB"),
    ("test_read_bytes", {"payload": 1048576}, "Read 1MB"),
    ("test_exists_hit", {}, "Exists"),
    ("test_list_files", {}, "List 50"),
    ("test_delete", {}, "Delete"),
]

# Throughput file sizes.
THROUGHPUT_SIZES: list[tuple[int, str]] = [
    (1024, "1KB"),
    (65536, "64KB"),
    (1048576, "1MB"),
    (10485760, "10MB"),
]

# Chart colors — Material Design indigo palette to match docs theme.
COLORS = {
    "s3": "#3F51B5",  # indigo 500 (primary)
    "sftp": "#7986CB",  # indigo 300
    "azure": "#1A237E",  # indigo 900
    "local": "#C5CAE9",  # indigo 100
}

# Style constants.
_FONT_FAMILY = "sans-serif"
_TITLE_SIZE = 13
_LABEL_SIZE = 10
_TICK_SIZE = 9
_GRID_ALPHA = 0.15
_BAR_WIDTH = 0.22


def _apply_style() -> None:
    """Apply a clean chart style matching the docs theme."""
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#BDBDBD",
            "axes.labelcolor": "#212121",
            "text.color": "#212121",
            "xtick.color": "#616161",
            "ytick.color": "#616161",
            "grid.color": "#E0E0E0",
            "legend.frameon": False,
            "legend.fontsize": 9,
            "font.family": _FONT_FAMILY,
        }
    )


# ---------------------------------------------------------------------------
# Data extraction (shared helpers imported from report.py)
# ---------------------------------------------------------------------------


def _extract_throughput(
    benchmarks: list[dict[str, Any]],
    test_prefix: str,
    sizes: list[tuple[int, str]],
) -> dict[str, dict[str, dict[int, float]]]:
    """Return {backend: {target_kind: {payload_bytes: mean_seconds}}}."""
    result: dict[str, dict[str, dict[int, float]]] = {}
    for bm in benchmarks:
        if _test_name(bm) != test_prefix:
            continue
        bt = _parse_backend_and_target(bm)
        if bt is None:
            continue
        backend_type, target_kind = bt
        payload = bm.get("params", {}).get("payload")
        if payload is None:
            continue
        if payload not in {s for s, _ in sizes}:
            continue
        result.setdefault(backend_type, {}).setdefault(target_kind, {})[payload] = bm["stats"]["mean"]
    return result


# ---------------------------------------------------------------------------
# Chart 1: Overhead % by backend (grouped bar)
# ---------------------------------------------------------------------------


def chart_overhead(benchmarks: list[dict[str, Any]], output: Path) -> None:
    """Generate grouped bar chart: overhead % vs raw SDK per backend."""
    data = _build_comparative_table(benchmarks, ops=OVERHEAD_OPS)
    op_labels = [label for _, _, label in OVERHEAD_OPS]
    backends = [b for b in COMPARATIVE_BACKENDS if any(b in data.get(op, {}) for op in op_labels)]

    if not backends:
        print("No comparative data found for overhead chart.", file=sys.stderr)
        return

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(op_labels))

    for i, backend in enumerate(backends):
        overheads = []
        for op_label in op_labels:
            targets = data.get(op_label, {}).get(backend, {})
            rs = targets.get("remote_store")
            raw = targets.get(RAW_SDK_TARGET.get(backend, ""))
            if rs is not None and raw is not None and raw > 0:
                pct = ((rs - raw) / raw) * 100
                overheads.append(pct)
            else:
                overheads.append(float("nan"))

        offset = (i - len(backends) / 2 + 0.5) * _BAR_WIDTH
        bars = ax.bar(
            x + offset,
            overheads,
            _BAR_WIDTH,
            label=BACKEND_LABELS.get(backend, backend),
            color=COLORS.get(backend, "#888"),
            edgecolor="white",
            linewidth=0.5,
        )
        # Value labels on bars (bar_label handles alignment automatically).
        labels = [f"{v:+.0f}%" if not np.isnan(v) and abs(v) > 3 else "" for v in overheads]
        ax.bar_label(bars, labels=labels, fontsize=7, label_type="edge")

    ax.set_xlabel("")
    ax.set_ylabel("Overhead vs raw SDK (%)", fontsize=_LABEL_SIZE)
    ax.set_title("Abstraction overhead by backend", fontsize=_TITLE_SIZE, pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(op_labels, fontsize=_TICK_SIZE)
    ax.tick_params(axis="y", labelsize=_TICK_SIZE)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.legend(fontsize=_TICK_SIZE, frameon=False)
    ax.grid(axis="y", alpha=_GRID_ALPHA)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  {output}")


# ---------------------------------------------------------------------------
# Chart 2: Overhead vs RTT (line chart — placeholder structure)
# ---------------------------------------------------------------------------


def chart_overhead_vs_rtt(benchmarks: list[dict[str, Any]], output: Path) -> None:
    """Generate line chart: overhead % at different RTTs.

    This chart requires benchmark data from multiple ``--network-profile``
    runs stored in separate JSON files. Until that data is collected, this
    function generates a placeholder with a note.
    """
    # The data for this chart comes from running benchmarks at clean, rtt20,
    # rtt50, rtt100 profiles and saving each as a separate JSON file.
    # For now, generate a placeholder noting data collection is needed.
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(
        0.5,
        0.5,
        "Overhead vs RTT chart\n\nRun benchmarks at each network profile\nand re-run bench-charts to populate.",
        ha="center",
        va="center",
        fontsize=_LABEL_SIZE,
        color="#888",
        transform=ax.transAxes,
    )
    ax.set_xlabel("Network latency (ms)", fontsize=_LABEL_SIZE)
    ax.set_ylabel("Overhead vs raw SDK (%)", fontsize=_LABEL_SIZE)
    ax.set_title("Overhead collapses under network latency", fontsize=_TITLE_SIZE, pad=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  {output} (placeholder — needs multi-profile data)")


# ---------------------------------------------------------------------------
# Chart 3: Throughput by file size (line chart, one panel per backend)
# ---------------------------------------------------------------------------


def chart_throughput(benchmarks: list[dict[str, Any]], output: Path) -> None:
    """Generate line chart: throughput (MB/s) by file size per backend."""
    write_data = _extract_throughput(benchmarks, "test_write_bytes", THROUGHPUT_SIZES)
    read_data = _extract_throughput(benchmarks, "test_read_bytes", THROUGHPUT_SIZES)

    backends = [b for b in COMPARATIVE_BACKENDS if b in write_data or b in read_data]
    if not backends:
        print("No throughput data found.", file=sys.stderr)
        return

    fig, axes = plt.subplots(1, len(backends), figsize=(5 * len(backends), 4), sharey=True)
    if len(backends) == 1:
        axes = [axes]

    # Canonical x positions and labels for all sizes.
    all_sizes = [sz for sz, _ in THROUGHPUT_SIZES]
    all_labels = [lbl for _, lbl in THROUGHPUT_SIZES]

    # Distinct colors: indigo for remote-store, amber for raw SDK.
    _RS_COLOR = "#3F51B5"  # indigo 500
    _RAW_COLOR = "#FF8F00"  # amber 800

    for ax, backend in zip(axes, backends, strict=True):
        for dataset, op_label, ls in [(write_data, "Write", "-"), (read_data, "Read", "--")]:
            targets = dataset.get(backend, {})
            for target_kind, style_suffix, color in [
                ("remote_store", "", _RS_COLOR),
                (RAW_SDK_TARGET.get(backend, ""), " (raw)", _RAW_COLOR),
            ]:
                size_means = targets.get(target_kind, {})
                if not size_means:
                    continue
                # Plot at canonical x positions so all series align.
                x_positions = []
                throughputs = []
                for i, sz in enumerate(all_sizes):
                    if sz in size_means and size_means[sz] > 0:
                        mb_per_s = (sz / 1_048_576) / size_means[sz]
                        x_positions.append(i)
                        throughputs.append(mb_per_s)
                if throughputs:
                    label = f"{op_label}{style_suffix}"
                    ax.plot(
                        x_positions,
                        throughputs,
                        ls,
                        color=color,
                        label=label,
                        marker="o",
                        markersize=4,
                    )

        ax.set_title(BACKEND_LABELS.get(backend, backend), fontsize=_LABEL_SIZE)
        ax.set_xticks(range(len(all_labels)))
        ax.set_xticklabels(all_labels, fontsize=_TICK_SIZE)
        ax.tick_params(axis="y", labelsize=_TICK_SIZE)
        ax.legend(fontsize=8, frameon=False, loc="upper left")
        ax.grid(axis="y", alpha=_GRID_ALPHA)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].set_ylabel("Throughput (MB/s)", fontsize=_LABEL_SIZE)
    fig.suptitle("Throughput by file size", fontsize=_TITLE_SIZE, y=1.02)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate benchmark charts")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(".benchmarks"),
        help="Benchmarks directory (default: .benchmarks)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs-src/img/benchmarks"),
        help="Output directory for SVG charts",
    )
    args = parser.parse_args()

    files = sorted(args.dir.rglob("*.json"))
    if not files:
        print(f"No benchmark files found in {args.dir}", file=sys.stderr)
        sys.exit(1)

    latest = json.loads(files[-1].read_text())
    benchmarks = latest["benchmarks"]
    print(f"Loaded {len(benchmarks)} benchmarks from {files[-1].name}")
    print("Generating charts:")

    _apply_style()

    chart_overhead(benchmarks, args.output_dir / "overhead.svg")
    chart_overhead_vs_rtt(benchmarks, args.output_dir / "overhead-vs-rtt.svg")
    chart_throughput(benchmarks, args.output_dir / "throughput.svg")

    print("Done.")


if __name__ == "__main__":
    main()
