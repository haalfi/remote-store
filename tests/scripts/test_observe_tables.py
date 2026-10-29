"""Tests for ``scripts/observe_tables.py`` (RFC-0029 R1, BK-504).

The script checks the tables of an ``/observe`` record, or a spec, against the
domains a sidecar declares for them. Pinned: a case table is complete and
disjoint over its members (ranges expanded, whole words, declared parts); a
member must occur in its declared source; a state table has a row per state,
a column per event and no empty cell; every table is declared and every anchor
finds one; every ID cited in a declared family is defined, and ``<ID>, row <n>``
names an existing row. Each failure mode fails the run. Seeded mutants of
OP-01's real record each produce a finding the record itself does not
(ADR-0045: the check can come out the other way).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

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


def test_an_undeclared_table_and_a_lost_anchor_are_reported(tmp_path: Path) -> None:
    toml = PARTITION_TOML.replace('at = "OP-01/D18"', 'at = "OP-01/D19"')
    assert _findings(_run(tmp_path, PARTITION, toml)) == [
        "- declaration: 'OP-01/D19' table 1 matches no table",
        "- declaration: OP-01/D18 table 1 (line 26) is declared by no entry",
    ]


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


def test_unusable_input_exits_2(tmp_path: Path) -> None:
    assert _run(tmp_path, PARTITION, "[[table]\n").returncode == 2
    assert _run(tmp_path, PARTITION, '[[table]]\nat = "OP-01/D1"\nkind = "case"\n').returncode == 2
    assert _run(tmp_path, PARTITION, '[[table]]\nat = "OP-01/D1"\nkind = "lattice"\n').returncode == 2


def test_a_malformed_declaration_exits_2_not_as_findings(tmp_path: Path) -> None:
    # Exit 1 means findings, so a broken sidecar must not read as a record with gaps.
    bad_regex = PARTITION_TOML.replace('members = ["E1", "E2", "E3"]', 'members = [{ name = "x", match = "(" }]')
    ids_not_array = PARTITION_TOML.replace('[[ids]]\nfamily = "OP-01/E"\nshort = "E"\n', "").replace("[[ids]]", "[ids]")
    item_not_table = 'table = ["OP-01/D1"]\n'
    # A string where a list belongs would be read character by character into false gaps.
    members_not_list = PARTITION_TOML.replace('members = ["E1", "E2", "E3"]', 'members = "E1"')
    states_not_list = STATE_TOML.replace('states = ["Open", "Closed"]', 'states = "Open"')
    with_parts = PARTITION_TOML.replace('members = ["E1", "E2", "E3"]', 'members = ["E1", "E2", "E3"]\nparts = PARTS')
    part_not_list = with_parts.replace("PARTS", '{ E3 = "disk" }')
    parts_not_table = with_parts.replace("PARTS", '["E3"]')
    parts_off_members = with_parts.replace("PARTS", '{ E9 = ["disk"] }')
    register_no_reason = PARTITION_TOML.replace(
        'kind = "case"\nkey = 1\nmembers = ["E1", "E2", "E3"]', 'kind = "register"'
    )
    malformed = (bad_regex, ids_not_array, item_not_table, members_not_list, states_not_list, part_not_list)
    for toml in (*malformed, parts_not_table, parts_off_members, register_no_reason):
        result = _run(tmp_path, PARTITION, toml)
        assert result.returncode == 2, (toml, result.stdout, result.stderr)
        assert result.stderr.startswith("observe_tables: "), result.stderr


# Seeded mutants of OP-01's real record: each yields a finding the record itself does not.


def _op01_findings(tmp_path: Path, record: str) -> set[str]:
    return set(_findings(_run(tmp_path, record, OP01_TABLES.read_text(encoding="utf-8"))))


def _mutant_adds(tmp_path: Path, old: str, new: str) -> set[str]:
    record = OP01.read_text(encoding="utf-8")
    assert record.count(old) == 1, old
    return _op01_findings(tmp_path, record.replace(old, new)) - _op01_findings(tmp_path, record)


def test_op01_mutant_dropping_a_partition_row_is_a_gap(tmp_path: Path) -> None:
    added = _mutant_adds(tmp_path, "  | Ω_S(k) = Found(e, folder), the root included | failure: not an item |\n", "")
    # D34 draws its pre-state members from D9's column, so its source check sees the loss too.
    assert added == {
        "- OP-01/D9 table 1: gap: 'Found(e, folder)' is matched by no row",
        "- OP-01/D34 table 1: source: 'Found(e, folder)' occurs in no cell of"
        " Environment column 1 or OP-01/D9 column 1",
    }


def test_op01_mutant_exposing_an_environment_row_twice_is_an_overlap(tmp_path: Path) -> None:
    added = _mutant_adds(tmp_path, "| E6, E15 (O3) |", "| E6, E15, E3 (O3) |")
    assert added == {"- OP-01/D19 table 1: overlap: 'E3' is matched by rows 2 and 3"}


def test_op01_mutant_emptying_a_state_cell_is_reported(tmp_path: Path) -> None:
    added = _mutant_adds(
        tmp_path, "| Closed | `ValueError` (D15) | no-op | no effect |", "| Closed | `ValueError` (D15) | no-op |  |"
    )
    assert added == {"- OP-01/D18 table 1: row 4 ('Closed') has an empty cell in column 4"}


def test_op01_mutant_citing_a_missing_register_row_is_reported(tmp_path: Path) -> None:
    line = next(n for n, text in enumerate(OP01.read_text(encoding="utf-8").splitlines(), 1) if "(D41, row 3)" in text)
    added = _mutant_adds(tmp_path, "(D41, row 3)", "(D41, row 9)")
    assert added == {f"- citation: 'D41, row 9' (line {line}): OP-01/D41's first table has 8 rows"}


def test_op01_observer_mentions_are_no_open_item_citations(tmp_path: Path) -> None:
    # O1 to O3 are axes.md's observers as well as open items; dropping the item O2 must not make
    # the Environment's actor "O2" a dangling citation.
    record = OP01.read_text(encoding="utf-8")
    item = next(line for line in record.splitlines() if line.startswith("- `OP-01/O2`:"))
    added = _mutant_adds(tmp_path, item, item.replace("- `OP-01/O2`:", "- dropped:"))
    assert [f for f in added if f.startswith("- citation: 'O2'")] == []
    # The full form is still checked: OP-01/D10 cites `OP-01/O2`.
    assert any(f.startswith("- citation: 'OP-01/O2'") for f in added)


def test_op01_mutant_dropping_an_environment_row_is_reported(tmp_path: Path) -> None:
    row = next(line for line in OP01.read_text(encoding="utf-8").splitlines() if line.startswith("| `OP-01/E15`"))
    added = _mutant_adds(tmp_path, row + "\n", "")
    assert "- OP-01/D19 table 1: source: 'E15' occurs in no cell of Environment column 1" in added
    assert any(f.startswith("- citation: 'E15'") for f in added)


def test_op01_mutant_adding_an_undeclared_table_is_reported(tmp_path: Path) -> None:
    added = _mutant_adds(
        tmp_path,
        "- **Decision:** (a). OP-01 takes no option",
        "  | A | B |\n  |---|---|\n  | x | y |\n\n- **Decision:** (a). OP-01 takes no option",
    )
    assert len(added) == 1
    assert next(iter(added)).startswith("- declaration: OP-01/D44 table 1 (line ")
