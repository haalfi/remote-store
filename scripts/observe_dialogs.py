"""Pair each decision of an ``/observe`` record with the dialog that answered it (BK-499).

Usage: ``python scripts/observe_dialogs.py <record> <log> [<log> ...]``, the
logs being every ``sdd/decisions/`` file the session's dialogs went to (a
worker restart can split one session across two, BK-397).

Each decision ``### <entry>/D<n>: ...`` carries one line per dialog that
answered it, written by the session (``/observe`` step 3) in the form
``sdd/observe/axes.md`` § Per-question loop states, the one place the armed
session can read it::

    - **Asked:** "<the question's opening words>" → "<the answer's opening words>"

A decision passes when each quoted opening is the start of exactly one answered
question in the logs and each quoted answer is the start of that question's
logged answer, read from the event's ``tool_response`` (RFC-0018). A question
asked more than once pairs by the quoted answer, and a dismissed dialog counts
as unanswered. Anything else fails: a ``###`` heading
off the decision form, a record with no decision, no ``Asked:`` line, one off
that form (named as such), no question or several, or another answer.

The report prints each decision's Decision text beside its question, answer
and the chosen option's description, and beside the record's own text of each
option the Decision adopts by label, for the readers of ``/observe-review`` to
judge what a script cannot: text in the Decision beyond what the dialog
answered (audit-025 § 5, class 2). A reopened record's ``Amends:`` and
``Amended by:`` lines (BK-501) are printed after the Decision they belong to,
so an amended decision is not read as current. Answered questions no
decision pairs with, such as the Environment's first dialog, are listed with
their answer and option, not failed: a record older than the Asked line is
paired by hand from them.

Bound: it checks that a dialog answered each decision, not what the Decision
says beyond the answer, and a quote that is too short to be unique fails
rather than guessing. The decisions are enumerated from the record's own
``### <entry>/D<n>`` headings; the log governs what was asked (RFC-0028 P2).
Advisory, run by ``/observe-review`` only: a record names neither its session
nor its logs, so a gate could not choose which logs to read, and a record
written before the Asked line (OP-01's) fails it on every decision.

Exit 0 when every decision pairs, 1 otherwise, 2 on unusable input.

Drift-gate::

    kind:       pair
    compares:   an /observe record's decisions and their Asked lines ↔ the answered
        dialogs in the session's sdd/decisions/ logs
    domain:     process
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_DECISION = re.compile(r"^### (?P<id>OP-\d{2}/D\d+):")
_ASKED = re.compile(r'^- \*\*Asked:\*\*\s*"(?P<q>[^"]+)"\s*→\s*"(?P<a>[^"]+)"\s*$')
_FIELD = re.compile(r"^- \*\*(?P<name>[A-Za-z ]+):\*\*\s?(?P<rest>.*)$")
# An option label opening the Options field or following ";" or ":" (a follow-up question's
# options, OP-01/D2), and the labels a Decision opens with.
_LABEL = re.compile(r"(?:^|[;:]\s+)\((?P<label>[a-z]{1,4})\)\s")
_ADOPTED = re.compile(r"\((?P<label>[a-z]{1,4})\)")
_POINTERS = ("Amends", "Amended by")
# The harness's answer to a dismissed dialog (RFC-0018 case a'), as check_traces.py matches it.
_DISMISSED = "[User dismissed"


@dataclass
class Dialog:
    question: str
    answer: str
    description: str


@dataclass
class Decision:
    id: str
    text: str
    asked: list[tuple[str, str]]
    options: str = ""
    # A reopen's pointers (axes.md § Per-question loop), as (field, text) in record order:
    # a decision amended twice carries two Amended by lines.
    pointers: list[tuple[str, str]] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    heading_ok: bool = True

    def adopted(self) -> list[str]:
        """The record's own text of each option the Decision adopts by label, in order."""
        marks = list(_LABEL.finditer(self.options))
        ends = [m.start() for m in marks[1:]] + [len(self.options)] * bool(marks)
        texts = {m["label"]: self.options[m.end() : end].strip(" ;,.\n") for m, end in zip(marks, ends, strict=True)}
        lead = re.match(r"(?:\([a-z]{1,4}\)[\s,]*(?:and\s+)?)+", self.text)
        labels = [m["label"] for m in _ADOPTED.finditer(lead[0])] if lead else []
        return [f"({label}) {_norm(texts[label]) if label in texts else 'not found in Options'}" for label in labels]


def _norm(text: str) -> str:
    return " ".join(text.split())


def _join_asked(lines: list[str]) -> list[str]:
    """Join an Asked line's two-space continuation lines onto it, as records hard-wrap every bullet."""
    joined: list[str] = []
    for line in lines:
        if joined and joined[-1].startswith("- **Asked:**") and line.startswith("  ") and line.strip():
            joined[-1] += " " + line.strip()
        else:
            joined.append(line)
    return joined


