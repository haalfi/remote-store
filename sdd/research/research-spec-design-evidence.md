# Research: Outside evidence for RFC-0022's spec design (BK-457)

**Date:** 2026-10-18
**Backlog items:** BK-457
**Status:** Interim. To be merged with
[`research-spec-design.md`](research-spec-design.md) into one record after
maintainer review, and then deleted. Tests
[RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md) against outside
evidence; produced by a multi-agent research run whose agents could read
search-result summaries only, since every direct page fetch failed. Two
external AI reviews (Perplexity, Gemini) were then weighed (§ External reviews
considered). Markers: **[corroborated]** means a figure was checked against the
primary source by an external review, second-hand and not by this repo;
**[verify]** means no check yet. The source links were not opened from here.

## Outside evidence backs RFC-0022, with five amendments

Outside evidence supports the direction of every RFC-0022 decision examined here. No decision is contradicted. Four of the five need rewording, because the evidence says something more specific than the draft does. The largest change is to D5: in industry, a formal model governs code only through a mechanical bridge, and the bridges differ a lot in maturity. The Dafny-to-Python oracle is a well-precedented bridge for single-call semantics. TLA+ lifecycles have a credible bridge that remote-store would have to build itself. Multi-client concurrency has an expensive bridge with one documented failure. Liveness has essentially no bridge. D4's open question has a clear answer: make the TLA+ module the source, and keep the Mermaid diagram as a hand-written projection that is checked for set equality against it. D3 holds, but practice adds a second axis, cutting at interface contracts. D1 should say mechanism is *relocated*, not forbidden. D7's skeleton holds, provided agents can actually reach the "tested against" tests. **Caveat on evidence quality:** all four researchers worked only from search-result summaries and abstracts. Every direct page fetch (arXiv, ACM, USENIX, MongoDB, martinfowler.com, mermaid.js.org and others) failed in the sandbox. Figures below carry **[corroborated]** or **[verify]** as defined in the header; the RFC quotes neither until someone has checked the full text.

## Model-to-code bridges: every working bridge is empirical, and maturity varies by kind

