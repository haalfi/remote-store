# Research: TLA+ Spec Augmentation (ID-147)

**Date:** 2026-04-17
**Status:** In progress — spike plan
**Scope:** Plan and execution record for ID-147: three minimal TLA+ modules
augmenting existing Markdown specs with machine-checkable cross-layer
consistency properties.
**Related:** ID-147, [sdd/formal/README.md](../formal/README.md),
[spec 003](../specs/003-backend-adapter-contract.md),
[spec 019](../specs/019-ext-observe.md),
[rfc-0011](../rfcs/rfc-0011-write-result.md).

**Context:** PR 448 (WriteResult) amended five specs in one feature. The
manual ripple-check table tells reviewers *what* to check; it cannot tell
them whether the amended specs are mutually consistent. Dafny covers
per-operation contracts and data-structure invariants but has no model of
how layers compose. This spike explores TLA+ as a lightweight, additive
layer for cross-spec protocol consistency — augmenting the Markdown specs,
not replacing them.

---

## 1. Scope boundaries

**In scope for this spike:**

| TLA+ module | Shadows | Key properties |
|---|---|---|
| `Backend.tla` | spec 003 (CAP-001..CAP-007, BE-001..BE-019) | capability gate ordering, error discrimination, entry partition |
| `Store.tla` | spec 001 (STORE-004, STORE-005, STORE-006) | store wraps backend, capability gate fires before I/O |
| `Observer.tla` | spec 019 (OBS-001..OBS-003) | every completed op fires exactly one event; hook routing matches outcome |

**Explicitly out of scope for this spike:**

- WR-019 proxy forwarding (spec 045 / OBS-015): these sections live on
  `master` via PR 448 but not on this branch. Captured as a follow-up in
  ID-147 once spec 045 is available here.
- Async store API (spec 029 / ID-013b): higher concurrency complexity;
  defer until single-threaded model is understood.
- Replacing or superseding any Markdown spec section.

---

## 2. What TLC checks that Dafny does not

Dafny proves properties *within* a single method contract or refinement.
TLC model-checks *reachable states* of a composed system by exhaustive
(bounded) enumeration. The two tools are complementary:

| Question | Dafny | TLC |
|---|---|---|
| "Does this postcondition hold for all inputs?" | ✅ unbounded proof | bounded (finite model) |
| "Can a failed op still fire on_write instead of on_error?" | ❌ not expressible | ✅ state enumeration |
| "Does the capability gate always fire before any I/O action?" | ❌ cross-layer | ✅ interleaving |
| "Can two layers disagree on WriteResult?" | ❌ cross-module | ✅ composition |

---

## 3. Module design

### 3.1 Backend.tla

