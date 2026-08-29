"""Check that every unreleased ``**Breaking**`` entry links its upgrade path.

`CONTRIBUTING.md` § Release Phase 1 and the ripple-check's **Breaking
change** row both require the PR making a break to write a
``## vPREV to vNEXT`` section in ``docs-src/reference/migration.md``. This
gate is the mechanical half of that rule.

Why the link and not the heading
================================

The obvious check -- "if any ``[Unreleased]`` entry is marked
``**Breaking**``, a ``## vCURRENT to vNEXT`` heading must exist" -- was
proposed and does not work, for a measured reason. In the v0.31.0 window
BK-357 wrote that heading while BUG-248 and BK-324 shipped uncovered
under it, so a heading-existence check passes with two of three breaks
undocumented. The heading is per-release; the obligation is per-entry, so
the check has to be per-entry too.

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
marker in its prose is not treated as carrying it.

**Not** checked, and stated rather than implied
([`DRIFT-RULES.md` Rule 7](../sdd/DRIFT-RULES.md#miss-rate)):

* Whether the linked section says anything *useful*, or says anything
  about this entry at all. A link to the right heading with the wrong
  content passes.
* Released sections. Phase 2 condensation drops the ``**Breaking**``
  marker, so there is nothing to key on once a section ships; this gate
  sees only the current window.
* The softer half of the rule -- an entry a caller must act on that
  carries no marker. No marker decides that, so no gate measures it, and
  `CONTRIBUTING.md` § Release Phase 1 keeps it as a human judgement. In
  the v0.31.0 window that unmarked set was **6** entries against 4 marked
  ones, so the unchecked remainder is larger than the checked part.

Exit codes
==========

* ``0`` -- every marked entry carries a migration-guide link.
* ``1`` -- one or more do not; one line per entry to stderr, plus
  remediation.

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

# An entry is one line starting `- PREFIX-NNN: `. Compound prefixes are
# allowed so a future `SQL-BLOB-020`-shaped tracker still parses.
_ENTRY_RE = re.compile(r"^- ([A-Z][A-Z0-9-]*-\d+): ")

# The marker is *anchored* to the start of the entry body, which is where the
# convention puts it (`- BK-357: **Breaking** — ...`) and where the release
# skill reads it. A substring test instead of an anchored one treats an entry
# that merely *discusses* the marker as carrying it -- this gate's own CHANGELOG
# stub was the first false positive, on its first run.
_MARKED_RE = re.compile(r"^- [A-Z][A-Z0-9-]*-\d+: \*\*Breaking\*\*")

# Both spellings the corpus uses: the published site URL, and a relative
# link for anything authored against the repo tree.
_LINK_RE = re.compile(r"reference/migration(?:/|\.md)")


@dataclass(frozen=True)
class Violation:
    line: int
    entry_id: str


def collect_violations(changelog: Path) -> list[Violation]:
    try:
        lines = changelog.read_text(encoding="utf-8").splitlines()
    except OSError as exc:  # pragma: no cover - only if the file vanishes
        print(f"cannot read {changelog}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        start = lines.index(_UNRELEASED)
    except ValueError:
        print(f"{changelog}: no '{_UNRELEASED}' section", file=sys.stderr)
        raise SystemExit(1) from None

    end = len(lines)
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if _RELEASE_HEADING_RE.match(line):
            end = offset
            break

    violations: list[Violation] = []
    for offset, line in enumerate(lines[start:end], start=start):
        match = _ENTRY_RE.match(line)
        if not match or not _MARKED_RE.match(line):
            continue
        if not _LINK_RE.search(line):
            violations.append(Violation(offset + 1, match.group(1)))
    return violations


_REMEDIATION = (
    "Every [Unreleased] entry marked **Breaking** must link the section that "
    "carries its upgrade path, e.g.\n"
    "  Upgrade path in the [migration guide]"
    "(https://docs.remotestore.dev/stable/reference/migration/#v0300-to-v0310).\n"
    "Write the section in docs-src/reference/migration.md under the "
    "'## vPREV to vNEXT' heading for this release (append to it if it exists), "
    "then link it from the entry. See CONTRIBUTING.md (Release, Phase 1) and the "
    "ripple-check's 'Breaking change' row in sdd/CLAUDE-REFERENCE.md."
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
    violations = collect_violations(changelog)
    if not violations:
        print("check_breaking_migration_link: every unreleased **Breaking** entry links its upgrade path.")
        return 0

    for v in violations:
        print(
            f"CHANGELOG.md:{v.line}: {v.entry_id} is marked **Breaking** and links no migration section",
            file=sys.stderr,
        )
    print(
        f"\ncheck_breaking_migration_link: {len(violations)} unlinked breaking entry/entries.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
