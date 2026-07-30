"""Shared vocabulary for the rulebook-PoC analysis scripts.

Both `score.py` and `section_coverage.py` normalise trace `section` strings and
classify files against the compiled set. Those two derivations used to be written
twice and had already diverged (`whole file` was whole-doc in one and an ordinary
section in the other), which is the failure `sdd/DRIFT-RULES.md` Rule 1 names:
one normative description driving N artifacts, not N copies. It lives here.
"""

from __future__ import annotations

import re

#: The ten rule-stating documents RULEBOOK.md compiles. `CONTRIBUTING.md` is in
#: the set because RULEBOOK section 7 compiles its Authoritative Document Format
#: section and arm A was forbidden from opening it.
COMPILED = {
    "CLAUDE.md",
    "sdd/000-process.md",
    "sdd/DESIGN.md",
    "sdd/TESTING.md",
    "sdd/AUTHORING.md",
    "sdd/DOCUMENTATION.md",
    "sdd/CONTENT-RULES.md",
    "sdd/DRIFT-RULES.md",
    "sdd/CI-OPERATIONS.md",
    "CONTRIBUTING.md",
}

#: `CLAUDE.md` headings RULEBOOK section 0 does NOT carry. Section 0 is marked
#: *(condensed below Audits)*, so treating the whole file as carried inflates the
#: carried/dropped split in the artefact's favour. Enumerated by hand against
#: RULEBOOK section 0, because `CLAUDE.md` has no `## Rules` block to derive from.
CLAUDE_MD_DROPPED = {
    "project",
    "feature reference",
    "code conventions",
    "testing conventions",
    "drift checks",
    "repo skills",
}

#: `CONTRIBUTING.md` heading RULEBOOK section 7 carries; everything else in that
#: file is dropped.
CONTRIBUTING_CARRIED = {"authoritative document format"}


def key(section: str) -> str:
    """Normalise a trace `section` string to a comparison key.

    Returns ``"RULES"`` for a numbered-rule reference, ``"FULL"`` for a
    whole-document read, else the lowercased heading text.
    """
    s = section.split(" / ")[0].strip().lower()
    if s.startswith("rules") or re.match(r"^\d+[\s.(]", s):
        return "RULES"
    if s.startswith("(full") or s in ("whole file", "(item)"):
        return "FULL"
    return s