**What it models:** The abstract backend interface — not the filesystem
implementation (that is Dafny's job). This module defines the *protocol*
a backend participates in: what capabilities exist, what errors are
possible, what the outcome of each operation class is.

```
CONSTANTS Paths, Capabilities, Errors

VARIABLES fs,          \* function: Paths -> {"file", "dir", "missing"}
          declared_caps \* set of declared Capability values

TypeInvariant ==
    /\ fs \in [Paths -> {"file", "dir", "missing"}]
    /\ declared_caps \subseteq Capabilities

EntryPartition ==
    \A p \in Paths: ~(fs[p] = "file" /\ fs[p] = "dir")

CapabilityGate(op_cap) ==
    op_cap \notin declared_caps =>
        outcome = "CapabilityNotSupported"
```

Key properties to check:
- `EntryPartition`: invariant — no path is simultaneously file and dir.
- `CapabilityGateFiresFirst`: if a capability is missing, no `fs` mutation
  occurs (outcome = CapabilityNotSupported AND fs' = fs).
- `ErrorDiscrimination`: `NotFound # AlreadyExists # InvalidPath # ...`
  (error types are distinct — catches any future enum collision).

### 3.2 Store.tla

**What it models:** The Store layer wrapping a Backend. Focuses on the
protocol boundary: Store adds its own capability check (via `require()`),
then delegates to the backend. The key question: does the Store's gate
always fire before any backend action?

```
EXTENDS Backend

CapGatePrecedesIO ==
    \* If Store fires CapabilityNotSupported, backend action is skipped.
    (store_outcome = "CapabilityNotSupported") =>
        UNCHANGED fs
```

For now Store.tla is thin — it establishes the composition scaffold that
WR-019 forwarding will inhabit once spec 045 is available.

### 3.3 Observer.tla

**What it models:** The observer proxy wrapping Store. Adds an `events`
sequence and models hook dispatch from spec 019 OBS-001..OBS-003.

The key properties from OBS-003:
- `on_write` fires after `write`, `write_text`, `write_atomic`.
- `on_error` fires for any operation that raises.
- `on_any` fires for every completed operation (success or error).

```
VARIABLES events   \* sequence of StoreEvent records

EventBijection ==
    \* Every completed operation produces exactly one event in on_any.
    Len(events) = completedOps

HookRouting ==
    \* A write that succeeds goes to on_write; one that fails goes to on_error.
    \A e \in Range(events):
        /\ (e.operation \in WriteOps /\ e.error = None) => on_write_fired(e)
        /\ (e.error # None) => on_error_fired(e)

NoDoubleDispatch ==
    \* on_any fires exactly once per operation, even if around hook raises.
    \A op \in CompletedOps: Cardinality({e \in events: e.correlates(op)}) = 1
```

`NoDoubleDispatch` is the most valuable check: the around-hook pattern
(OBS-005) nests around the operation *and* the hook dispatch. If the
around context manager raises on `__exit__`, does on_any fire twice?
TLC can enumerate this scenario; Dafny cannot express it.

---

## 4. Toolchain

### 4.1 TLC (model checker)

TLC is the standard TLA+ model checker. It runs from `tla2tools.jar`
(self-contained, ~10 MB, Java 11+). No Toolbox GUI required.

```bash
java -jar tla2tools.jar -config sdd/formal/tla/MC_Observer.cfg \
    sdd/formal/tla/MC_Observer.tla
```

Local setup: download `tla2tools.jar` into `scripts/` (gitignored) or use
Docker (same pattern as `scripts/dafny_verify.sh`). Prefer Docker for CI
reproducibility.

### 4.2 Module + config structure

```
sdd/formal/tla/
    Backend.tla         abstract backend protocol
    Store.tla           store wrapping backend (EXTENDS Backend)
    Observer.tla        observer proxy (EXTENDS Store)
    MC_Backend.tla      model-checking harness (instantiates with small Paths)
    MC_Store.tla        model-checking harness for Store properties
    MC_Observer.tla     model-checking harness for Observer properties
    MC_Backend.cfg      TLC config: INIT, NEXT, INVARIANTS
    MC_Store.cfg
    MC_Observer.cfg
```

Each `MC_*.tla` file instantiates the corresponding module with a small
finite model (e.g. `Paths == {"a", "b"}`, `Capabilities == {READ, WRITE}`).
This keeps TLC state space tractable while covering all relevant cases.

### 4.3 CI integration

Add a `verify-tla` job to `.github/workflows/ci.yml`, triggered when
`sdd/formal/tla/**` changes. Pattern mirrors the existing `verify-formal`
(Dafny) job:

```yaml
verify-tla:
  runs-on: ubuntu-latest
  if: ...changed files include sdd/formal/tla/...
  steps:
    - uses: actions/setup-java@v4
      with: { java-version: '21' }
    - run: bash scripts/tlc_check.sh
```

`scripts/tlc_check.sh` runs TLC on each `MC_*.tla` and exits non-zero on
any invariant violation or TLC error.

---

## 5. Implementation plan

Each phase is a self-contained session. Commit after each phase so the
branch records the progression.

### Phase 1 — Toolchain (session 1)

- [ ] Create `sdd/formal/tla/` directory.
- [ ] Write `scripts/tlc_check.sh` (Docker wrapper, mirrors
  `scripts/dafny_verify.sh`).
- [ ] Verify TLC runs clean on a trivial "hello world" spec.
- [ ] Add `verify-tla` stub to `.github/workflows/ci.yml` (not yet
  enforced — no modules to check).

### Phase 2 — Backend.tla (session 2)

- [ ] Write `Backend.tla`: CONSTANTS, VARIABLES, TypeInvariant,
  EntryPartition, CapabilityGate, operation actions.
- [ ] Write `MC_Backend.tla` + `MC_Backend.cfg`: `Paths == {"a", "b"}`,
  `Capabilities == {READ, WRITE, DELETE}`, INIT, NEXT, INVARIANTS.
- [ ] Run TLC. Confirm: all invariants hold, state space is enumerable in
  < 30 s.
- [ ] Record: authoring time, friction, anything surprising.

### Phase 3 — Store.tla (session 3)

- [ ] Write `Store.tla`: EXTENDS Backend, adds `CapGatePrecedesIO`.
- [ ] Write `MC_Store.tla` + `MC_Store.cfg`.
- [ ] Run TLC. Confirm `CapGatePrecedesIO` holds.
- [ ] Intentionally break it (remove gate) and confirm TLC produces a
  counterexample trace — this validates TLC is checking something real.

### Phase 4 — Observer.tla (session 4)

- [ ] Write `Observer.tla`: EXTENDS Store, adds `events`, `EventBijection`,
  `HookRouting`, `NoDoubleDispatch`.
- [ ] Write `MC_Observer.tla` + `MC_Observer.cfg`.
- [ ] Run TLC. Confirm all properties hold.
- [ ] Introduce a deliberate dispatch bug (fire on_write for failed ops)
  and confirm TLC catches it with a counterexample.

### Phase 5 — Spike report (session 5)

Update this document with findings:
- Authoring workflow: how long, what was hard, contributor friction estimate.
- TLC results: state space size, check time, any real violations found.
- Proof depth: which properties are meaningfully bounded vs. trivially small.
- Recommendation: extend (which targets next?), keep as-is, or icebox.

---

## 6. Open questions

1. **Co-location:** `sdd/formal/tla/` keeps TLA+ alongside Dafny as a
   single formal layer. Alternative: `sdd/tla/` as a peer to `sdd/formal/`.
   Decision: `sdd/formal/tla/` preferred — both are machine-checkable
   spec artefacts, not runtime code.

2. **EXTENDS vs. INSTANCE:** `Observer EXTENDS Store` pulls in all Store
   definitions unmodified. `Observer INSTANCE Store WITH ...` allows
   substituting Store variables — useful if Observer needs to track
   Store's `fs` via a renamed variable. Decide during Phase 4 authoring.

3. **Bounded model guarantees:** TLC with `Paths == {"a", "b"}` exhaustively
   checks all 2-path scenarios. Is that enough to be meaningful? Initial
   hypothesis: yes for routing and gating properties; borderline for
   depth-counting properties (which Dafny already covers).

4. **CI enforcement vs. informational:** Start CI as informational (non-blocking)
   until at least two modules verify cleanly. Promote to blocking in the
   same commit that finishes Phase 4.

5. **Sync with master:** This branch predates PR 448 (spec 045, OBS-015).
   Once the WR-019 forwarding target is ready, sync from master and add
   `Store.tla` WR-019 properties as a Phase 6.

---

## 7. Relationship to existing formal layer

| Layer | Artefact | Tool | Covers |
|---|---|---|---|
| Spec | `sdd/specs/*.md` | Review | Human-readable contracts |
| Dafny | `sdd/formal/*.dfy` | Dafny verifier | Per-operation pre/postconditions, data invariants, resource safety |
| TLA+ | `sdd/formal/tla/*.tla` | TLC | Cross-layer protocol properties, hook routing, composition |
| Tests | `tests/` | pytest + Hypothesis | Runtime conformance, PBT |

No layer replaces another. Dafny and TLA+ answer different questions about
the same system.
