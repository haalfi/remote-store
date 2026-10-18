# Research: How a spec should be designed (BK-457)

**Date:** 2026-10-18
**Backlog items:** BK-457
**Status:** Point-in-time record. Part A is the analysis of one maintainer
working session; Part B tests it against outside evidence; Part C records the
verdicts, the reviews weighed and what is open. The proposal it leads to is
[RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md), where the decisions
live. § 6 is to become doctrine in `sdd/SPEC-DESIGN.md` (maintainer's choice,
decision log below). **Completion standard** (maintainer's choice): an
evidence record adequate to decide RFC-0022, honestly graded, not an
independently reproducible review; unverified figures stay marked.
**Scope:** What makes a spec good, where one spec ends, which form and which
formal layer fit which kind of truth, worked on one operation: a streaming
read. Decision log: `sdd/decisions/6b9890d9-f718-508d-b861-aef8c0398c78.jsonl`.

**Method and its limits.** Part A reasoned from [spec
051](../specs/051-store-tree.md), the README and `CLAUDE.md` only, on purpose:
the question was what a spec should be, not what the repo's specs are. Spec 003
was not read, so § 2 and § 7 restate ground that spec 003's BE-032 and BE-033
already cover in part (§ 8). Part B came from a multi-agent research run whose
agents could read search-result summaries only, since every direct page fetch
failed. Markers: **[corroborated]** means a figure was checked against the
primary source by an external review, second-hand and not by this repo;
**[verify]** means no check yet. The source links were not opened from here.

**The core claim, a bounded synthesis.** Agents do not need more prose; they
need tighter feedback loops, refereed by the spec. It is a hypothesis drawn
from three findings in different settings, not one established result (§ 11):

| Finding | Setting | Compared | Outcome | Limit |
| --- | --- | --- | --- | --- |
| Vericoding | LLMs writing verified code from formal specs | Formal spec alone vs. with a natural-language description | No significant gain from the description **[corroborated]** | Function-level verified code, not engineering specs |
| TiCoder | Code generation with intent clarified by tests | With vs. without clarifying tests | Pass@1 up roughly 22 to 54 points **[verify]** | Simulated users; function level |
| ImpossibleBench | Agents given tests that contradict the spec | Cheating rate across benchmarks | 76% on Oneoff-SWEbench, 2.9% on Oneoff-LiveCodeBench **[corroborated]**; stricter prompts cut it substantially | Shows tests can be gamed, not that a spec is always right |

"Refereed by the spec" means the spec is what a conflict is decided against
after investigation, under `000-process.md` Rule 7; the spec itself can be
wrong (§ 9).

---

**Part A: The session's analysis (§§ 1–8)**

## 1. What made spec 051 good, and what did not

**Spec 051 holds up against its own obligation; its one defect was project
status inside the spec.** Its strengths: one invariant per section, each one
line; axioms (TREE-001 to TREE-008) apart from consequences (TREE-010 to
TREE-012), each consequence named with the lemma that proves it; a scope that
says what it leaves to other specs.

A first list of weaknesses did not survive the question *is this the spec's
obligation?*:

| Claimed weakness | Verdict | Whose it is |
| --- | --- | --- |
| Not tied to backends or operations | Stated scope, not a defect | Backend conformance and the operation specs |
| Static: no operations, no concurrency | Stated scope | Operation specs |
| Empty folders on flat backends | Not this spec's layer | Spec 003, BE-032 |
| Alphabet abstract, no length limits | Deliberate | The input layer (spec 004) |
| Exact name equality vs. coarser file systems | A stated choice with its price | — |
| Rationale is a frozen snapshot | Guards against drift | — |
| Proofs not checkable in a given session | The session's limit, not the spec's | — |

What remained: the layering paragraph carried time-bound status ("yet"), a
backlog ID, and spec 003's detail about flat backends. A backlog item points
to the spec it serves; a spec pointing back at the item goes stale when the
item closes and copies a relation the backlog already records. The sentence
worth keeping was what the sections are tested against. That fix shipped
beside this record.

## 2. One operation, walked

**Even the happy path of a read crosses many owners, and each step has its own
failure.** The plain read:

| # | Step | Owner | What can go wrong |
| --- | --- | --- | --- |
| 1 | Caller passes a key | Caller | Wrong type, empty |
| 2 | Validate the key | Store | `..`, leading or trailing `/`, `//`, control characters, length |
| 3 | Normalize (or not) | Store | Each rewrite creates an alias |
| 4 | Scope to the store root | Store | Escaping the root, nested scopes |
| 5 | Check the capability | Store | Backend cannot read |
| 6 | Hand the key to the backend | Store to backend | Whose key form is passed |
| 7 | Map the key to a native address | Driver | Encoding, reserved characters, case folding, length |
| 8 | Connect and authenticate | Driver | Network, expired token, throttling |
| 9 | Locate the entity | Kernel and driver | Missing, a folder, item and prefix both present, link |
| 10 | Open or fetch | Driver | Permission, concurrent replace, consistency, size |
| 11 | Translate native errors | Kernel | Unmapped, wrong type, credentials in the message |
| 12 | Return bytes or a stream | Backend to store | Who owns the stream |
| 13 | Return to the caller | Store | Fails mid-read, not closed, content changed since step 9 |

**A stream adds time: the handle outlives the call that opened it.** Steps 10
to 13 become a lifetime, and state appears (handle, position, the version seen
at open, the token in use):

| Step | Owner | What can go wrong |
| --- | --- | --- |
| Open the stream | Driver | Handle leaks if a later step raises |
| Wrap it | Store | Native errors escape from inside `read()` |
| Return it; the call ends | Store to caller | Ownership unclear |
| Read a chunk | Caller to driver | Drop, timeout, throttling; resume or fail |
| Content changes between chunks | Another writer | Torn read |
| Entity deleted or moved | Another writer | Continue, fail, or undefined, by backend |
| Seek or range read | Caller | Not seekable; position after an error |
| Credentials expire mid-read | Driver | Re-authenticate or fail |
| Caller idle | Caller | Server drops the connection; pool exhausted |
| Shared across threads or tasks | Caller | Not safe |
| End of stream | Driver | Truncation indistinguishable from the end |
| Close | Caller | Never, raises, twice |
| Store or backend closes first | Owner of the store | Orphaned handle |

## 3. The building blocks

**Ownership, state and time cross the components; they are not inside any
one.** The conceptual blocks the walk needed: caller; store (facade); key;
validator; scope; capabilities; backend contract; kernel (semantics shared by
backends); driver (native I/O); session (credentials, pool, its own lifetime);
transport (timeouts, retries); error model; stream; state carried by a stream;
consistency guard; lifecycle rules; observability. Each has a lifetime, from a
value with none (key) to one longer than any call (session, stream).

## 4. An external review, challenged

**Prose that mandates internal algorithmic order is the pitfall; the cure is a
contract an observer can check, not a different notation.** An external model
proposed a spec per component, topology and lifecycle files, Mermaid diagrams,
contract tables and Gherkin scenarios. Its central diagnosis held, and two
tests follow from it for every sentence: could two different correct
implementations both satisfy it, and could a black-box test fail it?

| Proposal | Verdict |
| --- | --- |
| Let types enforce what types can (a key as a value, not a string) | Holds: an order that is impossible to bypass needs no prose |
| Pre, post and error contracts per boundary | Holds |
| States and allowed transitions instead of narrative | Holds |
| Shared contract tests unchanged across drivers; leak detectors | Holds |
| A spec per component, plus a topology file | Fails: the hard properties cross components, and the topology restates the component files |
| Diagrams and tables as the spec | Fails as illustration; for a lifecycle, see below |
| Gherkin scenarios as the spec | Fails: a scenario covers one case and an invariant all of them; Given and When invite step order |
| Several of its own rules (capture the version "at the exact moment", regex masking, "reverse order", a named design pattern) | Fail its own diagnosis: they prescribe how |

**A state diagram reconsidered.** The maintainer's objection held: for a
lifecycle a state diagram is clearer than any sequence of sentences. The
session concluded it can be the source when closed world (an undrawn transition
is forbidden), single-sourced and checked against the model. Part B refines
the direction: the TLA+ module is the source and the diagram a checked view
(§ 10). Mechanism the tests remove from a spec is relocated to an ADR, a design
note or a task plan, not deleted (§ 11).

## 5. Proof instead of review

**Formal layers fit kinds of truth, and each needs a bridge to the code or it
proves only a model.**

| Part of the flow | Property | Tool |
| --- | --- | --- |
| Validator | Accepts exactly the keys spec 051 admits; no two inputs map to one key | Dafny |
| Scope | Never escapes the root; nested scopes compose | Dafny |
| Capability gate | No driver call for an undeclared capability | Dafny or tests |
| Error model | Total mapping | Dafny; "no secret in a message" stays a test |
| Stream lifecycle | Closed once, no read after close, one owner | TLA+ |
| Concurrent writer | One version or a fault, where the backend can tell | TLA+ with an environment model |
| Close order | No orphan, a defined result for every order | TLA+ |
| Retry and resume | Terminates; no duplicated or skipped bytes | TLA+, bounded obligations only (§ 9) |
| Native I/O | — | Contract tests only |

Review then moves from "is the behaviour right?" to "is this the right
property, and are the assumptions realistic?". Part B says how far each bridge
carries (§ 9), and in what order to adopt the tools:

**Graduation path.** Every clause starts with contract tests, the baseline
that binds any spec to any backend. A formal model is added only where review
measurably fails: ownership, interleavings, time. It governs only from the
level its bridge reaches (§ 9's ladder). The tools are adopted one kind at a
time, Dafny for single calls first since its bridge exists, not all at once.

## 6. What makes a spec good

**A spec is good when its clauses are valid, consistent and checkable against
a stated domain, and every gap is declared.** Being falsifiable is necessary,
not sufficient: a testable clause can still be wrong, and a valid requirement
that no finite test can witness is declared as an assumption rather than
dropped. Eight properties, each with a check:

| Property | Means | Checked by |
| --- | --- | --- |
| Well founded | Every clause has a traceable reason and an owner | Axioms apart from consequences; a countermodel per axiom |
| Verifiable | Every clause has a defined witness of violation, or is declared an assumption | The two tests of § 4 |
| Lasting | True without edits as the project moves | The six-month test; links point at the spec |
| Correct | Says what the system must do, and it can | Proof or model check, through a bridge; contract tests |
| Free of contradictions | No two clauses or neighbouring specs disagree | One home per fact; the model has an instance |
| No unstated gaps | Whatever is open is declared open | Scope and non-scope; closed world; assumptions |
| Placed | Covers only its own layer | § 1's defect |
| Comprehensible | Leads with its claim, in the form its content needs | Rule 7; § 4's diagram |

An external review proposed five criteria; they map onto these: semantic
validity to *correct*, consistency to *free of contradictions*, observability
to *verifiable*, evidence coverage (a stated domain) to D7's "Tested against",
traceability to *well founded*.

## 7. The streaming read, split

**A candidate split: where the kind of truth changes.** It is a plausible
design, not a shown optimum: the evidence (§ 11) does not establish cutting by
property, and the alternative of one operation contract with linked lifecycle
and consistency models is not yet compared (§ 15).

| Spec | Subject | Kind | Authority |
| --- | --- | --- | --- |
| Store tree | What a key denotes | Structure | Alloy and Lean (spec 051) |
| Key admission | Input to key, or rejected | Function | Dafny |
| Scope | Store-relative key to backend key | Function | Dafny |
| Read contract | One `read(k)` at the moment it opens | Single call | Dafny and contract tests |
| Stream lifecycle | A handle from open to close | Lifetime | TLA+ |
| Read consistency | Open stream and a concurrent writer | Lifetime and environment | TLA+ with assumptions |
| Error model | Native failure to library error | Function | Dafny and tests |
| Session and transport | Retry, resume, timeout | Liveness | TLA+, bounded obligations only |

Each takes spec 051's skeleton: overview (claim and scope), terms, one
invariant per section, assumptions where the environment matters, notes for
derived properties, tested against. Part B adds a second cutting axis inside a
kind, the interface contract between layers (§ 10).

**Decided in the session:** key admission rejects non-canonical input rather
than normalizing it; the stream lifecycle comes first. **Left to the key
admission spec:** who normalizes before admission (the caller, a helper, or
spec 004's input layer), so a caller is not left guessing where sanitizing
belongs.

## 8. A lifecycle drafted

**A handle's life is three states, one owner at a time, and a release that
happens once.** States Open, Faulted, Closed; owners backend, store, caller.
Transitions: open to Open; read keeps Open; fault or session close moves Open
to Faulted; close moves Open or Faulted to Closed; close on Closed is a no-op.
Invariants drafted: one state at a time; only the drawn transitions; Closed
terminal; one owner, handed only backend to store to caller; an owner that
cannot hand over closes; resources released once, on entering Closed; Faulted
and Closed deliver no bytes; a session close faults its open streams and the
owner still closes them; position never decreases. Not guaranteed: that a
caller ever closes.

**Open before it can inform implementation** (external review): who owns and
releases a stream faulted by a session close; what a re-close does when the
first close failed to release; whether bytes obtained before a fault may still
be returned; which of a racing read and close wins, and whether that read may
return partial data; whether an owner that cannot hand over can always close;
whether a non-decreasing position defines correctness under retry, partial
reads and range requests.

**Decided in the session:** a second close is a no-op; a session close faults
its open streams.

**Overlap.** Spec 003's BE-033 already states a lifecycle-scoped interaction
protocol (ownership, transitions, cancellation), and BK-454 and BK-455 hold the
read handle and the `Session` state set. This draft was made without reading
them; reconciling it is their work, and RFC-0022 uses it only as an
illustration.

---

**Part B: Outside evidence (§§ 9–11)**

## 9. Model-to-code bridges: every working bridge is empirical

**A formal layer governs only the class of executions its bridge observes or
generates, and no bridge in industrial use is a proof.**

Industry has converged on bridges that test agreement between model and code without proving it. **Cedar** (AWS) runs differential random testing: millions of generated inputs go to both the Rust production code and a Lean model, and any disagreement counts as a bug ([arXiv 2407.01688](https://arxiv.org/html/2407.01688v1)). Cedar does not ship a release unless its model, proofs and differential tests are all current. Its authors report **21 bugs** found by differential and property testing combined ([paper](https://assets.amazon.science/d3/86/99db1aa142ffb6981d86dc849e4c/how-we-built-cedar-a-verification-guided-approach.pdf)); a later poster reports **25** from differential random testing alone ([POPL'24 SRC poster](https://bhaktishh.github.io/papers/popl-24-src-poster.pdf)). The two counts use different boundaries **[corroborated]**. This is the same pattern as remote-store's Dafny oracle with twin parity. Dafny's Python backend is real but immature: the reference manual still calls it "still under development" ([DafnyRef](https://dafny.org/dafny/DafnyRef/DafnyRef)), generated code uses Dafny runtime types, not native ones ([arXiv 2501.06283](https://arxiv.org/pdf/2501.06283)), and its sets and maps run slower than native Python ([arXiv 2606.32007](https://arxiv.org/pdf/2606.32007)). AWS ships Python transpiled from Dafny in its Cryptographic Material Providers Library ([repo](https://github.com/aws/aws-cryptographic-material-providers-library)). For an oracle that runs only in tests these limits are acceptable; the consequences are to pin the Dafny version, regenerate in CI, and treat the adapter between runtime types and native types as unverified glue.

TLA+ has two bridges, and the evidence ranks them. **Trace validation** replays logged runs through TLC. CCF's verification work found **six bugs, five safety and one liveness [corroborated]**, with logging taking about **one day** and a **400-line** trace spec **[verify]**. Adoption also drove **88 commits to the trace spec and 107 changes to the consensus spec [corroborated]**, and diagnosing mismatches was the dominant cost ([NSDI'25](https://www.usenix.org/system/files/nsdi25-howard.pdf)). MongoDB cancelled its 2020 trace checking of the server ("cost more effort than it was worth"; two engineers spent **10 weeks** without trace-checking one spec, effort largely specific to `RaftMongo.tla` **[corroborated]**), because of the gap between a highly abstract spec and multithreaded implementation state ([MongoDB blog](https://www.mongodb.com/company/blog/engineering/conformance-checking-at-mongodb-testing-our-code-matches-our-tla-specs); [VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf)). The same paper reports that **model-based test generation** reached **100% branch coverage** of a sequential algorithm, against 21% for handwritten tests and 92% for AFL fuzzing **[corroborated]**; branch coverage is not behavioural correctness, and MongoDB's 2025 transactions work used generation again ([VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf)). The authors of the trace-validation method state that it "does not provide formal correctness guarantees" ([arXiv 2404.16075](https://arxiv.org/abs/2404.16075v2)). No Python tooling exists for either bridge: the tools are Java (Kuppe/Merz) and Rust (Quint/Apalache ITF consumers such as [tla-connect](https://docs.rs/tla-connect)). A Python ITF replayer would have to be built in-house, but ITF is plain JSON ([Apalache ADR-015](https://apalache-mc.org/docs/adr/015adr-trace.html)). For concurrent clients, OmniLink's black-box method is the closest fit: record `(op, args, result, t_start, t_end)` and check the record against a sequential model ([arXiv 2601.11836](https://arxiv.org/abs/2601.11836)), a single 2026 preprint.

**Liveness.** No finite trace can falsify a liveness property, so no bridge
reaches it beyond bounded obligations. Proving liveness in TLA+ also needs
fairness conditions (weak or strong fairness), which can hide model errors or
blow up the state space; a fairness condition is an assumption about the
environment and belongs in the spec's Assumptions section like any other.
Liveness model checking is a design aid, not a guarantee.

The Alloy and Lean store-tree axioms got the least attention. Their realistic bridge is to assert the axioms as Hypothesis properties on generated trees, which checks samples only. Cedar's move from Dafny to Lean, made because Dafny handled meta-theoretic proofs poorly, shows that matching the tool to the kind of property has real cost consequences ([Cedar RFC 0032](https://github.com/cedar-policy/rfcs/blob/main/text/0032-port-formalization-to-lean.md)).

| Bridge | Establishes | Typical failure | Fit for remote-store |
| --- | --- | --- | --- |
| Differential oracle | Agreement on generated single-call inputs and outputs | Oracle and code share one misreading of the contract | Strong: the Dafny oracle exists |
| Model-based test generation | Generated executions of the model run against the code | Generated runs miss adversarial interleavings | Lifecycles, first: MongoDB's record favours it over trace checking |
| Trace validation | Observed runs are permitted by the model | The gap between implementation state and model state | Lifecycles, second: CCF made it work at real cost; MongoDB cancelled |
| Black-box history checking | Concurrent histories satisfy a concurrency contract | Nondeterminism, timeouts, partial failure | Highest value, highest cost; one 2026 preprint |

From it follows a ladder of what a clause can claim:

1. **Unbridged model:** informs review; a conflict with a test is a finding to investigate, not a win for either side.
2. **Differential oracle:** governs single-call semantics on the generated input space.
3. **Generated tests:** govern the generated execution space, not every behaviour.
4. **Trace-validated:** governs that observed transitions are model-permitted.
5. **History-checked:** governs observable concurrent histories, under the checker's assumptions.
6. **Liveness:** governs only when reduced to a bounded obligation a test can fail (for example, a retry completes within N attempts under injected delay M); unbounded eventual progress stays a design assertion.

A clause's level changes when a bridge is built, so it is derived from the
bridges and their tests, not written into the spec by hand.

**The ladder grades verification confidence, not normative authority.** Which
artifact states the contract, and how a conflict between contract, model, test
and code is resolved, stays with `000-process.md` Rule 7: a test can encode a
bug, a bridged model can rest on a mistaken contract, and a model can expose a
contradiction before any bridge exists. A conflict triggers investigation, not
automatic deference to either artifact.

## 10. Lifecycle as checked source: the module wins, the diagram is a checked view

**Wherever a diagram is "the source", a formal executable notation sits under
it; Mermaid has none, so the TLA+ module is the source and the diagram a view
checked against it.**

Every such case has a formal notation underneath: SCXML ([W3C](https://w3.org/TR/scxml/)), XState with bidirectional code and diagram views ([Stately](https://stately.ai/blog/2023-11-20-stately-studio-2-0)), or Stateflow (background knowledge, unverified). Mermaid's guards are free label text, and its docs define no execution semantics ([stateDiagram.md](https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/docs/syntax/stateDiagram.md)). State diagrams still reportedly use the legacy JISON parser rather than the new `@mermaid-js/parser` (secondary sources, **[verify]**). The only Python wrapper needs Node and has no releases ([mermaid-parser-py](https://github.com/20001LastOrder/mermaid-parser-py)). Twenty-five years of translating UML state machines to model checkers have produced no agreed semantics; translations drop or redefine composites, history and fork/join ([survey, arXiv 2407.17215](https://arxiv.org/pdf/2407.17215)).

AWS's P puts authority in the executable state-machine model and links it to production logs through PObserve ([ACM Queue](https://queue.acm.org/detail.cfm?id=3712057)). A plain diagram cannot express data, guards, multiplicity, ownership, interleavings or liveness, so the TLA+ module strictly contains the diagram's information. TLC does not produce a lifecycle diagram: its `-dump dot` output shows the concrete state graph and is readable only up to about **30 to 100 states [verify]** ([vscode-tlaplus wiki](https://github.com/tlaplus/vscode-tlaplus/wiki/Visualizing-States)). The recommended check: a small in-repo Python parser accepts a declared Mermaid subset (flat states, `[*]`, `A --> B : ActionName`) and rejects everything else; the phase relation is derived from a tiny TLC configuration by projecting each state onto a named phase variable, or from a declared mapping of actions to phases; and the check asserts **set equality** with the drawn edges. Equality enforces the closed world both ways: no reachable transition is missing from the diagram, and no drawn transition is dead. No published experience report of such a drift check was found, so this part is reasoned rather than observed. Cross-object constraints, such as "session Closed implies all its handles are Closed", stay as TLA+ invariants and do not appear as edges.

On Gherkin, the evidence is weak and mostly negative. Studies report long, repetitive specs and a heavy maintenance burden ([Patkar et al. 2022](https://scg.unibe.ch/assets/archive/papers/Patk22b.pdf); [Islam 2024](https://theses.gla.ac.uk/84085/1/2024IslamPhD.pdf)). Gherkin scenarios are traces, and traces cannot state "any undrawn transition is forbidden".

## 11. How industrial teams cut and govern specs, and what agents implement well

**Teams cut by protocol and guarantee, a model governs only where it is bound
to the code, and agents do best with short contracts whose tests they can run.**

Published spec inventories are cut by **algorithm or guarantee, not by service**. AWS's 2015 table lists separate specs for S3's network algorithm and redistribution, DynamoDB replication, and EBS volume management: 804, 645, 939 and 102 lines **[corroborated]** ([Lamport excerpt](https://lamport.azurewebsites.net/tla/amazon-excerpt.html)). The Cosmos DB spec covers the five client-observable consistency levels ([arXiv 2210.13661](https://arxiv.org/pdf/2210.13661)). RaftMongo.tla covers one gossip sub-protocol ([VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf)). Elastic organises its models by algorithm ([repo](https://github.com/elastic/elasticsearch-formal-models)). The partial counter-pattern is ShardStore: reference models per component, at about **1%** of code size **[verify]** and reused as test mocks, yet a correctness argument split **by execution kind** (sequential, crash, concurrent), close to § 7's kinds ([SOSP 2021](https://dl.acm.org/doi/pdf/10.1145/3477132.3483540)). MongoDB 2025 cuts at an **explicit interface contract** between the protocol and the storage layer, so each side can be conformance-tested on its own ([VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf)), the closest analogue for a library with several backends. No source states "cut by property" as a rule; the pattern is inferred from how the inventories are organised, and no study measures whether it yields fewer contradictions. A systematic review of industrial TLA+ names choosing the abstraction level as the main obstacle ([arXiv 2411.13722](https://arxiv.org/abs/2411.13722)); six kinds means six such choices.

On authority, no company publishes a general rule for resolving conflicts; authority is implicit in the workflow. Cosmos DB's public docs point to the TLA+ repository as the precise definition, and the spec corrected two documentation errors ([Microsoft Learn](https://learn.microsoft.com/azure/cosmos-db/consistency-levels)). Cedar gates releases on its model. Elastic, by contrast, warns that its models "can differ to their implementations in substantial ways", and Datadog's model was not guaranteed to stay aligned with the code ([Datadog](https://datadoghq.com/blog/engineering/formal-modeling-and-simulation)). A model governs only where it is bound to the code. Woodcock and Larsen's 2026 critical evaluation says the public AWS evidence is selective and keeping specs current is a challenge ([ACM DL](https://dl.acm.org/doi/10.1145/3815784)); its detail was not read.

For agents, the strongest datum is the vericoding benchmark: **12,504 formal specs**, with LLMs producing verified code for about **82% of the Dafny specs**, and **adding natural-language descriptions did not significantly improve results** ([arXiv 2509.22908](https://arxiv.org/pdf/2509.22908)) **[corroborated]**. Over one year of model progress, pure-Dafny success rose from 68% to 96% in the arXiv abstract and to 97% in an OpenReview version; quote the version of record. A single thesis reports that explicit pre/postconditions raise pass@k over natural-language descriptions ([ERAU](https://commons.erau.edu/edt/927/)), weak evidence. Spec-kit, Kiro and Tessl all separate the *what* from the *how* and move the *how* into a plan or design document ([Böckeler](https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html); [Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/spec-driven-development)). They relocate it rather than delete it, and step plans measurably help generation: self-planning gives up to **+25.4% relative pass@1 [verify]** ([arXiv 2303.06689](https://arxiv.org/pdf/2303.06689)). EARS, Kiro's syntax for acceptance criteria, has **no measured accuracy evidence** for agents ([Wikipedia](https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax)).

Examples cut both ways. TiCoder's test-driven clarification raised pass@1 by roughly **22 to 54 points** under simulated users **[verify]** ([arXiv 2208.05950](https://arxiv.org/pdf/2208.05950)). Models also pattern-match examples ([arXiv 2411.06774](https://arxiv.org/html/2411.06774)), and they cheat on tests that contradict the spec: GPT-5 exploited contradictory tests in **76%** of Oneoff-SWEbench tasks but only **2.9%** of Oneoff-LiveCodeBench tasks **[corroborated]** ([ImpossibleBench, arXiv 2510.20270](https://arxiv.org/pdf/2510.20270)), and stricter prompts cut the rate substantially. That supports keeping the normative claim in one place and tracing tests to it, with agents pointed at those tests. On structure, adherence falls as the number of instructions grows: the best models reach about **68% at 500 instructions**, with a bias towards earlier instructions **[verify]** ([IFScale, arXiv 2507.11538](https://arxiv.org/html/2507.11538v1)), and accuracy drops for content placed mid-context ([Lost in the Middle, arXiv 2307.03172](https://arxiv.org/abs/2307.03172)). Neither benchmark measures code. Practitioners name spec verbosity and review burden as the main failure of spec-driven development tooling ([Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/spec-driven-development)).

---

**Part C: Verdicts, reviews and open questions (§§ 12–15)**

## 12. Verdicts per RFC decision

**The evidence supports the direction of every RFC-0022 decision examined and
contradicts none; four of five need sharper wording, and the largest change is
that authority depends on a bridge, not on a layer.**

| Decision | Verdict | Evidence strength | Proposed rewording (where "changes how") |
| --- | --- | --- | --- |
| D1 contract only, never mechanism | Changes how | Moderate for the what/how split (vericoding null result, framework consensus); weak for contracts beating prose (one thesis) | "A spec states only the observable contract. Mechanism is relocated to ADRs, design notes or the per-task plan, not deleted. Mechanism a caller can observe (side-effect order, visible retries) is contract and stays." |
| D3 split by kind of truth | Changes how | Moderate, inferred from spec inventories; no rule stated anywhere and no contradiction-rate data | "Split by kind of truth first, then by interface contract (API to backend) within a kind. A property that spans kinds names one owning spec and links from the others." |
| D4 closed-world Mermaid, examples in tests, no Gherkin | Holds; source question resolved | Strong that the executable model holds authority; weak for drift-check practice (none found); weak-moderate against Gherkin | "The TLA+ module is the source. The Mermaid diagram is a hand-written projection, checked for set equality of edges (labels = action names) against the phase projection of a small TLC config. Mermaid is limited to a declared subset parsed in-repo. Cross-object constraints stay as invariants." State the divergence from spec-kit's Given/When/Then explicitly. |
| D5 the proving layer governs, only through a bridge | Changes how | Moderate-strong (Cedar, CCF, MongoDB, Elastic/Datadog disclaimers, Kuppe/Merz) | "A formal layer governs a clause only once a bridge binds it to tests, and only as far as § 9's ladder reaches. Until then its result is informational about the model. Liveness governs only as a bounded obligation, and fairness conditions are assumptions. The ladder grades verification confidence, not authority: a conflict between contract, model, test and code is investigated and resolved under Rule 7." Adopt the tools along § 5's graduation path. |
| D7 one skeleton per spec | Holds, with one condition | Moderate (IFScale and lost-in-the-middle are not code-specific; TiCoder and ImpossibleBench are strong but idealised) | Condition only: "Tested against" must name runnable tests that the agent is directed to read or run, derived from the tests' spec marks rather than listed in the spec. |

## 13. Evidence quality

| Class | Findings |
| --- | --- |
| Corroborated against a primary source (second-hand) | CCF bug and commit counts; MongoDB's ten-week outcome and 100% branch coverage; vericoding headline results; AWS 2015 line counts; Cedar's bug counts and method; ImpossibleBench's split |
| Primary source, figure unchecked | CCF's one-day and 400-line costs; TiCoder, self-planning and IFScale figures; ShardStore's 1% |
| Inferred, not observed | Industry cuts specs by property; diagram-to-model drift check; the bridge ladder itself; the graduation path; the core claim as a synthesis |
| Single source or preprint | Black-box history checking (OmniLink); Dafny-to-Python performance; the agent benchmarks (vericoding, ImpossibleBench, IFScale) are arXiv preprints and may change on publication |

## 14. External reviews considered

**Five external AI reviews were weighed on 2026-10-18, in three rounds; each
finding was adopted, deferred to the RFC or guide, or rejected with a reason.**
Round one, Perplexity and Gemini on the outside evidence; round two, Gemini on
the session analysis; round three, ChatGPT and Gemini on this merged record in
PR #1160's review.

**Adopted in round three:** the core claim recast as a bounded synthesis with
its three findings' settings and limits (ChatGPT); falsifiability as necessary
but not sufficient, with untestable requirements declared as assumptions
(ChatGPT, § 6); the ladder as verification confidence, not normative
authority, with conflicts resolved under Rule 7 (ChatGPT, § 9); § 7's split
marked a candidate (ChatGPT); the lifecycle's open questions (ChatGPT, § 8);
MongoDB's coverage figure corroborated by ChatGPT's own check (§ 9); preprints
marked as such (Gemini, § 13). **Not adopted in round three:** the dependence
on this repo's artifacts (Gemini), since this is the repo's own record and
those links are its purpose; the missing Python tooling as a new finding
(Gemini), already stated in § 15 and RFC-0022's Impact. Source versions could
not be pinned, since no page could be fetched.

**Adopted:** the figure checks and precision fixes (Perplexity); the bridge
taxonomy (Perplexity), reordered because its "trace validation strong for
lifecycles" contradicts MongoDB's record and CCF's cost; the governance ladder
and bounded liveness (Perplexity, matching Gemini's "binding levels"); the
evidence-quality table (Perplexity); "agents do not need more prose; they need
tighter feedback loops" (Gemini), qualified with "refereed by the spec" and
made the core claim; a graduation path for adopting the formal tools (Gemini,
second review), now § 5; fairness conditions as assumptions (Gemini, second
review), now § 9.

**Recorded as candidates for the RFC or guide, not research findings:** a
bridge acceptance checklist (observable interface, encoding of runtime values
into model values, generation or capture method, pass criterion, known blind
spots, owning CI job), which also covers the unverified glue between Dafny
runtime types and Python; "a clause names a test that fails if it is violated,
and an agent stops and reports a conflict between test and clause rather than
changing either", whose second half `000-process.md` Rule 7 already covers;
and who normalizes a key before admission (Gemini, second review), left to the
key admission spec (§ 7).

**Not adopted:** binding levels tagged on each clause by hand (Gemini), since a
level changes as bridges are built and a hand tag is project state in a spec;
test IDs listed in a spec footer (Gemini), which reverses the link direction
that spec marks already give; "Gherkin bloats the context" (Gemini), which no
source supports; a spec index with per-component context slices (Gemini),
which concerns how agents read specs and which the repo's lookup commands
already serve; a mandatory pre-flight check before writing a spec (Gemini,
second review), which already exists as the orient step `CLAUDE.md` § Backlog
requires before planning item work, and which found § 8's overlap in this
session.

## 15. Open questions and gaps

**Six questions stay open, and the decision-relevant figures left to check are
few.** The first is how an unbridged TLA+ clause interacts with
`000-process.md` Rule 7: CCF's 107 changes to its consensus spec suggest the
spec is wrong about as often as the code once a bridge exists. The second is
whether ITF-driven generation can be built at reasonable cost for
remote-store's lifecycles: no Python precedent exists, and the action-to-API
mapping carries the abstraction-gap risk that sank MongoDB's trace checking.
The third is whether nondeterministic backends (S3, Azure) make black-box trace
checking impractical. The fourth is the Gherkin question for agents: no
evidence shows that Given/When/Then or EARS helps or hurts accuracy, so D4
stands on maintenance and closed-world grounds. The fifth is whether any of
this transfers to multi-file agent work, since all spec-form evidence is at
function or class level. The sixth is whether § 7's split beats one operation
contract with linked lifecycle and consistency models, judged by duplication,
cross-reference burden, change propagation and test ownership; no comparison
has been made.

The gaps: no comparison of contradiction rates between cutting by property and
by component; no experience report of a diagram-to-model drift check; the TLC
`-dump` flags (`actionlabels`) unconfirmed; Woodcock and Larsen 2026 not read
in detail; the current Python feature table for Dafny not retrieved; Alloy
barely covered; Python linearizability checkers not researched. The
decision-relevant **[verify]** figures left are CCF's one-day and 400-line
costs.

## Sources

**Bridges and Dafny:** [Cirstea et al., arXiv 2404.16075](https://arxiv.org/abs/2404.16075v2) · [Howard et al., NSDI'25](https://www.usenix.org/system/files/nsdi25-howard.pdf) · [Davis et al., VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf) · [MongoDB conformance blog](https://www.mongodb.com/company/blog/engineering/conformance-checking-at-mongodb-testing-our-code-matches-our-tla-specs) · [Schultz & Demirbas, VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf) · [OmniLink, arXiv 2601.11836](https://arxiv.org/abs/2601.11836) · [Apalache ITF ADR-015](https://apalache-mc.org/docs/adr/015adr-trace.html) · [tla-connect](https://docs.rs/tla-connect) · [Hypothesis stateful testing](https://hypothesis.works/articles/rule-based-stateful-testing/) · [Dafny Reference Manual](https://dafny.org/dafny/DafnyRef/DafnyRef) · [arXiv 2501.06283](https://arxiv.org/pdf/2501.06283) · [AxDafny, arXiv 2606.32007](https://arxiv.org/pdf/2606.32007) · [AWS MPL](https://github.com/aws/aws-cryptographic-material-providers-library) · [Cedar, arXiv 2407.01688](https://arxiv.org/html/2407.01688v1) · [Cedar RFC 0032](https://github.com/cedar-policy/rfcs/blob/main/text/0032-port-formalization-to-lean.md) · [Amazon Science: Cedar](https://www.amazon.science/blog/how-we-built-cedar-with-automated-reasoning-and-differential-testing) · [Cedar paper](https://assets.amazon.science/d3/86/99db1aa142ffb6981d86dc849e4c/how-we-built-cedar-a-verification-guided-approach.pdf) · [Cedar POPL'24 SRC poster](https://bhaktishh.github.io/papers/popl-24-src-poster.pdf)

**Lifecycle:** [SCXML](https://w3.org/TR/scxml/) · [Stately Studio 2.0](https://stately.ai/blog/2023-11-20-stately-studio-2-0) · [UML verification survey, arXiv 2407.17215](https://arxiv.org/pdf/2407.17215) · [Mermaid stateDiagram docs](https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/docs/syntax/stateDiagram.md) · [mermaid-parser-py](https://github.com/20001LastOrder/mermaid-parser-py) · [vscode-tlaplus: Visualizing States](https://github.com/tlaplus/vscode-tlaplus/wiki/Visualizing-States) · [ACM Queue: AWS correctness practices](https://queue.acm.org/detail.cfm?id=3712057) · [Patkar et al. 2022](https://scg.unibe.ch/assets/archive/papers/Patk22b.pdf) · [Islam 2024 thesis](https://theses.gla.ac.uk/84085/1/2024IslamPhD.pdf)

**Industrial structure:** [AWS 2015 excerpt](https://lamport.azurewebsites.net/tla/amazon-excerpt.html) · [ShardStore, SOSP 2021](https://dl.acm.org/doi/pdf/10.1145/3477132.3483540) · [Cosmos DB, arXiv 2210.13661](https://arxiv.org/pdf/2210.13661) · [Cosmos consistency docs](https://learn.microsoft.com/azure/cosmos-db/consistency-levels) · [Elastic formal models](https://github.com/elastic/elasticsearch-formal-models) · [Datadog formal modeling](https://datadoghq.com/blog/engineering/formal-modeling-and-simulation) · [Industrial TLA+ SLR, arXiv 2411.13722](https://arxiv.org/abs/2411.13722) · [Woodcock & Larsen 2026](https://dl.acm.org/doi/10.1145/3815784) · [Jackson & Wing 1996](https://people.csail.mit.edu/dnj/publications/ieee96-roundtable.html)

**Agents:** [Vericoding, arXiv 2509.22908](https://arxiv.org/pdf/2509.22908) · [ERAU thesis](https://commons.erau.edu/edt/927/) · [nl2postcond, arXiv 2310.01831](https://arxiv.org/pdf/2310.01831) · [Böckeler, SDD tools](https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) · [Thoughtworks Radar: SDD](https://www.thoughtworks.com/radar/techniques/spec-driven-development) · [EARS](https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax) · [Self-planning, arXiv 2303.06689](https://arxiv.org/pdf/2303.06689) · [TiCoder, arXiv 2208.05950](https://arxiv.org/pdf/2208.05950) · [arXiv 2411.06774](https://arxiv.org/html/2411.06774) · [ImpossibleBench, arXiv 2510.20270](https://arxiv.org/pdf/2510.20270) · [IFScale, arXiv 2507.11538](https://arxiv.org/html/2507.11538v1) · [Lost in the Middle, arXiv 2307.03172](https://arxiv.org/abs/2307.03172)
