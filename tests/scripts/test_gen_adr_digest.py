"""Unit tests for scripts/gen_adr_digest.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gen_adr_digest as _mod  # noqa: E402


def _adr_text(
    number: str,
    title: str,
    *,
    status: str = "Accepted",
    supersedes: list[str] | None = None,
    superseded_by: list[str] | None = None,
    amends: list[str] | None = None,
    decision: str = "We will do the sensible thing.",
    with_meta: bool = True,
    with_fence: bool = True,
) -> str:
    """Build a minimal ADR body with the marker comments."""

    def _flow(items: list[str] | None) -> str:
        return "[" + ", ".join(items or []) + "]"

    meta = (
        (
            "<!-- adr:meta\n"
            f"status: {status}\n"
            f"supersedes: {_flow(supersedes)}\n"
            f"superseded-by: {_flow(superseded_by)}\n"
            f"amends: {_flow(amends)}\n"
            "-->\n\n"
        )
        if with_meta
        else ""
    )
    body_decision = f"<!-- adr:decision -->\n{decision}\n<!-- /adr:decision -->\n" if with_fence else decision + "\n"
    return (
        f"# ADR-{number}: {title}\n\n"
        f"{meta}"
        "## Status\n\n"
        f"{status}\n\n"
        "## Decision\n\n"
        f"{body_decision}\n"
        "Some trailing explanation that must not be captured.\n"
    )


def _write(adr_dir: Path, number: str, **kwargs) -> Path:
    slug = kwargs.pop("slug", "some-decision")
    path = adr_dir / f"{number}-{slug}.md"
    path.write_text(_adr_text(number, kwargs.pop("title", "A Decision"), **kwargs), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_git_dates(monkeypatch):
    # Keep the digest deterministic and offline: no git shell-out in tests.
    monkeypatch.setattr(_mod, "_git_date", lambda _p: "")


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


class TestParse:
    def test_extracts_all_fields(self, tmp_path):
        path = _write(
            tmp_path,
            "0017",
            title="Seekable read on the store API",
            supersedes=["ADR-0016"],
            decision="**We put seekable read on the Store API.**",
        )
        adr, errors = _mod.parse(path, with_date=False)
        assert errors == []
        assert adr is not None
        assert adr.id == "ADR-0017"
        assert adr.number == "0017"
        assert adr.title == "Seekable read on the store API"  # ADR-NNNN prefix stripped
        assert adr.status == "Accepted"
        assert adr.supersedes == ["ADR-0016"]
        assert adr.decision == "**We put seekable read on the Store API.**"

    def test_missing_meta_block_yields_none(self, tmp_path):
        path = _write(tmp_path, "0003", with_meta=False)
        adr, errors = _mod.parse(path, with_date=False)
        assert adr is None
        assert any("no metadata" in e for e in errors)

    def test_missing_decision_fence_is_hard_error(self, tmp_path):
        path = _write(tmp_path, "0004", with_fence=False)
        adr, errors = _mod.parse(path, with_date=False)
        assert adr is not None  # still placeable, but flagged
        assert any("missing <!-- adr:decision --> fence" in e for e in errors)

    def test_bad_status_flagged(self, tmp_path):
        path = _write(tmp_path, "0005", status="Approved")
        _, errors = _mod.parse(path, with_date=False)
        assert any("not in ['Proposed', 'Accepted', 'Superseded']" in e for e in errors)

    def test_decision_whitespace_is_collapsed(self, tmp_path):
        path = _write(tmp_path, "0009", decision="line one\n  line two")
        adr, _ = _mod.parse(path, with_date=False)
        assert adr.decision == "line one line two"


def _adr_table_text(
    number: str,
    title: str,
    *,
    status: str = "Accepted",
    supersedes: str = "—",
    superseded_by: str = "—",
    amends: str = "—",
    decision: str = "We will do the sensible thing.",
) -> str:
    """Build an ADR whose metadata is a visible key/value table (not a comment)."""
    return (
        f"# ADR-{number}: {title}\n\n"
        "## Status\n\n"
        "| Field | Value |\n"
        "| --- | --- |\n"
        f"| Status | {status} |\n"
        f"| Supersedes | {supersedes} |\n"
        f"| Superseded by | {superseded_by} |\n"
        f"| Amends | {amends} |\n\n"
        "## Decision\n\n"
        f"<!-- adr:decision -->\n{decision}\n<!-- /adr:decision -->\n"
    )


class TestTableForm:
    def test_table_metadata_parsed(self, tmp_path):
        path = tmp_path / "0017-seekable.md"
        path.write_text(
            _adr_table_text("0017", "Seekable read", supersedes="ADR-0016"),
            encoding="utf-8",
        )
        adr, errors = _mod.parse(path, with_date=False)
        assert errors == []
        assert adr.status == "Accepted"
        assert adr.supersedes == ["ADR-0016"]
        assert adr.superseded_by == []  # em-dash cell -> empty

    def test_table_and_comment_yield_same_data(self, tmp_path):
        table = tmp_path / "0016-table.md"
        table.write_text(_adr_table_text("0016", "Seekable", supersedes="ADR-0009"), encoding="utf-8")
        comment = _write(tmp_path, "0016", slug="comment", supersedes=["ADR-0009"])
        a_table, _ = _mod.parse(table, with_date=False)
        a_comment, _ = _mod.parse(comment, with_date=False)
        assert a_table.supersedes == a_comment.supersedes == ["ADR-0009"]
        assert a_table.status == a_comment.status

    def test_multiple_links_in_one_cell(self, tmp_path):
        path = tmp_path / "0020-multi.md"
        path.write_text(
            _adr_table_text("0020", "Multi", supersedes="ADR-0018, ADR-0019"),
            encoding="utf-8",
        )
        adr, _ = _mod.parse(path, with_date=False)
        assert adr.supersedes == ["ADR-0018", "ADR-0019"]

    def test_table_outside_status_section_is_ignored(self, tmp_path):
        # A lookalike table under a different heading must not be read as metadata.
        path = tmp_path / "0005-stray.md"
        path.write_text(
            "# ADR-0005: Stray\n\n"
            "## Context\n\n"
            "| Status | Accepted |\n| --- | --- |\n\n"
            "## Decision\n\n<!-- adr:decision -->\nDo it.\n<!-- /adr:decision -->\n",
            encoding="utf-8",
        )
        adr, errors = _mod.parse(path, with_date=False)
        assert adr is None
        assert any("no metadata" in e for e in errors)


# ---------------------------------------------------------------------------
# hard_errors (dangling graph refs)
# ---------------------------------------------------------------------------


class TestHardErrors:
    def test_dangling_supersedes_target(self, tmp_path):
        _write(tmp_path, "0020", supersedes=["ADR-0099"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        errors = _mod.hard_errors(adrs)
        assert any("supersedes points at unknown ADR 'ADR-0099'" in e for e in errors)

    def test_valid_graph_has_no_hard_errors(self, tmp_path):
        _write(tmp_path, "0016", slug="old")
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        assert _mod.hard_errors(adrs) == []


# ---------------------------------------------------------------------------
# drift_warnings (the headline: one-sided supersession)
# ---------------------------------------------------------------------------


class TestDriftWarnings:
    def test_supersedes_accepted_target_warns(self, tmp_path):
        # ADR-0017 retires ADR-0016, but 0016 is still marked Accepted.
        _write(tmp_path, "0016", slug="old", status="Accepted")
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        warnings = _mod.drift_warnings(adrs)
        assert any("ADR-0017 supersedes ADR-0016" in w and "Accepted" in w for w in warnings)

    def test_consistent_supersession_no_warning(self, tmp_path):
        _write(tmp_path, "0016", slug="old", status="Superseded", superseded_by=["ADR-0017"])
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        assert _mod.drift_warnings(adrs) == []

    def test_superseded_without_record_warns(self, tmp_path):
        _write(tmp_path, "0006", status="Superseded", superseded_by=[])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        warnings = _mod.drift_warnings(adrs)
        assert any("nothing records what superseded it" in w for w in warnings)

    def test_amends_does_not_require_status_change(self, tmp_path):
        # A clause-level amend leaves the target fully in force.
        _write(tmp_path, "0008", slug="ext", status="Accepted")
        _write(tmp_path, "0013", slug="drop", amends=["ADR-0008"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        assert _mod.drift_warnings(adrs) == []


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


class TestRender:
    def test_groups_by_status_and_links_back(self, tmp_path):
        _write(tmp_path, "0001", title="First", slug="first", decision="Decision one.")
        _write(
            tmp_path,
            "0006",
            title="Old",
            slug="old",
            status="Superseded",
            superseded_by=["ADR-0007"],
            decision="Decision six.",
        )
        _write(tmp_path, "0007", title="New", slug="new", decision="Decision seven.")
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        out = _mod.render(adrs)
        assert "## Accepted" in out
        assert "## Superseded" in out
        # Accepted group precedes Superseded group.
        assert out.index("## Accepted") < out.index("## Superseded")
        assert "### [ADR-0001](0001-first.md) — First" in out
        assert "Decision one." in out
        assert "> superseded by ADR-0007." in out

    def test_amends_edge_rendered(self, tmp_path):
        _write(tmp_path, "0008", slug="ext")
        _write(tmp_path, "0013", slug="drop", amends=["ADR-0008"])
        adrs, _ = _mod.load_all(tmp_path, with_date=False)
        out = _mod.render(adrs)
        assert "amends ADR-0008 (clause)" in out


# ---------------------------------------------------------------------------
# generate / check
# ---------------------------------------------------------------------------


def _setup_repo(tmp_path, monkeypatch) -> Path:
    adr_dir = tmp_path / "sdd" / "adrs"
    adr_dir.mkdir(parents=True)
    digest = adr_dir / "DIGEST.md"
    monkeypatch.setattr(_mod, "ROOT", tmp_path)
    monkeypatch.setattr(_mod, "ADR_DIR", adr_dir)
    monkeypatch.setattr(_mod, "DIGEST", digest)
    return adr_dir


class TestGenerate:
    def test_writes_digest(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0001", slug="first")
        assert _mod.generate() == 0
        assert _mod.DIGEST.exists()
        assert "wrote" in capsys.readouterr().out.lower()

    def test_is_idempotent(self, tmp_path, monkeypatch):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0001", slug="first")
        _mod.generate()
        first = _mod.DIGEST.read_text(encoding="utf-8")
        _mod.generate()
        assert _mod.DIGEST.read_text(encoding="utf-8") == first

    def test_refuses_on_hard_error(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0020", slug="new", supersedes=["ADR-0099"])
        assert _mod.generate() == 1
        assert not _mod.DIGEST.exists()
        assert "ERROR" in capsys.readouterr().err


class TestCheck:
    def test_clean_returns_zero(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0001", slug="first")
        _mod.generate()
        capsys.readouterr()
        assert _mod.check() == 0
        assert "digest current" in capsys.readouterr().out

    def test_stale_digest_returns_one(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0001", slug="first")
        _mod.generate()
        _write(adr_dir, "0002", slug="second")  # new ADR, digest now stale
        capsys.readouterr()
        assert _mod.check() == 1
        assert "STALE" in capsys.readouterr().out

    def test_drift_returns_one(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0016", slug="old", status="Accepted")
        _write(adr_dir, "0017", slug="new", supersedes=["ADR-0016"])
        _mod.generate()  # digest itself is fresh...
        capsys.readouterr()
        assert _mod.check() == 1  # ...but the drift still fails the gate
        assert "DRIFT" in capsys.readouterr().out

    def test_missing_digest_returns_one(self, tmp_path, monkeypatch, capsys):
        adr_dir = _setup_repo(tmp_path, monkeypatch)
        _write(adr_dir, "0001", slug="first")
        assert _mod.check() == 1
        assert "not found" in capsys.readouterr().out
