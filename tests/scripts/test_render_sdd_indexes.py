"""Tests for the status and date index columns in scripts/docs/{scan,render}.py.

``SddKind.dated`` (declared per kind in ``docs-src/_path_rules.yml``) adds a
"Date (as of)" column to that kind's index table and lists it newest first.
Research is the only dated kind today: a survey ages, so a reader needs to see
how current it is.

The reordering is scoped to the index table — nav and the design landing page
keep scan (filename) order — so these tests pin both halves.

``SddKind.status`` adds a status column whose cell is each document's own
status (DOCFRAME-010): the ADR metadata table, or the RFC ``## Status``
paragraph or ``**Status:**`` header line. BUG-338: the cell was a per-kind
constant, so every RFC read "Proposed" and every ADR "Accepted".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.os_sensitive

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def mods():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import docs.render as render
    import docs.scan as scan

    return scan, render


# ---------------------------------------------------------------------------
# Header date parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Research: T\n\n**Date:** 2026-03-24\n", "2026-03-24"),
        # Real docs carry the date below other metadata lines (line 6 in
        # research-google-docstring-migration.md).
        ("# T\n\n**Item IDs:** ID-064\n**Related:** x\n**Date:** 2026-03-13\n", "2026-03-13"),
        ("# T\n\nNo date here.\n", None),
        # A date in the body (appendices carry their own) must not be picked up.
        ("# T\n\n---\n\n**Date:** 2026-01-01\n", None),
        ("# T\n\n**Date:** March 2026\n", None),
    ],
)
def test_parse_header_date(mods, text, expected):
    scan, _ = mods
    assert scan._parse_header_date(text) == expected


def test_parse_header_date_ignores_late_body_date(mods):
    """A **Date:** past the header window is body content, not the doc's date."""
    scan, _ = mods
    text = "# T\n" + "\nfiller\n" * 20 + "\n**Date:** 2026-01-01\n"
    assert scan._parse_header_date(text) is None


def test_scan_kind_parses_date_only_for_dated_kinds(mods, tmp_path):
    scan, _ = mods
    d = tmp_path / "sdd" / "research"
    d.mkdir(parents=True)
    (d / "research-a.md").write_text("# Research: A\n\n**Date:** 2026-05-01\n", encoding="utf-8")

    dated = scan.SddKind("research", "sdd/research", "Research", glob="research-*.md", numbered=False, dated=True)
    undated = scan.SddKind("research", "sdd/research", "Research", glob="research-*.md", numbered=False)

    assert scan._scan_kind(tmp_path, dated)[0].date == "2026-05-01"
    assert scan._scan_kind(tmp_path, undated)[0].date is None


# ---------------------------------------------------------------------------
# Row ordering and the date column
# ---------------------------------------------------------------------------


def _entry(scan, kind, slug, title, date):
    return scan.SddEntry(number=slug, slug=slug, title=title, source=Path(slug), kind=kind, date=date)


@pytest.fixture
def dated_kind(mods):
    scan, _ = mods
    return scan.SddKind("research", "sdd/research", "Research", glob="research-*.md", numbered=False, dated=True)


def test_index_order_is_newest_first(mods, dated_kind):
    scan, render = mods
    entries = [
        _entry(scan, dated_kind, "old", "Old", "2026-03-02"),
        _entry(scan, dated_kind, "new", "New", "2026-08-30"),
        _entry(scan, dated_kind, "mid", "Mid", "2026-05-11"),
    ]
    assert [e.slug for e in render._index_order(dated_kind, entries)] == ["new", "mid", "old"]


def test_index_order_breaks_same_date_ties_by_title(mods, dated_kind):
    """Three research docs share 2026-03-24; the table must not shuffle between builds."""
    scan, render = mods
    entries = [
        _entry(scan, dated_kind, "c", "Seekable Read", "2026-03-24"),
        _entry(scan, dated_kind, "a", "Azure PyArrow", "2026-03-24"),
        _entry(scan, dated_kind, "b", "Benchmark Suite", "2026-03-24"),
    ]
    assert [e.slug for e in render._index_order(dated_kind, entries)] == ["a", "b", "c"]


