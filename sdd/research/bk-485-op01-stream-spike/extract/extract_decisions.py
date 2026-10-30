#!/usr/bin/env python3
"""Extract closed decisions from an observe record into a Markdown table.

Usage: extract_decisions.py RECORD.md OUT.md

Keeps every `### <ID>/Dn` section whose Open items field is `none` and emits
Heading | Scenario | Observed. A decision starting with option letters,
e.g. `(a).`, has each letter expanded to that option's text from Options.
Tables embedded in a field are dropped; prose is flattened to one line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADING = re.compile(r"^### (\S+/D\d+: .+)$")
FIELD = re.compile(r"^- \*\*(?P<name>[^*]+):\*\*\s?(?P<rest>.*)$")
LEADING = re.compile(r"^\(([a-z])\)((?: and \([a-z]\))*)")


def sections(text: str) -> list[tuple[str, list[str]]]:
    """Split into (heading, body lines) for each decision section."""
    out: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            current = (m.group(1), [])
            out.append(current)
        elif line.startswith(("## ", "### ")):
            current = None  # any other heading ends a decision section
        elif current is not None:
            current[1].append(line)
    return out


def fields(body: list[str]) -> dict[str, str]:
    """Map field name to flattened prose; embedded table rows are dropped."""
    raw: dict[str, list[str]] = {}
    name = None
    for line in body:
        m = FIELD.match(line)
        if m:
            name = m.group("name")
            raw[name] = [m.group("rest")]
        elif name is not None and not line.lstrip().startswith("|"):
            raw[name].append(line)
    return {k: " ".join(" ".join(v).split()) for k, v in raw.items()}


def option_text(options: str, letter: str) -> str:
    """Text of option `(letter)`: up to the next letter's marker or Follow-up."""
    start = options.find(f"({letter}) ")
    if start < 0:
        raise ValueError(f"option ({letter}) not found in: {options!r}")
    start += len(letter) + 3
    ends = [options.find(f"({chr(ord(letter) + 1)}) ", start), options.find("Follow-up", start)]
    end = min((e for e in ends if e >= 0), default=len(options))
    return options[start:end].strip().rstrip(";.,").strip()


def expand(decision: str, options: str) -> str:
    """Replace leading option letters with `(x) <option text>`."""
    m = LEADING.match(decision)
    if not m:
        return decision
    letters = [m.group(1), *re.findall(r"\(([a-z])\)", m.group(2))]
    head = " and ".join(f"({x}) {option_text(options, x)}" for x in letters)
    rest = decision[m.end() :]
    return head + (rest if rest else ".")


def cell(s: str) -> str:
    return s.replace("|", r"\|")


def main(record: Path, out: Path) -> None:
    rows = []
    for heading, body in sections(record.read_text(encoding="utf-8")):
        f = fields(body)
        if f.get("Open items", "").rstrip(".") != "none":
            continue
        observed = expand(f["Decision"], f["Options"])
        rows.append(f"| {cell(heading)} | {cell(f['Scenario'])} | {cell(observed)} |")
    lines = [
        f"# {record.stem}: closed decisions",
        "",
        "<!-- doc: repo-only -->",
        "",
        f"Source: `{record.as_posix()}`. Decisions with Open items `none`: {len(rows)}.",
        "That field is each decision's own; later open items do not update it (see ../report.md § 2).",
        "",
        "```markdown",
        "| Heading | Scenario | Observed |",
        "|---|---|---|",
        *rows,
        "```",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
