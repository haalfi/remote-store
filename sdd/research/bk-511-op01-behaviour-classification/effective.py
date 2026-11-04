"""Effective-decision view of an /observe record, plus coarse classification signals.

Usage: effective.py RECORD.md OUT.json

Per decision: heading, axis tag, reopen/close-out source, direct Amends targets,
Amended-by (direct and transitive), and keyword signals for the facets to be
designed: Environment rows cited, read form, sync/async, backends, path.
Signals are keyword hits, not a classification.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

FIELD = re.compile(r"^- \*\*(?P<name>[^*]+):\*\*\s?(?P<rest>.*)$")
BACKENDS = ["Local", "S3", "Azure", "SFTP", "GCS", "HTTP", "Memory", "NFS", "Windows", "MinIO"]
FORMS = {
    "whole": r"\bwhole (read|bytes|text)|read_bytes|read_text|\bbytes form|\btext form",
    "stream": r"\bstream",
    "async": r"\basync|AsyncStore|asyncio|\btask\b",
    "sync": r"\bsync form|\bStore\b(?!\w)",
}
PATH = {
    "failure": r"\bfail|\braise|\berror|\bunavailable|\btimeout|not found|denied|refused|\bchanged\b",
    "cancel": r"\bcancel",
    "concurrency": r"\bO2\b|\bO3\b|overlap|concurrent|interleav",
    "lifecycle": r"\bclose|\bClosed\b|\bExhausted\b|\bFailed\b|\bOpen\b|lifetime|collect",
}


def parse(text: str) -> dict[int, dict]:
    head = text.split("\n## Axis status\n")[0]
    out = {}
    for sec in re.split(r"^(?=### OP-01/D\d+:)", head, flags=re.M):
        m = re.match(r"### OP-01/D(\d+): (.*)", sec)
        if not m:
            continue
        d, title = int(m.group(1)), m.group(2).strip()
        fields, name = {}, None
        for line in sec.splitlines()[1:]:
            fm = FIELD.match(line)
            if fm:
                name = fm.group("name")
                fields[name] = [fm.group("rest")]
            elif name and line.startswith("  "):
                fields[name].append(line)
        fields = {k: " ".join(" ".join(v).split()) for k, v in fields.items()}
        tag = re.search(r"\(([^()]*)\)\s*$", title)
        tag = tag.group(1) if tag else ""
        out[d] = {
            "title": title,
            "axis": re.findall(r"AX-\d+", tag),
            "source": re.sub(r"AX-\d+,?\s*", "", tag).strip(", "),
            "amends": [int(x) for x in re.findall(r"OP-01/D(\d+)", fields.get("Amends", ""))],
            "amended_by_field": [int(x) for x in re.findall(r"OP-01/D(\d+)", fields.get("Amended by", ""))],
            "open_items": fields.get("Open items", ""),
            "scenario": fields.get("Scenario", ""),
            "decision": fields.get("Decision", ""),
        }
    return out


def main(record: Path, out: Path) -> None:
    ds = parse(record.read_text(encoding="utf-8"))
    by = collections.defaultdict(set)
    for d, v in ds.items():
        for t in v["amends"]:
            by[t].add(d)

    def closure(d, seen=None):
        seen = set() if seen is None else seen
        for a in sorted(by.get(d, ())):
            if a not in seen:
                seen.add(a)
                closure(a, seen)
        return seen

    for d, v in ds.items():
        v["amended_by"] = sorted(by.get(d, ()))
        v["amended_by_all"] = sorted(closure(d))
        v["field_agrees"] = sorted(v["amended_by_field"]) == v["amended_by"]
        body = v["scenario"] + " " + v["decision"]
        v["env_rows"] = sorted(set(re.findall(r"\bE(\d+)\b", body)), key=int)
        v["forms"] = [k for k, p in FORMS.items() if re.search(p, body)]
        v["backends"] = [b for b in BACKENDS if re.search(rf"\b{b}\b", body)]
        v["path"] = [k for k, p in PATH.items() if re.search(p, body, re.I if k != "lifecycle" else 0)]
    out.write_text(json.dumps(ds, indent=1, ensure_ascii=False), encoding="utf-8")

    n = len(ds)
    amended = [d for d, v in ds.items() if v["amended_by"]]
    print(f"decisions: {n}; amended: {len(amended)}; amending: {sum(1 for v in ds.values() if v['amends'])}")
    print("Amended-by field disagrees with Amends lines:", [d for d, v in ds.items() if not v["field_agrees"]])
    deep = sorted(((len(v["amended_by_all"]), d) for d, v in ds.items()), reverse=True)[:8]
    print("deepest chains (decision: transitive amenders):", ", ".join(f"D{d}: {k}" for k, d in deep))
    print(
        "by axis:",
        dict(
            sorted(
                collections.Counter(a for v in ds.values() for a in v["axis"] or ["none"]).items(),
                key=lambda x: (x[0] == "none", int(x[0][3:]) if x[0] != "none" else 0),
            )
        ),
    )
    for facet in ("forms", "path", "backends"):
        c = collections.Counter(x for v in ds.values() for x in v[facet])
        none = sum(1 for v in ds.values() if not v[facet])
        print(f"{facet}: {dict(c.most_common())}; none: {none}")
    c = collections.Counter(e for v in ds.values() for e in v["env_rows"])
    print("Environment rows cited:", {f"E{k}": c[k] for k in sorted(c, key=int)})
    src = collections.Counter(
        "reopen"
        if "reopen" in v["source"]
        else "close-out"
        if "close-out" in v["source"]
        else "end check"
        if "end check" in v["source"]
        else "first session"
        if d <= 44
        else "other"
        for d, v in ds.items()
    )
    print("by source:", dict(src))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
