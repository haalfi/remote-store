# Research: Code Abundance — Tao's ICM 2026 Argument Transposed to Coding Agents

## Context

Terence Tao's public lecture at the International Congress of Mathematicians 2026,
_Mathematics in the age of AI_ (July 24, 2026,
[slides](https://teorth.github.io/tao-web/slides/age-of-ai-icm-2026.pdf)), makes an
argument whose shape is not specific to mathematics. This record transposes it to
software development with coding agents, tests each transposed claim against
published evidence, marks where the analogy breaks, and derives concrete proposals.

The transposition is worth doing because Tao's move is structural, not
metaphorical. He declines to argue about capability, conditions on it, and then
asks what the community actually wants — which turns out to be the harder and
more neglected question. Software development has the same neglected question, an
isomorphic production pipeline, and one extra stage that mathematics does not
have.

**Sourcing note.** The Tao slides were read in full from the PDF. Several primary
sources cited below were unreachable from this environment (the egress proxy
blocks `arxiv.org`, `dora.dev`, `martinfowler.com`, `simonwillison.net`,
`leidendeclaration.ai`, `flowverify.co`); those figures come from search-engine
extractions of the primary documents, not from the documents themselves, and are
marked accordingly in the table in § 4. Repo counts in the appendix were derived
by running the stated command.

## 1. The source argument

Tao's structure, compressed to its load-bearing parts.

1. **Decompose the question.** "How should the mathematical community respond to
   modern AI?" splits into a capability subquestion and an orthogonal
   goals-and-values subquestion. Almost all public debate lives in the first.

2. **Condition, don't argue.** He states an _AI Capability Conjecture_ as a
   template full of placeholders ("some AI tools will, at some expense, with some
   supervision, accomplish some research-level tasks..."), notes that the evidence
   is contaminated by reporting bias and undisclosed costs, and then declines to
   adjudicate it. He adopts a _Working Hypothesis_ — a reasonably strong form is
   true — and asks the audience to reason conditionally. "Evidence for or against
   the Working Hypothesis is orthogonal to the rest of my talk."

3. **Ask what we actually want.** The _Goals and Values Question_ asks for the
   real goals, "not just the explicit goals that we communicate to the public (or
   to funding agencies), but also the implicit goals that we actually seek in
   practice." Historically these goals were positively correlated, so one could
   serve as a proxy for the others and most could stay implicit.

4. **Goodhart breaks the correlation.** Under heavy optimization the goals
   diverge. Tao names "the inherently ungrounded nature of generative AI, as well
   as the financial incentives of AI companies" as making this failure especially
   likely.

5. **Refine the goal until it is honest.** He iterates the problem-solving goal
   four times. Solve problems → and verify them → and communicate them clearly →
   and have them digested, accepted, and incorporated into the definitive theory
   of the field. Each refinement adds a pipeline stage: generation, verification,
   exposition, publication, canonicalization.

6. **Note where the pipeline jams.** Cheap generation with unchanged downstream
   capacity produces "impedance mismatches" or "proof indigestion" at every
   stage: proofs waiting to be verified, verified proofs waiting for a readable
   writeup, correct and readable proofs overwhelming peer review, published
   proofs never worked into definitive form. "We will transition from an era of
   proof scarcity to an era of proof abundance."

7. **Recommend.** Three things: normalize responsible disclosure of AI
   assistance rather than driving it covert; shift emphasis from generation and
   priority toward digestion; and a rule of thumb — "if the authors cannot
   convincingly demonstrate that they can give a clear, expert-level talk on
   their results, that is correct and properly attributed, then the result should
   not be published."

Two further observations from the talk carry over unusually well.

- **Friction is information.** An over-polished proof presents routine and
  difficult steps as equally easy. Human-written proofs "retain some natural
  friction that prompts the reader to slow down." Current AI exposition "dwells
  at length on trivialities, while passing very briefly through (or even
  obscuring) the most interesting and novel portions."
- **Canonical work is the substrate for the tools.** "The success of AI tools in
  mathematics crucially relies upon the canonical theories that human
  mathematicians have painstakingly built over the centuries." The slowest,
  least-automatable stage is the one the automation depends on.

## 2. The transposition

### 2.1 The Working Hypothesis for software

Stated in Tao's template form:

> **Working Hypothesis (software).** Coding agents will, reasonably soon, become
> capable of performing a reasonable fraction of production software engineering
> tasks, with reasonable levels of success, quality, supervision, and cost.

The first disanalogy is immediate and important: **in software this hypothesis is
much less contested, and the contamination Tao warns about is worse.** Adoption
is near-universal — the 2025 Stack Overflow Developer Survey reports 84% of
developers using or planning to use AI tools, up from 76% in 2024 — while trust
runs the other way, with 46% distrusting output accuracy against 29% trusting it.
CloudBees' 2026 survey of 213 enterprise technology leaders reports AI generating
or assisting 61% of the average enterprise codebase.

So the software community has, in effect, already accepted the Working
Hypothesis in practice without ever having the goals-and-values conversation Tao
is asking for. That is the opposite ordering from mathematics, and it is the
central reason the transposed argument is urgent rather than speculative.

The contamination warning also lands harder. Tao notes that public capability
evidence is "highly subject to reporting bias and non-scientific incentives, with
some important costs and variables remaining undisclosed." Software's closest
thing to a controlled trial found the opposite of the marketing: METR's 2025
randomized controlled trial of 16 experienced open-source developers across 246
real tasks measured a 19% _slowdown_ with AI tools, while the same developers
estimated a 20% speedup after the fact. METR itself now labels that result
historical. The point is not that the result still holds; it is that a
perception-reality gap of ~39 percentage points was measurable at all, and that
almost no other software capability claim has been tested this way.

### 2.2 The Goals and Values Question for software

> **Goals and Values Question (software).** What are the precise goals of a
> software engineering organization, and of the practice of software
> engineering? Not just the goals stated to executives, boards, or the market,
> but the implicit ones actually pursued.

An honest list, matching Tao's:

- Ship working features to users.
- Build systems that can still be changed in five years.
- Understand the system well enough to operate it under failure.
- Keep the system secure and compliant.
- Build and hold a team.
- Train the next generation of engineers.
- Contribute to the shared commons (libraries, standards, published knowledge).
- Create artifacts of enduring craft value.

As in mathematics, these were historically correlated. Writing the feature
_was_ how you came to understand it; the person who understood it was the person
who could operate it; operating it was how a junior became a senior. The
correlation was so reliable that the industry built its instruments on it — the
truck factor estimates retained knowledge by measuring authorship footprint,
because typing code and understanding code came bundled.

**Agents break the bundle.** This is the software-specific form of Tao's
divergence diagram, and it has been named precisely: "The Substrate Collapse"
(arXiv 2606.20882) argues that a truck factor over an agent-written codebase
"still returns a number, and the number is meaningless — not approximately, but
in the precise sense that the thing it measures, the distribution of authorship
footprint, has stopped being correlated with the thing it was used to estimate,
the distribution of retained theory." The mechanism is exactly Tao's: "you
couldn't write a retry mechanism without briefly holding the failure modes in
your head," and now you can.

The deep version of this is 40 years old. Peter Naur's _Programming as Theory
Building_ (1985) holds that the program is not the artifact; the theory of the
program — held in the heads of the people who built it — is. Code is a
projection of the theory, and when the theory is lost the code becomes
unmaintainable regardless of its quality. Naur's conclusion, that the only way to
acquire the theory is active engagement in developing the program, is the precise
software analogue of Tao's canonicalization stage: the slowest, least
automatable, and most valuable step.

### 2.3 Goodhart, applied

Every conventional engineering metric measures volume, speed, or frequency of
human effort, and every one of them can now be inflated by an agent without
corresponding value: lines of code, commit count, PR count, story points, and —
newly — token spend, in the practice already named "tokenmaxxing." Tao's
formulation applies verbatim: when a measure becomes a target it ceases to be a
good measure, and generative AI's ungroundedness plus vendor financial incentives
make software unusually exposed.

Note that the DORA metrics themselves partially survive, because two of them
(change failure rate, time to restore) measure outcomes rather than effort. This
is the discriminator: **metrics that measure what happened as a result of the
work survive; metrics that measure how much work happened do not.**

### 2.4 The pipeline, with one extra stage

| Tao's stage | Software analogue | What it produces |
|---|---|---|
| Proof generation | Code generation | An unverified diff |
| Proof verification | Tests, types, CI, static analysis, formal methods | A diff that passes its checks |
| Proof exposition | Commit messages, PR descriptions, docs, comments, ADRs | A diff a reviewer can follow |
| Proof publication | Code review and merge | A diff in the main branch |
| — | **Operation** | A diff running in production, under someone's pager |
| Proof canonicalization | The team's shared theory: architecture, conventions, libraries, onboarding material | A change absorbed into how the system is understood |

The extra stage is the largest structural difference, and it cuts against
software. A published proof that nobody fully understands sits inertly in the
literature; it does not wake anyone at 3am. Software does. An engineer quoted in
the 2026 on-call literature puts it exactly: "the team's ratio of 'code in
production' to 'code we understand deeply enough to debug under pressure' has
shifted, and it's shifted in the wrong direction for incident response."

Tao asks, of mathematics, "Could we have a verified proof of a major result that
no human understands enough to explain it?" The software version is not
hypothetical and not rhetorical: **we already run systems no one understands well
enough to explain, and they fail.**

## 3. Impedance mismatch, stage by stage

Tao's prediction is that under cheap generation, every downstream stage jams. In
software this is not a prediction. Each stage has measured evidence.

**Generation is cheap and getting cheaper.** This is the premise, and it is met.

**Verification is partially cheap, and that is a trap.** Software's genuine
advantage over mathematics is a mature stack of partial oracles: tests, types,
CI, fuzzing, static analysis. But their coverage is narrower than it looks.
Veracode's GenAI Code Security Report (2025, 80 curated tasks across 100+ models)
found models chose the insecure implementation 45% of the time when given the
choice; its Spring 2026 update reports syntax-correctness above 95% while
security pass rates sit near 55%, roughly unchanged over two years. The deeper
problem is the **oracle problem**: when the same agent writes both the code and
its tests, the tests optimize for passing rather than for correctness, and the
verification stage silently degrades into a second generation stage.

**Exposition degrades in exactly the way Tao describes.** His complaint about
AI-written proofs — flawless surface, disproportionate attention to trivialities,
no connection to prior work — has a direct measurement. A study of 23,247
agent-authored pull requests across five agents (MSR 2026) found that among
high-inconsistency PRs the dominant failure was "descriptions claim unimplemented
changes" (45.4%), followed by scope understatement (22.0%) and placeholder
descriptions (18.8%); those PRs had 51.7 percentage points lower acceptance
(28.3% vs 80.0%) and took 3.5× longer to merge. Agents write better commit
messages than humans at the individual-commit level and worse summaries at the
PR level — that is, they are good at local description and bad at telling you
what the change means, which is Tao's complaint restated.

**Publication is the visible jam.** This is where software's indigestion is
loudest. Reported 2026 telemetry: median code review time up 441.5% across 22,000
developers (Faros AI) against task throughput up 33.7%; AI-assisted PRs roughly
2.5× larger and waiting ~5× longer for a reviewer across 8.1M PRs (LinearB);
feature-branch throughput up 59% year over year while median-team _main branch_
throughput fell (CircleCI). That last pair is the impedance mismatch in a single
statistic: more work entering the pipe, less work leaving it.

In open source the jam has already broken things. The Jazzband collective shut
down, citing unsustainable volumes of AI-generated spam PRs and issues; Godot
maintainers describe triaging AI slop as demoralizing; curl cancelled its bug
bounty because it became a magnet for low-effort AI submissions. The mechanism is
worth naming precisely, because it is more general than AI: **agentic generation
removes the effort-based backpressure that used to make low-quality submission
self-limiting.** Peer review was never designed as a filter; it worked because
producing a submission was expensive.

**Operation degrades.** CloudBees (2026, n=213): 81% of enterprise technology
leaders report production issues tied to AI-generated code. DORA's 2025 report
(n≈5,000 professionals) finds AI adoption associated with increased throughput
_and_ increased delivery instability simultaneously. A Lightrun survey (April
2026) reports 43% of AI-generated code changes requiring debugging in production.

**Canonicalization degrades most, and quietly.** GitClear's analysis of 211
million changed lines (January 2020 – December 2024) found refactored ("moved")
lines falling from 24.1% to 9.5% of changes, duplicated code blocks rising
eightfold in 2024, and code revised within two weeks of commit rising from 3.1%
to 5.7%. Read against Tao's framing, these are not code-quality statistics.
Refactoring and consolidation _are_ canonicalization: the act of working a
solution into the definitive form of the system. A measured collapse in
refactoring share is a measured collapse in the stage Tao calls "the most
valuable part of the entire process."

Architecture research reaches the same place from another angle: agents achieve
structural modularity while failing at semantic cohesion, producing a "modular
mirage" where file separation does not correspond to logical separation (arXiv
2605.02741).

**And the substrate dependency holds.** Tao's observation that AI mathematics
depends on painstakingly canonicalized human theory has a direct software
counterpart: agents perform markedly better on popular, well-documented libraries
that are dense in training data, and misuse niche or new ones. Documentation
written for humans is often insufficient. This is the sharpest practical argument
against letting canonicalization decay: **the stage the agents cannot do is the
stage that determines how well the agents work.**

## 4. Figures and their derivations

Per [`CLAUDE.md` principle 9](../../CLAUDE.md#principles), each figure names its
source. "Extraction" means the primary document was unreachable from this
environment and the figure comes from a search-engine extraction of it.

| Figure | Source | Sample / date | Access |
|---|---|---|---|
| 19% slowdown; 20% perceived speedup | METR RCT | 16 devs, 246 tasks, Jul 2025 | Extraction |
| 84% use/plan AI; 46% distrust; 66% "almost right"; 45% lose time debugging | Stack Overflow Developer Survey 2025 | Published Dec 2025 | Extraction |
| 61% of enterprise codebase AI-written; 81% report production issues | CloudBees State of Code Abundance | n=213 leaders, May 2026, ±8% | Extraction |
| Throughput up and instability up together; seven capabilities | DORA State of AI-assisted Software Development 2025 | ~5,000 professionals | Extraction |
| Review time +441.5%; throughput +33.7% | Faros AI 2026 telemetry | 22,000 developers | Extraction (secondary) |
| PRs 2.5× larger, 5× longer wait | LinearB benchmarks | 8.1M PRs, 2026 | Extraction (secondary) |
| Feature-branch throughput +59%, main-branch throughput down | CircleCI 2026 data | — | Extraction (secondary) |
| Refactoring 24.1%→9.5%; duplication 8×; churn 3.1%→5.7% | GitClear AI Code Quality | 211M lines, Jan 2020–Dec 2024 | Extraction |
| 45% insecure choice; ~55% security pass rate | Veracode GenAI Code Security 2025 / Spring 2026 | 80 tasks, 100+ models | Extraction |
| 1.7% high-inconsistency PRs; 45.4% claim unimplemented changes; 28.3% vs 80.0% acceptance; 3.5× merge time | Message-Code Inconsistency study (arXiv 2601.04886) | 23,247 agentic PRs, 5 agents, 974 annotated | Extraction |
| 43% of AI changes need production debugging | Lightrun survey | Apr 2026 | Extraction (secondary) |
| Truck-factor invalidation argument | "The Substrate Collapse" (arXiv 2606.20882) | Analytical, Jun 2026 | Extraction |
| Modular mirage | arXiv 2605.02741 | 2026 | Extraction |
| SDD artifact counts | This repo | `ls` commands in § Appendix | Direct |

Three cautions about this table. The Faros/LinearB/CircleCI/Lightrun rows are
vendor telemetry reported through a secondary aggregator, and vendors selling
review tooling have an interest in a review crisis. The GitClear correlation is
temporal, not causal — 2020–2024 also contains a hiring bust and a rates cycle.
And Tao's own warning applies to the whole table: this is largely uncontrolled
evidence gathered under commercial incentives. It is consistent, which is
something, but consistency across biased sources is weaker than it feels.

## 5. Where the analogy breaks

Faithfulness requires marking the disanalogies, and three of them matter enough
to change the recommendations.

**Software's peer review is far weaker than mathematics'.** Tao can lean on
editors, referees, and community acceptance as a backstop that "cannot be
optimized purely by the authors and their AI tools." Software's equivalent is
typically one colleague, under deadline, in a private repository, with no
external record and no referee report. Where Tao worries that AI output will
_overwhelm_ peer review, software's review was already the weak link — and the
2026 data shows reviewers approving agent-authored PRs more readily despite those
PRs carrying more technical debt on average. **The backstop Tao relies on does
not exist in software at comparable strength, so software cannot solve its
version of the problem by protecting review alone. It has to build capacity that
mathematics already had.**

**Software has cheap partial oracles; mathematics does not.** This is software's
genuine advantage and it should be pressed hard. A test suite is a weaker
guarantee than a Lean proof but incomparably cheaper than a referee, and it runs
on every change forever. Formal methods research in 2026 is converging on using
verifiers as ground-truth oracles precisely because AI-generated tests inherit
the generator's blind spots. The strategic implication: software should invest in
the stage where it has an advantage mathematics lacks, rather than importing
mathematics' referee-centric answer wholesale.

**Software is deletable; mathematics is cumulative.** A wrong proof pollutes the
literature permanently; wrong code can be reverted. This cuts both ways and the
second way is worse: reverted code still ran, still leaked data, still lost
money. Software's mistakes are cheaper to _remove_ and more expensive to _make_.

**The value of understanding is instrumental in software, terminal in
mathematics.** Thurston's line, which Tao quotes — "the measure of our success is
whether what we do enables people to understand and think more clearly" — makes
understanding the product. In software the product is working systems, and
understanding is a means. This is the honest reason software teams will be
tempted to skip the digestion stage: they can, for a while. The argument for not
skipping it is not aesthetic. It is that change, incident response, security
review, and audit all cash out understanding, and they arrive later than the
ship date.

## 6. Proposals

Tao's three recommendations transpose directly. Five more are software-specific,
following from the disanalogies above.

**1. Normalize disclosure; do not drive it covert.** Tao's worst case is authors
using AI covertly and concealing it to avoid criticism. Open source has already
converged on a mechanism: the `Assisted-by:` git trailer. The Linux kernel's AI
coding assistants policy prescribes `Assisted-by: AGENT_NAME:MODEL_VERSION` and
is explicit that agents must not add `Signed-off-by` — liability stays with the
human. Fedora requires disclosure when a significant part of a contribution is
taken from a tool unchanged. QEMU is moving from a blanket ban toward
disclosure-based acceptance for mechanical changes, tests, docs, and small fixes.

The operational payoff is not moral. It is that provenance metadata survives to
the incident: at 3am it tells you whether the change you are staring at was
reviewed deeply or approved quickly, and who to wake.

**2. Shift emphasis from generation to digestion.** Tao: decrease emphasis on
proof generation and being first; increase emphasis on exposition, publication,
and canonicalization. Software's version is concrete and unpopular: **promote
people for review throughput, consolidation, deletion, and documentation, not for
PR count.** Given the collapse in refactoring share, the highest-leverage
engineering work available in 2026 is probably consolidating what agents have
already produced. Almost no compensation system rewards it.

**3. The talk rule, transposed.** Tao: if the authors cannot give a clear,
expert-level talk on the result, that is correct and properly attributed, do not
publish it. Software's version:

> **If no human on the team can explain the change at review depth — why this
> approach, what it breaks, how it fails, and how they would debug it in
> production — it does not merge.**

This is a stronger claim than "review it." It is a claim about a named person
holding the theory. It is testable in the review conversation, it degrades
gracefully (the answer can be "not yet"), and it is the only proposal here that
directly defends the operation stage.

**4. Make verification adversarial, and never let one agent close the loop.**
Press software's oracle advantage, but respect the oracle problem: the agent that
writes the implementation should not be the sole author of the property it is
checked against. Practical forms — human-written tests with agent-written
implementations, property-based tests over agent-generated code, formal twins
checked against the implementation, mutation testing to verify the tests
themselves have teeth. The general rule: **the specification and the
implementation should not have the same author, human or not.**

**5. Treat the harness as the deliverable.** DORA 2025's central finding is that
AI amplifies existing capability rather than supplying it, and it names seven
capabilities that decide the direction of amplification, including a clear AI
stance, strong version control, small batches, and quality internal platforms.
The corollary for teams adopting agents: the gates, hooks, checks, and
specifications that constrain an agent are not overhead around the work — with
cheap generation they _are_ the work, because they are the only part that does
not scale with token spend.

**6. Preserve natural friction in exposition.** Tao's most counter-intuitive
point: over-polished writing presents routine and difficult steps as equally
easy, removing the friction that tells a reader to slow down, and human
"mistakes" in exposition can help. The software version is to record what was
hard — the approaches that failed, the constraint that forced the design, the
part that is subtle. This is what an architecture decision record is for, and
what an agent-written PR description systematically omits, because the agent
found nothing hard.

**7. Defend the training pipeline explicitly.** Tao lists training the next
generation among the goals that used to be correlated with the others and warns
they may diverge. In software the divergence is already measured: entry-level
developer postings down sharply since 2022 and junior employment declining
month over month, while a 2025 Harvard study found junior employment dropping
9–10% within 18 months of a firm adopting AI assistants. Under the bundled
regime, juniors learned by doing the work agents now do. **If a team wants
seniors in five years it now has to pay for the training path deliberately,
because the free version was a side effect of the bundle that has broken.** This
is the goal most likely to be optimized away silently, because its costs are
immediate and its benefits arrive after the current planning horizon.

**8. Pick metrics that survive Goodhart.** Retire volume and effort proxies —
lines, commits, PR count, story points, token spend. Keep outcome measures —
change failure rate, time to restore, incidents per change, and the share of
changes whose author can explain them. Accept that the truck factor, computed
over authorship, no longer measures retained understanding, and either
instrument comprehension directly or stop quoting the number.

## 7. What a Leiden Declaration for software would need to say

Tao points to the [Leiden Declaration on AI and Mathematics](https://leidendeclaration.ai)
(June 2026, endorsed by the International Mathematical Union) as an excellent
starting point. It asks individual researchers to disclose AI use, take
responsibility for correctness, and cite prior work; asks professional bodies to
develop publication and review policy; and asks policymakers about regulation and
public infrastructure. It does not ban AI; it demands explicit community norms.

Software has no equivalent, and the pieces it would need are already scattered
across the open source policies cited above. Assembled, the minimum clauses are:

1. **Disclosure.** AI assistance is declared on the change, in a machine-readable
   form that survives into version control and reaches the incident responder.
2. **Human liability.** A named human signs off. Agents may be credited; they may
   not be accountable.
3. **Comprehension before merge.** A named human can explain the change at review
   depth. Absent that, it does not merge.
4. **Independent verification.** The specification and the implementation do not
   share an author.
5. **Digestion is work.** Review, consolidation, deletion, and documentation are
   first-class engineering contributions and are resourced and rewarded as such.
6. **Protect the pipeline.** Organizations state how engineers acquire system
   understanding now that writing code no longer confers it.
7. **Honest measurement.** Effort-volume proxies are retired; outcome measures
   and comprehension measures replace them.

The clause software needs that mathematics does not is (3), because of the
operation stage. The clause mathematics has that software lacks the institutions
for is community acceptance — which is why (5) has to be an explicit resourcing
commitment rather than an appeal to professional norms.

## Appendix: remote-store as a worked example

This repository is an unusually complete instance of the argument, because its
process was built for exactly the conditions Tao describes. The mapping, and the
gaps.

Counts derived by running, from the repository root:
`ls sdd/adrs/[0-9]*.md | wc -l` → 38; `ls sdd/specs/*.md | wc -l` → 50;
`ls sdd/traces/[!_]*.yml | wc -l` → 279; `ls sdd/formal/*.dfy | wc -l` → 4.

| Stage | Existing machinery | Assessment |
|---|---|---|
| Generation | `.claude/skills/`, `CLAUDE.md` | Constrained rather than maximized. Skills encode workflows; hooks enforce what instructions only request. |
| Verification | Conformance suite, `hatch run all`, coverage gate, mutation lane, Dafny twins under `sdd/formal/`, TLA+ models | Strongest stage. The Dafny twins and mutation testing are direct answers to proposal 4: the spec and the implementation genuinely do not share an author. |
| Exposition | ADRs, [`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md), CHANGELOG discipline, docstring parity checks | The 6-month test and "no pseudo-precise values in narrative" are anti-drift rules, which is the exposition-stage failure Tao describes. |
| Publication | `/pr`, `/rvw-pr`, `/fix-pr`, `/ship` skills; convergence-driven review ([ADR-0033](../adrs/0033-ship-convergence-driven-review.md)) | Reviewing to convergence rather than to a round count is the explicit refusal of a Goodhart-vulnerable metric. |
| Operation | CI operations handbook, health checks, benchmark lane | Present but the thinnest stage relative to the others — expected for a library rather than a service. |
| Canonicalization | [`sdd/000-process.md`](../000-process.md) ("specs are source of truth"), the ripple-check, [`sdd/DRIFT-RULES.md`](../DRIFT-RULES.md), 279 traces, `sdd/BACKLOG.md` | This is the distinctive investment. Most repositories have nothing at this stage. |

Three observations worth recording.

**The traces are an instrument for the substrate collapse.** Trace files record
what an agent actually read, tagged `unclear` or `misleading` where a document
failed the reader, aggregated by `hatch run report-trace-outcomes`. That measures
comprehension transfer rather than authorship footprint — which is precisely the
substitution the truck-factor critique argues is now required. The schema's own
warning that "cleaned-up 'ideal' traces silently lie to the aggregator" is Tao's
friction argument applied to process data.

**Principle 9 is the talk rule in miniature.** Requiring that a figure name the
command it came from, derived before the sentence is written, is the same
demand: demonstrate that you can defend the claim, or do not publish it.
[ADR-0037](../adrs/0037-whole-file-gate-and-derived-figures.md) records the
measured failure modes that motivated it.

**The gaps.** Measured against § 6, three proposals have no mechanism here.
(1) Disclosure — commit messages carry backlog IDs but no `Assisted-by:` trailer,
so AI provenance does not survive into `git log`. (7) The training pipeline — a
single-maintainer project has no junior path to defend, but that also means the
repo cannot demonstrate the hardest proposal. (8) Comprehension measurement — the
traces instrument agent comprehension, not human comprehension of
agent-authored changes, and nothing currently asks whether a human could explain
a merged change at review depth.

These are observations, not recommendations to act. Per
[`CLAUDE.md` § Audits](../../CLAUDE.md), disposition is the user's call.

## Sources

Tao's talk and the mathematics context:

- [Mathematics in the age of AI, ICM 2026 slides](https://teorth.github.io/tao-web/slides/age-of-ai-icm-2026.pdf)
- [Leiden Declaration on AI and Mathematics](https://leidendeclaration.ai/) · [Wikipedia](https://en.wikipedia.org/wiki/Leiden_Declaration_on_Artificial_Intelligence_and_Mathematics) · [LMS announcement](https://www.lms.ac.uk/news/leiden-declaration-on-ai-and-mathematics) · [CACM commentary](https://cacm.acm.org/blogcacm/the-leiden-declaration-mathematics-ai-and-making-our-values-explicit/)
- [First Proof project](https://1stproof.org/) · [Scientific American on the results](https://www.scientificamerican.com/article/first-proof-is-ais-toughest-math-test-yet-the-results-are-mixed/)

Capability and productivity evidence:

- [METR: Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) · [arXiv 2507.09089](https://arxiv.org/abs/2507.09089)
- [DORA State of AI-assisted Software Development 2025](https://dora.dev/dora-report-2025/) · [Google Cloud announcement](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report)
- [Stack Overflow 2025 Developer Survey](https://survey.stackoverflow.co/2025/ai) · [trust findings](https://stackoverflow.co/company/press/archive/stack-overflow-2025-developer-survey/)
- [CloudBees 2026 State of Code Abundance](https://www.cloudbees.com/lp/2026-state-of-code-abundance-report) · [press release](https://www.cloudbees.com/newsroom/enterprise-technology-leaders-report-production-failures-from-ai-generated-code)

Pipeline degradation:

- [GitClear: AI Copilot Code Quality 2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research) · [The Maintainability Gap 2026](https://www.gitclear.com/the_ai_code_quality_maintainability_gap)
- [Analyzing Message-Code Inconsistency in AI Coding Agent-Authored Pull Requests](https://arxiv.org/abs/2601.04886)
- [AI-Generated Smells: Code and Architecture in LLM- and Agent-Driven Development](https://arxiv.org/html/2605.02741v1)
- [The Substrate Collapse](https://arxiv.org/pdf/2606.20882)
- [Veracode GenAI Code Security Report](https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/) · [Spring 2026 update](https://www.veracode.com/blog/spring-2026-genai-code-security/)
- [The AI Code Review Bottleneck, By the 2026 Numbers](https://www.flowverify.co/blog/ai-code-review-bottleneck-2026-data) · [CIO: the code review crisis](https://www.cio.com/article/4207438/the-code-review-crisis-and-how-you-should-rebuild-review-models.html)
- [Open source maintainers are drowning in AI-generated pull requests](https://thenewstack.io/ai-generated-code-crisis/) · [96% of codebases rely on open source, and AI slop is putting them at risk](https://thenewstack.io/ai-slop-open-source/)
- [The on-call cost of AI-generated code](https://greatcircle.com/blog/2026/06/09/on-call-cost-of-ai-generated-code/)
- [Slopsquatting research note (Cloud Security Alliance)](https://labs.cloudsecurityalliance.org/research/csa-research-note-slopsquatting-ai-supply-chain-20260419-csa/)

Theory, norms, and practice:

- [Peter Naur, Programming as Theory Building (1985)](https://pages.cs.wisc.edu/~remzi/Naur.pdf)
- [Assisted-by: how open source projects are drawing the line on AI contributions](https://allthingsopen.org/articles/open-source-ai-contributions-assisted-by-git-trailer-standard) · [Linux kernel policy coverage](https://www.tomshardware.com/software/linux/linux-lays-down-the-law-on-ai-generated-code-yes-to-copilot-no-to-ai-slop-and-humans-take-the-fall-for-mistakes-after-months-of-fierce-debate-torvalds-and-maintainers-come-to-an-agreement) · [QEMU relaxation patch](https://lists.nongnu.org/archive/html/qemu-devel/2026-05/msg07614.html)
- [Martin Fowler / Birgitta Böckeler, Exploring Gen AI](https://martinfowler.com/articles/exploring-gen-ai.html) · [Harness Engineering](https://martinfowler.com/articles/exploring-gen-ai/harness-engineering-memo.html) · [TDD inside the agent loop](https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html)
- [Simon Willison, Agentic Engineering Patterns](https://simonwillison.net/2026/Feb/23/agentic-engineering-patterns/)
- [Anthropic: Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices) · [How Anthropic teams use Claude Code](https://claude.com/blog/how-anthropic-teams-use-claude-code)
- [The 8 software engineering metrics AI broke](https://leaddev.com/ai/the-8-software-engineering-metrics-ai-broke)
- [Junior developer pipeline collapse](https://www.forbes.com/sites/josipamajic/2026/08/09/coding-jobs-vanish-for-juniors-as-ai-reshapes-career-path/)
