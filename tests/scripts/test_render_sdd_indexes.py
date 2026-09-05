"""Tests for the dated-kind index column in scripts/docs/{scan,render}.py.

``SddKind.dated`` (declared per kind in ``docs-src/_path_rules.yml``) adds a
"Date (as of)" column to that kind's index table and lists it newest first.
Research is the only dated kind today: a survey ages, so a reader needs to see
how current it is.

The reordering is scoped to the index table — nav and the design landing page
keep scan (filename) order — so these tests pin both halves.
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
    kind = scan.SddKind("adrs", "sdd/adrs", "ADRs", status="Accepted")
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
    kind = scan.SddKind("adrs", "sdd/adrs", "ADRs", status="Accepted")
    row = render._index_row(kind, _entry(scan, kind, "0001-a", "A", None))
    assert row == "| 0001-a | [A](0001-a.md) | Accepted |"


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
