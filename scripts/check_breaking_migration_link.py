"""Check that every unreleased ``**Breaking**`` entry links its upgrade path.

`CONTRIBUTING.md` § Release Phase 1 and the ripple-check's **Breaking
change** row both require the PR making a break to write a
``## vPREV to vNEXT`` section in ``docs-src/reference/migration.md``, and
to link that section from the entry. This gate is the mechanical half of
that rule.

Why the link and not the heading
================================

The obvious check -- "if any ``[Unreleased]`` entry is marked
``**Breaking**``, a ``## vCURRENT to vNEXT`` heading must exist" -- was
proposed and does not work, for a measured reason. In the v0.31.0 window
BK-357 wrote that heading while BUG-248 and BK-324 shipped uncovered
under it, so a heading-existence check passes with two of the four marked
entries undocumented. The heading is per-release; the obligation is
per-entry, so the check has to be per-entry too.

The published guide cannot cite the entry it answers
(``check_no_tracker_refs.py`` bars ``PREFIX-NNN`` from all of
``docs-src/``), so the link runs the other way: the CHANGELOG entry, which
*is* addressed by its tracker ID, names the section that answers it. That
also gives a reader of the entry somewhere to go, which is the user-facing
half of the same rule.

Scope and bound
===============

Checked: entries under ``## [Unreleased]`` whose body *opens* with
``**Breaking**``, matched as ``- <ID>: **Breaking**``. The marker is
anchored rather than searched for, so an entry that merely mentions the
marker in its prose is not treated as carrying it. The link is matched as
a Markdown link to the **published** guide URL, for two reasons: a bare
mention of the path in prose is not a link, and a repo-relative path would
break on the site, since this file is dual-published to
``reference/changelog.md`` and the href would resolve under ``reference/``.

The fragment **is** checked, against the ``## `` headings
``docs-src/reference/migration.md`` actually exposes. Nothing else in the
repo does: `check_links` discards the fragment of an absolute docs-site
URL (``_resolve_docs_site_path`` returns ``parts.path`` only) and
``mkdocs build --strict`` does not resolve external URLs. Without it the
gate could be satisfied by a link to a heading nobody wrote -- which is
the whole obligation slipping through the check meant to enforce it.

**Not** checked, and stated rather than implied
([`DRIFT-RULES.md` Rule 7](../sdd/DRIFT-RULES.md#miss-rate)):

* Whether the linked section says anything *useful*, or says anything
  about this entry at all. The heading now has to exist, but a link to a
  real heading with the wrong content -- last release's pair, say --
  passes.
* The link must sit on the **same physical line as the ID**: the match
  runs over one line, so an entry wrapped with its link on a
  continuation line reads as unlinked. One-line stubs are the documented
  convention (`sdd/CLAUDE-REFERENCE.md`, "CHANGELOG entry" row), so this
  is narrow, but it fails without naming its cause.
* **The condensed form of the section, which is a live blind window and
  not merely "released sections".** `CONTRIBUTING.md` § Release **Phase
  1** condenses ``[Unreleased]`` in place -- stubs become
  ``### Added`` / ``### Changed`` prose whose entries lead with a title
  rather than an ID (``- **SFTP write() cuts round-trips** (BK-313): …``).
  The operative exclusion is that *shape*, not the marker: a condensed
  entry that kept ``**Breaking**`` would still be invisible, because the
  ID no longer leads the line. So from the moment Phase 1 condenses until
  Phase 2 renames the heading, this gate enumerates zero entries. **Phase
  1 is ordered so its own migration-guide item is verified before that
  window opens**, and it says so where the step is: the item keys on the
  same marker this gate does, so running it after condensing would leave
  it reading nothing. An earlier version of this bullet recorded the
  opposite -- that the blind window fell "exactly while" that item was
  being verified -- which was true of the order at the time and is the
  overlap the reorder removed. The success line always reports how many
  entries were enumerated so the window is visible rather than
  indistinguishable from a clean pass.
* The softer half of the rule -- an entry a caller must act on that
  carries no marker. No marker decides that, so no gate measures it, and
  `CONTRIBUTING.md` § Release Phase 1 keeps it as a human judgement. In
  the v0.31.0 window that unmarked set was **6** entries against 4 marked
  ones, so the unchecked remainder is larger than the checked part.

Exit codes
==========

* ``0`` -- every marked entry links a real section of the guide.
* ``1`` -- one or more do not; one line per entry to stderr naming which
  of the two failures it is, plus remediation. Also ``1`` if the
  ``[Unreleased]`` heading is missing, or either file cannot be read: a
  gate that cannot find its subject fails loud rather than reporting
  success over nothing.

Drift-gate::

    kind:       pair
    compares: CHANGELOG.md [Unreleased] **Breaking** entries ↔ the
        docs-src/reference/migration.md link each one carries
    domain:     process
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_UNRELEASED = "## [Unreleased]"
_RELEASE_HEADING_RE = re.compile(r"^## \[")

# The entry grammar. The ID leads the line and may carry a lowercase suffix:
# `sdd/traces/_schema.yml` states the shape as `PREFIX-[0-9]+[a-z]?`, and
# BACKLOG-DONE.md carries live suffixed IDs (BK-139d, ID-118b, BK-167a/b,
# ID-013b, ID-151b/c, ID-147b, ID-143b). Dropping the suffix made a marked
# entry using one skip silently, which for a gate is the expensive direction.
# The prefix class also admits a compound form (`SQL-BLOB-020`), which no
# tracker uses today but which `check_no_tracker_refs.py` already treats as
# valid, so the two agree on what a coordinate looks like.
_ENTRY_RE = re.compile(r"^- ([A-Z][A-Z0-9-]*-\d+[a-z]*): ")

# The marker opens the entry *body*, which is where the convention puts it
# (`- BK-357: **Breaking** — ...`). Tested by position against the entry match
# rather than by a second regex, for two reasons. A substring test treats an
# entry that merely *discusses* the marker as carrying it -- this gate's own
# CHANGELOG stub was the first false positive, on its first run. And a second
# regex restating the ID grammar is what made the suffix fix have to widen two
# places: widen one and the enumeration silently narrows, no violation, exit 0 --
# the same fail-open class this gate exists to prevent, rebuilt inside it.
_MARKER = "**Breaking**"

# A Markdown link to the *published* guide. Two things are load-bearing.
# Matching the link rather than the bare path is the same rule as the marker:
# these entries run to kilobytes of prose, so a passing mention of the path is a
# real shape and it is not a link. And the target must be the site URL, the only
# spelling this file uses -- `rg -o '\]\([^)]*migration[^)]*\)' CHANGELOG.md`
# returns 7 hits, every one `https://docs.remotestore.dev/...`. A repo-relative
# `docs-src/reference/migration.md` would be worse than merely unattested:
# CHANGELOG.md carries a `doc: dual dest=reference/changelog.md` marker, so it
# renders at `reference/changelog.md`, where that href resolves to
# `reference/docs-src/reference/migration.md` and does not exist -- a broken link
# on the published site, which `check_links` and `mkdocs build --strict` reject.
# Accepting it would let an author pass `lint` and fail `docs-gate` on the same
# rule in the same PR.
# The trailing slash is optional, because `check_links` treats both spellings as
# the same page: `_resolve_docs_site_path` does `parts.path.strip("/")` and
# `_normalize_docs_dest("reference/migration.md")` yields `reference/migration`.
# Requiring it here would reject a URL the repo's own link checker has just
# declared valid, and report it as "links no migration section" -- a failure
# naming the wrong defect.
_LINK_RE = re.compile(r"\[[^\]]*\]\((https://docs\.remotestore\.dev/[^)]*reference/migration/?(?:#([^)]*))?)\)")

# A `## ` heading in the migration guide, and the slug it renders as. The rule
# is narrow because the headings are: lowercase, drop characters that are
# neither alphanumeric nor space nor hyphen, then spaces to hyphens -- so
# `## v0.30.0 to v0.31.0` becomes `v0300-to-v0310`. It is not a general slug
# engine and does not try to be; `check_links._extract_anchors` is, but reaching
# for it would import a git-invoking module tree into `lint` to answer one
# question. What keeps this honest is that the four live links in CHANGELOG.md
# are checked against it on every run: get the rule wrong and this gate fails on
# master immediately, rather than passing something.
_HEADING_RE = re.compile(r"^## +(.+?)\s*$")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9 -]")


@dataclass(frozen=True)
class Entry:
    """One ``[Unreleased]`` entry that opens with the ``**Breaking**`` marker."""

    line: int
    entry_id: str
    linked: bool
    #: The fragment the entry links, if it links one at all. ``None`` when the
    #: entry carries no link; ``""`` when it links the page with no anchor.
    anchor: str | None = None


class ChangelogUnreadable(RuntimeError):
    """The gate could not find its subject. Never reported as a pass."""


def _slug(heading: str) -> str:
    return _SLUG_STRIP_RE.sub("", heading.lower()).strip().replace(" ", "-")


def migration_anchors(migration: Path) -> set[str]:
    """Fragment IDs the migration guide's ``## `` headings expose."""
    try:
        text = migration.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChangelogUnreadable(f"cannot read {migration}: {exc}") from exc
    return {_slug(m.group(1)) for line in text.splitlines() if (m := _HEADING_RE.match(line))}


