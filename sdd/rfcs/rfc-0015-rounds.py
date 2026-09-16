#!/usr/bin/env python3
"""Derivation for RFC-0015 Table 1: ``review_rounds`` before and after a commit.

Population: traces first added since ``<since>``, from
``git log --diff-filter=A --format= --name-only <since>..HEAD -- sdd/traces``
(underscore-prefixed files are schema, not traces). A trace added in that
range and renamed later in it (re-homing a backlog ID renames its trace) is
listed under its original name; renames in the same range are read from
``git log --diff-filter=R --name-status -M`` and followed to the current name.
A trace added *before* ``<since>`` and renamed after it is not "added since"
and stays in the "before" population. The "before" population is every other
``sdd/traces/[!_]*.yml``.

Value: the integer after ``^review_rounds:`` in each file; a trailing comment
is ignored. The field is not required by the schema, so a trace without it is
excluded and **named in the output**; ``n`` is the count of traces carrying it.

``--at <rev>`` reads the tree at that revision instead of the working tree
(``git ls-tree`` for the population, ``git show rev:path`` for each file), so
a figure can be pinned to a commit and re-derived there.

Prints sorted values with trace names, then median and mean, for both
populations.

Usage::

    python sdd/rfcs/rfc-0015-rounds.py 24d9464
    python sdd/rfcs/rfc-0015-rounds.py 24d9464 --at 2a1bbfe
"""

from __future__ import annotations

import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RX = re.compile(r"^review_rounds:\s*(\d+)", re.M)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def _is_trace(p: str) -> bool:
    return p.startswith("sdd/traces/") and p.endswith(".yml") and not Path(p).name.startswith("_")


def main(since: str, at: str | None) -> None:
    head = at or "HEAD"
    added_raw = {
        p
        for p in _git(
            "log", "--diff-filter=A", "--format=", "--name-only", f"{since}..{head}", "--", "sdd/traces"
        ).split()
        if _is_trace(p)
    }
    renames: dict[str, str] = {}
    for line in _git(
        "log", "--diff-filter=R", "--name-status", "--format=", "-M", f"{since}..{head}", "--", "sdd/traces"
    ).splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames[parts[1]] = parts[2]

    def current(p: str) -> str:
        while p in renames:
            p = renames[p]
        return p

    if at:
        everything = {p for p in _git("ls-tree", "-r", "--name-only", at, "sdd/traces").split() if _is_trace(p)}
        read = lambda p: _git("show", f"{at}:{p}")  # noqa: E731
    else:
        everything = {str(p.relative_to(ROOT)) for p in (ROOT / "sdd/traces").glob("[!_]*.yml")}
        read = lambda p: (ROOT / p).read_text()  # noqa: E731
    added = {current(p) for p in added_raw} & everything
    for label, paths in ((f"since {since} at {head}", added), (f"before {since} at {head}", everything - added)):
        vals = []
        missing = []
        for p in sorted(paths):
            m = RX.search(read(p))
            if m:
                vals.append((int(m.group(1)), Path(p).stem))
            else:
                missing.append(Path(p).stem)
        vals.sort()
        nums = [v for v, _ in vals]
        print(
            f"{label}: n={len(nums)} median={statistics.median(nums)} mean={statistics.mean(nums):.2f} "
            f"(traces without the field, excluded: {len(missing)}"
            + (": " + ", ".join(missing) if missing else "")
            + ")"
        )
        print("  " + ", ".join(f"{n}:{name}" for n, name in vals))


if __name__ == "__main__":
    args = sys.argv[1:]
    rev = args[args.index("--at") + 1] if "--at" in args else None
    main(args[0], rev)
