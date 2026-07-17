#!/usr/bin/env python3
"""Compile sdd/adrs/*.md into sdd/adrs/DIGEST.md — deterministically, no LLM.

Each ADR carries its own machine-readable summary in two places the tool reads:
a visible key/value table in the ``## Status`` section, and an invisible
``<!-- adr:decision -->`` fence around the decision statement. Extraction is a
parse, never an inference, so the digest is a pure function of the ADRs and
cannot drift from them:

    # ADR-0002: Configuration Resolution - No Merging

    ## Status

    | Field         | Value    |
    | ------------- | -------- |
    | Status        | Accepted |
    | Supersedes    | —        |
    | Superseded by | —        |
    | Amends        | —        |

    ## Decision

    <!-- adr:decision -->
    **Config-as-code has absolute priority. No merging, no env var overrides.**
    <!-- /adr:decision -->

``Status`` is one of Proposed | Accepted | Superseded. Link cells hold bare ADR
ids (e.g. ``ADR-0007``), comma-separated, or ``—`` when none: ``Supersedes`` /
``Superseded by`` are whole-ADR edges; ``Amends`` is a clause-level change that
leaves the target ADR otherwise in force. Extra prose (which clause, revision
notes) goes below the table.

Normal mode (no flag):
    Regenerate sdd/adrs/DIGEST.md. Refuses on hard errors (missing table/fence,
    bad status, dangling supersession target); prints drift warnings but still
    writes. Run: hatch run gen-adr-digest.

Check mode (--check):
    Read-only. Exit 0 when every ADR is well-formed, the supersession graph is
    consistent, and DIGEST.md matches a fresh render. Exit 1 otherwise. Suitable
    as a lint gate.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "sdd" / "adrs"
DIGEST = ADR_DIR / "DIGEST.md"

STATUSES = ("Proposed", "Accepted", "Superseded")
LINK_KEYS = ("supersedes", "superseded-by", "amends")

# Real ADR files are named NNNN-slug.md; DIGEST.md and any future non-numbered
# companion must not be parsed as an ADR.
ADR_GLOB = "[0-9][0-9][0-9][0-9]-*.md"

DECISION_RE = re.compile(
    r"<!--\s*adr:decision\s*-->\s*(.*?)\s*<!--\s*/adr:decision\s*-->",
    re.DOTALL,
)
H1_RE = re.compile(r"^#\s+(.*?)\s*$", re.MULTILINE)
STATUS_SECTION_RE = re.compile(r"^##\s+Status\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)

# Metadata is a visible key/value table in the `## Status` section — the same
# text a human reads and edits, so there is no hidden source of truth to drift
# from. The table is scoped to `## Status` so an unrelated table elsewhere in
# the ADR is never mistaken for metadata.
_TABLE_FIELDS = {
    "status": "status",
    "supersedes": "supersedes",
    "superseded by": "superseded-by",
    "superseded-by": "superseded-by",
    "amends": "amends",
}
_EMPTY_CELL = {"", "-", "—", "none", "n/a"}


def _split_links(cell: str) -> list[str]:
    if cell.strip().lower() in _EMPTY_CELL:
        return []
    return [part.strip() for part in cell.split(",") if part.strip().lower() not in _EMPTY_CELL]


def _table_meta(text: str) -> dict | None:
    """Parse the key/value metadata table from the ``## Status`` section, or None."""
    section = STATUS_SECTION_RE.search(text)
    if not section:
        return None
    fields: dict[str, str] = {}
    for line in section.group(1).splitlines():
        row = line.strip()
        if not (row.startswith("|") and row.endswith("|")):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) != 2:
            continue
        mapped = _TABLE_FIELDS.get(cells[0].lower())
        if mapped is not None:  # skips header ("Field") and separator ("---") rows
            fields[mapped] = cells[1]
    if "status" not in fields:
        return None
    return {
        "status": fields["status"],
        "supersedes": _split_links(fields.get("supersedes", "")),
        "superseded-by": _split_links(fields.get("superseded-by", "")),
        "amends": _split_links(fields.get("amends", "")),
    }


@dataclasses.dataclass
class Adr:
    path: Path
    id: str  # "ADR-0002"
    number: str  # "0002"
    title: str  # heading with the "ADR-NNNN: " prefix stripped
    status: str
    supersedes: list[str]
    superseded_by: list[str]
    amends: list[str]
    decision: str


def _norm_id(number: str) -> str:
    return f"ADR-{number}"


def parse(path: Path) -> tuple[Adr | None, list[str]]:
    """Parse one ADR. Returns (adr, hard_errors).

    *adr* is None only when the file is too malformed to place in the digest.
    """
    text = path.read_text(encoding="utf-8")
    number = path.stem.split("-", 1)[0]
    adr_id = _norm_id(number)
    errors: list[str] = []

    h1 = H1_RE.search(text)
    title = h1.group(1) if h1 else ""
    title = re.sub(rf"^ADR-{number}:\s*", "", title).strip()

    meta = _table_meta(text)
    if meta is None:
        return None, [f"{path.name}: no metadata table in the ## Status section"]

    status = meta.get("status")
    if not status:
        errors.append(f"{path.name}: Status table missing a 'Status' row")
    elif status not in STATUSES:
        errors.append(f"{path.name}: status '{status}' not in {list(STATUSES)}")

    links = {key: list(meta.get(key) or []) for key in LINK_KEYS}

    dec_match = DECISION_RE.search(text)
    if not dec_match:
        errors.append(f"{path.name}: missing <!-- adr:decision --> fence")
    # Preserve internal structure (a decision is often a lead-in + list); only
    # trim the outer whitespace. Collapsing to one line would drop the layers.
    decision = dec_match.group(1).strip() if dec_match else ""

    adr = Adr(
        path=path,
        id=adr_id,
        number=number,
        title=title,
        status=str(status or ""),
        supersedes=links["supersedes"],
        superseded_by=links["superseded-by"],
        amends=links["amends"],
        decision=decision,
    )
    return adr, errors


