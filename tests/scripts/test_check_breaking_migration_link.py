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


def _migration(tmp_path: Path, headings: tuple[str, ...] = ("v0.30.0 to v0.31.0",)) -> Path:
    """A migration guide exposing *headings*, so fragments have something to resolve against."""
    path = tmp_path / "docs-src" / "reference" / "migration.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Migration Guide\n\n" + "\n\n".join(f"## {h}\n\nbody" for h in headings) + "\n", "utf-8")
    return path


# --------------------------------------------------------------------------- #
# The pair the gate was written for
# --------------------------------------------------------------------------- #


def test_a_marked_entry_carrying_the_link_passes(tmp_path: Path) -> None:
    """BK-357's shape: marked, and its entry names the section."""
    changelog = _changelog(tmp_path, f"- BK-357: **Breaking** — seeking now raises. Upgrade path in the {_LINK}.")
    assert _mod.collect_violations(changelog, _migration(tmp_path)) == []
    assert [e.entry_id for e in _mod.marked_entries(changelog)] == ["BK-357"], "the entry must be seen, not skipped"


def test_a_marked_entry_without_the_link_is_a_violation(tmp_path: Path) -> None:
    """BUG-248's shape: the defect the gate was written for."""
    changelog = _changelog(tmp_path, "- BUG-248: **Breaking** — an absent drive now reads as an absent path")
    violations = _mod.collect_violations(changelog, _migration(tmp_path))
    assert [e.entry_id for e, _ in violations] == ["BUG-248"]
    assert violations[0][0].line == 5, "the reported line must point at the entry, not the section"
    assert violations[0][1] == "links no migration section"


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
    assert [e.entry_id for e, _ in _mod.collect_violations(changelog, _migration(tmp_path))] == ["BK-139e"]


def test_a_compound_prefix_is_still_matched(tmp_path: Path) -> None:
    """`check_no_tracker_refs.py` treats `SQL-BLOB-020` as a coordinate; so does this."""
    changelog = _changelog(tmp_path, "- SQL-BLOB-020: **Breaking** — a compound-prefix tracker")
    assert [e.entry_id for e, _ in _mod.collect_violations(changelog, _migration(tmp_path))] == ["SQL-BLOB-020"]


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
    assert [e.entry_id for e, _ in _mod.collect_violations(changelog, _migration(tmp_path))] == ["BK-360"]


def test_a_repo_relative_link_is_a_violation(tmp_path: Path) -> None:
    """The one spelling that looks right and breaks the published site.

    CHANGELOG.md carries a ``doc: dual dest=reference/changelog.md`` marker, so
    it renders at ``reference/changelog.md`` — where this href resolves to
    ``reference/docs-src/reference/migration.md``, which does not exist.
    Accepting it would let an author pass ``lint`` and fail ``docs-gate`` on the
    same rule in the same PR, so the gate rejects it here instead.
    """
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — something. See [the guide](docs-src/reference/migration.md).",
    )
    assert [e.entry_id for e, _ in _mod.collect_violations(changelog, _migration(tmp_path))] == ["BK-360"]


def test_a_versioned_published_link_satisfies_the_rule(tmp_path: Path) -> None:
    """The site URL is required, but not pinned to ``/stable/``."""
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — x. See "
        "[the guide](https://docs.remotestore.dev/0.31.0/reference/migration/#v0300-to-v0310).",
    )
    assert _mod.collect_violations(changelog, _migration(tmp_path)) == []


def test_a_link_to_a_heading_that_does_not_exist_is_a_violation(tmp_path: Path) -> None:
    """The miss that would let the whole obligation through the gate.

    Nothing else in the repo validates this fragment: ``check_links``
    discards it for an absolute docs-site URL (``_resolve_docs_site_path``
    returns ``parts.path`` only) and ``mkdocs build --strict`` does not resolve
    external URLs. Without this check an author could satisfy the rule with a
    link to a section nobody wrote — the defect BUG-261 and BUG-262 exist to
    close, reached *through* the gate instead of around it.
    """
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — x. Upgrade path in the "
        "[migration guide](https://docs.remotestore.dev/stable/reference/migration/#v9999-to-v9999).",
    )
    violations = _mod.collect_violations(changelog, _migration(tmp_path))
    assert [e.entry_id for e, _ in violations] == ["BK-360"]
    assert violations[0][1] == "links #v9999-to-v9999, which is not a heading in migration.md", (
        "the message must name the missing anchor, not the wrong defect"
    )


def test_the_slug_rule_matches_the_headings_it_is_derived_from(tmp_path: Path) -> None:
    """The narrow slug rule, pinned against the shapes the guide actually uses."""
    migration = _migration(tmp_path, headings=("v0.30.0 to v0.31.0", "v0.29.1 to v0.30.0"))
    assert _mod.migration_anchors(migration) == {"v0300-to-v0310", "v0291-to-v0300"}


