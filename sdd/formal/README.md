# Formal Verification Layer (`sdd/formal/`)

Machine-checkable specification artefacts — not runtime code.

## Why this layer exists

Review and runtime tests catch what a reader notices and what a test
case exercises. A formal layer is a third line: machine-checkable
statements of what the system must do, verified against the actual
implementation or a reference model (the Dafny `MemoryBackend`).

Three properties we want this layer to enforce:

1. **Internal consistency of the contract** — no two stated properties
   contradict each other.
2. **Satisfiability** — the contract is met by a mechanically verified
   witness, so it is not quietly impossible. The witness is the Dafny
   `MemoryBackend` refinement, discharged by the Dafny verifier (not
   an ad-hoc Python example).
3. **Cross-layer consistency** — when a change amends multiple specs
   at once, *protocol properties* that span them still hold. A
   protocol property is an invariant that crosses module boundaries:
   "every successful write emits exactly one observer event," "the
   capability gate fires before any I/O action," "a proxy forwards
   `WriteResult` unchanged."

The first two are per-operation questions — **Dafny** territory. The
third is composition — **TLA+** territory.

## What we use

### Dafny

Dafny proves properties *inside* one method contract or data
structure: pre/postconditions, data invariants, resource safety. The
verifier is sound and unbounded within the types the spec declares —
properties hold for all inputs those types admit. Dafny also compiles
to Python, which lets us run the reference `MemoryBackend` through
the full conformance suite as a known-correct oracle.

