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

from benchmarks.report import (  # noqa: E402
    _LATENCY_VARIANT,
    COMPARATIVE_BACKENDS,
    OVERHEAD_OPS,
    RAW_SDK_TARGET,
    _build_comparative_table,
    _parse_backend_and_target,
    _test_name,
)
from benchmarks.report import BACKEND_LABELS as _REPORT_LABELS  # noqa: E402

# ---------------------------------------------------------------------------
# Shared configuration
# ---------------------------------------------------------------------------

# COMPARATIVE_BACKENDS, OVERHEAD_OPS, and _LATENCY_VARIANT are imported from
# report.py (matplotlib-free) so the slim_run_of_record guard can share them.

# Extend report labels with emulator suffixes for chart clarity.
BACKEND_LABELS = {
    **_REPORT_LABELS,
    "azure": "Azure (Azurite)",
    "s3-pyarrow": "S3-PyArrow",
}

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
    "s3-pyarrow": "#7C4DFF",  # deep purple A200
    "sftp": "#7986CB",  # indigo 300
    "azure": "#1A237E",  # indigo 900
    "local": "#C5CAE9",  # indigo 100
}

# RTT profile metadata: (profile_name, nominal_rtt_ms).
RTT_PROFILES = [("clean", 0), ("rtt20", 20), ("rtt50", 50), ("rtt100", 100)]

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
# Chart 1: Overhead (ms) by backend (grouped bar)
# ---------------------------------------------------------------------------


def chart_overhead(benchmarks: list[dict[str, Any]], output: Path) -> None:
    """Generate grouped bar chart: absolute ms overhead vs raw SDK per backend.

    Overhead is ``remote_store - raw_sdk`` in milliseconds (BK-314) — the
    absolute cost the wrapper adds, not a percentage of raw time. A percentage
    axis hides that the cost is a fixed number of extra round trips, so under
    latency it scales with RTT rather than shrinking to a vanishing share.
    """
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
            if rs is not None and raw is not None:
                overheads.append((rs - raw) * 1000)
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
        labels = [f"{v:+.1f}" if not np.isnan(v) and abs(v) >= 0.1 else "" for v in overheads]
        ax.bar_label(bars, labels=labels, fontsize=7, label_type="edge")

    ax.set_xlabel("")
    ax.set_ylabel("Overhead vs raw SDK (ms)", fontsize=_LABEL_SIZE)
    ax.set_title("Abstraction overhead by backend (clean, no added latency)", fontsize=_TITLE_SIZE, pad=12)
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
# Chart 2: Overhead vs RTT (line chart)
# ---------------------------------------------------------------------------


def _overhead_ms_by_profile(
    profile_data: dict[str, list[dict[str, Any]]],
    base_backends: list[str],
) -> dict[str, dict[str, dict[str, tuple[float, float]]]]:
    """Return ``{profile: {base_backend: {op_label: (raw_ms, overhead_ms)}}}``.

    Uses the base backend for the ``clean`` profile and the Toxiproxy
    ``-latency`` variant for each latency profile, so the overhead ratio has
    both operands (see the run-of-record guard 2). Overhead is
    ``(remote_store - raw_sdk)`` in milliseconds.
    """
    out: dict[str, dict[str, dict[str, tuple[float, float]]]] = {}
    for profile, benchmarks in profile_data.items():
        data = _build_comparative_table(benchmarks, ops=OVERHEAD_OPS)
        per_backend: dict[str, dict[str, tuple[float, float]]] = {}
        for base in base_backends:
            bk = _LATENCY_VARIANT[base] if profile != "clean" else base
            raw_key = RAW_SDK_TARGET.get(bk, RAW_SDK_TARGET.get(base, ""))
            op_ms: dict[str, tuple[float, float]] = {}
            for _, _, op_label in OVERHEAD_OPS:
                targets = data.get(op_label, {}).get(bk, {})
                rs = targets.get("remote_store")
                raw = targets.get(raw_key)
                if rs is not None and raw is not None:
                    op_ms[op_label] = (raw * 1000, (rs - raw) * 1000)
            if op_ms:
                per_backend[base] = op_ms
        if per_backend:
            out[profile] = per_backend
    return out


