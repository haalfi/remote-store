"""Unit tests for scripts/gen_adr_digest.py."""

from __future__ import annotations

import sys
from pathlib import Path

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
    with_table: bool = True,
    with_decision: bool = True,
) -> str:
    """Build an ADR body: visible Status table + a full ## Decision section.

    The decision is the whole ## Decision section (up to the next ##), so the
    trailing ## Consequences content must never leak into it.
    """

    def _cell(items: list[str] | None) -> str:
        return ", ".join(items) if items else "—"

    table = (
        "| Field         | Value |\n"
        "| ------------- | ----- |\n"
        f"| Status        | {status} |\n"
        f"| Supersedes    | {_cell(supersedes)} |\n"
        f"| Superseded by | {_cell(superseded_by)} |\n"
        f"| Amends        | {_cell(amends)} |\n"
        if with_table
        else ""
    )
    decision_section = f"## Decision\n\n{decision}\n\n" if with_decision else ""
    return (
        f"# ADR-{number}: {title}\n\n"
        "## Status\n\n"
        f"{table}\n"
        f"{decision_section}"
        "## Consequences\n\n"
        "Trailing content that must not be captured in the decision.\n"
    )


def _write(adr_dir: Path, number: str, **kwargs) -> Path:
    slug = kwargs.pop("slug", "some-decision")
    title = kwargs.pop("title", "A Decision")
    path = adr_dir / f"{number}-{slug}.md"
    path.write_text(_adr_text(number, title, **kwargs), encoding="utf-8")
    return path


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
        adr, errors = _mod.parse(path)
        assert errors == []
        assert adr is not None
        assert adr.id == "ADR-0017"
        assert adr.number == "0017"
        assert adr.title == "Seekable read on the store API"  # ADR-NNNN prefix stripped
        assert adr.status == "Accepted"
        assert adr.supersedes == ["ADR-0016"]
        assert adr.superseded_by == []  # em-dash cell -> empty
        assert adr.decision == "**We put seekable read on the Store API.**"

    def test_missing_status_table_yields_none(self, tmp_path):
        path = _write(tmp_path, "0003", with_table=False)
        adr, errors = _mod.parse(path)
        assert adr is None
        assert any("no metadata table" in e for e in errors)

    def test_missing_decision_section_is_hard_error(self, tmp_path):
        path = _write(tmp_path, "0004", with_decision=False)
        adr, errors = _mod.parse(path)
        assert adr is not None  # still placeable, but flagged
        assert any("missing or empty ## Decision section" in e for e in errors)

    def test_bad_status_flagged(self, tmp_path):
        path = _write(tmp_path, "0005", status="Approved")
        _, errors = _mod.parse(path)
        assert any("not in ['Proposed', 'Accepted', 'Superseded']" in e for e in errors)

    def test_full_decision_section_extracted(self, tmp_path):
        # The whole ## Decision section is the decision — headline AND the
        # resolution rules that flesh it out (the PR #909 chat point).
        decision = "Headline decision.\n\nResolution rules:\n\n1. first rule\n2. second rule"
        path = _write(tmp_path, "0002", decision=decision)
        adr, _ = _mod.parse(path)
        assert "Headline decision." in adr.decision
        assert "Resolution rules:" in adr.decision
        assert "1. first rule" in adr.decision
        assert "2. second rule" in adr.decision

    def test_decision_stops_at_next_section(self, tmp_path):
        path = _write(tmp_path, "0002")
        adr, _ = _mod.parse(path)
        assert "must not be captured" not in adr.decision  # ## Consequences excluded

    def test_internal_headings_demoted(self, tmp_path):
        # A ### sub-heading inside Decision would collide with the digest's own
        # per-ADR ### heading, so it is pushed down (by 2 -> #####).
        decision = "Lead.\n\n### Tier 1\n\nbody\n\n#### Deep\n\nmore"
        path = _write(tmp_path, "0009", decision=decision)
        adr, _ = _mod.parse(path)
        assert "##### Tier 1" in adr.decision
        assert "###### Deep" in adr.decision  # #### + 2, capped at 6
        assert "### Tier 1" not in adr.decision.replace("##### Tier 1", "")

    def test_headings_in_code_blocks_not_demoted(self, tmp_path):
        decision = "Lead.\n\n```python\n# a comment, not a heading\n```"
        path = _write(tmp_path, "0009", decision=decision)
        adr, _ = _mod.parse(path)
        assert "# a comment, not a heading" in adr.decision

    def test_section_split_is_code_fence_aware(self, tmp_path):
        # A `## ...` inside a fenced code block must not end the section early
        # (PR #909 review: the splitter must match _demote_headings' fence awareness).
        decision = "Lead decision.\n\n```markdown\n## Not a real section\n```\n\nStill the decision."
        path = _write(tmp_path, "0009", decision=decision)
        adr, _ = _mod.parse(path)
        assert "## Not a real section" in adr.decision  # code-fenced, not a boundary
        assert "Still the decision." in adr.decision  # content after the fenced ## survives
        assert "must not be captured" not in adr.decision  # real ## Consequences still ends it

    def test_multiple_links_in_one_cell(self, tmp_path):
        path = _write(tmp_path, "0020", supersedes=["ADR-0018", "ADR-0019"])
        adr, _ = _mod.parse(path)
        assert adr.supersedes == ["ADR-0018", "ADR-0019"]

    def test_table_outside_status_section_is_ignored(self, tmp_path):
        # A lookalike table under a different heading must not be read as metadata.
        path = tmp_path / "0005-stray.md"
        path.write_text(
            "# ADR-0005: Stray\n\n## Context\n\n| Status | Accepted |\n| --- | --- |\n\n## Decision\n\nDo it.\n",
            encoding="utf-8",
        )
        adr, errors = _mod.parse(path)
        assert adr is None
        assert any("no metadata table" in e for e in errors)


