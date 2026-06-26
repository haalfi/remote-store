"""Generate docs-src/explanation/graph_viz.html from graph.json (ID-165, ID-223).

Run with:  hatch run gen-graph-viz
           hatch run python scripts/gen_graph_viz.py [--check]

--check exits 1 if graph_viz.html would change; use in CI or pre-commit.

The output is an interactive HTML visualization of the project's API graph: a
"explore instead of read source" surface, not a static diagram (ID-223). The
graph data is embedded as a JSON literal, but D3 is loaded from the sibling
vendored ``_data/graph/d3.v7.min.js`` via a relative ``<script src>`` rather than
inlined -- so the library is committed once, not duplicated into this file
(ID-224).  No server or build step required: the relative path resolves both in
the repo checkout and the built MkDocs site.

What ID-223 adds on top of the original force-directed layout:

- **Role-aware nodes** (DGM-004): class nodes are coloured by ``role`` -- concrete
  ``backend`` (blue), abstract ``abc`` base (dashed, light blue), and ``facade``
  (indigo). ``Store``/``AsyncStore`` are distinguished from other facades by their
  URI label, not a separate role (DGM-007): they render larger with a gold ring.
- **Containment clustering + collapse** (DGM-008): method nodes are collapsed
  into their class by default, so the opening view is capability-level. Expand a
  class (double-click it, the detail-panel button, or *Expand all*) to reveal its
  methods, which the ``contains`` link force clusters around the class; classes
  cluster around their package the same way. Gate (``requirement``) labels are
  disambiguated as ``Class.method`` by walking ``gates`` to the gated method then
  ``contains`` back to its class.
- **Node *and* edge detail** with deep links (DGM-009): selecting a node or an
  edge shows its metadata plus **deep links** to the authority -- source
  ``file:line`` and the governing spec on GitHub, and the API docs page on the
  site -- so a reader jumps to the source instead of grepping. Method authority
  is derived from the containing class (DGM-009).
- **Composable faceted filtering**: text search plus facets for node kind, class
  role, edge kind, runtime (sync/async), capability (show only a capability's
  gate/declare chain), and dependency (isolate a selected node's neighbourhood
  along ``inherits``/``contains``/``gates``/``of``/``mirrors``). Facets intersect.

Schema compatibility: reads graph.json schema_version 1.0 through 1.4. 1.1 fields
(is_abstract, is_async, file, line on method nodes) drive the abstract styling
and source deep links; 1.2 ``capability_delta`` on ``mirrors`` edges renders in
the edge detail panel; 1.3 ``abc``/``facade`` roles, ``contains`` edges, and
``spec``/``doc`` link metadata drive role rendering, clustering, and deep links;
1.4 ungated facade method nodes (``gated: False``) render as ordinary method
nodes and surface ``gated`` in the detail panel. The rendering degrades
gracefully when any of these are absent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "docs-src" / "_data" / "graph" / "graph.json"
OUT = ROOT / "docs-src" / "explanation" / "graph_viz.html"
D3_VENDOR = ROOT / "docs-src" / "_data" / "graph" / "d3.v7.min.js"
PYPROJECT = ROOT / "pyproject.toml"

# ---------------------------------------------------------------------------
# HTML template  (raw string -- no .format(), placeholders are __TOKENS__;
# the embedded JS uses backslash regexes, so the string is raw to keep them
# literal, and substitution is done with re.sub, which does not rescan values.)
# ---------------------------------------------------------------------------

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>remote-store API graph — v__VERSION__</title>
<script src="../_data/graph/d3.v7.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;
display:flex;height:100vh;height:100dvh;overflow:hidden;-webkit-tap-highlight-color:transparent}
#sidebar{width:288px;min-width:288px;background:#1e293b;padding:14px;overflow-y:auto;
border-right:1px solid #334155;display:flex;flex-direction:column;gap:12px}
#sidebar h1{font-size:13px;font-weight:700;color:#94a3b8;letter-spacing:.05em;text-transform:uppercase}
#sidebar h2{font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;
letter-spacing:.08em;margin-bottom:5px}
.legend-row{display:flex;align-items:center;gap:8px;font-size:11.5px;cursor:pointer;padding:2px 0}
.legend-row input{accent-color:#7c3aed}
.dot{width:11px;height:11px;border-radius:50%;flex-shrink:0}
.dot.ring{box-shadow:0 0 0 2px #fbbf24}
.dot.dashed{border:1.5px dashed #cbd5e1;background:transparent!important}
.swatch-sq{width:11px;height:11px;flex-shrink:0;border-radius:2px}
.line-sample{width:24px;height:3px;flex-shrink:0;border-radius:2px}
.dim{opacity:.45;font-size:10px}
#search{width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;
border-radius:6px;padding:6px 8px;font-size:12px}
#search::placeholder{color:#475569}
.cap-list{max-height:148px;overflow-y:auto;padding-right:4px}
.expand-btns{display:flex;gap:6px;margin-top:6px}
#detail{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px;
font-size:11px;line-height:1.55;min-height:72px}
#detail .detail-id{font-weight:700;color:#c4b5fd;word-break:break-all;margin-bottom:3px}
#detail .detail-row{color:#94a3b8}
#detail .detail-row span{color:#e2e8f0}
#detail .placeholder{color:#475569;font-style:italic}
#detail .links{margin-top:7px;border-top:1px solid #334155;padding-top:6px;display:flex;flex-direction:column;gap:3px}
#detail .links a{color:#7dd3fc;text-decoration:none;word-break:break-all}
#detail .links a:hover{text-decoration:underline}
#detail .xref{color:#c4b5fd;cursor:pointer;text-decoration:underline dotted}
#detail .detail-btn{margin-top:7px}
#sidebar [data-ea-publisher]{position:sticky;bottom:0;font-size:10.5px;min-height:0}
#canvas-wrap{flex:1;position:relative;overflow:hidden}
svg{width:100%;height:100%;display:block;touch-action:none;-webkit-user-select:none;user-select:none}
.node circle{stroke-width:1.5px;cursor:pointer;transition:r .12s}
.node circle:hover{stroke-width:3px}
.node.abstract circle{stroke-dasharray:4,2}
.node.store circle{stroke:#fbbf24;stroke-width:2.5px}
.node.store text.label{font-weight:700;fill:#fde68a}
.node text{font-size:10px;fill:#cbd5e1;pointer-events:none;text-shadow:0 1px 3px #0f172a}
.node.selected circle{stroke-width:3px;filter:drop-shadow(0 0 7px currentColor)}
.link{stroke-opacity:.5;cursor:pointer}
.link.faded{stroke-opacity:.06}
.link.selected-edge{stroke-opacity:1}
.node.faded circle{opacity:.13}
.node.faded text{opacity:0}
.sub-badge{font-size:7.5px;fill:#7dd3fc;pointer-events:none}
.count-badge{font-size:8px;fill:#fcd34d;pointer-events:none;font-weight:700}
#controls{position:absolute;top:10px;right:10px;display:flex;gap:6px}
.btn{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 10px;
border-radius:5px;cursor:pointer;font-size:11px}
.btn:hover{background:#334155;color:#e2e8f0}
#zoom-hint{position:absolute;bottom:8px;right:10px;font-size:10px;color:#475569}
</style>
</head>
<body>
<div id="sidebar">
  <div>
    <h1>remote-store</h1>
    <div style="font-size:10px;color:#475569;margin-top:2px;">API graph — v__VERSION__
      &nbsp;|&nbsp; __N_NODES__ nodes &nbsp;|&nbsp; __N_EDGES__ edges
      &nbsp;|&nbsp; schema __SCHEMA_VERSION__</div>
  </div>
  <div><input id="search" type="search" placeholder="Search nodes…" autocomplete="off"></div>
  <div><h2>Node types</h2><div id="node-legend"></div></div>
  <div><h2>Class roles</h2><div id="role-legend"></div></div>
  <div><h2>Edge types</h2><div id="edge-legend"></div></div>
  <div><h2>Runtime</h2><div id="runtime-legend"></div></div>
  <div><h2>Capabilities <span class="dim">(none = all)</span></h2><div id="cap-legend" class="cap-list"></div></div>
  <div><h2>Explore</h2>
    <label class="legend-row"><input type="checkbox" id="iso-toggle">
      <span>Isolate selection's neighbourhood</span></label>
    <div class="expand-btns">
      <button class="btn" id="btn-expand-all">Expand all</button>
      <button class="btn" id="btn-collapse-all">Collapse all</button>
    </div>
  </div>
  <div><h2>Selected</h2><div id="detail">
    <span class="placeholder">Click a node or an edge to inspect it</span></div></div>
  <div id="ethical-ad-placement"></div>
</div>
<div id="canvas-wrap">
  <svg id="graph" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid meet"></svg>
  <div id="controls">
    <button class="btn" id="btn-reset">Reset zoom</button>
    <button class="btn" id="btn-reheat">Reheat</button>
  </div>
  <div id="zoom-hint">Scroll to zoom &bull; Drag to pan &bull; Double-click a class to expand</div>
</div>
<script>
const GRAPH = __GRAPH_DATA__;
const BLOB_BASE = "__BLOB_BASE__";  // GitHub blob root for source/spec deep links

// ---- Config ---------------------------------------------------------------
// Class nodes are coloured by ROLE (DGM-004); other kinds by kind.
const KIND_COLOR = {
  capability:'#F59E0B', method:'#10B981', package:'#A855F7',
  requirement:'#F43F5E', extra:'#94A3B8',
};
const ROLE_COLOR = {backend:'#3B82F6', abc:'#60A5FA', facade:'#6366F1'};
const KIND_R = {capability:14, class:13, method:10, package:15, requirement:8, extra:11};

// declares + contains are off by default: they dominate numerically and
// collapse the centre.  contains is still used structurally to cluster
// methods inside an *expanded* class and classes inside their package, even
// when its legend toggle is off (see computeActiveLinks).
const EDGE_CFG = {
  inherits:{color:'#A855F7',dash:'0',  width:2,   defaultOn:true},
  mirrors: {color:'#F59E0B',dash:'6,3',width:2,   defaultOn:true},
  enables: {color:'#10B981',dash:'4,3',width:1.5, defaultOn:true},
  gates:   {color:'#F43F5E',dash:'0',  width:1.5, defaultOn:true},
  of:      {color:'#64748B',dash:'2,2',width:1,   defaultOn:true},
  declares:{color:'#3B82F6',dash:'0',  width:1,   defaultOn:false},
  contains:{color:'#22D3EE',dash:'1,3',width:1,   defaultOn:false},
};
const ISO_EDGES = new Set(['inherits','contains','gates','of','mirrors']);

function isStoreFacade(n){return n.kind==='class'&&/\.(Async)?Store$/.test(n.id);}
function nodeColor(n){
  if(n.kind==='class') return ROLE_COLOR[n.role]||ROLE_COLOR.backend;
  return KIND_COLOR[n.kind]||'#888';
}
function nodeRadius(n){
  let r=KIND_R[n.kind]||10;
  if(isStoreFacade(n)) r+=3;
  return r;
}
function isAbstractNode(n){
  return n.is_abstract===true||(n.kind==='class'&&n.role==='abc');
}

// ---- Graph data -----------------------------------------------------------
const nodeMap = new Map(GRAPH.nodes.map(n=>[n.id,{...n}]));
const nodes   = [...nodeMap.values()];
const links   = GRAPH.edges
  .map(e=>({...e, source:nodeMap.get(e.src), target:nodeMap.get(e.dst)}))
  .filter(l=>l.source&&l.target);

// Containment maps (DGM-008: class --contains--> method).
const classOfMethod = new Map();
const methodsOfClass = new Map();
links.filter(l=>l.kind==='contains'&&l.source.kind==='class'&&l.target.kind==='method')
  .forEach(l=>{
    classOfMethod.set(l.target.id, l.source.id);
    if(!methodsOfClass.has(l.source.id)) methodsOfClass.set(l.source.id, []);
    methodsOfClass.get(l.source.id).push(l.target.id);
  });

// Gate-label disambiguation (DGM-008 contains direction): a requirement gates a
// method; the method's class disambiguates same-named gates across classes
// (Backend.copy vs Store.copy), and the .gate_depth suffix is marked "(depth)".
const reqLabel = new Map();
links.filter(l=>l.kind==='gates').forEach(l=>{
  const clsId=classOfMethod.get(l.target.id);
  const cls=clsId?clsId.split('.').pop():'';
  const mtd=l.target.id.split('.').pop();
  const suffix=l.source.id.endsWith('.gate_depth')?' (depth)':'';
  reqLabel.set(l.source.id, (cls?cls+'.':'')+mtd+suffix);
});

function nodeLabel(n){
  switch(n.kind){
    case 'capability': return n.value||n.id.split(':')[1];
    case 'class':
    case 'method':     return n.id.split('.').pop();
    case 'package':
    case 'extra':      return n.id.split(':')[1];
    case 'requirement':return reqLabel.get(n.id)||n.id.split('.').slice(-2).join('.');
    default:           return n.id;
  }
}
function nodeRuntime(n){
  if(n.runtime) return n.runtime;                  // class, package
  if(n.kind==='method') return n.is_async?'async':'sync';
  return null;                                      // capability/requirement/extra: agnostic
}

// ---- State ----------------------------------------------------------------
const visibleNodeKinds = new Set(['capability','class','method','package','requirement','extra']);
const visibleRoles     = new Set(['backend','abc','facade']);
const visibleEdgeKinds = new Set(Object.entries(EDGE_CFG).filter(([,v])=>v.defaultOn).map(([k])=>k));
const visibleRuntimes  = new Set(['sync','async']);
const selectedCaps     = new Set();   // capability facet; empty == no capability filter
const expandedClasses  = new Set();   // classes whose methods are revealed
let searchQuery = '';
let isolate = false;
let selected = null;                  // {type:'node', id} | {type:'edge', id:'src|kind|dst'}

// ---- Soft positional bias (keeps force organic but guided) ----------------
const X_BIAS = {package:0.08, extra:0.18, class:0.30, capability:0.52, requirement:0.68, method:0.84};
const Y_BIAS = {package:0.12};

// ---- SVG / simulation -----------------------------------------------------
const svg = d3.select('#graph');
const W0 = 1200, H0 = 800;
const simulation = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d=>d.id)
    .distance(d=>d.kind==='contains'?45:d.kind==='declares'?170:d.kind==='inherits'?65:100)
    .strength(d=>d.kind==='contains'?0.7:d.kind==='declares'?0.04:d.kind==='of'?0.5:0.4))
  .force('charge', d3.forceManyBody().strength(-620))
  .force('collide', d3.forceCollide().radius(d=>nodeRadius(d)+14))
  .force('xbias', d3.forceX(d=>(X_BIAS[d.kind]??0.5)*W0).strength(0.07))
  .force('ybias', d3.forceY(d=>(Y_BIAS[d.kind]??0.5)*H0).strength(0.04));

const defs = svg.append('defs');
Object.entries(EDGE_CFG).forEach(([kind,cfg])=>{
  defs.append('marker').attr('id','arrow-'+kind)
    .attr('viewBox','0 -5 10 10').attr('refX',22).attr('refY',0)
    .attr('markerWidth',5).attr('markerHeight',5).attr('orient','auto')
    .append('path').attr('d','M0,-5L10,0L0,5').attr('fill',cfg.color);
});
const g = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.1,4]).on('zoom', e=>g.attr('transform',e.transform));
svg.call(zoom);
svg.on('dblclick.zoom', null);  // free dblclick for expand/collapse on class nodes
document.getElementById('btn-reset').onclick =
  ()=>svg.transition().duration(500).call(zoom.transform,d3.zoomIdentity);
document.getElementById('btn-reheat').onclick =
  ()=>simulation.alpha(0.7).restart();

// ---- Sidebar controls -----------------------------------------------------
function countNodeKind(k){return GRAPH.nodes.filter(n=>n.kind===k).length;}

function buildControls(){
  const nl=d3.select('#node-legend');
  ['capability','class','method','package','requirement','extra'].forEach(kind=>{
    const row=nl.append('div').attr('class','legend-row');
    row.append('input').attr('type','checkbox').property('checked',true)
      .on('change',function(){this.checked?visibleNodeKinds.add(kind):visibleNodeKinds.delete(kind);update();});
    row.append('div').attr('class','dot').style('background',KIND_COLOR[kind]||ROLE_COLOR.backend);
    row.append('span').text(kind+' ('+countNodeKind(kind)+')');
  });

  const rl=d3.select('#role-legend');
  [['backend','backend'],['abc','abstract base (abc)'],['facade','facade']].forEach(([role,label])=>{
    const n=GRAPH.nodes.filter(x=>x.kind==='class'&&x.role===role).length;
    const row=rl.append('div').attr('class','legend-row');
    row.append('input').attr('type','checkbox').property('checked',true)
      .on('change',function(){this.checked?visibleRoles.add(role):visibleRoles.delete(role);update();});
    row.append('div').attr('class','dot'+(role==='abc'?' dashed':'')).style('background',ROLE_COLOR[role]);
    row.append('span').text(label+' ('+n+')');
  });

  const el=d3.select('#edge-legend');
  Object.entries(EDGE_CFG).forEach(([kind,cfg])=>{
    const on=cfg.defaultOn;
    const row=el.append('div').attr('class','legend-row'+(on?'':' dim'));
    row.append('input').attr('type','checkbox').property('checked',on)
      .on('change',function(){this.checked?visibleEdgeKinds.add(kind):visibleEdgeKinds.delete(kind);update();});
    row.append('div').attr('class','line-sample')
      .style('background', cfg.dash==='0'?cfg.color
        :`repeating-linear-gradient(90deg,${cfg.color} 0,${cfg.color} 4px,transparent 4px,transparent 7px)`)
      .style('height',cfg.width+'px');
    row.append('span').text(kind+(on?'':' — off')+' ('+GRAPH.edges.filter(e=>e.kind===kind).length+')');
  });

  const rt=d3.select('#runtime-legend');
  ['sync','async'].forEach(r=>{
    const row=rt.append('div').attr('class','legend-row');
    row.append('input').attr('type','checkbox').property('checked',true)
      .on('change',function(){this.checked?visibleRuntimes.add(r):visibleRuntimes.delete(r);update();});
    row.append('span').text(r);
  });

  const cl=d3.select('#cap-legend');
  GRAPH.nodes.filter(n=>n.kind==='capability').forEach(n=>{
    const row=cl.append('div').attr('class','legend-row');
    row.append('input').attr('type','checkbox').property('checked',false)
      .on('change',function(){this.checked?selectedCaps.add(n.id):selectedCaps.delete(n.id);update();});
    row.append('div').attr('class','dot').style('background',KIND_COLOR.capability);
    row.append('span').text(n.value||n.id.split(':')[1]);
  });

  document.getElementById('search').addEventListener('input',function(){
    searchQuery=this.value.trim().toLowerCase();update();
  });
  document.getElementById('iso-toggle').addEventListener('change',function(){
    isolate=this.checked;update();
  });
  document.getElementById('btn-expand-all').onclick=()=>{
    nodes.filter(n=>n.kind==='class').forEach(n=>expandedClasses.add(n.id));update();
  };
  document.getElementById('btn-collapse-all').onclick=()=>{
    expandedClasses.clear();update();
  };
}

// ---- Detail panel ---------------------------------------------------------
function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function docHref(doc){
  // docs-src/reference/api/store.md -> ../reference/api/store/ (use_directory_urls)
  return '../'+doc.replace(/^docs-src\//,'').replace(/\/index\.md$/,'/').replace(/\.md$/,'/');
}
function deepLinks(n){
  const out=[];
  if(n.file) out.push({label:'Source', href:BLOB_BASE+n.file+(n.line?('#L'+n.line):''),
                       text:n.file+(n.line?(':'+n.line):'')});
  const cls = n.kind==='class' ? n
            : (n.kind==='method' ? nodeMap.get(classOfMethod.get(n.id)) : null);
  if(cls&&cls.spec) out.push({label:'Spec', href:BLOB_BASE+cls.spec, text:cls.spec});
  if(cls&&cls.doc)  out.push({label:'Docs', href:docHref(cls.doc), text:cls.doc});
  return out;
}
function fieldRows(node){
  const skip=new Set(['id','kind','file','line','spec','doc','x','y','vx','vy','fx','fy','index']);
  return Object.entries(node).filter(([k,v])=>!skip.has(k)&&typeof v!=='object')
    .map(([k,v])=>`<div class="detail-row">${esc(k)}: <span>${esc(v)}</span></div>`).join('');
}
function showNodeDetail(node){
  const el=document.getElementById('detail');
  const links=deepLinks(node).map(l=>
    `<a href="${esc(l.href)}" target="_blank" rel="noopener">${esc(l.label)}: ${esc(l.text)}</a>`).join('');
  let btn='';
  if(node.kind==='class'){
    const ms=(methodsOfClass.get(node.id)||[]).length;
    if(ms) btn=`<button class="btn detail-btn" id="detail-toggle">`
      +`${expandedClasses.has(node.id)?'Collapse':'Expand'} ${ms} method${ms===1?'':'s'}</button>`;
  }
  el.innerHTML=`<div class="detail-id">${esc(node.id)}</div>`
    +`<div class="detail-row">kind: <span>${esc(node.kind)}</span></div>`
    +fieldRows(node)
    +(links?`<div class="links">${links}</div>`:'')
    +btn;
  const t=document.getElementById('detail-toggle');
  if(t) t.onclick=()=>{
    expandedClasses.has(node.id)?expandedClasses.delete(node.id):expandedClasses.add(node.id);
    update();showNodeDetail(node);
  };
}
function showEdgeDetail(l){
  const el=document.getElementById('detail');
  const xref=(id)=>`<span class="xref" data-id="${esc(id)}">${esc(nodeLabel(nodeMap.get(id)||{id}))}</span>`;
  let rows=`<div class="detail-row">${xref(l.src)} &rarr; ${xref(l.dst)}</div>`;
  if(l.condition) rows+=`<div class="detail-row">condition: <span>${esc(l.condition)}</span></div>`;
  if(l.capability_delta){
    const cd=l.capability_delta;
    rows+=`<div class="detail-row">async only: <span>${esc((cd.async_only||[]).join(', ')||'—')}</span></div>`;
    rows+=`<div class="detail-row">sync only: <span>${esc((cd.sync_only||[]).join(', ')||'—')}</span></div>`;
  }
  el.innerHTML=`<div class="detail-id">${esc(l.kind)} edge</div>`+rows;
}
function clearDetail(){
  document.getElementById('detail').innerHTML=
    '<span class="placeholder">Click a node or an edge to inspect it</span>';
}
// Cross-reference clicks in the edge panel select the endpoint node.
document.getElementById('detail').addEventListener('click',ev=>{
  const x=ev.target.closest('.xref');
  if(x&&x.dataset.id) selectNodeById(x.dataset.id);
});
function selectNodeById(id){
  const n=nodeMap.get(id);
  if(!n) return;
  if(n.kind==='method'){const c=classOfMethod.get(id); if(c) expandedClasses.add(c);}
  selected={type:'node', id};
  update();
  showNodeDetail(n);
}

// ---- Faceted filtering ----------------------------------------------------
// Capability facet: when capabilities are selected, keep only those caps and
// their gate/declare chains (req -> method -> class -> package, declaring
// backends, enabling extras).
function capabilityKeep(){
  if(selectedCaps.size===0) return null;
  const keep=new Set(selectedCaps);
  links.forEach(l=>{
    if(l.kind==='of'&&selectedCaps.has(l.target.id)) keep.add(l.source.id);       // requirement
    if(l.kind==='declares'&&selectedCaps.has(l.target.id)) keep.add(l.source.id); // backend
    if(l.kind==='enables'&&selectedCaps.has(l.target.id)) keep.add(l.source.id);  // extra
  });
  links.forEach(l=>{if(l.kind==='gates'&&keep.has(l.source.id)) keep.add(l.target.id);}); // gated methods
  links.forEach(l=>{if(l.kind==='contains'&&keep.has(l.target.id)) keep.add(l.source.id);}); // class, package
  return keep;
}
function nodePassesFacets(n, capKeep){
  if(!visibleNodeKinds.has(n.kind)) return false;
  if(n.kind==='class'&&!visibleRoles.has(n.role)) return false;
  const rt=nodeRuntime(n);
  if(rt&&!visibleRuntimes.has(rt)) return false;
  if(capKeep&&!capKeep.has(n.id)) return false;
  if(n.kind==='method'){
    const c=classOfMethod.get(n.id);
    if(!c||!expandedClasses.has(c)) return false;   // collapsed into class by default
  }
  if(searchQuery){
    const hay=(n.id+' '+(n.summary||'')+' '+nodeLabel(n)).toLowerCase();
    if(!hay.includes(searchQuery)) return false;
  }
  return true;
}
function computeActiveNodes(){
  // Isolating a class reveals its methods first: they are collapsed (off-canvas)
  // by default, so without this the cone of a collapsed class could never
  // include the methods its comment promises. Expanding it also makes the
  // cluster links consistent and flips its detail-panel toggle to "Collapse".
  if(isolate&&selected&&selected.type==='node'){
    const sel=nodeMap.get(selected.id);
    if(sel&&sel.kind==='class') expandedClasses.add(selected.id);
  }
  const capKeep=capabilityKeep();
  let active=nodes.filter(n=>nodePassesFacets(n,capKeep));
  if(isolate&&selected&&selected.type==='node'){
    const activeIds=new Set(active.map(n=>n.id));
    if(activeIds.has(selected.id)){
      // Directed dependency cone: descendants (follow edges out) plus ancestors
      // (follow edges in). An *undirected* transitive walk leaks through shared
      // capability nodes and selects almost everything; the directed up/down
      // cone stays bounded and meaningful (a class -> its methods + subclasses).
      const walk=(forward)=>{
        const seen=new Set([selected.id]);
        let frontier=[selected.id], guard=0;
        while(frontier.length&&guard++<60){
          const fset=new Set(frontier), next=[];
          links.forEach(l=>{
            if(!ISO_EDGES.has(l.kind)) return;
            const from=forward?l.source.id:l.target.id, to=forward?l.target.id:l.source.id;
            if(fset.has(from)&&activeIds.has(to)&&!seen.has(to)){seen.add(to);next.push(to);}
          });
          frontier=next;
        }
        return seen;
      };
      const nb=new Set([...walk(true),...walk(false)]);
      active=active.filter(n=>nb.has(n.id));
    }
  }
  return active;
}
function computeActiveLinks(activeIds){
  return links.filter(l=>{
    if(!activeIds.has(l.source.id)||!activeIds.has(l.target.id)) return false;
    if(visibleEdgeKinds.has(l.kind)) return true;
    if(l.kind==='contains'){                                   // structural clustering
      if(l.source.kind==='package') return true;               // classes inside package
      if(l.source.kind==='class'&&expandedClasses.has(l.source.id)) return true; // methods inside class
    }
    return false;
  });
}

// ---- Rendering ------------------------------------------------------------
let linkSel, nodeSel;

function update(){
  const activeNodes=computeActiveNodes();
  const activeIds=new Set(activeNodes.map(n=>n.id));
  const activeLinks=computeActiveLinks(activeIds);

  linkSel=g.selectAll('.link')
    .data(activeLinks,d=>d.src+'|'+d.kind+'|'+d.dst)
    .join(enter=>enter.append('line').attr('class','link')
        .on('click',(ev,d)=>{
          ev.stopPropagation();
          const key=d.src+'|'+d.kind+'|'+d.dst;
          selected = selected&&selected.type==='edge'&&selected.id===key ? null : {type:'edge',id:key};
          selected?showEdgeDetail(d):clearDetail();
          applySelection();
        }),
      u=>u, exit=>exit.remove())
    .attr('stroke',d=>EDGE_CFG[d.kind]?.color||'#666')
    .attr('stroke-width',d=>EDGE_CFG[d.kind]?.width||1.2)
    .attr('stroke-dasharray',d=>EDGE_CFG[d.kind]?.dash||'0')
    .attr('marker-end',d=>`url(#arrow-${d.kind})`);

  nodeSel=g.selectAll('.node').data(activeNodes,d=>d.id)
    .join(
      enter=>{
        const ng=enter.append('g').attr('class','node')
          .call(d3.drag()
            .on('start',(ev,d)=>{if(!ev.active)simulation.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;})
            .on('drag',(ev,d)=>{d.fx=ev.x;d.fy=ev.y;})
            .on('end',(ev,d)=>{if(!ev.active)simulation.alphaTarget(0);d.fx=null;d.fy=null;}))
          .on('click',(ev,d)=>{
            ev.stopPropagation();
            selected = selected&&selected.type==='node'&&selected.id===d.id ? null : {type:'node',id:d.id};
            selected?showNodeDetail(d):clearDetail();
            applySelection();
          })
          .on('dblclick',(ev,d)=>{
            ev.stopPropagation();
            if(d.kind!=='class'||!(methodsOfClass.get(d.id)||[]).length) return;
            expandedClasses.has(d.id)?expandedClasses.delete(d.id):expandedClasses.add(d.id);
            update();
          });
        ng.append('circle');
        ng.append('text').attr('class','label').attr('dy','0.35em').attr('text-anchor','middle');
        ng.append('text').attr('class','sub-badge').attr('text-anchor','middle');
        ng.append('text').attr('class','count-badge').attr('text-anchor','middle');
        return ng;
      },
      u=>u, exit=>exit.remove());

  nodeSel.select('circle')
    .attr('r',d=>nodeRadius(d))
    .attr('fill',d=>nodeColor(d))
    .attr('stroke',d=>d3.color(nodeColor(d)).brighter(0.8));
  nodeSel.classed('abstract',d=>isAbstractNode(d))
         .classed('store',d=>isStoreFacade(d));
  nodeSel.select('text.label')
    .text(d=>nodeLabel(d))
    .attr('dy',d=>nodeRadius(d)+12);
  nodeSel.select('text.sub-badge')
    .text(d=>d.kind==='method'&&d.is_async===true?'async':'')
    .attr('dy',d=>nodeRadius(d)+21);
  nodeSel.select('text.count-badge')
    .text(d=>{
      if(d.kind!=='class') return '';
      const ms=(methodsOfClass.get(d.id)||[]).length;
      return ms&&!expandedClasses.has(d.id)?('+'+ms):'';
    })
    .attr('dy','-0.7em').attr('dx',d=>nodeRadius(d)-2);

  simulation.nodes(activeNodes);
  simulation.force('link').links(activeLinks);
  simulation.alpha(0.4).restart();
  applySelection();
}

simulation.on('tick',()=>{
  linkSel?.each(function(d){
    const sx=d.source.x,sy=d.source.y,tx=d.target.x,ty=d.target.y;
    const dx=tx-sx,dy=ty-sy,dist=Math.sqrt(dx*dx+dy*dy);
    const r=nodeRadius(d.target)+3;
    const f=dist>r?(dist-r)/dist:0;
    d3.select(this).attr('x1',sx).attr('y1',sy).attr('x2',sx+dx*f).attr('y2',sy+dy*f);
  });
  nodeSel?.attr('transform',d=>`translate(${d.x},${d.y})`);
});

function applySelection(){
  nodeSel?.classed('selected',d=>selected?.type==='node'&&d.id===selected.id);
  if(!selected){nodeSel?.classed('faded',false);linkSel?.classed('faded',false);linkSel?.classed('selected-edge',false);return;}
  if(selected.type==='node'){
    const nb=new Set([selected.id]);
    linkSel?.each(d=>{if(d.source.id===selected.id||d.target.id===selected.id){nb.add(d.source.id);nb.add(d.target.id);}});
    nodeSel?.classed('faded',d=>!nb.has(d.id));
    linkSel?.classed('faded',d=>d.source.id!==selected.id&&d.target.id!==selected.id);
    linkSel?.classed('selected-edge',false);
  } else {
    const [s,k,t]=selected.id.split('|');
    const nb=new Set([s,t]);
    nodeSel?.classed('faded',d=>!nb.has(d.id));
    linkSel?.classed('faded',d=>!(d.src===s&&d.kind===k&&d.dst===t));
    linkSel?.classed('selected-edge',d=>d.src===s&&d.kind===k&&d.dst===t);
  }
}
svg.on('click',()=>{selected=null;clearDetail();applySelection();});

buildControls();
update();

// Reparent RTD's EthicalAds injection into the sidebar so it does not float
// over the canvas.  RTD appends a div[data-ea-publisher] to <body>; we move it
// into #sidebar and strip the 'raised' float class.
(function(){
  var sb=document.getElementById('sidebar');
  var obs;
  function adopt(n){
    if(n.nodeType!==1||!n.dataset||!n.dataset.eaPublisher)return;
    n.classList.remove('raised');
    n.style.marginTop='';
    sb.appendChild(n);
    if(obs)obs.disconnect();
  }
  obs=new MutationObserver(function(ms){ms.forEach(function(m){m.addedNodes.forEach(adopt);});});
  obs.observe(document.body,{childList:true});
  document.querySelectorAll('body>[data-ea-publisher]').forEach(adopt);
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


_TOKENS = (
    "__VERSION__",
    "__SCHEMA_VERSION__",
    "__N_NODES__",
    "__N_EDGES__",
    "__BLOB_BASE__",
    "__GRAPH_DATA__",
)
_TOKEN_RE = re.compile("|".join(re.escape(t) for t in _TOKENS))


def _repo_blob_base() -> str:
    """GitHub blob root for deep links, single-sourced from pyproject [project.urls].

    Reads ``Repository`` rather than hardcoding the URL in the generator
    (principle 4: single source of truth). Source (``src/``) and spec (``sdd/``)
    files are not served on the docs site, so the detail panel deep-links them to
    GitHub; docs pages stay site-relative.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    repo = data.get("project", {}).get("urls", {}).get("Repository", "").rstrip("/")
    if not repo:
        raise RuntimeError("pyproject [project.urls].Repository is required for graph_viz deep links")
    return repo + "/blob/master/"


def generate(graph: dict) -> str:
    # The template references D3 via a relative <script src> to the sibling
    # vendored copy (ID-224); assert it is present so a missing vendor file fails
    # generation rather than silently producing a broken page.
    if not D3_VENDOR.exists():
        raise FileNotFoundError(f"{D3_VENDOR.name} not found — it should be committed to the repo.")
    graph_data = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    replacements = {
        "__VERSION__": graph.get("source_version", ""),
        "__SCHEMA_VERSION__": graph.get("schema_version", ""),
        "__N_NODES__": str(len(graph.get("nodes", []))),
        "__N_EDGES__": str(len(graph.get("edges", []))),
        "__BLOB_BASE__": _repo_blob_base(),
        "__GRAPH_DATA__": graph_data,
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
