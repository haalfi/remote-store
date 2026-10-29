"""Tests for ``scripts/observe_tables.py`` (RFC-0029 R1, BK-504).

The script checks the tables of an ``/observe`` record, or a spec, against the
domains a sidecar declares for them. Pinned: a case table is complete and
disjoint over its members (ranges expanded, whole words, declared parts); a
member must occur in its declared source, and a ``complete`` source's every row
must be some member; a state table has a row per state, a column per event, an
event per column and no empty cell; every table is declared once and every
anchor finds one; every ID cited in a declared family is defined or retired, and
``<ID>, row <n>`` names an existing row; each declaration in ``MALFORMED`` exits 2,
never as findings. Seeded mutants of OP-01's real record each produce a finding
the record itself does not (ADR-0045: the check can come out the other way).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/observe_tables.py"
OP01 = ROOT / "sdd/observe/records/OP-01.md"
OP01_TABLES = ROOT / "sdd/observe/tables/OP-01.toml"

PARTITION = """\
# OP-01: observable semantics

## Environment

| ID | Actor | Action |
|---|---|---|
| `OP-01/E1` | O2 | writes |
| `OP-01/E2` | O3 | deletes |
| `OP-01/E3` | World | stalls |

## Decisions

### OP-01/D1: The partition (AX-3)

- **Decision:** (a).

  | Pre-state | Outcome |
  |---|---|
  | Found(e, item) | success |
  | Absent, AbsentAncestor | not found |

### OP-01/D18: Exposure (AX-7)

- **Decision:** (a), see D1 and `OP-01/E2`.

  | Row | s1 |
  |---|---|
  | E1 to E3 | yes |
"""

PARTITION_TOML = """\
[[table]]
at = "Environment"
kind = "ids"
column = 1

[[table]]
at = "OP-01/D1"
kind = "case"
key = 1
members = ["Found(e, item)", "Absent", "AbsentAncestor"]

[[table]]
at = "OP-01/D18"
kind = "case"
key = 1
members = ["E1", "E2", "E3"]
source = [{ at = "Environment", column = 1 }]

[[ids]]
family = "OP-01/D"
short = "D"

