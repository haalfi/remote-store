"""One driver for "which files under ``sdd/traces/`` are traces", and how they parse.

``sdd/traces/_schema.yml`` tells aggregators to glob
``"sdd/traces/[!_]*.yml"`` so that underscore-prefixed infrastructure
files — the schema itself — are not read as traces. Two tools need that
carve-out: ``check_traces.py`` (the PR-time schema validation gate) and
``report_trace_outcomes.py`` (the outcome report).

It lives here rather than in either tool because
[`sdd/DRIFT-RULES.md` Rule 1](../sdd/DRIFT-RULES.md#one-driver) prefers one
normative description driving N artifacts over N copies that agree until
they do not. A copied glob is exactly the shape that drifts: an earlier
draft of the research behind this module counted ``sdd/traces/*.yml``, one
character looser, and so counted ``_schema.yml`` as a trace.

**Authority: the schema governs, and this constant is a copy of it**
([Rule 4](../sdd/DRIFT-RULES.md#authority) — a direction stated rather
than left inferable). ``TRACE_GLOB`` and the schema's prose instruction
are two descriptions of one fact, and nothing detects them diverging: if
the schema changes the carve-out, this constant is what is wrong, and no
check will say so.

The report does not import the gate directly, even though the gate is
where the glob first landed. ``check_traces`` imports ``jsonschema`` at
module scope, and a report that only needs to parse YAML should not
acquire a schema-validation dependency to borrow a five-character
string.

``load_trace`` is here for the same Rule 1 reason as ``TRACE_GLOB``: the
gate and the report must not disagree about which files parse, and the
duplicate-key refusal below is a parse-time verdict rather than a schema
one. A consumer reaching for ``yaml.safe_load`` directly opts back out of
it silently, which is why there is one function rather than a documented
convention.

Underscore-prefixed: this module is scripts/ infrastructure, not a
runnable script, matching ``_dafny_classorder.py``.
"""

from __future__ import annotations

from collections.abc import Hashable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parent.parent
TRACES_DIR = ROOT / "sdd" / "traces"

# The "[!_]" carve-out skips infrastructure files like _schema.yml, per
# the schema's own note to aggregators. Do not loosen it: under a
# parsed-YAML reader the immediate cost is a corpus count that is one too
# high, and under any text-scanning reader the schema's own `examples`
# block starts contributing steps that were never traces.
TRACE_GLOB = "[!_]*.yml"


def iter_trace_files(traces_dir: Path = TRACES_DIR) -> Iterator[Path]:
    """Yield every trace file (sorted), skipping underscore-prefixed infra."""
    return iter(sorted(traces_dir.glob(TRACE_GLOB)))


class StrictTraceLoader(yaml.SafeLoader):
    """``SafeLoader`` that refuses a repeated mapping key instead of merging it.

    PyYAML implements YAML 1.1's last-wins resolution for duplicate keys and
    reports nothing, so a trace carrying one parses into a document missing
    whatever the earlier occurrence held. The schema then validates the
    *survivor*, which is well-formed, and the gate calls the file clean.

    **Measured, not anticipated.** Before this class existed,
    ``BK-221-test-pbt-write-result-s3-azure-per-backend.yml`` carried
    ``surprising_ripples`` at two top-level positions and passed
    ``check_traces.py``; the corpus scan that found it reported 1 of 325 files
    affected.

    The reachable authoring path is RFC-0015 D4's paste-the-block workflow — a
    second paste rather than a replacement leaves two ``review:`` keys, and the
    nine-field ``required:`` list cannot see it because the survivor has all
    nine. The check is not scoped to that key, because the defect is not: the
    BK-221 instance predates the block entirely.

    Every depth, not just the document root. A nested duplicate discards content
    the same way, and restricting the guard to top-level keys would buy nothing
    while making the rule harder to state.
    """

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        # Flatten first, for the same reason `SafeConstructor.construct_mapping`
        # does it first: a merge key (`<<: *anchor`) is not a duplicate, it is an
        # instruction to splice. Scanning `node.value` before flattening sees the
        # literal `<<` and refuses a document `yaml.safe_load` accepts — measured,
        # a two-key merge document parsed under `safe_load` and raised here, with
        # an error naming `tag:yaml.org,2002:merge` rather than anything a reader
        # could act on. Flattening is idempotent, so super()'s own call is a
        # no-op. After it, a key the merge spliced in that the mapping also
        # states literally is resolved by YAML's merge semantics, not a
        # duplicate, and is correctly not reported.
        self.flatten_mapping(node)
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            # Hashability first, exactly as `BaseConstructor.construct_mapping`
            # does it. Testing membership before this check performs the
            # unhashable lookup itself and raises `TypeError` on a complex key
            # (`? [a, b]`), which is not a YAMLError and so escapes the arm
            # both consumers report `(parse)` violations from — the very
            # traceback the ConstructorError choice below exists to avoid.
            # Deferring to super() here would not help: the duplicate scan runs
            # first by construction.
            if not isinstance(key, Hashable):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found unhashable key of type {type(key).__name__}",
                    key_node.start_mark,
                )
            if key in seen:
                # ConstructorError, not a bare ValueError: it subclasses
                # YAMLError, which is what both consumers already catch and
                # report as a `(parse)` violation. A non-YAMLError would
                # escape that handler and abort the gate with a traceback.
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r} — YAML keeps only the last, silently discarding the earlier one",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_trace(text: str) -> Any:
    """Parse one trace, refusing duplicate keys (see ``StrictTraceLoader``).

    The single entry point both the gate and the report call, so they cannot
    disagree about what parses — the same Rule 1 reason ``TRACE_GLOB`` lives
    here. A consumer calling ``yaml.safe_load`` directly gets the silent
    last-wins behaviour back.
    """
    return yaml.load(text, Loader=StrictTraceLoader)  # noqa: S506 — StrictTraceLoader derives from SafeLoader
