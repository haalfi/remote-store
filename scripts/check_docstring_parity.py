"""Verify docstring parity between the sync API and its hand-mirrored async twin (BK-297).

The ``remote_store.aio`` tree mirrors the synchronous API by hand.  A subset of
each twin's method docstrings are meant to stay character-identical (e.g.
``Store.copy`` / ``AsyncStore.copy``); they drift silently when only one side is
edited, because nothing couples the two strings.  The rest diverge on purpose --
the async contract genuinely differs (async-iterator reads, eager-validation
notes, write-validation cross-references) and forcing those into lockstep would
be wrong.

This script classifies every shared-docstring method of each twin as either:

  identical  -- the sync and async docstrings must match byte-for-byte.
  divergent  -- the async docstring is authored independently for a real
                contract difference; allowlisted, content not compared.

and fails on:

  * an ``identical`` method whose sync/async docstrings differ (drift -- the
    bug this gate exists to catch),
  * a shared-docstring method in neither set (unclassified -- a new method
    slipped in without a parity decision; the author must classify it),
  * a registry entry that is no longer a shared-docstring method (stale -- the
    method was renamed/removed on one side, or its docstring dropped).

Verification only by default -- no curated prose is generated or rewritten.
``--fix`` repairs drift in one direction only: it copies the *sync* docstring
(the canonical source) onto the async twin for ``identical`` methods.

This is not a size optimisation.  Static griffe renders the aio API pages from
docstrings physically present in source (mkdocs ``paths: [src]``, no
inspection), so the text must remain on each method -- this gate keeps the
identical subset honest, it does not remove bytes.

Run with:
  hatch run check-docstring-parity
  python scripts/check_docstring_parity.py
  python scripts/check_docstring_parity.py --fix
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Twin:
    """A sync class and its hand-mirrored async counterpart.

    ``identical`` and ``divergent`` together must cover exactly the methods that
    carry a docstring on *both* classes.  ``identical`` docstrings are compared
    byte-for-byte; ``divergent`` ones are allowlisted (intentionally different)
    so a newly added shared method cannot skip the parity decision.
    """

    sync_path: Path
    sync_class: str
    async_path: Path
    async_class: str
    identical: frozenset[str]
    divergent: frozenset[str]

    @property
    def label(self) -> str:
        return f"{self.sync_class}/{self.async_class}"


# ---------------------------------------------------------------------------
# Registry
#
# Seeded from the current source; regenerate the membership (not the decision)
# with the same AST walk this script uses.  The ``divergent`` lists are the
# analytically interesting part: they record where the async contract is
# deliberately its own thing.  When a new method lands on both twins, the gate
# fails until it is placed in one set -- that placement is the parity decision.
# ---------------------------------------------------------------------------

TWINS: tuple[Twin, ...] = (
    Twin(
        sync_path=ROOT / "src" / "remote_store" / "_store.py",
        sync_class="Store",
        async_path=ROOT / "src" / "remote_store" / "aio" / "_async_store.py",
        async_class="AsyncStore",
        identical=frozenset(
            {
                "_full_path",
                "_gate",
                "_rebase_file_info",
                "_rebase_folder_entry",
                "_rebase_folder_info",
                "_rebase_write_result",
                "_require_file_path",
                "_strip_root",
                "copy",
                "delete",
                "delete_folder",
                "get_file_info",
                "get_folder_info",
                "move",
                "native_path",
                "ping",
                "resolve",
                "to_key",
                "unwrap",
            }
        ),
        # Async contract genuinely differs: reads yield an async iterator rather
        # than a stream; glob/iter/list note eager validation; write* cross-ref
        # Store.write validation instead of inlining it; read_text/read_bytes
        # gain ``await``; child/supports examples use ``async for``.
        divergent=frozenset(
            {
                "child",
                "exists",
                "glob",
                "head",
                "is_file",
                "is_folder",
                "iter_children",
                "list_files",
                "list_folders",
                "read",
                "read_bytes",
                "read_text",
                "supports",
                "write",
                "write_atomic",
                "write_text",
            }
        ),
    ),
    Twin(
        sync_path=ROOT / "src" / "remote_store" / "_backend.py",
        sync_class="Backend",
        async_path=ROOT / "src" / "remote_store" / "aio" / "_async_backend.py",
        async_class="AsyncBackend",
        identical=frozenset(
            {
                "capabilities",
                "check_health",
                "name",
                "resolve",
                "unwrap",
            }
        ),
        # The backend protocol's I/O methods describe async signatures and
        # lifecycle (await, async iterators, aclose) -- independently authored.
        divergent=frozenset(
            {
                "copy",
                "delete",
                "delete_folder",
                "exists",
                "get_file_info",
                "get_folder_info",
                "glob",
                "is_file",
                "is_folder",
                "iter_children",
                "list_files",
                "list_folders",
                "move",
                "native_path",
                "read",
                "read_bytes",
                "to_key",
                "write",
                "write_atomic",
            }
        ),
    ),
    Twin(
        sync_path=ROOT / "src" / "remote_store" / "backends" / "_azure.py",
        sync_class="AzureBackend",
        async_path=ROOT / "src" / "remote_store" / "aio" / "backends" / "_azure.py",
        async_class="AsyncAzureBackend",
        identical=frozenset(
            {
                "_errors",
                "check_health",
                "delete_folder",
            }
        ),
        # AsyncAzureBackend is async-native (the sync class bridges to it), so
        # most shared-name methods describe distinct client plumbing.
        divergent=frozenset(
            {
                "_blob_client",
                "_blob_service",
                "_cc",
                "_datalake_service",
                "_del_cleanup",
                "_fs",
                "_hns_first_file_ancestor",
                "_maybe_check_no_file_ancestor",
                "_raise_if_closed",
                "_raise_invalid_if_hns_file_ancestor",
                "copy",
                "delete",
                "exists",
                "get_file_info",
                "get_folder_info",
                "glob",
                "is_file",
                "is_folder",
                "iter_children",
                "list_files",
                "list_folders",
                "move",
                "read",
                "read_bytes",
                "resolve",
                "write",
                "write_atomic",
            }
        ),
    ),
)


# ---------------------------------------------------------------------------
# Extractor (pure over source text)
# ---------------------------------------------------------------------------


def class_method_docstrings(source: str, classname: str) -> dict[str, str]:
    """Return ``{method_name: docstring}`` for direct methods of *classname*.

    Scoped to the named class's own body -- the sync ``_backend.py`` /
    ``_azure.py`` modules also define helper classes (``_SeekableSpool``,
    ``_AzureRangeReader``, ...) whose methods must not leak into the twin
    comparison.  Methods without a docstring are omitted (only shared
    *docstrings* are in scope).  Raw value (``clean=False``) so indentation
    differences would themselves count as drift.
    """
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == classname:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(child, clean=False)
                    if doc is not None:
                        out[child.name] = doc
    return out


# ---------------------------------------------------------------------------
# Compare (pure)
# ---------------------------------------------------------------------------


def compare(
    twin: Twin,
    sync_docs: dict[str, str],
    async_docs: dict[str, str],
) -> list[str]:
    """Return parity errors for one twin.  Empty list means parity holds."""
    errors: list[str] = []
    shared = set(sync_docs) & set(async_docs)
    classified = twin.identical | twin.divergent

    for method in sorted(shared - classified):
        errors.append(
            f"{twin.label}: `{method}` carries a docstring on both classes but is "
            f"unclassified -- add it to `identical` (must match) or `divergent` "
            f"(intentionally different) in scripts/check_docstring_parity.py"
        )

    for method in sorted(classified - shared):
        errors.append(
            f"{twin.label}: registry lists `{method}` but it is no longer a "
            f"shared-docstring method (renamed, removed, or docstring dropped on "
            f"one side) -- remove it from the registry"
        )

    for method in sorted(twin.identical & shared):
        if sync_docs[method] != async_docs[method]:
            errors.append(
                f"{twin.label}: `{method}` docstring drift -- classified "
                f"`identical` but sync and async differ. Re-sync from {twin.sync_class} "
                f"(or reclassify as `divergent` if the async contract now differs). "
                f"`--fix` copies {twin.sync_class}.{method} onto {twin.async_class}.{method}."
            )

    return errors


# ---------------------------------------------------------------------------
# Fix (source-span replacement, sync -> async, identical methods only)
# ---------------------------------------------------------------------------


def _docstring_node(source: str, classname: str, method: str) -> ast.expr | None:
    """Return the literal node of *method*'s docstring in *classname*, or ``None``.

    The node carries ``lineno`` / ``col_offset`` / ``end_lineno`` / ``end_col_offset``
    for exact source-span splicing.  ``None`` when the class/method/docstring is
    absent.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == classname:
            for child in node.body:
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name == method
                    and ast.get_docstring(child, clean=False) is not None
                ):
                    expr = child.body[0]
                    assert isinstance(expr, ast.Expr)
                    return expr.value
    return None


