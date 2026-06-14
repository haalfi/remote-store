"""Tests for scripts/check_api_docs.py (ID-170).

Each extractor is tested in isolation:

* ``graph_class_methods`` against tiny synthetic graphs and the real
  ``graph.json``.
* ``page_class_methods`` against handcrafted markdown fixtures covering the
  section-level / method-level admonition placement rules.
* ``compare`` against synthetic IRs covering missing-directive,
  missing-cap, exact-match, and over-claim cases.

A final integration test runs the real script against the live page and
graph -- the same check CI runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_api_docs

    return check_api_docs


# ---------------------------------------------------------------------------
# Graph extractor
# ---------------------------------------------------------------------------


class TestGraphClassMethods:
    def test_empty_graph_yields_empty_dict(self, mod):
        graph: dict = {"nodes": [], "edges": []}
        assert mod.graph_class_methods(graph, "pkg.mod.Foo") == {}

    def test_single_gate_single_cap(self, mod):
        graph = {
            "nodes": [],
            "edges": [
                {"kind": "gates", "src": "req:pkg.mod.Foo.bar.gate", "dst": "mtd:pkg.mod.Foo.bar"},
                {"kind": "of", "src": "req:pkg.mod.Foo.bar.gate", "dst": "cap:READ"},
            ],
        }
        assert mod.graph_class_methods(graph, "pkg.mod.Foo") == {"bar": frozenset({"READ"})}

    def test_multi_gate_method_unions_caps(self, mod):
        graph = {
            "nodes": [],
            "edges": [
                {"kind": "gates", "src": "req:pkg.mod.Foo.x.gate_a", "dst": "mtd:pkg.mod.Foo.x"},
                {"kind": "gates", "src": "req:pkg.mod.Foo.x.gate_b", "dst": "mtd:pkg.mod.Foo.x"},
                {"kind": "of", "src": "req:pkg.mod.Foo.x.gate_a", "dst": "cap:METADATA"},
                {"kind": "of", "src": "req:pkg.mod.Foo.x.gate_b", "dst": "cap:LIST"},
            ],
        }
        assert mod.graph_class_methods(graph, "pkg.mod.Foo") == {"x": frozenset({"METADATA", "LIST"})}

    def test_orphan_gate_method_silently_skipped(self, mod):
        # A `gates` edge with no paired `of` edge -> the method is silently
        # skipped.  gen-graph-check upstream guarantees the schema, so this
        # branch shouldn't fire in practice; the test documents the intended
        # behaviour and pins it against future refactors.
        graph = {
            "nodes": [],
            "edges": [
                {"kind": "gates", "src": "req:pkg.mod.Foo.x.g", "dst": "mtd:pkg.mod.Foo.x"},
                # no matching `of` edge for the gate
            ],
        }
        assert mod.graph_class_methods(graph, "pkg.mod.Foo") == {}

    def test_other_class_methods_excluded(self, mod):
        graph = {
            "nodes": [],
            "edges": [
                {"kind": "gates", "src": "req:pkg.mod.Foo.x.g", "dst": "mtd:pkg.mod.Foo.x"},
                {"kind": "gates", "src": "req:pkg.mod.Bar.y.g", "dst": "mtd:pkg.mod.Bar.y"},
                {"kind": "of", "src": "req:pkg.mod.Foo.x.g", "dst": "cap:READ"},
                {"kind": "of", "src": "req:pkg.mod.Bar.y.g", "dst": "cap:WRITE"},
            ],
        }
        result = mod.graph_class_methods(graph, "pkg.mod.Foo")
        assert result == {"x": frozenset({"READ"})}
        assert "y" not in result

    def test_real_graph_store_methods(self, mod):
        # Sanity check against the live graph: a few well-known Store methods.
        graph = mod._load_graph()
        ir = mod.graph_class_methods(graph, "remote_store._store.Store")
        assert ir["read"] == frozenset({"READ"})
        assert ir["write"] == frozenset({"WRITE"})
        assert ir["copy"] == frozenset({"COPY"})
        assert ir["get_folder_info"] == frozenset({"METADATA", "LIST"})
        # Ungated methods (exists, ping, close, ...) must NOT appear.
        for ungated in ("exists", "is_file", "is_folder", "ping", "close", "child", "resolve"):
            assert ungated not in ir

    def test_real_graph_backend_methods(self, mod):
        # Sanity check against the live graph: a few well-known Backend methods.
        graph = mod._load_graph()
        ir = mod.graph_class_methods(graph, "remote_store._backend.Backend")
        assert ir["read"] == frozenset({"READ"})
        assert ir["write"] == frozenset({"WRITE"})
        assert ir["write_atomic"] == frozenset({"ATOMIC_WRITE"})
        assert ir["glob"] == frozenset({"GLOB"})
        assert ir["get_file_info"] == frozenset({"METADATA"})
        assert ir["get_folder_info"] == frozenset({"METADATA"})
        # Ungated methods must NOT appear.
        for ungated in (
            "name",
            "capabilities",
            "exists",
            "is_file",
            "is_folder",
            "resolve",
            "check_health",
            "close",
            "unwrap",
            "native_path",
            "to_key",
        ):
            assert ungated not in ir

    def test_real_graph_async_store_methods(self, mod):
        # Sanity check against the live graph: a few well-known AsyncStore methods (ID-172).
        graph = mod._load_graph()
        ir = mod.graph_class_methods(graph, "remote_store.aio._async_store.AsyncStore")
        assert ir["read"] == frozenset({"READ"})
        assert ir["write"] == frozenset({"WRITE"})
        assert ir["write_atomic"] == frozenset({"ATOMIC_WRITE"})
        assert ir["copy"] == frozenset({"COPY"})
        assert ir["get_folder_info"] == frozenset({"METADATA", "LIST"})
        # Ungated methods (exists, ping, aclose, ...) must NOT appear.
        for ungated in ("exists", "is_file", "is_folder", "ping", "aclose", "child", "resolve"):
            assert ungated not in ir

    def test_real_graph_async_backend_methods(self, mod):
        # Sanity check against the live graph: a few well-known AsyncBackend methods (ID-172).
        graph = mod._load_graph()
        ir = mod.graph_class_methods(graph, "remote_store.aio._async_backend.AsyncBackend")
        assert ir["read"] == frozenset({"READ"})
        assert ir["write"] == frozenset({"WRITE"})
        assert ir["write_atomic"] == frozenset({"ATOMIC_WRITE"})
        assert ir["glob"] == frozenset({"GLOB"})
        assert ir["get_file_info"] == frozenset({"METADATA"})
        # AsyncBackend mirrors sync Backend: get_folder_info is METADATA-only (no dual gate).
        assert ir["get_folder_info"] == frozenset({"METADATA"})
        # Ungated methods must NOT appear.
        for ungated in (
            "name",
            "capabilities",
            "exists",
            "is_file",
            "is_folder",
            "resolve",
            "check_health",
            "aclose",
            "unwrap",
            "native_path",
            "to_key",
        ):
            assert ungated not in ir


# ---------------------------------------------------------------------------
# Page extractor
# ---------------------------------------------------------------------------


def _page(text: str) -> str:
    """Strip leading newline so multi-line strings line up at column 0."""
    return text.lstrip("\n")


class TestPageClassMethods:
    def test_section_level_admonition_applies_to_all_methods(self, mod):
        text = _page("""
