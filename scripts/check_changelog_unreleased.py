"""Gate: the CHANGELOG ``[Unreleased]`` section says one thing per item, once.

Three properties of that section were stated as rules and checked by nobody,
and the first of them failed on master: ``BK-355`` and ``BK-354`` each appeared
twice, the lower copy of each being pre-amendment wording, so the section
stated both that one spec records a single exception and that it "still records
two", and called an item open two lines below the entry that closed it. A merge
conflict where one side is a revision of the other is not a keep-both, and the
CHANGELOG commit immediately before it records a reviewer catching the
identical resolution by hand. Found once by attention, missed by the next
merge.

``scripts/check_breaking_migration_link.py`` (BUG-262) parses the same section,
and is the only other thing that does: every remaining ``CHANGELOG`` mention in
``scripts/`` is a link or render concern, and ``ci.yml`` names it only inside
``DOCS_PAT``. That gate asks whether a **Breaking** entry links its upgrade
path; this one asks whether the section's entries exist once each and cover the
completed items. Neither asserts the other's claim, but they share a grammar —
see ``_ENTRY_RE``, which is spelled to agree with its counterpart there.

The three rules
===============

1. **Unique.** One entry per item ID. A second entry for an ID is a failure
   naming both lines.
2. **A stub, not a section.** Every non-blank line in the section is an entry
   matching ``- <ID>: <text>``, and no entry exceeds ``_MAX_ENTRY_CHARS``
   characters **of prose** — Markdown link targets are discounted, because a
   URL's length is a property of the docs site rather than a choice the author
   made, and counting it priced a breaking entry out of linking to the
   migration section it owes.
   Length is the machine-decidable half of "one-line stub": each entry is
   already one physical line, so a line-count rule would pass on a 4,910
   character paragraph, and paragraphs are what hid the duplicate — at one
   line each two copies are unmissable, at 2.3 kB each they sat four lines
   apart unseen. The budget is justified by what the section is *for* — a
   scannable index of what shipped, which is what makes a duplicate visible —
   and deliberately not by "the release re-expands this prose anyway": that
   premise is exactly what ID-253 files as unbacked, since ``CONTRIBUTING.md``
   Phase 1 names no source for the expanded prose and the release skill has no
   expansion step.
3. **The audience rule.** Every item under ``BACKLOG-DONE.md`` § Unreleased
   whose ``audience`` carries a ``user.*`` tag has an entry. This is the
   direction ``CONTRIBUTING.md`` § Release Phase 1 already runs, and the only
   one that governs — see the authority note below.

Authority (Rule 4)
==================

The two sets are not required to be equal, and declaring which side governs is
what makes this checkable at all. **The completed-item side governs**: a
user-facing completed item without an entry is a failure. An entry with no
completed item is **not failed**, because two legitimate cases produce one — an
item still open in ``BACKLOG.md`` that shipped one bullet (the live instance at
the time of writing had an entry and no ``BACKLOG-DONE.md`` counterpart for
exactly that reason), and the trace schema's own escape clause, under which a
``contributor.process`` change that introduces a user-facing framework earns an
entry without a ``user.*`` tag. Failing those would make the gate wrong about
the repo rather than the repo wrong about itself.

The first of those is *registered* rather than merely tolerated: an entry whose
ID is open in ``BACKLOG.md`` is silent, and only an ID the backlog knows nowhere
draws a note. See the Bounds list.

Bounds (Rule 7)
===============

* It keys on the **ID at line start**. So it catches a duplicated entry and
  cannot catch a single entry whose *content* went stale — the wider defect
  the recurrence's own commit message describes. It says nothing about whether
  a title is right, only that there is exactly one.
* Length is a proxy for shape. A 300-character entry that reads as a paragraph
  passes; a terse entry that happens to run long fails. The budget is a
  ceiling on prose, not a definition of a good stub.
* It reads the ``[Unreleased]`` heading only. Released sections carry
  ``### Added`` groupings and condensed prose by design, and none of the three
  rules applies to them.
* **It stands down inside the release window, loudly.** ``CONTRIBUTING.md``
  § Release Phase 1 condenses ``[Unreleased]`` into that same released shape
  *in place*, and Phase 2 is what renames the heading — so from Phase 1 until
  Phase 2 the released shape lives under ``[Unreleased]``, and Phase 3 runs
  ``hatch run all`` over it. All three rules key on ``- <ID>:`` lines, which
  that shape does not have: run anyway, this gate reported every condensed
  line as a stray and every completed item as entry-less, and its remediation
  told the release manager to do Phase 2 early. It now detects a ``###``
  grouping in the section and reports the window instead of failing, which is
  the same survival ``check_breaking_migration_link.py`` gets by reporting a
  count. The cost is that a stray ``###`` mid-cycle disables all three rules —
  so the stand-down prints on every run, including green ones, rather than
  being inferred from silence.
* The audience rule reaches exactly as far as the ``audience:`` lines under
  ``BACKLOG-DONE.md`` § Unreleased. An item whose line is missing is reported
  as unevaluable rather than passed.
* The advisory half is **registered, not chatty**. An entry whose ID is a live
  open item in ``sdd/BACKLOG.md`` is a tolerated divergence with an owner and a
  rationale already — the item — so it is silent
  ([Rule 6](../sdd/DRIFT-RULES.md#tolerated)); a note that printed on every
  green run until that item closed would teach readers to skip a passing gate's
  output. Only an ID the backlog knows nowhere is reported. The cost is that a
  *wrong* ID that happens to match some other open item passes silently.
* Completed means ``[x]``, matching ``BACKLOG-DONE.md``'s own preamble and
  ``gen_backlogid.py``. A ``[ ]`` or ``[~]`` bullet under § Unreleased is not a
  completed item, and whether it belongs in that file at all is ID-235's. It is
  still an **input**, not something outside this gate: it ends the item above
  it. Reading only ``[x]`` bullets as boundaries meant a ``[~]`` item's
  ``audience:`` line was credited to the completed item above — which both
  silenced the "no ``audience:`` line" finding for that item and reported it
  against tags it does not carry.
* Neither half may fail **silently**. A ``BACKLOG-DONE.md`` with no
  ``## Unreleased`` heading once made the audience rule evaluate an empty set
  while this gate printed success, and Phase 2 renames that exact heading. It
  now raises ``DerivationError`` and exits 1: a check that can fail silently is
  worse than none, because it is trusted.

Exit codes
==========

* ``0`` — the section is unique, stub-shaped, and covers every completed
  user-facing item; or the release window is open and the gate stood down.
  Notes may still be printed, and the stand-down always is.
* ``1`` — one line per violation to stderr, plus remediation.

Drift-gate::

    kind:       pair
    compares: the CHANGELOG [Unreleased] entries ↔ the completed items under
        sdd/BACKLOG-DONE.md § Unreleased, with sdd/BACKLOG.md read as the
        register that decides which unmatched entries are tolerated
    domain:     process

Drift-gate::

    kind:       rule
    rule: every line under CHANGELOG [Unreleased] is a `- <ID>: <text>` stub,
        one per ID, within the prose budget
    domain:     process
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHANGELOG = _REPO_ROOT / "CHANGELOG.md"

# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

_UNRELEASED = "## [Unreleased]"

# A released section's heading, e.g. `## [0.30.0] - 2026-07-19`. Any `## [`
# after the Unreleased heading closes the section.
_SECTION_RE = re.compile(r"^## \[")

# The entry grammar. The ID must lead the line: keying on it is what makes a
# duplicate detectable, and what bounds this gate to entry identity rather
# than entry content.
#
# The prefix class is `[A-Z][A-Z0-9-]*`, spelled to equal
# `check_breaking_migration_link.py`'s `_ENTRY_RE`, the only other parser of
# this section. It was `[A-Z]+`, which excluded the compound form that gate
# admits: `- SQL-BLOB-020: ...` was a valid entry there and a stray line here,
# so one `hatch run lint` returned two verdicts about one line — the failure
# mode the comment below says this module exists to avoid one level up. The
# wider class is the safe direction of the two: it fails open on a prefix
# neither gate has seen, where the narrow one failed a legitimate entry.
#
# No `text` group: this gate keys on identity and length, never on entry
# content. A parsed-but-unread field is what the `prose_length` docstring
# records deleting once already.
_ENTRY_RE = re.compile(r"^- (?P<id>[A-Z][A-Z0-9-]*-\d+[a-z]*): .*$")

# An inline Markdown link. Used to discount the target when measuring an
# entry against the stub budget — see `Entry.prose_length`.
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


class DerivationError(RuntimeError):
    """A half of a claim could not be derived. Never treated as a pass.

    ``parse_done_unreleased`` used to return ``[]`` both for "no completed
    items" and for "this file has no ``## Unreleased`` heading", so a renamed
    heading made the audience rule evaluate nothing while the gate printed
    success. Phase 2 renames that exact heading, so the silent case was on the
    release path. A check that can fail silently is worse than none, because it
    is trusted.
    """


@dataclass(frozen=True)
class Entry:
    """One ``[Unreleased]`` entry."""

    item_id: str
    line: int  # 1-indexed line in CHANGELOG.md
    raw: str

    @property
    def prose_length(self) -> int:
        """Characters in the entry line, with Markdown link targets discounted.

        This is the only length the budget is spelled in. A raw ``len(raw)``
        property was carried alongside it for one commit, read by nothing, and
        left the next reader two lengths to choose between.

        A budget on entry length exists to stop prose, and a URL is not prose:
        its length is a property of the docs site, not a choice the author
        made. Counting it would price a stub out of linking to the migration
        section its own breaking change owes — which is exactly what happened,
        two of four breaking entries busting the budget on a link alone.

        ``[text](url)`` therefore counts as ``text``. The link markup and the
        target are discounted; everything the reader actually reads is counted.
        """
        return len(_LINK_RE.sub(r"\1", self.raw))


@dataclass(frozen=True)
class Section:
    """The parsed ``[Unreleased]`` section."""

    entries: list[Entry]
    # Lines inside the section that are neither blank nor an entry. A
    # continuation line of a wrapped entry and a stray sub-heading both land
    # here, which is deliberate: both break the one-entry-per-line grammar the
    # duplicate check keys on.
    stray: list[tuple[int, str]]
    found: bool
    # A `### ` grouping inside the section: the shape Phase 1 condenses into
    # and Phase 2 renames. See the release-window bound in the module
    # docstring — this is what makes the gate survive its own release.
    grouped: bool = False


def parse_unreleased(changelog: Path = _CHANGELOG) -> Section:
    """Parse the ``[Unreleased]`` section of *changelog*.

    A missing *heading* returns ``found=False`` rather than raising, so a caller
    can report it as the failure it is instead of dying inside the parser. An
    unreadable *file* raises ``DerivationError``, because the two are different
    failures and reporting one as the other sent the reader to Phase 2 to look
    for a renamed heading in a file that was not there.
    """
    try:
        lines = changelog.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        raise DerivationError(f"cannot read {changelog}: {exc}") from exc

    try:
        start = lines.index(_UNRELEASED)
    except ValueError:
        return Section(entries=[], stray=[], found=False)

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _SECTION_RE.match(lines[i]):
            end = i
            break

    entries: list[Entry] = []
    stray: list[tuple[int, str]] = []
    grouped = False
    for i in range(start + 1, end):
        line = lines[i]
        if not line.strip():
            continue
        if line.startswith("### "):
            grouped = True
        m = _ENTRY_RE.match(line)
        if m:
            entries.append(Entry(item_id=m.group("id"), line=i + 1, raw=line))
        else:
            stray.append((i + 1, line))
    return Section(entries=entries, stray=stray, found=True, grouped=grouped)


@dataclass(frozen=True)
class DoneItem:
    """One item under ``BACKLOG-DONE.md`` § Unreleased."""

    item_id: str
    audience: tuple[str, ...]
    line: int

    @property
    def is_user_facing(self) -> bool:
        """True when any audience tag starts with ``user.``.

        The schema's predicate, not a substring search: ``sdd/traces/_schema.yml``
        defines the CHANGELOG-required rule as "any entry in ``audience`` starts
        with ``user.``". Testing for the literal ``user.api`` would silently drop
        the items whose only user tag is ``user.site`` or
        ``user.discoverability.llm``.
        """
        return any(tag.startswith("user.") for tag in self.audience)


# Completed means `[x]`, and only `[x]`. `BACKLOG-DONE.md`'s own preamble says
# "All items must use `[x]` status", and `gen_backlogid.py` reads the same file
# with the same rule — two parsers over one artifact disagreeing about what
# counts is the defect this module exists to avoid one level up. A `[ ]` or
# `[~]` bullet under § Unreleased is therefore not a completed item here, and
# the audience rule says nothing about it; that gap belongs to the backlog
# structural lint (ID-235), which checks this file's shape.
#
# The suffix and parenthetical match `gen_backlogid.py`; the prefix class is
# deliberately wider. IDs here may carry a letter suffix (`BK-139d`, `ID-118b`,
# `ID-013b` are live) and a bullet may read `**BK-167b (partial) — ...`.
# Spelling the ID `[A-Z]+-\d+` looked right and was wrong three times over — it
# failed a legitimate suffixed stub as a stray line; with no anchor after the
# digits it silently truncated `BK-139a` to `BK-139` here; and its prefix class
# disagreed with the sibling gate over the same section (see `_ENTRY_RE`).
# `gen_backlogid.py` spells the prefix as the closed set `(BK|BUG|ID|AF|BL)`
# because it *allocates* IDs and may not invent a prefix; these patterns
# *recognise* them, where a closed set fails a legitimate line. The trailing
# ` —` is the anchor that makes the truncation impossible.
_ITEM_RE = re.compile(r"^- \[x\] \*\*(?P<id>[A-Z][A-Z0-9-]*-\d+[a-z]*)(?:\s+\([^)]+\))? —")
# Any status bullet, `[x]` or not. `_ITEM_RE` decides what is a *completed
# item*; this decides where one *ends*. Conflating the two credited a `[~]`
# item's `audience:` line to the completed item above it: the finding that item
# was owed ("carries no `audience:` line") was silenced, and a violation was
# reported against tags it does not carry. A boundary and a selection are
# different questions over one file, and one pattern cannot answer both.
_ANY_ITEM_RE = re.compile(r"^- \[[x ~]\] \*\*")
# Anchored to the metadata line, not searched for anywhere in the body.
# `search` over the whole line meant an item with *no* metadata line whose
# body prose contains the word — these bodies argue about audience
# routinely — was handed whatever that sentence parsed to, and escaped the
# rule silently if none of it began with `user.`. The docstring credited
# "only the first match" with preventing that; what prevented it was a
# convention, and a convention is not a guard.
_AUDIENCE_RE = re.compile(r"^\s*(?:spec:.*?·\s*)?(?:effort:.*?·\s*)?audience:\s*(?P<tags>.+?)\s*$")


def parse_done_unreleased(backlog_done: Path) -> list[DoneItem]:
    """Items under ``BACKLOG-DONE.md`` § ``Unreleased``, with their audience tags.

    The audience line belongs to the item whose bullet most recently opened, so
    a body paragraph that happens to contain the word is not mistaken for one:
    only the first ``audience:`` after a bullet is taken. An item whose bullet
    is followed by the next bullet with no ``audience:`` in between is returned
    with an empty tuple rather than dropped — an item the rule cannot be
    evaluated for is a finding, not a silent pass.

    "The next bullet" means any status bullet (``_ANY_ITEM_RE``), not the next
    ``[x]`` one. See that pattern's comment: the two questions look like one
    and are not.
    """
    try:
        lines = backlog_done.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        raise DerivationError(f"cannot read {backlog_done}: {exc}") from exc

    try:
        start = lines.index("## Unreleased")
    except ValueError:
        raise DerivationError(
            f"{backlog_done}: no `## Unreleased` heading, so the completed-item side of the "
            f"audience rule cannot be derived. Phase 2 renames this heading and adds a fresh "
            f"empty one; if that is what happened, the empty one is missing"
        ) from None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    items: list[DoneItem] = []
    pending_id: str | None = None
    pending_line = 0

    def flush() -> None:
        nonlocal pending_id
        if pending_id is not None:
            items.append(DoneItem(item_id=pending_id, audience=(), line=pending_line))
            pending_id = None

    for i in range(start + 1, end):
        m = _ITEM_RE.match(lines[i])
        if m:
            flush()
            pending_id = m.group("id")
            pending_line = i + 1
            continue
        if _ANY_ITEM_RE.match(lines[i]):
            # A `[ ]` or `[~]` bullet: not an item this gate evaluates, but it
            # closes the one above, whose metadata lines cannot appear below it.
            flush()
            continue
        if pending_id is None:
            continue
        a = _AUDIENCE_RE.search(lines[i])
        if a:
            tags = tuple(t.strip() for t in re.split(r"[,·]", a.group("tags")) if t.strip())
            items.append(DoneItem(item_id=pending_id, audience=tags, line=pending_line))
            pending_id = None
    flush()
    return items


_OPEN_ITEM_RE = re.compile(r"^- \[[ ~]\] \*\*(?P<id>[A-Z][A-Z0-9-]*-\d+[a-z]*)(?:\s+\([^)]+\))? —")


def open_item_ids(backlog: Path) -> set[str]:
    """IDs of items still open in ``BACKLOG.md`` (`[ ]` or `[~]`).

    This is the **register** behind the audience rule's advisory half
    ([`DRIFT-RULES.md` Rule 6](../sdd/DRIFT-RULES.md#tolerated)): an
    ``[Unreleased]`` entry whose ID is a live open item is a *tolerated*
    divergence with an owner and a rationale already — the item itself — and
    saying so on every green run is how a permanent line teaches readers to
    skip a passing gate's output. An entry whose ID is open nowhere and
    completed nowhere is *unnoticed*, and that is the one worth a note.

    A missing file yields an empty set rather than raising: this feeds the
    advisory half only, so failing to read it can widen what is reported but
    can never turn a violation into a pass.
    """
    try:
        text = backlog.read_text(encoding="utf-8")
    except OSError:
        return set()
    return {m.group("id") for line in text.split("\n") if (m := _OPEN_ITEM_RE.match(line))}


# --------------------------------------------------------------------------- #
# The rules
# --------------------------------------------------------------------------- #

# A ceiling on prose, not a fitted curve. The first draft was set just above
# the longest surviving entry, and saying so was itself the mistake: the
# sentence describing the fit outlived the fit twice — once when adding a
# migration link to four entries and discounting link targets moved the longest
# entry, and again when a rebase re-applied the condensation onto a different
# base and moved it further. **Neither the headroom nor the fit is stated here,
# deliberately.** Both are measurements, and this constant answers a question
# about what the section is *for*. Re-derive instead of reading a number:
#
#     hatch run python -c "import runpy; m = runpy.run_path('scripts/check_changelog_unreleased.py'); \
#         print(max(e.prose_length for e in m['parse_unreleased']().entries))"
#
# Raising the budget is a decision about what the section is for, so it is a
# constant with a reason rather than a literal — but the reason is the rule
# (a stub, not a paragraph), never a measurement that ages.
_MAX_ENTRY_CHARS = 320


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    message: str


def _check_unique(entries: list[Entry]) -> list[Violation]:
    by_id: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_id[entry.item_id].append(entry)
    violations: list[Violation] = []
    for item_id, group in by_id.items():
        if len(group) > 1:
            first = group[0]
            for dup in group[1:]:
                violations.append(
                    Violation(
                        "CHANGELOG.md",
                        dup.line,
                        f"{item_id} already has an entry at line {first.line}: a conflict where one "
                        f"side revises the other is not a keep-both; keep the amended copy only",
                    )
                )
    return violations


def _check_shape(entries: list[Entry], stray: list[tuple[int, str]]) -> list[Violation]:
    violations = [
        Violation(
            "CHANGELOG.md",
            line,
            f"not an entry, and [Unreleased] holds nothing else: {text.strip()[:60]!r}. "
            f"Every line is `- <ID>: <text>`; sub-headings and wrapped entries belong to a "
            f"released section",
        )
        for line, text in stray
    ]
    violations.extend(
        Violation(
            "CHANGELOG.md",
            entry.line,
            f"{entry.item_id} runs {entry.prose_length} characters of prose, over the "
            f"{_MAX_ENTRY_CHARS} an [Unreleased] stub gets; state what shipped and leave the "
            f"prose to the release",
        )
        for entry in entries
        if entry.prose_length > _MAX_ENTRY_CHARS
    )
    return violations


def _check_audience(entries: list[Entry], backlog_done: Path, backlog: Path) -> tuple[list[Violation], list[str]]:
    """Return (violations, advisory notes). See the authority note in the docstring."""
    items = parse_done_unreleased(backlog_done)
    entry_ids = {entry.item_id for entry in entries}

    violations: list[Violation] = []
    for item in items:
        if not item.audience:
            violations.append(
                Violation(
                    "sdd/BACKLOG-DONE.md",
                    item.line,
                    f"{item.item_id} carries no `audience:` line, so the CHANGELOG rule cannot be evaluated for it",
                )
            )
        elif item.is_user_facing and item.item_id not in entry_ids:
            violations.append(
                Violation(
                    "sdd/BACKLOG-DONE.md",
                    item.line,
                    f"{item.item_id} is user-facing ({', '.join(item.audience)}) and has no "
                    f"CHANGELOG [Unreleased] entry",
                )
            )

    done_ids = {item.item_id for item in items}
    open_ids = open_item_ids(backlog)
    notes = [
        f"CHANGELOG.md:{entry.line}: {entry.item_id} has an entry, and is neither a completed item "
        f"under BACKLOG-DONE.md § Unreleased nor an open item in BACKLOG.md. An entry for an ID "
        f"the backlog does not know is the case worth looking at."
        for entry in entries
        if entry.item_id not in done_ids and entry.item_id not in open_ids
    ]
    return violations, notes


# The stand-down is a note, so it rides the same channel as the advisory half
# and needs no third return value from `collect`. `main` keys on this prefix to
# keep from printing "unique, stub-shaped and complete" about a section it did
# not read — the one sentence a stood-down run must not say.
_STOOD_DOWN = "stood down: "


def _release_window_note(section: Section) -> str:
    """The stand-down line, printed rather than inferred from silence.

    Named "stood down" and not "passed" on purpose: the caller reports zero
    violations here because it checked nothing, and a reader who cannot tell
    those apart has no way to notice a stray ``###`` switching the gate off
    mid-cycle.
    """
    remaining = len(section.entries)
    return (
        f"{_STOOD_DOWN}[Unreleased] carries a `###` grouping, the shape "
        "CONTRIBUTING.md § Release Phase 1 condenses it into and Phase 2 renames. All three rules "
        f"key on `- <ID>:` lines, so none was evaluated ({remaining} line(s) still in stub shape). "
        "Outside a release, this means a `###` heading reached [Unreleased] by mistake: remove it "
        "and the rules come back."
    )


def collect(repo_root: Path = _REPO_ROOT) -> tuple[list[Violation], list[str]]:
    section = parse_unreleased(repo_root / "CHANGELOG.md")
    if not section.found:
        return [Violation("CHANGELOG.md", 1, "no `## [Unreleased]` heading (was it renamed early?)")], []

    if section.grouped:
        return [], [_release_window_note(section)]

    violations = _check_unique(section.entries)
    violations.extend(_check_shape(section.entries, section.stray))
    audience_violations, notes = _check_audience(
        section.entries, repo_root / "sdd" / "BACKLOG-DONE.md", repo_root / "sdd" / "BACKLOG.md"
    )
    violations.extend(audience_violations)
    violations.sort(key=lambda v: (v.path, v.line))
    return violations, notes


# The rule is stated here because this is where a failing developer is standing.
# Its remediation used to be two document pointers alone, and neither document
# states any of the three rules: someone told their entry ran over the budget
# was sent to two files where that number does not appear and no length rule is
# written down, its only home being a constant in this file. The pointers stay,
# after the rule rather than instead of it — and CONTRIBUTING.md § Release
# Phase 1 now names this gate, which is the ripple BUG-262's trace recorded
# nobody asking about.
_REMEDIATION = (
    f"An [Unreleased] entry is one line, `- <ID>: <Title>`, one per ID, at most {_MAX_ENTRY_CHARS} "
    "characters of prose (Markdown link targets are not counted), and every completed user-facing "
    "item under sdd/BACKLOG-DONE.md § Unreleased has one. Prose belongs in the release section, "
    "the backlog entry, or the migration guide. See CONTRIBUTING.md § Release Phase 1 and the "
    "ripple-check row **CHANGELOG entry** in sdd/CLAUDE-REFERENCE.md."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root (default: the checkout this script lives in).",
    )
    args = parser.parse_args(argv)

    try:
        violations, notes = collect(args.repo_root)
    except DerivationError as exc:
        print(f"check_changelog_unreleased: cannot derive the claim: {exc}", file=sys.stderr)
        return 1

    stood_down = False
    for note in notes:
        if note.startswith(_STOOD_DOWN):
            stood_down = True
            print(f"check_changelog_unreleased: {note}")
        else:
            print(f"check_changelog_unreleased: note: {note}")

    if not violations:
        if not stood_down:
            print("check_changelog_unreleased: [Unreleased] is unique, stub-shaped and complete.")
        return 0

    for v in violations:
        print(f"{v.path}:{v.line}: {v.message}", file=sys.stderr)
    print(f"\ncheck_changelog_unreleased: {len(violations)} violation(s).", file=sys.stderr)
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
