#!/usr/bin/env python
"""Generate a setup-inclusive pytest-split durations file (BK-319).

``pytest-split --store-durations`` records only each test's *call*-phase time.
For remote-store that mis-balances CI shards badly: the live-backend and
azure_replay (VCR cassette) fixtures do most of their work in *setup*, so the
setup-heavy tests carry a tiny recorded weight and pytest-split piles them all
into one shard (observed: a 2-way split where one shard ran ~1.8x longer).

This generator records ``setup + call + teardown`` wall time per test — the real
per-test cost that shard balancing must equalise — and writes it in the
pytest-split durations format (``{nodeid: seconds}``). Under xdist the controller
process receives every worker's phase reports, so only the controller writes.

Usage::

    python scripts/gen_split_durations.py <output-path> -- <pytest args...>
"""

from __future__ import annotations

import json
import sys

import pytest


class _TotalDurations:
    """Pytest plugin summing setup+call+teardown wall time per test node."""

    def __init__(self, out_path: str) -> None:
        self._out_path = out_path
        self._durations: dict[str, float] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # Fires for each of setup/call/teardown; sum them for the full cost.
        self._durations[report.nodeid] = self._durations.get(report.nodeid, 0.0) + report.duration

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        # Only the xdist controller (no ``workerinput``) writes the merged file.
        if hasattr(session.config, "workerinput"):
            return
        with open(self._out_path, "w", encoding="utf-8") as fh:
            json.dump(self._durations, fh, indent=2, sort_keys=True)
            fh.write("\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = argv[1]
    pytest_args = argv[2:]
    # Tolerate a leading ``--`` separator between our args and pytest's.
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    return int(pytest.main(pytest_args, plugins=[_TotalDurations(out_path)]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
