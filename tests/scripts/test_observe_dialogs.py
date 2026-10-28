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


def _answered(question: str, answer: str, options: dict[str, str] | None = None, harness: str | None = None) -> str:
    # The recorder's shape: the harness also writes into tool_input, but tool_response is authoritative (RFC-0018).
    opts = [{"label": k, "description": v} for k, v in (options or {answer: "the chosen option"}).items()]
    return json.dumps(
        {
            "event": "answered",
            "tool_input": {
                "questions": [{"question": question, "options": opts}],
                "answers": {question: harness or answer},
            },
            "tool_response": {"answers": {question: answer}},
        },
        ensure_ascii=False,  # as record_decision.py writes, so U+2028 and its kin stay raw
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
    unpaired = "- Which backlog item?\n  Answer: BK-485\n  Option: the chosen option\n"
    assert result.stdout.endswith("# Answered questions no decision pairs with\n" + unpaired)


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
        # The answer narrows only one question asked twice, never a quote too short to be unique.
        ((("AX-1,", "Root"),), "FAIL 2 answered questions start with 'AX-1,'"),
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


def test_a_question_dismissed_then_answered_pairs_with_its_answer(tmp_path: Path) -> None:
    # RFC-0018 case a': a dismissal is logged as an answer; the re-asked question must still pair.
    dismissed = _answered(FORMS, "[User dismissed — do not proceed, wait for next instruction]")
    record = _record(_decision(1, ("AX-1, forms.", "Bytes")))
    result = _run(tmp_path, record, [dismissed, _answered(FORMS, "Bytes")])
    assert result.returncode == 0, result.stdout
    assert "## OP-01/D1: ok\n" in result.stdout
    assert "User dismissed" not in result.stdout


def test_the_same_question_answered_twice_pairs_by_the_quoted_answer(tmp_path: Path) -> None:
    record = _record(_decision(1, ("AX-1, forms.", "Text")))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes"), _answered(FORMS, "Text only")])
    assert result.returncode == 0, result.stdout
    assert "Answer: Text only\n" in result.stdout


def test_the_answer_is_read_from_tool_response(tmp_path: Path) -> None:
    # RFC-0018's parsing rules: tool_response.answers governs where it and tool_input differ.
    record = _record(_decision(1, ("AX-1, forms.", "Bytes")))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes", harness="Text")])
    assert result.returncode == 0, result.stdout
    assert "Answer: Bytes\n" in result.stdout


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085"])
def test_a_raw_unicode_line_separator_stays_inside_its_record(tmp_path: Path, separator: str) -> None:
    # check_traces.py's hazard: str.splitlines() would cut the recorder's ensure_ascii=False line here.
    record = _record(_decision(1, ("AX-1, forms.", "Bytes")))
    result = _run(tmp_path, record, [_answered(FORMS, f"Bytes{separator}pasted")])
    assert result.returncode == 0, result.stderr
    assert "## OP-01/D1: ok\n" in result.stdout


def test_unpaired_dialogs_carry_their_answer_and_option(tmp_path: Path) -> None:
    # A record older than the Asked line is paired by hand from this section (/observe-review step 1).
    log = [_answered(ROOT_Q, "Root is a folder", {"Root is a folder": "spec 052's root"})]
    result = _run(tmp_path, _record(_decision(1, text="(a).")), log)
    section = result.stdout.split("# Answered questions no decision pairs with\n", 1)[1]
    assert section == f"- {ROOT_Q}\n  Answer: Root is a folder\n  Option: spec 052's root\n"


def test_a_heading_off_the_decision_form_fails_and_takes_its_own_fields(tmp_path: Path) -> None:
    slipped = _decision(2, ("AX-1, the root.", "Root"), text="(b). The slipped one.").replace(
        "### OP-01/D2: A title (AX-1)", "### OP-01/D2 — A title (AX-1)"
    )
    record = _record(_decision(1, ("AX-1, forms.", "Bytes"), text="(a). The first."), slipped)
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes"), _answered(ROOT_Q, "Root is a folder")])
    assert result.returncode == 1
    assert "## OP-01/D1: ok\nDecision: (a). The first.\n" in result.stdout
    assert "## ### OP-01/D2 — A title (AX-1): FAIL heading not in the form '### <entry>/D<n>:'\n" in result.stdout


def test_a_record_with_no_decision_fails(tmp_path: Path) -> None:
    result = _run(tmp_path, "# OP-01: observable semantics\n\nNo decisions here.\n", [_answered(FORMS, "Bytes")])
    assert result.returncode == 1
    assert "FAIL no decision found" in result.stdout


def test_a_wrapped_asked_line_is_joined_like_any_bullet(tmp_path: Path) -> None:
    # Records hard-wrap bullets onto two-space continuation lines (OP-01.md), Asked included.
    first = '- **Asked:** "AX-1, forms. Scenario: a caller reads a config. Which forms'
    wrapped = "\n".join([first, '  does OP-01 offer?" → "Bytes"'])
    record = _record(_decision(1, text="(a).").replace("- **Decision:**", wrapped + "\n- **Decision:**"))
    result = _run(tmp_path, record, [_answered(FORMS, "Bytes")])
    assert result.returncode == 0, result.stdout
    assert "## OP-01/D1: ok\n" in result.stdout


def test_an_answer_holding_a_quote_pairs_by_its_opening(tmp_path: Path) -> None:
    # axes.md item 5: the answer, like the question, is quoted up to its first '"'.
    record = _record(_decision(1, ("AX-1, forms.", "Raise on read(")))
    result = _run(tmp_path, record, [_answered(FORMS, 'Raise on read("") as a caller error')])
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("line", ["[1, 2]", '"text"', "3"])
def test_a_log_line_that_is_no_object_is_unusable_input(tmp_path: Path, line: str) -> None:
    result = _run(tmp_path, _record(_decision(1, ("AX-1, forms.", "Bytes"))), [line])
    assert result.returncode == 2
    assert "observe_dialogs:" in result.stderr


def test_unusable_input_exits_2(tmp_path: Path) -> None:
    result = _run(tmp_path, _record(), ["not json"])
    assert result.returncode == 2
    assert "observe_dialogs:" in result.stderr
    usage = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert usage.returncode == 2
    assert "Usage" in usage.stderr
