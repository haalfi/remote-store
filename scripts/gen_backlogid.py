#!/usr/bin/env python3
"""Maintain sdd/backlogid.json — max ID per prefix in BACKLOG-DONE.md.

Normal mode (no flag):
    Scans BACKLOG-DONE.md, writes sdd/backlogid.json.
    Run after moving items to BACKLOG-DONE.md: hatch run gen-backlogid.

Check mode (--check):
    Read-only and offline. Verifies the JSON is current, then checks BACKLOG.md
    for collisions with done items **and for one ID carried by two open
    items**, checks BACKLOG-DONE.md for one ID on two entries with at least one
    above released history, checks each open item's attributes (R1) and the file's shape
    (R2–R4, below), and prints next safe IDs per prefix — safe **for this tree
    only**; parallel sessions mint from a reservation instead
    (``BACKLOG.md`` § How this file works).
    Exit 0 = clean; 1 = stale JSON, collisions, duplicates, or R1–R4 violations.
    Wired into `hatch run lint` and `hatch run docs-gate` — the latter because
    `lint` is CODE_PAT-gated and so skipped for an `sdd/`-only change, which is
    exactly the change that bumps this file.

    The duplicate half exists because the open-versus-done comparison could not
    see its own file: `_extract_ids` returns sets, so two headers sharing an ID
    collapsed to one before anything compared them. Measured — `BK-382` reached
    master on two distinct open items (from `8e35697` and `e5fb4a8`) and this
    check printed "No ID collisions." ID-257 predicted the minting collision and
    records that its open-versus-open half had no gate; this is that gate. It
    catches the collision **after** both branches merge and does not prevent it;
    ``--remote`` below is the opt-in view before the merge.

    **The done register (BK-385).** `BACKLOG-DONE.md` collapses the same way,
    and the path is the ordinary one: two branches mint one ID and each
    *closes* its item before merging, so neither is ever open. An ID on two
    done headers fails when at least one header sits above the first
    ``## v<digit>`` heading — `Absorbed`, `Decided against` and `Unreleased`,
    where every close lands first. **Bound: a pair wholly inside released
    history is not reported.** The register carries four such pairs from before
    the ID discipline (`BK-001`, `BUG-001`, `BUG-144`, and `BK-167b`, whose
    second header is the sanctioned `(partial)` split shape); renumbering inside
    released sections would falsify the release record, so the release record
    is their register (DRIFT-RULES Rule 6) and no exemption list exists. A new
    pair cannot reach released history without first passing the live region,
    unless the gate was bypassed. Pinned by ``TestCheck``'s stated-bound test.

    **R1, attribute vocabulary** ([ADR-0040](../sdd/adrs/0040-backlog-as-index.md)).
    Every open item's header is followed directly by its
    ``spec: … · effort: … · audience: …`` line; ``effort`` is one of S/M/L and
    each ``audience`` value is in ``sdd/traces/_schema.yml``'s enum, read from
    the schema so the two vocabularies cannot drift. A missing line fails too,
    or an item could evade the rule by omitting it. It checks vocabulary, not
    whether a value is right for the item.

    **R2–R4, shape** (ADR-0040, RFC-0016 D1–D3). A *section* is a ``## ``
    heading other than the rules header; it ends before the separators
    (blank, ``---``, anchor) that precede the next heading.

    * R2: an item is at most 8 content lines (header through its last
      non-separator line, as ``sdd/rfcs/rfc-0016-measure.py`` counts), and at
      most 5 of them between the attribute line and an optional final
      ``Detail:`` line.
    * R3: the preamble is one ``**Promise:**`` paragraph of at most 3
      sentences. So ``Closes when`` fails it. Sentences are split on ``.!?``
      before whitespace and a capital-ish opener. **Bound, both directions:**
      an abbreviation before a capital over-counts (fails loud); a sentence
      opening with a lowercase identifier or a digit (``s3fs``, ``404s``) is
      not counted (fails open). Pinned by ``TestShape``'s stated-bound test.
    * R4: a ``Detail:`` line has the shape
      ``Detail: [dossier](backlog/<id>-<slug>.md)``, resolves from ``sdd/``,
      and the dossier's first ``# `` heading opens with the item's ID.

    **Scope.** R2, R3 and R4 run on every section. ADR-0040 scoped R2 and R3
    to migrated sections through an opt-out marker; ADR-0041 retired it once
    every section was converted, so no line can exempt a section.
    **Bounds:** R4 checks link and ID, not that index and dossier agree
    (``BACKLOG.md`` § Item authority states that bound); a dossier no item
    links is not detected.

Remote mode (--check --remote), ID-257:
    Opt-in, never in ``lint``: it needs the network, and the offline gate must
    stay pure. Fetches every ``origin`` branch under an explicit refspec (a
    ``--depth`` or ``--single-branch`` clone would otherwise fetch master
    alone), then compares the items this working tree minted — its headers
    minus those at the merge-base with ``origin/master``, so an uncommitted
    mint counts — with ``origin/master`` and with what each other ``origin/*``
    branch gained since its merge-base with ``HEAD`` and that ``origin/master``
    does not already carry, open or done. So once this tree's item has landed,
    a rival branch's mint of the same ID is that branch's to re-mint: its own
    ``--remote`` run reports the clash with master, and this one passes. **A clash
    is one ID under two headers**, compared as the text after the ``- [?] ``
    checkbox. One item keeps that text wherever it travels (a merge, a squash
    merge, this session's own push from any checkout, a close on one side), so
    it never reads as two; a rival mint names something else. Fails naming
    each clashing ID and the ref carrying it, and prints the next safe IDs
    across every pushed branch. A failed fetch fails loud rather than reporting
    agreement. ``TestRemote`` enumerates the one-item space (whose item,
    whether and how master took it, attached or detached ``HEAD``).
    **Bounds:** a branch not yet pushed, or pushed to a fork, is invisible —
    at mint time that is the usual state of a parallel session, which is why a
    reservation and not this mode is the minting rule; a stale or abandoned
    branch still carrying an ID can report a clash nobody will merge; two mints
    that happen to share header text read as one item; and an item whose header
    changes on one side after the other side took it — retitled, or absorbed
    and given its ``→ **HOST**`` — reads as two. Every ``Drift-gate::``
    block below carries an ``entrypoint:``, so the inventory gives the
    ``--check --remote`` block only the passthrough ``gen-backlogid`` alias as
    a home and derives it ``advisory``; without entrypoints it would inherit
    the offline ``--check``'s homes and read as gating in ``lint``.

Drift-gate::

    entrypoint: --check
    kind:       pair
    compares: the max ID per prefix in sdd/BACKLOG-DONE.md ↔ sdd/backlogid.json, and the open IDs in
        sdd/BACKLOG.md against both
    domain:     process

Drift-gate::

    entrypoint: --check
    kind:       rule
    rule: no ID appears on two open item headers in sdd/BACKLOG.md, nor on two done
        headers in sdd/BACKLOG-DONE.md when one sits above released history
    domain:     process

Drift-gate::

    entrypoint: --check
    kind:       pair
    compares: each open item's audience values in sdd/BACKLOG.md ↔ the audience
        enum in sdd/traces/_schema.yml, which governs (R1; effort against S/M/L)
    domain:     process

Drift-gate::

    entrypoint: --check
    kind:       rule
    rule: in each sdd/BACKLOG.md section, an item is at most
        eight content lines with a diagnosis of at most five (R2), and the preamble is one
        Promise paragraph of at most three sentences (R3)
    domain:     process

Drift-gate::

    entrypoint: --check
    kind:       pair
    compares: each open item's Detail link and ID in sdd/BACKLOG.md ↔ the dossier file under
        sdd/backlog/ and its header ID; the item governs (R4)
    domain:     process

Drift-gate::

    entrypoint: --check --remote
    kind:       pair
    compares: the IDs this working tree minted ↔ the same IDs under other headers on origin/master
        and every other pushed origin branch
    domain:     process
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _trace_corpus import load_trace

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "sdd" / "BACKLOG.md"
BACKLOG_DONE = ROOT / "sdd" / "BACKLOG-DONE.md"
ID_FILE = ROOT / "sdd" / "backlogid.json"

TRACE_SCHEMA = ROOT / "sdd" / "traces" / "_schema.yml"

_PREFIXES = ("BK", "BUG", "ID", "AF", "BL")
_HEADER_RE = re.compile(
    r"^- \[(.)\] \*\*(" + "|".join(_PREFIXES) + r")-(\d+[a-z]*)(?:\s+\([^)]+\))? —",
    re.MULTILINE,
)
_ATTR_RE = re.compile(r"^  spec: .+ · effort: (.+?) · audience: (.+)$")
_EFFORTS = ("S", "M", "L")
# BK-385: the done register's released history starts at the first version heading.
_RELEASED_RE = re.compile(r"^## v\d", re.MULTILINE)

# R2–R4. Separator lines are not content (RFC-0016 D1); rfc-0016-measure.py
# uses the same delimitation, so the gate and the acceptance figure agree.
_SEP_RE = re.compile(r'^(\s*|---|<a id="[^"]+"></a>)$')
_RULES_ANCHOR = '<a id="how-this-file-works"></a>'
_DETAIL_RE = re.compile(r"^  Detail: \[dossier\]\((backlog/[^)\s]+\.md)\)$")
_DOSSIER_ID_RE = re.compile(r"^# ([A-Z]+-\d+[a-z]*) —")
_ITEM_CAP, _DIAGNOSIS_CAP, _PROMISE_CAP = 8, 5, 3
# A sentence ends at . ! or ? (optionally closed by a backtick, bold or bracket)
# followed by whitespace and a capital-ish opener; "e.g. this" does not split,
# and neither does a lowercase or digit opener (the docstring's fail-open bound).
_SENTENCE_END_RE = re.compile(r"[.!?][`*)\"']*\s+(?=[A-Z`*(\[\"])")


def _extract_ids(text: str, status_chars: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {p: set() for p in _PREFIXES}
    for m in _HEADER_RE.finditer(text):
        status, prefix, num = m.group(1), m.group(2), m.group(3)
        if status in status_chars:
            result[prefix].add(f"{prefix}-{num}")
    return result


def _duplicate_ids(text: str, status_chars: str) -> dict[str, int]:
    """IDs whose header appears more than once in one file, with their count.

    Separate from ``_extract_ids`` rather than a widening of it. That function
    returns ``dict[str, set[str]]`` and ``check_backlog_ids_vs_base.py`` imports
    it for set arithmetic against the base — a guard test pins the import to
    this module — so changing its return type to carry multiplicity would
    rewrite a second gate to fix this one. Two functions over one
    ``_HEADER_RE`` keeps the grammar single-homed, which is the property that
    mattered.

    Keyed on the whole ``PREFIX-NNN[a-z]*`` token, so ``BK-139a`` and
    ``BK-139b`` are two items rather than one item twice. Keying on the numeric
    part would fail every split item, which is the shape this check must not
    touch.
    """
    counts: Counter[str] = Counter()
    for m in _HEADER_RE.finditer(text):
        status, prefix, num = m.group(1), m.group(2), m.group(3)
        if status in status_chars:
            counts[f"{prefix}-{num}"] += 1
    return {item: n for item, n in counts.items() if n > 1}


def _done_duplicate_ids(done_text: str) -> dict[str, int]:
    """BK-385: IDs on two or more done headers, at least one above released history.

    Released history (from the first ``## v<digit>`` heading down) is frozen,
    so a pair lying wholly inside it is tolerated: those are the pairs from
    before the ID discipline. Every new close lands above that line first, so
    one live header is enough to report the pair, including a new close that
    reuses a released ID.
    """
    released = _RELEASED_RE.search(done_text)
    live_text = done_text[: released.start()] if released else done_text
    live = {item for ids in _extract_ids(live_text, "x").values() for item in ids}
    return {item: n for item, n in _duplicate_ids(done_text, "x").items() if item in live}


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)


def _headed(open_text: str, done_text: str) -> dict[str, str]:
    """Every header ID in one tree's pair of backlog files, open or done, with its header text.

    The text after the ``- [?] `` checkbox is what makes an item *one* item
    across trees: a squash merge carries it verbatim with no shared commit, and
    one item's open and done headers differ only in the box, while a rival
    mint of the same ID names something else. Nothing is parsed out of it:
    three rounds of review each refuted a rule for where a title ends.
    """
    found: dict[str, str] = {}
    for text, status in ((open_text, " ~"), (done_text, "x")):
        for m in _HEADER_RE.finditer(text):
            if m.group(1) in status:
                eol = text.find("\n", m.start())
                found[f"{m.group(2)}-{m.group(3)}"] = text[m.start() + 6 : eol if eol != -1 else None].rstrip()
    return found


def _remote_view(remote: str = "origin", base: str = "master") -> tuple[dict[str, list[str]], set[str]]:
    """ID-257: this tree's new items against every pushed branch. Raises ``RuntimeError``.

    Returns ``(clashes, seen)``: each ID this tree minted that another ref
    carries **under different header text**, with those refs, and every ID on
    the base or any pushed branch. "Minted here" is the working tree minus the
    merge-base with the base, so an uncommitted mint counts. Comparing header
    text rather than commits is what keeps one item, reached by squash merge
    or a push from another checkout, from reading as two.
    """
    # An explicit refspec: a clone made with `--depth`/`--single-branch` would
    # otherwise fetch master alone, and every other branch would be unseen.
    fetch = _git("fetch", "--quiet", "--prune", remote, f"+refs/heads/*:refs/remotes/{remote}/*")
    if fetch.returncode:
        raise RuntimeError(fetch.stderr.strip() or f"git fetch {remote} exited {fetch.returncode}")
    base_ref = f"{remote}/{base}"
    fork = _git("merge-base", "HEAD", base_ref)
    if fork.returncode:
        raise RuntimeError(f"no merge-base between HEAD and {base_ref}")
    paths = [p.relative_to(ROOT).as_posix() for p in (BACKLOG, BACKLOG_DONE)]

    def items_at(ref: str) -> dict[str, str]:
        open_text, done_text = (_git("show", f"{ref}:{p}").stdout for p in paths)
        return _headed(open_text, done_text)

    tree = _headed(BACKLOG.read_text(encoding="utf-8"), BACKLOG_DONE.read_text(encoding="utf-8"))
    forked = items_at(fork.stdout.strip())
    mine = {item: header for item, header in tree.items() if item not in forked}
    clashes: dict[str, list[str]] = defaultdict(list)

    def compare(ref: str, theirs: dict[str, str]) -> None:
        for item in sorted(mine.keys() & theirs.keys()):
            if theirs[item] != mine[item]:
                clashes[item].append(ref)

    base_items = items_at(base_ref)
    compare(base_ref, base_items)
    # `origin/HEAD` lists as bare `origin` under `refname:short`.
    skip = {base_ref, f"{remote}/HEAD", remote}
    refs = _git("for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}").stdout.split()
    seen = set(base_items)
    for ref in refs:
        if ref in skip:
            continue
        ref_items = items_at(ref)
        seen |= ref_items.keys()
        # What the ref gained since it diverged from HEAD, minus whatever the
        # base tip carries: an old item whose header changed on either side is
        # not a new mint, and an ID already on master is checked against master.
        shared = _git("merge-base", "HEAD", ref)
        old = items_at(shared.stdout.strip()).keys() if shared.returncode == 0 else set()
        compare(ref, {k: v for k, v in ref_items.items() if k not in base_items and k not in old})
    return dict(clashes), seen


def _audience_enum() -> set[str]:
    """The trace schema's audience enum: one vocabulary for traces and items."""
    schema = load_trace(TRACE_SCHEMA.read_text(encoding="utf-8"))
    return set(schema["properties"]["audience"]["items"]["enum"])


def _attribute_violations(text: str, audiences: set[str]) -> list[str]:
    """R1: each open item's next line is its attribute line, with legal values.

    Open items only (``[ ]``/``[~]``); ``BACKLOG-DONE.md`` entries carry no
    attribute line. A missing line is a violation, else it would bypass the rule.
    """
    lines = text.split("\n")
    found: list[str] = []
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if not m or m.group(1) not in " ~":
            continue
        item = f"{m.group(2)}-{m.group(3)}"
        where = f"line {i + 2}: {item}"
        attr = _ATTR_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
        if attr is None:
            found.append(f"{where}: no attribute line (`  spec: … · effort: … · audience: …`)")
            continue
        effort, audience = attr.group(1), attr.group(2)
        if effort not in _EFFORTS:
            found.append(f"{where}: effort {effort!r} not in {'/'.join(_EFFORTS)}")
        found.extend(
            f"{where}: audience {a!r} not in {TRACE_SCHEMA.name}'s enum"
            for a in (x.strip() for x in audience.split(","))
            if a not in audiences
        )
    return found


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """Each backlog section as ``(title, heading index, end index)``.

    The rules header (the heading under ``_RULES_ANCHOR``) is not a section.
    ``end`` is exclusive and pulled back over separators, so a section's
    trailing ``---`` and the next anchor belong to the next section.
    """
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    out = []
    for k, h in enumerate(heads):
        if h > 0 and lines[h - 1] == _RULES_ANCHOR:
            continue
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        while end > h + 1 and _SEP_RE.match(lines[end - 1]):
            end -= 1
        out.append((lines[h][3:], h, end))
    return out


def _items(lines: list[str], start: int, end: int) -> list[tuple[str, int, int]]:
    """Items in ``lines[start:end]`` as ``(ID, header index, last content index)``."""
    heads = [j for j in range(start, end) if _HEADER_RE.match(lines[j])]
    out = []
    for a, b in zip(heads, [*heads[1:], end][: len(heads)], strict=True):
        last = b - 1
        while last > a and _SEP_RE.match(lines[last]):
            last -= 1
        m = _HEADER_RE.match(lines[a])
        assert m is not None  # heads holds only matching lines
        out.append((f"{m.group(2)}-{m.group(3)}", a, last))
    return out


def _shape_violations(text: str, base: Path) -> tuple[list[str], list[str], list[str]]:
    """R2 item cap, R3 section shape, R4 dossier link, as three lists, over every section (ADR-0041)."""
    lines = text.split("\n")
    caps: list[str] = []
    shapes: list[str] = []
    links: list[str] = []
    for title, h, end in _sections(lines):
        items = _items(lines, h + 1, end)
        shapes.extend(_section_shape(title, lines[h + 1 : items[0][1] if items else end]))
        for item, a, last in items:
            detail = _DETAIL_RE.match(lines[last]) is not None
            n = last - a + 1
            diagnosis = n - 2 - detail
            if n > _ITEM_CAP:
                caps.append(f"line {a + 1}: {item}: {n} content lines (cap {_ITEM_CAP})")
            elif diagnosis > _DIAGNOSIS_CAP:
                caps.append(f"line {a + 1}: {item}: diagnosis {diagnosis} lines (cap {_DIAGNOSIS_CAP})")
            for j in range(a + 1, last + 1):
                if lines[j].startswith("  Detail:"):
                    links.extend(f"line {j + 1}: {item}: {v}" for v in _dossier_link(item, lines[j], base))
    return caps, shapes, links


def _section_shape(title: str, preamble: list[str]) -> list[str]:
    """R3: heading, optional anchor, one ``**Promise:**`` paragraph of ≤ 3 sentences."""
    paragraphs: list[list[str]] = [[]]
    for line in preamble:
        if not line.strip():
            paragraphs.append([])
        elif not _SEP_RE.match(line):
            paragraphs[-1].append(line)
    paragraphs = [p for p in paragraphs if p]
    found = []
    if len(paragraphs) != 1:
        found.append(f"{title}: preamble has {len(paragraphs)} paragraphs (one Promise paragraph only)")
    if not paragraphs or not paragraphs[0][0].startswith("**Promise:**"):
        found.append(f"{title}: preamble does not open with **Promise:**")
        return found
    sentences = len(_SENTENCE_END_RE.findall(" ".join(paragraphs[0]).strip())) + 1
    if sentences > _PROMISE_CAP:
        found.append(f"{title}: Promise has {sentences} sentences (cap {_PROMISE_CAP})")
    return found


def _dossier_link(item: str, line: str, base: Path) -> list[str]:
    """R4: the link has D2's shape, resolves, and the dossier is named and headed for ``item``."""
    m = _DETAIL_RE.match(line)
    if m is None:
        return ["Detail: line is not `Detail: [dossier](backlog/<id>-<slug>.md)`"]
    rel = m.group(1)
    path = base / rel
    if not path.is_file():
        return [f"Detail: {rel} does not resolve"]
    found = []
    if not path.name.startswith(f"{item.lower()}-"):
        found.append(f"dossier path {rel} is not named {item.lower()}-<slug>.md")
    first = next((x for x in path.read_text(encoding="utf-8").split("\n") if x.startswith("# ")), "")
    head = _DOSSIER_ID_RE.match(first)
    if head is None or head.group(1) != item:
        found.append(f"dossier {rel} is headed {head.group(1) if head else 'with no ID'}")
    return found


def _max_numeric(ids: set[str]) -> int:
    best = 0
    for item in ids:
        m = re.search(r"\d+", item.split("-", 1)[1])
        if m:
            best = max(best, int(m.group()))
    return best


def _generate() -> int:
    done_ids = _extract_ids(BACKLOG_DONE.read_text(encoding="utf-8"), "x")
    max_done = {p: _max_numeric(done_ids[p]) for p in _PREFIXES}
    # newline="\n": force LF; text-mode write on Windows emits CRLF and churns the eol=lf JSON.
    ID_FILE.write_text(json.dumps(max_done, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Updated {ID_FILE.relative_to(ROOT)}")
    return 0


def _check(remote: bool = False) -> int:
    done_text = BACKLOG_DONE.read_text(encoding="utf-8")
    active_text = BACKLOG.read_text(encoding="utf-8")

    done_ids = _extract_ids(done_text, "x")
    active_ids = _extract_ids(active_text, " ~")

    actual_max = {p: _max_numeric(done_ids[p]) for p in _PREFIXES}

    try:
        stored = json.loads(ID_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: {ID_FILE.relative_to(ROOT)} not found. Run: hatch run gen-backlogid")
        return 1

    stale = [p for p in _PREFIXES if stored.get(p) != actual_max[p]]
    if stale:
        for p in stale:
            print(f"STALE: {p}: stored={stored.get(p)}, actual={actual_max[p]}")
        print("Run: hatch run gen-backlogid")
        return 1

    collisions = sorted(item for p in _PREFIXES for item in active_ids[p] & done_ids[p])
    duplicates = _duplicate_ids(active_text, " ~")
    done_duplicates = _done_duplicate_ids(done_text)
    attributes = _attribute_violations(active_text, _audience_enum())
    caps, shapes, links = _shape_violations(active_text, BACKLOG.parent)

    max_active = {p: _max_numeric(active_ids[p]) for p in _PREFIXES}
    next_ids = {p: max(actual_max[p], max_active[p]) + 1 for p in _PREFIXES}
    next_str = "  ".join(f"{p}={next_ids[p]}" for p in _PREFIXES)
    print(f"Next safe IDs (this tree only; parallel sessions mint from a reservation): {next_str}")

    clashes: dict[str, list[str]] = {}
    if remote:
        try:
            clashes, seen = _remote_view()
        except RuntimeError as exc:
            print(f"ERROR: --remote could not fetch origin or read its refs, so nothing was compared: {exc}")
            return 1
        by_prefix = {p: {item for item in seen if item.startswith(f"{p}-")} for p in _PREFIXES}
        floor = {p: max(next_ids[p], _max_numeric(by_prefix[p]) + 1) for p in _PREFIXES}
        print("Next safe IDs across pushed branches: " + "  ".join(f"{p}={floor[p]}" for p in _PREFIXES))

    # Both failures are reported before returning, rather than the first one
    # short-circuiting: an author who fixes a duplicate only to be told about a
    # collision on the next run pays two cycles for one read of the file.
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicate ID(s) — one ID on two open items in {BACKLOG.name}:")
        for item, count in sorted(duplicates.items()):
            print(f"  {item} ({count} headers)")
        print(
            "\nTwo branches minted the same ID before either merged (ID-257). Renumber the "
            "later-merged item to the next safe ID above, and sweep every reference to it."
        )

    if collisions:
        print(f"\nFound {len(collisions)} collision(s) — same ID active and done:")
        for c in collisions:
            print(f"  {c}")
        print("\nAssign a new ID to the active item (the next safe ID above).")

    if done_duplicates:
        print(
            f"\nFound {len(done_duplicates)} duplicate ID(s) in {BACKLOG_DONE.name} — "
            "one ID on two entries, at least one above released history (BK-385):"
        )
        for item, count in sorted(done_duplicates.items()):
            print(f"  {item} ({count} headers)")
        print("\nRenumber the later-merged entry to the next safe ID above, and sweep every reference to it.")

    if clashes:
        print(f"\nFound {len(clashes)} ID(s) this tree minted that a pushed ref carries under another header (ID-257):")
        for item, refs in sorted(clashes.items()):
            print(f"  {item} also minted on {', '.join(refs)}")
        print("\nRe-mint from the floor across pushed branches above, before either side merges.")

    if attributes:
        print(f"\nFound {len(attributes)} attribute violation(s) in {BACKLOG.name} (R1, ADR-0040):")
        for v in attributes:
            print(f"  {v}")

    for found, rule in (
        (caps, "item(s) over the cap (R2)"),
        (shapes, "section shape violation(s) (R3)"),
        (links, "dossier link violation(s) (R4)"),
    ):
        if found:
            print(f"\nFound {len(found)} {rule} in {BACKLOG.name}, ADR-0040:")
            for v in found:
                print(f"  {v}")

    if duplicates or done_duplicates or collisions or clashes or attributes or caps or shapes or links:
        return 1

    # Every rule named, so a clean run says which ones passed. The duplicate
    # rules are only reachable after two branches merge, so this line is the
    # first evidence most authors will have that they exist at all.
    print(
        "No ID collisions, no ID on two open items or on two done entries with one above released history, "
        + ("no ID this tree minted under another header on a pushed branch, " if remote else "")
        + "every open item's attributes in vocabulary, "
        "every section and its items in shape, and every Detail: link resolving to its dossier."
    )
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--remote" in args and "--check" not in args:
        print("ERROR: --remote is a mode of --check: run gen_backlogid.py --check --remote")
        return 1
    if "--check" in args:
        return _check(remote="--remote" in args)
    return _generate()


if __name__ == "__main__":
    raise SystemExit(main())
