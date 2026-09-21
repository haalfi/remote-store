#!/usr/bin/env python3
"""BK-378: the head's backlog ID set agrees with the base's (RFC-0015 D4).

Two things happened on PR #997 that no gate covered, in rounds 5 and 7: a rebase
dropped a live item out of ``sdd/BACKLOG.md``, and the PR body claimed to close
an item that belonged to another branch. Both are two artifacts disagreeing —
this branch's backlog files and ``origin/master``'s — which is
``sdd/DRIFT-RULES.md``'s subject, and that file says a report is not a
reduced-obligation category. So this ships as a gate.

What it compares
----------------
The ``PREFIX-NNN`` **item headers** in ``sdd/BACKLOG.md`` and
``sdd/BACKLOG-DONE.md``, as they stand in the working tree, against the same two
files at ``origin/master`` (read with ``git show``, so no checkout and no second
worktree). Two failures:

1. **Dropped.** An ID ``origin/master`` has *open* that the head has nowhere —
   neither open nor done. A rebase that resolves a conflict by taking one side
   wholesale does this, and nothing else in the repo notices: ``gen_backlogid.py``
   compares open IDs against *done* ones, so an item that simply vanishes passes
   it.
2. **Poached.** An ID the head marks *done* that ``origin/master`` still has
   open, and that **this branch's commits never name**. Closing an item you did
   the work for is the normal case and must not fail; the branch's own commit
   subjects are what separates the two, since
   [`CLAUDE.md` § Backlog](../CLAUDE.md#backlog) makes the leading
   ``PREFIX-NNN`` token of a commit subject the item it belongs to. That is the
   same extraction ``/pr``'s trace gate runs, spelled the same way.

Authority (Rule 4)
------------------
``origin/master`` governs *existence*: an ID it has open is live until a commit
on this branch says otherwise. The head governs *state*, but only for the IDs
its commits name. Neither side governs unconditionally, which is why the two
failures above are asymmetric rather than one set difference reported twice.

Reuse
-----
``gen_backlogid.py``'s ``_HEADER_RE`` and ``_extract_ids`` parse the headers.
A second spelling of that grammar is exactly the drift this repo keeps finding —
``check_changelog_unreleased.py``'s docstring records its own ``_ENTRY_RE``
being deliberately held to its counterpart's — so this imports rather than
re-writes, the way ``gen_python_support.py`` imports ``python_support``.

Bounds (DRIFT-RULES Rule 7)
---------------------------
* **It compares headers, not bodies.** An item whose header survives while its
  body is gutted by a bad merge passes.
* **It is only as current as ``origin/master``.** A stale ref compares against
  the wrong base, which is why its home is the PR validation gates, *after* the
  branch-freshness check has fetched. Run standalone without fetching and it
  will happily report nothing. A base that resolves but carries *neither*
  backlog file is the same failure one step further along, and is refused
  rather than reported as agreement — measured: before that guard,
  ``--base <a ref without sdd/>`` printed "Backlog ID sets agree" and exited 0.
* **Failure 2 keys on commit subjects**, so an item legitimately closed by a
  commit whose subject does not name it reads as poached. ``subject_ids``
  reads every ID in the run before the colon, which is this repo's co-shipped
  spelling; what it cannot read is an ID no subject spells, including the tail
  of a ``BUG-283..286`` range.
* **It does not look at other open branches.** "Another branch's account" is
  inferred from ``origin/master`` plus this branch's commits, never by
  enumerating remote branches — that would need a network walk on a gate that is
  otherwise offline. An item opened *and* closed entirely on a third branch,
  never reaching master, is invisible here.
* **A head-open ID that master has done is not reported.** Re-opening a
  completed item is a real edit with a real author; nothing observed has needed
  it flagged, and ``gen_backlogid.py --check`` already fails on that exact
  collision.

Run with::

    hatch run check-backlog-ids-vs-base
    python scripts/check_backlog_ids_vs_base.py [--base origin/master]

Exit codes: ``0`` clean, ``1`` one or more disagreements, each naming the ID and
the side (DRIFT-RULES Rule 2).

Drift-gate::

    kind:       pair
    compares: the PREFIX-NNN item headers in sdd/BACKLOG.md and sdd/BACKLOG-DONE.md at the working
        tree ↔ the same headers at origin/master, arbitrated by the item IDs this branch's commit
        subjects name
    domain:     process
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_backlogid import _PREFIXES, _extract_ids  # noqa: E402  — sibling module, as gen_python_support does

DEFAULT_BASE = "origin/master"
BACKLOG_FILES = ("sdd/BACKLOG.md", "sdd/BACKLOG-DONE.md")

# One `PREFIX-NNN` token, with the trailing letter `_schema.yml` allows for
# split items (BK-167a). The number is spelled `(\d+[a-z]*)` to match
# `gen_backlogid._HEADER_RE` exactly: the arbitration below is set membership,
# so a header yielding `BK-167ab` against a commit yielding `BK-167a` would read
# as POACHED. One token, one grammar.
_ID_TOKEN = re.compile(r"\b(" + "|".join(_PREFIXES) + r")-(\d+[a-z]*)\b")


def subject_ids(subject: str) -> set[str]:
    """Every item ID a commit subject claims.

    **A subject may claim several**, and this repo's convention spells that as a
    comma-separated run before the colon: ``BK-375, BK-373, BK-377: derive the
    published support windows``. Four of the forty commits before this one used
    that shape, so reading only the leading token made every co-shipped branch
    report its legitimate closures as POACHED.

    Two rules keep it from over-claiming:

    * the subject must **start** with an ID token, so ``Merge branch 'master'
      into bk-378`` and ``Fix the thing (BK-378)`` claim nothing; and
    * only the text **before the first colon** is read, so
      ``BK-001: fix the BK-002 regression`` claims `BK-001` alone.

    Bound: a range shorthand claims only the IDs it spells in full.
    ``BUG-283..286: …`` claims `BUG-283`, because `284` to `286` carry no
    prefix and inventing them would make the gate trust a number nobody wrote.
    """
    stripped = subject.strip()
    if not _ID_TOKEN.match(stripped):
        return set()
    head = stripped.partition(":")[0]
    return {f"{m.group(1)}-{m.group(2)}" for m in _ID_TOKEN.finditer(head)}


class Disagreement:
    """One ID the two sides disagree about, with the side that is wrong."""

    __slots__ = ("item_id", "kind", "detail")

    def __init__(self, item_id: str, kind: str, detail: str) -> None:
        self.item_id, self.kind, self.detail = item_id, kind, detail

    def format(self) -> str:
        return f"{self.kind}: {self.item_id} — {self.detail}"


def _git(*args: str, root: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True)


def read_base(path: str, base: str = DEFAULT_BASE, root: Path = ROOT) -> str:
    """The file's content at ``base``; empty string when it does not exist there."""
    done = _git("show", f"{base}:{path}", root=root, check=False)
    return done.stdout if done.returncode == 0 else ""


