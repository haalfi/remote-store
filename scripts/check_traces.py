"""PR-time gate: every trace under ``sdd/traces/`` validates against the schema.

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
note; it lives in ``scripts/_trace_corpus.py`` so this gate and
``report_trace_outcomes.py`` share one definition of "a trace"), parse
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

Exit codes
==========

* ``0`` — every trace (and every schema example) validates.
* ``1`` — one or more violations, printed to stderr as
  ``file: <json-path>: <message>``, sorted for stable diffs.

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
    rule: no trace under sdd/traces/, and not the schema itself, repeats a
        mapping key at any depth
    domain:     process
"""

from __future__ import annotations

import argparse
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
# shared with report_trace_outcomes.py so the gate and the report cannot
# disagree about what a trace is. DRIFT-RULES Rule 1.


@dataclass(frozen=True)
class Violation:
    """A single schema failure, located at ``source`` and ``path``."""

    source: str
    path: str
    message: str

    def format(self) -> str:
        return f"{self.source}: {self.path}: {self.message}"


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


def collect_violations(
    *,
    schema_path: Path = SCHEMA_PATH,
    traces_dir: Path = TRACES_DIR,
) -> list[Violation]:
    """Validate the schema, its examples, and every trace; return violations.

    Order: the schema is checked for well-formedness first (a broken
    schema is reported and short-circuits, since it would make every
    trace result meaningless), then the schema's ``examples`` block, then
    each trace file.
    """
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
            # report_trace_outcomes.py handles the same three for the same
            # reason: one driver, so the consumers must agree about what
            # it can hand them.
            violations.append(Violation(source=str(rel), path="(parse)", message=f"{type(exc).__name__}: {exc}"))
            continue
        violations.extend(_validate_document(validator, document, source=str(rel)))

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
    args = parser.parse_args(argv)

    violations = collect_violations(schema_path=args.schema, traces_dir=args.traces_dir)
    if not violations:
        print("check_traces: all traces validate against sdd/traces/_schema.yml.")
        return 0

    for v in violations:
        print(v.format(), file=sys.stderr)
    print(
        f"\ncheck_traces: {len(violations)} schema violation(s) across sdd/traces/. "
        "Fix the trace to match sdd/traces/_schema.yml.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
