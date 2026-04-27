# RFC-0012: Documentation Graph Model

## Status

Accepted

## Summary

Define a machine-readable intermediate representation (IR) for the remote-store
API surface: a typed graph of nodes and edges derived from source code via static
analysis, serialized as JSON, and projected to multiple documentation outputs
(FEATURES.md capability matrix, per-class API reference stubs, extras index).
The graph is the single source of truth for any derived doc artefact; FEATURES.md
becomes a projection of it rather than a hand-maintained file. Versioned snapshots
replace in-node `since:` / `deprecated_in:` tracking.

## Motivation

Two documentation surfaces share the same drift problem:

**`FEATURES.md`** (ID-159) is a hand-maintained capabilities snapshot. The
capability matrix, method list, and extras table are all mechanically derivable
from source.

**The API reference** (`docs/api/store/`, `docs/api/aio/`, per-backend pages)
has the same issue: method tables, capability gates, and backend-conditional
parameter admonitions are written by hand against the source and drift silently
as the API evolves.

Both surfaces expose the same cross-cutting relationships — which capability
gates which method, which extra enables which backend — but currently each is
authored independently with no shared extraction logic.

Without a shared IR:

- `FEATURES.md`, the API reference, and the extras index each duplicate the
  same traversal logic.
- Cross-cutting relationships — `cap:WRITE` gates `Store.write`,
  `xtr:s3` enables `S3Backend` — are not queryable; they live in prose.
- Diff between releases requires diffing prose documents, not structured data.

This RFC defines the graph IR. Implementation (the loader, projection scripts,
and release-skill integration) is tracked under ID-159.

## Goals

- One typed graph; all derived doc artefacts are projections of it.
- The graph is queryable in plain Python; no SPARQL, no property-graph DB.
- Cross-cutting edges (`capability → method`, `extra → backend`,
  `sync ↔ async mirror`) are first-class, not buried in prose.
- Versioned snapshots replace `since:` tracking; git-diff two snapshots to
  produce a changelog.
- JSON serialization is byte-stable across regenerations of the same source
  tree (suitable for `git diff`).
- The graph accommodates conditional capabilities (ID-140: per-instance,
  dialect-conditional capabilities) without a schema change.

## Non-goals

- Generating narrative prose. Curated sections of FEATURES.md remain
  hand-maintained (region-tagged).
- Replacing the mkdocstrings HTML renderer. The API reference is still
  rendered by mkdocstrings; the graph produces structured stubs and
  admonition metadata, not raw HTML.
- Storing type-inference results. Types are recorded as opaque `TypeRef`
  node labels, not inferred by a type checker.
- Querying across multiple versions. The consumer loads two snapshots and
  diffs them; the IR itself is single-version.

---

## Proposal

### The graph: two collections

The IR is two sorted arrays: `nodes` and `edges`. Everything is
addressable by a stable URI string. No separate adjacency structure — queries
iterate the arrays.