def decisions(record: str) -> list[Decision]:
    """The record's decisions in order, each with its Decision text and its ``Asked:`` quote."""
    found: list[Decision] = []
    name = None
    for line in _join_asked(record.splitlines()):
        head = _DECISION.match(line)
        if head:
            found.append(Decision(head["id"], "", []))
            name = None
            continue
        if line.startswith("### "):  # a decision heading off the form fails as its own entry
            found.append(Decision(line.strip(), "", [], heading_ok=False))
            name = None
            continue
        if not found or line.startswith("#"):
            name = None if line.startswith("#") else name
            continue
        current = found[-1]
        asked = _ASKED.match(line)
        if asked:
            current.asked.append((_norm(asked["q"]), _norm(asked["a"])))
            name = None
            continue
        if line.startswith("- **Asked:**"):
            current.malformed.append(line[len("- **Asked:** ") :])
            name = None
            continue
        bullet = _FIELD.match(line)
        if bullet:
            name = bullet["name"]
            if name == "Decision":
                current.text = bullet["rest"]
            elif name == "Options":
                current.options = bullet["rest"]
            elif name in _POINTERS:
                current.pointers.append((name, bullet["rest"].strip()))
            continue
        if name == "Decision":
            current.text += "\n" + line
        elif name == "Options":
            current.options += "\n" + line
        elif name in _POINTERS and line.strip():  # a wrapped pointer list
            field_name, text = current.pointers[-1]
            current.pointers[-1] = (field_name, f"{text} {line.strip()}")
    for d in found:
        d.text = d.text.strip()
    return found


def dialogs(logs: list[Path]) -> list[Dialog]:
    """Every answered question in *logs*, duplicates (one event logged twice) dropped."""
    seen: dict[tuple[str, str], Dialog] = {}
    for log in logs:
        # Split on b"\n" alone: the recorder's ensure_ascii=False leaves U+2028, U+2029 and U+0085
        # raw inside strings, where str.splitlines() would cut a record (as check_traces.py does).
        for raw in log.read_bytes().split(b"\n"):
            if not raw.strip():
                continue
            event = json.loads(raw.decode("utf-8"))
            if not isinstance(event, dict):
                raise ValueError(f"{log}: a log line is no JSON object")
            if event.get("event") != "answered":
                continue
            given = event.get("tool_input") or {}
            options = {q.get("question"): q.get("options") or [] for q in given.get("questions") or []}
            # RFC-0018's parsing rules: the answer is tool_response's; the harness also writes into tool_input.
            response = event.get("tool_response")
            answers = response.get("answers") if isinstance(response, dict) else None
            for question, answer in (answers if isinstance(answers, dict) else {}).items():
                if str(answer).startswith(_DISMISSED):
                    continue
                labels = {o.get("label"): o.get("description", "") for o in options.get(question, [])}
                key = (_norm(question), _norm(str(answer)))
                seen.setdefault(key, Dialog(key[0], key[1], labels.get(answer, "(free text or several options)")))
    return list(seen.values())


def pair(record: str, logs: list[Path]) -> tuple[list[str], list[str], bool]:
    """The report's lines, the unpaired dialogs (question, answer, option), and whether every decision paired."""
    pool = dialogs(logs)
    used: set[int] = set()
    lines: list[str] = []
    ok = True
    found = decisions(record)
    if not found:
        lines.append("## FAIL no decision found: no heading '### <entry>/D<n>:'")
        ok = False
    for d in found:
        verdicts = [] if d.heading_ok else ["FAIL heading not in the form '### <entry>/D<n>:'"]
        verdicts += [f"FAIL Asked line not in axes.md's form: {bad!r}" for bad in d.malformed]
        verdicts += [] if d.asked or d.malformed else ["FAIL no Asked line"]
        paired = []
        for quote, answer in d.asked:
            hits = [i for i, g in enumerate(pool) if g.question.startswith(quote)]
            # One question asked twice (re-asked after another answer) pairs by its quoted answer.
            narrowed = [i for i in hits if pool[i].answer.startswith(answer)]
            one_question = len({pool[i].question for i in hits}) == 1
            hits = narrowed if len(hits) > 1 and one_question and len(narrowed) == 1 else hits
            if len(hits) != 1:
                verdicts.append(f"FAIL {len(hits)} answered questions start with {quote!r}")
                continue
            used.add(hits[0])
            paired.append(pool[hits[0]])
            if not pool[hits[0]].answer.startswith(answer):
                verdicts.append(f"FAIL answered {pool[hits[0]].answer!r}, not {answer!r}")
        ok = ok and not verdicts
        lines += [f"## {d.id}: {'; '.join(verdicts) or 'ok'}", f"Decision: {d.text}"]
        lines += [f"{name}: {text}" for name, text in d.pointers]
        lines += [f"Adopted option: {text}" for text in d.adopted()]
        for g in paired:
            lines += [f"Question: {g.question}", f"Answer: {g.answer}", f"Option: {g.description}"]
        lines.append("")
    unpaired = [
        f"{g.question}\n  Answer: {g.answer}\n  Option: {g.description}" for i, g in enumerate(pool) if i not in used
    ]
    return lines, unpaired, ok


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        record = Path(argv[1]).read_text(encoding="utf-8")
        lines, unpaired, ok = pair(record, [Path(p) for p in argv[2:]])
    except (OSError, ValueError) as exc:
        print(f"observe_dialogs: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    print("# Answered questions no decision pairs with")
    print("\n".join(f"- {q}" for q in unpaired) or "none")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main(sys.argv))
