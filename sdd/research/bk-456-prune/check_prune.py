#!/usr/bin/env python3
"""Prove a BK-456 stage-three prune changed only what its ledger claims.

Usage: ``python sdd/research/bk-456-prune/check_prune.py LEDGER`` (a module beside
this script, e.g. ``ledger_052``). Exit 0 when every check passes, 1 otherwise.

Checks, against the ledger's ``SPEC`` at its ``BASE``:

1. **Cover.** Every ledger fragment occurs exactly once in the old spec, and
   together they cover it: nothing but Markdown punctuation is left over.
2. **Survive.** A ``keep`` fragment, and a ``reword`` fragment's ``new``, stand
   in the new spec under the section the ledger names (an ID's ``###`` section,
   or a ``##`` heading such as ``Notes``), or, for a ``reword`` whose
   destination is a path, in that file.
3. **Relocate.** A ``move`` fragment stands verbatim in its destination file,
   and a ``homed`` fragment's ``new`` stands there.
4. **IDs.** Every section ID of the old spec is still declared in it, and the
   new IDs are exactly the ledger's ``NEW_IDS``.
5. **Anchors.** Every link into the spec, from any tracked ``.md`` or ``.py``
   outside ``sdd/decisions``, ``sdd/traces`` and ``sdd/research``, names a
   heading it has.
6. **Gates.** ``scripts/check_spec_marks.py`` and ``scripts/check_formal_trace.py``
   exit 0.

Comparison folds whitespace, strips quote (``>``) and comment (``#``) markers,
and folds a link target to the spec (``](NNN-x.md#a)``, ``](../specs/NNN-x.md#a)``,
``](#a)``) to ``](#a)``. Bounds: check 2 proves a reworded clause's new text
exists where the ledger says, not that it means what the old text meant; that
is the review's.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_ID = re.compile(r"^#{2,3} ([A-Z]+-\d+[a-z]?):", re.M)
_HEAD = re.compile(r"^(#{2,3}) (.+)$", re.M)
_GEN = re.compile(r"<!-- BEGIN_GENERATED:\w+ -->.*?<!-- END_GENERATED:\w+ -->", re.S)
_PUNCT = re.compile(r"[\s|#*`>:\-—.;,()]+")


def norm(text: str, spec_name: str) -> str:
    text = re.sub(r"^[ \t]*(?:>|#)[ \t]?", "", text, flags=re.M)
    text = text.replace("](../specs/", "](")
    text = re.sub(rf"\]\({re.escape(spec_name)}#", "](#", text)
    return re.sub(r"\s+", " ", text).strip()


def git_show(rev: str, path: str) -> str:
    out = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, text=True, check=True)
    return out.stdout


def sections(text: str) -> dict[str, str]:
    """Map each ``###`` ID and each ``##`` heading's text to its body; ``title`` to the whole file."""
    out = {"title": text}
    heads = [(m.start(), m.group(1), m.group(2)) for m in _HEAD.finditer(text)] + [(len(text), "##", "")]
    for start, level, title in heads[:-1]:
        end = next(s for s, lv, _ in heads if s > start and len(lv) <= len(level))
        m = _ID.match(text, start)
        out[m.group(1) if m else title] = text[start:end]
    return out


def slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    led = importlib.import_module(sys.argv[1])
    spec_name = Path(led.SPEC).name
    old_raw = git_show(led.BASE, led.SPEC)
    new_raw = (ROOT / led.SPEC).read_text(encoding="utf-8")
    old, new_secs = (
        norm(_GEN.sub("GENERATED_BLOCK", old_raw), spec_name),
        {k: norm(v, spec_name) for k, v in sections(new_raw).items()},
    )
    fails: list[str] = []

    # 1. Cover.
    covered = [False] * len(old)
    for frag, kind, *_ in led.LEDGER:
        f = norm(frag, spec_name)
        starts = [m.start() for m in re.finditer(re.escape(f), old)]
        if len(starts) != 1 and not (kind == "drop" and starts):
            fails.append(f"cover: fragment occurs {len(starts)} times in the old spec: {f[:80]!r}")
            continue
        for i in starts:  # a drop (a field label) may recur; every occurrence is its
            covered[i : i + len(f)] = [True] * len(f)
    left = "".join(c if not covered[i] else " " for i, c in enumerate(old))
    rest = [w for w in _PUNCT.split(left) if w]
    if rest:
        fails.append(f"cover: old text no fragment claims: {' '.join(rest)[:300]!r}")

    # 2 and 3. Survive and relocate.
    files: dict[str, str] = {}

    def where(path: str) -> str:
        if path not in files:
            files[path] = norm((ROOT / path).read_text(encoding="utf-8"), spec_name)
        return files[path]

    counts: dict[str, int] = {}
    old_gen = _GEN.search(old_raw)
    new_gen = _GEN.search(new_raw)
    for frag, kind, dest, new in led.LEDGER:
        counts[kind] = counts.get(kind, 0) + 1
        if frag == "GENERATED_BLOCK":
            same = old_gen is not None and new_gen is not None and old_gen.group(0) == new_gen.group(0)
            if not (same and norm(new_gen.group(0), spec_name) in new_secs.get(dest, "")):
                fails.append(f"survive: the generated block is not unchanged under {dest}")
            continue
        if kind == "drop":
            continue
        text = norm(frag if kind in ("keep", "move") else new, spec_name)
        if kind in ("move", "homed") or (kind == "reword" and "/" in dest):
            if text not in where(dest):
                fails.append(f"{kind}: not found in {dest}: {text[:90]!r}")
        elif text not in new_secs.get(dest, ""):
            fails.append(f"{kind}: not found under {dest} in the new spec: {text[:90]!r}")

    # 4. IDs.
    old_ids, new_ids = set(_ID.findall(old_raw)), set(_ID.findall(new_raw))
    if not old_ids <= new_ids:
        fails.append(f"ids: dropped {sorted(old_ids - new_ids)}")
    if new_ids - old_ids != set(led.NEW_IDS):
        fails.append(f"ids: new {sorted(new_ids - old_ids)}, ledger says {sorted(led.NEW_IDS)}")

    # 5. Anchors.
    anchors = {slug(m.group(2)) for m in _HEAD.finditer(new_raw)}
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", "*.md", "*.py", ":!sdd/decisions", ":!sdd/traces", ":!sdd/research"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    link = re.compile(rf"{re.escape(spec_name)}#([^)\s]+)\)")
    nlinks = 0
    for path in tracked:
        p = ROOT / path
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8")
        found = link.findall(body)
        if path == led.SPEC:
            found += re.findall(r"\]\(#([^)\s]+)\)", body)
        for a in found:
            nlinks += 1
            if a not in anchors:
                fails.append(f"anchors: {path} links {spec_name}#{a}, which has no such heading")

    # 6. Gates.
    for gate in ("scripts/check_spec_marks.py", "scripts/check_formal_trace.py"):
        r = subprocess.run([sys.executable, str(ROOT / gate)], capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            fails.append(f"gate: {gate} exited {r.returncode}:\n{r.stdout[-1500:]}")

    print(
        f"ledger {sys.argv[1]}: {len(led.LEDGER)} fragments, "
        + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    )
    print(f"ids: {len(old_ids)} kept, new {sorted(new_ids - old_ids)}; links into {spec_name}: {nlinks}")
    for f in fails:
        print("FAIL:", f)
    print("RESULT:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
