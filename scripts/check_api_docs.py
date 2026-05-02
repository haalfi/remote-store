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
         AsyncStore/AsyncBackend and ``api/index.md`` are follow-on items.

Run with:
  hatch run gen-api-check
  python scripts/check_api_docs.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"

# Class qualified-name -> page that documents it.
PAGES: dict[str, Path] = {
    "remote_store._store.Store": ROOT / "docs-src" / "reference" / "api" / "store.md",
    "remote_store._backend.Backend": ROOT / "docs-src" / "reference" / "api" / "backend.md",
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
_H2_RE = re.compile(r"^##\s+(.+)$")


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


def _split_h2_sections(lines: list[str]) -> list[list[str]]:
    """Partition *lines* on ``## H2`` boundaries.  H1 stays in the leading section."""
    sections: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _H2_RE.match(line):
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
    short_class = class_qname.rsplit(".", 1)[1]
    # The page may use either the internal qname or the public re-export
    # (``remote_store.Store.method``).  Match both.
    method_prefixes = (
        f"{class_qname}.",
        f"remote_store.{short_class}.",
    )

    method_caps: dict[str, set[str]] = {}

    for sec_lines in _split_h2_sections(text.splitlines()):
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

    if errors:
        print("API doc verification failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nFix the page, or update the relevant _GATING dict "
            "(Store: src/remote_store/_store.py, Backend: scripts/gen_graph.py) "
            "if the gate itself is wrong, then re-run `hatch run gen-graph`.",
            file=sys.stderr,
        )
        return 1

    print(f"API doc verification passed ({len(PAGES)} page(s) checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