```json
{
  "schema_version": "1.0",
  "source_version": "0.24.0",
  "snapshot": "0.24.0",
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

`schema_version` and `source_version` are independent fields. A schema bump
(new node kinds, renamed edge kinds) increments `schema_version`; a new package
release increments `source_version`. `snapshot` mirrors `source_version` (both
track `pyproject.toml[project][version]`).

---

### Promote-to-node rule

If a value is referenced from more than one node, or a natural query is "which
X have property Y", it is a node. Closed enumerations that only describe their
parent (booleans, `sync/async`, `abc/backend/facade`) stay as properties.

---

### Node taxonomy

| Kind | URI prefix | Key properties | Role property |
|---|---|---|---|
| `package` | `pkg:` | `runtime` (`sync`/`async`), `version` | — |
| `module` | `mod:` | `file` | — |
| `class` | `cls:` | `role`, `runtime`, `file`, `line`, `summary` | `abc` · `backend` · `facade` · `extension` · `data` · `enum` · `error` · `helper` |
| `method` | `mtd:` | `summary`, `is_abstract`, `is_async`, `file`, `line` | — |
| `capability` | `cap:` | `summary`, `semantics` | — |
| `data_model` | `dm:` | `frozen`, `summary` | — |
| `field` | `fld:` | `default`, `summary` | — |
| `error` | `err:` | `when_raised`, `summary` | — |
| `extra` | `xtr:` | `kind` (`backend`/`extension`/`aggregate`) | — |
| `package_dep` | `dep:` | `min_version` | — |
| `parameter` | `prm:` | `has_default`, `summary` | — |
| `type_ref` | `typ:` | `label` (opaque string) | — |
| `predicate` | `prd:` | `label` (opaque string, e.g. `"dialect == 'sqlite'"`) | — |
| `requirement` | `req:` | `mode` (`all`/`any`, default `all`) | — |
| `role` | `rol:` | `label` (`source`/`dest`/`self`) | — |

`predicate` carries the condition for a conditional `declares` or `raises` edge
as an opaque label. The IR records it; the semantic interpretation belongs to
the code. This covers ID-140 (dialect-conditional capabilities) without a schema
change.

`requirement` is an explicit AND/OR group between a method and its capability
gate(s). All current methods use `mode: all` with a single capability; the
node exists so the schema does not change when a method needs a conjunction or
disjunction.

---

### Edge taxonomy

| Kind | Domain → Range | Attributes | Notes |
|---|---|---|---|
| `contains` | package/module/class → child | — | Containment tree |
| `inherits` | class → class | — | DAG |
| `declares` | backend → capability | `condition: prd URI \| null` | `null` for unconditional |
| `gates` | requirement → method | — | Via `req:` group |
| `of` | requirement → capability | `index: int` | Members of the group |
| `enables` | extra → class/extension | — | pip extra → backend |
| `requires_dep` | extra → package_dep | — | pip dependency |
| `mirrors` | class → class | — | Canonical direction: async → sync peer (one edge per pair; deduped by generator) |
| `composes` | extension → class | — | The Store/Backend it wraps |
| `requires_cap` | extension/role → capability | — | Capability needed by ext/role |
| `played_by` | extension → role | — | Extension has this role on the edge |
| `returns` | method → data_model | — | — |
| `accepts` | method → data_model | `param: str` | — |
| `has_param` | method → parameter | `position: int` | — |
| `typed` | parameter/field → type_ref | — | — |
| `has_field` | data_model → field | — | — |
| `raises` | method → error | `condition: prd URI \| null` | — |

`gates` and `of` together replace a simple "method requires capability" attribute.
A method with one unconditional gate has one `req:` node linked by a single
`of` edge to the capability, and one `gates` edge from that `req:` to the method.
When a second capability is added, a second `of` edge joins the same `req:` node —
no schema change.

---

### Diagram

```mermaid
graph LR
  xtr -- enables --> cls_backend
  cls_backend -. mirrors .- cls_async
  cls_backend -- declares --> cap
  cap <-- of -- req -- gates --> mtd
  mtd -- returns --> dm
  dm -- has_field --> fld
  fld -- typed --> typ
  mtd -- has_param --> prm
  prm -- typed --> typ
  mtd -- raises --> err
  ext -- composes --> cls_backend
  ext -- played_by --> rol
  rol -- requires_cap --> cap
  xtr -- requires_dep --> dep
```

---

### Worked example: S3Backend neighborhood

One-hop walk from `cls:remote_store.backends._s3.S3Backend`:

```
cls:...S3Backend
  ← enables          xtr:s3
  → inherits         cls:remote_store._backend.Backend
  → declares (×13)   cap:READ, cap:WRITE, cap:DELETE, cap:LIST, cap:GLOB,
                     cap:MOVE, cap:COPY, cap:ATOMIC_WRITE, cap:METADATA,
                     cap:USER_METADATA, cap:SEEKABLE_READ, cap:LAZY_READ,
                     cap:WRITE_RESULT_NATIVE
                     (all condition: null)
  ↔ mirrors          (no async S3 backend exists yet; edge applies once one is added)

