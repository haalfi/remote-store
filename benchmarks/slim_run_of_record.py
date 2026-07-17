"""Slim raw pytest-benchmark JSON into the committed run of record and guard it.

The run of record (``benchmarks/results/run-of-record/``) is the committed,
diffable source for the published overhead charts and ``comparative.md``. This
script slims a raw pytest-benchmark JSON dump to the fields the generators read
— ``name`` / ``params`` / ``stats.mean``, plus the top-level ``network_profile``
and ``machine_info`` — and then asserts the three invariants that otherwise fail
**silently**: a wrong-shaped run of record ships a blank or placeholder chart
with no error (ID-230).

**This slimming deliberately diverges from the ``baseline/local-baseline.json``
recipe.** The baseline is a single clean-profile file that never feeds the
overhead-vs-RTT chart, so it can drop the top-level ``network_profile`` key. The
run of record **must not**: ``charts.py`` groups profiles by that *in-file*
field, not the filename (``charts._load_profile_data``). Strip it and every file
collapses to ``"clean"``, ``overhead_by_profile`` ends up with ``< 2`` profiles,
and the overhead-vs-RTT chart renders its placeholder instead of the real chart.

The three guarded invariants (see the ID-230 plan, § 3.5):

1. **Profiles present** — the committed set carries ``"clean"`` plus at least one
   latency profile, so the overhead-vs-RTT chart has ``>= 2`` profiles to plot
   and does not fall back to its placeholder.
2. **Latency files use ``-latency`` variants, both sides of the ratio** — each
   rtt file carries ``s3-latency`` / ``sftp-latency`` / ``azure-latency``
   benchmarks for *both* the ``remote_store`` target and its paired raw SDK
   target, so ``charts.py``'s ``_LATENCY_VARIANT`` lookup hits and the
   overhead-vs-rtt chart (which divides remote_store by raw) has both operands.
   A run that proxied the *base* backends, or captured only one side of the
   ratio, drops the series silently.
3. **Clean file carries the base comparative backends, both sides of the ratio**
   — the clean file has ``s3`` / ``s3-pyarrow`` / ``sftp`` / ``azure``
   ``remote_store`` **and** paired raw-SDK data for the overhead ops, so the
   three single-file charts (overhead / throughput / s3-comparison) read a real
   remote_store cell (and its raw divisor) instead of hitting their "No
   comparative data found" early return or blanking a backend. ``bench-charts``
   must then be invoked ``--file .../clean.json`` so those charts build from the
   clean run, not ``files[-1]``.

Usage::

    # slim raw dumps -> run-of-record/<profile>.json, then guard the set
    python benchmarks/slim_run_of_record.py \
        clean-raw.json rtt20-raw.json rtt50-raw.json rtt100-raw.json

    # re-guard the already-committed set without slimming
    python benchmarks/slim_run_of_record.py --check-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Import from report.py (matplotlib-free) rather than charts.py so this guard —
# and its tests — run in the lean tooling-tests lane that has no matplotlib.
from benchmarks.report import (
    _LATENCY_VARIANT,
    COMPARATIVE_BACKENDS,
    OVERHEAD_OPS,
    RAW_SDK_TARGET,
    _build_comparative_table,
    _parse_backend_and_target,
)

DEFAULT_OUT = Path("benchmarks/results/run-of-record")

# The -latency backends every rtt file must carry (guard 2).
_REQUIRED_LATENCY = set(_LATENCY_VARIANT.values())
# The base backends the clean file must carry comparative data for (guard 3).
_REQUIRED_CLEAN = list(COMPARATIVE_BACKENDS)


def _slim_benchmark(bm: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields the report/chart generators read from one entry."""
    return {
        "name": bm["name"],
        "params": bm.get("params", {}),
        "stats": {"mean": bm["stats"]["mean"]},
    }


