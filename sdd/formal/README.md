# Formal Verification Layer (`sdd/formal/`)
<!-- doc: repo-only -->

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
third is composition — **TLA+** territory. Below all three sits the
structure the operations act on; whether its axioms are consistent and
independent is a question for a model finder — **Alloy** territory —
and what follows from them over any universe is a question for a proof
assistant — **Lean 4** territory.

## Three shapes of Dafny-section work: (C), (T), (O)

The properties above explain why the layer exists. This subsection
explains how a *backlog item* earns its place in the Dafny track. The
SDD chain is `Markdown spec → @pytest.mark.spec test`. The marker is
just a string: nothing proves a spec clause is self-consistent, and
nothing proves the test faithfully encodes it. The Dafny layer is the
machine-checked interlock in that chain. It earns its place three
ways, none of which is "run a second backend and diff the output":

1. **(C) A proven contract.** Dafny verifies that a clause's
   postcondition is internally consistent and *satisfiable*, discharged
   by the `MemoryBackend` refinement. A Markdown paragraph can silently
   contradict itself; a verified `.dfy` postcondition cannot. A
   contract clause that exists only in prose is unproven.
2. **(T) The oracle certifies the test, not the backend.** The compiled
   `MemoryBackend` is correct by construction and already runs the
   whole conformance suite as a parametrized fixture. A green oracle on
   a test proves the test demands nothing the verified contract does
   not, i.e. the test faithfully encodes the spec. Running the oracle
   as a peer backend to diff against would only test the oracle twice.
3. **(O) The oracle as ground truth.** A deterministic test hardcodes
   its expected value, and that literal is a better oracle than a
   second process: readable and dependency-free. Only property-based
   tests, with random inputs, need the verified oracle to *compute* the
   expected value.

Runtime backend gaps downstream of a Dafny-backed clause — a backend
not honouring a verified postcondition — are spec-conformance work,
not Dafny-section work. File them under the relevant backend section
(SFTP, Azure, S3, etc.); the Dafny side of the contract is already
proven.

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

### Alloy

Alloy (the Alloy Analyzer, SAT-backed) searches for instances of a
relational model within a bounded scope. It is the fit for a static
axiom set: a `run` that finds an instance shows a structure exists
(consistency, a countermodel), and a `check` with no counterexample
shows a consequence holds up to the scope. Here it checks the store
tree of [spec 051](../specs/051-store-tree.md), which it restates
(§ Traceability tags). The rows, witnesses and lemma numbers are those
of its rationale,
[`research-store-model-axioms.md`](../research/research-store-model-axioms.md)
(BK-435): each § 5 countermodel breaks exactly its clause, the
witnesses are models, and lemmas L1 to L5 hold in scope.

Alloy's boundary: bounded scope, so nothing about infinite structures,
and a statement over all models (L6's correspondence up to
isomorphism) is out of reach. Proofs over the unrestricted universe are
the next layer's job. Every command carries `expect`, so a run is
green only when each outcome matches.

### Lean 4

Lean 4 is a proof assistant: a statement it accepts holds for every
structure its types admit, with no scope. Here it restates spec 051
too, and proves the research doc's lemmas over an arbitrary universe:
D1, L1 to L6
(including L6's correspondence up to isomorphism, which Alloy cannot
state), that the axioms have an infinite model, and § 9.7's infinite
upward chain. Lean core only, no Mathlib.

Lean's boundary: it proves what the file states, so fidelity to spec
051 is a review question, as for every layer here. The build fails on a
`sorry`, and `#guard_msgs` lines pin the axioms each headline result
rests on (the 10 at the end of `StoreAxioms.lean`); a new result is
pinned only once a line is added for it.

[`tex/`](tex/README.md) retells these proofs, and what the Alloy model
adds, in prose for human readers. Its proofs are not machine-checked; its
README says how to redo it when the Lean file changes.

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
  `PostWriteCacheNotTracked` is *stronger* than WR-018 strictly
  requires: WR-018 mandates invalidation at write time, but the
  current model omits a Read action and so the invariant reads as an
  eternal ban on tracking a written path (see I3 in
  `WR018ProxyForwarding.tla`). The mismatch is documented in the
  module; a future Read action would relax the invariant to match
  WR-018 exactly.

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

<a id="authoring-rules"></a>
### Authoring rules