[[ids]]
family = "OP-01/E"
short = "E"
"""


def _run(tmp_path: Path, doc: str, toml: str, *, newline: str = "\n") -> subprocess.CompletedProcess[str]:
    md = tmp_path / "doc.md"
    md.write_bytes(doc.replace("\n", newline).encode("utf-8"))
    side = tmp_path / "doc.toml"
    side.write_text(toml, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(md), str(side)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _findings(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if line.startswith("- ")]


def test_complete_disjoint_tables_pass(tmp_path: Path) -> None:
    result = _run(tmp_path, PARTITION, PARTITION_TOML)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _findings(result) == []
    assert "0 findings" in result.stdout


def test_crlf_document_parses_alike(tmp_path: Path) -> None:
    result = _run(tmp_path, PARTITION, PARTITION_TOML, newline="\r\n")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_member_no_row_covers_is_a_gap(tmp_path: Path) -> None:
    doc = PARTITION.replace("| Absent, AbsentAncestor | not found |", "| AbsentAncestor | not found |")
    result = _run(tmp_path, doc, PARTITION_TOML)
    assert result.returncode == 1
    # Whole words: AbsentAncestor does not cover Absent.
    assert _findings(result) == ["- OP-01/D1 table 1: gap: 'Absent' is matched by no row"]


def test_a_member_two_rows_cover_is_an_overlap(tmp_path: Path) -> None:
    doc = PARTITION.replace(
        "| Absent, AbsentAncestor | not found |", "| Absent, AbsentAncestor | not found |\n  | Absent | gone |"
    )
    result = _run(tmp_path, doc, PARTITION_TOML)
    assert result.returncode == 1
    assert _findings(result) == ["- OP-01/D1 table 1: overlap: 'Absent' is matched by rows 2 and 3"]


def test_a_row_no_member_matches_is_outside_the_domain(tmp_path: Path) -> None:
    doc = PARTITION.replace(
        "| Absent, AbsentAncestor | not found |", "| Absent, AbsentAncestor | not found |\n  | Blocked | x |"
    )
    result = _run(tmp_path, doc, PARTITION_TOML)
    assert _findings(result) == ["- OP-01/D1 table 1: row 3 ('Blocked') matches no member"]


def test_a_range_covers_its_inner_members_and_only_them(tmp_path: Path) -> None:
    doc = PARTITION.replace("| E1 to E3 | yes |", "| E1 to E2 | yes |")
    result = _run(tmp_path, doc, PARTITION_TOML)
    # E10 would not match E1: ranges and IDs are whole tokens.
    assert _findings(result) == ["- OP-01/D18 table 1: gap: 'E3' is matched by no row"]


def test_declared_parts_split_a_member_across_rows(tmp_path: Path) -> None:
    doc = PARTITION.replace("| E1 to E3 | yes |", "| E1, E2 | yes |\n  | E3, disk | yes |\n  | E3, memory | no |")
    toml = PARTITION_TOML.replace(
        'members = ["E1", "E2", "E3"]', 'members = ["E1", "E2", "E3"]\nparts = { E3 = ["disk", "memory"] }'
    )
    assert _run(tmp_path, doc, toml).returncode == 0
    missing = doc.replace("| E3, memory | no |\n", "")
    assert _findings(_run(tmp_path, missing, toml)) == [
        "- OP-01/D18 table 1: gap: 'E3' part 'memory' is matched by no row"
    ]
    twice = doc.replace("| E3, memory | no |", "| E3, memory | no |\n  | E3, disk | again |")
    assert _findings(_run(tmp_path, twice, toml)) == [
        "- OP-01/D18 table 1: overlap: 'E3' part 'disk' is matched by rows 2 and 4"
    ]


def test_a_member_absent_from_its_source_is_reported(tmp_path: Path) -> None:
    toml = PARTITION_TOML.replace('members = ["E1", "E2", "E3"]', 'members = ["E1", "E2", "E3", "E4"]')
    doc = PARTITION.replace("| E1 to E3 | yes |", "| E1 to E4 | yes |")
    assert _findings(_run(tmp_path, doc, toml)) == [
        "- OP-01/D18 table 1: source: 'E4' occurs in no cell of Environment column 1",
        "- citation: 'E4' (line 28) names no defined element",
    ]
    exempt = toml.replace(
        'members = ["E1", "E2", "E3", "E4"]', 'members = ["E1", "E2", "E3", "E4"]\nunsourced = ["E4"]'
    )
    assert _findings(_run(tmp_path, doc, exempt)) == ["- citation: 'E4' (line 28) names no defined element"]


def test_a_complete_source_row_no_member_names_is_reported(tmp_path: Path) -> None:
    # The reopen's likely edit: an Environment row is added and the table drawn from it is not.
    doc = PARTITION.replace(
        "| `OP-01/E3` | World | stalls |", "| `OP-01/E3` | World | stalls |\n| `OP-01/E4` | O2 | moves |"
    )
    assert _findings(_run(tmp_path, doc, PARTITION_TOML)) == []
    complete = PARTITION_TOML.replace(
        'source = [{ at = "Environment", column = 1 }]',
        'source = [{ at = "Environment", column = 1, complete = true }]',
    )
    assert _findings(_run(tmp_path, PARTITION, complete)) == []
    assert _findings(_run(tmp_path, doc, complete)) == [
        "- OP-01/D18 table 1: source: row 4 of Environment column 1 ('`OP-01/E4`') matches no member"
    ]


def test_a_complete_source_element_inside_a_range_or_list_is_reported(tmp_path: Path) -> None:
    # A row matching one member must still have each of its domain's IDs matched: "E1 to E4" holds E4.
    toml = (
        PARTITION_TOML.replace(
            'source = [{ at = "Environment", column = 1 }]', 'source = [{ at = "Groups", column = 1, complete = true }]'
        )
        + '\n[[table]]\nat = "Groups"\nkind = "register"\nreason = "r"\n'
    )
    for cell in ("E1 to E4", "E1 to E3, E4"):
        doc = PARTITION + f"\n## Groups\n\n| Rows | Note |\n|---|---|\n| {cell} | all |\n"
        assert _findings(_run(tmp_path, doc, toml)) == [
            f"- OP-01/D18 table 1: source: row 1 of Groups column 1 ({cell!r}) names 'E4', which no member matches",
            "- citation: 'E4' (line 34) names no defined element",
        ], cell
    clean = PARTITION + "\n## Groups\n\n| Rows | Note |\n|---|---|\n| E1 to E3 (D1) | all |\n"
    # D1 is no family the members name, so it is no element of the domain.
    assert _findings(_run(tmp_path, clean, toml)) == []


def test_a_regex_member_matches_its_spellings(tmp_path: Path) -> None:
    doc = PARTITION.replace(
        "| Found(e, item) | success |", "| Found(e, item) | success |\n  | ν refuses | key refused |"
    )
    toml = PARTITION_TOML.replace(
        'members = ["Found(e, item)", "Absent", "AbsentAncestor"]',
        'members = ["Found(e, item)", "Absent", "AbsentAncestor", { name = "refused", match = "refus(ed|es)" }]',
    )
    assert _run(tmp_path, doc, toml).returncode == 0


STATE = """\
# Spec

### OP-01/D18: The stream (AX-6)

  | State | `read`, chunks | `close` |
  |---|---|---|
  | Open (bytes remain) | next bytes | Closed |
  | Closed | `ValueError` | no-op |
