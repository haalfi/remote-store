"""Run the latency benchmark matrix across all network profiles.

Usage::

    hatch run bench-latency-matrix                    # rtt20, rtt50, rtt100
    hatch run bench-latency-matrix -- --profiles rtt50 rtt100

Requires Docker containers running::

    docker compose -f infra/docker-compose.yml up -d --wait
"""

from __future__ import annotations

import argparse
import subprocess
import sys

DEFAULT_PROFILES = ["rtt20", "rtt50", "rtt100"]
BACKENDS = "s3-latency,sftp-latency,azure-latency"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run latency benchmark matrix")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=DEFAULT_PROFILES,
        help=f"Network profiles to run (default: {' '.join(DEFAULT_PROFILES)})",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=20,
        help="Pool size for pedantic benchmarks (default: 20)",
    )
    parser.add_argument(
        "--bench-timeout",
        type=int,
        default=120,
        help="Benchmark timeout in seconds (default: 120)",
    )
    args = parser.parse_args()

    failed: list[str] = []

    for profile in args.profiles:
        print(f"\n=== Running profile: {profile} ===\n", flush=True)
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "benchmarks/",
            "-v",
            "--backend",
            BACKENDS,
            "--network-profile",
            profile,
            f"--pool-size={args.pool_size}",
            f"--bench-timeout={args.bench_timeout}",
            "-m",
            "not standard and not full",
            "--benchmark-autosave",
            "--benchmark-sort=mean",
            "-q",
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            failed.append(profile)
            print(f"=== FAILED: {profile} ===\n", flush=True)
        else:
            print(f"=== Done: {profile} ===\n", flush=True)

    print(f"Completed {len(args.profiles)} profiles.", flush=True)
    if failed:
        print(f"Failed: {', '.join(failed)}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
