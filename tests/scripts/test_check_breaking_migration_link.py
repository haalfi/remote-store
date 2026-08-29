"""Unit tests for scripts/check_breaking_migration_link.py.

The gate exists because the v0.31.0 window carried four `**Breaking**`
entries and one migration *link*: BK-357's entry named the section it
shipped, and BK-356, BUG-248 and BK-324 did not — even though BUG-261
(#984) had by then written subsections for all of them. The gate's subject
is therefore the missing link, not the missing section. The first two
cases below reproduce that pair, and the rest pin the boundaries where a
cheaper implementation would have been wrong: the entry grammar, the
anchored marker, the anchored link, the release-section scope, and the
difference between "no violations" and "matched nothing".
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_breaking_migration_link.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]

_LINK = "[migration guide](https://docs.remotestore.dev/stable/reference/migration/#v0300-to-v0310)"


def _load():
    spec = importlib.util.spec_from_file_location("check_breaking_migration_link", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_breaking_migration_link", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _changelog(tmp_path: Path, unreleased: str, released: str = "") -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n" + unreleased + "\n\n## [0.30.0] - 2026-07-19\n\n" + released + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# The pair the gate was written for
# --------------------------------------------------------------------------- #


def test_a_marked_entry_carrying_the_link_passes(tmp_path: Path) -> None:
    """BK-357's shape: marked, and its entry names the section."""
    changelog = _changelog(tmp_path, f"- BK-357: **Breaking** — seeking now raises. Upgrade path in the {_LINK}.")
    assert _mod.collect_violations(changelog) == []
    assert [e.entry_id for e in _mod.marked_entries(changelog)] == ["BK-357"], "the entry must be seen, not skipped"


def test_a_marked_entry_without_the_link_is_a_violation(tmp_path: Path) -> None:
    """BUG-248's shape: the defect the gate was written for."""
    changelog = _changelog(tmp_path, "- BUG-248: **Breaking** — an absent drive now reads as an absent path")
    violations = _mod.collect_violations(changelog)
    assert [v.entry_id for v in violations] == ["BUG-248"]
    assert violations[0].line == 5, "the reported line must point at the entry, not the section"


# --------------------------------------------------------------------------- #
# Matcher boundaries — each of these was a live fail-open
# --------------------------------------------------------------------------- #


def test_a_suffixed_id_is_still_matched(tmp_path: Path) -> None:
    """Split items carry a lowercase suffix, and a grammar without it fails open.

    `sdd/traces/_schema.yml` states the shape as ``PREFIX-[0-9]+[a-z]?`` and
    BACKLOG-DONE.md carries BK-139d, ID-118b, BK-167a/b, ID-013b, ID-151b/c.
    An ID-ends-in-digits grammar skips those entries and exits 0.
    """
    changelog = _changelog(tmp_path, "- BK-139e: **Breaking** — a split item's second half")
    assert [v.entry_id for v in _mod.collect_violations(changelog)] == ["BK-139e"]


def test_a_compound_prefix_is_still_matched(tmp_path: Path) -> None:
    """`check_no_tracker_refs.py` treats `SQL-BLOB-020` as a coordinate; so does this."""
    changelog = _changelog(tmp_path, "- SQL-BLOB-020: **Breaking** — a compound-prefix tracker")
    assert [v.entry_id for v in _mod.collect_violations(changelog)] == ["SQL-BLOB-020"]


def test_an_entry_that_merely_mentions_the_marker_is_not_marked(tmp_path: Path) -> None:
    """The gate's own first false positive, pinned so it cannot come back.

    An unanchored substring test flags any entry whose prose contains the
    marker. This gate's own CHANGELOG stub does -- it describes the rule it
    enforces -- and the full gate failed on it the first time it ran.
    """
    changelog = _changelog(
        tmp_path,
        "- BUG-262: Gate that every unreleased `**Breaking**` entry links its upgrade path",
    )
    assert _mod.marked_entries(changelog) == []


def test_a_bare_mention_of_the_path_is_not_a_link(tmp_path: Path) -> None:
    """The same unanchored-substring class as the marker, on the other half.

    These entries run to kilobytes of prose, so an entry that *talks about*
    the guide without linking it is a real shape -- and a substring search
    for the path passes it.
    """
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — X now raises. The docs-src/reference/migration.md section is not written yet.",
    )
    assert [v.entry_id for v in _mod.collect_violations(changelog)] == ["BK-360"]


def test_a_relative_markdown_link_satisfies_the_rule(tmp_path: Path) -> None:
    """An entry authored against the repo tree, not the published site."""
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — something. See [the guide](docs-src/reference/migration.md).",
    )
    assert _mod.collect_violations(changelog) == []


