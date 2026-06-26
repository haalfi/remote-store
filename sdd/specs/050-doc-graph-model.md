# Spec 050 — Documentation Graph Model

**Scope:** Build & CI tooling. Specifies the concrete obligations the graph
generator must satisfy when emitting `docs-src/_data/graph/graph.json` at
`schema_version` 1.4. Not library source code; the contracts here govern
`scripts/gen_graph.py`, `scripts/gen_graph_viz.py`, and their golden tests
in `tests/scripts/`.

**Prefix:** `DGM`

**Author-facing surface:** [RFC-0012](../rfcs/rfc-0012-doc-graph-model.md) is the
accepted design — the node/edge taxonomy, the promote-to-node rule, the
determinism rules, and the projection design are normative there. This spec does
not restate the taxonomy; it pins which slice of it the generator emits at 1.4,
the deviations the implementation takes from the RFC's idealized shape, and the
test/CI contract that guards the artifact. Where this spec and the RFC disagree
on what the *generator emits*, this spec wins; where they disagree on the *model*,
the RFC wins and this spec is wrong (principle 5).

**Related decisions:** [ADR-0008](../adrs/0008-extension-architecture.md)
(extension architecture, the source of the `composes`/`played_by`/`requires_cap`
edges deferred below). [ID-224](../BACKLOG-DONE.md) introduced the
omit-when-null convention now formalized in DGM-010.

**Tracks:** [ID-221](../BACKLOG-DONE.md) (foundation: schema 1.3) and
[ID-222](../BACKLOG-DONE.md) (mechanical FEATURES.md projection, which drove the
1.4 ungated-method-node addition, DGM-014). [ID-223](../BACKLOG-DONE.md)
(role-aware visualization) also consumes the corrected graph and the link
metadata defined here — `gen_graph_viz.py` reads the roles, `contains` edges,
and `spec`/`doc` links at 1.4 with no schema change.

---

## DGM-001: Artifact Shape and Schema Version

**Invariant:** The generator emits a single JSON object with exactly these
top-level keys: `schema_version`, `source_version`, `snapshot`, `nodes`, `edges`.
At this spec's revision `schema_version` is `"1.4"`. `source_version` and
`snapshot` both equal `pyproject.toml[project][version]`, read dynamically.

**Rationale:** RFC-0012 "The graph: two collections" and "Snapshots". The 1.4
bump over 1.3 is one additive change: ungated facade method nodes carrying a
`gated` field (DGM-014), added so ID-222 can derive the Store "always available"
table. The 1.3 bump over 1.2 covered three additive changes: the `abc` and
`facade` class roles (DGM-004), the `contains` edge kind (DGM-008), and the
`spec`/`doc` link-metadata fields on class nodes (DGM-009).

**See also:** DGM-013 for the `schema_version` consumers that ripple on a bump.

---

## DGM-002: In-Scope vs Deferred Node Kinds

**Invariant:** At 1.4 the generator emits exactly these node kinds:

| Kind | Emitted for |
|---|---|
| `package` | `pkg:remote_store` (sync), `pkg:remote_store.aio` (async) |
| `class` | ABCs, concrete backends, and facades (DGM-004) |
| `method` | gated methods of `Store`/`AsyncStore`/`Backend`/`AsyncBackend` (from the `_GATING` / `_BACKEND_GATING` / `_ASYNC_BACKEND_GATING` maps), plus the ungated public methods of the `Store`/`AsyncStore` facades (DGM-014) |
| `capability` | every member of the `Capability` enum |
| `requirement` | one `req:` group per gated method, plus the `get_folder_info` depth gate |
| `extra` | every pip extra that enables a backend node |

**Invariant:** These RFC node kinds are **deferred** — the generator MUST NOT emit
them at 1.3: `module`, `data_model`, `field`, `error`, `parameter`, `type_ref`,
`predicate`, `package_dep`, `role`. They have no consumer yet; emitting them would
inflate the golden diff (principle: keep 1.3 compact, DGM-010). When a consumer
needs one (e.g. ID-222 may need `data_model` for the return-type column), it is
added under its own schema bump.

**Rationale:** RFC-0012 "Node taxonomy" defines the full set; the promote-to-node
rule says a value becomes a node only when referenced from more than one node or
queried directly. No 1.3 consumer queries the deferred kinds.