Dafny's boundary: it does not model how layers compose, and it has no
event/interleaving model. Cross-module protocol questions ("does the
capability gate always fire before any I/O action?") are outside its
natural expressiveness.

### TLA+

TLA+ (model-checked by TLC) enumerates reachable states of a composed
system within a bounded model. It is the natural fit for questions
Dafny cannot express: event routing, capability gating across layers,
proxy forwarding invariants, interleavings.

TLC's boundary: it is finite-state. Guarantees hold for the bounded
model only; scaling constants can change runtime from milliseconds to
minutes.

### Decoupled, not coupled

IronFleet and `tla-dafny` embed TLA+ operators inside Dafny so
distributed and per-operation proofs share a logic. This repo
deliberately does *not*: Dafny covers per-operation contracts and the
compiled oracle; TLA+ sits beside it, stand-alone, for protocol
properties. Different layers, different questions, no shared proof
obligation. Coupling between them is *semantic*, not logical — both
tools are bound to the same Markdown spec, so a drift surfaces as a
verification failure on one side or the other, not as a joint proof
obligation.

### TLA+ as a spec-decomposition discipline

The primary value of TLA+ in this repo is not CI enforcement — it is
an authoring rule:

> When a normative spec item has more than one conjunction in its
> Markdown statement (a grammatical heuristic — "and", multiple
> clauses, enumerated obligations), write the corresponding TLA+
> invariant *first*. The real threshold is **more than one
> independently falsifiable claim**; the conjunction count is just
> the cheap spotter. If the invariant decomposes into independent
> top-level conjuncts, split the spec item into that many sub-items
> *before* review.

Two invariant flavours differ in what they must survive:

- **Authoring invariant** — written to force decomposition. Need not
  be machine-checked; the act of writing is the payoff.
- **Checked invariant** — a module lives under TLC, seeded-break
  tested, and expected to catch regressions. Subject to the CI rules
  below.

Authoring invariants are how the rule pays off at review time.
Checked invariants are how it pays off at regression time. Do not
conflate: a module of unverified authoring invariants should not
claim the same CI status as a checked one.

Writing the invariant mechanically surfaces bundled claims that a
reviewer — human or AI — has no hooks to check individually. Spec 045
§ WR-018 is the canonical example:

- **Before (Markdown):** one paragraph stating that proxies must
  forward `WriteResult` unchanged without substituting, mutating, or
  synthesising fields, invalidate post-write cache, and emit exactly
  one observer event.
- **After (TLA+):** four independent invariants — return-type widening
  (trivially enforced by constructor), `ProxyForwardUnchanged`,
  `PostWriteCacheNotTracked`, `EventPerWrite`. Three are independently
  breakable under TLC; the first is structural.

The rule applies **per spec item**, not to the spec as a whole.
Specifying a whole system as a conjunction of properties becomes
unreadable at scale — that is the reason TLA+ itself is state-machine
based, not property-list based. Decomposing one bundled item is a
review-scale operation; decomposing a whole spec is a re-architecture.

### TLA+ as a scope discipline

A second benefit, distinct from decomposition: each TLA+ module
targets one concern, with a small invariant table disjoint from its
peers. That caps the scope of any single formal artefact and keeps
the complexity of each module readable on its own.

The PoC demonstrated this with two stand-alone modules —
`WriteHeadRoundTrip` (field mapping) and `WR018ProxyForwarding`
(forwarding + event emission) — deliberately non-overlapping, each
enumerable quickly by TLC. Break-and-catch confirmed the invariants
were mutually independent: breaking one never triggered another.
Modules did not leak concerns into each other.

The consequence feeds back into the Markdown specs as a soft rule:
if a concern requires a sprawling TLA+ module to express, **revisit
the concern at the spec level** before enlarging the module. Module
size is a scope signal for the spec, not just for the proof. The
threshold is qualitative by design — two PoC modules is not enough
data to pin a numeric bound, and a false-precision threshold would
age worse than the qualitative one.

### Authoring rules

1. **Stand-alone modules per concern.** No `EXTENDS` hierarchy until a
   cross-module target empirically demonstrates value via
   break-and-catch.
2. **Target demonstrated bundling**, not abstract layers. WR-018's
   four-in-one paragraph is a target; "capability gate ordering" in
   the abstract is not.
3. **CI informational** until a TLA+ check catches a real regression
   on a production branch. Seeded breaks validate the tool; only a
   live catch validates the workflow. Informational signals atrophy —
   revisit the status at a fixed cadence (every 6 months, or after
   every 10 spec amendments, whichever first) and explicitly promote,
   remove, or re-defer. "Informational" must not silently become
   "unrun." Each revisit is tracked as a BACKLOG entry recording the
   decision (promote / remove / re-defer) — a calendar without a
   ticket is the same as no calendar.
4. **Promote `sdd/research/tla-poc/` → `sdd/formal/tla/`** only after
   (3). Until then, TLA+ artefacts live under research.

## Layers at a glance

| Layer | Source of truth | Verified by |
|-------|-----------------|-------------|
| Spec (`.md`) | Human-readable requirements | Review |
| Dafny (`.dfy`) | Machine-checkable per-operation contract | Dafny verifier |
| TLA+ (`.tla`, under `sdd/research/tla-poc/`) | Cross-layer protocol properties | TLC (bounded model) |
| Python (`_backend.py`) | Runtime implementation | pytest + Hypothesis PBT |

Dafny and TLA+ are parallel specifications — not auto-generated from
Python. When a Markdown spec item changes, the corresponding Dafny
postcondition or TLA+ invariant is updated; if the verifier rejects
the new form, the spec has an internal contradiction.

## Operations

### Files

| File | What it models |
|------|----------------|
| `BackendContract.dfy` | Abstract backend trait — error model, capabilities, all operation pre/postconditions |
| `MemoryBackend.dfy` | Reference refinement proving the contract is satisfiable; compiled to Python as the conformance oracle |
| `DepthCounting.dfy` | Verified `DEPTH-001` algorithm and the four depth-filter properties |
| `ResourceSafety.dfy` | Handle lifecycle, `_safe_wrap` invariant, move atomicity, connection lifecycle |

TLA+ modules currently live in `sdd/research/tla-poc/` (PoC state —
see *Authoring rules* for promotion criteria).

### Running the verifier

Local (Docker) — no Dafny install required:

```bash
bash scripts/dafny_verify.sh                       # all files
bash scripts/dafny_verify.sh BackendContract.dfy   # single file
```

Native: install [Dafny](https://github.com/dafny-lang/dafny) at the
pinned version (see
[`sdd/CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) § Local toolchain),
then `dafny verify sdd/formal/<file>.dfy`.

CI runs the `verify-formal` job automatically when `sdd/formal/` or
`sdd/specs/` files change.

### Verification practices

The Dafny files follow a small set of conventions that keep proofs
small, stable, and maintainable:

- **`assert` breadcrumbs** in every branch, to guide the solver to the
  postcondition rather than letting it search the full state space.
- **`calc` blocks** for depth arithmetic — calculation chains are
  readable and solver-stable.
- **No empty lemma bodies.** Every lemma has an explicit proof or at
  minimum assert breadcrumbs. "Obvious" facts are still spelled out.
- **Non-vacuous refinements.** `MemoryBackend` methods iterate and
  filter rather than returning `[]` to trivially satisfy
  postconditions.
- **`old(fs)` convention.** Mutating method precondition checks use
  `old(fs)` so post-state mutations don't leak into error-path
  reasoning.
- **`src == dst` as explicit no-op** in `Move`/`Copy`, with assertions
  proving each postcondition holds for the identity case.
- **Root as `"."`.** The Dafny `Path` type requires non-empty strings;
  the Python adapter translates `""` → `"."` once in `_str_to_dafny`,
  eliminating per-method root guards.

### Design decisions

- **Abstract trait, not class extraction.** Dafny models the
  *contract*, not the Python class hierarchy. Keeps the model small
  and focused on behavioural properties.
- **MemoryBackend as oracle.** The Dafny `MemoryBackend` is the
  reference implementation; the Python `MemoryBackend` acts as the
  PBT oracle. Both must agree.
- **Resource safety as state machine.** Pre/postconditions alone
  cannot express temporal properties (handle acquired then leaked);
  `ResourceSafety.dfy` uses explicit state tracking to model and
  prove them.
- **Safe/Unsafe pairs.** Each safety property is demonstrated with
  both a correct and a buggy implementation, so the invariant is
  never vacuously true.
- **No error-path frame condition.** `ensures r.Err? ==> fs == old(fs)`
  would be ideal, but `r.Err?` taints method bodies as
  specification-only in Dafny, preventing compiled assignments and
  returns. `MemoryBackend` preserves `fs` on error paths by
  construction instead.

### Compiled oracle as conformance gate

The Dafny `MemoryBackend` is compiled to Python via `dafny translate
py` and wrapped behind the `Backend` ABC as `DafnyOracleBackend`. The
oracle runs through the full conformance test suite alongside real
backends.

**Principle.** The compiled oracle is correct by construction. So:
if the oracle passes a conformance test, the test is known-correct
and can be trusted as a gate for real backends; if the oracle fails,
the test itself has a bug and must be fixed.

**Files:**

| File | Purpose |
|------|---------|
| `sdd/formal/MemoryBackend.dfy` | Source specification (verified) |
| `sdd/formal/MemoryBackend-py/module_.py` | Compiled Python output |
| `sdd/formal/MemoryBackend-py/_dafny/` | Dafny Python runtime |
| `tests/backends/dafny_oracle.py` | Adapter: compiled oracle → `Backend` ABC |

**Regenerating the compiled output.** The Dafny version is pinned
(see the toolchain reference above). Ghost-only changes (lemmas,
invariants, ghost variables, postconditions) erase at compile time
and produce no Python output — regeneration is not needed. Non-ghost
changes (method bodies, datatype definitions, function implementations)
do require regeneration:

```bash
dafny verify sdd/formal/MemoryBackend.dfy          # confirm spec
dafny translate py sdd/formal/MemoryBackend.dfy \
    --include-runtime --output sdd/formal/MemoryBackend
```

Dafny appends `-py` to the output directory name automatically.

**Class-ordering fix.** Dafny's Python translator emits
`MemoryBackend(Backend)` before `Backend` is defined — a
forward-reference error. After regeneration, reorder `module_.py` so
ADT types (`Error`, `Result`, `Entry`, `FileInfo`, `FolderInfo`,
`FolderEntry`, `Capability`) and `Backend` come before `MemoryBackend`,
with the `default__` helper (which uses `Path`, `IsChildOf`, `Depth`)
between them. Verify the reordering:

```bash
python -c "import sys; sys.path.insert(0, 'sdd/formal/MemoryBackend-py'); import module_"
```

**Running the oracle tests:**

```bash
pytest tests/backends/test_conformance.py -k "dafny-oracle" -v
pytest tests/backends/test_conformance_extended.py -k "dafny-oracle" -v
```

All tests should pass or self-skip (GLOB capability not declared).
Any failure indicates a conformance suite bug.

### Test conformance

Every Dafny postcondition has a corresponding Hypothesis property test
in `tests/backends/`. Dafny proves the property structurally for all
inputs a type admits; Hypothesis stress-tests the Python
implementation with randomised inputs, using the Python
`MemoryBackend` as the oracle. The authoritative list of current
tests is the test suite itself — not a mirror here.

## Origin — how we landed here

### Dafny: the BK-140 bug cluster

The Dafny layer landed after the 0.21.1 patch release fixed 22 bugs.
Root-cause analysis (BK-140) traced most of them to six gaps in the
backend ABC where behaviour was unspecified and backends diverged.
Each gap is now encoded as a machine-checkable pre/postcondition:

| # | Gap | Spec | Where encoded |
|---|-----|------|---------------|
| 1 | Precondition evaluation order | BE-008 | `BackendContract.dfy` |
| 2 | Canonical error-mapping table | BE-021 | `BackendContract.dfy` |
| 3 | Listing on missing paths | BE-014/015 | `BackendContract.dfy` |
| 4 | Depth-counting algorithm | DEPTH-001 | `DepthCounting.dfy` |
| 5 | Move atomicity | BE-018 | `ResourceSafety.dfy` |
| 6 | Acquire-then-wrap safety | SIO-001 | `ResourceSafety.dfy` |

Error-path frame conditions (gaps 1–2: `fs == old(fs)` on error) are
not machine-checked — the `r.Err?` discriminator taints method bodies
as specification-only in Dafny, preventing compiled assignments and
returns. `MemoryBackend` preserves the state by construction instead.

### TLA+: the WR-018 bundling finding

The TLA+ layer arrived during spec 045 (WriteResult) review. The
ID-147b PoC found that a single Markdown paragraph (§ WR-018) bundled
four independently breakable claims — a class of reviewer blind-spot
Dafny cannot surface because it is cross-layer, not per-operation.
That finding motivated the spec-decomposition discipline and the
authoring rules captured in *What we use* above.