def slim_file(src: Path, out_dir: Path) -> Path:
    """Slim one raw pytest-benchmark JSON into ``out_dir/<profile>.json``.

    Retains the top-level ``network_profile`` (load-bearing for the RTT chart)
    and ``machine_info`` (provenance header for ``comparative.md``).
    """
    data = json.loads(src.read_text())
    profile = data.get("network_profile", "clean")
    slim = {
        "network_profile": profile,
        "machine_info": data.get("machine_info", {}),
        "benchmarks": [_slim_benchmark(b) for b in data.get("benchmarks", [])],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{profile}.json"
    dest.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    return dest


def _backend_targets(benchmarks: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Map each backend type to the set of target kinds it carries."""
    out: dict[str, set[str]] = {}
    for bm in benchmarks:
        bt = _parse_backend_and_target(bm)
        if bt is not None:
            out.setdefault(bt[0], set()).add(bt[1])
    return out


def _missing_ratio_sides(targets_by_backend: dict[str, set[str]], required: list[str]) -> list[str]:
    """Required backends missing either side of the overhead ratio the chart computes.

    Each overhead chart divides a backend's ``remote_store`` mean by its raw-SDK
    mean, so *both* target kinds must be present or the series blanks/omits
    silently. Checking only one side (as an earlier revision did) lets a file
    with just a raw-SDK entry pass while the chart reads an absent
    ``remote_store`` cell.
    """
    missing: list[str] = []
    for backend in required:
        have = targets_by_backend.get(backend, set())
        raw = RAW_SDK_TARGET.get(backend, "")
        if "remote_store" not in have or raw not in have:
            missing.append(backend)
    return sorted(missing)


def guard(out_dir: Path) -> list[str]:
    """Return a list of invariant violations for the run-of-record set (empty = ok)."""
    files = sorted(out_dir.glob("*.json"))
    if not files:
        return [f"no run-of-record JSON files in {out_dir}"]

    loaded = {f: json.loads(f.read_text()) for f in files}
    profiles = {d.get("network_profile", "clean") for d in loaded.values()}
    errors: list[str] = []

    # Guard 1: profiles present (clean + >= 1 latency).
    if "clean" not in profiles:
        errors.append(f"guard 1: no 'clean' profile among {[f.name for f in files]}")
    if len(profiles) < 2:
        errors.append(
            f"guard 1: overhead-vs-rtt needs >= 2 distinct profiles, found {sorted(profiles)} "
            "(did the slim drop the top-level network_profile key?)"
        )

    for f, d in loaded.items():
        profile = d.get("network_profile", "clean")
        benches = d.get("benchmarks", [])
        if profile == "clean":
            # Guard 3: the clean file feeds the single-file comparative charts,
            # which read the remote_store cell (and divide by the raw SDK). Scope
            # to the OVERHEAD_OPS the charts actually plot, and require BOTH sides
            # of the ratio per backend — presence alone (a raw-only entry) would
            # still blank the chart.
            comp = _build_comparative_table(benches, ops=OVERHEAD_OPS)
            targets_in_ops: dict[str, set[str]] = {}
            for per_backend in comp.values():
                for backend, kinds in per_backend.items():
                    targets_in_ops.setdefault(backend, set()).update(kinds)
            missing = _missing_ratio_sides(targets_in_ops, _REQUIRED_CLEAN)
            if missing:
                errors.append(
                    f"guard 3: clean file {f.name} is missing the remote_store or paired raw-SDK "
                    f"overhead data for {missing} (overhead/throughput/s3-comparison charts would "
                    "blank or omit that backend)"
                )
        else:
            # Guard 2: each rtt file must carry both the -latency remote_store
            # variant AND its paired raw-SDK target — the overhead-vs-rtt chart
            # divides one by the other, so a missing raw side drops the series
            # just as silently as a missing remote_store side.
            missing = _missing_ratio_sides(_backend_targets(benches), sorted(_REQUIRED_LATENCY))
            if missing:
                errors.append(
                    f"guard 2: latency file {f.name} ({profile}) is missing the remote_store or "
                    f"paired raw-SDK target for {missing} (overhead-vs-rtt series would drop silently)"
                )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Slim + guard the benchmark run of record")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Raw pytest-benchmark JSON dumps to slim (omit with --check-only)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory for the slimmed set (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only re-guard the committed --out set; do not slim any inputs",
    )
    args = parser.parse_args()

    if not args.check_only:
        if not args.inputs:
            print("No input files given (use --check-only to guard the committed set).", file=sys.stderr)
            sys.exit(2)
        for src in args.inputs:
            if not src.exists():
                print(f"Input not found: {src}", file=sys.stderr)
                sys.exit(2)
            dest = slim_file(src, args.out)
            print(f"Slimmed {src} -> {dest}")

    errors = guard(args.out)
    if errors:
        print("\nRun-of-record guard FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    print(f"\nRun-of-record guard passed for {args.out} (all three chart invariants hold).")


if __name__ == "__main__":
    main()