---

## DGM-003: In-Scope vs Deferred Edge Kinds

**Invariant:** At 1.3 the generator emits exactly these edge kinds: `contains`
(DGM-008), `inherits` (DGM-005), `declares` (DGM-006), `gates`, `of`, `enables`,
`mirrors`. All other RFC edge kinds are **deferred** and MUST NOT be emitted:
`composes`, `requires_cap`, `played_by`, `returns`, `accepts`, `has_param`,
`typed`, `has_field`, `raises`, `requires_dep`.

**Rationale:** RFC-0012 "Edge taxonomy". The deferred edges describe the
data-model, extension-role, and error surfaces, none of which has a 1.3 consumer.

---

## DGM-004: Class Role Taxonomy

**Invariant:** Every `class` node carries a `role` property drawn from
`abc · backend · facade`. Assignment is exhaustive and mutually exclusive:

- **`abc`** — the `Backend` and `AsyncBackend` abstract base classes. Detected as
  a class named `Backend`/`AsyncBackend` whose **runtime** `CAPABILITIES` attribute
  is `None` (the ABCs carry a `CAPABILITIES: ClassVar` *annotation* with no value,
  so a Griffe member-name check alone misclassifies them as backends; the
  generator MUST resolve the value, not the annotation).
- **`backend`** — a concrete backend: a class whose runtime `CAPABILITIES` is a
  non-`None` `CapabilitySet` and which is not a facade.
- **`facade`** — a class that presents a `Store`/`Backend`-shaped surface but
  delegates rather than implementing storage: `Store`, `AsyncStore` (DGM-007),
  and `SyncBackendAdapter` (DGM-006).

**Postcondition:** `role="backend"` selects only concrete storage backends — no
ABCs, no facades. This is the precondition ID-222 relies on for its backend
capability table.

**Rationale:** RFC-0012 "Node taxonomy" lists `abc`/`backend`/`facade` among the
class roles. 1.2 emitted neither `abc` nor `facade`; every class node was
`backend`, so the two ABCs and the adapter misrepresented the API.

---

## DGM-005: `inherits` via MRO to the Nearest In-Graph Ancestor

**Invariant:** For each class node the generator walks the class's method
resolution order (`inspect.getmro`) and emits a single `inherits` edge to the
**nearest** ancestor that is itself a node in the graph. Classes whose MRO
reaches `Backend`/`AsyncBackend` only through a private intermediate base (which
is not a node) still emit an edge to the ABC.

**Postcondition:** `S3Backend` and `S3PyArrowBackend` (via `_S3Base`), and
`SQLBlobBackend` and `SQLQueryBackend` (via `_SQLAlchemyBaseBackend`), each emit
`inherits → cls:…Backend`. `SQLQueryBackend`'s confirmed MRO target is
`Backend` (its only in-graph ancestor is the sync `Backend` ABC, reached through
`_SQLAlchemyBaseBackend`). A class with no in-graph ancestor (e.g. the `Backend`
ABC itself) emits no `inherits` edge.

**Rationale:** 1.2 inspected only direct `__bases__`, so backends behind a
private base had no path to `Backend`. Async backends inherit `AsyncBackend`
directly; the MRO walk is a strict superset of the `__bases__` check and yields
the identical edge for them, so they need no special-casing — one code path
serves both.

---

## DGM-006: Facade `declares` Suppression (`SyncBackendAdapter`)

**Invariant:** `SyncBackendAdapter` is a `facade` (DGM-004), not a backend. The
generator MUST NOT emit `declares` edges from any `facade`-role class, even when
the class exposes a runtime `CAPABILITIES` set.

**Mechanism:** Suppression is driven off `role`, not a per-node or per-edge flag.
The generator skips `declares` emission for any class whose resolved role is
`facade`. There is no `is_passthrough`/`is_facade` boolean field on the node: such
a field would be exactly derivable from `role`, and DGM-010 forbids derivable
keys.

**Rationale:** `SyncBackendAdapter.CAPABILITIES` is the universal set (it claims
every capability because it forwards to whatever sync backend it wraps). Treating
that as 14 first-class `declares` edges made the adapter look like a backend that
natively supports everything. Its capabilities are a property of the wrapped
backend, discoverable at runtime, not a static declaration.

---

