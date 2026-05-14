#!/usr/bin/env python3
"""Record and verify HTTP cassettes for a given backend.

Usage::

    hatch run record-azure
    python scripts/record_cassettes.py --backend azure
    python scripts/record_cassettes.py --backend azure --verify-only

Steps (all backends):
    1. Delete existing cassettes for the backend.
    2. Record sync fixtures against the live service.
    3. Record async fixtures against the live service.
    4. Verify no real account name survived scrubbing.
    5. Replay smoke test (Stage 1) — confirms cassettes are replay-compatible.

Pass ``--verify-only`` to skip steps 1-3 and re-run only 4-5 (useful after
a partial failure or when checking an existing cassette set).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_CONFORMANCE = "tests/backends/conformance/"


# ---------------------------------------------------------------------------
# Per-backend account-name resolvers
# ---------------------------------------------------------------------------


def _resolve_azure_account() -> str:
    """Return the real storage account name from AZURE_STORAGE_CONNECTION_STRING.

    Loads ``.env`` via python-dotenv (no-op if not installed or file absent).
    Exits with a clear message if the env var is missing or malformed.
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv(override=False)
    except ImportError:
        pass
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    for part in conn.split(";"):
        if part.strip().lower().startswith("accountname="):
            account = part.split("=", 1)[1].strip()
            if account:
                return account
    _die(
        "AZURE_STORAGE_CONNECTION_STRING is missing or has no AccountName.\n"
        "  See docs-src/guides/backends/azure-hns-setup.md for setup instructions."
    )


# ---------------------------------------------------------------------------
# Backend config table
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, dict] = {
    "azure": {
        "cassette_dir": Path("tests/backends/cassettes/azure"),
        "sync_k": "azure_live and not async",
        "async_k": "azure_live_async",
        "replay_k": "azure_replay or azure_replay_async",
        "account_fn": _resolve_azure_account,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _die(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _run(*args: str) -> None:
    result = subprocess.run(args)  # noqa: S603
    if result.returncode != 0:
        _die(f"step failed (exit {result.returncode}): {' '.join(args)}")


def _section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        required=True,
        choices=list(_BACKENDS),
        metavar="BACKEND",
        help=f"backend to record: {', '.join(_BACKENDS)}",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="skip recording; run only scrub-verify + replay smoke test (steps 4-5)",
    )
    opts = parser.parse_args()

    cfg = _BACKENDS[opts.backend]
    cassette_dir: Path = cfg["cassette_dir"]

    if not opts.verify_only:
        _section("Step 1 — delete existing cassettes")
        deleted = 0
        for f in cassette_dir.glob("*.yaml"):
            f.unlink()
            deleted += 1
        print(f"  Deleted {deleted} file(s) from {cassette_dir}/")

        _section("Step 2 — record sync fixtures")
        _run(
            sys.executable,
            "-m",
            "pytest",
            "--stage=3",
            "--record",
            "-m",
            "live",
            "-k",
            cfg["sync_k"],
            _CONFORMANCE,
            "--tb=short",
            "-q",
        )

        _section("Step 3 — record async fixtures")
        _run(
            sys.executable,
            "-m",
            "pytest",
            "--stage=3",
            "--record",
            "-m",
            "live",
            "-k",
            cfg["async_k"],
            _CONFORMANCE,
            "--tb=short",
            "-q",
        )

    _section("Step 4 — verify scrub (no real credentials in cassettes)")
    account: str = cfg["account_fn"]()
    files = list(cassette_dir.glob("*.yaml"))
    bad = [f.name for f in files if account in f.read_text()]
    if bad:
        print("  LEAK detected in:")
        for name in bad:
            print(f"    {name}")
        _die("real account name survived scrubbing — do NOT commit these cassettes")
    print(f"  Clean: {len(files)} cassette(s) checked, account name absent.")

    _section("Step 5 — replay smoke test (Stage 1)")
    _run(
        sys.executable,
        "-m",
        "pytest",
        _CONFORMANCE,
        "-k",
        cfg["replay_k"],
        "--stage=1",
        "--tb=short",
        "-q",
    )

    print("\nAll steps passed.\n")


if __name__ == "__main__":
    main()
