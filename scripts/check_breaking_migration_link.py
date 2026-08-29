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
a Markdown link whose target names the guide, for the same reason: a bare
mention of the path in prose is not a link.

**Not** checked, and stated rather than implied
([`DRIFT-RULES.md` Rule 7](../sdd/DRIFT-RULES.md#miss-rate)):

* Whether the linked section says anything *useful*, or says anything
  about this entry at all. A link to the right heading with the wrong
  content passes.
* **The condensed form of the section, which is a live blind window and
  not merely "released sections".** `CONTRIBUTING.md` § Release **Phase
  1** condenses ``[Unreleased]`` in place -- stubs become
  ``### Added`` / ``### Changed`` prose whose entries lead with a title
  rather than an ID (``- **SFTP write() cuts round-trips** (BK-313): …``).
  The operative exclusion is that *shape*, not the marker: a condensed
  entry that kept ``**Breaking**`` would still be invisible, because the
  ID no longer leads the line. So from the moment Phase 1 condenses until
  Phase 2 renames the heading, this gate enumerates zero entries -- which
  is exactly while Phase 1's own migration-guide checklist item is being
  verified. The success line always reports how many entries were
  enumerated so that state is visible rather than indistinguishable from
  a clean pass.
* The softer half of the rule -- an entry a caller must act on that
  carries no marker. No marker decides that, so no gate measures it, and
  `CONTRIBUTING.md` § Release Phase 1 keeps it as a human judgement. In
  the v0.31.0 window that unmarked set was **6** entries against 4 marked
  ones, so the unchecked remainder is larger than the checked part.

Exit codes
==========

* ``0`` -- every marked entry carries a migration-guide link.
* ``1`` -- one or more do not; one line per entry to stderr, plus
  remediation. Also ``1`` if the ``[Unreleased]`` heading is missing or
  the file cannot be read: a gate that cannot find its subject fails
  loud rather than reporting success over nothing.

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

# The marker is *anchored* to the start of the entry body, which is where the
# convention puts it (`- BK-357: **Breaking** — ...`) and where the release
# skill reads it. A substring test instead of an anchored one treats an entry
# that merely *discusses* the marker as carrying it -- this gate's own CHANGELOG
# stub was the first false positive, on its first run.
_MARKED_RE = re.compile(r"^- [A-Z][A-Z0-9-]*-\d+[a-z]*: \*\*Breaking\*\*")

# A Markdown link whose target names the guide, in either spelling the corpus
# uses: the published site URL, or a repo-relative path. Matching the *link*
# rather than the bare path is the same rule as the anchored marker above --
# these entries run to kilobytes of prose, so a passing mention of the path is
# a real shape, and it is not a link.
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*reference/migration[^)]*\)")


@dataclass(frozen=True)
class Entry:
    """One ``[Unreleased]`` entry that opens with the ``**Breaking**`` marker."""

    line: int
    entry_id: str
    linked: bool


class ChangelogUnreadable(RuntimeError):
    """The gate could not find its subject. Never reported as a pass."""


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
        if not match or not _MARKED_RE.match(line):
            continue
        found.append(Entry(offset + 1, match.group(1), bool(_LINK_RE.search(line))))
    return found


def collect_violations(changelog: Path) -> list[Entry]:
    """The marked entries that carry no migration-guide link."""
    return [e for e in marked_entries(changelog) if not e.linked]


_REMEDIATION = (
    "Every [Unreleased] entry marked **Breaking** must link the section that "
    "carries its upgrade path, e.g.\n"
    "  Upgrade path in the [migration guide]"
    "(https://docs.remotestore.dev/stable/reference/migration/#v0300-to-v0310).\n"
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
    try:
        entries = marked_entries(changelog)
    except ChangelogUnreadable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    violations = [e for e in entries if not e.linked]
    if not violations:
        # The count is part of the success line, not decoration: this gate
        # enumerates zero entries once Phase 1 condenses the section, and a
        # bare "passed" would read identically to a real pass.
        print(
            f"check_breaking_migration_link: {len(entries)} marked entry/entries "
            f"under [Unreleased], all linking their upgrade path."
        )
        return 0

    for v in violations:
        print(
            f"CHANGELOG.md:{v.line}: {v.entry_id} is marked **Breaking** and links no migration section",
            file=sys.stderr,
        )
    print(
        f"\ncheck_breaking_migration_link: {len(violations)} of {len(entries)} "
        f"marked entry/entries link no upgrade path.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
