"""Unit tests for scripts/check_breaking_migration_link.py.

The gate exists because the v0.31.0 window shipped three `**Breaking**`
entries and one migration section: BK-357 wrote the section, BUG-248 and
BK-324 did not, and nothing noticed. The first two cases below reproduce
that pair exactly -- a linked entry passes, an unlinked one fails -- and
the rest pin the boundaries where a cheaper implementation would have
been wrong: keying on the release section rather than the whole file,
and ignoring entries that carry no marker.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_breaking_migration_link.py"

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


def test_a_marked_entry_carrying_the_link_passes(tmp_path: Path) -> None:
    """BK-357's shape: marked, and it wrote its own section."""
    changelog = _changelog(tmp_path, f"- BK-357: **Breaking** — seeking now raises. Upgrade path in the {_LINK}.")
    assert _mod.collect_violations(changelog) == []


def test_a_marked_entry_without_the_link_is_a_violation(tmp_path: Path) -> None:
    """BUG-248's shape: the defect the gate was written for."""
    changelog = _changelog(tmp_path, "- BUG-248: **Breaking** — an absent drive now reads as an absent path")
    violations = _mod.collect_violations(changelog)
    assert [v.entry_id for v in violations] == ["BUG-248"]
    assert violations[0].line == 5, "the reported line must point at the entry, not the section"


def test_an_unmarked_entry_is_ignored_however_breaking_it_reads(tmp_path: Path) -> None:
    """The softer half is a human judgement, and the gate must not pretend otherwise.

    BUG-259 changed what a stored ``base_path`` value means and carries a
    ``**Fix**`` marker. Phase 1 decides that class; a marker-keyed gate
    cannot, and firing here would make the miss-rate bound in the module
    docstring false.
    """
    changelog = _changelog(tmp_path, "- BUG-259: **Fix** — a write to the store root is now refused")
    assert _mod.collect_violations(changelog) == []


def test_an_entry_that_merely_mentions_the_marker_is_not_marked(tmp_path: Path) -> None:
    """The gate's own first false positive, pinned so it cannot come back.

    An unanchored substring test flags any entry whose prose contains the
    marker. This gate's own CHANGELOG stub does -- it describes the rule it
    enforces -- and the full gate failed on it the first time it ran. The
    convention puts the marker at the head of the entry body, so the match
    is anchored there.
    """
    changelog = _changelog(
        tmp_path,
        "- BUG-262: Gate that every unreleased `**Breaking**` entry links its upgrade path",
    )
    assert _mod.collect_violations(changelog) == []


def test_a_released_unlinked_entry_is_out_of_scope(tmp_path: Path) -> None:
    """Only the current window is checked; Phase 2 drops the marker anyway.

    Scoping to the whole file would fail on master from the first commit,
    because released sections keep prose that predates this rule.
    """
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — something. Upgrade path in the " + _LINK + ".",
        released="- **Old thing** (BK-100): **Breaking** — no link here",
    )
    assert _mod.collect_violations(changelog) == []


def test_a_relative_link_satisfies_the_rule(tmp_path: Path) -> None:
    """An entry authored against the repo tree, not the published site."""
    changelog = _changelog(
        tmp_path,
        "- BK-360: **Breaking** — something. See [the guide](docs-src/reference/migration.md).",
    )
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


def test_the_repository_satisfies_its_own_gate() -> None:
    """The gate must be green on the tree that ships it."""
    repo_root = Path(__file__).resolve().parents[2]
    assert _mod.collect_violations(repo_root / "CHANGELOG.md") == []