def test_index_order_puts_undated_last(mods, dated_kind):
    scan, render = mods
    entries = [
        _entry(scan, dated_kind, "none", "No Date", None),
        _entry(scan, dated_kind, "old", "Old", "2026-03-02"),
    ]
    assert [e.slug for e in render._index_order(dated_kind, entries)] == ["old", "none"]


def test_index_order_leaves_undated_kinds_in_scan_order(mods):
    scan, render = mods
    kind = scan.SddKind("adrs", "sdd/adrs", "ADRs", status=True)
    entries = [
        _entry(scan, kind, "0002-b", "B", None),
        _entry(scan, kind, "0001-a", "A", None),
    ]
    assert render._index_order(kind, entries) == entries


def test_index_row_appends_date_cell(mods, dated_kind):
    scan, render = mods
    row = render._index_row(dated_kind, _entry(scan, dated_kind, "research-a", "A", "2026-05-01"))
    assert row == "| A | [A](research-a.md) | 2026-05-01 |"


def test_index_row_renders_em_dash_for_missing_date(mods, dated_kind):
    """CLAUDE.md § Response style: — is the table N/A value, never '--' or 'No'."""
    scan, render = mods
    row = render._index_row(dated_kind, _entry(scan, dated_kind, "research-a", "A", None))
    assert row.endswith("| — |")


def test_index_row_has_no_date_cell_for_undated_kind(mods):
    scan, render = mods
    kind = scan.SddKind("adrs", "sdd/adrs", "ADRs", status=True)
    entry = scan.SddEntry(number="0001", slug="0001-a", title="A", source=Path("x"), kind=kind, status="Accepted")
    assert render._index_row(kind, entry) == "| 0001 | [A](0001-a.md) | Accepted |"


# ---------------------------------------------------------------------------
# Status column: each document's own status (DOCFRAME-010, BUG-338)
# ---------------------------------------------------------------------------


def _adr(status: str) -> str:
    return (
        "# ADR-0001: T\n\n## Status\n\n| Field | Value |\n| ----- | ----- |\n"
        f"| Status | {status} |\n| Supersedes | — |\n\n## Decision\n\nD.\n"
    )


@pytest.mark.spec("DOCFRAME-010")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # `## Status` paragraph forms, one per shape the live RFCs use.
        ("# RFC-0001: T\n\n## Status\n\nAccepted\n\n## Summary\n", "Accepted"),
        ("# RFC-0021: T\n\n## Status\n\nAccepted, 2026-10-13, by the maintainer.\n", "Accepted"),
        ("# RFC-0015: T\n\n## Status\n\nDraft. Tracked as **BK-384**.\n", "Draft"),
        ("# RFC-0017: T\n\n## Status\n\n**Accepted**, in BK-394's PR, together with\n", "Accepted"),
        ("# RFC-0009: T\n\n## Status\n\nSuperseded by [ADR-0020](../adrs/x.md)\n", "Superseded"),
        ("# RFC-0003: T\n\n## Status\n\nAccepted (implemented via ID-208).\n", "Accepted"),
        ("# RFC-0099: T\n\n## Status\n\nUnder Review since 2026-10-01.\n", "Under Review"),
        ("# RFC-0099: T\n\n## Status\n\nRejected: no measurable gain.\n", "Rejected"),
        # Older header-line form (rfc-0005/6/7).
        ("# RFC-0006: T\n\n**Status:** Accepted (implemented via BK-010)\n\n---\n", "Accepted"),
        # A `**Status: ...**` line in the body is a finding's verdict, not the RFC's.
        ("# RFC-0007: T\n\n---\n\n**Status: Compliant.** All pages ...\n", None),
        # Off-vocabulary, or no status at all, is None, never the raw prose.
        ("# RFC-0011: T\n\n## Status\n\nImplemented\n", None),
        ("# RFC-0099: T\n\n## Summary\n\nNo status.\n", None),
        # A word that merely starts like a term is not that term.
        ("# RFC-0099: T\n\n## Status\n\nDrafted 2026-10-12.\n", None),
    ],
)
def test_rfc_status_reads_the_status_keyword(mods, text, expected):
    scan, _ = mods
    assert scan._rfc_status(text) == expected


@pytest.mark.spec("DOCFRAME-010")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_adr("Accepted"), "Accepted"),
        (_adr("Superseded"), "Superseded"),
        (_adr("Proposed"), "Proposed"),
        (_adr("Withdrawn"), None),
        ("# ADR-0001: T\n\n## Decision\n\nNo status table.\n", None),
    ],
)
def test_adr_status_reads_the_metadata_table(mods, text, expected):
    scan, _ = mods
    assert scan._adr_status(text) == expected