# ---------------------------------------------------------------------------
# hard_errors (dangling graph refs)
# ---------------------------------------------------------------------------


class TestHardErrors:
    def test_dangling_supersedes_target(self, tmp_path):
        _write(tmp_path, "0020", supersedes=["ADR-0099"])
        adrs, _ = _mod.load_all(tmp_path)
        errors = _mod.hard_errors(adrs)
        assert any("supersedes points at unknown ADR 'ADR-0099'" in e for e in errors)

    def test_valid_graph_has_no_hard_errors(self, tmp_path):
        _write(tmp_path, "0016", slug="old", status="Superseded", superseded_by=["ADR-0017"])
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path)
        assert _mod.hard_errors(adrs) == []


# ---------------------------------------------------------------------------
# drift_warnings (the headline: one-sided supersession)
# ---------------------------------------------------------------------------


class TestDriftWarnings:
    def test_supersedes_accepted_target_warns(self, tmp_path):
        # ADR-0017 retires ADR-0016, but 0016 is still marked Accepted.
        _write(tmp_path, "0016", slug="old", status="Accepted")
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path)
        warnings = _mod.drift_warnings(adrs)
        assert any("ADR-0017 supersedes ADR-0016" in w and "Accepted" in w for w in warnings)

    def test_consistent_supersession_no_warning(self, tmp_path):
        _write(tmp_path, "0016", slug="old", status="Superseded", superseded_by=["ADR-0017"])
        _write(tmp_path, "0017", slug="new", supersedes=["ADR-0016"])
        adrs, _ = _mod.load_all(tmp_path)
        assert _mod.drift_warnings(adrs) == []

    def test_one_sided_superseded_by_warns(self, tmp_path):
        # 0006 declares superseded-by 0007, but 0007 omits the matching supersedes
        # (the ADR-0006/0007 asymmetry from PR #909 review).
        _write(tmp_path, "0006", slug="old", status="Superseded", superseded_by=["ADR-0007"])
        _write(tmp_path, "0007", slug="new")  # supersedes: —
        adrs, _ = _mod.load_all(tmp_path)
        warnings = _mod.drift_warnings(adrs)
        assert any("one-sided edge" in w and "ADR-0006" in w for w in warnings)

    def test_one_sided_supersedes_warns(self, tmp_path):
        # Mirror direction: superseding side declares the edge, target omits it.
        _write(tmp_path, "0019", slug="old", status="Superseded")  # superseded-by: —
        _write(tmp_path, "0020", slug="new", supersedes=["ADR-0019"])
        adrs, _ = _mod.load_all(tmp_path)
        warnings = _mod.drift_warnings(adrs)
        assert any("one-sided edge" in w and "ADR-0020" in w for w in warnings)

    def test_superseded_without_record_warns(self, tmp_path):
        _write(tmp_path, "0006", status="Superseded", superseded_by=[])
        adrs, _ = _mod.load_all(tmp_path)
        warnings = _mod.drift_warnings(adrs)
        assert any("nothing records what superseded it" in w for w in warnings)

    def test_amends_does_not_require_status_change(self, tmp_path):
        # A clause-level amend leaves the target fully in force.
        _write(tmp_path, "0008", slug="ext", status="Accepted")
        _write(tmp_path, "0013", slug="drop", amends=["ADR-0008"])
        adrs, _ = _mod.load_all(tmp_path)
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
        adrs, _ = _mod.load_all(tmp_path)
        out = _mod.render(adrs)
        assert "## Accepted" in out
        assert "## Superseded" in out
        # Accepted group precedes Superseded group.
        assert out.index("## Accepted") < out.index("## Superseded")
        assert "### [ADR-0001](0001-first.md): First" in out
        assert "Decision one." in out
        assert "> superseded by ADR-0007." in out

    def test_amends_edge_rendered(self, tmp_path):
        _write(tmp_path, "0008", slug="ext")
        _write(tmp_path, "0013", slug="drop", amends=["ADR-0008"])
        adrs, _ = _mod.load_all(tmp_path)
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


# ---------------------------------------------------------------------------
# The real ADR tree (PR #909 review, finding 4): guard the committed digest
# against the actual sdd/adrs so a forgotten fence/table or a stale DIGEST.md
# fails a test, even though gen-adr-digest-check is not wired into the gate.
# ---------------------------------------------------------------------------


class TestRealAdrs:
    def test_real_adrs_parse_without_hard_errors(self):
        adrs, errors = _mod.load_all(_mod.ADR_DIR)
        assert errors == []
        assert _mod.hard_errors(adrs) == []
        assert len(adrs) >= 30

    def test_real_supersession_graph_has_no_drift(self):
        adrs, _ = _mod.load_all(_mod.ADR_DIR)
        assert _mod.drift_warnings(adrs) == []

    def test_committed_digest_matches_fresh_render(self):
        adrs, _ = _mod.load_all(_mod.ADR_DIR)
        assert _mod.DIGEST.read_text(encoding="utf-8") == _mod.render(adrs)