mtd:remote_store.Store.write
  ← gates    req:Store.write.gate
  req:Store.write.gate
  → of       cap:WRITE
  mtd:Store.write → returns → dm:remote_store.WriteResult
  dm:WriteResult → has_field → fld:WriteResult.etag → typed → typ:str|None
```

The FEATURES.md capability matrix is a two-hop walk:

```python
def matrix(g):
    return {
        b: {c: [m for m in methods_gated_by(g, c)]
            for c in capabilities_declared_by(g, b)}
        for b in g.nodes(kind="class", role="backend")
    }
```

---

### Snapshots

One rolling file tracks the current development state. `source_version` and
`snapshot` are both set to the `pyproject.toml` `[project][version]` at
generation time; `gen_graph.py` reads this dynamically so no manual update is
needed.

| File | `source_version` | `snapshot` |
|---|---|---|
| `docs-src/_data/graph/graph.json` | current pyproject version | current pyproject version |

Files live in `docs-src/_data/graph/` (git-tracked; mkdocs copies the
directory verbatim).

**Release-time flow (Phase 2):** after `bump-my-version` stamps the new version
into `pyproject.toml`, run `hatch run gen-graph` to re-stamp `graph.json` with
the release version before committing. The git tag then freezes the file;
`source_version` is self-describing for consumers without git context.

**Consumer note:** between releases `graph.json` reflects the pyproject version
at the last commit that touched it, not necessarily the in-progress dev state.
Use git history or `git tag` to identify the exact released snapshot.

**Determinism:** the serializer must produce byte-identical output for the same
source tree. Rules:

- `nodes` sorted ascending by `id` URI.
- `edges` sorted ascending by `(kind, src, dst)`.
- Object keys sorted (JSON `sort_keys=True`).
- LF line endings, no trailing whitespace, 2-space indent.
- One golden test: generate twice, assert the files are identical.

---

### Projection design

Three layers between source and rendered Markdown:

```
src/  ─ Loader ─► IR (graph.json)  ─ Projection ─► View  ─ Jinja ─► Markdown
                                     (pure Python)
