#!/usr/bin/env python3
"""Record and verify HTTP cassettes for a given backend.

Usage::

    hatch run record-azure
    python scripts/record_cassettes.py --backend azure
    python scripts/record_cassettes.py --backend azure --verify-only
    python scripts/record_cassettes.py --backend azure --node "<nodeid>[azure_live]"

Steps (all backends):
    1. Delete existing cassettes for the backend.
    2. Record sync fixtures against the live service.
    3. Record async fixtures against the live service.
    4. Verify no real account name survived scrubbing.
    5. Replay smoke test (Stage 1) — confirms cassettes are replay-compatible.

Pass ``--verify-only`` to skip steps 1-3 and re-run only 4-5 (useful after
a partial failure or when checking an existing cassette set).

Pass ``--node SELECTOR`` to record a *single* cassette without the
all-or-nothing tree-wipe: steps 1-3 are replaced by one targeted
``pytest --stage=3 --record`` run for the given node (no Step-1 delete, no
min-cassette guard), then the whole-dir scrub-verify + replay (steps 4-5)
run unchanged. ``SELECTOR`` is a pytest node id (or path) and must name the
*live* variant of the test, e.g. ``...::test_y[azure_live]`` or
``...::test_y[azure_live_async]``. Use this to add or refresh one cassette
without churning every other file's volatile headers.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

_CONFORMANCE = "tests/backends/conformance/"

# Add the repo root to sys.path so test helpers are importable without install.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Per-backend account-name resolvers
# ---------------------------------------------------------------------------


def _resolve_azure_account() -> str:
    """Return the real storage account name from AZURE_STORAGE_CONNECTION_STRING.

    Loads ``.env`` via python-dotenv (no-op if not installed or file absent).
    Exits with a clear message if the env var is missing, malformed, or points
    at the Azurite emulator (which would produce a false-clean scrub result).
    """
    from tests.backends.fixtures._cassettes import _AZURITE_FRAGMENTS, parse_account_name  # noqa: PLC0415

    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv(override=False)
    except ImportError:
        pass
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not conn:
        _die(
            "AZURE_STORAGE_CONNECTION_STRING is missing.\n"
            "  See docs-src/guides/backends/azure-hns-setup.md for setup instructions."
        )
    if any(frag in conn for frag in _AZURITE_FRAGMENTS):
        _die(
            "AZURE_STORAGE_CONNECTION_STRING points at Azurite; "
            "scrub verification requires a real ADLS Gen2 account name.\n"
            "  See docs-src/guides/backends/azure-hns-setup.md for setup instructions."
        )
    try:
        account = parse_account_name(conn)
    except ValueError as exc:
        _die(str(exc))
    if not account:
        _die(
            "AZURE_STORAGE_CONNECTION_STRING has an empty AccountName= value.\n"
            "  See docs-src/guides/backends/azure-hns-setup.md for setup instructions."
        )
    return account


# ---------------------------------------------------------------------------
# Backend config table
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, dict] = {
    "azure": {
        "cassette_dir": Path("tests/backends/cassettes/azure"),
        "sync_k": "azure_live and not async",
        "async_k": "azure_live_async",
        "replay_k": "azure_replay",
        "account_fn": _resolve_azure_account,
        # Live opt-in flag — checked at preflight so the absence does not
        # wipe cassettes before the pytest fixture would fail (BUG-212).
        "live_opt_in_env": "RS_TEST_LIVE_HNS",
        # Lower-bound guard: recording fewer cassettes than this means pytest
        # silently selected zero tests (k-filter mismatch, stage gate, etc.).
        "min_cassettes": 200,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _die(msg: str) -> NoReturn:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _run(*args: str) -> None:
    result = subprocess.run(args)  # noqa: S603
    if result.returncode != 0:
        _die(f"step failed (exit {result.returncode}): {' '.join(args)}")


def _section(title: str) -> None:
    bar = "-" * 60
    print(f"\n{bar}\n  {title}\n{bar}")


def _preflight_env(cfg: dict, *, verify_only: bool) -> None:
    """Validate env vars BEFORE Step 1 deletes existing cassettes (BUG-212).

    Recording deletes the cassette tree at Step 1, then validates env
    inside pytest at Step 2/3 and inside ``account_fn`` at Step 4. A
    missing opt-in flag or a missing / Azurite connection string would
    otherwise wipe the cassette tree before any error surfaces. Run all
    env validation upfront so a misconfigured invocation leaves the tree
    intact.

    When ``verify_only`` is true the preflight is a no-op: no Step 1
    delete to protect, and Step 4 calls ``account_fn`` directly with its
    own error path. Requiring the live opt-in flag here would block the
    documented "skip recording; run only scrub-verify + replay" workflow.
    """
    if verify_only:
        return

    try:
        from dotenv import load_dotenv  # noqa: PLC0415 -- optional dep, lazy
    except ImportError:
        pass
    else:
        load_dotenv(override=False)

    opt_in = cfg["live_opt_in_env"]
    if os.environ.get(opt_in) != "1":
        _die(
            f"{opt_in}=1 is required for recording (targets a real account).\n"
            f"  See docs-src/guides/backends/azure-hns-setup.md for setup instructions."
        )
    cfg["account_fn"]()  # validates cred string; calls _die on failure


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-only",
        action="store_true",
        help="skip recording; run only scrub-verify + replay smoke test (steps 4-5)",
    )
    mode.add_argument(
        "--node",
        metavar="NODEID",
        help=(
            "record a single cassette: pytest node selector for the live test variant "
            "(e.g. path::Class::test[azure_live]); skips the tree-wipe (Step 1) and the "
            "min-cassette guard, then runs scrub-verify + replay (steps 4-5)"
        ),
    )
    opts = parser.parse_args()

    cfg = _BACKENDS[opts.backend]
    cassette_dir: Path = cfg["cassette_dir"]
    single = opts.node is not None

    # Single mode records against live too, so it runs the recording preflight
    # (opt-in flag + cred validation). It performs no Step-1 delete, so the
    # BUG-212 wipe-before-validate hazard does not apply, but failing fast on
    # missing credentials is still correct.
    _preflight_env(cfg, verify_only=opts.verify_only)

    if single:
        _section("Step 1-3 — record single cassette (no tree-wipe)")
        before = {f.name: f.stat().st_mtime for f in cassette_dir.glob("*.yaml")}
        # The node selector replaces both the -k filter and the conformance-dir
        # positional. -m live overrides the default addopts "-m 'not live'".
        _run(
            sys.executable,
            "-m",
            "pytest",
            "--stage=3",
            "--record",
            "-m",
            "live",
            opts.node,
            "--tb=short",
            "-q",
        )
        new = sorted(f.name for f in cassette_dir.glob("*.yaml") if f.name not in before)
        modified = sorted(
            f.name for f in cassette_dir.glob("*.yaml") if f.name in before and f.stat().st_mtime > before[f.name]
        )
        if new:
            print(f"  New cassette(s): {', '.join(new)}")
        if modified:
            print(f"  Refreshed in place: {', '.join(modified)}")
        if not new and not modified:
            print("  No cassette file changed — check the node selector named a recordable live test.")
    elif not opts.verify_only:
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

    if not opts.verify_only and not single:
        min_expected = cfg.get("min_cassettes", 0)
        recorded = len(list(cassette_dir.glob("*.yaml")))
        if recorded < min_expected:
            _die(
                f"only {recorded} cassette(s) recorded (expected >= {min_expected}); "
                "pytest likely selected zero tests — check the k-filter and --stage value"
            )
        print(f"  Cassette count OK: {recorded} >= {min_expected}")

    _section("Step 4 — verify scrub (no real credentials in cassettes)")
    account: str = cfg["account_fn"]()
    account_bytes = account.encode()
    files = list(cassette_dir.glob("*.yaml"))
    bad = [f.name for f in files if account_bytes in f.read_bytes()]
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