@pytest.mark.spec("DOCFRAME-010")
def test_scan_kind_reads_each_documents_own_status(mods, tmp_path):
    scan, _ = mods
    adrs = tmp_path / "sdd" / "adrs"
    rfcs = tmp_path / "sdd" / "rfcs"
    adrs.mkdir(parents=True)
    rfcs.mkdir(parents=True)
    (adrs / "0001-a.md").write_text(_adr("Accepted"), encoding="utf-8")
    (adrs / "0002-b.md").write_text(_adr("Superseded"), encoding="utf-8")
    (rfcs / "rfc-0001-a.md").write_text("# RFC-0001: A\n\n## Status\n\nAccepted\n", encoding="utf-8")
    (rfcs / "rfc-0002-b.md").write_text("# RFC-0002: B\n\n## Status\n\nDraft. More.\n", encoding="utf-8")
    (rfcs / "rfc-0003-c.md").write_text("# RFC-0003: C\n\nNo status.\n", encoding="utf-8")

    adr_kind = scan.SddKind("adrs", "sdd/adrs", "ADRs", status=True)
    rfc_kind = scan.SddKind("rfcs", "sdd/rfcs", "RFCs", glob="rfc-*.md", status=True)
    no_status = scan.SddKind("rfcs", "sdd/rfcs", "RFCs", glob="rfc-*.md")

    assert [e.status for e in scan._scan_kind(tmp_path, adr_kind)] == ["Accepted", "Superseded"]
    assert [e.status for e in scan._scan_kind(tmp_path, rfc_kind)] == ["Accepted", "Draft", None]
    assert [e.status for e in scan._scan_kind(tmp_path, no_status)] == [None, None, None]


@pytest.mark.spec("DOCFRAME-010")
def test_index_row_renders_each_documents_status(mods, tmp_path, monkeypatch):
    """The BUG-338 reproduction: two RFCs with different statuses render differently."""
    scan, render = mods
    kind = scan.SddKind("rfcs", "sdd/rfcs", "RFCs", glob="rfc-*.md", status=True)
    monkeypatch.setattr(render, "SDD_KINDS", (kind,))
    design = tmp_path / "explanation" / "design"
    (design / "rfcs").mkdir(parents=True)
    (design / "rfcs" / "_index.tmpl").write_text("| # | RFC | Status |\n{{ rfc_rows }}\n", encoding="utf-8")
    (design / "_index.tmpl").write_text("{{ rfc_links }}\n", encoding="utf-8")

    def rfc(num, title, status):
        return scan.SddEntry(number=num, slug=f"rfc-{num}-x", title=title, source=Path("x"), kind=kind, status=status)

    entries = [rfc("0001", "A", "Accepted"), rfc("0002", "B", "Draft"), rfc("0003", "C", None)]
    out: dict[str, str] = {}
    render.render_sdd_indexes(tmp_path, lambda p, t: out.__setitem__(p, t), {"rfcs": entries})
    assert out["explanation/design/rfcs/index.md"].splitlines()[1:] == [
        "| 0001 | [A](rfc-0001-x.md) | Accepted |",
        "| 0002 | [B](rfc-0002-x.md) | Draft |",
        "| 0003 | [C](rfc-0003-x.md) | — |",
    ]


@pytest.mark.spec("DOCFRAME-010")
def test_rfc_vocabulary_is_the_templates(mods):
    """The RFC vocabulary is derived from the template's Status line, not kept beside it."""
    scan, _ = mods
    template = (ROOT / "sdd" / "templates" / "rfc-template.md").read_text(encoding="utf-8")
    assert "Draft | Under Review | Accepted | Rejected | Superseded by RFC-XXXX" in template
    assert scan.STATUS_VOCABULARY["rfcs"] == ("Draft", "Under Review", "Accepted", "Rejected", "Superseded")


@pytest.mark.spec("DOCFRAME-010")
def test_adr_vocabulary_is_the_digests(mods):
    scan, _ = mods
    import gen_adr_digest

    assert scan.STATUS_VOCABULARY["adrs"] == gen_adr_digest.STATUSES


