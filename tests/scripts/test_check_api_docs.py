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
