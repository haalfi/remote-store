"""Golden test for scripts/gen_graph_viz.py (ID-165).

Verifies that the committed graph_viz.html matches a fresh generate() call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_graph_viz_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import gen_graph_viz

    return gen_graph_viz


@pytest.mark.os_sensitive
def test_graph_viz_html_is_up_to_date(gen_graph_viz_module):
    """Committed graph_viz.html must match a fresh generate() call.

    Fails if the script was modified but the output file was not regenerated.
    Run:  hatch run gen-graph-viz
    """
    committed = gen_graph_viz_module.OUT.read_bytes()
    committed_lf = committed.replace(b"\r\n", b"\n")

    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    fresh = gen_graph_viz_module.generate(graph)
    fresh_bytes = fresh.encode("utf-8")

    assert committed_lf == fresh_bytes, "graph_viz.html is out of date. Run:  hatch run gen-graph-viz"


def test_generate_raises_when_d3_vendor_missing(gen_graph_viz_module, monkeypatch, tmp_path):
    """generate() must raise FileNotFoundError when D3_VENDOR is absent."""
    monkeypatch.setattr(gen_graph_viz_module, "D3_VENDOR", tmp_path / "nonexistent.js")
    graph = json.loads((ROOT / "docs-src" / "_data" / "graph" / "graph.json").read_bytes())
    with pytest.raises(FileNotFoundError):
        gen_graph_viz_module.generate(graph)


def test_generate_raises_on_token_contamination(gen_graph_viz_module):
    """generate() must raise RuntimeError when a replacement value re-introduces a token.

    source_version == "__GRAPH_DATA__": re.sub fills the __VERSION__ slot with the
    string "__GRAPH_DATA__", which survives in the output (re.sub does not rescan
    replacement values). The post-substitution guard must catch this.
    """
    graph = {
        "source_version": "__GRAPH_DATA__",
        "schema_version": "1.1",
        "nodes": [],
        "edges": [],
    }
    with pytest.raises(RuntimeError, match="survived substitution"):
        gen_graph_viz_module.generate(graph)