def marked_entries(changelog: Path) -> list[Entry]:
    """Every ``[Unreleased]`` entry opening with ``**Breaking**``, linked or not.

    Exposed separately from `collect_violations` so a caller -- and the
    guard in ``tests/scripts/`` -- can tell "found no violations" from
    "matched no entries". Those are the same return value from a
    violations-only API, and the second is how this gate goes blind.
    """
    try:
        lines = changelog.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ChangelogUnreadable(f"cannot read {changelog}: {exc}") from exc

    try:
        start = lines.index(_UNRELEASED)
    except ValueError:
        raise ChangelogUnreadable(f"{changelog}: no '{_UNRELEASED}' section") from None

    end = len(lines)
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if _RELEASE_HEADING_RE.match(line):
            end = offset
            break

    found: list[Entry] = []
    for offset, line in enumerate(lines[start:end], start=start):
        match = _ENTRY_RE.match(line)
        if not match or not line[match.end() :].startswith(_MARKER):
            continue
        link = _LINK_RE.search(line)
        anchor = (link.group(2) or "") if link else None
        found.append(Entry(offset + 1, match.group(1), link is not None, anchor))
    return found


def collect_violations(changelog: Path, migration: Path) -> list[tuple[Entry, str]]:
    """Marked entries that carry no usable link, each with why it is a violation.

    Two failures, deliberately reported apart. An entry with no link at all is
    the defect this gate was written for. An entry whose link names a fragment
    the guide does not expose is the one that would otherwise slip *through* the
    gate: nothing else in the repo validates it -- `check_links` discards the
    fragment of an absolute docs-site URL (`_resolve_docs_site_path` returns
    `parts.path` only) and `mkdocs build --strict` does not resolve external
    URLs -- so without this, an entry could satisfy the rule while the section
    it points at was never written.
    """
    anchors = migration_anchors(migration)
    out: list[tuple[Entry, str]] = []
    for entry in marked_entries(changelog):
        if not entry.linked:
            out.append((entry, "links no migration section"))
        elif entry.anchor and entry.anchor not in anchors:
            out.append((entry, f"links #{entry.anchor}, which is not a heading in {migration.name}"))
    return out