"""

STATE_TOML = """\
[[table]]
at = "OP-01/D18"
kind = "state"
states = ["Open", "Closed"]
events = ["read", "close"]
"""


def test_a_full_state_table_passes(tmp_path: Path) -> None:
    assert _run(tmp_path, STATE, STATE_TOML).returncode == 0


def test_state_table_gaps_are_each_localized(tmp_path: Path) -> None:
    toml = STATE_TOML.replace('["Open", "Closed"]', '["Open", "Failed", "Closed"]').replace(
        '["read", "close"]', '["read", "close", "cancelled"]'
    )
    doc = STATE.replace("| Closed | `ValueError` | no-op |", "| Closed | `ValueError` |  |")
    assert _findings(_run(tmp_path, doc, toml)) == [
        "- OP-01/D18 table 1: state 'Failed' has no row",
        "- OP-01/D18 table 1: event 'cancelled' has no column",
        "- OP-01/D18 table 1: row 2 ('Closed') has an empty cell in column 3",
    ]


def test_a_state_column_no_event_names_is_reported(tmp_path: Path) -> None:
    doc = STATE.replace(
        "| State | `read`, chunks | `close` |\n  |---|---|---|",
        "| State | `read`, chunks | `close` | seek |\n  |---|---|---|---|",
    )
    doc = doc.replace("| Closed |\n", "| Closed | moves |\n").replace("| no-op |\n", "| no-op | moves |\n")
    assert _findings(_run(tmp_path, doc, STATE_TOML)) == ["- OP-01/D18 table 1: column 4 ('seek') matches no event"]


def test_an_event_two_columns_name_is_reported(tmp_path: Path) -> None:
    doc = STATE.replace("| `close` |\n  |---|---|---|", "| `close` | `read` again |\n  |---|---|---|---|")
    doc = doc.replace("| Closed |\n", "| Closed | more |\n").replace("| no-op |\n", "| no-op | more |\n")
    assert _findings(_run(tmp_path, doc, STATE_TOML)) == ["- OP-01/D18 table 1: event 'read' has columns 2 and 4"]


def test_an_undeclared_table_and_a_lost_anchor_are_reported(tmp_path: Path) -> None:
    toml = PARTITION_TOML.replace('at = "OP-01/D18"', 'at = "OP-01/D19"')
    assert _findings(_run(tmp_path, PARTITION, toml)) == [
        "- declaration: 'OP-01/D19' table 1 matches no table",
        "- declaration: OP-01/D18 table 1 (line 26) is declared by no entry",
    ]


def test_a_table_declared_twice_is_reported(tmp_path: Path) -> None:
    toml = PARTITION_TOML + '\n[[table]]\nat = "OP-01/D1"\nkind = "register"\nreason = "again"\n'
    assert _findings(_run(tmp_path, PARTITION, toml)) == [
        "- declaration: OP-01/D1 table 1 (line 17) is declared by 2 entries"
    ]


def test_a_column_beyond_the_table_is_a_declaration_finding(tmp_path: Path) -> None:
    # Not a gap per member: the declaration, not the record, is what is wrong.
    key = PARTITION_TOML.replace("key = 1", "key = 3", 1)
    assert _findings(_run(tmp_path, PARTITION, key)) == ["- declaration: 'OP-01/D1' table 1 has 2 columns, not 3"]
    ids = PARTITION_TOML.replace("column = 1\n", "column = 4\n", 1)
    # The IDs it would define go undefined, so citations of them follow; the declaration comes first.
    assert _findings(_run(tmp_path, PARTITION, ids))[0] == "- declaration: 'Environment' table 1 has 3 columns, not 4"
    source = PARTITION_TOML.replace("column = 1 }", "column = 7 }")
    assert _findings(_run(tmp_path, PARTITION, source)) == [
        "- OP-01/D18 table 1: source: 'Environment' table 1 has 3 columns, not 7"
    ]


def test_a_fenced_table_is_skipped_by_either_fence(tmp_path: Path) -> None:
    for fence in ("```", "~~~"):
        doc = PARTITION + f"\n{fence}\n| A | B |\n|---|---|\n| x | y |\n{fence}\n"
        assert _findings(_run(tmp_path, doc, PARTITION_TOML)) == [], fence


def test_a_one_dash_separator_still_makes_a_table(tmp_path: Path) -> None:
    doc = PARTITION + "\n## Notes\n\n| A | B |\n|-|-|\n| x | y |\n"
    assert _findings(_run(tmp_path, doc, PARTITION_TOML)) == [
        "- declaration: Notes table 1 (line 32) is declared by no entry"
    ]


def test_index_selects_a_later_table_under_one_heading(tmp_path: Path) -> None:
    # A spec heading often holds several tables: index picks one, for a table and for a source.
    doc = PARTITION + "\n## Notes\n\n| X | Y |\n|---|---|\n| a | b |\n\n| Rows | Z |\n|---|---|\n| E1 to E3 | c |\n"
    second = '\n[[table]]\nat = "Notes"\nindex = 2\nkind = "case"\nkey = 1\nmembers = ["E1", "E2", "E3"]\n'
    assert _findings(_run(tmp_path, doc, PARTITION_TOML + second)) == [
        "- declaration: Notes table 1 (line 32) is declared by no entry"
    ]
    first = '\n[[table]]\nat = "Notes"\nkind = "register"\nreason = "r"\n'
    sourced = PARTITION_TOML.replace(
        'source = [{ at = "Environment", column = 1 }]', 'source = [{ at = "Notes", index = 2, column = 1 }]'
    )
    assert _findings(_run(tmp_path, doc, sourced + second + first)) == []


def test_an_anchor_two_headings_share_is_reported_not_guessed(tmp_path: Path) -> None:
    doc = PARTITION.replace("### OP-01/D18: Exposure (AX-7)", "### OP-01/D1: Exposure again (AX-7)")
    toml = PARTITION_TOML.replace('at = "OP-01/D18"', 'at = "OP-01/D1"\nindex = 2')
    result = _run(tmp_path, doc, toml)
    assert "- declaration: 'OP-01/D1' matches 2 headings" in _findings(result)
    assert result.returncode == 1


def test_a_lost_source_anchor_is_reported(tmp_path: Path) -> None:
    toml = PARTITION_TOML.replace(
        'source = [{ at = "Environment", column = 1 }]', 'source = [{ at = "Actors", column = 1 }]'
    )
    assert _findings(_run(tmp_path, PARTITION, toml)) == [
        "- OP-01/D18 table 1: source: 'Actors' table 1 matches no table"
    ]


def test_a_row_matching_a_member_but_none_of_its_parts_is_reported(tmp_path: Path) -> None:
    doc = PARTITION.replace(
        "| E1 to E3 | yes |", "| E1, E2 | yes |\n  | E3, disk | yes |\n  | E3, memory | no |\n  | E3 | ? |"
    )
    toml = PARTITION_TOML.replace(
        'members = ["E1", "E2", "E3"]', 'members = ["E1", "E2", "E3"]\nparts = { E3 = ["disk", "memory"] }'
    )
    assert _findings(_run(tmp_path, doc, toml)) == ["- OP-01/D18 table 1: row 4 matches 'E3' but none of its parts"]


def test_a_state_two_rows_match_is_reported(tmp_path: Path) -> None:
    doc = STATE.replace(
        "| Closed | `ValueError` | no-op |", "| Closed | `ValueError` | no-op |\n  | Closed again | x | y |"
    )
    assert _findings(_run(tmp_path, doc, STATE_TOML)) == ["- OP-01/D18 table 1: state 'Closed' has rows 2 and 3"]


def test_a_row_matching_no_state_is_reported(tmp_path: Path) -> None:
    doc = STATE.replace("| Closed | `ValueError` | no-op |", "| Closed | `ValueError` | no-op |\n  | Paused | ? | ? |")
    assert _findings(_run(tmp_path, doc, STATE_TOML)) == ["- OP-01/D18 table 1: row 3 ('Paused') matches no state"]


def test_ci_runs_this_module_when_a_file_it_reads_changes() -> None:
    # tooling-tests is the only job running tests/scripts/, gated on HOOKS_PAT (CLAUDE-REFERENCE's
    # "Test whose subject is outside src/ or scripts/" row): an edit to a record or its sidecar runs it.
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    hooks_pat = re.compile(re.search(r"HOOKS_PAT='([^']+)'", ci)[1])  # type: ignore[index]
    read = [OP01, OP01_TABLES, *(ROOT / "sdd/observe/records").glob("*.md"), *(ROOT / "sdd/observe/tables").glob("*")]
    assert [p.relative_to(ROOT).as_posix() for p in read if not hooks_pat.search(p.relative_to(ROOT).as_posix())] == []


def test_an_anchor_does_not_match_a_longer_id(tmp_path: Path) -> None:
    # "OP-01/D1" must anchor D1's heading only, never D18's.
    result = _run(tmp_path, PARTITION, PARTITION_TOML)
    assert "matches 2 headings" not in result.stdout
    assert result.returncode == 0


def test_an_undefined_citation_is_reported(tmp_path: Path) -> None:
    doc = PARTITION.replace("see D1 and `OP-01/E2`", "see D7 and `OP-01/E9`")
    assert _findings(_run(tmp_path, doc, PARTITION_TOML)) == [
        "- citation: 'D7' (line 24) names no defined element",
        "- citation: 'OP-01/E9' (line 24) names no defined element",
    ]


def test_a_cited_row_beyond_the_table_is_reported(tmp_path: Path) -> None:
    doc = PARTITION.replace("see D1 and", "see D1, row 2, D1, row 3 and")
    assert _findings(_run(tmp_path, doc, PARTITION_TOML)) == [
        "- citation: 'D1, row 3' (line 24): OP-01/D1's first table has 2 rows"
    ]


SPEC = """\
# 052: Store Key Specification

