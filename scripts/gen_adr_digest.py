#!/usr/bin/env python3
"""Compile sdd/adrs/*.md into sdd/adrs/DIGEST.md — deterministically, no LLM.

Each ADR is read through its own document structure — no hand-placed markers:
the metadata is a visible key/value table in the ``## Status`` section, and the
decision is the entire ``## Decision`` section (up to the next ``##``).
Extraction is a parse, never an inference, so the digest is a pure function of
the ADRs and cannot drift from them:

    # ADR-0002: Configuration Resolution - No Merging

    ## Status

    | Field         | Value    |
    | ------------- | -------- |
    | Status        | Accepted |
    | Supersedes    | —        |
    | Superseded by | —        |
    | Amends        | —        |

    ## Decision

    **Config-as-code has absolute priority. No merging, no env var overrides.**

    Resolution rules: ...

``Status`` is one of Proposed | Accepted | Superseded. Link cells hold bare ADR
ids (e.g. ``ADR-0007``), comma-separated, or ``—`` when none: ``Supersedes`` /
``Superseded by`` are whole-ADR edges; ``Amends`` is a clause-level change that
leaves the target ADR otherwise in force. Extra prose (which clause, revision
notes) goes below the table. The whole ``## Decision`` section is lifted into
the digest verbatim, with its internal headings demoted to nest cleanly.

Normal mode (no flag):
    Regenerate sdd/adrs/DIGEST.md. Refuses on hard errors (missing Status table
    or Decision section, bad status, dangling supersession target); prints drift
    warnings but still writes. Run: hatch run gen-adr-digest.

Check mode (--check):
    Read-only. Exit 0 when every ADR is well-formed, the supersession graph is
    consistent, and DIGEST.md matches a fresh render. Exit 1 otherwise. Suitable
    as a lint gate.

Advisory stream (both modes):
    Each ``## Decision`` section is additionally checked, on its raw (undemoted)
    body, against a word budget, presence of version specifiers (e.g. ``>=1.3``,
    which usually belong in pyproject/spec rather than prose), and heading depth
    (a ``####`` or deeper heading inside a Decision is a smell). Flagged ADRs
    print non-failing ``ADVICE`` notices, plus a corpus-wide Decision word-count
    summary, in both normal and ``--check`` mode. Thresholds are configurable via
    ``--max-decision-words`` / ``--max-decision-depth``. This stream never changes
    the exit status — it is advisory only, not a gate (ID-232 research §8).
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "sdd" / "adrs"
DIGEST = ADR_DIR / "DIGEST.md"

STATUSES = ("Proposed", "Accepted", "Superseded")
LINK_KEYS = ("supersedes", "superseded-by", "amends")

# Advisory thresholds for the (non-failing) Decision-bloat heuristic — see the
# "Advisory stream" note in the module docstring and `advisory_notices()`.
DECISION_WORD_BUDGET = 350
DECISION_MAX_DEPTH = 3  # H3; deeper (####) headings inside a Decision are a smell

# Real ADR files are named NNNN-slug.md; DIGEST.md and any future non-numbered
# companion must not be parsed as an ADR.
ADR_GLOB = "[0-9][0-9][0-9][0-9]-*.md"

H1_RE = re.compile(r"^#\s+(.*?)\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})(\s)")
_H2_RE = re.compile(r"^##\s")


def _fence_toggle(line: str) -> bool:
    return line.lstrip().startswith("```")


def _section(text: str, name: str) -> str | None:
    """Return the body of the ``## <name>`` section, up to the next ``##`` heading
    that is not inside a fenced code block, or None if the heading is absent.

    Code-fence aware so a ``## ...`` line inside a code block (e.g. a markdown
    example in a Decision section) does not truncate the section — matching
    ``_demote_headings`` and closing the silent-truncation gap the whole-section
    refactor set out to eliminate.
    """
    heading = re.compile(rf"^##\s+{re.escape(name)}\s*$")
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return None
    body: list[str] = []
    in_code = False
    for line in lines[start:]:
        if _fence_toggle(line):
            in_code = not in_code
        elif not in_code and _H2_RE.match(line):
            break
        body.append(line)
    return "\n".join(body)


def _demote_headings(md: str, by: int = 2) -> str:
    """Push ATX headings down *by* levels (capped at 6) so a lifted Decision
    section nests under the digest's per-ADR heading instead of colliding with
    it. Headings inside fenced code blocks are left alone."""
    out: list[str] = []
    in_code = False
    for line in md.splitlines():
        if _fence_toggle(line):
            in_code = not in_code
            out.append(line)
            continue
        m = _HEADING_RE.match(line)
        if m and not in_code:
            level = min(len(m.group(1)) + by, 6)
            line = "#" * level + line[len(m.group(1)) :]
        out.append(line)
    return "\n".join(out)


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
    section = _section(text, "Status")
    if section is None:
        return None
    fields: dict[str, str] = {}
    for line in section.splitlines():
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
    decision_raw: str  # undemoted ## Decision body, for advisory measurement


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

    # The decision is the whole ## Decision section (up to the next ## heading),
    # not a hand-placed span — the section boundary can't be misplaced, and every
    # detail (resolution rules, tiers, tables) comes along. Internal headings are
    # demoted so they nest under the digest's per-ADR heading.
    section = _section(text, "Decision")
    body = section.strip() if section else ""
    if not body:
        errors.append(f"{path.name}: missing or empty ## Decision section")
    decision = _demote_headings(body)

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
        decision_raw=body,
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

    Three checks:
    1. Status drift — ADR X fully supersedes Y, but Y is not marked Superseded.
    2. Reciprocity — a supersession edge declared on one side but not the other.
       (A supersedes-B must appear as B superseded-by-A, and vice versa; an edge
       recorded on only one side renders an asymmetric graph in the digest.)
    3. Orphan — a Superseded ADR with nothing recording what superseded it.
    """
    warnings: list[str] = []
    by_id = {a.id: a for a in adrs}
    for a in adrs:
        for target in a.supersedes:
            other = by_id.get(target)
            if other is None:
                continue  # dangling target is a hard error, reported elsewhere
            # (1) status drift
            if other.status != "Superseded":
                warnings.append(
                    f"{a.id} supersedes {target}, but {target} is still '{other.status}' (expected 'Superseded')"
                )
            # (2) reciprocity: the target must record the back-edge
            if a.id not in other.superseded_by:
                warnings.append(
                    f"{a.id} declares 'supersedes {target}', but {target} does not "
                    f"list {a.id} under 'superseded-by' (one-sided edge)"
                )
        for target in a.superseded_by:
            other = by_id.get(target)
            if other is not None and a.id not in other.supersedes:
                warnings.append(
                    f"{a.id} declares 'superseded-by {target}', but {target} does not "
                    f"list {a.id} under 'supersedes' (one-sided edge)"
                )
        # (3) orphaned Superseded status
        if a.status == "Superseded" and not a.superseded_by and not any(a.id in other.supersedes for other in adrs):
            warnings.append(f"{a.id} is 'Superseded' but nothing records what superseded it")
    return warnings