## DGM-007: `Store` and `AsyncStore` Facade Nodes

**Invariant:** The generator emits a `class` node with `role="facade"` for
`Store` (`cls:remote_store._store.Store`) and `AsyncStore`
(`cls:remote_store.aio._async_store.AsyncStore`).

**Postcondition:** Every `method` node whose URI is `mtd:<class-path>.<name>`
has its containing `class` node present, so no method node is orphaned. Before
1.3 the `Store`/`AsyncStore` method nodes existed with no class node to contain
them (DGM-008).

**Rationale:** The `Store` method nodes were emitted from the `_GATING` table
with no corresponding class node. ID-223 distinguishes `Store` from other facades
by URI label, not role, so both keep `role="facade"`.

---

## DGM-008: `contains` Edges

**Invariant:** The generator emits `contains` edges along the containment tree:

- **package → class** (Fix F): `pkg:remote_store` contains every sync-runtime
  class node; `pkg:remote_store.aio` contains every async-runtime class node.
  Runtime is determined as in RFC-0012 (`.aio.` in the class path ⇒ async).
- **class → method** (Fix E): a class node contains every method node whose URI
  is `mtd:<that class's path>.<name>`. The containing class is resolved by
  stripping the trailing `.<name>` from the method URI and matching the
  corresponding `cls:` node; if no such class node exists the edge is not emitted.

**Invariant:** `requirement` (`req:`) nodes are **not** contained — they are gate
groups, not members of the containment tree (RFC-0012 "Edge taxonomy": `contains`
is package/module/class → child). They connect to methods via `gates`/`of` only.

**Rationale:** 1.2 left package nodes with zero edges and the class→method link
implicit in the URI prefix. ID-223 clusters methods inside their class and classes
inside their package using these edges.

---

## DGM-009: Link Metadata

**Invariant:** Each `class` node carries link metadata pointing at the authority
for that class:

- **`spec`** — repo-relative path to the governing spec document
  (e.g. `sdd/specs/001-store-api.md`).
- **`doc`** — repo-relative path to the class's API reference page
  (e.g. `docs-src/reference/api/store.md`).

Both are repo-relative from the project root, consistent with the existing `file`
node field. The generator MUST assert each mapped path exists on disk, so a stale
mapping fails generation rather than emitting a dangling link.

**Granularity (documented scope decision):** Link metadata is attached at
**file/page** granularity on **class** nodes only. The task framing asked for a
spec-*clause* ID and a docs *anchor* per node; 1.3 deliberately attaches the
governing spec *file* and the docs *page* instead, because:

- A class has no single governing clause (e.g. `Store` is governed by the whole
  `STORE-*` block, not one ID), so a per-class clause ID would be arbitrary.
- The mkdocstrings symbol anchor uses the *public* import path
  (`remote_store.Store.read`) while node URIs use the *canonical* Griffe path
  (`remote_store._store.Store.read`); deriving the fragment in the generator would
  duplicate mkdocstrings' path logic. The consumer (ID-223) composes the fragment
  from `doc` + the method name instead.

**Derivation, not duplication:** `method`, `package`, and `requirement` nodes and
all edges do **not** carry `spec`/`doc`. A method's authority is derived by the
consumer from its containing `class` (via the `contains` edge, DGM-008) plus the
method name; an edge's authority is derived from its endpoints. Storing the same
links per method would be derivable bloat (DGM-010).

**Source:** The class→(spec, doc) mapping is a curated table in `gen_graph.py`.
Unlike the extras→backend join (RFC-0012 "Tooling appendix"), there is no second
machine source to join against — the spec and docs structure is editorial — so a
curated table is the honest representation. A class with no dedicated spec/page
(e.g. the `S3Boto3Backend` proof-of-concept) is listed on an explicit exempt
allowlist; every other class node of role `abc`/`backend`/`facade` MUST carry both
fields. The Test Traceability section pins the drift-guard test
(`test_class_nodes_carry_link_metadata`) for this clause.

---

## DGM-010: Omit-When-Null / No-Derivable-Keys Hygiene

**Invariant:** A key is present on a node or edge only when it carries
information that is neither null nor exactly derivable from another field on the
same object. Specifically:

- A key whose value would be `null`/`None` is omitted, not emitted as
  `key: null`. Consumers read *absent* as the null/default case.
