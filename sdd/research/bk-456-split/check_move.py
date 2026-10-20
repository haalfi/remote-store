#!/usr/bin/env python3
"""Prove BK-456 stage two moved spec 003's sections whole (a pure move).

Usage: ``python sdd/research/bk-456-split/check_move.py [BASE]``. BASE defaults
to ``4694e7a``, the master commit the split was cut from (stage one's merge); a
later master no longer holds the moved sections, so it is no base for this
check. Exit 0 when every check passes, 1 otherwise.

Checks, against spec 003 at BASE:

1. The section ID set before equals the union after, and no ID is declared twice.
2. Each section (``### CAP-/BE-NNN`` heading to the next ``##``/``###``, trailing
   blank and ``---`` lines dropped), and the ``## Contract kernel`` intro, is
   byte-identical to its text at BASE once two edit classes are reversed:
   - a link target into one of the three files, ``](NNN-name.md#a)`` or
     ``](#a)``, is folded to ``](#a)`` on both sides;
   - the ``RETARGETS`` below, each a "this spec" turned into a link to the spec
     it meant at BASE (the kernel intro's also drops "other", since none of
     003's clauses is a kernel clause after the split), each required to occur
     exactly once.
3. Every link into the three files, from any tracked ``.md`` or ``.py`` outside
   ``sdd/decisions``, ``sdd/traces`` and ``sdd/research``, names an anchor that
   file has, so the fold in 2 cannot hide a link sent to the wrong file.
4. No unanchored link to spec 003, in the same files, names a section that left
   it: neither its text (``[BE-033](...003...md)``) nor a parenthesised ID right
   after it, a line break allowed (``[003-...md](003-...md)\n(BE-028)``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "sdd" / "specs"
F003 = "003-backend-adapter-contract.md"
NEW = ("052-backend-lifetime.md", "053-contract-kernel.md")
FILES = (F003, *NEW)
KERNEL_INTRO = "contract-kernel"
BASE = "4694e7a"
RETARGETS = [
    (
        "the other formal-coverage notes in this spec quote",
        "the other formal-coverage notes in [spec 003](003-backend-adapter-contract.md) quote",
    ),
    (
        "The other clauses of this spec\nstate each call",
        "The other clauses of [spec 003](003-backend-adapter-contract.md) and\n"
        "[spec 053](053-contract-kernel.md) state each call",
    ),
    (
        "the other clauses of this spec leave",
        "the clauses of [spec 003](003-backend-adapter-contract.md) leave",
    ),
]
_HEAD = re.compile(r"#{2,3} ")
_SECTION = re.compile(r"### ((?:CAP|BE)-\d+):")
_FOLD = re.compile(r"\]\((?:(?:003-backend-adapter-contract|052-backend-lifetime|053-contract-kernel)\.md)?#")
_BARE = re.compile(r"\]\(#([^)\s]+)\)")
_UNANCHORED = re.compile(r"\[([^\]]*)\]\([^)\s#]*003-backend-adapter-contract\.md\)(?:\s*\((BE-\d+)\))?")
_LINK = re.compile(
    r"\]\(([^)\s]*?)((?:003-backend-adapter-contract|052-backend-lifetime|053-contract-kernel)\.md)#([^)\s]+)\)"
)


def slug(heading: str) -> str:
    text = re.sub(r"[^\w\- ]", "", heading.lstrip("#").strip().lower())
    return text.replace(" ", "-")


def sections(text: str) -> dict[str, str]:
    """Map each section ID (and the kernel intro) to its text."""
    lines = text.split("\n")
    heads = [i for i, line in enumerate(lines) if _HEAD.match(line)] + [len(lines)]
    out: dict[str, str] = {}
    for a, b in zip(heads, heads[1:]):
        m = _SECTION.match(lines[a])
        key = m.group(1) if m else (KERNEL_INTRO if lines[a] == "## Contract kernel" else None)
        if key is None:
            continue
        block = lines[a:b]
        while block and block[-1].strip() in ("", "---"):
            block.pop()
        if key in out:
            raise SystemExit(f"FAIL: {key} declared twice")
        out[key] = "\n".join(block)
    return out


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else BASE
    before = sections(
        subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{base}:sdd/specs/{F003}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    )
    texts = {f: (SPECS / f).read_text(encoding="utf-8") for f in FILES}
    after: dict[str, tuple[str, str]] = {}
    for f, text in texts.items():
        for key, body in sections(text).items():
            if key in after:
                print(f"FAIL: {key} in both {after[key][0]} and {f}")
                return 1
            after[key] = (f, body)

    failures = 0
    if set(before) != set(after):
        print(
            f"FAIL: ID sets differ; only before {sorted(set(before) - set(after))}, "
            f"only after {sorted(set(after) - set(before))}"
        )
        failures += 1
    ids = sorted(k for k in before if k != KERNEL_INTRO)
    print(
        f"IDs: {len(ids)} before, {len([k for k in after if k != KERNEL_INTRO])} after, sets equal: {set(before) == set(after)}"
    )

    used = {old: 0 for old, _ in RETARGETS}
    folded = identical = 0
    placed = {f: 0 for f in FILES}
    for key in sorted(before):
        if key not in after:
            continue
        f, body = after[key]
        placed[f] += 1
        for old, new in RETARGETS:
            if new in body:
                used[old] += body.count(new)
                body = body.replace(new, old)
        folded += len(_FOLD.findall(body)) - len(re.findall(r"\]\(#", body))
        if _FOLD.sub("](#", body) == _FOLD.sub("](#", before[key]):
            identical += 1
        else:
            print(f"FAIL: {key} ({f}) differs from {base}")
            failures += 1
    for old, n in used.items():
        if n != 1:
            print(f"FAIL: retarget {old!r} applied {n} times, expected 1")
            failures += 1
    print(
        f"sections byte-identical after the fold: {identical} of {len(before)} "
        f"(placed: {', '.join(f'{f} {n}' for f, n in placed.items())}); "
        f"link targets folded: {folded}; 'this spec' retargets: {sum(used.values())}"
    )

    # Every link into the three files resolves, cross-file or in-file, so the fold
    # cannot hide a link sent to the wrong file or left bare in the wrong one.
    anchors = {f: {slug(line) for line in t.split("\n") if _HEAD.match(line)} for f, t in texts.items()}
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", "*.md", "*.py", ":!sdd/decisions", ":!sdd/traces", ":!sdd/research"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    moved = {key for key, (f, _) in after.items() if f != F003}
    links = unresolved = stale = 0
    for path in sorted(set(tracked) | {f"sdd/specs/{f}" for f in FILES}):
        p = ROOT / path
        if not p.exists():
            continue
        whole = p.read_text(encoding="utf-8")
        for m in _UNANCHORED.finditer(whole):
            named = {i for i in re.findall(r"BE-\d+", m.group(1)) + [m.group(2) or ""] if i in moved}
            if named:
                n = whole.count("\n", 0, m.start()) + 1
                print(f"FAIL: {path}:{n} links spec 003 for {', '.join(sorted(named))}, which left it")
                stale += 1
        for n, line in enumerate(whole.split("\n"), 1):
            found = [(t, a) for _, t, a in _LINK.findall(line)]
            if p.parent == SPECS and p.name in FILES:
                found += [(p.name, a) for a in _BARE.findall(line)]
            for target, anchor in found:
                links += 1
                if anchor not in anchors[target]:
                    print(f"FAIL: {path}:{n} links {target}#{anchor}, which has no such heading")
                    unresolved += 1
    failures += unresolved + stale
    print(f"links into the three files: {links}, unresolved: {unresolved}; "
          f"unanchored links to 003 naming a moved ID: {stale}")
    print("RESULT:", "FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