1. **Stand-alone modules per concern.** No `EXTENDS` hierarchy until a
   cross-module target empirically demonstrates value via
   break-and-catch.
2. **Target demonstrated bundling**, not abstract layers. WR-018's
   four-in-one paragraph is a target; "capability gate ordering" in
   the abstract is not.
3. **A TLA+ check gates per module, from the PR that bridges the
   module to code** ([ADR-0048](../adrs/0048-how-specs-are-designed.md),
   [`SPEC-DESIGN.md` Rule 4](../SPEC-DESIGN.md#governing-layer)). An
   unbridged module stays informational: gating it would prove only
   that the model agrees with itself. Gating per module needs
   `verify-tla` split per module (BK-461). Revisit the unbridged
   modules' informational status every 6 months, or in the PR that
   first bridges a TLA+ module to code, whichever comes first: the
   bridged module gates from that PR, and for each unbridged one,
   explicitly promote, remove, or re-defer. "Informational" must not
   silently become "unrun." Each revisit is tracked as a BACKLOG entry
   recording the decision (promote / remove / re-defer) — a calendar
   without a ticket is the same as no calendar. The first `verify-tla`
   job landed under ID-147 on 2026-04-19; ID-150 re-deferred it on
   2026-10-18 and the next revisit is tracked as ID-270.
4. **Live TLA+ modules live under `sdd/formal/tla/`.** The
   `sdd/research/tla-poc/` tree is the frozen 2026-04 PoC that
   established the spec-decomposition discipline (see
   `sdd/research/research-id-147b-tla-poc.md`) and is not extended or
   maintained going forward. The finding stays in the repo as history
   — the layer it motivated lives in `sdd/formal/tla/`. "Informal
   layer" and "under `sdd/formal/`" are not contradictory: rule 3
   controls CI gate status (blocking vs informational), rule 4
   controls physical location. A module is informal until rule 3
   promotes it, regardless of directory.

<a id="layers-at-a-glance"></a>
## Layers at a glance

| Layer | Source of truth | Verified by | Governs, through a bridge |
|-------|-----------------|-------------|---------------------------|
| Spec (`.md`) | Human-readable requirements | Review | Every clause no bridged model governs |
| Dafny (`.dfy`) | Machine-checkable per-operation contract | Dafny verifier | Function and single-call clauses |
| TLA+ (`.tla`, under `sdd/formal/tla/`) | Cross-layer protocol properties | TLC (bounded model) | Lifetime and environment clauses; liveness as bounded obligations only |
| Alloy (`.als`, under `sdd/formal/alloy/`) | Static store-model axioms: consistency, independence, lemmas in scope | Alloy Analyzer (bounded scope) | Structure clauses, bounded |
| Lean 4 (`.lean`, under `sdd/formal/lean/`) | Static store-model lemmas over an unrestricted universe | Lean 4 kernel (`lake build`) | Structure clauses, unbounded |
| Python (`_backend.py`) | Runtime implementation | pytest + Hypothesis PBT | — |

The last column is [`SPEC-DESIGN.md` Rule 4](../SPEC-DESIGN.md#governing-layer):
a layer governs a clause only where a bridge binds its model to the tests, only
as far as that bridge reaches, and only while the layer's own check gates in
CI. Alloy and Lean run in no CI job (§ Running the verifier), so they govern no
clause until one does. A bridge already in the repo, such as the compiled
oracles below, counts only once [`SPEC-DESIGN.md` Rule
8](../SPEC-DESIGN.md#bridge-checklist)'s six items are stated for it. Dafny's
`verify-formal` gates every `.dfy` file, bridged or not, for its own reason: a
postcondition the verifier rejects is a contradiction in the contract itself
([`000-process.md` Rule 7](../000-process.md#intent-attribution)'s
Unsatisfiable row).

Dafny and TLA+ are parallel specifications — not auto-generated from
Python. When a Markdown spec item changes, the corresponding Dafny
postcondition or TLA+ invariant is updated; if the verifier rejects
the new form, the spec has an internal contradiction.

A rejected form is only the case a verifier can catch. For the
disagreement generally — prose against a checked model clause or
against a green conformance suite, including where prose is the side
that must move — see [`000-process.md` Rule
7](../000-process.md#intent-attribution).

## Operations

### Files

| File | What it models |
|------|----------------|
| `BackendContract.dfy` | Abstract backend trait — error model, capabilities, all operation pre/postconditions, the `AddressesRoot` root predicate |
| `MemoryBackend.dfy` | Reference refinement proving the contract is satisfiable; compiled to Python as the conformance oracle, together with the files it includes (§ Compiled oracle lists them) |
| `DepthCounting.dfy` | Verified `DEPTH-001` algorithm and the four depth-filter properties |
| `ResourceSafety.dfy` | Handle lifecycle, `_safe_wrap` invariant, move atomicity, connection lifecycle |
| `KernelProtocol.dfy` | Spec 052's close and cleanup clauses on the kernel (BE-020's I1, BE-034's I2, BE-033's I3), standalone (nothing includes it) and compiled to an oracle of its own (§ Compiled oracle): the close posture as a transition function, with terminal absorption (`TerminalCloseAbsorbs`, I1) and every close forwarded (`CloseIsForwardedAndIdempotent`, I2); `KernelExit` over every exit the kernel observes, leaving no write handle open, every stream closed or, when its failure condemned the connection, released without a close, and no caller iterator with `aclose` suspended (`CleanupOnEveryExit`, I3). I1 covers the calls the closed guard covers; the addressing members are not modelled. The `Session` states are not modelled |
| `RootPath.dfy` | What `AddressesRoot` accepts: exactly the keys whose every `/`-segment is `""` or `"."` (`RootSpellingCharacterisation`), so the six BE-029 spellings; only `Root` among well-formed paths; not `\` (BE-029). BE-029's table derived from the trait for every refinement (`RootAnswersPerTable`), and the raw-key entry (`WriteKey`, `MoveKey`, `CopyKey`) that folds every root spelling of a write or `move`/`copy` destination onto `Root` |
| `StoreTree.dfy` | RFC-0021's model, a sketch not yet wired into the trait. Its header lists §1 to §12: the store as a tree over spec 051's names (TREE-007), whose distinct Keys never join to the same string (TREE-010); a flat encoding's partial `decode`; agreement between a flat driver's lookups, listings, recursive `delete_folder` walk and `move`/`copy` and the tree; D4's write checks; that a flat encoding holds no empty folder; A.8's refusal rule for every call, namespace and row; and that a valid tree is the pair of spec 051's lemma L6, for finite stores only |

Live TLA+ modules live in `sdd/formal/tla/`. The frozen PoC modules
remain in `sdd/research/tla-poc/` as the historical record of the
exercise that established the discipline — see
`sdd/research/research-id-147b-tla-poc.md`.

### Running the verifier

Local (Docker) — no Dafny install required:

```bash
bash scripts/dafny_verify.sh                       # all files
bash scripts/dafny_verify.sh BackendContract.dfy   # single file
```

Native: install [Dafny](https://github.com/dafny-lang/dafny) at the
pinned version (see
[`sdd/CLAUDE-REFERENCE.md` § Local toolchain](../CLAUDE-REFERENCE.md#local-toolchain)),
then `dafny verify sdd/formal/<file>.dfy`.

CI runs the `verify-formal` job automatically when a changed path outside
`sdd/formal/tla/`, `alloy/` and `lean/` (which the filter step drops first)
matches `FORMAL_PAT` in
`.github/workflows/ci.yml`; it also checks the compiled oracle
against its sources and runs the oracle's tests (see § Compiled oracle as
conformance gate).

TLA+ (TLC): `bash scripts/tlc_check.sh` runs the Observer model
(default target `sdd/formal/tla/MC3`) via a pinned Docker image — no
local Java or `tla2tools.jar` install required. The historical PoC
configs still run via `bash scripts/tlc_check.sh sdd/research/tla-poc MC`
(or `MC2`). CI's informational `verify-tla` job runs the live MC3
model whenever files under `sdd/formal/tla/` or the TLC tooling
change.

Alloy: `bash scripts/alloy_check.sh` (or `hatch run verify-alloy`) runs
every command of `sdd/formal/alloy/StoreAxioms.als` and exits non-zero
when any outcome differs from its `expect`. It uses a native `alloy` on
`PATH` that reports the pinned version, and otherwise a Docker image
built from `scripts/alloy.Dockerfile`; `ALLOY_RUNNER=docker` forces
Docker. No CI job runs it (maintainer decision, 2026-10-13); one added
later starts informational, as authoring rule 3 sets for TLA+.

Native setup needs a Java runtime and no root. On 2026-10-13 the model
ran green under the image's Java 21 (`eclipse-temurin:21-jre`) and,
natively, under OpenJDK 25.0.1 (`java -version` on the machine that ran
it); other versions are untried. `session-init.sh` does the same into
`/usr/local` in a claude.ai/code container. The version and sha256 are
the ones pinned in `scripts/alloy.Dockerfile`. `~/.local/bin` must be on
`PATH` for the last line and for `alloy_check.sh` to find it:

```bash
mkdir -p ~/.local/lib/alloy ~/.local/bin
curl -fsSL -o ~/.local/lib/alloy/alloy.jar \
  https://repo1.maven.org/maven2/org/alloytools/org.alloytools.alloy.dist/6.2.0/org.alloytools.alloy.dist-6.2.0.jar
echo "6037cbeee0e8423c1c468447ed10f5fcf2f2743a2ffc39cb1c81f2905c0fdb9d  $HOME/.local/lib/alloy/alloy.jar" | sha256sum --check
printf '#!/bin/bash\nexec java --enable-native-access=ALL-UNNAMED -jar "$HOME/.local/lib/alloy/alloy.jar" "$@"\n' > ~/.local/bin/alloy
chmod +x ~/.local/bin/alloy
alloy version    # 6.2.0
```

`alloy gui` opens the Analyzer's editor and visualizer on the same jar,
which is the quickest way to look at an instance a `run` found.

Lean: `bash scripts/lean_check.sh` (or `hatch run verify-lean`) runs
`lake build` on `sdd/formal/lean/` and exits non-zero on any error,
a `sorry` or a changed axiom list included. It builds
`StoreAxioms.lean` and what that file imports, so a new `.lean` file
is checked only once it is imported there. It uses a native `lean` on
`PATH` that reports the pinned version from inside the project, and
otherwise a Docker image built from `scripts/lean.Dockerfile`, which
checks the release archive against a pinned sha256;
`LEAN_RUNNER=docker` forces Docker. No CI job runs it, as for Alloy.
Unlike Alloy, `session-init.sh` does not install Lean in a
claude.ai/code container: the release archive is about 580 MB
(`content-length: 580432872` for `lean-4.34.1-linux.tar.zst` from
`curl -sIL` on the release URL in `scripts/lean.Dockerfile`), it unpacks
to about 2.9 GB (`du -sh /opt/lean` in the image built from that
Dockerfile), and a container starts fresh each session (maintainer
decision, 2026-10-13). It prints a message instead: in such a container
that the proofs cannot be checked in the session, elsewhere that
`lean_check.sh` falls back to Docker.

Native setup needs no root. [elan](https://github.com/leanprover/elan),
Lean's version manager, reads the project's `lean-toolchain` file and
fetches that release on first use; it does not check the Dockerfile's
sha256, and the installer below is fetched unpinned. These steps are
untested: on 2026-10-13 the proofs were built only through the Docker
image (maintainer decision to leave the native path untested). The installer adds
`~/.elan/bin` to the shell profile; the `export` line puts it on `PATH`
in the current shell:

```bash
curl -fsSL -o elan-init.sh https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh
sh elan-init.sh -y --default-toolchain none
export PATH="$HOME/.elan/bin:$PATH"
cd sdd/formal/lean
lean --version    # Lean (version 4.34.1, ...)
```

An editor with the Lean 4 extension (VS Code) shows each proof state
interactively on the same toolchain.

<a id="traceability-tags"></a>
### Traceability tags

A formal statement names the spec section it encodes in a line comment:

- **Dafny:** `// @spec <ID>` above the `ensures` it tags.
- **Alloy and Lean:** `-- @spec <ID>` above the predicate, structure field,
  definition or theorem that restates the section, and one
  `-- @restates sdd/specs/<file>.md` line per spec the file restates. A
  file at the top level of `alloy/` or `lean/` with none fails the check,
  so a module that restates no spec sits in a subdirectory, which the
  check does not read: Alloy opens it as `open sub/Helper`, and Lean
  imports `lean/StoreAxioms/Helper.lean` as `StoreAxioms.Helper`.
  `StoreAxioms.als` and `StoreAxioms.lean` each restate spec 051.

**The spec governs the tags.** A section with no tag in a file that
restates its spec, or a tag citing an ID no spec declares, is fixed in the
formal file. Disagreement about content follows each file's header rule
and [`000-process.md` Rule 7](../000-process.md#intent-attribution).

`scripts/check_formal_trace.py` enforces both directions in `lint`,
`docs-gate` and CI's `verify-formal`, so an edit confined to an `.als` or
`.lean` file is checked through `docs-gate`. It checks citation only. It
does not check that a tagged statement says what its section says, and it
does not run Alloy or Lean. Its docstring states the full bound.

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
  the Python adapter translates `""` → `"."` once in `_str_to_dafny`, so
  the model sees one root spelling. The per-method root checks are not
  there for other spellings: `Write`, `Move` and `Copy` check
  `AddressesRoot` to rank the root refusal ahead of every observed check
  on `Root` itself (BE-029, BE-018's root-destination carve-out), and
  `DeleteFolder` refuses `Root` (spec 053 BE-031 § The root). Spellings such as `"./"` or
  `"/"` are outside the methods' `WellFormedPath` domain; the raw-key
  entry in `RootPath.dfy` §5 folds them onto `Root` before the trait.
  `MemoryBackend.dfy` includes `RootPath.dfy` so that entry compiles into
  the oracle, and the adapter sends every write key and `move`/`copy`
  destination through it (ID-251). The oracle's refusal of those spellings
  is therefore the verified one, and it names `Root`, not the raw key.
- **`MemoryBackend` / `MemoryBackendMinimal` parity.** Dafny has no
  class-to-class inheritance, so `MemoryBackendMinimal` duplicates every
  method body of `MemoryBackend` with a narrower capability set and a
  terminal close posture.  Any
  postcondition or body change to `MemoryBackend` **must be manually
  mirrored** in `MemoryBackendMinimal`.

  Each class proves its own contract, so `dafny_verify.sh` catches a one-sided
  edit only when it changes what that class can prove.  Weakening a
  postcondition the trait declares is caught; drift inside what the contract
  leaves open is not.  Changing the twin's `GetFolderInfo` folder-name field —
  which no postcondition pins — verifies with *0 errors* while
  changing the twin's behaviour for every folder, and proof-structure edits
  verify clean by construction.  That band is now gated by
  `scripts/check_dafny_twin_parity.py`, which compares the two classes member by
  member and pins the two deliberate divergences (the constructor's capability
  set and close posture, and `Write`'s `CapWriteResultNative` branch) rather
  than skipping them.
  It needs no Dafny toolchain, and runs both in `hatch run lint` and in CI's
  `verify-formal` job — the latter because `lint` is skipped for a change
  confined to `sdd/`, which is precisely the shape of a one-sided edit here.
  Both measured mutation classes are held by
  `tests/scripts/test_check_dafny_twin_parity.py`.

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
  construction instead. The exception is a frame keyed on the pre-state
  rather than on `r`: the closed-guard and root-refusal frames of gaps 9
  and 10, and `Write`'s WR-010 gate, are stated and verified.

<a id="compiled-oracle"></a>
### Compiled oracle as conformance gate

The Dafny `MemoryBackend` is compiled to Python by the `dafny build -t py`
invocation in `scripts/dafny_translate.sh` and wrapped behind the `Backend` ABC
as `DafnyOracleBackend`. The
oracle runs through the full conformance test suite alongside real
backends.

**Principle.** The compiled oracle is correct by construction. So:
if the oracle passes a conformance test, the test is known-correct
and can be trusted as a gate for real backends; if the oracle fails,
the test itself has a bug and must be fixed.

**Files:**

| File | Purpose |
|------|---------|
| `sdd/formal/MemoryBackend.dfy` | Source specification (verified); the translation entry point |
| `sdd/formal/BackendContract.dfy`, `sdd/formal/RootPath.dfy`, `sdd/formal/ResourceSafety.dfy` | Included by `MemoryBackend.dfy` (`ResourceSafety.dfy` through `BackendContract.dfy`), so every non-ghost member they declare (datatypes, functions, methods) compiles into `module_.py` too — for example `RootPath.dfy`'s §5 `RootFold` and `ResourceSafety.dfy`'s `SafeWrap` |
| `sdd/formal/MemoryBackend-py/module_.py` | Compiled Python output |
| `sdd/formal/MemoryBackend-py/_dafny/` | Dafny Python runtime |
| `tests/backends/dafny/_helpers.py` | Adapter: compiled oracle → `Backend` ABC |
| `sdd/formal/KernelProtocol.dfy` | The second translation entry point: spec 052's kernel protocol (BE-020, BE-033, BE-034), one named `module KernelProtocol`, including nothing and included by nothing |
| `sdd/formal/KernelProtocol-py/KernelProtocol.py` | Its compiled Python: `KernelExit`, `KernelStep`, `KernelRun` and their datatypes (`module_.py` beside it is Dafny's stub entry, not this module) |
| `tests/_kernel/test_protocol_oracle.py` | Drives the kernel through the exits its case builders enumerate (below, **What the kernel oracle suite drives**) and compares the state it leaves with `KernelExit`'s and `KernelStep`'s answer |

**The second oracle.** `KernelProtocol-py/` serves a different direction from
`MemoryBackend-py/`: not "a test the oracle passes is a correct test", but "the
kernel leaves the state the proved model computes". Its suite runs the products
its case builders enumerate rather than sampling, maps what the fake driver observed onto the
model's datatypes, and asks the compiled model for the expected state, so a
lemma about `KernelExit` is a claim about the kernel only as far as that
mapping is faithful. The mapping is stated in the suite's module docstring;
read it before trusting a pass. Both oracles share the Dafny runtime (`_dafny/`,
`System_/`), byte-identical under the one pin. The named module gives the
second its own `KernelProtocol.py`, but Dafny still writes a stub `module_.py`
beside it, and `KernelProtocol.py` imports it; on `sys.path` or cached in
`sys.modules`, that stub shadows the first oracle's `module_` for any later
import. So the suite puts `KernelProtocol-py/` on `sys.path` for its own import
only, then removes it and restores `sys.modules["module_"]`, and a cell pins
both. `scripts/gen_protocol_diagram.py` imports it the same way to draw spec
052's state diagrams (its Notes) from `KernelStep` and `KernelExit`, so after
rebuilding this oracle run `hatch run gen-protocol-diagram` too, or
`preflight` fails on the stale block.

**What the kernel oracle suite drives**, which bounds how far spec 052's I1 to
I3 hold of the code (moved from spec 052's BE-033):
`KernelProtocol.dfy` compiles to
`sdd/formal/KernelProtocol-py/`, and `tests/_kernel/test_protocol_oracle.py`
drives the kernel through the exits its case builders enumerate (`_write_cases`,
`_UNDRAINED_ROUTES`, `_open_atomic_cases`, `_read_cases`, `_sequences`; that file
is the list), not every exit and not every state the model admits (most admitted
states pair resources no single exit holds). The writes run on a hierarchical
namespace with `overwrite=True` and an unnested key, and fault only the driver
steps the builders name; a step reached but never faulted, and an exit never
reached, is outside the suite: for example a failed `abort` or a failed delete
of the temporary (both pinned in `test_protocol.py` instead), the probes after a
refusal, `ensure_parents`, the metadata, content-shape and capability gates, a
refused open of a read, or a flat namespace. Each cell but the read's closed
guard, which asserts that no stream was opened, requires the state the kernel
left to equal what the compiled `KernelExit` or `KernelStep` computes from the
state at the exit, so I1 to I3 hold of the code on these exits to the extent
that suite's stated mapping from the fake driver's records onto the model's
states is faithful.

**Regenerating the compiled output.** Ghost-only changes (lemmas,
invariants, ghost variables, postconditions) erase at compile time and
produce no Python output — regeneration is not needed. Non-ghost changes
(method bodies, datatype definitions, function implementations) do require
regeneration, in any of the source files above, not only
`MemoryBackend.dfy`. The sources govern: each `<stem>-py/` is derived, and a
difference is fixed by regenerating, never by editing the output.
`scripts/check_dafny_oracle_fresh.py` holds that in CI's `verify-formal` job: it
rebuilds each oracle with the pinned Dafny and fails, naming each differing file
and line, when the committed tree is not what the sources compile to. Its
docstring states what it does not catch. After it, the same job runs
`tests/backends/dafny` and the oracle's conformance lanes (`-k dafny`) against
the committed `module_.py`, so a regenerated oracle is tested even when nothing
outside `sdd/` changed. Run the Docker wrapper:

```bash
bash scripts/dafny_verify.sh MemoryBackend.dfy     # confirm spec
bash scripts/dafny_translate.sh                    # translate + reorder
```

The translate wrapper uses the same Dafny release and SHA-256 pin as
`dafny_verify.sh`, writes `sdd/formal/MemoryBackend-py/` and
`sdd/formal/KernelProtocol-py/` (its default `FILES` list, which the freshness
check reads), and calls
`scripts/_dafny_classorder.py` on the output so classes are emitted in
importable order (ADT types → `Backend` → `default__` → `MemoryBackend` →
`MemoryBackendMinimal`).
No local Dafny toolchain required — Docker Desktop is enough. With native Dafny
at the pinned version on `PATH`, `hatch run check-dafny-oracle-fresh` runs the CI
freshness check locally.

Verify the regenerated module imports:

```bash
python -c "import sys; sys.path.insert(0, 'sdd/formal/MemoryBackend-py'); import module_"
```

**Running the oracle tests:**

```bash
pytest tests/backends/dafny tests/backends/conformance -k dafny -q
```

`verify-formal` runs it, and then `pytest tests/_kernel/test_protocol_oracle.py
tests/scripts/test_gen_protocol_diagram.py` for the second oracle and the
diagrams drawn from it. All tests should pass or self-skip
(an opt-in the fixture leaves off, a capability the oracle does not declare,
or a cell aimed at non-declaring backends). A conformance failure indicates a
conformance suite bug; a failure under `tests/backends/dafny` is the adapter's.

### Test conformance

Two distinct test suites cover the contract:

- **Conformance tests** (`tests/backends/conformance/`) drive
  every backend — including the compiled Dafny oracle
  (`DafnyOracleBackend`) — against the same scenarios. The oracle is
  the gate; if it passes, the test is known-correct.
- **Hypothesis property tests** (`tests/test_pbt_properties.py`,
  `tests/test_pbt_stateful.py`) stress-test the Python implementation
  with randomised inputs, using the Python `MemoryBackend` as the
  oracle.

Dafny postconditions and Hypothesis properties cover overlapping but
not identical surface — Dafny proves properties structurally for all
inputs a type admits; Hypothesis exercises a sampled subset against
the runtime. A 1:1 mapping is *not* maintained or enforced; the
authoritative list of current tests is the test suite itself, not a
mirror here.

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
| 7 | `WriteResult` field mapping + capability round-trip | WR-001a, WR-004, WR-008, WR-012, WR-013 | `BackendContract.dfy` |
| 8 | Seekable-read quality flag | SIO-008 | `BackendContract.dfy` |
| 9 | Root rule on write-shaped operations | BE-029 | `BackendContract.dfy`, `RootPath.dfy` |
| 10 | Close posture | BE-020 | `BackendContract.dfy` |
| 11 | Absent container | BE-021 § Reach | `BackendContract.dfy` |

Gaps 9 to 11 were added under BK-388, ahead of RFC-0017's kernel, which is
written against them (RFC-0017 D7). The ranking they encode is the one
spec 003 states: a closed terminal backend answers `BackendUnavailable` first
(BE-029), the key-decided root checks come next, a root `move`/`copy`
destination included (BE-018 § Precondition order), and every observed check
follows. On `Write`, WR-010's metadata gate sits between the root and the
observed checks, the order the kernel answers in (BE-030), since the gate is
capability data and held ahead of any I/O.
The first two, and `Write`'s gate, also state that nothing changed
(`fs == old(fs)`): the only error-path frames the model carries, possible
because each is keyed on the pre-state rather than on the result.
`MemoryBackend` matches the Python class (non-terminal close, a container
present from construction), so `MemoryBackendMinimal` witnesses the
`BackendUnavailable` branches. Both classes carry a `DropContainer` method,
which models the environment removing the container and is the only way
either class reaches the absent state. The Python oracle adapter wraps
`MemoryBackend` only: its `close()` drives `Close()` and the conformance
close-posture cells then probe it, so the lane runs the root rule and gap
10's non-terminal half. The class is non-terminal and the adapter never calls
`DropContainer`, so the lane reaches no `BackendUnavailable` branch and no
absent-container branch. The root rule
covers `write` and the `move`/`copy` source and destination; the other
file-shaped operations reach the root through the `IsDir` clause, because
`Valid()` keeps `Root` a `DirEntry` in every state. `DeleteFolder`'s clauses
leave the root's own answer free, since BE-029 leaves `delete_folder("")`
undefined, but not its survival; both refinements refuse it with
`InvalidPath`, as a class on the kernel does (spec 053 BE-031 § The root),
the Python `MemoryBackend` among them.

`DeleteFolder` requires a recursive delete of a present folder to succeed and
remove every key under it only when `CanonicalUnder(old(fs), path)` holds:
every key below `path` is `Canonical`, the model of BE-030's `listable`. Over
a key the rule omits, a walk on the kernel leaves it behind and answers
`DirectoryNotEmpty`, so there the trait permits that error or success
(spec 053 BE-031). The emptiness clauses carry the same guard. Both
refinements keep the unguarded clauses, because they remove every key under
`path`. `Canonical`'s comment in `BackendContract.dfy` states what it does
not model.

The trait takes well-formed paths, and on that domain `AddressesRoot` holds
for `Root` alone, so the trait by itself states the root rule for the
sentinel spelling only. BE-029 binds every spelling on the write clause, and
`RootPath.dfy` §5 carries that: `WriteKey`, `MoveKey` and `CopyKey` take the
raw write or `move`/`copy` destination key, fold every root spelling onto
`Root`, and prove the refusal from the trait's postconditions. A non-root key
must still be well-formed there. Those three are the oracle adapter's entry
for writes and `move`/`copy` destinations, so the conformance cells that run
all six spellings reach the oracle through the verified fold. The `move`/`copy` source and the read side
are not widened, because BE-029 decides them with `is_root`: the source must
be well-formed, and `Root` is its one root spelling.

Gap 7 was added under ID-151 after root-cause analysis of the ID-146
review. Review found ~24% of the 95 comments were shaped as per-operation
postcondition failures Dafny can prove directly: backends declaring a
capability (`WRITE_RESULT_NATIVE` or `USER_METADATA`) but silently
violating the corresponding `WriteResult`/`FileInfo` contract. The
`Write` postcondition chain now ties capability declaration to field
consistency and metadata round-trip; `WriteResultFromFileInfo` +
`WR008FieldMapping` pin the `head()` field table against the Dafny
datatype.

Honest scope: the capability-round-trip postcondition detects
*divergence* between `WriteResult` and the subsequently readable
`FileInfo` — not *absence*. A declaring backend that returns
`WriteResult` with all rich fields `None` and stores `FileInfo` with
all rich fields `None` still verifies. Empirical "rich fields were
actually populated" is a test-assertion and review concern, not a
Dafny-expressible postcondition. Store-layer composition (WR-018,
WR-019) and ext.write gating (EW-003) remain outside this layer — see
`sdd/formal/tla/` for the cross-layer track.

Gap 8 was added under ID-188. The `Read` return type widened from
`Result<seq<nat>>` to `Result<ReadStream>` (a `ReadStream(content,
seekable)` datatype) so the SIO-008 capability-gated postcondition
`CapSeekableRead in capabilities ==> r.value.seekable` has a stream-
shaped target to bind to. `CapLazyRead` was added as an advisory stub
variant in the same change: the Dafny model materialises content as a
`seq<nat>`, so SIO-009's "no I/O before first read" runtime protocol
property has no enforceable postcondition here and stays load-bearing
in Python conformance only.

Error-path frame conditions (gaps 1–2: `fs == old(fs)` on error) are
not machine-checked — the `r.Err?` discriminator taints method bodies
as specification-only in Dafny, preventing compiled assignments and
returns. `MemoryBackend` preserves the state by construction instead.
Gaps 9 and 10, and `Write`'s WR-010 gate, are the exception: their
frames key on the pre-state (`!old(Live())`, `AddressesRoot`,
`HasUserMetadata(metadata) && CapUserMetadata !in capabilities`), not on
`r`, and are verified.

### TLA+: the WR-018 bundling finding

The TLA+ layer arrived during spec 045 (WriteResult) review. The
ID-147b PoC found that a single Markdown paragraph (§ WR-018) bundled
four independently breakable claims — a class of reviewer blind-spot
Dafny cannot surface because it is cross-layer, not per-operation.
That finding motivated the spec-decomposition discipline and the
authoring rules captured in *What we use* above.