```

One projection function per output; all query logic lives in Python, not Jinja:

| Output | Projection input | Primary walk |
|---|---|---|
| `FEATURES.md` capability matrix | All backend nodes | `backend → declares → cap → gates → method` |
| Per-backend reference page | One backend node | `backend → declares`, `mirrors`, `enables` |
| Capability × method table | All capability nodes | `cap ← of ← req ← gates ← method` |
| Extras index | All extra nodes | `extra → enables → backend`, `extra → requires_dep` |

The projection returns plain Python dataclasses (view objects); templates render
only. This makes the test surface trivial: snapshot the projection output, not
the rendered Markdown.

---

### Schema evolution

Older snapshots are frozen at their `schema_version`. The chosen strategy is
**read-only legacy**: loaders support the lowest common subset across known
schema versions; projections degrade gracefully when a node kind or edge kind
is absent. Forklift-upgrade (re-running the generator against every historical
tag) is deferred until a second schema version is actually needed.

---

### Tooling appendix

This section is informational; implementation decisions belong to ID-159.

**Loader.** Griffe is already loaded by mkdocstrings (configured in
`mkdocs.yml`). The graph generator reuses Griffe's parse via a Griffe
Extension that fires on `on_class_instance` to populate `declares` edges from
each backend's `capabilities` property, and on `on_module` to collect extras
from `pyproject.toml`. Griffe is not the IR; it is the parse layer.

**Extras → backend mapping.** The mapping is a two-source join:

1. `src/remote_store/backends/__init__.py` — each `try/except ImportError` block
   names the backend class and, implicitly, the package whose absence causes the
   failure (e.g. `from remote_store.backends._s3 import S3Backend` fails when
   `s3fs` is absent).
2. `pyproject.toml` `[project.optional-dependencies]` — maps each pip extra name
   to the packages it installs.

The generator joins the two by package name: "which extra installs the package
that `backends/__init__.py` needs for this class?" This requires no
hand-maintained table and stays correct as new backends are added, as long as
both sources are consulted.

**Static capability extraction.** Today capabilities are declared as
module-level `CapabilitySet` constants and exposed via a `capabilities`
property. The lightest annotation that makes them statically extractable without
running the code is a `ClassVar` annotation directly on the subclass:

```python
CAPABILITIES: ClassVar[CapabilitySet] = CapabilitySet({...})
```

This is the recommended precondition for ID-159. It is a small, non-breaking
refactor of each backend.

**Gating table.** Today, capability gating in `_store.py` is done via inline
`.require()` calls scattered across each method (see References). The recommended
precondition for ID-159 is to consolidate these into a central `_GATING` dict
mapping method names to `Capability` values — making it both the runtime check
source and the static extraction target for `gates` edges. This is the same
category of precondition as `CAPABILITIES: ClassVar` on backends.

## Alternatives Considered

### Griffe tree as IR

Griffe's object tree is containment-only. Cross-cutting edges (capability gates
method, extra enables backend, sync mirrors async) have no natural home.
Griffe's `extra` dict can carry annotations per node, but it cannot represent
edges between nodes. The proposed graph is loaded *from* Griffe, not *as*
Griffe.

### RDF / property-graph database

No SPARQL queries are needed. All queries are simple array iterations in
Python. RDF does not survive `git diff` as cleanly as JSON. Rejected.

### `docspec` (Pydoc-Markdown's IR)

A published Python API IR format. Griffe is already in the dependency set
(via mkdocstrings); adding docspec would be a second parse layer for no gain.
Rejected.

### Versioning as a graph axis (`since:` / `deprecated_in:` on edges)

Adding version fields to every edge grows the schema and the serialization
cost. Per-file snapshots give the same information for free via git diff: a
node present in `graph-0.24.0.json` and absent in `graph-0.23.0.json` was
added in 0.24.0. Rejected.

### Single rolling file (no per-version snapshots)

**Adopted (ID-163).** The original proposal kept per-version archive files
(`graph-X.Y.Z.json`) alongside the rolling file. During implementation the
archive step was dropped in favour of simplicity: `graph.json` is always
stamped with the current `pyproject.toml` version; the git tag is the
immutable record of the released state. Diffing two releases means checking out
the two tags and comparing `graph.json`. This trades the convenience of
in-tree snapshot artefacts for a smaller file surface and a simpler release
sequence.

## Impact

- **Public API:** none. This RFC defines a build-time artefact, not a runtime
  surface.
- **Backwards compatibility:** not applicable.
- **Performance:** graph generation is a build-time step, not a hot path.
  The JSON file for the current backend surface is expected to be under 1 MB.
- **Testing:** one golden test (byte-stable round-trip); snapshot tests for
  each projection function. No runtime tests.
- **Ripple-check:** this RFC is design-only. The implementation PR for ID-159
  will touch backends (adding `CAPABILITIES: ClassVar`), `_store.py` (adding
  `_GATING` table), `docs-src/_data/graph/`, `scripts/`, the release skill,
  and `FEATURES.md`.

## Open Questions

**Sync↔async peer discovery for `mirrors` edges.** Resolved by ID-159: each
async backend carries a ``__mirror__: ClassVar[type[T]]`` annotation pointing
to its sync peer.  The generator emits one directed edge per pair in the
canonical async → sync direction (deduped).  Consumers that need to query from
the sync side must reverse the edge themselves.

## References

- ID-159 (`FEATURES.md` hybrid generation): `sdd/BACKLOG.md`
- ID-140 (dialect-conditional capabilities): `sdd/BACKLOG.md`
- Backend capabilities: `src/remote_store/backends/_local.py:26`,
  `_s3.py:37`, `_sftp.py:47`, `_azure.py:47`, `_sqlalchemy.py:47`,
  `_http.py:41`
- Capability gating in Store: `src/remote_store/_store.py:68,87,118,189`
- Capability enum: `src/remote_store/_capabilities.py`
- mkdocs + mkdocstrings config: `mkdocs.yml`
- Existing gen-files script: `scripts/gen_pages.py`
- Extension architecture: `sdd/adrs/0008-extension-architecture.md`
- Backend adapter contract: `sdd/specs/003-backend-adapter-contract.md`
