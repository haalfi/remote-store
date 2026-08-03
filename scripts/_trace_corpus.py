"""One driver for "which files under ``sdd/traces/`` are traces".

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

Underscore-prefixed: this module is scripts/ infrastructure, not a
runnable script, matching ``_dafny_classorder.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
