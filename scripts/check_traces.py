"""PR-time gate: every trace under ``sdd/traces/`` parses cleanly and matches the schema.

``sdd/traces/_schema.yml`` is the single authority for the shape of an
agent use-case trace: which fields are required, the id/pattern
constraints, the ``read_type`` and ``audience`` enums, and
``additionalProperties: false`` on every object. BK-193 made ``audience``
*required* in the schema but left enforcement as an authoring convention —
"validated on the next aggregator run" — and no aggregator ever landed, so
nothing checked a trace at commit time. Drift accumulated unnoticed (a
top-level ``notes`` field, hyphenated phase ids). ID-179 promotes the
convention to a mechanical gate.

What this gate does
-------------------
For every ``sdd/traces/[!_]*.yml`` file (the ``[!_]`` glob skips
infrastructure files like ``_schema.yml`` itself, per the schema's own
note; it lives in ``scripts/_trace_corpus.py`` so this gate and every
report over the corpus share one definition of "a trace"), parse
the YAML and validate the document against the *whole*
schema using ``jsonschema``. The draft is selected from the schema's
``$schema`` keyword, so the check tracks whatever JSON Schema dialect the
schema declares. Two further self-checks run first:

* the schema itself is validated with ``check_schema`` — a malformed
  schema fails loudly here rather than silently passing every trace, and
* every entry in the schema's top-level ``examples`` block is validated
  against the schema. ``examples`` is a JSON Schema *annotation*
  (jsonschema never validates it), so an example that drifts out of sync
  with the constraints would otherwise mislead authors who copy it as a
  template.

**One rule, not only the pair.** Parsing goes through
``_trace_corpus.load_trace``, which refuses a repeated mapping key at any depth
instead of letting YAML keep the last silently. That is a rule about a single
artifact rather than a comparison against the schema: the survivor of a
last-wins merge is well-formed, so schema validation passes while half the
content is gone. Measured — ``BK-221-test-pbt-write-result-s3-azure-per-backend.yml``
carried ``surprising_ripples`` twice and this gate reported the corpus clean.
The schema is read the same way, because a duplicate key *there* disarms the
gate for the whole corpus rather than for one file.

What this gate does NOT check
-----------------------------
Conventions the schema documents in prose but cannot express in JSON
Schema are out of scope and stay reviewer-enforced: that the trace's own
id is the first ``source_items`` entry, that ``audience`` is sorted by
priority, that an ``outcome`` tag honestly reflects how a read landed, or
that the filename slug matches the title. The gate certifies structural
conformance, not authoring honesty.

The duplicate-key rule reaches repeated *keys*, not repeated *content*: two
differently-named keys holding the same list, or one key whose list repeats an
entry, are both well-formed and pass.

Decision logs (RFC-0018 D4.2)
-----------------------------
For each path a trace lists under ``decisions:`` that the schema accepts, the
log exists, every line decodes as UTF-8 and parses as one JSON object, and no
``tool_use_id`` has two
``answered`` events. A path the schema rejects is reported by the schema and not
read. What an author may do about each failure is stated with the key, in
``sdd/traces/_schema.yml``. **Reported, not failed**, as notes on stdout: a
question left ``unanswered`` (no ``answered`` event, no answer for it, or an
answer starting with the dismissal prefix ``[User dismissed``), because
declining a dialog is a legitimate act and the report is how it stays visible;
an event of a kind other than ``asked`` and ``answered``, so a later hook
registration cannot break this reader (D3); an ``asked`` event whose
``tool_input.questions`` is not a list of objects, which would otherwise drop
out of the unanswered report silently; an ``answered`` event with no
``asked`` event; and an event whose ``tool_use_id`` is not a string (missing,
null, a list or an object), which cannot pair and is skipped. Lines are split on
the byte ``\\n`` alone, the only break the recorder writes, and decoded one at a
time, so an append cut inside a multi-byte character fails its own line. An
entry listed twice is read once.

Bounds: it reads only the logs a trace lists. Whether a trace lists *every* log
its work produced, or a log that belongs to other work, is D4.0's binding rule
and is not checked here. The dismissal prefix is an undocumented harness string
(RFC-0018 D3): a rewording passes as an answer, and free text starting with the
prefix reads as a dismissal. Outcomes other than ``unanswered`` are not derived.
A question whose object lacks a ``question`` key is matched under the text
``None``, so it reads as unanswered rather than being skipped.

Exit codes
==========

* ``0`` — every trace (and every schema example) validates, and every listed
  log passes; notes may still be printed.
* ``1`` — one or more violations, printed to stderr as
  ``file: <json-path>: <message>``, sorted for stable diffs. A
  ``decisions[N]`` path is about that entry: a schema failure (a path that does
  not match, an entry that is not a string) or a missing log is the trace's
  entry to fix, only a ``<log> line K:`` message is a fault in that log, and
  an ``OSError`` reading it is the checkout's (permissions, a locked file).

Run with::

    hatch run lint                  # bundled
    hatch run docs-gate             # bundled; the gate CI runs for an
                                    # ``sdd/``-only change, which ``lint``
                                    # skips (CODE_PAT) even though such a
                                    # change is what adds a trace
    python scripts/check_traces.py

Drift-gate::

    kind:       pair
    compares:   every trace under sdd/traces/ ↔ the schema in sdd/traces/_schema.yml
    domain:     process

Drift-gate::

    kind:       rule
    rule: no file this gate parses repeats a mapping key at any depth — every
        trace under sdd/traces/, and sdd/traces/_schema.yml itself
    domain:     process

Drift-gate::

    kind:       pair
    compares:   a trace's decisions: list ↔ the sdd/decisions/ logs that exist
    domain:     process

Drift-gate::

    kind:       rule
    rule: every sdd/decisions/ log a trace lists has one JSON object per line
        and no dialog answered twice
    domain:     process
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema.validators import validator_for

sys.path.insert(0, str(Path(__file__).parent))

from _trace_corpus import ROOT, TRACES_DIR, iter_trace_files, load_trace  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterable

    from jsonschema.protocols import Validator

SCHEMA_PATH = TRACES_DIR / "_schema.yml"

# The "[!_]" carve-out that skips _schema.yml lives in _trace_corpus.py,
# shared with every corpus consumer so the gate and the reports cannot
# disagree about what a trace is. DRIFT-RULES Rule 1.


@dataclass(frozen=True)
class Violation:
    """A single schema failure, located at ``source`` and ``path``."""

    source: str
    path: str
    message: str

    def format(self) -> str:
        return f"{self.source}: {self.path}: {self.message}"


@dataclass(frozen=True)
class Report:
    """What one run found: ``violations`` fail the gate, ``notes`` are printed and do not."""

    violations: list[Violation]
    notes: list[Violation]


# The harness's dismissal answer, matched by prefix (RFC-0018 D3, follow-up case a').
_DISMISSED_PREFIX = "[User dismissed"


def _json_path(absolute_path: Iterable[Any]) -> str:
    """Render a jsonschema error path as a compact ``a.b[0].c`` string."""
    parts: list[str] = []
    for part in absolute_path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        elif parts:
            parts.append(f".{part}")
        else:
            parts.append(str(part))
    return "".join(parts) if parts else "(root)"


def load_schema(schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """Parse the trace schema YAML into a mapping, refusing duplicate keys.

    The schema is read with the same strict loader as the traces, because it is
    the one file here whose duplicate key disarms the gate for the *whole*
    corpus rather than for one trace: two ``required:`` keys under
    ``properties.review`` leave a schema that ``check_schema`` passes, and
    every trace then validates against constraints nobody wrote. Measured
    under ``safe_load``, a schema with two ``required:`` keys validated a
    document against the survivor and reported the mismatch as an ordinary
    ``(root)`` violation, which reads as the trace being wrong.
    """
    return load_trace(schema_path.read_text(encoding="utf-8"))


def _validate_document(
    validator: Validator,
    document: Any,
    *,
    source: str,
) -> list[Violation]:
    """Collect every schema error for one parsed document, sorted by path."""
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    return [Violation(source=source, path=_json_path(e.absolute_path), message=e.message) for e in errors]


def _questions(event: dict[str, Any]) -> list[tuple[str, str]]:
    """``(question, header)`` per question of an ``asked`` event; empty if its input is not that shape."""
    tool_input = event.get("tool_input")
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    if not isinstance(questions, list):
        return []
    return [(str(q.get("question")), str(q.get("header", q.get("question")))) for q in questions if isinstance(q, dict)]


def _check_decision_log(root: Path, name: str, *, source: str, path: str) -> Report:
    """RFC-0018 D4.2 for the log listed as *name*: exists, parses, one ``answered`` per dialog."""
    violations: list[Violation] = []
    notes: list[Violation] = []
    log = root / name
    if not log.is_file():
        return Report(
            [
                Violation(
                    source, path, f"{name}: log does not exist; fix the trace's entry, never create a log to match it"
                )
            ],
            [],
        )
    try:
        data = log.read_bytes()
    except OSError as exc:
        return Report([Violation(source, path, f"{name}: {type(exc).__name__}: {exc}")], [])

    asked: dict[str, dict[str, Any]] = {}
    answered: dict[str, tuple[int, dict[str, Any], str]] = {}
    # Split on b"\n" alone, the only break the recorder writes, and decode per
    # line. Its ensure_ascii=False leaves U+2028, U+2029 and U+0085 raw inside
    # strings, where str.splitlines() would cut a real record; and an append cut
    # inside a multi-byte character then fails its own line, not the whole file.
    # A CRLF checkout's trailing "\r" is whitespace json.loads accepts.
    chunks = data.split(b"\n")
    if chunks and not chunks[-1]:
        chunks.pop()
    for lineno, chunk in enumerate(chunks, start=1):
        try:
            raw = chunk.decode("utf-8")
        except UnicodeDecodeError as exc:
            violations.append(Violation(source, path, f"{name} line {lineno}: not UTF-8 ({exc.reason})"))
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            violations.append(Violation(source, path, f"{name} line {lineno}: not JSON ({exc.msg})"))
            continue
        if not isinstance(event, dict):
            violations.append(Violation(source, path, f"{name} line {lineno}: not a JSON object"))
            continue
        kind, tool_use_id = event.get("event"), event.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            # Missing, null, a list or an object: none can pair. Null in
            # particular would pair unrelated id-less dialogs under one key.
            notes.append(Violation(source, path, f"{name} line {lineno}: tool_use_id is not a string, skipped"))
            continue
        if kind == "asked":
            asked.setdefault(tool_use_id, event)
        elif kind == "answered":
            if tool_use_id in answered:
                first, _, first_raw = answered[tool_use_id]
                # Which remedy applies (sdd/traces/_schema.yml `decisions`) turns on this.
                how = f"identical copy of line {first}" if raw == first_raw else f"differs from line {first}"
                violations.append(
                    Violation(source, path, f"{name} line {lineno}: {tool_use_id} answered twice ({how})")
                )
            else:
                answered[tool_use_id] = (lineno, event, raw)
        else:
            notes.append(Violation(source, path, f"{name} line {lineno}: unknown event kind {kind!r}, skipped"))

    for tool_use_id, event in asked.items():
        response = answered.get(tool_use_id, (0, {}, ""))[1].get("tool_response")
        answers = response.get("answers") if isinstance(response, dict) else None
        answers = answers if isinstance(answers, dict) else {}
        questions = _questions(event)
        if not questions:
            notes.append(Violation(source, path, f"{name}: {tool_use_id} asked event has no readable questions"))
        for question, header in questions:
            answer = answers.get(question)
            if not isinstance(answer, str) or answer.startswith(_DISMISSED_PREFIX):
                notes.append(Violation(source, path, f"{name}: {tool_use_id} question {header!r} unanswered"))
    for tool_use_id, (lineno, _, _) in answered.items():
        if tool_use_id not in asked:
            notes.append(Violation(source, path, f"{name} line {lineno}: {tool_use_id} answered with no asked event"))
    return Report(violations, notes)


def collect(
    *,
    schema_path: Path = SCHEMA_PATH,
    traces_dir: Path = TRACES_DIR,
    root: Path = ROOT,
) -> Report:
    """Validate the schema, its examples, every trace, and every listed decision log.

    Order: the schema is checked for well-formedness first (a broken
    schema is reported and short-circuits, since it would make every
    trace result meaningless), then the schema's ``examples`` block, then
    each trace file and the logs its ``decisions:`` lists, resolved against
    *root*. A ``decisions:`` entry that is not a string is left to the schema.
    """
    notes: list[Violation] = []
    violations = _collect(schema_path=schema_path, traces_dir=traces_dir, root=root, notes=notes)
    notes.sort(key=lambda v: (v.source, v.path, v.message))
    return Report(violations, notes)


def collect_violations(
    *,
    schema_path: Path = SCHEMA_PATH,
    traces_dir: Path = TRACES_DIR,
    root: Path = ROOT,
) -> list[Violation]:
    """The failing half of ``collect``."""
    return collect(schema_path=schema_path, traces_dir=traces_dir, root=root).violations


def _collect(
    *,
    schema_path: Path,
    traces_dir: Path,
    root: Path,
    notes: list[Violation],
) -> list[Violation]:
    rel = schema_path.relative_to(ROOT) if schema_path.is_relative_to(ROOT) else schema_path
    try:
        schema = load_schema(schema_path)
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        # Reported, not raised, symmetric with the check_schema arm below: an
        # unreadable or duplicate-keyed schema is this gate's subject at its
        # largest, so it prints a violation rather than aborting with a
        # traceback. Same three exception types the trace loop catches, for the
        # same reasons.
        return [Violation(source=str(rel), path="(schema)", message=f"{type(exc).__name__}: {exc}")]

    validator_cls = validator_for(schema)

    try:
        validator_cls.check_schema(schema)
    except Exception as exc:  # noqa: BLE001 — surface any schema-validation failure
        return [Violation(source=str(rel), path="(schema)", message=f"schema is not valid: {exc}")]

    validator = validator_cls(schema)
    violations: list[Violation] = []

    # The schema's own examples are illustrative templates; keep them honest.
    for idx, example in enumerate(schema.get("examples", [])):
        violations.extend(_validate_document(validator, example, source=f"{rel} examples[{idx}]"))

    for trace_path in iter_trace_files(traces_dir):
        rel = trace_path.relative_to(ROOT) if trace_path.is_relative_to(ROOT) else trace_path
        try:
            document = load_trace(trace_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            # OSError and UnicodeDecodeError come from read_text, not the
            # parser, and neither is a yaml.YAMLError. The shared glob
            # admits directories (Path.glob does not filter to files) and
            # a bad rebase can leave a file undecodable. Uncaught, either
            # aborts this gate with a traceback in `lint` and `docs-gate`
            # instead of printing the violation it exists to print.
            # Every corpus consumer handles the same three for the same
            # reason: one driver, so the consumers must agree about what
            # it can hand them.
            violations.append(Violation(source=str(rel), path="(parse)", message=f"{type(exc).__name__}: {exc}"))
            continue
        document_violations = _validate_document(validator, document, source=str(rel))
        violations.extend(document_violations)
        # An entry the schema rejected is not read: its pattern is what confines
        # a listed path to the log directory, so reading it anyway would open,
        # and echo in notes, a file the trace was not allowed to name.
        rejected = {v.path for v in document_violations}
        logs = document.get("decisions") if isinstance(document, dict) else None
        # uniqueItems reports at `decisions`, not at the repeated entry, so a
        # repeat is skipped here rather than read twice.
        seen: set[str] = set()
        for idx, entry in enumerate(logs if isinstance(logs, list) else []):
            if isinstance(entry, str) and f"decisions[{idx}]" not in rejected and entry not in seen:
                seen.add(entry)
                report = _check_decision_log(root, entry, source=str(rel), path=f"decisions[{idx}]")
                violations.extend(report.violations)
                notes.extend(report.notes)

    violations.sort(key=lambda v: (v.source, v.path, v.message))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=TRACES_DIR,
        help="Directory of trace YAML files (default: sdd/traces).",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="Trace schema file (default: sdd/traces/_schema.yml).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Directory a trace's decisions: paths resolve against (default: the repo root).",
    )
    args = parser.parse_args(argv)

    report = collect(schema_path=args.schema, traces_dir=args.traces_dir, root=args.root)
    # Notes and violations echo log text (headers, ids, event kinds), which a
    # redirected Windows stdout would encode as cp1252 and fail on (BUG-305).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    for note in report.notes:
        print(f"note: {note.format()}")
    violations = report.violations
    if not violations:
        print(
            "check_traces: all traces parse and validate against sdd/traces/_schema.yml, "
            "and every decision log they list passes."
        )
        return 0

    for v in violations:
        print(v.format(), file=sys.stderr)
    print(
        f"\ncheck_traces: {len(violations)} violation(s). Each line above names the file to fix: "
        "a `(parse)` or `(schema)` path is a malformed or duplicate-keyed file, "
        "an `examples[N]` source is the schema's own example block, "
        "a `decisions[N]` path is about that entry: a schema failure or a missing log is the "
        "trace's entry to fix, only a `<log> line K:` message is a fault in that log "
        "(the remedy per fault is under `decisions:` in sdd/traces/_schema.yml), "
        "and an `OSError` reading it is the checkout's; "
        "anything else is a trace disagreeing with sdd/traces/_schema.yml.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