def chart_overhead_vs_rtt(
    profile_data: dict[str, list[dict[str, Any]]],
    output: Path,
) -> None:
    """Generate line chart: absolute ms overhead at different RTTs.

    Overhead is remote-store minus raw SDK in milliseconds (BK-314). Because the
    wrapper's cost is a fixed number of extra round trips, the line *rises* with
    RTT rather than flattening toward a vanishing percentage.

    Args:
        profile_data: ``{profile_name: benchmarks_list}`` from multiple
            ``--network-profile`` runs. Must include ``"clean"`` as baseline
            and at least one latency profile.
        output: Path for the SVG file.
    """
    # Compute ms overhead per (backend, op) at each RTT. Use latency backends
    # (s3-latency etc.) for latency profiles, base backends for clean.
    base_backends = ["s3", "sftp", "azure"]

    # Build {profile: {base_backend: {op_label: avg overhead_ms}}}
    raw_ovh_by_profile = _overhead_ms_by_profile(profile_data, base_backends)
    overhead_by_profile: dict[str, dict[str, dict[str, float]]] = {
        profile: {base: {op: ovh for op, (_raw, ovh) in ops.items()} for base, ops in per_backend.items()}
        for profile, per_backend in raw_ovh_by_profile.items()
    }

    if len(overhead_by_profile) < 2:
        # Not enough data — generate placeholder.
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(
            0.5,
            0.5,
            "Overhead vs RTT chart\n\nRun benchmarks at each network profile\n"
            "and re-run bench-charts to populate.\n\n"
            f"Profiles found: {', '.join(sorted(profile_data.keys())) or 'none'}",
            ha="center",
            va="center",
            fontsize=_LABEL_SIZE,
            color="#888",
            transform=ax.transAxes,
        )
        ax.set_xlabel("Network latency (ms)", fontsize=_LABEL_SIZE)
        ax.set_ylabel("Overhead vs raw SDK (ms)", fontsize=_LABEL_SIZE)
        ax.set_title("Overhead vs network latency", fontsize=_TITLE_SIZE, pad=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, format="svg", bbox_inches="tight")
        plt.close(fig)
        print(f"  {output} (placeholder — need clean + at least one latency profile)")
        return

    # Plot: one line per backend, average overhead across ops at each RTT.
    rtt_lookup = dict(RTT_PROFILES)
    profiles_ordered = [p for p, _ in RTT_PROFILES if p in overhead_by_profile]
    rtts = [rtt_lookup[p] for p in profiles_ordered]

    fig, ax = plt.subplots(figsize=(8, 4.5))

    for base in base_backends:
        overheads = []
        for profile in profiles_ordered:
            ops_at_profile = overhead_by_profile.get(profile, {}).get(base, {})
            if ops_at_profile:
                overheads.append(sum(ops_at_profile.values()) / len(ops_at_profile))
            else:
                overheads.append(float("nan"))

        if any(not np.isnan(v) for v in overheads):
            ax.plot(
                rtts,
                overheads,
                "-o",
                color=COLORS.get(base, "#888"),
                label=BACKEND_LABELS.get(base, base),
                markersize=5,
            )

    ax.set_xlabel("Network round-trip time (ms)", fontsize=_LABEL_SIZE)
    ax.set_ylabel("Average overhead vs raw SDK (ms)", fontsize=_LABEL_SIZE)
    ax.set_title("Overhead grows with round-trip time", fontsize=_TITLE_SIZE, pad=12)
    ax.set_xticks(rtts)
    ax.tick_params(axis="both", labelsize=_TICK_SIZE)
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
# Chart 2b: Overhead decomposition — raw SDK time + overhead (ms) stacked
# ---------------------------------------------------------------------------

# Decomposition stack colors: raw SDK time as a recessive base, remote-store
# overhead as the accent that carries the story.
_RAW_STACK_COLOR = "#C5CAE9"  # indigo 100
_OVERHEAD_STACK_COLOR = "#3F51B5"  # indigo 500


