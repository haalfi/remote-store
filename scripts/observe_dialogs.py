"""Pair each decision of an ``/observe`` record with the dialog that answered it (BK-499).

Usage: ``python scripts/observe_dialogs.py <record> <log> [<log> ...]``, the
logs being every ``sdd/decisions/`` file the session's dialogs went to (a
worker restart can split one session across two, BK-397).

Each decision ``### <entry>/D<n>: ...`` carries one line per dialog that
answered it, written by the session (``/observe`` step 3)::

    - **Asked:** "<the question's opening words>" → "<the answer chosen>"

A decision passes when each quoted opening is the start of exactly one answered
question in the logs and each quoted answer is the start of that question's
logged answer. Anything else fails: no ``Asked:`` line, no question or several,
or another answer. The report prints each decision's Decision text beside its
question, answer and the chosen option's description, for the reader of
``/observe-review`` to judge what a script cannot: text in the Decision beyond
what the dialog answered (audit-025 § 5, class 2). Answered questions no
decision pairs with, such as the Environment's first dialog, are listed, not
failed.

Bound: it checks that a dialog answered each decision, not what the Decision
says beyond the answer, and a quote that is too short to be unique fails
rather than guessing. The decisions are enumerated from the record's own
``### <entry>/D<n>`` headings; the log governs what was asked (RFC-0028 P2).
Advisory, run by ``/observe-review`` only: the session's logs are uncommitted
until that review commits them, so no gate has them.

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
from dataclasses import dataclass
from pathlib import Path

_DECISION = re.compile(r"^### (?P<id>OP-\d{2}/D\d+):")
_ASKED = re.compile(r'^- \*\*Asked:\*\*\s*"(?P<q>[^"]+)"\s*→\s*"(?P<a>[^"]+)"\s*$')
_FIELD = re.compile(r"^- \*\*(?P<name>[A-Za-z ]+):\*\*\s?(?P<rest>.*)$")


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


def _norm(text: str) -> str:
    return " ".join(text.split())


def decisions(record: str) -> list[Decision]:
    """The record's decisions in order, each with its Decision text and its ``Asked:`` quote."""
    found: list[Decision] = []
    field = None
    for line in record.splitlines():
        head = _DECISION.match(line)
        if head:
            found.append(Decision(head["id"], "", []))
            field = None
            continue
        if not found or line.startswith("#"):
            field = None if line.startswith("#") else field
            continue
        current = found[-1]
        asked = _ASKED.match(line)
        if asked:
            current.asked.append((_norm(asked["q"]), _norm(asked["a"])))
            field = None
            continue
        bullet = _FIELD.match(line)
        if bullet:
            field = bullet["name"]
            if field == "Decision":
                current.text = bullet["rest"]
            continue
        if field == "Decision":
            current.text += "\n" + line
    for d in found:
        d.text = d.text.strip()
    return found


def dialogs(logs: list[Path]) -> list[Dialog]:
    """Every answered question in *logs*, duplicates (one event logged twice) dropped."""
    seen: dict[tuple[str, str], Dialog] = {}
    for log in logs:
        for line in log.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event") != "answered":
                continue
            given = event.get("tool_input") or {}
            options = {q.get("question"): q.get("options") or [] for q in given.get("questions") or []}
            for question, answer in (given.get("answers") or {}).items():
                labels = {o.get("label"): o.get("description", "") for o in options.get(question, [])}
                key = (_norm(question), _norm(str(answer)))
                seen.setdefault(key, Dialog(key[0], key[1], labels.get(answer, "(free text or several options)")))
    return list(seen.values())


def pair(record: str, logs: list[Path]) -> tuple[list[str], list[str], bool]:
    """The report's lines, the unpaired dialogs' questions, and whether every decision paired."""
    pool = dialogs(logs)
    used: set[int] = set()
    lines: list[str] = []
    ok = True
    for d in decisions(record):
        verdicts, paired = [] if d.asked else ["FAIL no Asked line"], []
        for quote, answer in d.asked:
            hits = [i for i, g in enumerate(pool) if g.question.startswith(quote)]
            if len(hits) != 1:
                verdicts.append(f"FAIL {len(hits)} answered questions start with {quote!r}")
                continue
            used.add(hits[0])
            paired.append(pool[hits[0]])
            if not pool[hits[0]].answer.startswith(answer):
                verdicts.append(f"FAIL answered {pool[hits[0]].answer!r}, not {answer!r}")
        ok = ok and not verdicts
        lines += [f"## {d.id}: {'; '.join(verdicts) or 'ok'}", f"Decision: {d.text}"]
        for g in paired:
            lines += [f"Question: {g.question}", f"Answer: {g.answer}", f"Option: {g.description}"]
        lines.append("")
    unpaired = [g.question for i, g in enumerate(pool) if i not in used]
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