# ---------------------------------------------------------------------------
# render_sdd_indexes: table reorders, landing page does not
# ---------------------------------------------------------------------------


def test_render_sdd_indexes_sorts_table_but_not_landing_page(mods, tmp_path, monkeypatch):
    scan, render = mods
    kind = scan.SddKind("research", "sdd/research", "Research", glob="research-*.md", numbered=False, dated=True)
    monkeypatch.setattr(render, "SDD_KINDS", (kind,))

    design = tmp_path / "explanation" / "design"
    (design / "research").mkdir(parents=True)
    (design / "research" / "_index.tmpl").write_text(
        "| T | D | Date (as of) |\n{{ research_rows }}\n", encoding="utf-8"
    )
    (design / "_index.tmpl").write_text("{{ research_links }}\n", encoding="utf-8")

    entries = [  # scan order = filename order
        _entry(scan, kind, "research-a", "A", "2026-03-02"),
        _entry(scan, kind, "research-z", "Z", "2026-08-30"),
        _entry(scan, kind, "research-n", "N", None),
    ]
    out: dict[str, str] = {}
    render.render_sdd_indexes(tmp_path, lambda p, t: out.__setitem__(p, t), {"research": entries})

    index = out["explanation/design/research/index.md"]
    assert index.splitlines()[1:] == [
        "| Z | [Z](research-z.md) | 2026-08-30 |",
        "| A | [A](research-a.md) | 2026-03-02 |",
        "| N | [N](research-n.md) | — |",
    ]
    landing = out["explanation/design/index.md"]
    assert landing.splitlines()[:3] == [
        "- [A](research/research-a.md)",
        "- [Z](research/research-z.md)",
        "- [N](research/research-n.md)",
    ], "landing page keeps scan order"


# ---------------------------------------------------------------------------
# Positive control against the live repo
# ---------------------------------------------------------------------------


def test_live_research_index_is_fully_dated_and_descending(mods):
    scan, render = mods
    entries = scan.scan_all_sdd(ROOT)["research"]
    dates = [e.date for e in entries]

    assert entries, "research kind scanned no documents"
    undated = [e.slug for e in entries if e.date is None]
    assert not undated, f"research docs missing a **Date:** header: {undated}"

    kind = next(k for k in scan.SDD_KINDS if k.slug == "research")
    assert kind.dated is True
    ordered = render._index_order(kind, entries)
    # `dates` is derived from the scan, not from `ordered`, so this fails on an
    # ascending sort, no sort, a dropped entry, or a scrambled middle.
    assert [e.date for e in ordered] == sorted(dates, reverse=True)
    # Dates alone cannot see one same-date document substituted for another.
    assert {e.slug for e in ordered} == {e.slug for e in entries}


@pytest.mark.spec("DOCFRAME-010")
def test_live_status_kinds_carry_a_vocabulary_status(mods):
    """Every live RFC and ADR yields a status from its kind's vocabulary.

    The renderer prints `—` for a missing status, which `mkdocs build --strict`
    accepts, so drift would ship silently without this control (and without
    check_sdd_index.py R3, which runs where this test cannot: on sdd-only diffs).
    """
    scan, _ = mods
    entries_by_kind = scan.scan_all_sdd(ROOT)
    status_kinds = [k for k in scan.SDD_KINDS if k.status]
    assert {k.slug for k in status_kinds} == {"adrs", "rfcs"}
    for kind in status_kinds:
        entries = entries_by_kind[kind.slug]
        assert entries, f"{kind.slug} scanned no documents"
        vocabulary = scan.STATUS_VOCABULARY[kind.slug]
        off = {e.slug: e.status for e in entries if e.status not in vocabulary}
        assert not off, f"{kind.slug} without a vocabulary status {vocabulary}: {off}"


@pytest.mark.spec("DOCFRAME-010")
def test_live_adr_statuses_match_the_digest(mods):
    """The index and DIGEST.md read one parser, so they cannot disagree about an ADR."""
    scan, _ = mods
    import gen_adr_digest

    adrs, errors = gen_adr_digest.load_all(ROOT / "sdd" / "adrs")
    assert not errors
    digest = {a.path.stem: a.status for a in adrs}
    index = {e.slug: e.status for e in scan.scan_all_sdd(ROOT)["adrs"]}
    assert index == digest
