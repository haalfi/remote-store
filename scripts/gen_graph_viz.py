"""Generate docs-src/explanation/graph_viz.html from graph.json (ID-165).

Run with:  hatch run gen-graph-viz
           hatch run python scripts/gen_graph_viz.py [--check]

--check exits 1 if graph_viz.html would change; use in CI or pre-commit.

The output is a self-contained, single-file interactive HTML visualization
of the project's API graph.  No server or build step required -- open directly
in a browser.  The graph data is embedded as a JSON literal so the file is
portable and versionable.

Layout: D3 force-directed with per-kind positional bias (soft LR columns
without rigidity).  "declares" edges are hidden by default -- they dominate
numerically and collapse the centre; toggle them on to see the full picture.

Schema compatibility: reads graph.json schema_version 1.0, 1.1, and 1.2.
1.1 fields (is_abstract, is_async, file, line on method nodes) are used when
present; the rendering degrades gracefully when they are absent.  1.2 adds
``capability_delta`` to ``mirrors`` edges; the viz embeds it as data but does
not render it (consumers wanting a sync/async capability diff should query
``graph.json`` directly).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"
OUT = ROOT / "docs-src" / "explanation" / "graph_viz.html"
D3_VENDOR = ROOT / "docs-src" / "_data" / "graph" / "d3.v7.min.js"

# ---------------------------------------------------------------------------
# HTML template  (plain string -- no .format(), placeholders are __TOKENS__)
# ---------------------------------------------------------------------------

_TEMPLATE = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    "<title>remote-store API graph — v__VERSION__</title>\n"
    "<script>__D3_INLINE__</script>\n"
    "<style>\n"
    "*{box-sizing:border-box;margin:0;padding:0}\n"
    "body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;"
    "display:flex;height:100vh;height:100dvh;overflow:hidden;"
    "-webkit-tap-highlight-color:transparent}\n"
    "#sidebar{width:268px;min-width:268px;background:#1e293b;padding:14px;overflow-y:auto;"
    "border-right:1px solid #334155;display:flex;flex-direction:column;gap:13px}\n"
    "#sidebar h1{font-size:13px;font-weight:700;color:#94a3b8;letter-spacing:.05em;"
    "text-transform:uppercase}\n"
    "#sidebar h2{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;"
    "letter-spacing:.08em;margin-bottom:5px}\n"
    ".legend-row{display:flex;align-items:center;gap:8px;font-size:11.5px;cursor:pointer;"
    "padding:2px 0}\n"
    ".legend-row input{accent-color:#7c3aed}\n"
    ".dot{width:11px;height:11px;border-radius:50%;flex-shrink:0}\n"
    ".line-sample{width:24px;height:3px;flex-shrink:0;border-radius:2px}\n"
    ".dim{opacity:.45;font-size:10px}\n"
    "#detail{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;"
    "font-size:11px;line-height:1.55;min-height:72px}\n"
    "#detail .detail-id{font-weight:700;color:#c4b5fd;word-break:break-all;margin-bottom:3px}\n"
    "#detail .detail-row{color:#94a3b8}\n"
    "#detail .detail-row span{color:#e2e8f0}\n"
    "#detail .placeholder{color:#475569;font-style:italic}\n"
    "#canvas-wrap{flex:1;position:relative;overflow:hidden}\n"
    "svg{width:100%;height:100%;display:block;touch-action:none;"
    "-webkit-user-select:none;user-select:none}\n"
    ".node circle{stroke-width:1.5px;cursor:pointer;transition:r .12s}\n"
    ".node circle:hover{stroke-width:3px}\n"
    ".node.abstract circle{stroke-dasharray:4,2}\n"
    ".node text{font-size:10px;fill:#cbd5e1;pointer-events:none;"
    "text-shadow:0 1px 3px #0f172a}\n"
    ".node.selected circle{stroke-width:3px;"
    "filter:drop-shadow(0 0 7px currentColor)}\n"
    ".link{stroke-opacity:.5}\n"
    ".link.faded{stroke-opacity:.06}\n"
    ".node.faded circle{opacity:.13}\n"
    ".node.faded text{opacity:0}\n"
    ".async-badge{font-size:7.5px;fill:#7dd3fc;pointer-events:none}\n"
    "#controls{position:absolute;top:10px;right:10px;display:flex;gap:6px}\n"
    ".btn{background:#1e293b;border:1px solid #334155;color:#94a3b8;"
    "padding:4px 10px;border-radius:5px;cursor:pointer;font-size:11px}\n"
    ".btn:hover{background:#334155;color:#e2e8f0}\n"
    "#zoom-hint{position:absolute;bottom:8px;right:10px;font-size:10px;color:#475569}\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
    '<div id="sidebar">\n'
    "  <div>\n"
    "    <h1>remote-store</h1>\n"
    '    <div style="font-size:10px;color:#475569;margin-top:2px;">'
    "API graph — v__VERSION__ &nbsp;|&nbsp; __N_NODES__ nodes"
    " &nbsp;|&nbsp; __N_EDGES__ edges &nbsp;|&nbsp; schema __SCHEMA_VERSION__"
    "</div>\n"
    "  </div>\n"
    '  <div><h2>Node types</h2><div id="node-legend"></div></div>\n'
    '  <div><h2>Edge types</h2><div id="edge-legend"></div></div>\n'
    '  <div><h2>Selected node</h2><div id="detail">'
    '<span class="placeholder">Click a node to inspect it</span>'
    "</div></div>\n"
    "</div>\n"
    '<div id="canvas-wrap">\n'
    '  <svg id="graph" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid meet"></svg>\n'
    '  <div id="controls">\n'
    '    <button class="btn" id="btn-reset">Reset zoom</button>\n'
    '    <button class="btn" id="btn-reheat">Reheat</button>\n'
    "  </div>\n"
    '  <div id="zoom-hint">'
    "Scroll to zoom &bull; Drag to pan &bull; Drag nodes to reposition"
    "</div>\n"
    "</div>\n"
    "<script>\n"
    "const GRAPH = __GRAPH_DATA__;\n"
    "\n"
    "// ---- Config ---------------------------------------------------------------\n"
    "const NODE_CFG = {\n"
    "  capability:  {color:'#F59E0B',r:14, label:n=>n.value||n.id.split(':')[1]},\n"
    "  class:       {color:'#3B82F6',r:13, label:n=>n.id.split('.').pop()},\n"
    "  method:      {color:'#10B981',r:10, label:n=>n.id.split('.').pop()},\n"
    "  package:     {color:'#A855F7',r:15, label:n=>n.id.split(':')[1]},\n"
    "  requirement: {color:'#F43F5E',r:8,  label:n=>{\n"
    "    const p=n.id.split('.');return p[p.length-2]+'.'+p[p.length-1];\n"
    "  }},\n"
    "  extra:       {color:'#94A3B8',r:11, label:n=>n.id.split(':')[1]},\n"
    "};\n"
    "\n"
    "// declares hidden by default: 133 edges collapse the centre.\n"
    "// Toggle on to verify the full capability surface.\n"
    "const EDGE_CFG = {\n"
    "  inherits:{color:'#A855F7',dash:'0',  width:2,   defaultOn:true},\n"
    "  mirrors: {color:'#F59E0B',dash:'6,3',width:2,   defaultOn:true},\n"
    "  enables: {color:'#10B981',dash:'4,3',width:1.5, defaultOn:true},\n"
    "  gates:   {color:'#F43F5E',dash:'0',  width:1.5, defaultOn:true},\n"
    "  of:      {color:'#64748B',dash:'2,2',width:1,   defaultOn:true},\n"
    "  declares:{color:'#3B82F6',dash:'0',  width:1,   defaultOn:false},\n"
    "};\n"
    "\n"
    "// ---- State ----------------------------------------------------------------\n"
    "const visibleNodeKinds = new Set(Object.keys(NODE_CFG));\n"
    "const visibleEdgeKinds = new Set(\n"
    "  Object.entries(EDGE_CFG).filter(([,v])=>v.defaultOn).map(([k])=>k)\n"
    ");\n"
    "let selectedId = null;\n"
    "\n"
    "// ---- Graph data -----------------------------------------------------------\n"
    "const nodeMap = new Map(GRAPH.nodes.map(n=>[n.id,{...n}]));\n"
    "const nodes   = [...nodeMap.values()];\n"
    "const links   = GRAPH.edges\n"
    "  .map(e=>({...e, source:nodeMap.get(e.src), target:nodeMap.get(e.dst)}))\n"
    "  .filter(l=>l.source&&l.target);\n"
    "\n"
    "// ---- Soft positional bias (keeps force organic but guided) ----------------\n"
    "// x-target by kind: extras/classes left, caps centre, reqs right, mtds far right\n"
    "const X_BIAS = {\n"
    "  package:     0.08,\n"
    "  extra:       0.18,\n"
    "  class:       0.30,\n"
    "  capability:  0.52,\n"
    "  requirement: 0.68,\n"
    "  method:      0.84,\n"
    "};\n"
    "const Y_BIAS = {\n"
    "  package: 0.12,\n"
    "};\n"
    "\n"
    "// ---- SVG ------------------------------------------------------------------\n"
    "const svg = d3.select('#graph');\n"
    "\n"
    "// ---- Simulation -----------------------------------------------------------\n"
    "// forceX/forceY call .x()/.y() synchronously during initialize() -- svg must\n"
    "// be declared first.  clientWidth is 0 at init time anyway; use design constants.\n"
    "const W0 = 1200, H0 = 800;\n"
    "const simulation = d3.forceSimulation(nodes)\n"
    "  .force('link', d3.forceLink(links).id(d=>d.id)\n"
    "    .distance(d=>d.kind==='declares'?170:d.kind==='inherits'?65:100)\n"
    "    .strength(d=>d.kind==='declares'?0.04:d.kind==='of'?0.5:0.4))\n"
    "  .force('charge', d3.forceManyBody().strength(-620))\n"
    "  .force('collide', d3.forceCollide().radius(d=>(NODE_CFG[d.kind]?.r||10)+14))\n"
    "  .force('xbias', d3.forceX(d=>(X_BIAS[d.kind]??0.5)*W0).strength(0.07))\n"
    "  .force('ybias', d3.forceY(d=>(Y_BIAS[d.kind]??0.5)*H0).strength(0.04));\n"
    "\n"
    "const defs = svg.append('defs');\n"
    "Object.entries(EDGE_CFG).forEach(([kind,cfg])=>{\n"
    "  defs.append('marker').attr('id','arrow-'+kind)\n"
    "    .attr('viewBox','0 -5 10 10').attr('refX',22).attr('refY',0)\n"
    "    .attr('markerWidth',5).attr('markerHeight',5).attr('orient','auto')\n"
    "    .append('path').attr('d','M0,-5L10,0L0,5').attr('fill',cfg.color);\n"
    "});\n"
    "const g = svg.append('g');\n"
    "const zoom = d3.zoom().scaleExtent([0.1,4])\n"
    "  .on('zoom', e=>g.attr('transform',e.transform));\n"
    "svg.call(zoom);\n"
    "document.getElementById('btn-reset').onclick =\n"
    "  ()=>svg.transition().duration(500).call(zoom.transform,d3.zoomIdentity);\n"
    "document.getElementById('btn-reheat').onclick =\n"
    "  ()=>simulation.alpha(0.7).restart();\n"
    "\n"
    "// ---- Legend ---------------------------------------------------------------\n"
    "function buildLegend(){\n"
    "  const nl=d3.select('#node-legend');\n"
    "  Object.entries(NODE_CFG).forEach(([kind,cfg])=>{\n"
    "    const row=nl.append('div').attr('class','legend-row');\n"
    "    row.append('input').attr('type','checkbox').property('checked',true)\n"
    "      .on('change',function(){\n"
    "        this.checked?visibleNodeKinds.add(kind):visibleNodeKinds.delete(kind);\n"
    "        update();\n"
    "      });\n"
    "    row.append('div').attr('class','dot').style('background',cfg.color);\n"
    "    row.append('span').text(\n"
    "      kind+' ('+GRAPH.nodes.filter(n=>n.kind===kind).length+')');\n"
    "  });\n"
    "\n"
    "  const el=d3.select('#edge-legend');\n"
    "  Object.entries(EDGE_CFG).forEach(([kind,cfg])=>{\n"
    "    const on=cfg.defaultOn;\n"
    "    const row=el.append('div').attr('class','legend-row'+(on?'':' dim'));\n"
    "    row.append('input').attr('type','checkbox').property('checked',on)\n"
    "      .on('change',function(){\n"
    "        this.checked?visibleEdgeKinds.add(kind):visibleEdgeKinds.delete(kind);\n"
    "        update();\n"
    "      });\n"
    "    row.append('div').attr('class','line-sample')\n"
    "      .style('background', cfg.dash==='0'\n"
    "        ? cfg.color\n"
    "        : `repeating-linear-gradient(90deg,${cfg.color} 0,${cfg.color} 4px,`\n"
    "          +`transparent 4px,transparent 7px)`)\n"
    "      .style('height',cfg.width+'px');\n"
    "    row.append('span').text(\n"
    "      kind\n"
    "      +(on?'':' — off')\n"
    "      +' ('+GRAPH.edges.filter(e=>e.kind===kind).length+')');\n"
    "  });\n"
    "}\n"
    "\n"
    "// ---- Detail ---------------------------------------------------------------\n"
    "function esc(s){\n"
    "  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')\n"
    "    .replace(/>/g,'&gt;').replace(/\"/g,'&quot;');\n"
    "}\n"
    "function showDetail(node){\n"
    "  const el=document.getElementById('detail');\n"
    '  if(!node){el.innerHTML=\'<span class="placeholder">'
    "Click a node to inspect it</span>';return;}\n"
    "  const skip=new Set(['id','kind']);\n"
    "  const rows=Object.entries(node)\n"
    "    .filter(([k])=>!skip.has(k))\n"
    '    .map(([k,v])=>`<div class="detail-row">${esc(k)}: <span>${esc(v)}</span></div>`)\n'
    "    .join('');\n"
    '  el.innerHTML=`<div class="detail-id">${esc(node.id)}</div>`\n'
    '    +`<div class="detail-row">kind: <span>${esc(node.kind)}</span></div>${rows}`;\n'
    "}\n"
    "\n"
    "// ---- Rendering ------------------------------------------------------------\n"
    "let linkSel, nodeSel;\n"
    "\n"
    "function update(){\n"
    "  const activeNodes=nodes.filter(n=>visibleNodeKinds.has(n.kind));\n"
    "  const activeIds=new Set(activeNodes.map(n=>n.id));\n"
    "  const activeLinks=links.filter(\n"
    "    l=>visibleEdgeKinds.has(l.kind)\n"
    "    &&activeIds.has(l.source.id)&&activeIds.has(l.target.id));\n"
    "\n"
    "  linkSel=g.selectAll('.link')\n"
    "    .data(activeLinks,d=>d.src+'|'+d.kind+'|'+d.dst)\n"
    "    .join(\n"
    "      enter=>enter.append('line').attr('class','link'),\n"
    "      u=>u, exit=>exit.remove())\n"
    "    .attr('stroke',d=>EDGE_CFG[d.kind]?.color||'#666')\n"
    "    .attr('stroke-width',d=>EDGE_CFG[d.kind]?.width||1.2)\n"
    "    .attr('stroke-dasharray',d=>EDGE_CFG[d.kind]?.dash||'0')\n"
    "    .attr('marker-end',d=>`url(#arrow-${d.kind})`);\n"
    "\n"
    "  nodeSel=g.selectAll('.node').data(activeNodes,d=>d.id)\n"
    "    .join(\n"
    "      enter=>{\n"
    "        const ng=enter.append('g').attr('class','node')\n"
    "          .call(d3.drag()\n"
    "            .on('start',(ev,d)=>{\n"
    "              if(!ev.active)simulation.alphaTarget(0.3).restart();\n"
    "              d.fx=d.x;d.fy=d.y;\n"
    "            })\n"
    "            .on('drag',(ev,d)=>{d.fx=ev.x;d.fy=ev.y;})\n"
    "            .on('end',(ev,d)=>{\n"
    "              if(!ev.active)simulation.alphaTarget(0);\n"
    "              d.fx=null;d.fy=null;\n"
    "            }))\n"
    "          .on('click',(ev,d)=>{\n"
    "            ev.stopPropagation();\n"
    "            selectedId=selectedId===d.id?null:d.id;\n"
    "            showDetail(selectedId?d:null);\n"
    "            highlightNeighbors();\n"
    "          });\n"
    "        ng.append('circle');\n"
    "        ng.append('text').attr('dy','0.35em').attr('text-anchor','middle');\n"
    "        ng.append('text').attr('class','async-badge').attr('text-anchor','middle');\n"
    "        return ng;\n"
    "      },\n"
    "      u=>u, exit=>exit.remove());\n"
    "\n"
    "  nodeSel.select('circle')\n"
    "    .attr('r',d=>NODE_CFG[d.kind]?.r||10)\n"
    "    .attr('fill',d=>NODE_CFG[d.kind]?.color||'#888')\n"
    "    .attr('stroke',d=>d3.color(NODE_CFG[d.kind]?.color||'#888').brighter(0.8));\n"
    "  nodeSel.classed('abstract',d=>d.is_abstract===true);\n"
    "  nodeSel.select('text:not(.async-badge)')\n"
    "    .text(d=>NODE_CFG[d.kind]?.label(d)||d.id)\n"
    "    .attr('dy',d=>(NODE_CFG[d.kind]?.r||10)+12);\n"
    "  nodeSel.select('text.async-badge')\n"
    "    .text(d=>d.is_async===true?'async':'')\n"
    "    .attr('dy',d=>(NODE_CFG[d.kind]?.r||10)+21);\n"
    "  nodeSel.classed('selected',d=>d.id===selectedId);\n"
    "\n"
    "  simulation.nodes(activeNodes);\n"
    "  simulation.force('link').links(activeLinks);\n"
    "  simulation.alpha(0.4).restart();\n"
    "}\n"
    "\n"
    "simulation.on('tick',()=>{\n"
    "  linkSel?.each(function(d){\n"
    "    const sx=d.source.x,sy=d.source.y,tx=d.target.x,ty=d.target.y;\n"
    "    const dx=tx-sx,dy=ty-sy,dist=Math.sqrt(dx*dx+dy*dy);\n"
    "    const r=(NODE_CFG[d.target.kind]?.r||10)+3;\n"
    "    const f=dist>r?(dist-r)/dist:0;\n"
    "    d3.select(this)\n"
    "      .attr('x1',sx).attr('y1',sy)\n"
    "      .attr('x2',sx+dx*f).attr('y2',sy+dy*f);\n"
    "  });\n"
    "  nodeSel?.attr('transform',d=>`translate(${d.x},${d.y})`);\n"
    "});\n"
    "\n"
    "function highlightNeighbors(){\n"
    "  if(!selectedId){\n"
    "    nodeSel?.classed('faded',false);\n"
    "    linkSel?.classed('faded',false);\n"
    "    return;\n"
    "  }\n"
    "  const nb=new Set([selectedId]);\n"
    "  linkSel?.each(d=>{\n"
    "    if(d.source.id===selectedId||d.target.id===selectedId){\n"
    "      nb.add(d.source.id);nb.add(d.target.id);\n"
    "    }\n"
    "  });\n"
    "  nodeSel?.classed('faded',d=>!nb.has(d.id));\n"
    "  linkSel?.classed('faded',\n"
    "    d=>d.source.id!==selectedId&&d.target.id!==selectedId);\n"
    "}\n"
    "svg.on('click',()=>{selectedId=null;showDetail(null);highlightNeighbors();});\n"
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


_TOKENS = ("__VERSION__", "__SCHEMA_VERSION__", "__N_NODES__", "__N_EDGES__", "__GRAPH_DATA__", "__D3_INLINE__")
_TOKEN_RE = re.compile("|".join(re.escape(t) for t in _TOKENS))


def generate(graph: dict) -> str:
    if not D3_VENDOR.exists():
        raise FileNotFoundError(f"{D3_VENDOR.name} not found — it should be committed to the repo.")
    d3_src = D3_VENDOR.read_text(encoding="utf-8")
    graph_data = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    replacements = {
        "__VERSION__": graph.get("source_version", ""),
        "__SCHEMA_VERSION__": graph.get("schema_version", ""),
        "__N_NODES__": str(len(graph.get("nodes", []))),
        "__N_EDGES__": str(len(graph.get("edges", []))),
        "__GRAPH_DATA__": graph_data,
        "__D3_INLINE__": d3_src,
    }
    # Single-pass substitution: re.sub does not rescan replacement values, so a
    # replacement that contains another token cannot cause cross-contamination.
    result = _TOKEN_RE.sub(lambda m: replacements[m.group(0)], _TEMPLATE)
    for token in _TOKENS:
        if token in result:
            raise RuntimeError(f"Template token {token!r} survived substitution — check for collisions")
    return result


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
            label = "stale"
        else:
            label = "missing"
        print(
            f"gen-graph-viz-check: {OUT.name} is {label} -- run hatch run gen-graph-viz",
            file=sys.stderr,
        )
        sys.exit(1)

    OUT.write_bytes(html_bytes)
    print(f"Written {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