def load_all(adr_dir: Path) -> tuple[list[Adr], list[str]]:
    adrs: list[Adr] = []
    errors: list[str] = []
    for path in sorted(adr_dir.glob(ADR_GLOB)):
        adr, errs = parse(path)
        errors.extend(errs)
        if adr is not None:
            adrs.append(adr)
    return adrs, errors


def hard_errors(adrs: list[Adr]) -> list[str]:
    """Graph-level problems that make the digest wrong (block generation)."""
    errors: list[str] = []
    known = {a.id for a in adrs}
    for a in adrs:
        for key, targets in (
            ("supersedes", a.supersedes),
            ("superseded-by", a.superseded_by),
            ("amends", a.amends),
        ):
            for target in targets:
                if target not in known:
                    errors.append(f"{a.id}: {key} points at unknown ADR '{target}'")
    return errors


def drift_warnings(adrs: list[Adr]) -> list[str]:
    """Consistency problems worth surfacing that do not block generation.

    The headline case: ADR X declares it fully supersedes Y, but Y is still
    marked Accepted instead of Superseded — the retirement was recorded on one
    side only.
    """
    warnings: list[str] = []
    by_id = {a.id: a for a in adrs}
    for a in adrs:
        for target in a.supersedes:
            other = by_id.get(target)
            if other is not None and other.status != "Superseded":
                warnings.append(
                    f"{a.id} supersedes {target}, but {target} is still '{other.status}' (expected 'Superseded')"
                )
        if a.status == "Superseded" and not a.superseded_by and not any(a.id in other.supersedes for other in adrs):
            warnings.append(f"{a.id} is 'Superseded' but nothing records what superseded it")
    return warnings


def render(adrs: list[Adr]) -> str:
    lines = [
        "# ADR digest",
        "",
        # Generated repo artifact, not a docs-site page: classify it out of the
        # docs bridge (docs-framework G-01). skip_stems keeps it out of the ADR
        # nav; this marker satisfies the "every file is classified" gate.
        "<!-- doc: repo-only -->",
        "",
        f"Compiled from {len(adrs)} ADR(s) by `scripts/gen_adr_digest.py`. "
        "Do not edit by hand; run `hatch run gen-adr-digest`.",
        "",
    ]
    for status in STATUSES:
        group = sorted((a for a in adrs if a.status == status), key=lambda x: x.number)
        if not group:
            continue
        lines.append(f"## {status}")
        lines.append("")
        for a in group:
            lines.append(f"### [{a.id}]({a.path.name}): {a.title}")
            lines.append("")
            lines.append(a.decision or "_(no decision recorded)_")
            edges = []
            if a.supersedes:
                edges.append("supersedes " + ", ".join(a.supersedes))
            if a.superseded_by:
                edges.append("superseded by " + ", ".join(a.superseded_by))
            if a.amends:
                edges.append("amends " + ", ".join(a.amends) + " (clause)")
            if edges:
                lines.append("")
                lines.append("> " + "; ".join(edges) + ".")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _report(stream, label: str, items: list[str]) -> None:
    for item in items:
        print(f"{label} {item}", file=stream)


def generate() -> int:
    adrs, errors = load_all(ADR_DIR)
    errors += hard_errors(adrs)
    if errors:
        _report(sys.stderr, "ERROR", errors)
        print(f"\n{len(errors)} hard error(s); refusing to write DIGEST.md.", file=sys.stderr)
        return 1
    DIGEST.write_text(render(adrs), encoding="utf-8", newline="\n")
    rel = DIGEST.relative_to(ROOT)
    print(f"Wrote {rel} ({len(adrs)} ADRs).")
    warnings = drift_warnings(adrs)
    if warnings:
        _report(sys.stdout, "DRIFT", warnings)
        print(f"{len(warnings)} drift warning(s) — see above.")
    return 0


def check() -> int:
    adrs, errors = load_all(ADR_DIR)
    errors += hard_errors(adrs)
    if errors:
        _report(sys.stderr, "ERROR", errors)
        print(f"\n{len(errors)} hard error(s). Run: hatch run gen-adr-digest", file=sys.stderr)
        return 1

    rendered = render(adrs)
    try:
        current = DIGEST.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR {DIGEST.relative_to(ROOT)} not found. Run: hatch run gen-adr-digest")
        return 1
    stale = current != rendered

    warnings = drift_warnings(adrs)
    if warnings:
        _report(sys.stdout, "DRIFT", warnings)
    if stale:
        print(f"STALE: {DIGEST.relative_to(ROOT)} is out of date. Run: hatch run gen-adr-digest")

    if stale or warnings:
        return 1
    print(f"OK — {len(adrs)} ADR(s), digest current, graph consistent.")
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check()
    return generate()


if __name__ == "__main__":
    raise SystemExit(main())