def branch_commit_ids(base: str = DEFAULT_BASE, root: Path = ROOT) -> set[str]:
    """Every item ID this branch's commit subjects claim (see ``subject_ids``)."""
    subjects = _git("log", "--format=%s", f"{base}..HEAD", root=root).stdout.splitlines()
    found: set[str] = set()
    for subject in subjects:
        found |= subject_ids(subject)
    return found


def _flatten(by_prefix: dict[str, set[str]]) -> set[str]:
    return {item for ids in by_prefix.values() for item in ids}


def _ids(text_open: str, text_done: str) -> tuple[set[str], set[str]]:
    """(open, done) ID sets for one side, using gen_backlogid's header grammar."""
    return (
        _flatten(_extract_ids(text_open, " ~")),
        _flatten(_extract_ids(text_done, "x")),
    )


def compare(
    head_backlog: str,
    head_done: str,
    base_backlog: str,
    base_done: str,
    commit_ids: set[str],
    base: str = DEFAULT_BASE,
) -> list[Disagreement]:
    """Every way the head's ID set disagrees with the base's. Pure; the I/O is in main().

    ``base`` is named in the messages rather than assumed: reporting a side the
    run never read is the failure `DRIFT-RULES.md` Rule 2 is about, and under
    ``--base`` the reads and the prose would otherwise disagree.
    """
    head_open, head_closed = _ids(head_backlog, head_done)
    base_open, _base_closed = _ids(base_backlog, base_done)

    out: list[Disagreement] = []

    dropped = base_open - head_open - head_closed
    for item_id in sorted(dropped):
        out.append(
            Disagreement(
                item_id,
                "DROPPED",
                f"{base} has it open and the head has it nowhere. "
                "A rebase or merge resolution lost a live item; restore it to sdd/BACKLOG.md.",
            )
        )

    poached = (head_closed & base_open) - commit_ids
    for item_id in sorted(poached):
        out.append(
            Disagreement(
                item_id,
                "POACHED",
                f"the head closes it while {base} has it open, and no commit on this "
                "branch names it. Close only what this branch did; if it did do the work, the "
                "commit subject has to say so.",
            )
        )

    return out


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"base ref to compare against (default: {DEFAULT_BASE})")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root or root

    if _git("rev-parse", "--verify", "--quiet", args.base, root=root, check=False).returncode != 0:
        print(
            f"ERROR: {args.base} is not a ref here. Run `git fetch origin master` first — "
            "this gate's home is after the branch-freshness check for that reason.",
            file=sys.stderr,
        )
        return 1

    head_backlog, head_done = ((root / path).read_text(encoding="utf-8") for path in BACKLOG_FILES)
    base_backlog, base_done = (read_base(path, args.base, root=root) for path in BACKLOG_FILES)

    # A ref that resolves but carries neither backlog file makes `base_open`
    # empty, which makes both disagreement sets empty by construction — so the
    # gate would report agreement having compared nothing, in the same
    # reassuring words it uses for a real pass. That is a louder failure than
    # the staleness the Bounds list already states, so it is refused rather
    # than warned about.
    if not base_backlog and not base_done:
        print(
            f"ERROR: {args.base} carries neither {BACKLOG_FILES[0]} nor {BACKLOG_FILES[1]}, "
            "so there is nothing to compare against. Check the ref.",
            file=sys.stderr,
        )
        return 1

    problems = compare(
        head_backlog, head_done, base_backlog, base_done, branch_commit_ids(args.base, root=root), base=args.base
    )
    if not problems:
        print(f"Backlog ID sets agree with {args.base}.")
        return 0

    print(f"Found {len(problems)} backlog ID disagreement(s) with {args.base}:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem.format()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