# Store

## Reading

!!! note "Requires `Capability.READ`"
    All read methods raise CapabilityNotSupported.

::: remote_store.Store.read
    options:
      show_root_heading: true

::: remote_store.Store.read_bytes
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir == {
            "read": frozenset({"READ"}),
            "read_bytes": frozenset({"READ"}),
        }

    def test_method_level_admonition_does_not_bleed_backward(self, mod):
        # Admonition trailing the LAST directive applies to that directive
        # (write_atomic), and must NOT reach back to an earlier directive (write).
        text = _page("""
## Writing

::: remote_store.Store.write
    options:
      show_root_heading: true

::: remote_store.Store.write_atomic
    options:
      show_root_heading: true

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Method-level note for write_atomic.
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["write"] == frozenset()
        assert ir["write_atomic"] == frozenset({"ATOMIC_WRITE"})

    def test_method_level_admonition_does_not_bleed_forward(self, mod):
        # Admonition BETWEEN two directives applies to the preceding directive
        # (write), and must NOT bleed forward into the next directive (write_atomic).
        text = _page("""
## Writing

::: remote_store.Store.write
    options:
      show_root_heading: true

!!! note "Requires `Capability.WRITE`"
    Method-level note for write.

::: remote_store.Store.write_atomic
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["write"] == frozenset({"WRITE"})
        assert ir["write_atomic"] == frozenset()

    def test_section_and_method_level_unioned(self, mod):
        text = _page("""
## Writing

!!! note "Requires `Capability.WRITE`"
    Section-level.

::: remote_store.Store.write_atomic
    options:
      show_root_heading: true

!!! note "Requires `Capability.ATOMIC_WRITE`"
    Method-level.
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["write_atomic"] == frozenset({"WRITE", "ATOMIC_WRITE"})

    def test_info_admonitions_ignored(self, mod):
        text = _page("""
## Reading

::: remote_store.Store.read_seekable
    options:
      show_root_heading: true

!!! info "Quality flag: `Capability.SEEKABLE_READ`"
    Quality flag, not a gate.
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        # SEEKABLE_READ from `info` admonition must not be picked up.
        assert ir["read_seekable"] == frozenset()

    def test_non_requires_note_admonitions_ignored(self, mod):
        text = _page("""
## Writing

::: remote_store.Store.write
    options:
      show_root_heading: true

!!! note "Backend-conditional argument: `metadata=`"
    Not a requirement -- mentions `Capability.USER_METADATA` in body.
    `Capability.USER_METADATA`
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        # USER_METADATA is in the body of a non-Requires note -> filtered out.
        assert ir["write"] == frozenset()

    def test_capability_depends_admonition_picked_up(self, mod):
        text = _page("""
## Metadata

::: remote_store.Store.get_folder_info
    options:
      show_root_heading: true

!!! note "Capability depends on `max_depth`"
    Without `max_depth`: requires `Capability.METADATA`.
    With `max_depth` set: requires `Capability.LIST`.
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["get_folder_info"] == frozenset({"METADATA", "LIST"})

    def test_directive_with_other_class_ignored(self, mod):
        text = _page("""
## Section

!!! note "Requires `Capability.READ`"
    Should not bleed across classes.

::: remote_store.Backend.read
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir == {}

    def test_admonition_after_last_directive_in_section(self, mod):
        text = _page("""
## Section

::: remote_store.Store.foo
    options:
      show_root_heading: true

!!! note "Requires `Capability.X`"
    Last admonition in section.
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["foo"] == frozenset({"X"})

    def test_h2_boundary_isolates_sections(self, mod):
        # Section-level admonition in section A must not apply to methods in section B.
        text = _page("""
## A

!!! note "Requires `Capability.A_CAP`"
    Section A only.

::: remote_store.Store.a_method
    options:
      show_root_heading: true

## B

::: remote_store.Store.b_method
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store._store.Store")
        assert ir["a_method"] == frozenset({"A_CAP"})
        assert ir["b_method"] == frozenset()

    def test_aio_submodule_public_prefix_matched(self, mod):
        # aio/store.md uses the submodule public re-export ``remote_store.aio.AsyncStore.``,
        # which is neither the internal qname nor the top-level re-export. The
        # public prefix is derived by dropping ``_``-prefixed module segments (ID-172).
        text = _page("""
## AsyncStore

### Reading

!!! note "Requires `Capability.READ`"
    All read methods raise CapabilityNotSupported.

::: remote_store.aio.AsyncStore.read
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store.aio._async_store.AsyncStore")
        assert ir == {"read": frozenset({"READ"})}

    def test_h3_subsections_scope_admonitions(self, mod):
        # On a multi-class page, capability groups are H3 nested under each
        # class's H2. A section-level note in one H3 group must NOT bleed into a
        # sibling H3 group (ID-172). Without H3 splitting, READ would leak onto write.
        text = _page("""
## AsyncStore

### Reading

!!! note "Requires `Capability.READ`"
    Read group only.

::: remote_store.aio.AsyncStore.read
    options:
      show_root_heading: true

### Writing

!!! note "Requires `Capability.WRITE`"
    Write group only.

::: remote_store.aio.AsyncStore.write
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store.aio._async_store.AsyncStore")
        assert ir["read"] == frozenset({"READ"})
        assert ir["write"] == frozenset({"WRITE"})

    def test_other_class_h2_section_ignored(self, mod):
        # When checking AsyncStore, directives under a sibling class's H2
        # (AsyncBackend) must not be attributed to AsyncStore (ID-172).
        text = _page("""
## AsyncStore

### Reading

::: remote_store.aio.AsyncStore.read
    options:
      show_root_heading: true

## AsyncBackend

### Reading

!!! note "Requires `Capability.READ`"
    AsyncBackend read.

::: remote_store.aio.AsyncBackend.read
    options:
      show_root_heading: true
""")
        ir = mod.page_class_methods(text, "remote_store.aio._async_store.AsyncStore")
        assert ir == {"read": frozenset()}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


class TestCompare:
    def test_exact_match_yields_no_errors(self, mod):
        graph = {"foo": frozenset({"READ"})}
        page = {"foo": frozenset({"READ"})}
        assert mod.compare(graph, page, "Store", Path("p.md")) == []

    def test_missing_directive_in_page(self, mod):
        graph = {"foo": frozenset({"READ"})}
        page: dict = {}
        errors = mod.compare(graph, page, "Store", Path("p.md"))
        assert len(errors) == 1
        assert "missing" in errors[0]
        assert "Store.foo" in errors[0]

    def test_missing_required_cap(self, mod):
        graph = {"foo": frozenset({"READ", "WRITE"})}
        page = {"foo": frozenset({"READ"})}
        errors = mod.compare(graph, page, "Store", Path("p.md"))
        assert len(errors) == 1
        assert "WRITE" in errors[0]
        assert "READ" not in errors[0].split("missing required")[1]

    def test_overclaim_is_not_an_error(self, mod):
        # Page mentions extra caps the graph does not gate -- intentional, no error.
        graph = {"foo": frozenset({"READ"})}
        page = {"foo": frozenset({"READ", "EXTRA"})}
        assert mod.compare(graph, page, "Store", Path("p.md")) == []

    def test_multiple_methods_each_reported(self, mod):
        graph = {"a": frozenset({"X"}), "b": frozenset({"Y"})}
        page: dict = {}
        errors = mod.compare(graph, page, "Store", Path("p.md"))
        assert len(errors) == 2
        assert any("Store.a" in e for e in errors)
        assert any("Store.b" in e for e in errors)


# ---------------------------------------------------------------------------
# Live integration
# ---------------------------------------------------------------------------


class TestLivePages:
    def test_check_passes_on_real_pages(self, mod):
        """Top-level: every page in PAGES must agree with graph.json."""
        graph = mod._load_graph()
        all_errors: list[str] = []
        for class_qname, page_path in mod.PAGES.items():
            graph_ir = mod.graph_class_methods(graph, class_qname)
            page_text = page_path.read_text(encoding="utf-8")
            page_ir = mod.page_class_methods(page_text, class_qname)
            class_label = class_qname.rsplit(".", 1)[1]
            all_errors.extend(mod.compare(graph_ir, page_ir, class_label, page_path))
        assert all_errors == [], "API doc drift: " + "; ".join(all_errors)


# ===========================================================================
# __all__ <-> index.md parity (ID-173) -- a separate IR from the method-caps
# check above: {symbol_name: kind} rather than {method: caps}.
# ===========================================================================


class _FakeModule:
    """Minimal stand-in for a real module: an ``__all__`` plus attributes.

    ``exports_symbols`` reads ``__all__`` and ``getattr`` only, so a fake with
    the right attributes exercises it without importing the real package.
    """

    def __init__(self, all_names: list[str], **attrs: object) -> None:
        self.__all__ = all_names
        for name, obj in attrs.items():
            setattr(self, name, obj)


def _obj(module: str, *, is_class: bool = True):
    if is_class:
        obj = type("Sym", (), {})
        obj.__module__ = module
        return obj

    def fn() -> None:  # a routine
        ...

    fn.__module__ = module
    return fn


# ---------------------------------------------------------------------------
# Exports extractor (__all__ -> {symbol_name: kind})
# ---------------------------------------------------------------------------


class TestExportsSymbols:
    def test_classifies_class_and_function(self, mod):
        m = _FakeModule(
            ["Foo", "do_it"],
            Foo=_obj("pkg.core", is_class=True),
            do_it=_obj("pkg.core", is_class=False),
        )
        assert mod.exports_symbols([m]) == {"Foo": "class", "do_it": "function"}

    def test_dunders_excluded(self, mod):
        m = _FakeModule(["Foo", "__version__"], Foo=_obj("pkg.core"), __version__="1.0")
        assert mod.exports_symbols([m]) == {"Foo": "class"}

    def test_ext_module_symbols_excluded(self, mod):
        # Symbols re-exported from remote_store.ext.* are documented as *module*
        # rows in the index Extensions section, not per symbol -- excluded.
        m = _FakeModule(
            ["Core", "cache"],
            Core=_obj("remote_store._store"),
            cache=_obj("remote_store.ext.cache", is_class=False),
        )
        assert mod.exports_symbols([m]) == {"Core": "class"}

    def test_multiple_modules_merged(self, mod):
        a = _FakeModule(["A"], A=_obj("pkg.a"))
        b = _FakeModule(["B"], B=_obj("pkg.backends"))
        assert mod.exports_symbols([a, b]) == {"A": "class", "B": "class"}

    def test_non_class_non_routine_is_other(self, mod):
        # e.g. a type alias (AsyncWritableContent) -- neither class nor routine.
        m = _FakeModule(["Alias"], Alias="bytes | AsyncIterator[bytes]")
        assert mod.exports_symbols([m]) == {"Alias": "other"}


# ---------------------------------------------------------------------------
# Index link-row extractor (index.md -> {symbol names})
# ---------------------------------------------------------------------------


class TestIndexLinkSymbols:
    def test_identifier_link_rows_collected(self, mod):
        text = _page("""
## Core

| Class | Description |
|-------|-------------|
| [Store](store.md) | Main entry point |
| [Registry](registry.md) | Backend registry |
""")
        assert mod.index_link_symbols(text) == {"Store", "Registry"}

    def test_module_rows_excluded(self, mod):
        # Extensions section rows use dotted module names as link text -- not
        # Python identifiers, so they are not symbol rows.
        text = _page("""
## Extensions

| Module | Description |
|--------|-------------|
| [ext.batch](extensions/batch.md) | Batch ops |
| [aio.ext.write](aio/extensions/write.md) | Async write helpers |
""")
        assert mod.index_link_symbols(text) == set()

    def test_anchor_targets_do_not_affect_symbol_name(self, mod):
        text = _page("""
| [RegistryConfig](config.md#remote_store.RegistryConfig) | Config |
| [info](info.md#remote_store.info) | Introspection |
""")
        assert mod.index_link_symbols(text) == {"RegistryConfig", "info"}


# ---------------------------------------------------------------------------
# Directive extractor (::: pkg.path.Name -> {leaf symbol names})
# ---------------------------------------------------------------------------


class TestDirectiveSymbols:
    def test_leaf_names_collected_across_texts(self, mod):
        a = _page("""
::: remote_store.backends.ArrowSerializer
    options:
      show_root_heading: true
""")
        b = _page("""
::: remote_store.aio.AsyncAzureBackend
""")
        assert mod.directive_symbols([a, b]) == {"ArrowSerializer", "AsyncAzureBackend"}

    def test_non_directive_lines_ignored(self, mod):
        text = _page("""
# Heading

Some prose with ::: not-a-directive inline.

::: remote_store.backends.ResultSerializer
""")
        assert mod.directive_symbols([text]) == {"ResultSerializer"}


# ---------------------------------------------------------------------------
# Exports compare (bidirectional set diff)
# ---------------------------------------------------------------------------


class TestCompareExports:
    def test_exact_match_yields_no_errors(self, mod):
        expected = {"Store": "class", "info": "function"}
        index = {"Store", "info"}
        assert mod.compare_exports(expected, index, frozenset()) == []

    def test_missing_index_row_is_error(self, mod):
        expected = {"Store": "class"}
        errors = mod.compare_exports(expected, set(), frozenset())
        assert len(errors) == 1
        assert "Store" in errors[0]
        assert "class" in errors[0]

    def test_primary_class_dropped_from_index_still_fails(self, mod):
        # Regression for PR #697 review: a *primary* public class that loses its
        # index row must fail MISSING even though it is ::: -rendered on its own
        # page live.  The exemption is the explicit allowlist, NOT "rendered
        # somewhere" -- so a class absent from _INDEX_EXEMPT is never excused.
        expected = {"NotFound": "class"}
        errors = mod.compare_exports(expected, set(), mod._INDEX_EXEMPT)
        assert len(errors) == 1
        assert "NotFound" in errors[0]

    def test_allowlisted_companion_is_exempt(self, mod):
        # Backend-companion helper on the allowlist: no index row, not an error.
        expected = {"ArrowSerializer": "class"}
        assert mod.compare_exports(expected, set(), frozenset({"ArrowSerializer"})) == []

    def test_extra_index_link_is_error(self, mod):
        expected: dict[str, str] = {}
        errors = mod.compare_exports(expected, {"Ghost"}, frozenset())
        assert len(errors) == 1
        assert "Ghost" in errors[0]

    def test_allowlist_does_not_rescue_an_extra(self, mod):
        # A symbol linked in the index but absent from __all__ is EXTRA even if
        # it is on the exempt allowlist -- it is not part of the public surface.
        expected: dict[str, str] = {}
        errors = mod.compare_exports(expected, {"Ghost"}, frozenset({"Ghost"}))
        assert len(errors) == 1
        assert "Ghost" in errors[0]


# ---------------------------------------------------------------------------
# Allowlist staleness policing
# ---------------------------------------------------------------------------


class TestAllowlistStaleness:
    def test_healthy_allowlist_yields_no_errors(self, mod):
        # Public, absent from the index, and rendered -> a genuine companion.
        expected = {"ArrowSerializer": "class"}
        errors = mod.allowlist_staleness_errors(frozenset({"ArrowSerializer"}), expected, set(), {"ArrowSerializer"})
        assert errors == []

    def test_exempt_not_in_any_all_is_flagged(self, mod):
        errors = mod.allowlist_staleness_errors(frozenset({"Gone"}), {}, set(), {"Gone"})
        assert len(errors) == 1
        assert "Gone" in errors[0]
        assert "__all__" in errors[0]

    def test_exempt_with_index_row_is_flagged_as_redundant(self, mod):
        # If a former companion gains its own index row, the allowlist entry is
        # now redundant and must be removed.
        expected = {"AsyncAzureBackend": "class"}
        errors = mod.allowlist_staleness_errors(
            frozenset({"AsyncAzureBackend"}), expected, {"AsyncAzureBackend"}, {"AsyncAzureBackend"}
        )
        assert len(errors) == 1
        assert "index row" in errors[0]

    def test_exempt_not_rendered_is_flagged_as_undocumented(self, mod):
        # An exempt symbol that is not ::: -rendered anywhere is genuinely
        # undocumented -- the allowlist must not hide that.
        expected = {"ResultSerializer": "class"}
        errors = mod.allowlist_staleness_errors(frozenset({"ResultSerializer"}), expected, set(), set())
        assert len(errors) == 1
        assert "undocumented" in errors[0]


# ---------------------------------------------------------------------------
# Live index parity
# ---------------------------------------------------------------------------


class TestLiveIndex:
    """Live round-trip against the real surface.

    Runs against live imports, so it is only correct in a full-extras
    environment (hatch / CI) -- bare-python sandboxes lack optional-dep
    symbols.  Same trade-off as the strict coverage gate.
    """

    def _live(self, mod):
        import remote_store
        import remote_store.aio
        import remote_store.backends

        modules = [remote_store, remote_store.backends, remote_store.aio]
        expected = mod.exports_symbols(modules)
        index = mod.index_link_symbols(mod.INDEX_PAGE.read_text(encoding="utf-8"))
        rendered = mod.directive_symbols(p.read_text(encoding="utf-8") for p in mod.API_DIR.rglob("*.md"))
        return expected, index, rendered

    def test_index_mirrors_public_all(self, mod):
        expected, index, _ = self._live(mod)
        errors = mod.compare_exports(expected, index, mod._INDEX_EXEMPT)
        assert errors == [], "index.md parity drift: " + "; ".join(errors)

    def test_allowlist_is_not_stale(self, mod):
        # Self-policing for _INDEX_EXEMPT, via the same function main() runs:
        # each entry must be a real public symbol, absent from the index, and
        # ::: -rendered somewhere.  Keeps the hand-maintained allowlist honest.
        expected, index, rendered = self._live(mod)
        errors = mod.allowlist_staleness_errors(mod._INDEX_EXEMPT, expected, index, rendered)
        assert errors == [], "stale _INDEX_EXEMPT: " + "; ".join(errors)