### KEY-013: Resolution Outcomes

| Case | Outcome |
|---|---|
| item | Found |
| folder | Found |
| none | Absent |

## Notes

KEY-013 is exhaustive; KEY-006 was removed.
"""

SPEC_TOML = """\
[[table]]
at = "KEY-013"
kind = "case"
key = 1
members = ["item", "folder", "none"]

[[ids]]
family = "KEY-"
"""


def test_spec_mode_checks_a_spec_by_the_same_rules(tmp_path: Path) -> None:
    result = _run(tmp_path, SPEC, SPEC_TOML)
    assert _findings(result) == ["- citation: 'KEY-006' (line 13) names no defined element"]
    clean = _run(tmp_path, SPEC.replace("; KEY-006 was removed", ""), SPEC_TOML)
    assert clean.returncode == 0


def test_a_zero_padded_range_keeps_its_width(tmp_path: Path) -> None:
    # Spec IDs are zero-padded: "KEY-002 to KEY-004" covers KEY-003, in a case cell and in an ids cell.
    doc = (
        "# Spec\n\n## IDs\n\n| ID | Note |\n|---|---|\n| KEY-010 to KEY-012 | defined |\n\n"
        "### KEY-020: Cases\n\n| Case | Outcome |\n|---|---|\n| KEY-002 to KEY-004 | x |\n\nSee KEY-011.\n"
    )
    toml = (
        '[[table]]\nat = "IDs"\nkind = "ids"\ncolumn = 1\n\n'
        '[[table]]\nat = "KEY-020"\nkind = "case"\nkey = 1\nmembers = ["KEY-002", "KEY-003", "KEY-004"]\n\n'
        '[[ids]]\nfamily = "KEY-"\nretired = ["KEY-002", "KEY-003", "KEY-004"]\n'
    )
    assert _findings(_run(tmp_path, doc, toml)) == []


def test_a_retired_id_is_no_dangling_citation(tmp_path: Path) -> None:
    # A spec names the IDs it retired ("KEY-006, KEY-007 and KEY-A-01 are unassigned", spec 052).
    retired = SPEC_TOML.replace('family = "KEY-"', 'family = "KEY-"\nretired = ["KEY-006"]')
    assert _findings(_run(tmp_path, SPEC, retired)) == []
    defined = SPEC_TOML.replace('family = "KEY-"', 'family = "KEY-"\nretired = ["KEY-013"]')
    assert _findings(_run(tmp_path, SPEC, defined)) == [
        "- citation: 'KEY-013' is declared retired but is defined",
        "- citation: 'KEY-006' (line 13) names no defined element",
    ]


def _variant(base: str, old: str, new: str) -> str:
    assert old in base, old
    return base.replace(old, new, 1)


_D1 = 'members = ["Found(e, item)", "Absent", "AbsentAncestor"]'
_D18 = 'members = ["E1", "E2", "E3"]'
_SRC = '{ at = "Environment", column = 1 }'
# Wrong shapes of the keys validate() reads, and the clashes across [[ids]]: a sample of the key-by-shape
# space, not all of it. Rounds 1 to 4 of PR #1197 each found one more read as findings, which is why it
# is a table (/ship's repeat-site check).
MALFORMED = {
    "toml syntax": "[[table]\n",
    "table not an array": 'table = ["OP-01/D1"]\n',
    "ids not an array": PARTITION_TOML.replace('[[ids]]\nfamily = "OP-01/E"\nshort = "E"\n', "").replace(
        "[[ids]]", "[ids]"
    ),
    "top-level key unknown": "tabel = 1\n" + PARTITION_TOML,
    "kind missing": '[[table]]\nat = "OP-01/D1"\n',
    "kind unknown": '[[table]]\nat = "OP-01/D1"\nkind = "lattice"\n',
    "at missing": '[[table]]\nkind = "register"\nreason = "r"\n',
    "at empty": _variant(PARTITION_TOML, 'at = "OP-01/D1"', 'at = ""'),
    "at not a string": _variant(PARTITION_TOML, 'at = "OP-01/D1"', "at = 1"),
    "table key unknown": _variant(PARTITION_TOML, "source = [", "sources = ["),
    "index zero": _variant(PARTITION_TOML, 'at = "OP-01/D1"', 'at = "OP-01/D1"\nindex = 0'),
    "index bool": _variant(PARTITION_TOML, 'at = "OP-01/D1"', 'at = "OP-01/D1"\nindex = true'),
    "index string": _variant(PARTITION_TOML, 'at = "OP-01/D1"', 'at = "OP-01/D1"\nindex = "1"'),
    "index float": _variant(PARTITION_TOML, 'at = "OP-01/D1"', 'at = "OP-01/D1"\nindex = 1.5'),
    "basis not a string": _variant(PARTITION_TOML, _D1, _D1 + "\nbasis = 1"),
    "case key missing": _variant(PARTITION_TOML, "key = 1\n", ""),
    "case key zero": _variant(PARTITION_TOML, "key = 1", "key = 0"),
    "case key negative": _variant(PARTITION_TOML, "key = 1", "key = -1"),
    "case key bool": _variant(PARTITION_TOML, "key = 1", "key = true"),
    "case key string": _variant(PARTITION_TOML, "key = 1", 'key = "1"'),
    "case key float": _variant(PARTITION_TOML, "key = 1", "key = 1.9"),
    "members missing": _variant(PARTITION_TOML, _D1 + "\n", ""),
    "members a string": _variant(PARTITION_TOML, _D18, 'members = "E1"'),
    "members empty": _variant(PARTITION_TOML, _D1, "members = []"),
    "member empty": _variant(PARTITION_TOML, _D18, 'members = ["E1", "", "E3"]'),
    "member not a string": _variant(PARTITION_TOML, _D18, 'members = ["E1", 2, "E3"]'),
    "member twice": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", "E3", "E1"]'),
    "member name only": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = "E3" }]'),
    "member match empty": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = "E3", match = "" }]'),
    "member name empty": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = "", match = "E3" }]'),
    "member key unknown": _variant(
        PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = "E3", match = "E3", why = "x" }]'
    ),
    "member bad regex": _variant(PARTITION_TOML, _D18, 'members = [{ name = "x", match = "(" }]'),
    "parts not a table": _variant(PARTITION_TOML, _D18, _D18 + '\nparts = ["E3"]'),
    "parts off members": _variant(PARTITION_TOML, _D18, _D18 + '\nparts = { E9 = ["disk"] }'),
    "part a string": _variant(PARTITION_TOML, _D18, _D18 + '\nparts = { E3 = "disk" }'),
    "parts empty": _variant(PARTITION_TOML, _D18, _D18 + "\nparts = { E3 = [] }"),
    "part empty": _variant(PARTITION_TOML, _D18, _D18 + '\nparts = { E3 = ["disk", ""] }'),
    "part not a string": _variant(PARTITION_TOML, _D18, _D18 + "\nparts = { E3 = [1] }"),
    "source a string": _variant(PARTITION_TOML, f"source = [{_SRC}]", 'source = "Environment"'),
    "source empty": _variant(PARTITION_TOML, f"source = [{_SRC}]", "source = []"),
    "source entry not a table": _variant(PARTITION_TOML, f"source = [{_SRC}]", "source = [1]"),
    "source at missing": _variant(PARTITION_TOML, _SRC, "{ column = 1 }"),
    "source at empty": _variant(PARTITION_TOML, _SRC, '{ at = "", column = 1 }'),
    "source column missing": _variant(PARTITION_TOML, _SRC, '{ at = "Environment" }'),
    "source column zero": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 0 }'),
    "source column float": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 1.5 }'),
    "source index zero": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 1, index = 0 }'),
    "source complete not a bool": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 1, complete = 1 }'),
    "source key unknown": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 1, colum = 2 }'),
    "unsourced a string": _variant(PARTITION_TOML, _D18, _D18 + '\nunsourced = "E3"'),
    "unsourced not a member": _variant(PARTITION_TOML, _D18, _D18 + '\nunsourced = ["E9"]'),
    "unsourced not a string": _variant(PARTITION_TOML, _D18, _D18 + "\nunsourced = [1]"),
    "unsourced without source": _variant(PARTITION_TOML, _D1, _D1 + '\nunsourced = ["Absent"]'),
    "states missing": _variant(STATE_TOML, 'states = ["Open", "Closed"]\n', ""),
    "states a string": _variant(STATE_TOML, 'states = ["Open", "Closed"]', 'states = "Open"'),
    "states empty": _variant(STATE_TOML, 'states = ["Open", "Closed"]', "states = []"),
    "state empty": _variant(STATE_TOML, 'states = ["Open", "Closed"]', 'states = ["Open", ""]'),
    "events empty": _variant(STATE_TOML, 'events = ["read", "close"]', "events = []"),
    "event empty": _variant(STATE_TOML, 'events = ["read", "close"]', 'events = ["read", ""]'),
    "event twice": _variant(STATE_TOML, 'events = ["read", "close"]', 'events = ["read", "read"]'),
    "state key unknown": _variant(STATE_TOML, 'events = ["read", "close"]', 'event = ["read", "close"]'),
    "ids column missing": _variant(PARTITION_TOML, 'kind = "ids"\ncolumn = 1\n', 'kind = "ids"\n'),
    "ids column zero": _variant(PARTITION_TOML, 'kind = "ids"\ncolumn = 1', 'kind = "ids"\ncolumn = 0'),
    "ids column bool": _variant(PARTITION_TOML, 'kind = "ids"\ncolumn = 1', 'kind = "ids"\ncolumn = true'),
    "register reason missing": _variant(PARTITION_TOML, 'kind = "case"\nkey = 1\n' + _D18, 'kind = "register"'),
    "register reason empty": _variant(
        PARTITION_TOML, 'kind = "case"\nkey = 1\n' + _D18, 'kind = "register"\nreason = ""'
    ),
    "register reason not a string": _variant(
        PARTITION_TOML, 'kind = "case"\nkey = 1\n' + _D18, 'kind = "register"\nreason = 1'
    ),
    "family missing": PARTITION_TOML + '\n[[ids]]\nshort = "X"\n',
    "family empty": _variant(PARTITION_TOML, 'family = "OP-01/D"', 'family = ""'),
    "family not a string": _variant(PARTITION_TOML, 'family = "OP-01/D"', "family = 1"),
    "short empty": _variant(PARTITION_TOML, 'short = "D"', 'short = ""'),
    "short not a string": _variant(PARTITION_TOML, 'short = "D"', "short = 1"),
    "retired a string": _variant(PARTITION_TOML, 'short = "D"', 'short = "D"\nretired = "OP-01/D7"'),
    "retired off its family": _variant(PARTITION_TOML, 'short = "D"', 'short = "D"\nretired = ["OP-01/E7"]'),
    "ids key unknown": _variant(PARTITION_TOML, 'short = "D"', 'short = "D"\nshrot = "X"'),
    "member match not a string": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = "E3", match = 1 }]'),
    "member name not a string": _variant(PARTITION_TOML, _D18, 'members = ["E1", "E2", { name = 3, match = "E3" }]'),
    "source at not a string": _variant(PARTITION_TOML, _SRC, "{ at = 1, column = 1 }"),
    "source column bool": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = true }'),
    "source index bool": _variant(PARTITION_TOML, _SRC, '{ at = "Environment", column = 1, index = true }'),
    "state twice": _variant(STATE_TOML, 'states = ["Open", "Closed"]', 'states = ["Open", "Open"]'),
    "part twice": _variant(PARTITION_TOML, _D18, _D18 + '\nparts = { E3 = ["disk", "disk"] }'),
    "unsourced twice": _variant(PARTITION_TOML, _D18, _D18 + '\nunsourced = ["E3", "E3"]'),
    "retired twice": _variant(PARTITION_TOML, 'short = "D"', 'short = "D"\nretired = ["OP-01/D7", "OP-01/D7"]'),
    # Across [[ids]]: a bare D18 would be read as two families' IDs, one of them undefined.
    "short shared by two families": _variant(PARTITION_TOML, 'short = "E"', 'short = "D"'),
    "family declared twice": PARTITION_TOML + '\n[[ids]]\nfamily = "OP-01/D"\n',
}


@pytest.mark.parametrize("toml", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_declaration_exits_2_not_as_findings(tmp_path: Path, toml: str) -> None:
    # Exit 1 means findings, so a broken sidecar must not read as a record with gaps; exit 0 would
    # mean a misspelt or coerced key switched a check off.
    doc = STATE if "states" in toml or "events" in toml or "event =" in toml else PARTITION
    result = _run(tmp_path, doc, toml)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith("observe_tables: "), result.stderr
    assert "Traceback" not in result.stderr


# Seeded mutants of OP-01's real record: each yields a finding the record itself does not. Each
# target is found in the parsed record, never written as a literal cell, so a reopen that adds a
# row or a column to these tables leaves the mutants valid.


def _script() -> Any:
    sys.path.insert(0, str(ROOT / "scripts"))
    import observe_tables

    return observe_tables


def _op01() -> tuple[str, Any, dict[str, Any]]:
    record = OP01.read_text(encoding="utf-8")
    return record, _script().parse(record), tomllib.loads(OP01_TABLES.read_text(encoding="utf-8"))


def _table(doc: Any, at: str) -> Any:
    table = _script()._find(doc, at, 1)
    assert table is not None, at
    return table


def _op01_findings(tmp_path: Path, record: str) -> set[str]:
    return set(_findings(_run(tmp_path, record, OP01_TABLES.read_text(encoding="utf-8"))))


def _mutant_adds(tmp_path: Path, record: str, lines: dict[int, str | None], tail: str = "") -> set[str]:
    """The findings *record* gains when each numbered line is replaced (None drops it) and *tail* appended."""
    text = record.split("\n")
    mutant = [lines.get(n, line) for n, line in enumerate(text, 1)]
    mutated = "\n".join(line for line in mutant if line is not None) + tail
    return _op01_findings(tmp_path, mutated) - _op01_findings(tmp_path, record)


def test_op01_mutant_dropping_a_partition_row_is_a_gap(tmp_path: Path) -> None:
    record, doc, _ = _op01()
    line = next(n for n, cells in _table(doc, "OP-01/D9").rows if "Found(e, folder)" in cells[0])
    # D34 draws its pre-state members from D9's column, so its source check sees the loss too.
    assert _mutant_adds(tmp_path, record, {line: None}) == {
        "- OP-01/D9 table 1: gap: 'Found(e, folder)' is matched by no row",
        "- OP-01/D34 table 1: source: 'Found(e, folder)' occurs in no cell of"
        " Environment column 1 or OP-01/D9 column 1",
    }


def test_op01_mutant_exposing_an_environment_row_twice_is_an_overlap(tmp_path: Path) -> None:
    record, doc, decl = _op01()
    members = next(e["members"] for e in decl["table"] if e["at"] == "OP-01/D19")
    (_, cells1), (second, cells2) = _table(doc, "OP-01/D19").rows[:2]
    member = next(m for m in members if re.search(rf"(?<!\w){re.escape(m)}(?!\w)", _script()._expand(cells1[0])))
    text = record.split("\n")[second - 1]
    assert _mutant_adds(tmp_path, record, {second: text.replace(cells2[0], f"{cells2[0]}, {member}", 1)}) == {
        f"- OP-01/D19 table 1: overlap: {member!r} is matched by rows 1 and 2"
    }


def test_op01_mutant_emptying_a_state_cell_is_reported(tmp_path: Path) -> None:
    record, doc, _ = _op01()
    line, cells = _table(doc, "OP-01/D18").rows[-1]
    text = record.split("\n")[line - 1]
    head, _, _ = text.rstrip().rstrip("|").rpartition("|")
    rows = len(_table(doc, "OP-01/D18").rows)
    assert _mutant_adds(tmp_path, record, {line: f"{head}|  |"}) == {
        f"- OP-01/D18 table 1: row {rows} ({cells[0]!r}) has an empty cell in column {len(cells)}"
    }


def test_op01_mutant_citing_a_missing_register_row_is_reported(tmp_path: Path) -> None:
    record, doc, _ = _op01()
    rows = len(_table(doc, "OP-01/D41").rows)
    last = len(record.split("\n"))
    added = _mutant_adds(tmp_path, record, {}, f"\nSee D41, row {rows + 1}.\n")
    assert added == {f"- citation: 'D41, row {rows + 1}' (line {last + 1}): OP-01/D41's first table has {rows} rows"}


def test_op01_observer_mentions_are_no_open_item_citations(tmp_path: Path) -> None:
    # O1 to O3 are axes.md's observers as well as open items; dropping the item O2 must not make
    # the Environment's actor "O2" a dangling citation.
    record, _, _ = _op01()
    line = next(n for n, text in enumerate(record.split("\n"), 1) if text.startswith("- `OP-01/O2`:"))
    text = record.split("\n")[line - 1]
    added = _mutant_adds(tmp_path, record, {line: text.replace("- `OP-01/O2`:", "- dropped:")})
    assert [f for f in added if f.startswith("- citation: 'O2'")] == []
    # The full form is still checked: OP-01/D10 cites `OP-01/O2`.
    assert any(f.startswith("- citation: 'OP-01/O2'") for f in added)


def test_op01_mutant_dropping_an_environment_row_is_reported(tmp_path: Path) -> None:
    record, doc, decl = _op01()
    members = next(e["members"] for e in decl["table"] if e["at"] == "OP-01/D19")
    line, cells = next(
        (n, c) for n, c in reversed(_table(doc, "Environment").rows) if c[0].strip("`").split("/")[-1] in members
    )
    element = cells[0].strip("`").split("/")[-1]
    added = _mutant_adds(tmp_path, record, {line: None})
    assert f"- OP-01/D19 table 1: source: {element!r} occurs in no cell of Environment column 1" in added
    assert any(f.startswith(f"- citation: {element!r}") for f in added)


def test_op01_mutant_adding_an_environment_row_no_table_names_is_reported(tmp_path: Path) -> None:
    # The reopen O21 and O44 propose: a new Environment row, and D19's and D34's tables left as they were.
    record, doc, _ = _op01()
    env = _table(doc, "Environment")
    line, cells = env.rows[-1]
    number = 1 + max(int(re.search(r"\d+$", c[0].strip("`"))[0]) for _, c in env.rows)  # type: ignore[index]
    new = f"`OP-01/E{number}`"
    text = record.split("\n")[line - 1]
    rows = len(env.rows) + 1
    added = _mutant_adds(tmp_path, record, {line: text + "\n" + text.replace(cells[0], new, 1)})
    assert added == {
        f"- OP-01/D19 table 1: source: row {rows} of Environment column 1 ({new!r}) matches no member",
        f"- OP-01/D34 table 1: source: row {rows} of Environment column 1 ({new!r}) matches no member",
    }


def test_op01_mutant_adding_a_d34_category_is_reported_by_d38(tmp_path: Path) -> None:
    # D38's source is complete: a category D34 gains needs a D38 row.
    record, doc, _ = _op01()
    d34 = _table(doc, "OP-01/D34")
    line, cells = d34.rows[-1]
    text = record.split("\n")[line - 1]
    indent = text[: len(text) - len(text.lstrip())]
    new = indent + "| " + " | ".join([cells[0], "quota exceeded", *cells[2:]]) + " |"
    added = _mutant_adds(tmp_path, record, {line: text + "\n" + new})
    row = len(d34.rows) + 1
    assert f"- OP-01/D38 table 1: source: row {row} of OP-01/D34 column 2 ('quota exceeded') matches no member" in added


def test_op01_mutant_adding_an_undeclared_table_is_reported(tmp_path: Path) -> None:
    record, _, _ = _op01()
    last = len(record.split("\n"))
    added = _mutant_adds(tmp_path, record, {}, "\n### Scratch\n\n| A | B |\n|---|---|\n| x | y |\n")
    assert added == {f"- declaration: Scratch table 1 (line {last + 3}) is declared by no entry"}
