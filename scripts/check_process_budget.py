#!/usr/bin/env python3
"""BK-422: the process files agents re-read may not grow without a recorded raise.

Every byte of ``CLAUDE.md``, a skill or an agent definition is re-read on every
later call of the session that loads it, and again in every subagent; the
measurement is ``sdd/research/token-usage/report.md``. Nothing priced their
growth, so this gate is a ratchet on their **total**, held in
``sdd/process-budget.json``:

* **Growth fails.** The current total may not exceed the recorded ``total``.
  Growth that is wanted is a *raise*: ``--raise --item <ID> --reason <text>``
  records it in the file's ``raises`` register (DRIFT-RULES Rule 6), so it is
  argued in the diff instead of accumulating unseen.
* **An unrecorded shrink fails too.** Below ``total × (1 − slack)`` the check
  asks for ``--update``, which locks the lower total in. Without that, a cut
  would leave credit that later growth spends silently.

Sizes are bytes with ``\\r\\n`` counted as ``\\n``, so a Windows checkout
measures the same as CI.

Bounds (DRIFT-RULES Rule 7)
---------------------------
* **Bytes, not tokens, and not reads.** A file every reviewer loads counts the
  same as one read once a month; the budget prices size only.
* **The total, not each file.** One file may grow while another shrinks by as
  much. That is the intent: growth costs a removal somewhere in the set.
* **Only what ``globs`` match.** The system prompt, tool schemas, the user's
  global instructions and memory sit outside the repo and outside this gate.
* **Per branch.** Two PRs that each fit the recorded total can exceed it once
  both merge; the next run on the merged tree reports it.

Run with::

    hatch run check-process-budget
    hatch run preflight      # bundled
    hatch run docs-gate      # bundled; ci.yml routes .claude/ and CLAUDE.md
                             # diffs to the docs job, not the CODE_PAT lint job
    python scripts/check_process_budget.py --update
    python scripts/check_process_budget.py --raise --item BK-422 --reason "..."

Exit codes: ``0`` within budget (or the file was rewritten), ``1`` over or under
it, each budgeted file's change since the last lock-in printed (Rule 2), or a
glob matching no file; ``2`` a refused or malformed update.

Drift-gate::

    kind:       rule
    rule: the total size of the process files agents re-read (CLAUDE.md, skills, agent
        definitions, CLAUDE-REFERENCE.md, the trace schema) neither exceeds nor falls unrecorded
        below the total sdd/process-budget.json records, and every raise carries an item and a reason
    domain:     process
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = Path("sdd/process-budget.json")

_ITEM_RX = re.compile(r"^(BL|BK|BUG|ID)-\d+$")


def measure(root: Path, globs: list[str]) -> dict[str, int]:
    """Size of every file the globs match, keyed by repo-relative POSIX path."""
    sizes: dict[str, int] = {}
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                sizes[rel] = len(path.read_bytes().replace(b"\r\n", b"\n"))
    return sizes


def load(root: Path) -> dict:
    return json.loads((root / BUDGET).read_text(encoding="utf-8"))


def save(root: Path, budget: dict) -> None:
    (root / BUDGET).write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")


def deltas(recorded: dict[str, int], current: dict[str, int]) -> list[str]:
    """One line per file whose size moved since the last lock-in, largest first."""
    rows = []
    for path in sorted(recorded.keys() | current.keys()):
        old, new = recorded.get(path), current.get(path)
        if old == new:
            continue
        diff = (new or 0) - (old or 0)
        state = "new" if old is None else "removed" if new is None else f"{old} -> {new}"
        rows.append((abs(diff), f"  {diff:+7d}  {path} ({state})"))
    return [text for _, text in sorted(rows, key=lambda r: -r[0])]


def lock(budget: dict, current: dict[str, int]) -> dict:
    budget["total"] = sum(current.values())
    budget["files"] = current
    return budget


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--update", action="store_true", help="lock in a lower total after a cut")
    parser.add_argument("--raise", dest="raise_", action="store_true", help="record a wanted growth")
    parser.add_argument("--item", help="backlog ID owning the raise")
    parser.add_argument("--reason", help="why the growth is worth its cost")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root or root

    budget = load(root)
    dead = [g for g in budget["globs"] if not any(p.is_file() for p in root.glob(g))]
    if dead:
        # A renamed file would otherwise leave the budget silently (Rule 3).
        print(f"Budget glob(s) match no file: {', '.join(dead)}", file=sys.stderr)
        return 1
    current = measure(root, budget["globs"])
    total, recorded = budget["total"], budget["files"]
    now = sum(current.values())
    floor = int(total * (1 - budget["slack"]))

    if args.update:
        if now > total:
            print(f"Refused: {now} bytes exceeds the recorded {total}; growth is a --raise.", file=sys.stderr)
            return 2
        save(root, lock(budget, current))
        print(f"Locked in {now} bytes (was {total}).")
        return 0

    if args.raise_:
        if not (args.item and _ITEM_RX.match(args.item) and args.reason and args.reason.strip()):
            print("Refused: --raise needs --item <PREFIX-NNN> and a non-empty --reason.", file=sys.stderr)
            return 2
        if now <= total:
            print(f"Refused: {now} bytes fits the recorded {total}; nothing to raise.", file=sys.stderr)
            return 2
        budget.setdefault("raises", []).append(
            {"item": args.item, "from": total, "to": now, "reason": args.reason.strip()}
        )
        save(root, lock(budget, current))
        print(f"Raised {total} -> {now} bytes under {args.item}.")
        return 0

    if floor <= now <= total:
        print(f"Process files within budget: {now} of {total} bytes ({len(current)} files).")
        return 0

    over = now > total
    if over:
        head = f"Process files grew: {now} bytes against a recorded {total} (+{now - total})."
        fix = "Cut as much elsewhere in the set, or record the growth with --raise --item <ID> --reason <text>."
    else:
        head = f"Process files shrank below the slack: {now} bytes against a recorded {total}."
        fix = "Lock the cut in with --update, so later growth cannot spend it unseen."
    print(head, file=sys.stderr)
    for row in deltas(recorded, current):
        print(row, file=sys.stderr)
    print(f"\n{fix}\n(scripts/check_process_budget.py; budget in {BUDGET.as_posix()})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