def chart_overhead_decomposition(
    profile_data: dict[str, list[dict[str, Any]]],
    output: Path,
) -> None:
    """Stacked bars: raw SDK time + remote-store overhead (ms) per RTT profile.

    One panel per network backend; each bar decomposes the mean per-op time
    (averaged across the overhead ops) into the raw SDK cost and the
    remote-store overhead on top, labelled in ms and as a share of the total
    (BK-314). It makes the mechanism visible: the raw op time and the overhead
    both scale with RTT because both are round-trip counts, so the absolute
    overhead grows even where its share of the total stays modest.

    Args:
        profile_data: ``{profile_name: benchmarks_list}`` across
            ``--network-profile`` runs. Needs ``"clean"`` plus at least one
            latency profile.
        output: Path for the SVG file.
    """
    base_backends = ["s3", "sftp", "azure"]
    raw_ovh = _overhead_ms_by_profile(profile_data, base_backends)

    # Average raw and overhead across the ops present, per (profile, backend).
    # {backend: {profile: (avg_raw_ms, avg_overhead_ms)}}
    by_backend: dict[str, dict[str, tuple[float, float]]] = {}
    for profile, per_backend in raw_ovh.items():
        for base, op_ms in per_backend.items():
            raws = [raw for raw, _ in op_ms.values()]
            ovhs = [ovh for _, ovh in op_ms.values()]
            if raws:
                by_backend.setdefault(base, {})[profile] = (
                    sum(raws) / len(raws),
                    sum(ovhs) / len(ovhs),
                )

    profiles_ordered = [p for p, _ in RTT_PROFILES if any(p in v for v in by_backend.values())]
    backends = [b for b in base_backends if b in by_backend]

    if len(profiles_ordered) < 2 or not backends:
        # Not enough data — generate a placeholder mirroring the RTT chart.
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(
            0.5,
            0.5,
            "Overhead decomposition chart\n\nRun benchmarks at each network profile\n"
            "and re-run bench-charts to populate.\n\n"
            f"Profiles found: {', '.join(sorted(profile_data.keys())) or 'none'}",
            ha="center",
            va="center",
            fontsize=_LABEL_SIZE,
            color="#888",
            transform=ax.transAxes,
        )
        ax.set_ylabel("Mean time per op (ms)", fontsize=_LABEL_SIZE)
        ax.set_title("Where the time goes: raw SDK + remote-store overhead", fontsize=_TITLE_SIZE, pad=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, format="svg", bbox_inches="tight")
        plt.close(fig)
        print(f"  {output} (placeholder — need clean + at least one latency profile)")
        return

    rtt_lookup = dict(RTT_PROFILES)
    x = np.arange(len(profiles_ordered))
    xtick_labels = [f"{p}\n{rtt_lookup[p]} ms" for p in profiles_ordered]

    fig, axes = plt.subplots(1, len(backends), figsize=(4.2 * len(backends), 4.5))
    if len(backends) == 1:
        axes = [axes]

    for ax, backend in zip(axes, backends, strict=True):
        raws = [by_backend[backend].get(p, (float("nan"), float("nan")))[0] for p in profiles_ordered]
        ovhs = [by_backend[backend].get(p, (float("nan"), float("nan")))[1] for p in profiles_ordered]
        # A stacked bar can only draw a non-negative segment; clamp the drawn
        # overhead height but always label the true (possibly negative) value.
        drawn_ovh = [max(0.0, o) if not np.isnan(o) else 0.0 for o in ovhs]

        ax.bar(
            x,
            raws,
            0.6,
            color=_RAW_STACK_COLOR,
            edgecolor="white",
            linewidth=0.5,
            label="Raw SDK time",
        )
        ax.bar(
            x,
            drawn_ovh,
            0.6,
            bottom=raws,
            color=_OVERHEAD_STACK_COLOR,
            edgecolor="white",
            linewidth=0.8,  # 2px surface gap between the two fills
            label="remote-store overhead",
        )

        for xi, raw, ovh in zip(x, raws, ovhs, strict=True):
            if np.isnan(raw) or np.isnan(ovh):
                continue
            total = raw + ovh
            share = (ovh / total * 100) if total > 0 else 0.0
            top = raw + max(0.0, ovh)
            # `{:+.0f}` carries the sign itself — a positive overhead reads
            # "+30 ms", a faster-than-raw one "-2 ms" (never "+-2 ms").
            text = f"{ovh:+.0f} ms\n({share:+.0f}%)" if abs(ovh) >= 0.5 else "~0 ms"
            ax.text(xi, top, text, ha="center", va="bottom", fontsize=7, color="#212121")

        ax.set_title(BACKEND_LABELS.get(backend, backend), fontsize=_LABEL_SIZE)
        ax.set_xticks(x)
        ax.set_xticklabels(xtick_labels, fontsize=_TICK_SIZE)
        ax.tick_params(axis="y", labelsize=_TICK_SIZE)
        ax.margins(y=0.15)  # headroom for the top labels
        ax.grid(axis="y", alpha=_GRID_ALPHA)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].set_ylabel("Mean time per op (ms)", fontsize=_LABEL_SIZE)
    fig.tight_layout()
    # Title on top, then a single shared legend just below it (identity is
    # never colour-alone); both sit above the panels with a clear gap.
    fig.suptitle("Where the time goes: raw SDK + remote-store overhead", fontsize=_TITLE_SIZE, y=1.13)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, fontsize=_TICK_SIZE, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.05), ncol=2
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, format="svg", bbox_inches="tight")
    plt.close(fig)
    print(f"  {output}")


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
# Chart 4: S3 vs S3-PyArrow side-by-side (grouped bar)
# ---------------------------------------------------------------------------