_REMEDIATION = (
    "Every [Unreleased] entry marked **Breaking** must link the section that "
    "carries its upgrade path, e.g.\n"
    "  Upgrade path in the [migration guide]"
    "(https://docs.remotestore.dev/stable/reference/migration/#vPREV-to-vNEXT).\n"
    "  The anchor is this release's own version pair. A copied anchor naming the\n"
    "  previous release passes this gate -- see its first stated bound.\n"
    "Write the section in docs-src/reference/migration.md under the "
    "'## vPREV to vNEXT' heading for this release (append to it if it exists), "
    "then link it from the entry. Both halves are stated in CONTRIBUTING.md "
    "(Release, Phase 1) and in the ripple-check's 'Breaking change' row in "
    "sdd/CLAUDE-REFERENCE.md."
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

    changelog = args.repo_root / "CHANGELOG.md"
    migration = args.repo_root / "docs-src" / "reference" / "migration.md"
    try:
        # `entries` is for the count in both lines below; `violations` comes
        # from collect_violations rather than being re-derived here, so the
        # definition of "violation" lives in exactly one place -- the same rule
        # the _MARKER comment above argues for, applied to the predicate.
        entries = marked_entries(changelog)
        violations = collect_violations(changelog, migration)
    except ChangelogUnreadable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not violations:
        # The count is part of the success line, not decoration: this gate
        # enumerates zero entries once Phase 1 condenses the section, and a
        # bare "passed" would read identically to a real pass.
        print(
            f"check_breaking_migration_link: {len(entries)} marked entry/entries "
            f"under [Unreleased], all linking a real section of their upgrade path."
        )
        return 0

    for entry, why in violations:
        print(
            f"CHANGELOG.md:{entry.line}: {entry.entry_id} is marked **Breaking** and {why}",
            file=sys.stderr,
        )
    print(
        f"\ncheck_breaking_migration_link: {len(violations)} of {len(entries)} "
        f"marked entry/entries do not reach their upgrade path.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