# Advisory-only heuristics: never gate (see the module docstring's "Advisory
# stream" note). Measured on the *raw*, undemoted Decision body — `a.decision`
# has already been heading-demoted by +2, which would corrupt depth checks.
_VERSION_SPEC_RE = re.compile(r"(?:>=|<=|==|~=|!=)\s*\d+(?:\.\d+)*")


def _version_specs_outside_fences(body: str) -> list[str]:
    """Version-specifier literals (e.g. ``>=1.3``) outside fenced code blocks."""
    matches: list[str] = []
    in_code = False
    for line in body.splitlines():
        if _fence_toggle(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        matches.extend(m.group(0) for m in _VERSION_SPEC_RE.finditer(line))
    return matches


def _deepest_heading_over(body: str, max_depth: int) -> int:
    """Deepest ATX heading level exceeding *max_depth* outside fenced code
    blocks, or 0 if none exceed it."""
    deepest = 0
    in_code = False
    for line in body.splitlines():
        if _fence_toggle(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if level > max_depth:
                deepest = max(deepest, level)
    return deepest


def _count_subsections_and_fences(body: str) -> tuple[int, int]:
    """(count of exact ``### `` subsection headings, count of fenced code
    blocks) outside/around fences, on the raw Decision body."""
    subsections = 0
    fence_toggles = 0
    in_code = False
    for line in body.splitlines():
        if _fence_toggle(line):
            in_code = not in_code
            fence_toggles += 1
            continue
        if not in_code and line.startswith("### "):
            subsections += 1
    return subsections, fence_toggles // 2


def _subsections(body: str) -> list[tuple[str, str]]:
    """Split *body* into (title, text) segments on exact ``### `` headings
    outside fenced code blocks. Text before the first such heading is titled
    ``(preamble)``. Headings inside fences do not split a segment."""
    segments: list[tuple[str, list[str]]] = [("(preamble)", [])]
    in_code = False
    for line in body.splitlines():
        if _fence_toggle(line):
            in_code = not in_code
            segments[-1][1].append(line)
            continue
        if not in_code and line.startswith("### "):
            segments.append((line.lstrip("#").strip(), []))
            continue
        segments[-1][1].append(line)
    return [(title, "\n".join(lines)) for title, lines in segments]


def decision_word_total(adrs: list[Adr]) -> int:
    """Total word count across every ADR's raw Decision body — the
    before/after corpus metric for a Decision-slimming pass."""
    return sum(len(a.decision_raw.split()) for a in adrs)


def advisory_notices(
    adrs: list[Adr],
    *,
    word_budget: int = DECISION_WORD_BUDGET,
    max_depth: int = DECISION_MAX_DEPTH,
) -> list[str]:
    """Non-failing advisory signals on each ADR's raw ``## Decision`` body.

    Three triggers, any one of which flags the ADR:
    1. Word budget — the Decision body exceeds *word_budget* words.
    2. Version specifiers — pins like ``>=1.3`` outside fenced code, which
       usually belong in pyproject/spec rather than ADR prose.
    3. Heading depth — a heading deeper than *max_depth* (default H3), a
       forward guardrail against Decisions growing their own outline.

    Enrichment (subsection/code-block counts, heaviest subsections) is
    reported alongside a length flag but never triggers one by itself.

    Returns one combined notice string per flagged ADR (unflagged ADRs are
    omitted), without a leading label — callers prefix via `_report`, same as
    `drift_warnings`. Never affects exit status: advisory only (ID-232
    research §8).
    """
    notices: list[str] = []
    for a in adrs:
        body = a.decision_raw
        words = len(body.split())
        over_budget = words > word_budget
        specs = _version_specs_outside_fences(body)
        deepest = _deepest_heading_over(body, max_depth)

        if not (over_budget or specs or deepest):
            continue

        parts: list[str] = []
        if over_budget:
            overage = words - word_budget
            subsection_count, code_blocks = _count_subsections_and_fences(body)
            piece = (
                f"Decision {words} words (budget {word_budget}, +{overage}); "
                f"{subsection_count} subsections, {code_blocks} code blocks"
            )
            heavy = sorted(
                ((title, len(text.split())) for title, text in _subsections(body) if len(text.split()) > 100),
                key=lambda item: item[1],
                reverse=True,
            )[:3]
            if heavy:
                heavy_str = ", ".join(f"'{title}' (~{count} w)" for title, count in heavy)
                piece += f"; heaviest: {heavy_str}"
            parts.append(piece)
        if specs:
            parts.append(
                f"Decision carries {len(specs)} version specifier(s) (e.g. '{specs[0]}') "
                "— spec-rate pins belong in pyproject/spec"
            )
        if deepest:
            parts.append(f"Decision has a heading at depth {deepest} (max advised {max_depth}); consider flattening")

        notices.append(f"{a.id} ({a.path.name}): " + "; ".join(parts))
    return notices


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


def _report_advice(adrs: list[Adr], *, word_budget: int, max_depth: int) -> None:
    """Print the advisory ADVICE stream plus the corpus summary line. Purely
    additive output — never consulted for the caller's return value."""
    notices = advisory_notices(adrs, word_budget=word_budget, max_depth=max_depth)
    if notices:
        _report(sys.stdout, "ADVICE", notices)
    total = decision_word_total(adrs)
    print(f"Decision total: {total} words across {len(adrs)} ADR(s).")
    if notices:
        print(f"{len(notices)} advisory notice(s); advisory only, never a gate (ID-232 research §8).")


def generate(*, word_budget: int = DECISION_WORD_BUDGET, max_depth: int = DECISION_MAX_DEPTH) -> int:
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
    _report_advice(adrs, word_budget=word_budget, max_depth=max_depth)
    return 0


def check(*, word_budget: int = DECISION_WORD_BUDGET, max_depth: int = DECISION_MAX_DEPTH) -> int:
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

    result = 1 if (stale or warnings) else 0
    if result == 0:
        print(f"OK — {len(adrs)} ADR(s), digest current, graph consistent.")
    _report_advice(adrs, word_budget=word_budget, max_depth=max_depth)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only: exit 1 on hard errors, drift, or a stale DIGEST.md; 0 otherwise.",
    )
    parser.add_argument(
        "--max-decision-words",
        type=int,
        default=DECISION_WORD_BUDGET,
        help=f"Advisory word budget for a ## Decision body (default {DECISION_WORD_BUDGET}).",
    )
    parser.add_argument(
        "--max-decision-depth",
        type=int,
        default=DECISION_MAX_DEPTH,
        help=f"Advisory max heading depth inside a ## Decision body (default {DECISION_MAX_DEPTH}).",
    )
    args = parser.parse_args()
    if args.check:
        return check(word_budget=args.max_decision_words, max_depth=args.max_decision_depth)
    return generate(word_budget=args.max_decision_words, max_depth=args.max_decision_depth)


if __name__ == "__main__":
    raise SystemExit(main())
