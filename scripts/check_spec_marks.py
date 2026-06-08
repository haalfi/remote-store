#!/usr/bin/env python3
"""Spec-mark drift gate (BK-251).

Audit-015 found that nothing enforced the `000-process.md` Rule 2 promise
("no spec without tests") at the *mark* layer: a shipped spec ID could
lose (or never grow) its ``@pytest.mark.spec("ID")`` and no check would
notice, and a marker could cite an ID no spec declares (the audit found a
stale ``HTTP-001`` left in ``test_examples.py``). This script makes the
spec ↔ mark wiring mechanically checkable across two sources:

  S — spec IDs declared as a section in ``sdd/specs/`` — either a
      ``##``/``###`` heading (``### BE-014: ...``) or a row of a
      requirement table (a table whose first column header is ``ID`` —
      the form spec 022 uses for SAW-001..015). Heading level and
      declaration form are not consistent across spec files. Per-ID
      *locations* are kept so a doubly-declared ID is detectable.
  T — spec IDs cited by a ``@pytest.mark.spec`` marker anywhere under
      ``tests/`` (not just conformance — backend-specific and ext tests
      carry marks too). A ``*.mark.spec(...)`` call counts only in a
      position pytest actually treats as a marker: a decorator on a test
      function/class, a ``pytest.param(marks=...)`` entry, or a
      ``pytestmark`` assignment. A bare ``pytest.mark.spec(...)``
      expression that decorates nothing is dead code and is ignored.

Five failure modes:

  drift  — a *shipped* spec ID (declared in S, not allowlisted) that no
           marker cites (not in T). The marks rotted, or a new spec
           shipped without one.
  stale  — a marker citing a spec ID absent from S (the ``HTTP-001``
           case). The spec was renamed/renumbered and the mark was left.
  dup    — a spec ID declared more than once in the spec tree (the
           ``STORE-015`` collision: two distinct invariants, one ID).
           A duplicate cannot be unambiguously marked or traced.
  allowlist-stale — an enumerated allowlist entry (below) that no longer
           earns its place: its spec section was renamed/removed, or it
           grew a real mark and is now testable. Gives the allowlist the
           same shrink-only self-pruning the baseline has.
  heading-no-colon — an ID-shaped heading ``_HEADING_RE`` cannot parse
           because it lacks the trailing colon. Such a line declares
           nothing and cites nothing, so without this check the ID would
           silently fall out of S with no signal — the one structural
           blind spot in the parse.

Scope — what this check does and does not prove
-----------------------------------------------
  * **Citation, not assertion.** T records that a marker naming an ID
    sits on a test; it does not verify the test asserts that behavior,
    or that the test is even enabled (a marker on a skipped test still
    counts), or that the cited ID is the *right* one for that test.
  * **ID granularity, not clause granularity.** One marker citing an ID
    clears drift for every sub-clause sharing that ID. The check proves
    each shipped ID is cited at least once — not that each invariant
    sub-clause has its own test.

Allowlist — IDs that legitimately carry no mark
-----------------------------------------------
Two classes of declared spec ID are excused from the drift rule:

  * **type-(d) — design / meta / deferred.** Invariants that describe a
    design principle, a process/meta section, or an explicitly *deferred*
    feature (TLS Phase 2, ext.parquet Dagster-v2, the async
    ``read_seekable`` / ``open_atomic`` deferrals, graph retry, the Graph
    item-id addressing deferral ``GR-011``). These are not runtime-testable
    behaviors; a mark would have nothing to sit on. Seeded from audit-015's
    verified addendum's (d) rows.
  * **implementation-pending backends absent from ``FEATURES.md``.**
    Currently empty: this was the coarse ``GR-*`` prefix while the Graph
    backend (spec 044 / 005, owned by ID-127) was unbuilt. GR-DONE landed the
    backend, its tests, and the integration tier, so the prefix was removed as
    a unit and the shipped GR-NNN IDs now carry real marks. A future unbuilt
    backend would re-seed this class.

An allowlisted ID is excused from *drift* only. It is still checked for
duplicate declaration, and a marker citing it is still valid (it is
declared). When an enumerated allowlist ID becomes testable (grows a
mark) or its spec section disappears, the *allowlist-stale* mode above
fails the gate until the entry is removed — so the allowlist cannot rot
silently, the same shrink-only contract the baseline has.

Landing strategy — checked-in baseline
--------------------------------------
Wiring this in surfaces every pre-existing unmarked-but-shipped ID at
once. Audit-015 counted ~127 type-(b) label backfills plus 5 type-(a)
coverage gaps still owed — a hard gate would break the build on day one.
``_BASELINE`` is a checked-in allow-list of the violations known when the
gate landed. Two things are mechanically enforced:

  * a violation NOT in the baseline fails the check — a regression, and
  * a baseline entry that no longer matches a live violation fails the
    check — a stale entry, i.e. the gap was closed.

The second rule makes the baseline self-prune: backfilling a mark (the
BK-252 work) forces that ID's baseline entry out in the same change.
Baseline *growth* is NOT blocked mechanically — a new violation can be
parked by editing ``_BASELINE``. That edit is visible in review and is
the point where a human must refuse new debt; the check cannot make that
judgement.

BK-252 has since **drained ``_BASELINE`` to empty**: every shipped spec
ID is now either marked (behavior backfilled or newly tested) or
allowlisted (type-(d) design/meta/perf, or a moved-to-EW stub). The gate
is therefore a hard zero-tolerance check now — any new shipped ID without
a mark or allowlist entry fails immediately.

CI enforcement. Exit code 0 = ok; 1 = violations found.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A spec-section ID: an uppercase family (optionally hyphenated, e.g.
# ``SQL-BLOB``) followed by a hyphen-number and an optional split-item
# suffix letter (``WR-001a``).
_SPEC_ID = r"[A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+[a-z]?"
_SPEC_ID_RE = re.compile(_SPEC_ID)

# Declaration of a spec section: a Markdown heading at any level, or a
# row of a requirement table — a table whose first column header is
# ``ID``. In a heading the ID may carry a parenthetical before the colon
# (``## EW-001 (was WR-014): ...``); the optional group keeps those in S.
_HEADING_RE = re.compile(rf"^#+[ \t]+({_SPEC_ID})(?: \([^)]*\))?:")
_TABLE_ROW_RE = re.compile(rf"^\|[ \t]*({_SPEC_ID})[ \t]*\|")
_ID_TABLE_HEADER_RE = re.compile(r"^\|[ \t]*ID[ \t]*\|", re.IGNORECASE)

# A heading that *starts* with a spec-shaped ID, regardless of whether the
# trailing colon ``_HEADING_RE`` requires is present. Used only to catch
# the gate's one structural blind spot: a heading-form declaration written
# without the colon (``### BE-099 Some Behavior``) parses as neither a
# declaration (S has no entry) nor a citation, so the ID would silently
# stop being tracked. A line matching this but NOT ``_HEADING_RE`` is such
# an unparseable declaration. The parenthetical form is parsed by
# ``_HEADING_RE``, so it is not falsely flagged.
_HEADING_ID_RE = re.compile(rf"^#+[ \t]+({_SPEC_ID})\b")

# Backlog / process item prefixes — the authoritative trace-id prefix set
# from the ``id`` pattern in ``sdd/traces/_schema.yml`` (``BK-167a`` etc.).
# It is duplicated here (a lint script must not parse YAML at import time),
# but the copy is NOT hand-maintained blind: ``test_backlog_prefixes_match_
# trace_schema`` in ``tests/scripts/test_check_spec_marks.py`` extracts the
# schema's pattern and fails if this tuple drifts from it, so a new prefix
# added to the schema forces this tuple to follow (and vice versa).
_BACKLOG_ID_PREFIXES: tuple[str, ...] = ("BK", "BUG", "ID", "AF", "BL", "UC")

# Marker namespaces this gate does NOT govern. ``@pytest.mark.spec(...)``
# is used repo-wide as a general traceability marker citing IDs from
# several namespaces, not only ``sdd/specs/`` sections:
#   * backlog / process items (``_BACKLOG_ID_PREFIXES`` above) — a
#     sanctioned provenance convention (a test tagged with the item that
#     introduced it).
#   * docs-framework gate codes (``G-01``..``G-07``) — defined in spec
#     047 and ``scripts/check_docs_framework.py``, cited alongside the
#     ``DOCFRAME-NNN`` section a docs-framework test traces to.
# A mark citing one of these is not a stale spec reference, so it is
# excluded from the stale check. No spec family uses these prefixes, so
# the exclusion cannot mask a real spec-section typo.
_NON_SPEC_MARK_RE = re.compile(rf"^(?:{'|'.join(_BACKLOG_ID_PREFIXES)})-\d+[a-z]?$|^G-\d+$")

# Violation kinds. Stable strings — they key the baseline below.
KIND_DRIFT = "shipped-spec-id-unmarked"
KIND_STALE = "mark-cites-unknown-spec"
KIND_DUPLICATE = "spec-id-declared-twice"
KIND_ALLOWLIST_STALE = "allowlist-entry-stale"
KIND_HEADING_NO_COLON = "spec-heading-missing-colon"

# ---------------------------------------------------------------------------
# Allowlist — declared IDs that legitimately carry no @pytest.mark.spec.
# ---------------------------------------------------------------------------

# type-(d): design principles, meta/process sections, and explicitly
# deferred features. Seeded from audit-015's verified addendum (the (d)
# rows of the findings table, plus the deferred features the addendum
# names: TLS Phase 2, ext.parquet Dagster-v2, async read_seekable /
# open_atomic deferrals, graph retry). These describe a constraint or a
# not-yet-built feature, not a runtime behavior a mark could sit on.
_ALLOWLIST_DESIGN: frozenset[str] = frozenset(
    {
        # Design principles / architectural constraints.
        "SIO-006",  # 006 — no framework dependencies
        "S3PA-006",  # 011 — dual-library architecture decision
        "ASYNC-056",  # 029 — no new dependencies
        # Meta / process / spec-update sections.
        "ITER-008",  # 027 — spec-updates meta section
        "RTXT-006",  # 028 — spec-updates meta section
        # Doc-framework principles (spec 047).
        "DOCFRAME-005",  # bridge replaces not augments
        "DOCFRAME-006",  # strict build, strict links
        "DOCFRAME-007",  # nav and URL alignment
        # Testing-process spec (spec 048) — not runtime behaviors.
        "TEST-002",  # conformance is cross-backend spine
        "TEST-003",  # backend-specific tests isolated per backend
        # TEST-007 (HTTP cassette + per-backend dir) now carries a mark via the
        # Graph scrub security-gate test (tests/backends/fixtures/test_cassettes.py).
        "TEST-008",  # replay scope is HTTP-transport only
        "TEST-009",  # cassette refresh is explicit
        # Deferred features (specced, not yet built — no behavior to mark).
        "TLS-008",  # 039 — tls_ca_bundle on AzureBackend (TLS Phase 2)
        "TLS-009",  # 039 — env var fallback chain for Azure (TLS Phase 2)
        "TLS-010",  # 039 — Azure connection_verify injection (TLS Phase 2)
        "PDS-009",  # 042 — Dagster integration (ext.parquet Dagster-v2)
        "ASYNC-061",  # 029 — read_seekable() deferral
        "ASYNC-062",  # 029 — open_atomic() deferral
        "RET-015",  # 025 — graph retry mapping (rides the Graph backend)
        "GR-011",  # 044 — item-id addressing deferred to a future RFC (reserved slot, no behavior)
        # Optional-dependency / packaging declarations (pyproject extras).
        "PA-023",  # 014 — pyarrow optional extra declaration
        "CFG-014",  # 021 — toml/yaml/pydantic optional extras declaration
        # --- BK-252 disposition: audit-015 held rows reclassified type-(d) ---
        # Design principles / architectural constraints (no runtime behavior to mark).
        "GLOB-015",  # 018 — ext.glob: no backend coupling (public Store API only)
        "CAP-007",  # 003 — quality-flag capabilities (declaring gates no method)
        "ASYNC-043",  # 029 — AsyncStore delegation (adds no I/O logic of its own)
        "ASYNC-077",  # 029 — AsyncAzure shared helpers (_azure_common code organization)
        "HTTP-TR-001",  # 032 — HttpTransport protocol interface definition
        "AZ-007",  # 012 — Azure single-container scope (no cross-container API exists)
        "NPR-018",  # 010 — to_key not gated by a Capability (no NATIVE_PATH_RESOLUTION)
        "NPR-009",  # 010 — future backends implement to_key (forward-looking)
        "NPR-017",  # 010 — RemotePath invariants preserved (PATH-001..014 remain in force)
        "NPR-019",  # 010 — backward compatibility (listing fix is a bug-fix, not a behavior change)
        "MEM-026",  # 013 — atomicity scope (no multi-op transaction; matches all backends)
        "RES-001",  # 043 — resolution opacity (problem-statement section, not an invariant)
        "CFG-007",  # 002 — config-as-code priority, no env-var merge (ADR-0002 design policy)
        # Meta / process / spec-update sections.
        "RTXT-002",  # 028 — read_text: no Backend ABC change (Store-level convenience only)
        "RTXT-003",  # 028 — read_text added to the STORE-008 API surface
        "WTXT-002",  # 030 — write_text: no Backend ABC change
        "WTXT-003",  # 030 — write_text added to the STORE-008 API surface
        "ITER-003",  # 027 — iter_children added to the STORE-008 API surface
        "MEM-030",  # 013 — must pass conformance with zero skips (testing-process)
        "MEM-031",  # 013 — recommendation: replace LocalBackend fixture with MemoryBackend
        "MEM-032",  # 013 — recommendation: keep dedicated LocalBackend tests
        # Performance-characteristic tables / data-structure rationale (prose, no behavior).
        "MEM-040",  # 013 — complexity summary table
        "MEM-041",  # 013 — memory overhead per entry table
        "MEM-042",  # 013 — scaling envelope
        "MEM-DS-001",  # 013 — why not a flat dict (rationale)
        "MEM-DS-003",  # 013 — why bytearray over bytes (rationale)
        "MEM-DS-004",  # 013 — slots=True (rationale)
        "SQL-BLOB-070",  # 040 — blob size guidelines (Performance section)
        "SQL-BLOB-071",  # 040 — connection pooling (SQLAlchemy default, no custom config)
        "SQL-QUERY-090",  # 041 — query execution (full materialization; streaming deferred)
        "SQL-QUERY-091",  # 041 — serialization overhead (full copy; zero-copy/ADBC deferred)
        # Moved to ext.write (spec 046 EW-001..004) per ADR-0008. The spec-045
        # WR-014..017 headings are cross-reference stubs kept for traceability; the
        # real behavior is marked under EW-* (tests/ext/test_write.py), so a WR-*
        # mark would be a duplicate of the EW-* coverage, not new debt.
        "WR-014",  # 045 — moved to EW-001 (write_with_hash returns digest)
        "WR-015",  # 045 — moved to EW-002 (write_with_hash works on every WRITE backend)
        "WR-016",  # 045 — moved to EW-003 (open_atomic_with_hash requires ATOMIC_WRITE)
        "WR-017",  # 045 — moved to EW-004 (open_atomic_with_hash exposes result after exit)
    }
)

# Implementation-pending backends absent from FEATURES.md. Was the coarse
# ``GR-*`` prefix while the Graph backend (spec 044 GR-001..GR-057, owned by
# ID-127) was unbuilt. GR-DONE (the final ID-127 step) landed the backend, its
# tests, and the integration tier, so the prefix was removed as a unit and every
# GR-NNN is now either marked or individually allowlisted (GR-011 — item-id
# addressing — is the lone deferred-feature exception, enumerated above with the
# other type-(d) deferrals). (ERR-013/ResourceLocked left the pending list
# earlier when its runtime class + tests landed in GR-CONTRACT, ahead of the
# backend that raises it — ADR-0024 bundled-implementation order.)
_ALLOWLIST_PENDING_PREFIXES: tuple[str, ...] = ()
_ALLOWLIST_PENDING_IDS: frozenset[str] = frozenset()

# The enumerated (non-prefix) allowlist — every explicitly named excused
# ID. These get the same shrink-only self-pruning the baseline enforces:
# an entry that no longer earns its place (the spec section was renamed /
# removed, or the ID grew a real mark and is now testable) is flagged so
# it cannot rot silently.
_ENUMERATED_ALLOWLIST: frozenset[str] = _ALLOWLIST_DESIGN | _ALLOWLIST_PENDING_IDS


def is_allowlisted(spec_id: str) -> bool:
    """True if ``spec_id`` is excused from the drift rule.

    Covers type-(d) design/meta/deferred IDs (and, when non-empty, any
    implementation-pending backend prefix — see ``_ALLOWLIST_PENDING_PREFIXES``,
    currently empty). An allowlisted ID is still checked for duplicate
    declaration.
    """
    if spec_id in _ALLOWLIST_DESIGN or spec_id in _ALLOWLIST_PENDING_IDS:
        return True
    return any(spec_id.startswith(prefix) for prefix in _ALLOWLIST_PENDING_PREFIXES)


# ---------------------------------------------------------------------------
# Source S — spec sections declared in sdd/specs/
# ---------------------------------------------------------------------------


def extract_declared_specs(specs_dir: Path) -> dict[str, list[str]]:
    """Map each spec ID declared in ``sdd/specs/`` to its declaration sites.

    A section is declared by either a Markdown heading at any level
    (``### BE-014: ...``) or a row of a *requirement table* — a table
    whose first column header is ``ID``. A table-shaped line outside such
    a table (a summary or cross-reference table) does not declare a spec.

    The value is the list of ``path:lineno`` sites; an ID with more than
    one site is a duplicate declaration (the STORE-015 collision shape).
    """
    declared: dict[str, list[str]] = {}
    for path in sorted(specs_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        in_requirement_table = False
        for lineno, line in enumerate(text.splitlines(), 1):
            heading = _HEADING_RE.match(line)
            if heading is not None:
                declared.setdefault(heading.group(1), []).append(f"{path}:{lineno}")
                in_requirement_table = False
                continue
            if not line.startswith("|"):
                in_requirement_table = False
                continue
            if _ID_TABLE_HEADER_RE.match(line):
                in_requirement_table = True
                continue
            if in_requirement_table:
                row = _TABLE_ROW_RE.match(line)
                if row is not None:
                    declared.setdefault(row.group(1), []).append(f"{path}:{lineno}")
    return declared


def extract_undeclared_id_headings(specs_dir: Path) -> dict[str, list[str]]:
    """Map each ID-shaped heading that ``_HEADING_RE`` cannot parse to its sites.

    A heading that starts with a spec-shaped ID but lacks the trailing
    colon (``### BE-099 Some Behavior``) is almost certainly a declaration
    the author meant to make, yet it lands in neither S (no colon → not
    matched) nor any citation, so the ID silently stops being tracked.
    This surfaces that one structural blind spot. The parenthetical form
    (``## EW-001 (was WR-014): ...``) is parsed by ``_HEADING_RE`` and is
    therefore not flagged.
    """
    undeclared: dict[str, list[str]] = {}
    for path in sorted(specs_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            id_heading = _HEADING_ID_RE.match(line)
            if id_heading is not None and _HEADING_RE.match(line) is None:
                undeclared.setdefault(id_heading.group(1), []).append(f"{path}:{lineno}")
    return undeclared


# ---------------------------------------------------------------------------
# Source T — @pytest.mark.spec markers across tests/
# ---------------------------------------------------------------------------


def _is_spec_call(node: ast.AST) -> bool:
    """True if ``node`` is a ``*.mark.spec(...)`` call (e.g. ``pytest.mark.spec``)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "spec"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "mark"
    )


def _is_pytestmark_name(node: ast.AST) -> bool:
    """True if ``node`` is the ``pytestmark`` name (a module/class marker list)."""
    return isinstance(node, ast.Name) and node.id == "pytestmark"


def _marker_anchors(node: ast.AST) -> list[ast.expr]:
    """Return the expressions where ``node`` may legitimately apply markers.

    The positions pytest treats as marker applications: a decorator on a
    function/class, a ``marks=`` value, and a ``pytestmark`` assignment
    (plain or annotated). Anything else is not a marker site.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return list(node.decorator_list)
    if isinstance(node, ast.Call):
        return [kw.value for kw in node.keywords if kw.arg == "marks"]
    if isinstance(node, ast.Assign) and any(_is_pytestmark_name(t) for t in node.targets):
        return [node.value]
    if isinstance(node, ast.AnnAssign) and node.value is not None and _is_pytestmark_name(node.target):
        return [node.value]
    return []


def _iter_spec_marker_args(tree: ast.Module) -> list[tuple[int, str]]:
    """Return ``(lineno, id)`` for every *applied* ``spec`` marker.

    A ``*.mark.spec("ID")`` call counts only when it sits in a position
    pytest actually treats as a marker (see ``_marker_anchors``). A bare
    ``pytest.mark.spec(...)`` expression that decorates nothing is dead
    code and is ignored.
    """
    anchored: set[int] = set()
    for node in ast.walk(tree):
        for anchor in _marker_anchors(node):
            for sub in ast.walk(anchor):
                if _is_spec_call(sub):
                    anchored.add(id(sub))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_spec_call(node) and id(node) in anchored:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    # A few example marks join several IDs in one string
                    # (``spec("DAG-002,DAG-003,DAG-005")``); count each.
                    for spec_id in _SPEC_ID_RE.findall(arg.value):
                        found.append((node.lineno, spec_id))
    return found


def extract_test_specs(tests_dir: Path) -> dict[str, list[str]]:
    """Map each spec ID cited by a ``@pytest.mark.spec`` marker to its sites."""
    cited: dict[str, list[str]] = {}
    for path in sorted(tests_dir.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:  # pragma: no cover - defensive
            sys.stderr.write(f"Skipping {path}: SyntaxError\n")
            continue
        for lineno, spec_id in _iter_spec_marker_args(tree):
            cited.setdefault(spec_id, []).append(f"{path}:{lineno}")
    return cited


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


def compute_violations(
    declared: dict[str, list[str]],
    marks: dict[str, list[str]],
    undeclared_headings: dict[str, list[str]] | None = None,
    allowlist: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """Return the sorted list of ``(kind, spec_id)`` violations.

    drift           — a declared, non-allowlisted spec ID with no marker.
    stale           — a marker citing an ID with no spec section.
    dup             — a spec ID declared more than once.
    allowlist-stale — an ``allowlist`` ID that no longer earns its place:
                      its spec section is gone (dead weight) or it grew a
                      real mark (now testable, no longer excused). Gives
                      the allowlist the same self-pruning the baseline has.
                      ``allowlist`` is the *enumerated* excused set only;
                      ``main`` passes ``_ENUMERATED_ALLOWLIST`` (the
                      ``GR-*`` prefix is deliberately excluded — it is
                      removed as a unit, not per ID). It defaults empty so
                      the core-mode unit tests stay isolated from it.
    heading-no-colon — an ID-shaped heading ``_HEADING_RE`` cannot parse
                      (no colon); an unparseable declaration the gate would
                      otherwise track silently as nothing.
    """
    undeclared_headings = undeclared_headings or {}
    violations: set[tuple[str, str]] = set()
    for spec_id, sites in declared.items():
        if len(sites) > 1:
            violations.add((KIND_DUPLICATE, spec_id))
        if spec_id not in marks and not is_allowlisted(spec_id):
            violations.add((KIND_DRIFT, spec_id))
    for spec_id in marks:
        if spec_id not in declared and not _NON_SPEC_MARK_RE.match(spec_id):
            violations.add((KIND_STALE, spec_id))
    for spec_id in allowlist:
        if spec_id not in declared or spec_id in marks:
            violations.add((KIND_ALLOWLIST_STALE, spec_id))
    for spec_id in undeclared_headings:
        violations.add((KIND_HEADING_NO_COLON, spec_id))
    return sorted(violations)


# ---------------------------------------------------------------------------
# Baseline — known violations at gate-landing time (BK-251).
#
# This list MUST shrink and MUST NOT grow. Each entry is a (kind, spec_id)
# pair. Backfilling a mark (BK-252) makes its drift entry stale, which
# fails the gate until the entry is removed in the same PR — the same
# shrink-only contract that forced out the STORE-015 duplicate entry when
# BK-250 renumbered the second invariant to STORE-018 (now an ordinary
# drift row, its GLOB-* coverage still owed a spec-file mark by BK-252).
# Adding a new gap fails the gate until fixed — the baseline is not a
# place to park new debt.
# ---------------------------------------------------------------------------
# BK-252 drained this to empty: every shipped spec ID is now either marked
# (its behavior backfilled or newly tested) or allowlisted above (type-(d)
# design/meta/perf, or a moved-to-EW stub). A new violation therefore has no
# baseline to hide behind — it fails the gate immediately, which is the
# end state this whole effort was driving toward. Park genuinely
# pre-existing debt here only with a reviewed justification.
_BASELINE: frozenset[tuple[str, str]] = frozenset()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_KIND_LABEL = {
    KIND_DRIFT: "shipped spec ID with no @pytest.mark.spec marker (drift)",
    KIND_STALE: "@pytest.mark.spec marker cites an unknown spec ID (stale)",
    KIND_DUPLICATE: "spec ID declared more than once (duplicate)",
    KIND_ALLOWLIST_STALE: "allowlist entry no longer earns its place (dead or now-marked)",
    KIND_HEADING_NO_COLON: "ID-shaped heading without a colon — unparseable declaration",
}


def _print_violations(
    violations: list[tuple[str, str]],
    declared: dict[str, list[str]],
    marks: dict[str, list[str]],
    undeclared_headings: dict[str, list[str]],
) -> None:
    """Print each violation grouped by kind, with source locations."""
    for kind in (
        KIND_DRIFT,
        KIND_STALE,
        KIND_DUPLICATE,
        KIND_ALLOWLIST_STALE,
        KIND_HEADING_NO_COLON,
    ):
        rows = [v for v in violations if v[0] == kind]
        if not rows:
            continue
        print(f"{_KIND_LABEL[kind]}:")
        for _, spec_id in rows:
            if kind == KIND_STALE:
                locations = marks.get(spec_id, [])
            elif kind == KIND_HEADING_NO_COLON:
                locations = undeclared_headings.get(spec_id, [])
            elif kind == KIND_ALLOWLIST_STALE:
                # An allowlist-stale ID is either gone from S (no location)
                # or now marked; show whichever explains it.
                locations = marks.get(spec_id) or declared.get(spec_id, ["(no spec section)"])
            else:
                locations = declared.get(spec_id, [])
            shown = ", ".join(locations[:3]) + (" ..." if len(locations) > 3 else "")
            print(f"  {spec_id}: {shown}")
        print()


def main(
    specs_dir: Path | None = None,
    tests_dir: Path | None = None,
    baseline: frozenset[tuple[str, str]] | None = None,
    allowlist: frozenset[str] | None = None,
) -> int:
    specs_dir = specs_dir or ROOT / "sdd" / "specs"
    tests_dir = tests_dir or ROOT / "tests"
    if baseline is None:
        baseline = _BASELINE
    if allowlist is None:
        allowlist = _ENUMERATED_ALLOWLIST

    declared = extract_declared_specs(specs_dir)
    marks = extract_test_specs(tests_dir)
    undeclared_headings = extract_undeclared_id_headings(specs_dir)
    violations = compute_violations(declared, marks, undeclared_headings, allowlist)

    print("spec <-> mark traceability gate (BK-251)")
    print(f"  declared spec sections : {len(declared)}")
    print(f"  mark-cited spec IDs    : {len(marks)}")
    print(f"  violations             : {len(violations)}")
    print()
    _print_violations(violations, declared, marks, undeclared_headings)

    violation_set = set(violations)
    new = sorted(violation_set - baseline)
    stale = sorted(baseline - violation_set)

    if new:
        print(f"FAIL: {len(new)} new spec-mark violation(s) not in the baseline:")
        for kind, spec_id in new:
            print(f"  [{kind}] {spec_id}")
        print("\nAdd the missing @pytest.mark.spec, fix the stale mark, or renumber")
        print("the duplicate. Only park genuinely pre-existing debt in _BASELINE")
        print("(scripts/check_spec_marks.py) with a reason — that is the BK-252 worklist.")
    if stale:
        print(f"FAIL: {len(stale)} stale baseline entry/ies (the gap was closed):")
        for kind, spec_id in stale:
            print(f"  [{kind}] {spec_id}")
        print("\nRemove these from _BASELINE in scripts/check_spec_marks.py —")
        print("the baseline must shrink as gaps close, never carry dead weight.")
    if new or stale:
        return 1

    if violations:
        print(f"OK: {len(violations)} known spec-mark gap(s), all baselined (see _BASELINE).")
    else:
        print("OK: spec <-> mark traceability is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
