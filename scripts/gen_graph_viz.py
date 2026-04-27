"""Generate docs-src/_data/graph/graph_viz.html from graph.json (ID-165).

Run with:  hatch run gen-graph-viz
           hatch run python scripts/gen_graph_viz.py [--check]

--check exits 1 if graph_viz.html would change; use in CI or pre-commit.

The output is a self-contained, single-file interactive HTML visualization
of the RFC-0012 graph IR.  No server or build step required -- open directly
in a browser.  The graph data is embedded as a JSON literal so the file is
portable and versionable.

Schema compatibility: reads graph.json schema_version 1.0 and 1.1.  Version
1.1 fields (is_abstract, is_async, file, line on method nodes) are used when
present; the rendering degrades gracefully when they are absent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"
OUT = ROOT / "docs-src" / "_data" / "graph" / "graph_viz.html"

# ---------------------------------------------------------------------------
# HTML template  (plain string -- no .format(), placeholders are __TOKENS__)
# ---------------------------------------------------------------------------

_TEMPLATE = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '<meta charset="UTF-8">\n'
    "<title>remote-store graph IR — v__VERSION__</title>\n"
    '<script src="https://d3js.org/d3.v7.min.js"></script>\n'
    "<style>\n"
    "*{box-sizing:border-box;margin:0;padding:0}\n"
    "body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;"
    "display:flex;height:100vh;overflow:hidden}\n"
    "#sidebar{width:280px;min-width:280px;background:#1e293b;padding:16px;overflow-y:auto;"
    "border-right:1px solid #334155;display:flex;flex-direction:column;gap:14px}\n"
    "#sidebar h1{font-size:14px;font-weight:700;color:#94a3b8;letter-spacing:.05em;text-transform:uppercase}\n"
    "#sidebar h2{font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;"
    "letter-spacing:.08em;margin-bottom:6px}\n"
    ".legend-row{display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;padding:3px 0}\n"
    ".legend-row input{accent-color:#7c3aed}\n"
    ".dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}\n"
    ".line-sample{width:28px;height:3px;flex-shrink:0;border-radius:2px}\n"
    "#detail{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;"
    "font-size:12px;line-height:1.6;min-height:80px}\n"
    "#detail .detail-id{font-weight:700;color:#c4b5fd;word-break:break-all;margin-bottom:4px}\n"
    "#detail .detail-row{color:#94a3b8}\n"
    "#detail .detail-row span{color:#e2e8f0}\n"
    "#detail .placeholder{color:#475569;font-style:italic}\n"
    "#canvas-wrap{flex:1;position:relative;overflow:hidden}\n"
    "svg{width:100%;height:100%}\n"
    ".node circle{stroke-width:1.5px;cursor:pointer}\n"
    ".node circle:hover{stroke-width:3px}\n"
    ".node.abstract circle{stroke-dasharray:4,2}\n"
    ".node text{font-size:10px;fill:#cbd5e1;pointer-events:none;text-shadow:0 1px 3px #0f172a}\n"
    ".node.selected circle{stroke-width:3px;filter:drop-shadow(0 0 6px currentColor)}\n"
    ".link{stroke-opacity:.55}\n"
    ".link.faded{stroke-opacity:.08}\n"
    ".node.faded circle{opacity:.15}\n"
    ".node.faded text{opacity:0}\n"
    ".async-badge{font-size:8px;fill:#7dd3fc;pointer-events:none}\n"
    "#controls{position:absolute;top:12px;right:12px;display:flex;gap:8px}\n"
    ".btn{background:#1e293b;border:1px solid #334155;color:#94a3b8;"
    "padding:5px 10px;border-radius:6px;cursor:pointer;font-size:12px}\n"
    ".btn:hover{background:#334155;color:#e2e8f0}\n"
    "#zoom-hint{position:absolute;bottom:10px;right:12px;font-size:11px;color:#475569}\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
    '<div id="sidebar">\n'
    "  <div>\n"
    "    <h1>remote-store</h1>\n"
    '    <div style="font-size:11px;color:#475569;margin-top:2px;">\n'
    "      graph IR &mdash; v__VERSION__ &nbsp;|&nbsp; __N_NODES__ nodes"
    " &nbsp;|&nbsp; __N_EDGES__ edges &nbsp;|&nbsp; schema __SCHEMA_VERSION__\n"
    "    </div>\n"
    "  </div>\n"
    '  <div><h2>Node types</h2><div id="node-legend"></div></div>\n'
    '  <div><h2>Edge types</h2><div id="edge-legend"></div></div>\n'
    '  <div><h2>Selected node</h2><div id="detail">'
    '<span class="placeholder">Click a node to inspect it</span></div></div>\n'
    "</div>\n"
    '<div id="canvas-wrap">\n'
    '  <svg id="graph"></svg>\n'
    '  <div id="controls">\n'
    '    <button class="btn" id="btn-reset">Reset zoom</button>\n'
    '    <button class="btn" id="btn-reheat">Reheat</button>\n'
    "  </div>\n"
    '  <div id="zoom-hint">Scroll to zoom &bull; Drag to pan &bull; Drag nodes to reposition</div>\n'
    "</div>\n"
    "<script>\n"
    "const GRAPH = __GRAPH_DATA__;\n"
    "\n"
    "const NODE_CFG = {\n"
    "  capability: {color:'#F59E0B',r:14,label:n=>n.value||n.id.split(':')[1]},\n"
    "  class:      {color:'#3B82F6',r:13,label:n=>n.id.split('.').pop()},\n"
    "  method:     {color:'#10B981',r:10,label:n=>n.id.split('.').pop()},\n"
    "  package:    {color:'#A855F7',r:16,label:n=>n.id.split(':')[1]},\n"
    "  requirement:{color:'#F43F5E',r:8, label:n=>{\n"
    "    const p=n.id.split('.');return p[p.length-2]+'.gate';\n"
    "  }},\n"
    "  extra:      {color:'#94A3B8',r:11,label:n=>n.id.split(':')[1]},\n"
    "};\n"
    "\n"
    "const EDGE_CFG = {\n"
    "  declares:{color:'#3B82F6',dash:'0',    width:1.5},\n"
    "  enables: {color:'#10B981',dash:'4,3',  width:1.5},\n"
    "  gates:   {color:'#F43F5E',dash:'0',    width:1.5},\n"
    "  inherits:{color:'#A855F7',dash:'0',    width:2  },\n"
    "  mirrors: {color:'#F59E0B',dash:'6,3',  width:2  },\n"
    "  of:      {color:'#64748B',dash:'2,2',  width:1  },\n"
    "};\n"
    "\n"
    "const visibleNodeKinds = new Set(Object.keys(NODE_CFG));\n"
    "const visibleEdgeKinds = new Set(Object.keys(EDGE_CFG));\n"
    "let selectedId = null;\n"
    "\n"
    "function buildLegend() {\n"
    "  const nl = d3.select('#node-legend');\n"
    "  Object.entries(NODE_CFG).forEach(([kind, cfg]) => {\n"
    "    const row = nl.append('div').attr('class','legend-row');\n"
    "    row.append('input').attr('type','checkbox').property('checked',true)\n"
    "      .on('change', function(){\n"
    "        this.checked?visibleNodeKinds.add(kind):visibleNodeKinds.delete(kind); update();\n"
    "      });\n"
    "    row.append('div').attr('class','dot').style('background',cfg.color);\n"
    "    row.append('span').text(kind+' ('+GRAPH.nodes.filter(n=>n.kind===kind).length+')');\n"
    "  });\n"
    "  const el = d3.select('#edge-legend');\n"
    "  Object.entries(EDGE_CFG).forEach(([kind, cfg]) => {\n"
    "    const row = el.append('div').attr('class','legend-row');\n"
    "    row.append('input').attr('type','checkbox').property('checked',true)\n"
    "      .on('change', function(){\n"
    "        this.checked?visibleEdgeKinds.add(kind):visibleEdgeKinds.delete(kind); update();\n"
    "      });\n"
    "    row.append('div').attr('class','line-sample')\n"
    "      .style('background', cfg.dash==='0'\n"
    "        ? cfg.color\n"
    "        : `repeating-linear-gradient(90deg,${cfg.color} 0,${cfg.color} 4px,transparent 4px,transparent 7px)`)\n"
    "      .style('height', cfg.width+'px');\n"
    "    row.append('span').text(kind);\n"
    "  });\n"
    "}\n"
    "\n"
    "function showDetail(node) {\n"
    "  const el = document.getElementById('detail');\n"
    "  if (!node) { el.innerHTML='<span class=\"placeholder\">Click a node to inspect it</span>'; return; }\n"
    "  const skip = new Set(['id','kind']);\n"
    "  const rows = Object.entries(node)\n"
    "    .filter(([k]) => !skip.has(k))\n"
    '    .map(([k,v]) => `<div class="detail-row">${k}: <span>${v}</span></div>`)\n'
    "    .join('');\n"
    '  el.innerHTML = `<div class="detail-id">${node.id}</div>`\n'
    '    + `<div class="detail-row">kind: <span>${node.kind}</span></div>${rows}`;\n'
    "}\n"
    "\n"
    "const svg = d3.select('#graph');\n"
    "const defs = svg.append('defs');\n"
    "Object.entries(EDGE_CFG).forEach(([kind, cfg]) => {\n"
    "  defs.append('marker').attr('id','arrow-'+kind)\n"
    "    .attr('viewBox','0 -5 10 10').attr('refX',22).attr('refY',0)\n"
    "    .attr('markerWidth',5).attr('markerHeight',5).attr('orient','auto')\n"
    "    .append('path').attr('d','M0,-5L10,0L0,5').attr('fill',cfg.color);\n"
    "});\n"
    "\n"
    "const g = svg.append('g');\n"
    "const zoom = d3.zoom().scaleExtent([0.15,4]).on('zoom', e=>g.attr('transform',e.transform));\n"
    "svg.call(zoom);\n"
    "document.getElementById('btn-reset').onclick =\n"
    "  () => svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);\n"
    "document.getElementById('btn-reheat').onclick = () => simulation.alpha(0.8).restart();\n"
    "\n"
    "const nodeMap = new Map(GRAPH.nodes.map(n=>[n.id,{...n}]));\n"
    "const links = GRAPH.edges\n"
    "  .map(e=>({...e, source:nodeMap.get(e.src), target:nodeMap.get(e.dst)}))\n"
    "  .filter(l=>l.source&&l.target);\n"
    "const nodes = [...nodeMap.values()];\n"
    "\n"
    "const simulation = d3.forceSimulation(nodes)\n"
    "  .force('link', d3.forceLink(links).id(d=>d.id).distance(d=>{\n"
    "    return {declares:90,enables:100,gates:80,inherits:80,mirrors:90,of:70}[d.kind]||90;\n"
    "  }).strength(0.4))\n"
    "  .force('charge', d3.forceManyBody().strength(-280))\n"
    "  .force('collide', d3.forceCollide().radius(d=>(NODE_CFG[d.kind]?.r||10)+8))\n"
    "  .force('center', d3.forceCenter(700,450));\n"
    "\n"
    "let linkSel, nodeSel;\n"
    "\n"
    "function update() {\n"
    "  const activeNodes = nodes.filter(n=>visibleNodeKinds.has(n.kind));\n"
    "  const activeIds = new Set(activeNodes.map(n=>n.id));\n"
    "  const activeLinks = links.filter(\n"
    "    l=>visibleEdgeKinds.has(l.kind)&&activeIds.has(l.source.id)&&activeIds.has(l.target.id));\n"
    "\n"
    "  linkSel = g.selectAll('.link').data(activeLinks, d=>d.src+'>'+d.kind+'>'+d.dst)\n"
    "    .join(enter=>enter.append('line').attr('class','link'), u=>u, exit=>exit.remove())\n"
    "    .attr('stroke', d=>EDGE_CFG[d.kind]?.color||'#666')\n"
    "    .attr('stroke-width', d=>EDGE_CFG[d.kind]?.width||1.5)\n"
    "    .attr('stroke-dasharray', d=>EDGE_CFG[d.kind]?.dash||'0')\n"
    "    .attr('marker-end', d=>`url(#arrow-${d.kind})`);\n"
    "\n"
    "  nodeSel = g.selectAll('.node').data(activeNodes, d=>d.id)\n"
    "    .join(\n"
    "      enter => {\n"
    "        const ng = enter.append('g').attr('class','node')\n"
    "          .call(d3.drag()\n"
    "            .on('start',(ev,d)=>{ if(!ev.active)simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })\n"
    "            .on('drag', (ev,d)=>{ d.fx=ev.x; d.fy=ev.y; })\n"
    "            .on('end',  (ev,d)=>{ if(!ev.active)simulation.alphaTarget(0); d.fx=null; d.fy=null; }))\n"
    "          .on('click',(ev,d)=>{\n"
    "            ev.stopPropagation();\n"
    "            selectedId = selectedId===d.id ? null : d.id;\n"
    "            showDetail(selectedId ? d : null);\n"
    "            highlightNeighbors();\n"
    "          });\n"
    "        ng.append('circle');\n"
    "        ng.append('text').attr('dy','0.35em').attr('text-anchor','middle');\n"
    "        ng.append('text').attr('class','async-badge').attr('text-anchor','middle');\n"
    "        return ng;\n"
    "      },\n"
    "      u=>u,\n"
    "      exit=>exit.remove()\n"
    "    );\n"
    "\n"
    "  nodeSel.select('circle')\n"
    "    .attr('r', d=>NODE_CFG[d.kind]?.r||10)\n"
    "    .attr('fill', d=>NODE_CFG[d.kind]?.color||'#888')\n"
    "    .attr('stroke', d=>d3.color(NODE_CFG[d.kind]?.color||'#888').brighter(0.8));\n"
    "\n"
    "  nodeSel.classed('abstract', d=>d.is_abstract===true);\n"
    "\n"
    "  nodeSel.select('text:not(.async-badge)')\n"
    "    .text(d=>NODE_CFG[d.kind]?.label(d)||d.id)\n"
    "    .attr('dy', d=>(NODE_CFG[d.kind]?.r||10)+12);\n"
    "\n"
    "  nodeSel.select('text.async-badge')\n"
    "    .text(d=>d.is_async===true?'async':'')\n"
    "    .attr('dy', d=>(NODE_CFG[d.kind]?.r||10)+22);\n"
    "\n"
    "  nodeSel.classed('selected', d=>d.id===selectedId);\n"
    "\n"
    "  simulation.nodes(activeNodes);\n"
    "  simulation.force('link').links(activeLinks);\n"
    "  simulation.alpha(0.4).restart();\n"
    "}\n"
    "\n"
    "function highlightNeighbors() {\n"
    "  if (!selectedId) { nodeSel?.classed('faded',false); linkSel?.classed('faded',false); return; }\n"
    "  const nb = new Set([selectedId]);\n"
    "  linkSel?.each(d=>{\n"
    "    if(d.source.id===selectedId||d.target.id===selectedId){\n"
    "      nb.add(d.source.id); nb.add(d.target.id);\n"
    "    }\n"
    "  });\n"
    "  nodeSel?.classed('faded', d=>!nb.has(d.id));\n"
    "  linkSel?.classed('faded', d=>d.source.id!==selectedId&&d.target.id!==selectedId);\n"
    "}\n"
    "\n"
    "svg.on('click',()=>{ selectedId=null; showDetail(null); highlightNeighbors(); });\n"
    "\n"
    "simulation.on('tick',()=>{\n"
    "  linkSel?.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)\n"
    "    .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);\n"
    "  nodeSel?.attr('transform',d=>`translate(${d.x},${d.y})`);\n"
    "});\n"
    "\n"
    "buildLegend();\n"
    "update();\n"
    "</script>\n"
    "</body>\n"
    "</html>\n"
)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(graph: dict) -> str:
    graph_data = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    return (
        _TEMPLATE.replace("__VERSION__", graph.get("source_version", ""))
        .replace("__SCHEMA_VERSION__", graph.get("schema_version", ""))
        .replace("__N_NODES__", str(len(graph.get("nodes", []))))
        .replace("__N_EDGES__", str(len(graph.get("edges", []))))
        .replace("__GRAPH_DATA__", graph_data)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if output would change")
    args = parser.parse_args()

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    html = generate(graph)
    html_bytes = html.encode("utf-8")

    if args.check:
        if OUT.exists():
            existing = OUT.read_bytes().replace(b"\r\n", b"\n")
            if existing == html_bytes:
                print(f"gen-graph-viz-check: {OUT.name} is up to date.")
                return
        print(
            f"gen-graph-viz-check: {OUT.name} is stale -- run hatch run gen-graph-viz",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT.write_bytes(html_bytes)
    print(f"Written {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
