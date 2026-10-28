"""Tests for ``scripts/observe_dialogs.py`` (RFC-0028 P2, BK-499).

The script pairs each decision of an ``/observe`` record with the answered
dialog in the session's decision logs. Pinned: a decision passes only when
every ``Asked:`` quote starts exactly one answered question and its answer;
each other case fails the run; a dialog split across two logs pairs; and the
report sets each Decision beside its dialog for the reader.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/observe_dialogs.py"

FORMS = "AX-1, forms. Scenario: a caller reads a config. Which forms does OP-01 offer?"
ROOT_Q = "AX-1, the root. Scenario: read(''). What is it?"
SHAPE = "AX-1, the stream's shape. Scenario: copyfileobj. What object?"


def _answered(question: str, answer: str, options: dict[str, str] | None = None) -> str:
    opts = [{"label": k, "description": v} for k, v in (options or {answer: "the chosen option"}).items()]
    return json.dumps(
        {
            "event": "answered",
            "tool_input": {"questions": [{"question": question, "options": opts}], "answers": {question: answer}},
        }
    )


def _record(*decisions: str) -> str:
    return "# OP-01: observable semantics\n\n## Decisions\n\n" + "\n".join(decisions) + "\n## Axis status\n"


def _decision(n: int, *asked: tuple[str, str], text: str = "(a).") -> str:
    lines = [f"### OP-01/D{n}: A title (AX-1)", "", "- **Scenario:** s."]
    lines += [f'- **Asked:** "{q}" → "{a}"' for q, a in asked]
    lines += [f"- **Decision:** {text}", "- **Consistency check:** none.", ""]
    return "\n".join(lines)


def _run(tmp_path: Path, record: str, *logs: list[str]) -> subprocess.CompletedProcess[str]:
    rec = tmp_path / "OP-01.md"
    rec.write_text(record, encoding="utf-8")
    paths = []
    for i, lines in enumerate(logs):
        log = tmp_path / f"log{i}.jsonl"
        log.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        paths.append(str(log))
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(rec), *paths], capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_every_decision_paired_passes_and_shows_its_dialog(tmp_path: Path) -> None:
    record = _record(
        _decision(1, ("AX-1, forms.", "Bytes, text"), text="(a). Three operations,\n  each sync and async."),
        _decision(2, ("AX-1, the root.", "Root is a folder")),
    )
    log = [
        _answered(
            FORMS, "Bytes, text, binary stream (Recommended)", {"Bytes, text, binary stream (Recommended)": "N-01"}
        ),
        _answered(ROOT_Q, "Root is a folder like any other (Recommended)"),
        _answered("Which backlog item?", "BK-485"),
    ]
    result = _run(tmp_path, record, log)
    assert result.returncode == 0, result.stdout
    head = "## OP-01/D1: ok\nDecision: (a). Three operations,\n  each sync and async.\n"
    assert head + "Adopted option: (a) not found in Options\nQuestion: " + FORMS in result.stdout
    assert "Answer: Bytes, text, binary stream (Recommended)\nOption: N-01" in result.stdout
    assert result.stdout.endswith("# Answered questions no decision pairs with\n- Which backlog item?\n")


def test_the_report_quotes_each_adopted_option(tmp_path: Path) -> None:
    # Audit-025 C2: an option's own wording, adopted by its label, conflicted where the Decision did not.
    decision = _decision(1, ("AX-1, forms.", "Bytes"), text="(b) and (c). Both.")
    decision = decision.replace(
        "- **Scenario:** s.",
        "- **Scenario:** s.\n- **Options:** (a) none; (b) the next read\n  resumes, unlike (a); (c) a third.",
    )
    result = _run(tmp_path, _record(decision), [_answered(FORMS, "Bytes")])
    assert "Adopted option: (b) the next read resumes, unlike (a)\nAdopted option: (c) a third\n" in result.stdout
    assert "Adopted option: (a)" not in result.stdout


def test_a_follow_up_label_after_a_colon_is_adopted_and_a_missing_one_is_reported(tmp_path: Path) -> None:
    # OP-01/D2's shape: a follow-up question's options open after ": " inside the same Options field.
    decision = _decision(2, ("AX-1, forms.", "Bytes"), text="(c) and (i) and (z): the maintainer's.")
    decision = decision.replace(
        "- **Scenario:** s.",
        "- **Scenario:** s.\n- **Options:** (a) one; (c) the file object of (a). Follow-up,\n"
        "  whether it seeks: (i) not seekable; (ii) seekable.",
    )
    result = _run(tmp_path, _record(decision), [_answered(FORMS, "Bytes")])
    assert "Adopted option: (c) the file object of (a). Follow-up, whether it seeks\n" in result.stdout
    assert "Adopted option: (i) not seekable\n" in result.stdout
    assert "Adopted option: (z) not found in Options\n" in result.stdout


@pytest.mark.parametrize(
    "line",
    ['- **Asked:** "AX-1, forms." -> "Bytes"', "- **Asked:** “AX-1, forms.” → “Bytes”"],
)
def test_an_asked_line_off_the_form_fails_by_name(tmp_path: Path, line: str) -> None:
    # The session writes the form axes.md states; a slip must not read as a missing line.
    record = _record(_decision(1, text="(a).").replace("- **Decision:**", line + "\n- **Decision:**"))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes")])
    assert result.returncode == 1
    assert f"## OP-01/D1: FAIL Asked line not in axes.md's form: {line[13:]!r}\n" in result.stdout


def test_a_decision_answered_in_two_split_logs_pairs(tmp_path: Path) -> None:
    record = _record(_decision(2, ("AX-1, the stream's shape.", "File object"), ("AX-1, forms.", "Bytes")))
    result = _run(tmp_path, record, [_answered(SHAPE, "File object plus chunks")], [_answered(FORMS, "Bytes")])
    assert result.returncode == 0, result.stdout
    assert "Question: " + SHAPE in result.stdout
    assert "Question: " + FORMS in result.stdout


@pytest.mark.parametrize(
    ("asked", "verdict"),
    [
        ((), "FAIL no Asked line"),
        ((("AX-9, nothing", "x"),), "FAIL 0 answered questions start with 'AX-9, nothing'"),
        ((("AX-1,", "x"),), "FAIL 2 answered questions start with 'AX-1,'"),
        ((("AX-1, the root.", "Not a folder"),), "FAIL answered 'Root is a folder', not 'Not a folder'"),
    ],
)
def test_an_unpaired_or_mismatched_decision_fails(
    tmp_path: Path, asked: tuple[tuple[str, str], ...], verdict: str
) -> None:
    record = _record(_decision(1, ("AX-1, forms.", "Bytes")), _decision(2, *asked))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes"), _answered(ROOT_Q, "Root is a folder")])
    assert result.returncode == 1
    assert "## OP-01/D1: ok\n" in result.stdout
    assert f"## OP-01/D2: {verdict}\n" in result.stdout


def test_the_same_answer_logged_twice_counts_once(tmp_path: Path) -> None:
    # A worker restart can log one answered event in both halves of a split session.
    record = _record(_decision(1, ("AX-1, forms.", "Bytes")))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes")], [_answered(FORMS, "Bytes")])
    assert result.returncode == 0, result.stdout


def test_unusable_input_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, _record(), ["not json"])
    assert result.returncode == 2
    assert "observe_dialogs:" in result.stderr
    usage = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert usage.returncode == 2
    assert "Usage" in usage.stderr
