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

Three more sections come before that list, also not failed (BK-510). A worker
restart files a dialog's answer under another session id, so the asking
session may never see it and a later one asks again. **Dialogs split across
logs** names each dialog asked in one log and answered in another, by its
``tool_use_id``. **Asked with no answer in these logs** names one whose answer
is in no log given, which usually means a log is missing from the arguments.
**Items asked in more than one dialog** lists every dialog naming one open item
(``<entry>/O<n>`` opening the question), in answer order, so a reader can see
two answers to one question. ``unrecorded()`` is the ground hook's half: the
answers to the record's open items that no Asked line records.

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


# An open item a question names by its opening, e.g. "OP-01/O66 (AX-6): ..." (BK-510).
_ITEM = re.compile(r"(?P<item>OP-\d{2}/O\d+)(?!\d)")
_ITEM_BULLET = re.compile(r"^- `(?P<item>OP-\d{2}/O\d+)`")


@dataclass
class Dialog:
    question: str
    answer: str
    description: str
    # Where the answer was logged (BK-510), empty in records built by hand.
    ts: str = ""
    log: str = ""
    tool_use_id: str = ""

    def item(self) -> str | None:
        """The open item the question opens with, or None."""
        m = _ITEM.match(self.question)
        return m["item"] if m else None


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


def _events(log: Path) -> list[dict]:
    """The log's events in line order; ValueError on a line that is no JSON object."""
    events = []
    # Split on b"\n" alone: the recorder's ensure_ascii=False leaves U+2028, U+2029 and U+0085
    # raw inside strings, where str.splitlines() would cut a record (as check_traces.py does).
    for raw in log.read_bytes().split(b"\n"):
        if not raw.strip():
            continue
        event = json.loads(raw.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError(f"{log}: a log line is no JSON object")
        events.append(event)
    return events


def _readable(logs: list[Path], errors: list[str] | None) -> list[tuple[Path, list[dict]]]:
    """Each log with its events; with *errors* a list, an unusable log is named there and skipped."""
    read = []
    for log in logs:
        try:
            read.append((log, _events(log)))
        except (OSError, ValueError) as exc:
            if errors is None:
                raise
            errors.append(f"{log.name}: {type(exc).__name__}")
    return read


def dialogs(logs: list[Path], errors: list[str] | None = None) -> list[Dialog]:
    """Every answered question in *logs*, duplicates (one event logged twice) dropped."""
    seen: dict[tuple[str, str], Dialog] = {}
    for log, events in _readable(logs, errors):
        for event in events:
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
                # A multiSelect answer can be logged as a list, which names no single label.
                label = labels.get(answer) if isinstance(answer, str) else None
                found = Dialog(key[0], key[1], "(free text or several options)" if label is None else label)
                found.ts, found.log, found.tool_use_id = (
                    str(event.get("ts") or ""),
                    log.name,
                    str(event.get("tool_use_id") or ""),
                )
                seen.setdefault(key, found)
    return list(seen.values())


def splits(logs: list[Path]) -> tuple[list[str], list[str]]:
    """Dialogs answered in another log than they were asked in, and asked ones no given log answers.

    A worker restart files the answer, and a replayed ``asked`` line, under another
    session id (BK-510), so a dialog is split when any ``asked`` line of its
    ``tool_use_id`` sits in a log other than its ``answered`` line's.
    """
    asked: dict[str, list[tuple[str, str, str]]] = {}
    answered: dict[str, tuple[str, str]] = {}
    for log, events in _readable(logs, None):
        for event in events:
            tid = event.get("tool_use_id")
            if not tid:
                continue
            if event.get("event") == "asked":
                questions = (event.get("tool_input") or {}).get("questions") or [{}]
                first = _norm(str(questions[0].get("question") or "(no question)"))
                asked.setdefault(tid, []).append((log.name, str(event.get("ts") or ""), first))
            elif event.get("event") == "answered":
                answered.setdefault(tid, (log.name, str(event.get("ts") or "")))
    split, unanswered = [], []
    for tid, lines in asked.items():
        name, ts, first = lines[0]
        if tid not in answered:
            unanswered.append(f"{first}\n  Asked in {name} at {ts}")
            continue
        others = sorted({n for n, _, _ in lines} - {answered[tid][0]})
        if others:
            split.append(
                f"{first}\n  Asked in {', '.join(others)}, answered in {answered[tid][0]} at {answered[tid][1]}"
            )
    return split, unanswered


def repeats(pool: list[Dialog]) -> dict[str, list[Dialog]]:
    """Each open item named by questions of more than one dialog, its dialogs in answer order (BK-510)."""
    by_item: dict[str, list[Dialog]] = {}
    for g in pool:
        if g.item():
            by_item.setdefault(g.item() or "", []).append(g)
    many = {k: v for k, v in by_item.items() if len({g.tool_use_id or id(g) for g in v}) > 1}
    return {k: sorted(v, key=lambda g: g.ts) for k, v in many.items()}


def open_items(record: str) -> set[str]:
    """The record's Open items no ``Decided by`` closes."""
    section = record.split("\n## Open items\n", 1)
    if len(section) < 2:
        return set()
    body = section[1].split("\n## ", 1)[0]
    found, current = {}, None
    for line in body.splitlines():
        bullet = _ITEM_BULLET.match(line)
        if bullet:
            current = bullet["item"]
            found[current] = line
        elif current and line.startswith("  "):
            found[current] += " " + line.strip()
        elif line.strip():
            current = None
    return {item for item, text in found.items() if "Decided by" not in _norm(text)}


def unrecorded(record: str, pool: list[Dialog]) -> list[Dialog]:
    """Answered questions naming an open item that no Asked line of the record pairs with (BK-510).

    These are answers the record should hold and does not: most often a dialog a
    worker restart answered into another session's log, so the session that
    asked never wrote its decision.
    """
    still_open = open_items(record)
    asked = [qa for d in decisions(record) for qa in d.asked]
    return [
        g
        for g in pool
        if g.item() in still_open and not any(g.question.startswith(q) and g.answer.startswith(a) for q, a in asked)
    ]


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
    logs = [Path(p) for p in argv[2:]]
    try:
        record = Path(argv[1]).read_text(encoding="utf-8")
        lines, unpaired, ok = pair(record, logs)
        split, unanswered = splits(logs)
        repeated = repeats(dialogs(logs))
    except (OSError, ValueError) as exc:
        print(f"observe_dialogs: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    print("# Dialogs split across logs")
    print("\n".join(f"- {s}" for s in split) or "none")
    print("# Asked with no answer in these logs")
    print("\n".join(f"- {s}" for s in unanswered) or "none")
    print("# Items asked in more than one dialog")
    for item, found in repeated.items():
        print(f"- {item}")
        print("\n".join(f"  {g.ts}: {g.question}\n    Answer: {g.answer}" for g in found))
    if not repeated:
        print("none")
    print("# Answered questions no decision pairs with")
    print("\n".join(f"- {q}" for q in unpaired) or "none")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main(sys.argv))