_S3_COMPARISON_OPS: list[tuple[str, dict[str, Any], str]] = [
    ("test_write_bytes", {"payload": 1024}, "Write 1KB"),
    ("test_write_bytes", {"payload": 1048576}, "Write 1MB"),
    ("test_read_bytes", {"payload": 1024}, "Read 1KB"),
    ("test_read_bytes", {"payload": 1048576}, "Read 1MB"),
    ("test_exists_hit", {}, "Exists"),
    ("test_list_files", {}, "List 50"),
    ("test_delete", {}, "Delete"),
]


def chart_s3_comparison(benchmarks: list[dict[str, Any]], output: Path) -> None:
    """Generate grouped bar chart: S3 vs S3-PyArrow absolute latency."""
    data = _build_comparative_table(benchmarks, ops=_S3_COMPARISON_OPS)
    op_labels = [label for _, _, label in _S3_COMPARISON_OPS]
    backends = ["s3", "s3-pyarrow"]

    # Check we have remote_store data for both backends.
    has_data = all(
        any(data.get(op, {}).get(b, {}).get("remote_store") is not None for op in op_labels) for b in backends
    )
    if not has_data:
        print(f"  {output} (skipped — need both S3 and S3-PyArrow data)", file=sys.stderr)
        return

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(op_labels))
    bar_width = 0.3

    for i, backend in enumerate(backends):
        latencies_ms = []
        for op_label in op_labels:
            targets = data.get(op_label, {}).get(backend, {})
            rs = targets.get("remote_store")
            latencies_ms.append(rs * 1000 if rs is not None else float("nan"))

        offset = (i - 0.5) * bar_width
        bars = ax.bar(
            x + offset,
            latencies_ms,
            bar_width,
            label=BACKEND_LABELS.get(backend, backend),
            color=COLORS.get(backend, "#888"),
            edgecolor="white",
            linewidth=0.5,
        )
        labels = [
            f"{v:.1f}" if not np.isnan(v) and v < 100 else (f"{v:.0f}" if not np.isnan(v) else "") for v in latencies_ms
        ]
        ax.bar_label(bars, labels=labels, fontsize=7, label_type="edge")

    ax.set_xlabel("")
    ax.set_ylabel("Latency (ms)", fontsize=_LABEL_SIZE)
    ax.set_title("S3 vs S3-PyArrow (remote-store)", fontsize=_TITLE_SIZE, pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(op_labels, fontsize=_TICK_SIZE)
    ax.tick_params(axis="y", labelsize=_TICK_SIZE)
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
# Main
# ---------------------------------------------------------------------------


def _load_profile_data(files: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """Load benchmark files and group by network profile.

    Returns ``{profile_name: merged_benchmarks_list}``.  Files without
    a ``network_profile`` key are treated as ``"clean"``.
    """
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        data = json.loads(f.read_text())
        profile = data.get("network_profile", "clean")
        by_profile.setdefault(profile, []).extend(data.get("benchmarks", []))
    return by_profile


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
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Explicit JSON file for baseline charts (overrides auto-detection)",
    )
    args = parser.parse_args()

    # Baseline file for single-file charts (overhead, throughput, s3-comparison).
    if args.file:
        if not args.file.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        baseline_file = args.file
        files = sorted(args.dir.rglob("*.json"))
        if args.file.resolve() not in {f.resolve() for f in files}:
            files.append(args.file)
    else:
        files = sorted(args.dir.rglob("*.json"))
        if not files:
            print(f"No benchmark files found in {args.dir}", file=sys.stderr)
            sys.exit(1)
        baseline_file = files[-1]

    latest = json.loads(baseline_file.read_text())
    benchmarks = latest["benchmarks"]
    print(f"Loaded {len(benchmarks)} benchmarks from {baseline_file.name}")
    print("Generating charts:")

    _apply_style()

    chart_overhead(benchmarks, args.output_dir / "overhead.svg")
    chart_throughput(benchmarks, args.output_dir / "throughput.svg")
    chart_s3_comparison(benchmarks, args.output_dir / "s3-comparison.svg")

    # Overhead-vs-RTT and the decomposition need data from multiple profiles.
    profile_data = _load_profile_data(files)
    profiles_found = sorted(profile_data.keys())
    print(f"Network profiles found: {', '.join(profiles_found)}")
    chart_overhead_vs_rtt(profile_data, args.output_dir / "overhead-vs-rtt.svg")
    chart_overhead_decomposition(profile_data, args.output_dir / "overhead-decomposition.svg")

    print("Done.")


if __name__ == "__main__":
    main()