def test_an_unmarked_entry_is_ignored_however_breaking_it_reads(tmp_path: Path) -> None:
    """The softer half is a human judgement, and the gate must not pretend otherwise.

    BUG-259 changed what a stored ``base_path`` value means and carries a
    ``**Fix**`` marker. Phase 1 decides that class; a marker-keyed gate
    cannot, and firing here would make the miss-rate bound in the module
    docstring false.
    """
    changelog = _changelog(tmp_path, "- BUG-259: **Fix** — a write to the store root is now refused")
    assert _mod.marked_entries(changelog) == []


def test_a_released_unlinked_entry_is_out_of_scope(tmp_path: Path) -> None:
    """The release boundary, pinned with a shape the entry grammar accepts.

    An earlier version of this case used the condensed ``- **Title** (ID):``
    form, which ``_ENTRY_RE`` rejects on its own — so the test passed with
    the section-scope loop deleted and pinned nothing. A stub-shaped released
    entry is the only shape that distinguishes the two implementations.
    """
    changelog = _changelog(
        tmp_path,
        f"- BK-360: **Breaking** — something. Upgrade path in the {_LINK}.",
        released="- BK-100: **Breaking** — no link here",
    )
    assert [e.entry_id for e in _mod.marked_entries(changelog)] == ["BK-360"], "the released entry must be out of scope"
    assert _mod.collect_violations(changelog) == []


def test_every_unlinked_entry_is_reported_not_just_the_first(tmp_path: Path) -> None:
    """The real window had two unlinked entries; a first-match gate hides one."""
    changelog = _changelog(
        tmp_path,
        "- BUG-248: **Breaking** — one\n- BK-324: **Breaking** — two\n- BK-357: **Breaking** — three, see "
        + _LINK
        + ".",
    )
    assert [v.entry_id for v in _mod.collect_violations(changelog)] == ["BUG-248", "BK-324"]


# --------------------------------------------------------------------------- #
# Failing loud rather than reporting success over nothing
# --------------------------------------------------------------------------- #


def test_a_missing_unreleased_heading_raises_rather_than_passing(tmp_path: Path) -> None:
    """Phase 2 renames this heading, so the branch is on the release path."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## [0.30.0] - 2026-07-19\n\n- BK-100: **Breaking** — x\n", encoding="utf-8")
    with pytest.raises(_mod.ChangelogUnreadable, match="no '## \\[Unreleased\\]'"):
        _mod.marked_entries(path)


def test_an_unreadable_changelog_raises_rather_than_passing(tmp_path: Path) -> None:
    with pytest.raises(_mod.ChangelogUnreadable, match="cannot read"):
        _mod.marked_entries(tmp_path / "absent.md")


# --------------------------------------------------------------------------- #
# main() — what lint and docs-gate actually run
# --------------------------------------------------------------------------- #


def test_main_returns_zero_and_reports_the_count(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _changelog(tmp_path, f"- BK-357: **Breaking** — x. See the {_LINK}.")
    assert _mod.main(["--repo-root", str(tmp_path)]) == 0
    assert "1 marked entry/entries" in capsys.readouterr().out


def test_main_returns_one_and_names_the_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _changelog(tmp_path, "- BUG-248: **Breaking** — no link")
    assert _mod.main(["--repo-root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "BUG-248 is marked **Breaking**" in err
    assert "Upgrade path in the [migration guide]" in err, "the remediation must show the shape it wants"


def test_main_fails_loud_when_it_cannot_find_its_subject(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A gate that cannot find its subject must not print success."""
    assert _mod.main(["--repo-root", str(tmp_path)]) == 1
    assert "cannot read" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The real tree
# --------------------------------------------------------------------------- #


def test_the_repository_satisfies_its_own_gate() -> None:
    assert _mod.collect_violations(_REPO_ROOT / "CHANGELOG.md") == []


def test_the_parser_agrees_with_an_independent_count_of_the_real_changelog() -> None:
    """Distinguish "no violations" from "matched nothing" against the live file.

    Every other case here uses a synthetic fixture, so a parser that matched
    zero entries -- a wrong grammar, a collapsed section boundary, the Phase 1
    condensed shape -- would satisfy all of them at once. This derives the
    expected set with its own regex over the same window and asserts the two
    agree, so the gate cannot go blind on the real tree and stay green.
    """
    lines = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("## [Unreleased]")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))
    expected = [
        m.group(1)
        for m in (re.match(r"^- ([A-Z][A-Z0-9-]*-\d+[a-z]*): \*\*Breaking\*\*", ln) for ln in lines[start:end])
        if m
    ]
    assert expected, "the fixture assumption is gone: [Unreleased] carries no marked entries at all"
    assert [e.entry_id for e in _mod.marked_entries(_REPO_ROOT / "CHANGELOG.md")] == expected