- The `declares` and `raises` edges carry `condition` (a `prd:` URI) only when the
  edge is conditional; an unconditional edge omits the key entirely (absent ⇒
  unconditional). This is the convention ID-224 introduced and RFC-0012's "Edge
  taxonomy" documents; this clause makes it normative for the generator.
- `method` nodes carry `gated` (DGM-014) only when it is `false`; a gated method
  omits the key (absent ⇒ gated). Gated methods are the common case and already
  carry a `gates` edge, so emitting `gated: true` on every one would be derivable
  bloat; `gated: false` on the ungated minority is the information-bearing form.
- No boolean or scalar that restates another field is emitted (DGM-006: no
  `is_facade` mirroring `role`).

**Rationale:** The golden `--check` diff (DGM-013) must track real API changes,
not null padding or derivable restatements. `contains` adds an edge per method and
per class and link metadata adds fields per class node; without this hygiene the
1.3 artifact would inflate substantially.

---

## DGM-011: The `kind_of` vs `kind` Deviation on Extra Nodes

**Invariant:** `extra` nodes carry their backend/extension/aggregate
classification under the key **`kind_of`**, not `kind`. RFC-0012 "Node taxonomy"
names this property `kind`, but `kind` is the reserved node-kind discriminator
present on every node (`"kind": "extra"`). The generator renames the RFC's `kind`
property to `kind_of` to avoid the collision.

**Rationale:** This is a documented, intentional divergence from the RFC's
property name. Recording it here keeps the code and the model reconcilable
(principle 5) instead of looking like a bug.

---

## DGM-012: Determinism

**Invariant:** The generator produces byte-identical output for an unchanged
source tree. `nodes` are sorted ascending by `id`; `edges` ascending by
`(kind, src, dst)`; object keys sorted (`json.dumps(sort_keys=True)`); 2-space
indent; LF line endings; trailing newline. `mirrors` edges are deduped to one
edge per peer pair in the canonical async→sync direction.

**Rationale:** RFC-0012 "Snapshots / Determinism". This is unchanged from 1.2 and
restated here because the new `contains` edges and link metadata must not
introduce set-ordering nondeterminism.

---

## DGM-013: The `--check` CI Contract

**Invariant:** `scripts/gen_graph.py --check` and
`scripts/gen_graph_viz.py --check` exit non-zero (without writing) when the
committed `graph.json` / `graph_viz.html` would differ from a fresh build. Both
run in the pre-commit gate (`hatch run all`) and in CI; a source change that is
not accompanied by regenerated artifacts fails the gate.

**Invariant (schema_version ripple):** Bumping `schema_version` requires updating
every consumer that pins or reads it: the `gen_graph_viz.py` schema-compatibility
comment and `__SCHEMA_VERSION__` rendering, the golden test's `schema_version`
assertion in `tests/scripts/test_gen_graph.py`, and the committed artifacts. The
two `--check` gates are the backstop that catches a missed regeneration.

**Invariant (generation environment):** The generator is run with **all extras
installed** (the `dev`/`docs` hatch env, which is what CI and the pre-commit gate
use). `declares`, `inherits`, and the `abc`/`backend` role split all read the
*runtime* class via `_import_class`; a missing optional dependency makes that
return `None`, leaving the (statically-collected) class node with its edges
silently dropped. Running without an extra therefore produces a smaller graph
that fails `--check` against the committed full artifact — which is the intended
loud signal. The contract: regenerate only in the all-extras environment, never
commit a partial-import build.

**Rationale:** RFC-0012 "Testing"; the golden round-trip is the single test that
makes the artifact trustworthy.

---

## DGM-014: Ungated Facade Method Nodes

**Invariant:** For the `Store` and `AsyncStore` facades (DGM-007) the generator
emits a `method` node for every **public, non-gated** function member — the
"always available" surface (`exists`, `is_file`, `is_folder`, `ping`,
`close`/`aclose`, `child`, `unwrap`, `resolve`, `native_path`, `to_key`,
`supports`). A method is *ungated* when its name is not a key of the facade's
`_GATING` map. Ungated nodes carry the same introspection fields as gated method
nodes (`summary`, `is_abstract`, `is_async`, `file`, `line`) plus `gated: false`.