def _abs_offset(source: str, lineno: int, col: int) -> int:
    """Absolute character offset in *source* for 1-based *lineno*, 0-based *col*.

    Sums full line lengths via ``splitlines(keepends=True)``, so line terminators
    (including ``\\r\\n``) are counted exactly -- the splice stays correct on CRLF
    files.  ``col`` is added as-is; for the docstring spans we touch, the prefix
    of the line up to the literal is ASCII indentation, so the ``ast`` column maps
    to a character index.
    """
    lines = source.splitlines(keepends=True)
    return sum(len(line) for line in lines[: lineno - 1]) + col


def fix_twin(twin: Twin) -> list[str]:
    """Copy sync docstrings onto the async twin for drifted ``identical`` methods.

    Returns the list of methods rewritten.  Splices by the exact AST span the
    parser reports -- ``source[:start] + sync_literal + source[end:]`` -- rather
    than text-matching the old literal, so a docstring whose text also appears
    elsewhere in the file cannot be rewritten at the wrong location.  Requires
    matching indentation (both twins are class methods at the same nesting), which
    keeps the spliced-in continuation lines aligned.
    """
    sync_src = twin.sync_path.read_text(encoding="utf-8")
    async_src = twin.async_path.read_text(encoding="utf-8")
    sync_docs = class_method_docstrings(sync_src, twin.sync_class)
    async_docs = class_method_docstrings(async_src, twin.async_class)
    shared = set(sync_docs) & set(async_docs)

    fixed: list[str] = []
    for method in sorted(twin.identical & shared):
        if sync_docs[method] == async_docs[method]:
            continue
        sync_node = _docstring_node(sync_src, twin.sync_class, method)
        # Re-parse the (possibly already-spliced) async source so spans stay valid.
        async_node = _docstring_node(async_src, twin.async_class, method)
        if sync_node is None or async_node is None:
            continue
        if sync_node.col_offset != async_node.col_offset:
            # Different indentation column: refuse rather than corrupt layout.
            continue
        sync_literal = ast.get_source_segment(sync_src, sync_node)
        if sync_literal is None:
            continue
        assert async_node.end_lineno is not None
        assert async_node.end_col_offset is not None
        start = _abs_offset(async_src, async_node.lineno, async_node.col_offset)
        end = _abs_offset(async_src, async_node.end_lineno, async_node.end_col_offset)
        async_src = async_src[:start] + sync_literal + async_src[end:]
        fixed.append(method)

    if fixed:
        twin.async_path.write_text(async_src, encoding="utf-8")
    return fixed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="copy sync docstrings onto the async twin for drifted `identical` methods",
    )
    args = parser.parse_args(argv)

    if args.fix:
        total: list[str] = []
        for twin in TWINS:
            fixed = fix_twin(twin)
            for method in fixed:
                print(f"fixed {twin.async_class}.{method} <- {twin.sync_class}.{method}")
            total.extend(fixed)
        print(f"\n{len(total)} docstring(s) re-synced." if total else "Nothing to fix.")
        # Fall through to a verification pass so the exit code reflects parity.

    errors: list[str] = []
    for twin in TWINS:
        sync_docs = class_method_docstrings(twin.sync_path.read_text(encoding="utf-8"), twin.sync_class)
        async_docs = class_method_docstrings(twin.async_path.read_text(encoding="utf-8"), twin.async_class)
        errors.extend(compare(twin, sync_docs, async_docs))

    if errors:
        print("Docstring parity verification failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nThe aio/ API mirrors the sync API by hand. `identical`-classified "
            "docstrings must match byte-for-byte; run with `--fix` to re-sync "
            "from the sync side, or reclassify in scripts/check_docstring_parity.py "
            "if the async contract has genuinely diverged.",
            file=sys.stderr,
        )
        return 1

    checked = sum(len(t.identical) for t in TWINS)
    print(f"Docstring parity verified ({len(TWINS)} twin(s), {checked} identical docstring(s) in lockstep).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