def test_the_live_guide_exposes_every_anchor_the_live_changelog_links() -> None:
    """The slug rule is only trustworthy because the real files check it every run.

    This gate re-implements a narrow slug rule rather than importing
    ``check_links._extract_anchors``, which would pull a git-invoking module
    tree into ``lint``. What keeps that honest is this: the anchors the live
    CHANGELOG links are resolved against the live guide, so a wrong rule fails
    here rather than passing something through.
    """
    entries = _mod.marked_entries(_REPO_ROOT / "CHANGELOG.md")
    anchors = _mod.migration_anchors(_REPO_ROOT / "docs-src" / "reference" / "migration.md")
    linked = [e for e in entries if e.anchor]
    if not linked:
        pytest.skip("[Unreleased] carries no marked entry with an anchored link")
    assert {e.anchor for e in linked} <= anchors


def test_the_trailing_slash_is_optional_because_check_links_normalises_it(tmp_path: Path) -> None:
    """Two gates must not disagree about the same URL.

    ``check_links._resolve_docs_site_path`` does ``parts.path.strip("/")``, so it
    accepts both spellings. Rejecting the slashless one here would fail a link
    the repo's own link checker has just declared valid, and report it as
    "links no migration section" — a message naming the wrong defect.
    """
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — x. See "
        "[the guide](https://docs.remotestore.dev/stable/reference/migration#v0300-to-v0310).",
    )
    assert _mod.collect_violations(changelog, _migration(tmp_path)) == []


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
    assert _mod.collect_violations(changelog, _migration(tmp_path)) == []


def test_every_unlinked_entry_is_reported_not_just_the_first(tmp_path: Path) -> None:
    """The real window had two unlinked entries; a first-match gate hides one."""
    changelog = _changelog(
        tmp_path,
        "- BUG-248: **Breaking** — one\n- BK-324: **Breaking** — two\n- BK-357: **Breaking** — three, see "
        + _LINK
        + ".",
    )
    assert [e.entry_id for e, _ in _mod.collect_violations(changelog, _migration(tmp_path))] == ["BUG-248", "BK-324"]


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
    _migration(tmp_path)
    assert _mod.main(["--repo-root", str(tmp_path)]) == 0
    assert "1 marked entry/entries" in capsys.readouterr().out


def test_main_returns_one_and_names_the_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _changelog(tmp_path, "- BUG-248: **Breaking** — no link")
    _migration(tmp_path)
    assert _mod.main(["--repo-root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "BUG-248 is marked **Breaking**" in err
    assert "Upgrade path in the [migration guide]" in err, "the remediation must show the shape it wants"


def test_main_fails_loud_when_the_file_is_absent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A gate that cannot find its subject must not print success."""
    assert _mod.main(["--repo-root", str(tmp_path)]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_main_fails_loud_when_the_unreleased_heading_is_gone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit-1 path a release operator is most likely to meet.

    Release Phase 2 renames ``## [Unreleased]`` before adding a fresh one, so
    this is a real state of the file rather than a corrupted one — and it is the
    branch whose stderr wording someone reads mid-release. Tested through
    ``main()`` because that is what ``lint`` and ``docs-gate`` run.
    """
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.31.0] - 2026-09-01\n\n- BK-100: **Breaking** — x\n", encoding="utf-8"
    )
    _migration(tmp_path)
    assert _mod.main(["--repo-root", str(tmp_path)]) == 1
    assert "no '## [Unreleased]' section" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The real tree
# --------------------------------------------------------------------------- #


def test_the_repository_satisfies_its_own_gate() -> None:
    assert _mod.collect_violations(_REPO_ROOT / "CHANGELOG.md", _REPO_ROOT / "docs-src/reference/migration.md") == []


def test_the_parser_agrees_with_a_differently_derived_set_over_the_real_changelog() -> None:
    """Distinguish "no violations" from "matched nothing" against the live file.

    Every other case here uses a synthetic fixture, so a parser that matched
    zero entries -- a collapsed section boundary, a narrowed grammar, the
    Phase 1 condensed shape -- would satisfy all of them at once.

    **The derivation here uses no ID grammar at all**, which is the point.
    An earlier version of this case re-implemented ``_ENTRY_RE`` verbatim and so
    went blind on exactly the inputs the implementation went blind on: both
    fail-opens review round 1 found -- the suffixed ID and the compound prefix --
    would have produced two empty lists and passed. That is
    [DRIFT-RULES Rule 8](../../sdd/DRIFT-RULES.md#independence): "verify
    independence of derivation path; never assume it ... Independent authors do
    not produce independent errors" -- and it was not even two authors.

    So the expected set is built by *position*: take the lines in the window
    that contain the marker at all, and keep the ones where it opens the entry
    body, splitting on the first ``": "`` rather than matching an ID. Whatever
    the ID looks like, this sees the entry.
    """
    lines = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("## [Unreleased]")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## [")), len(lines))

    expected: list[str] = []
    for line in lines[start:end]:
        if not line.startswith("- ") or "**Breaking**" not in line:
            continue
        head, sep, body = line.partition(": ")
        if sep and body.startswith("**Breaking**"):
            expected.append(head[2:])

    if not expected:
        pytest.skip(
            "[Unreleased] carries no entry opening with the marker. That is a normal "
            "state -- a release window with no breaking change, or Phase 1 after "
            "condensation -- and the module docstring declares the second as an "
            "accepted blind window, so it must not be a failure here."
        )
    assert [e.entry_id for e in _mod.marked_entries(_REPO_ROOT / "CHANGELOG.md")] == expected