**Invariant:** Ungated method nodes carry **no** `req:`/`gates`/`of` edges (they
have no capability gate). Their `contains` edge (class → method, DGM-008) is
emitted by the generic containment pass, so they are not orphaned.

**Scope:** Ungated emission applies to the `Store`/`AsyncStore` facades only.
The `Backend`/`AsyncBackend` ABCs continue to emit gated methods only (from
`_BACKEND_GATING` / `_ASYNC_BACKEND_GATING`): "always available" is a facade
guarantee to package consumers, not part of the backend-adapter contract, and no
consumer needs the ABCs' ungated surface. Dunders (leading `_`) are excluded;
the discriminator is "public function member not in `_GATING`", so a new ungated
facade method becomes a node automatically (no allowlist to maintain).

**Postcondition:** ID-222's `gen_features.py` derives the Store API "Ungated
(always available)" table by selecting `Store` method nodes with `gated == false`,
instead of hand-maintaining the method set. The schema 1.3 boundary deferred this
("only GATED method nodes are emitted"); 1.4 lifts it for the facades.

**Rationale:** The `gated` field is technically derivable from the absence of a
`gates` edge, which DGM-010 would normally forbid. It is emitted anyway as a
deliberate, documented exception: the field makes the ungated set directly
queryable without a negative edge-existence join, and the omit-when-default rule
(DGM-010) keeps it from inflating the gated majority.

---

## Test Traceability

Each numbered obligation above is anchored by at least one
`@pytest.mark.spec`-tagged test in `tests/scripts/test_gen_graph.py`, so a
regression names the broken clause (the `check_spec_marks` gate enforces that
every clause keeps a mark):

| Clause | Test |
|---|---|
| DGM-001 (schema 1.4, version fields) | `test_graph_schema` |
| DGM-002 (node kinds present / deferred absent) | `test_graph_schema`, `test_deferred_kinds_absent` |
| DGM-003 (edge kinds present / deferred absent) | `test_graph_schema`, `test_deferred_kinds_absent` |
| DGM-004 (`abc` role) | `test_abc_classes_have_abc_role` |
| DGM-004 (`backend` role excludes ABCs/facades) | `test_backend_role_is_concrete_backends_only` |
| DGM-005 (inherits via MRO) | `test_inherits_reaches_backend_through_private_base` |
| DGM-006 (facade suppression) | `test_facade_declares_suppressed` |
| DGM-007 (Store/AsyncStore facade nodes) | `test_store_facade_nodes_present` |
| DGM-008 (contains class→method) | `test_contains_class_to_method` |
| DGM-008 (contains package→class) | `test_contains_package_to_class` |
| DGM-009 (link metadata + drift guard) | `test_class_nodes_carry_link_metadata` |
| DGM-010 (no null/derivable keys) | `test_graph_schema` (condition guard) |
| DGM-011 (`kind_of` on extra nodes) | `test_extra_nodes_use_kind_of` |
| DGM-012 (determinism) | `test_graph_deterministic_in_process` |
| DGM-013 (artifact up to date) | `test_graph_json_is_up_to_date` |
| DGM-014 (ungated facade method nodes) | `test_ungated_facade_method_nodes` |

RFC-0012 makes the golden test the trust anchor; this table makes each obligation
individually falsifiable.

---

## Deferred / Out of Scope at 1.4

The following are explicitly out of scope and tracked elsewhere:

- **Argument-level capability gates.** `USER_METADATA` gates the `metadata=`
  kwarg, not a whole method; 1.4 still has no argument-level gate model. The RFC
  `prm:` / `predicate` nodes are the future path. ID-222 records this as a known
  limitation: the `metadata=` gate is documented as a FEATURES footnote and in the
  `Capabilities` table, not as a method gate, because the graph cannot yet model
  a per-argument predicate.
- **Ungated `Backend`/`AsyncBackend` methods.** DGM-014 emits ungated nodes for
  the `Store`/`AsyncStore` facades only; the ABCs' ungated surface has no consumer.
- **The deferred node/edge kinds of DGM-002/DGM-003**, each added under its own
  schema bump when a consumer needs it.

(Role-aware visualization, deep links, and faceted filtering — formerly deferred
here — shipped in ID-223 as a pure consumer of the 1.4 graph; see
`scripts/gen_graph_viz.py`.)