Industry has converged on bridges that test agreement between model and code without proving it. **Cedar** (AWS) runs differential random testing: millions of generated inputs go to both the Rust production code and a Lean model, and any disagreement counts as a bug ([arXiv 2407.01688](https://arxiv.org/html/2407.01688v1)). Cedar does not ship a release unless its model, proofs and differential tests are all current. Its authors report **21 bugs** found by differential and property testing combined ([paper](https://assets.amazon.science/d3/86/99db1aa142ffb6981d86dc849e4c/how-we-built-cedar-a-verification-guided-approach.pdf)); a later poster reports **25** from differential random testing alone ([POPL'24 SRC poster](https://bhaktishh.github.io/papers/popl-24-src-poster.pdf)). The two counts use different boundaries **[corroborated]**. This is the same pattern as remote-store's Dafny oracle with twin parity, so D5's single-call clause has the strongest precedent of any. Dafny's Python backend is real but immature. The reference manual still calls it "still under development" ([DafnyRef](https://dafny.org/dafny/DafnyRef/DafnyRef)). Generated code uses Dafny runtime types, not native ones ([arXiv 2501.06283](https://arxiv.org/pdf/2501.06283)), and its sets and maps run slower than native Python ([arXiv 2606.32007](https://arxiv.org/pdf/2606.32007)). Even so, AWS ships Python transpiled from Dafny in its Cryptographic Material Providers Library ([repo](https://github.com/aws/aws-cryptographic-material-providers-library)). For an oracle that runs only in tests these limits are acceptable. The practical consequences are to pin the Dafny version and regenerate in CI, and to treat the adapter between runtime types and native types as unverified glue.

TLA+ has two bridges, and the evidence ranks them. **Trace validation** replays logged runs through TLC. CCF's verification work found **six bugs, five safety and one liveness [corroborated]**, with logging taking about **one day** and a **400-line** trace spec **[verify]**. However, adoption also drove **88 commits to the trace spec and 107 changes to the consensus spec [corroborated]**, and diagnosing mismatches was the dominant cost ([NSDI'25](https://www.usenix.org/system/files/nsdi25-howard.pdf)). MongoDB cancelled its 2020 trace checking of the server ("cost more effort than it was worth"; two engineers spent **10 weeks** without trace-checking one spec, effort largely specific to `RaftMongo.tla` **[corroborated]**). The cause was the gap between a highly abstract spec and multithreaded implementation state ([MongoDB blog](https://www.mongodb.com/company/blog/engineering/conformance-checking-at-mongodb-testing-our-code-matches-our-tla-specs); [VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf)). The same paper reports that **model-based test generation** reached **100% branch coverage [verify]** of a sequential algorithm, and MongoDB's 2025 transactions work used generation again ([VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf)). The authors of the trace-validation method state that it "does not provide formal correctness guarantees" ([arXiv 2404.16075](https://arxiv.org/abs/2404.16075v2)). The researchers found **no Python tooling** for either bridge. The existing tools are Java (Kuppe/Merz) and Rust (Quint/Apalache ITF consumers such as [tla-connect](https://docs.rs/tla-connect)). A Python ITF replayer would have to be built in-house, but ITF is plain JSON ([Apalache ADR-015](https://apalache-mc.org/docs/adr/015adr-trace.html)). For concurrent clients, OmniLink's black-box method is the closest fit: record `(op, args, result, t_start, t_end)` and check the record against a sequential model ([arXiv 2601.11836](https://arxiv.org/abs/2601.11836)). It is a single 2026 preprint. For liveness, no bridge goes beyond bounded timeouts. That is an inference, because no finite trace can falsify a liveness property.

The Alloy and Lean store-tree axioms got the least attention. Their realistic bridge is to assert the axioms as Hypothesis properties on generated trees, which checks samples only. Cedar's move from Dafny to Lean, made because Dafny handled meta-theoretic proofs poorly, shows that matching the tool to the kind of property has real cost consequences ([Cedar RFC 0032](https://github.com/cedar-policy/rfcs/blob/main/text/0032-port-formalization-to-lean.md)).

## Lifecycle as checked source: the module wins, the diagram is a checked view

Every case where a diagram is "the source" has a formal executable notation underneath it: SCXML ([W3C](https://w3.org/TR/scxml/)), XState with bidirectional code and diagram views ([Stately](https://stately.ai/blog/2023-11-20-stately-studio-2-0)), or Stateflow (background knowledge, unverified). Mermaid has none. Its guards are free label text, and the docs define no execution semantics ([stateDiagram.md](https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/docs/syntax/stateDiagram.md)). State diagrams still reportedly use the legacy JISON parser rather than the new `@mermaid-js/parser` (secondary sources, **[verify]** against current Mermaid releases). The only Python wrapper needs Node and has no releases ([mermaid-parser-py](https://github.com/20001LastOrder/mermaid-parser-py)). Twenty-five years of translating UML state machines to model checkers have produced no agreed semantics. Translations drop or redefine composites, history and fork/join ([survey, arXiv 2407.17215](https://arxiv.org/pdf/2407.17215)).

AWS's P puts authority in the executable state-machine model and links it to production logs through PObserve ([ACM Queue](https://queue.acm.org/detail.cfm?id=3712057)). A plain diagram cannot express data, guards, multiplicity, ownership, interleavings or liveness. The TLA+ module therefore strictly contains the diagram's information, and it should be the source. TLC does not produce a lifecycle diagram. Its `-dump dot` output shows the concrete state graph and is readable only up to about **30 to 100 states [verify]** ([vscode-tlaplus wiki](https://github.com/tlaplus/vscode-tlaplus/wiki/Visualizing-States)). The researchers recommend a check rather than generation. A small in-repo Python parser accepts a declared Mermaid subset (flat states, `[*]`, `A --> B : ActionName`) and rejects everything else. The phase relation is derived from a tiny TLC configuration by projecting each state onto a named phase variable, or from a declared mapping of actions to phases. The check then asserts **set equality** with the drawn edges. Equality enforces the closed-world claim in both directions: no reachable transition is missing from the diagram, and no drawn transition is dead. The researchers found **no published experience report** of this kind of drift check, so this part of the recommendation is reasoned rather than observed. Cross-object constraints, such as "session Closed implies all its handles are Closed", stay as TLA+ invariants and do not appear as diagram edges.

On Gherkin, the evidence is weak and mostly negative. Studies report long, repetitive specs and a heavy maintenance burden ([Patkar et al. 2022](https://scg.unibe.ch/assets/archive/papers/Patk22b.pdf); [Islam 2024](https://theses.gla.ac.uk/84085/1/2024IslamPhD.pdf)). Gherkin scenarios are traces, and traces cannot state "any undrawn transition is forbidden".

## Industrial teams cut by protocol and guarantee, and authority follows binding

Published spec inventories are cut by **algorithm or guarantee, not by service**. AWS's 2015 table lists separate specs for S3's network algorithm and redistribution, DynamoDB replication, and EBS volume management, each a few hundred lines. The figures are 804, 645, 939 and 102 lines **[corroborated]** ([Lamport excerpt](https://lamport.azurewebsites.net/tla/amazon-excerpt.html)). Other examples are cut the same way. The Cosmos DB spec covers the five client-observable consistency levels ([arXiv 2210.13661](https://arxiv.org/pdf/2210.13661)). RaftMongo.tla covers one gossip sub-protocol ([VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf)). Elastic organises its models by algorithm ([repo](https://github.com/elastic/elasticsearch-formal-models)). The partial counter-pattern is ShardStore. It keeps reference models per component, at about **1%** of code size **[verify]** and reused as test mocks. It still splits the correctness argument **by execution kind** (sequential, crash, concurrent), which is close to D3's kinds ([SOSP 2021](https://dl.acm.org/doi/pdf/10.1145/3477132.3483540)). MongoDB 2025 cuts at an **explicit interface contract** between the protocol and the storage layer, so each side can be conformance-tested on its own ([VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf)). For a library with several backends, that is the closest analogue. No source states "cut by property" as a rule. The pattern is inferred from how the inventories are organised. No study measures whether cutting by property produces fewer contradictions than cutting by component. A systematic review of industrial TLA+ names choosing the abstraction level as the main obstacle ([arXiv 2411.13722](https://arxiv.org/abs/2411.13722)). Six kinds means six such choices.

On authority, no company publishes a general rule for resolving conflicts. Authority is implicit in the workflow. Cosmos DB's public docs point to the TLA+ repository as the precise definition, and the spec corrected two documentation errors ([Microsoft Learn](https://learn.microsoft.com/azure/cosmos-db/consistency-levels)). Cedar gates releases on its model. Elastic, by contrast, warns that its models "can differ to their implementations in substantial ways", and Datadog's model was not guaranteed to stay aligned with the code ([Datadog](https://datadoghq.com/blog/engineering/formal-modeling-and-simulation)). In short, a model governs only where it is bound to the code. Woodcock and Larsen's 2026 critical evaluation says the public AWS evidence is selective and that keeping specs current is a challenge ([ACM DL](https://dl.acm.org/doi/10.1145/3815784)). Its detail was not read.

## Spec forms agents implement well: contracts, short sections, examples as tests

The strongest datum comes from the vericoding benchmark: **12,504 formal specs**, with LLMs producing verified code for about **82% of the Dafny specs**. **Adding natural-language descriptions did not significantly improve results** ([arXiv 2509.22908](https://arxiv.org/pdf/2509.22908)) **[corroborated]**. Over one year of model progress, pure-Dafny success rose from 68% to 96% in the arXiv abstract and to 97% in an OpenReview version; quote the version of record. A single thesis reports that explicit pre/postconditions raise pass@k over natural-language descriptions ([ERAU](https://commons.erau.edu/edt/927/)). That is weak evidence. Spec-kit, Kiro and Tessl all separate the *what* from the *how* and move the *how* into a plan or design document ([Böckeler](https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html); [Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/spec-driven-development)). They relocate it rather than delete it, and step plans measurably help generation: self-planning gives up to **+25.4% relative pass@1 [verify]** ([arXiv 2303.06689](https://arxiv.org/pdf/2303.06689)). EARS, Kiro's syntax for acceptance criteria, has **no measured accuracy evidence** for agents ([Wikipedia](https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax)).

Examples cut both ways. TiCoder's test-driven clarification raised pass@1 by roughly **22 to 54 points** under simulated users **[verify]** ([arXiv 2208.05950](https://arxiv.org/pdf/2208.05950)). Models also pattern-match examples ([arXiv 2411.06774](https://arxiv.org/html/2411.06774)), and they cheat on tests that contradict the spec. GPT-5 exploited contradictory tests in **76%** of Oneoff-SWEbench tasks but only **2.9%** of Oneoff-LiveCodeBench tasks **[corroborated]** ([ImpossibleBench, arXiv 2510.20270](https://arxiv.org/pdf/2510.20270)). This supports keeping the normative claim in one place and tracing tests to it, but agents must be pointed at those tests. On structure, adherence falls as the number of instructions grows: the best models reach about **68% at 500 instructions**, with a bias towards earlier instructions **[verify]** ([IFScale, arXiv 2507.11538](https://arxiv.org/html/2507.11538v1)). Accuracy also drops for content placed mid-context ([Lost in the Middle, arXiv 2307.03172](https://arxiv.org/abs/2307.03172)). Neither benchmark measures code. Practitioners name spec verbosity and review burden as the main failure of spec-driven development tooling ([Thoughtworks Radar](https://www.thoughtworks.com/radar/techniques/spec-driven-development)).

## Bridges ranked by what they establish

**A formal layer governs only the class of executions its bridge observes or
generates.** Each bridge establishes something different and fails differently:

| Bridge | Establishes | Typical failure | Fit for remote-store |
| --- | --- | --- | --- |
| Differential oracle | Agreement on generated single-call inputs and outputs | Oracle and code share one misreading of the contract | Strong: the Dafny oracle exists |
| Model-based test generation | Generated executions of the model run against the code | Generated runs miss adversarial interleavings | Lifecycles, first: MongoDB's record favours it over trace checking |
| Trace validation | Observed runs are permitted by the model | The gap between implementation state and model state | Lifecycles, second: CCF made it work at real cost; MongoDB cancelled |
| Black-box history checking | Concurrent histories satisfy a concurrency contract | Nondeterminism, timeouts, partial failure | Highest value, highest cost; one 2026 preprint |

From it follows a ladder of what a clause can claim:

1. **Unbridged model:** informs review; never overrides a tested behaviour.
2. **Differential oracle:** governs single-call semantics on the generated input space.
3. **Generated tests:** govern the generated execution space, not every behaviour.
4. **Trace-validated:** governs that observed transitions are model-permitted.
5. **History-checked:** governs observable concurrent histories, under the checker's assumptions.
6. **Liveness:** governs only when reduced to a bounded obligation a test can fail (for example, a retry completes within N attempts under injected delay M); unbounded eventual progress stays a design assertion.

A clause's level changes when a bridge is built, so it is derived from the
bridges and their tests, not written into the spec by hand.

## Verdicts per RFC decision

| Decision | Verdict | Evidence strength | Proposed rewording (where "changes how") |
| --- | --- | --- | --- |
| D1 contract only, never mechanism | Changes how | Moderate for the what/how split (vericoding null result, framework consensus); weak for contracts beating prose (one thesis) | "A spec states only the observable contract. Mechanism is relocated to ADRs, design notes or the per-task plan, not deleted. Mechanism a caller can observe (side-effect order, visible retries) is contract and stays." |
| D3 split by kind of truth | Changes how | Moderate, inferred from spec inventories; no rule stated anywhere and no contradiction-rate data | "Split by kind of truth first, then by interface contract (API to backend) within a kind. A property that spans kinds names one owning spec and links from the others." |
| D4 closed-world Mermaid, examples in tests, no Gherkin | Holds; source question resolved | Strong that the executable model holds authority (P, Stately, UML literature); weak for drift-check practice (none found); weak-moderate against Gherkin | "The TLA+ module is the source. The Mermaid diagram is a hand-written projection, checked for set equality of edges (labels = action names) against the phase projection of a small TLC config. Mermaid is limited to a declared subset (flat states, `[*]`, labelled edges) parsed in-repo. Cross-object constraints stay as invariants." State the divergence from spec-kit's Given/When/Then explicitly. |
| D5 the proving layer governs, only through a bridge | Changes how | Moderate-strong (Cedar, CCF, MongoDB, Elastic/Datadog disclaimers, Kuppe/Merz) | "A formal layer governs a clause only once a bridge binds it to tests. Until then its result is informational about the model. The claim the code inherits is 'agrees with the model on generated or observed executions'. Preferred bridges: Dafny oracle with differential tests (single calls); ITF-generated tests replayed by pytest (lifecycles); black-box trace checking (multi-client). Liveness governs only as a bounded obligation. An unbridged model never overrides a tested behaviour." The ladder above states what each level may claim. |
| D7 one skeleton per spec | Holds, with one condition | Moderate (IFScale and lost-in-the-middle are not code-specific; TiCoder and ImpossibleBench are strong but idealised) | Condition only: "Tested against" must name runnable tests that the agent is directed to read or run, derived from the tests' spec marks rather than listed in the spec. |

## Open questions and gaps

Five questions remain open. The first is how an unbridged TLA+ clause interacts with Rule 7 on intent attribution. CCF's 107 changes to its consensus spec suggest the spec is wrong about as often as the code once a bridge exists. The second is whether ITF-driven generation can be built at reasonable cost for remote-store's lifecycles. No Python precedent exists, and the action-to-API mapping carries the same abstraction-gap risk that sank MongoDB's trace checking. The third is whether nondeterministic backends (S3, Azure) make black-box trace checking impractical. The fourth is the Gherkin question for agents specifically: no evidence shows that Given/When/Then or EARS helps or hurts accuracy, so D4 stands on maintenance and closed-world grounds, not on agent outcomes. The fifth is whether any of this transfers to multi-file agent work, since all spec-form evidence is at function or class level.

The gaps are as follows. There is no comparison of contradiction rates between cutting by property and cutting by component. No experience report of a diagram-to-model drift check was found. The TLC `-dump` flags (`actionlabels`) are unconfirmed. The detail of Woodcock and Larsen 2026, which might contain negative evidence, was not read. The current Python feature table for Dafny was not retrieved. Alloy received almost no attention, and Python linearizability checkers were not researched. Every figure marked **[verify]** comes from a search summary and must be checked against the full PDF before the RFC quotes it; the decision-relevant ones left are CCF's one-day and 400-line costs and MongoDB's 100% branch coverage.

## Evidence quality

| Class | Findings |
| --- | --- |
| Corroborated against a primary source (second-hand) | CCF bug and commit counts; MongoDB's ten-week outcome; vericoding headline results; AWS 2015 line counts; Cedar's bug counts and method; ImpossibleBench's split |
| Primary source, figure unchecked | CCF's one-day and 400-line costs; MongoDB's 100% branch coverage; TiCoder, self-planning and IFScale figures; ShardStore's 1% |
| Inferred, not observed | Industry cuts specs by property; diagram-to-model drift check; the bridge ladder itself |
| Single source or preprint | Black-box history checking (OmniLink); Dafny-to-Python performance |

## External reviews considered

Two external AI reviews of this record were weighed on 2026-10-18.

**Adopted:** the figure checks and precision fixes above (Perplexity); the
bridge taxonomy (Perplexity), reordered because its "trace validation strong
for lifecycles" contradicts MongoDB's record and CCF's cost; the governance
ladder and bounded liveness (Perplexity, matching Gemini's "binding levels");
the evidence-quality table (Perplexity); "agents do not need more prose; they
need tighter feedback loops" (Gemini), qualified with "refereed by the spec"
and leading the Conclusion.

**Recorded as candidates for the RFC or guide, not research findings:** a
bridge acceptance checklist (observable interface, encoding of runtime values
into model values, generation or capture method, pass criterion, known blind
spots, owning CI job), which also covers the unverified glue between Dafny
runtime types and Python; and "a clause names a test that fails if it is
violated, and an agent stops and reports a conflict between test and clause
rather than changing either", whose second half `000-process.md` Rule 7
already covers.

**Not adopted:** binding levels tagged on each clause by hand (Gemini), since a
level changes as bridges are built and a hand tag is project state in a spec;
test IDs listed in a spec footer (Gemini), which reverses the link direction
that spec marks already give; "Gherkin bloats the context" (Gemini), which no
source supports; a spec index with per-component context slices (Gemini),
which concerns how agents read specs rather than how specs are designed, and
which the repo's lookup commands already serve.

## Conclusion

**Agents do not need more prose; they need tighter feedback loops, refereed by
the spec.** Three findings carry it: natural-language text added to a formal
spec did not improve verified-code success (vericoding, **[corroborated]**);
tests used to clarify intent raised accuracy sharply (TiCoder, simulated users);
and agents game tests that contradict the spec (ImpossibleBench,
**[corroborated]**), so a loop works only where the spec decides between a test
and the code. The wording sharpens one line of Gemini's review (§ External
reviews considered); for the RFC it joins D1 (fewer, falsifiable clauses), D5
(bridges are the loop) and D7 ("tested against" names the loop).

The evidence moves RFC-0022 from asserting authority by layer to making authority depend on a bridge. On its own, "the layer that can prove it governs it" is what Elastic and Datadog practise, and their models drift. Cedar and CCF show that "governs once bound, to the extent of the bound" is what actually holds. This changes what the RFC can promise today. Dafny already governs single-call semantics. TLA+ lifecycles can govern once an ITF replayer and the diagram equality check exist. TLA+ concurrency and liveness clauses should be labelled informational, which matches the current non-gating TLC run in CI. The rest of the RFC (contract-only specs, kinds of truth, a single short skeleton) is consistent with both industrial practice and the agent evidence. It needs sharper wording, not reversal.

## Sources

**Bridges and Dafny:** [Cirstea et al., arXiv 2404.16075](https://arxiv.org/abs/2404.16075v2) · [Howard et al., NSDI'25](https://www.usenix.org/system/files/nsdi25-howard.pdf) · [Davis et al., VLDB 2020](https://www.vldb.org/pvldb/vol13/p1346-davis.pdf) · [MongoDB conformance blog](https://www.mongodb.com/company/blog/engineering/conformance-checking-at-mongodb-testing-our-code-matches-our-tla-specs) · [Schultz & Demirbas, VLDB 2025](https://www.vldb.org/pvldb/vol18/p5045-schultz.pdf) · [OmniLink, arXiv 2601.11836](https://arxiv.org/abs/2601.11836) · [Apalache ITF ADR-015](https://apalache-mc.org/docs/adr/015adr-trace.html) · [tla-connect](https://docs.rs/tla-connect) · [Hypothesis stateful testing](https://hypothesis.works/articles/rule-based-stateful-testing/) · [Dafny Reference Manual](https://dafny.org/dafny/DafnyRef/DafnyRef) · [arXiv 2501.06283](https://arxiv.org/pdf/2501.06283) · [AxDafny, arXiv 2606.32007](https://arxiv.org/pdf/2606.32007) · [AWS MPL](https://github.com/aws/aws-cryptographic-material-providers-library) · [Cedar, arXiv 2407.01688](https://arxiv.org/html/2407.01688v1) · [Cedar RFC 0032](https://github.com/cedar-policy/rfcs/blob/main/text/0032-port-formalization-to-lean.md) · [Amazon Science: Cedar](https://www.amazon.science/blog/how-we-built-cedar-with-automated-reasoning-and-differential-testing) · [Cedar paper](https://assets.amazon.science/d3/86/99db1aa142ffb6981d86dc849e4c/how-we-built-cedar-a-verification-guided-approach.pdf) · [Cedar POPL'24 SRC poster](https://bhaktishh.github.io/papers/popl-24-src-poster.pdf)

**Lifecycle:** [SCXML](https://w3.org/TR/scxml/) · [Stately Studio 2.0](https://stately.ai/blog/2023-11-20-stately-studio-2-0) · [UML verification survey, arXiv 2407.17215](https://arxiv.org/pdf/2407.17215) · [Mermaid stateDiagram docs](https://raw.githubusercontent.com/mermaid-js/mermaid/develop/packages/mermaid/src/docs/syntax/stateDiagram.md) · [mermaid-parser-py](https://github.com/20001LastOrder/mermaid-parser-py) · [vscode-tlaplus: Visualizing States](https://github.com/tlaplus/vscode-tlaplus/wiki/Visualizing-States) · [ACM Queue: AWS correctness practices](https://queue.acm.org/detail.cfm?id=3712057) · [Patkar et al. 2022](https://scg.unibe.ch/assets/archive/papers/Patk22b.pdf) · [Islam 2024 thesis](https://theses.gla.ac.uk/84085/1/2024IslamPhD.pdf)

**Industrial structure:** [AWS 2015 excerpt](https://lamport.azurewebsites.net/tla/amazon-excerpt.html) · [ShardStore, SOSP 2021](https://dl.acm.org/doi/pdf/10.1145/3477132.3483540) · [Cosmos DB, arXiv 2210.13661](https://arxiv.org/pdf/2210.13661) · [Cosmos consistency docs](https://learn.microsoft.com/azure/cosmos-db/consistency-levels) · [Elastic formal models](https://github.com/elastic/elasticsearch-formal-models) · [Datadog formal modeling](https://datadoghq.com/blog/engineering/formal-modeling-and-simulation) · [Industrial TLA+ SLR, arXiv 2411.13722](https://arxiv.org/abs/2411.13722) · [Woodcock & Larsen 2026](https://dl.acm.org/doi/10.1145/3815784) · [Jackson & Wing 1996](https://people.csail.mit.edu/dnj/publications/ieee96-roundtable.html)

**Agents:** [Vericoding, arXiv 2509.22908](https://arxiv.org/pdf/2509.22908) · [ERAU thesis](https://commons.erau.edu/edt/927/) · [nl2postcond, arXiv 2310.01831](https://arxiv.org/pdf/2310.01831) · [Böckeler, SDD tools](https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) · [Thoughtworks Radar: SDD](https://www.thoughtworks.com/radar/techniques/spec-driven-development) · [EARS](https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax) · [Self-planning, arXiv 2303.06689](https://arxiv.org/pdf/2303.06689) · [TiCoder, arXiv 2208.05950](https://arxiv.org/pdf/2208.05950) · [arXiv 2411.06774](https://arxiv.org/html/2411.06774) · [ImpossibleBench, arXiv 2510.20270](https://arxiv.org/pdf/2510.20270) · [IFScale, arXiv 2507.11538](https://arxiv.org/html/2507.11538v1) · [Lost in the Middle, arXiv 2307.03172](https://arxiv.org/abs/2307.03172)
