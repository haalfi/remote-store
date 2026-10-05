"""RFC-0019 D4 class-pattern audit (Phase 0). Throwaway research; report only.

1. Every literal path in ``ci.yml``'s ``CODE_PAT``, ``DOCS_PAT``,
   ``FORMAL_PAT``, ``TLA_PAT`` and ``HOOKS_PAT`` must match a tracked file
   (a literal file) or a tracked file under it (a literal directory prefix).
2. Every tracked file a test reads (layer-4 table, ``readers.json``) must
   classify into a class whose jobs run that test:
   ``tests/scripts/`` tests run in ``tooling-tests`` (``code`` or ``hooks``);
   every other Stage-1 test runs in ``test`` (``code``).

Usage: python sdd/research/bk-403-phase-0/audit_classes.py <rev> <readers.json> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

from p0tree import Tree

PAT_LINE = re.compile(r"^\s*(\w+_PAT)='(.+)'\s*$")


def alternatives(pat: str) -> list[str]:
    """Top-level ``|`` alternatives, with one level of ``(a|b)`` groups expanded."""
    parts, depth, cur = [], 0, ""
    for ch in pat:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    out = []
    for p in parts:
        m = re.search(r"\(([^()]*)\)", p)
        if m:
            for alt in m.group(1).split("|"):
                out.append(p[: m.start()] + alt + p[m.end() :])
        else:
            out.append(p)
    return out


def literal(alt: str) -> tuple[str, str] | None:
    """('file'|'prefix', path) when the alternative is a literal path."""
    a = alt.lstrip("^")
    exact = a.endswith("$")
    a = a.rstrip("$")
    if re.search(r"[\[\]*+?{}()|]", a.replace("\\.", "")):
        return None
    return ("file" if exact else "prefix", a.replace("\\.", "."))


def main() -> None:
    rev, readers_path, out = sys.argv[1:4]
    t = Tree(rev)
    ci = t.text(".github/workflows/ci.yml") or ""
    pats = {m.group(1): m.group(2) for m in (PAT_LINE.match(x) for x in ci.splitlines()) if m}
    compiled = {k: re.compile(v) for k, v in pats.items()}

    literal_misses = []
    literal_count = 0
    for name, pat in pats.items():
        for alt in alternatives(pat):
            lit = literal(alt)
            if lit is None:
                continue
            literal_count += 1
            kind, path = lit
            ok = path in t.files if kind == "file" else any(f.startswith(path) for f in t.files)
            if not ok:
                literal_misses.append({"pattern": name, "alternative": alt, "kind": kind})

    def classes(path: str) -> set[str]:
        return {k.removesuffix("_PAT").lower() for k, rx in compiled.items() if rx.search(path)}

    with open(readers_path, encoding="utf-8") as fh:
        readers = json.load(fh)
    violations = []
    by_classes: dict[str, set[str]] = defaultdict(set)
    for target, rs in readers["reads"].items():
        if target not in t.files:
            continue
        cls = classes(target)
        for r in rs:
            if r.startswith("dir:"):
                continue
            runs_on = {"code", "hooks"} if r.startswith("tests/scripts/") else {"code"}
            if not cls & runs_on:
                violations.append({"target": target, "classes": sorted(cls) or ["none"], "reader": r})
                by_classes[",".join(sorted(cls)) or "none"].add(target)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "rev": rev,
                "patterns": list(pats),
                "literal_alternatives": literal_count,
                "literal_misses": literal_misses,
                "read_violations": len(violations),
                "violating_targets": sum(len(v) for v in by_classes.values()),
                "violating_targets_by_class": {k: sorted(v) for k, v in sorted(by_classes.items())},
                "violations": violations,
            },
            fh,
            indent=1,
        )
    print(
        f"patterns {len(pats)}, literal alternatives {literal_count}, misses {len(literal_misses)}: "
        f"{[m['alternative'] for m in literal_misses]}; read violations {len(violations)} over "
        f"{sum(len(v) for v in by_classes.values())} files: { {k: len(v) for k, v in by_classes.items()} }"
    )


if __name__ == "__main__":
    main()
