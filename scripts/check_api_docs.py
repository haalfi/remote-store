"""Verify API reference pages against graph IR (ID-170, ID-171).

Hand-maintained API pages drift silently when methods or capability gates
change.  This script walks ``graph.json`` and each API page in parallel and
reports mismatches.  Verification only -- no generation, no curated prose
gets touched.

Pattern (per page):

  graph extractor  -> {method_name: frozenset(required capability names)}
  page extractor   -> same shape, derived from ``:::`` directives and the
                      ``!!! note "Requires Capability.X"`` admonitions in
                      scope.
  compare          -> list of error messages (graph and page must agree).

Each extractor is a pure function over its single input -- testable in
isolation.

Phase 1: Store -> ``docs-src/reference/api/store.md``.
Phase 2: Backend -> ``docs-src/reference/api/backend.md``.
Phase 3: AsyncStore/AsyncBackend -> ``docs-src/reference/api/aio.md`` (ID-172).
Phase 4: ``__all__`` <-> ``docs-src/reference/api/index.md`` parity (ID-173).

Phase 4 is a *different IR* from the method-caps check above -- a
``{symbol_name: kind}`` set rather than ``{method: caps}`` -- so it has its own
extractor trio and compare, run as a second pass in ``main()``:

  exports extractor   -> {symbol_name: kind} over the public ``__all__`` of
                         ``remote_store``, ``remote_store.backends`` and
                         ``remote_store.aio`` (three co-equal sources; symbols
                         re-exported from ``remote_store.ext.*`` are excluded --
                         they are documented as module rows, not per symbol).
  index extractor     -> the set of symbol names linked as ``[Name](page.md)``
                         rows in ``index.md`` (dotted Extensions module rows
                         are not symbols and drop out).
  directive extractor -> the set of symbols rendered via ``::: pkg.Name`` on
                         any API page -- used only to police the companion
                         allowlist (every exempt symbol must be genuinely
                         rendered somewhere), not to derive the exemption.
  compare             -> bidirectional set diff: every public symbol needs an
                         index row (the small ``_INDEX_EXEMPT`` allowlist of
                         backend-companion helpers documented on another
                         class's page aside); every index link needs a backing
                         public symbol.

The exports extractor imports the live packages, so optional-dependency symbols
only appear when their extra is installed.  Like the strict coverage gate, this
check is therefore correct only in a full-extras environment (``hatch`` / CI),
not a bare-``python`` sandbox.

Run with:
  hatch run gen-api-check
  python scripts/check_api_docs.py
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"
API_DIR = ROOT / "docs-src" / "reference" / "api"
INDEX_PAGE = API_DIR / "index.md"

# Class qualified-name -> page that documents it.
PAGES: dict[str, Path] = {
    "remote_store._store.Store": ROOT / "docs-src" / "reference" / "api" / "store.md",
    "remote_store._backend.Backend": ROOT / "docs-src" / "reference" / "api" / "backend.md",
    "remote_store.aio._async_store.AsyncStore": ROOT / "docs-src" / "reference" / "api" / "aio.md",
    "remote_store.aio._async_backend.AsyncBackend": ROOT / "docs-src" / "reference" / "api" / "aio.md",
}

# Admonition-title prefixes that introduce a capability requirement claim.
# ``!!! info`` admonitions (e.g. quality-flag notes) are explicitly out of
# scope -- they describe optional behaviour, not gates.
_REQUIRES_PREFIXES: tuple[str, ...] = (
    "Requires",
    "Partially requires",
    "Capability depends",
)

_CAP_RE = re.compile(r"`Capability\.(\w+)`")
_DIRECTIVE_RE = re.compile(r"^:::\s+([\w.]+)\s*$")
_ADMONITION_RE = re.compile(r'^!!!\s+(\w+)\s+"([^"]+)"\s*$')
# Capability groups delimit the sections that scope admonitions.  Single-class
# pages (store.md, backend.md) use ``## H2`` group headings; the multi-class
# aio.md nests groups as ``### H3`` under each class's ``## H2``.  Splitting on
# H2 *or* H3 scopes admonitions to their group on both shapes -- the page H1
# (``#``) stays in the leading section either way.
_SECTION_RE = re.compile(r"^#{2,3}\s+(.+)$")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_graph() -> dict:
    with open(GRAPH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Graph extractor
# ---------------------------------------------------------------------------


def graph_class_methods(graph: dict, class_qname: str) -> dict[str, frozenset[str]]:
    """Return ``{method_name: frozenset(required capability names)}`` for *class_qname*.

    Walks ``method <-gates- requirement -of-> capability`` edge chains.  Methods
    with multiple gates (e.g. ``Store.get_folder_info`` -> METADATA + LIST)
    accumulate the union.  Methods without any gate are absent from the result.
    """
    method_prefix = f"mtd:{class_qname}."
    gate_to_cap: dict[str, str] = {}
    for edge in graph["edges"]:
        if edge["kind"] == "of":
            gate_to_cap[edge["src"]] = edge["dst"].removeprefix("cap:")

    result: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        if edge["kind"] != "gates":
            continue
        method_id = edge["dst"]
        if not method_id.startswith(method_prefix):
            continue
        method_name = method_id.removeprefix(method_prefix)
        cap = gate_to_cap.get(edge["src"])
        if cap is not None:
            result.setdefault(method_name, set()).add(cap)

    return {k: frozenset(v) for k, v in result.items()}


# ---------------------------------------------------------------------------
# Page extractor
# ---------------------------------------------------------------------------


def _split_sections(lines: list[str]) -> list[list[str]]:
    """Partition *lines* on ``## H2`` / ``### H3`` boundaries.

    H1 (``#``) stays in the leading section.  See ``_SECTION_RE`` for why both
    heading levels delimit a section.
    """
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _SECTION_RE.match(line):
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    sections.append(current)
    return sections


def _collect_admonition_body(lines: list[str], start: int) -> tuple[list[str], int]:
    """Return (body_lines, next_index) for the admonition opened at *start*.

    Body is the contiguous block of indented (or blank) lines following the
    admonition title.  MkDocs admonition bodies use 4-space indentation.
    """
    body: list[str] = []
    j = start + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "" or line.startswith("    ") or line.startswith("\t"):
            body.append(line)
            j += 1
            continue
        break
    return body, j


def _parse_section(
    sec_lines: list[str],
    method_prefixes: tuple[str, ...],
) -> tuple[list[tuple[int, str]], list[tuple[int, str, list[str]]]]:
    """Return (directives, requires_admonitions) inside one section.

    directives: ``[(line_idx, method_name)]`` for each ``::: <prefix>.method``
    line in the section, in order.

    requires_admonitions: ``[(line_idx, title, body_lines)]`` for each
    ``!!! note "<requires-prefix> ..."`` admonition.  ``info`` admonitions
    and notes that are not requirement claims are filtered out here.
    """
    directives: list[tuple[int, str]] = []
    admonitions: list[tuple[int, str, list[str]]] = []

    i = 0
    while i < len(sec_lines):
        line = sec_lines[i]

        d = _DIRECTIVE_RE.match(line)
        if d:
            full = d.group(1)
            for prefix in method_prefixes:
                if full.startswith(prefix):
                    directives.append((i, full.removeprefix(prefix)))
                    break
            i += 1
            continue

        a = _ADMONITION_RE.match(line)
        if a:
            kind, title = a.group(1), a.group(2)
            body, next_i = _collect_admonition_body(sec_lines, i)
            if kind == "note" and title.startswith(_REQUIRES_PREFIXES):
                admonitions.append((i, title, body))
            i = next_i
            continue

        i += 1

    return directives, admonitions


def page_class_methods(text: str, class_qname: str) -> dict[str, frozenset[str]]:
    """Return ``{method_name: frozenset(claimed capability names)}`` for *class_qname*.

    Walks ``text`` partitioned by ``## H2`` headings.  Within each section:

    * Admonitions before the first ``:::`` directive are *section-level* --
      they apply to every method directive in that section.
    * Admonitions after a ``:::`` directive (and before the next one) are
      *method-level* -- they apply to that method only.

    A method's claimed cap set is the union of ``Capability.X`` mentions in
    titles AND bodies of all in-scope ``Requires``/``Partially requires``/
    ``Capability depends`` admonitions.  ``!!! info`` admonitions are
    intentionally excluded -- they describe quality flags, not gates.
    """
    # The page may use either the internal qname or the public re-export.  The
    # public path drops the private (leading-underscore) module segment(s):
    # ``remote_store._store.Store`` -> ``remote_store.Store``;
    # ``remote_store.aio._async_store.AsyncStore`` -> ``remote_store.aio.AsyncStore``.
    public_qname = ".".join(p for p in class_qname.split(".") if not p.startswith("_"))
    method_prefixes = (
        f"{class_qname}.",
        f"{public_qname}.",
    )

    method_caps: dict[str, set[str]] = {}

    for sec_lines in _split_sections(text.splitlines()):
        directives, admonitions = _parse_section(sec_lines, method_prefixes)
        if not directives:
            continue

        first_dir_idx = directives[0][0]
        section_level = [(t, b) for idx, t, b in admonitions if idx < first_dir_idx]

        method_level: dict[str, list[tuple[str, list[str]]]] = {}
        for k, (didx, mname) in enumerate(directives):
            next_idx = directives[k + 1][0] if k + 1 < len(directives) else len(sec_lines)
            method_level[mname] = [(t, b) for idx, t, b in admonitions if didx < idx < next_idx]

        for _didx, mname in directives:
            caps: set[str] = set()
            for title, body in section_level + method_level.get(mname, []):
                caps.update(_CAP_RE.findall(title))
                for line in body:
                    caps.update(_CAP_RE.findall(line))
            method_caps.setdefault(mname, set()).update(caps)

    return {k: frozenset(v) for k, v in method_caps.items()}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def compare(
    graph_ir: dict[str, frozenset[str]],
    page_ir: dict[str, frozenset[str]],
    class_label: str,
    page_path: Path,
) -> list[str]:
    """Coverage check: every cap the graph requires must be claimed by the page.

    Over-claims (page mentions caps the graph does not gate) are intentionally
    *not* errors here -- section-level admonition prose often references caps
    that only some methods in the section need, and forcing strict equality
    would be hostile to that style.
    """
    errors: list[str] = []
    rel = page_path.relative_to(ROOT) if page_path.is_absolute() else page_path

    for method, expected in sorted(graph_ir.items()):
        if method not in page_ir:
            errors.append(
                f"{rel}: missing `::: ...{class_label}.{method}` directive (graph gates it on {sorted(expected)})"
            )
            continue
        claimed = page_ir[method]
        missing = expected - claimed
        if missing:
            covered = sorted(claimed) if claimed else "no caps"
            errors.append(
                f"{rel}: `{class_label}.{method}` admonitions cover {covered}; "
                f"missing required {sorted(missing)} per graph"
            )

    return errors


# ---------------------------------------------------------------------------
# __all__ <-> index.md parity (ID-173)
#
# A second, independent IR from the method-caps check above: {symbol_name: kind}
# rather than {method: caps}.  Three pure extractors feed one bidirectional
# compare, wired as a second pass in main().
# ---------------------------------------------------------------------------

# Public namespaces whose ``__all__`` defines the documented surface.  Treated
# symmetrically: ``remote_store`` (primary), ``remote_store.backends`` (backend
# classes + per-backend helpers), ``remote_store.aio`` (async surface).
_PUBLIC_NAMESPACES: tuple[str, ...] = (
    "remote_store",
    "remote_store.backends",
    "remote_store.aio",
)

# Backend-companion symbols intentionally documented on another class's page
# (via a ``:::`` directive) rather than given a standalone ``index.md`` row.
# They are exempt from the MISSING check; everything else public needs a row.
#
# Why an explicit allowlist and not a derived ``:::``-render exemption: a
# render cannot distinguish a row-less companion from a primary class that
# *lost* its row, because most classes (and all classes on the shared pages
# ``aio.md`` / ``errors.md`` / ``models.md`` / ...) are ``:::``-rendered on a
# page co-owned by siblings.  Deriving the exemption from renders would mask a
# dropped row for any such class.  This list is small, stable, and self-policed
# by ``TestLiveIndex`` (each entry must be public, ``:::``-rendered, and
# genuinely absent from the index — otherwise the entry is stale and fails).
_INDEX_EXEMPT: frozenset[str] = frozenset(
    {
        "ArrowSerializer",  # on backends/sql-query.md, with SQLQueryBackend
        "ResultSerializer",  # on backends/sql-query.md, with SQLQueryBackend
        "AsyncAzureBackend",  # on aio.md, with the other async classes
    }
)

_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def exports_symbols(modules: list) -> dict[str, str]:
    """Return ``{symbol_name: kind}`` over each module's ``__all__``.

    ``kind`` is ``"class"`` / ``"function"`` / ``"other"`` -- it enriches error
    messages only; parity is a name set-diff.  Excluded:

    * ``__``-dunders (``__version__``) -- not documented symbols.
    * Symbols whose ``__module__`` is under ``remote_store.ext`` -- those are
      documented as *module* rows in the index Extensions section, not per
      symbol.  Note this keys on *definition* origin (``__module__``), not
      *export* origin: a symbol defined elsewhere but re-exported only through
      ``remote_store.ext.*`` would not be excluded.  That divergence is
      acceptable -- such a symbol would still be public and warrant an index
      row, and the two notions coincide for every current re-export.
    """
    result: dict[str, str] = {}
    for mod in modules:
        for name in getattr(mod, "__all__", []):
            if name.startswith("__"):
                continue
            obj = getattr(mod, name)
            origin = getattr(obj, "__module__", "") or ""
            if origin.startswith("remote_store.ext"):
                continue
            if inspect.isclass(obj):
                kind = "class"
            elif inspect.isroutine(obj):
                kind = "function"
            else:
                kind = "other"
            result[name] = kind
    return result


def index_link_symbols(text: str) -> set[str]:
    """Return the set of symbol names linked as ``[Name](target)`` in *text*.

    Only link texts that are bare Python identifiers count -- this drops the
    Extensions section's module rows (``[ext.arrow](...)``, ``[aio.ext.write]``)
    whose dotted text is not an identifier.

    The match is whole-file by intent: every link in ``index.md`` is a table
    row today, so there is no need to scope to tables.  If a future *prose*
    link reused an identifier that is not a public symbol, it would surface as
    a spurious EXTRA -- the signal to either rename it or scope this regex.
    """
    return {m.group(1) for m in _LINK_RE.finditer(text) if m.group(1).isidentifier()}


def directive_symbols(texts) -> set[str]:
    """Return the set of leaf symbol names rendered via ``::: pkg.path.Name``.

    Used to police the ``_INDEX_EXEMPT`` allowlist: every exempt symbol must be
    genuinely rendered somewhere in the API reference, so the exemption can
    never hide a truly undocumented symbol.  It is deliberately *not* used to
    derive the MISSING exemption itself -- see ``_INDEX_EXEMPT`` for why a
    render-derived exemption would mask dropped index rows.
    """
    out: set[str] = set()
    for text in texts:
        for line in text.splitlines():
            m = _DIRECTIVE_RE.match(line)
            if m:
                out.add(m.group(1).rsplit(".", 1)[-1])
    return out


def compare_exports(
    expected: dict[str, str],
    index: set[str],
    exempt: frozenset[str],
) -> list[str]:
    """Bidirectional parity between the public ``__all__`` surface and index.md.

    * MISSING -- a public symbol with no index link row.  Backend-companion
      symbols on the ``exempt`` allowlist are tolerated (documented on another
      class's page); every other public symbol must have its own row, so a
      primary class dropped from the index *fails* here.
    * EXTRA -- an index link with no backing public symbol.  The exempt
      allowlist does *not* rescue an extra: the symbol must be in a public
      ``__all__``.

    Both are errors -- the index must mirror the public surface in both
    directions.
    """
    errors: list[str] = []
    rel = INDEX_PAGE.relative_to(ROOT) if INDEX_PAGE.is_absolute() else INDEX_PAGE

    for name in sorted(set(expected) - index - exempt):
        errors.append(f"{rel}: public {expected[name]} `{name}` has no index link row")
    for name in sorted(index - set(expected)):
        errors.append(
            f"{rel}: `{name}` is linked but absent from any public `__all__` ({', '.join(_PUBLIC_NAMESPACES)})"
        )

    return errors


def allowlist_staleness_errors(
    exempt: frozenset[str],
    expected: dict[str, str],
    index: set[str],
    rendered: set[str],
) -> list[str]:
    """Police the ``_INDEX_EXEMPT`` allowlist so it cannot rot or hide drift.

    Each exempt entry must be (1) a real public symbol, (2) genuinely absent
    from the index (else the entry is redundant -- it now has a row), and
    (3) actually ``:::``-rendered somewhere (else it is undocumented, not a
    documented-elsewhere companion).  Run as part of ``main()`` so the tooling
    gate is self-contained, not test-only.
    """
    errors: list[str] = []
    src = Path("scripts/check_api_docs.py")
    for name in sorted(exempt):
        if name not in expected:
            errors.append(f"{src}: `{name}` is on _INDEX_EXEMPT but not in any public `__all__` -- remove it")
        elif name in index:
            errors.append(
                f"{src}: `{name}` is on _INDEX_EXEMPT but now has an index row -- remove it from the allowlist"
            )
        elif name not in rendered:
            errors.append(
                f"{src}: `{name}` is on _INDEX_EXEMPT but is not rendered via `:::` "
                f"on any API page -- it is undocumented"
            )
    return errors


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    graph = _load_graph()
    errors: list[str] = []

    for class_qname, page_path in PAGES.items():
        graph_ir = graph_class_methods(graph, class_qname)
        page_text = page_path.read_text(encoding="utf-8")
        page_ir = page_class_methods(page_text, class_qname)
        class_label = class_qname.rsplit(".", 1)[1]
        errors.extend(compare(graph_ir, page_ir, class_label, page_path))

    # ID-173: __all__ <-> index.md parity (separate IR from the method-caps loop).
    # Imported at runtime so the extractors above stay pure (testable with fakes).
    modules = [importlib.import_module(ns) for ns in _PUBLIC_NAMESPACES]
    expected = exports_symbols(modules)
    index = index_link_symbols(INDEX_PAGE.read_text(encoding="utf-8"))
    rendered = directive_symbols(p.read_text(encoding="utf-8") for p in API_DIR.rglob("*.md"))
    errors.extend(compare_exports(expected, index, _INDEX_EXEMPT))
    errors.extend(allowlist_staleness_errors(_INDEX_EXEMPT, expected, index, rendered))

    if errors:
        print("API doc verification failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nMethod-caps drift: fix the page, or update the relevant gating "
            "dict if the gate itself is wrong, then re-run `hatch run gen-graph`:\n"
            "  Store:        _GATING in src/remote_store/_store.py\n"
            "  AsyncStore:   _GATING in src/remote_store/aio/_async_store.py\n"
            "  Backend:      _BACKEND_GATING in scripts/gen_graph.py\n"
            "  AsyncBackend: _ASYNC_BACKEND_GATING in scripts/gen_graph.py\n"
            "\nindex.md parity drift (ID-173): add a missing link row to "
            "docs-src/reference/api/index.md, or remove a stale one. A genuine "
            "backend-companion documented on another class's page can be added "
            "to _INDEX_EXEMPT in scripts/check_api_docs.py instead. Run under "
            "`hatch` so optional-dependency symbols are present.",
            file=sys.stderr,
        )
        return 1

    print(f"API doc verification passed ({len(PAGES)} page(s) + index.md parity checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
