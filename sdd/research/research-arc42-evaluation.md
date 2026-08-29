# Research: arc42 as an architecture-level specification layer

**Date:** 2026-08-28
**Backlog items:** none — the question arrived directly, and § 4 explains why it
leaves none behind
**Status:** Research complete — disposition filed in
[`BACKLOG-DONE.md` § Decided against](../BACKLOG-DONE.md#decided-against)

---

## 1. Problem Statement

[arc42](https://arc42.org/) is a twelve-section template for architecture
documentation. The case for adopting it in a spec-driven repository worked by
coding agents is that it gives architectural intent a predictable, complete,
agent-readable home: instead of re-explaining boundaries, quality goals and
prior decisions in prompts, you maintain them as versioned documents an agent
consults before proposing a change. The pitch names specific agent failure modes
— adding a dependency that violates a platform rule, placing a component in the
wrong layer, implementing a happy path only, reopening a settled decision — and
maps each to the arc42 section that would have prevented it.

The question this document answers is whether that is worth doing here.

The obvious method is to walk the twelve sections, find the ones this repo has
no document for, and fill them. That method is the one
[research § 1](research-spec-kit-comparison.md) already rejected for the same
class of question: **it selects for absence rather than for cost.** A section
this repo has never had, and has never paid for not having, is not a gap, and
filling it spends review attention — the scarce resource — on a problem we do
not have.

So the decision is narrower than "is arc42 good": **which of its sections
addresses a failure this repo can show evidence of.** The primary filter is the
trace corpus, which records where our own descriptions have failed their readers
([`CONTENT-RULES.md`](../CONTENT-RULES.md)). § 3.1 states what that filter cannot
see, and supplies a second instrument for the part it misses.

Constraints that bind the answer:

- [`DRIFT-RULES.md` Rule 1](../DRIFT-RULES.md#one-driver): prefer one normative
  description driving N artifacts over N² pairwise checks. Twelve new documents
  restating what specs already state normatively is the shape this rejects.
- [`DRIFT-RULES.md` Rule 8](../DRIFT-RULES.md#independence): a second description
  must record what it was derived from, and independent authors do not produce
  independent errors.
- [`AUTHORING.md` Rule 2](../AUTHORING.md#rules): each `.md` lives at exactly one
  path; other presentations are derived, never copied. [ADR-0006](../adrs/0006-documentation-architecture.md)
  is the record of what it cost to have two homes for the same content.
- [`CLAUDE.md` principle 8](../../CLAUDE.md#principles): detail belongs at the
  layer whose change-rate and correctness-locus fit it.
- [`CONTENT-RULES.md` Rule 1](../CONTENT-RULES.md#six-month-test): anything
  adopted has to still be true in six months.

---

## 2. Survey

### 2.1 arc42

**Pattern:** architecture documentation as a fixed, tailorable table of contents.
Twelve purpose-specific sections, all optional, tool-agnostic, intended for
docs-as-code rather than a documentation ceremony. The template's own guidance is
to document only what stakeholders need in order to understand the system, and to
leave the rest sparse.

**How it works in the agent-enabled framing:** the twelve sections become stable
paths (conventionally `docs/architecture/01-…` through `12-…`) that an agent is
instructed to read before planning a change. Section 9 (Architecture Decisions)
holds ADRs; section 8 (Cross-cutting Concepts) holds error handling, logging,
auth and validation conventions; section 10 (Quality Requirements) holds
measurable scenarios that convert into acceptance criteria and tests; section 11
(Risks and Technical Debt) records areas an agent must not opportunistically
"clean up". A prompt contract in an agent-instructions file points at the index
and requires a change proposal naming affected building blocks, applicable
decisions and quality scenarios before implementation.

**Trade-offs:**

- Pro: the section list is a genuinely well-factored vocabulary for the questions
  an agent otherwise guesses at, and it is stable across projects, so it travels.
- Pro: it is explicitly tailorable — sparse use is sanctioned by the method
  itself, so adopting three sections is not a deviation.
- Con: every section is descriptive prose. Nothing in the template is executable,
  and its own limits section concedes that documentation alone is advisory and
  goes stale when updates are optional.
- Con: the framing it is usually pitched in is a deployed service — hosting,
  environments, secrets, scaling, observability in production, database
  migrations. A library has no deployment topology of its own.
- Con: the recommended layout puts architecture under `docs/`, a location this
  repo has already decided against (§ 3.4).

### 2.2 What this repo has, section by section

Mapping is by function, not by name — the question is whether a reader looking
for what section N answers has an authoritative place to look.

| arc42 section | Where the answer lives here | Status |
|---|---|---|
| 1. Introduction and goals | [`README.md`](../../README.md) — what it does, audience, when not to use it — and its § Quality & Testing, which states the quality intent per dimension; [`FEATURES.md`](../../FEATURES.md) | Covered |
| 2. Constraints | **Conventions:** the nine root-level `sdd/` process documents [`CONTRIBUTING.md` § Authoritative Document Format](../../CONTRIBUTING.md#authoritative-document-format) scopes, applied in a declared order ([`CLAUDE.md` § Documentation framework](../../CLAUDE.md#documentation-framework)). **Technical:** [ADR-0003](../adrs/0003-fsspec-is-implementation-detail.md), [ADR-0008](../adrs/0008-extension-architecture.md), [`sdd/DESIGN.md`](../DESIGN.md), `pyproject.toml` | Covered — a declared framework, not a scatter |
| 3. Context and scope | `README.md`, [spec 003](../specs/003-backend-adapter-contract.md), [`explanation/security-model.md`](../../docs-src/explanation/security-model.md) | Covered |
| 4. Solution strategy | [ADR-0001](../adrs/0001-architecture-store-registry-backends.md), [`explanation/architecture.md`](../../docs-src/explanation/architecture.md) | Covered |
| 5. Building-block view | ADR-0001, `explanation/architecture.md`, [`CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) repo layout | Covered |
| 6. Runtime view | [spec 001](../specs/001-store-api.md), [spec 006](../specs/006-streaming-io.md), [spec 022](../specs/022-streaming-atomic-writes.md), [`explanation/concurrency.md`](../../docs-src/explanation/concurrency.md) | Covered |
| 7. Deployment view | [`infra/`](../../infra), [`packaging/`](../../packaging) | Largely inapplicable |
| 8. Cross-cutting concepts | [spec 004](../specs/004-path-model.md), [spec 005](../specs/005-error-model.md), [spec 020](../specs/020-credential-hygiene.md), [spec 025](../specs/025-retry-policy.md), [`sdd/formal/`](../formal), the conformance suite | Stronger than the template asks |
| 9. Architecture decisions | [`sdd/adrs/`](../adrs) plus a generated [`DIGEST.md`](../adrs/DIGEST.md) with a gated supersession graph | Stronger |
| 10. Quality requirements | [`README.md` § Quality & Testing](../../README.md) names nine verified dimensions; each is enforced by a mechanism, not asserted — `benchmarks/` baseline gate, `mutation.yml`, `drift-guard.yml`, `codeql.yml`, `ci-full.yml` (inventoried in [`CI-OPERATIONS.md`](../CI-OPERATIONS.md)), the 95% coverage floor, the Dafny layer, Hypothesis, the conformance suite | Stronger — the requirements execute rather than being read |
| 11. Risks and technical debt | [`BACKLOG.md`](../BACKLOG.md), [`BACKLOG-DONE.md`](../BACKLOG-DONE.md), [`sdd/audits/`](../audits) | Stronger |
| 12. Glossary | Absent | Absent, and § 3.4 finds no cost |

Ten of the twelve have an authoritative home — every row above except 7, which
has little subject matter in a library, and 12, which is genuinely absent.

The four rows marked stronger are not close.

- **§ 8 and § 9** are prose a reader consults in arc42; specs 004, 005, 020 and
  025 are normative clauses with stable `PREFIX-NNN` identifiers, traced to
  conformance tests by
  [`check_spec_marks.py`](../../scripts/check_spec_marks.py), with a Dafny layer
  under `sdd/formal/` for the core contract.
- **§ 10** asks for measurable quality scenarios a reader converts into tests.
  Here the conversion has already happened in the other direction: each of the
  nine dimensions README names is a mechanism that fails a job. `mutation.yml`
  and `drift-guard.yml` run on their own schedules and open rolling issues;
  `codeql.yml`, `ci-full.yml` and `benchmark.yml` have runbooks in
  [`CI-OPERATIONS.md`](../CI-OPERATIONS.md), whose inventory
  `check_ci_inventory.py` gates against `.github/workflows/`. A scenario that
  runs weekly and files its own issue is not improved by also being a paragraph.
- **§ 11** asks for a list of known debt; `BACKLOG.md` is a promise-structured
  register with an admission test, an authority rule, and a drain file that
  records refusals so the same argument is not had twice.

---

## 3. Evaluation

### 3.1 The filter, and the thing it cannot see

`hatch run report-trace-outcomes`, measured at **`47f1b16`**:

| Measure | Value |
|---|---|
| Traces | 287 |
| Steps | 4,300 |
| Steps carrying an explicit `outcome` | 2,047 (47.6%) |
| Negative tags | 241 (`misleading` 204, `unclear` 37) |
| Traces and references carrying them | 121 traces, 118 references |

These figures are exact at the named commit and perishable, and the commit is
stamped for the reason [research § 3.1](research-spec-kit-comparison.md)
established: this document's own work adds to the corpus it measures, so an
unstamped table is false on arrival. Re-run the report and compare against
`47f1b16` rather than trusting the numbers.

The report's three documented bounds apply unchanged here — drain files split one
artifact's signal across two rows, the sort key measures exposure at least as much
as failure rate, and `rate`'s denominator mixes assessed with never-assessed
reads.

**A fourth bound matters more for this question than any of those three, and the
spec-kit precedent did not have to state it.** The corpus records what readers
read. **A document that does not exist cannot be tagged.** So the filter is
strong evidence for "should we restructure, merge or delete a document we have",
and it is *structurally blind* to "is an artifact missing". Three of the four
candidate dispositions in § 3.4 were advanced *as* missing-artifact claims — two
of them wrongly, as § 3.4 records — and reading their zero tags as a verdict
would be the same error as reading a shallow clone's zero commits as a quiet
period.

So a **second instrument** carries the missing-artifact half: for each candidate,
ask whether the thing arc42 would document already exists in a *non-prose* form —
an executable gate, or a tracked item with a named owner and cadence. Where it
does, the candidate is not a missing artifact but a missing *restatement*, and
[principle 8](../../CLAUDE.md#principles) decides restatements. Where it does not,
the candidate survives to be argued on its own. § 3.4 applies both instruments per
row and says which one decided.

### 3.2 What the corpus says about narrative architecture prose

arc42's deliverable is eleven or twelve narrative documents. This repo already has
one document of exactly that class and shape — `docs-src/explanation/architecture.md`,
which is arc42 § 4 and § 5 in miniature: the three-layer diagram, what each layer
is for, the error hierarchy, the capability system, the configuration philosophy.

It is cited **once** in the entire trace corpus (`rg -c
'docs-src/explanation/architecture\.md' sdd/traces` returns one file with one
hit, `bk-246-tracker-id-cleanup.yml`, where it was edited rather than consulted).

Counting citations by artifact class with one consistent method — `rg -c
'<prefix>' sdd/traces`, which counts every mention in a trace, not only step
references:

| Artifact class | Mentions in `sdd/traces` | Files |
|---|---:|---:|
| `sdd/specs/` | 359 | 147 |
| `sdd/adrs/` | 93 | 32 |
| `docs-src/explanation/` (every page under it) | 60 | 49 |
| `docs-src/explanation/architecture.md` | 1 | 1 |

**Read the method, not just the ranking.** This counts mentions, which is a
looser measure than the report's `reads` column (steps citing a reference); for
`architecture.md` the two agree at 1, and for the classes the mention count is
the reproducible one. It is a measure of what contributors and agents working in
this repo consult, and says nothing about end users of the docs site, who are the
audience `docs-src/explanation/` is written for and who leave no traces. The claim
is therefore bounded: **narrative architecture prose is the least-consulted
artifact class in the agent-facing corpus**, not that it is unread by everyone.

That bound does not weaken the conclusion, because arc42's case is specifically an
*agent-behaviour* case. The pitch is that agents consult these documents before
proposing changes. In the one instance where this repo already runs that
experiment, they do not, and the artifacts they do consult — specs, the backlog,
the ripple-check, source — are the ones with identifiers, gates and obligations
attached.

### 3.3 The one cluster that looks arc42-shaped, and what it actually is

Two references carry a dense negative-tag cluster around the same subject — what
a backend implementer must do — which is arc42's "agent violates a platform rule
/ implements against the wrong constraints" row:

| Total | `misleading` | `unclear` | `reads` | `rate` | Reference |
|---:|---:|---:|---:|---:|---|
| 7 | 5 | 2 | 73 | 9.6% | `sdd/specs/003-backend-adapter-contract.md` |
| 5 | 5 | 0 | 11 | 45.5% | `docs-src/guides/custom-backend-guide.md` |

Spec 003 is the most-read spec in the corpus, and the guide's `rate` is the
highest of any documentation file clearing a meaningful read count. **The two
clusters are different failures, and reading them as one total would invert the
conclusion.** Reading the extracts rather than counting them:

Spec 003's seven are *spec-internal*: BE-029's root row outranking § Reach's
NotFound row was stated only in a docstring and a backlog item (`bug-246`); a
clause placed writes to the root outside itself on a true premise and a wrong
conjunction (`bug-259`); the completeness clause was described as symmetrically
gated when the obligation had been weakened (`id-184`). Each was amended in the
same change that found it. That is a normative artifact being sharpened as cases
reach it — the process working, not a home missing.

The guide's five are drift: four are contract claims that were false against the
contract, and the fifth is stale test-path residue.

- `bk-320`: "Walkthrough agents consumed the guide as their sole instruction
  source; the Step 5/8 root-alias invariants and the standalone checklist's
  wrong-type rows proved wrong against the conformance-passing `s3_boto3`
  backend."
- `bug-259`: "The document a custom-backend author implements against, falsified
  by this change and not in its diff… It told implementers the root refusal was
  'a Store-enforced convention'" when the same item promoted it to a contract
  clause.
- `bug-259`, again: "The pattern across rounds 5, 6 and 7 is that the guide is the
  artifact each round updates last and verifies least."
- `bk-324`: the PR "shipped a guide line that told third-party backend authors to
  make the probe fail-open, unqualified — one commit after the same PR diagnosed
  that exact conflation as BUG-242's root cause."

This is the strongest architecture-adjacent evidence in the corpus, and it argues
**against** arc42 rather than for it. The failure is not that constraints lack a
home. They have one, it is normative, and it is the most-read spec in the repo.
The failure is that a *second* statement of the same constraints, written for a
different audience, is updated last and verified least. Adding arc42 § 2 as a
third statement is [Rule 1](../DRIFT-RULES.md#one-driver)'s N² shape with one
more node, and [Rule 8](../DRIFT-RULES.md#independence) says the new node —
derived from the same specs by the same kind of pass — would not even fail
independently.

The second instrument finds the ground held twice over:

- [`scripts/check_custom_backend_guide.py`](../../scripts/check_custom_backend_guide.py),
  wired into `lint` and `docs-gate`, differences the guide against
  `Backend.__abstractmethods__`, the conformance files it names, and the fixture
  loader's closed vocabularies.
- **BK-332** schedules the custom-backend rehearsal on a
  [Rule 9](../DRIFT-RULES.md#period) cadence anchored to the two events that can
  invalidate the guide, and states its own evidence level as n = 1.

**The gate's stated bound is what settles the arc42 question here**, and it is
stated in its own docstring rather than inferred: it proves *structural sync* —
names, members, files, enum values — and cannot reach a prose claim about what a
clause requires. Every one of the four contract-drift tags is in that
unreachable class: a sentence about the root refusal being a convention, a
sentence prescribing an unqualified fail-open probe. So the residual failure is
semantic drift between two prose statements of one contract, which
[research § 1](research-inconsistency-detection-multi-artifact.md) marks as
having no general oracle. A twelfth prose document is a net addition to exactly
the class nothing can check.

### 3.4 Candidates against the evidence

Four dispositions were put to evaluation: the full skeleton, and the three
sections that looked thin here on a first reading — § 2, § 10, § 12. The full
skeleton is evaluated separately because a reject of the parts does not by itself
reject the whole.

**Two of those three were thin only in the reading, not in the repo**, which
§ 2.2 now records: § 2's conventions are a declared nine-document framework, and
§ 10's requirements execute. Both were corrected by opening the source — the
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#authoritative-document-format) scope
list and `README.md` § Quality & Testing — after a first pass had judged them from
the section names. That is the same defect twice, and § 3.4's § 10 note and
§ 4.3's closing paragraph both turn on it.

| Candidate | Trace evidence | Second instrument | Verdict |
|---|---|---|---|
| § 10 — quality requirements as measurable scenarios | Zero tags; and the filter is blind here (§ 3.1) | The requirements **exist and execute**, across all nine dimensions README names — not only performance. `benchmarks/baseline/local-baseline.json` at `threshold 2.0` / `min-abs 0.0005` in [`benchmark.yml`](../../.github/workflows/benchmark.yml); `mutation.yml` and `drift-guard.yml` on their own schedules with rolling issues; `codeql.yml`; `ci-full.yml`; the 95% coverage floor; the Dafny layer and conformance suite. The benchmark gate's local-only scope is registered in BK-309's `BACKLOG-DONE.md` entry, the [Rule 6](../DRIFT-RULES.md#tolerated) form | **Reject** |
| § 2 — a single constraints home | The 5 guide tags are drift between two prose statements of one contract; spec 003's 7 are the normative doc being amended, not a missing home (§ 3.3) | The conventions already have a home *and a declared read order* — the nine process documents `CONTRIBUTING.md` scopes. The one measured drift site is held twice more: [`check_custom_backend_guide.py`](../../scripts/check_custom_backend_guide.py) in `lint` and `docs-gate`, plus **BK-332** on a Rule 9 cadence | **Reject** — the evidence argues the other way |
| § 12 — glossary | Zero tags; a keyword pass over all 241 negative tags for terminology, vocabulary, naming and ambiguity returns no instance of a reader blocked on vocabulary | No non-prose form exists, so this candidate genuinely survives instrument two — and has no evidence of cost to justify it | **Reject**, revisitable (§ 4.2) |
| Full twelve-section skeleton | `architecture.md`, the one document of this class, is cited once in 287 traces (§ 3.2) | Rules 1 and 8; `AUTHORING.md` Rule 2; ADR-0006 | **Reject** |

Two rows deserve their reasoning stated rather than compressed into a verdict.

**§ 10 is the row this evaluation got wrong twice, and the second miss is the
instructive one.** The pre-evidence reading was that quality requirements were
the strongest candidate, because `benchmarks/` measures and no prose states a
target. Opening `benchmark.yml` falsified that: a committed baseline, a stated
threshold, a stated floor, a stated scope and a registered bound are more than
arc42 § 10 asks for, and they fail a job rather than advising a reader.

**The correction was then itself under-scoped**, and review caught it. Having
opened the benchmark workflow, the row was rewritten to cite *only* the benchmark
workflow — as though performance were the whole of § 10. `README.md` § Quality &
Testing enumerates **nine** verified dimensions, of which benchmarks is one, and
[`CI-OPERATIONS.md`](../CI-OPERATIONS.md)'s gated inventory carries five more
`.github/workflows/` rows besides `benchmark.yml`. So the first fix
repaired the sentence a reviewer would have pointed at and left the class it
belonged to open — the failure mode
[`BACKLOG.md` § Item authority](../BACKLOG.md#how-this-file-works) describes, met
here in a research doc rather than an item.

What is absent in both readings is the *restatement*, and
[principle 8](../../CLAUDE.md#principles) puts a quality bar's authoritative home
at the mechanism that enforces it. The residue is real and already registered:
only the local backend is timing-gated, because the Docker backends have no
runner-captured baseline. That is a coverage bound with an owner, not a missing
document.

**The full skeleton was evaluated on its own terms, not dismissed as the sum of
the parts.** The maximal case is that the sections are worth more together than
apart: an agent reading one index gets boundaries, constraints, decisions and
qualities in a known order, which no assembly of specs provides. Against that:
eleven of twelve sections would be derived from artifacts this repo already
treats as authoritative, by one pass, which is precisely the derivation
[Rule 8](../DRIFT-RULES.md#independence) says produces correlated rather than
independent errors; the resulting documents would compete with `sdd/` for the
"where does this belong" question that [`AUTHORING.md` Rule 2](../AUTHORING.md#rules)
exists to answer once; and the conventional `docs/architecture/` location is
unavailable by construction, since [ADR-0006](../adrs/0006-documentation-architecture.md)
makes `docs/` a generated, gitignored representation. The index argument is the
strongest half and it already has a home: `CLAUDE-REFERENCE.md` is the most-read
document in the corpus and is exactly an architectural index, one whose rows are
triggers and ripples rather than chapters.

---

## 4. Recommendation

**Adopt nothing. File nothing.** The four candidates are rejected above, and the
rejections are the substance of this document.

### 4.1 Where the decision is registered

[`BACKLOG.md` § How this file works](../BACKLOG.md#how-this-file-works) gives a
refused idea the same register entry a removed one gets: a line in
[`BACKLOG-DONE.md` § Decided against](../BACKLOG-DONE.md#decided-against) with a
`—` where the ID would be, carrying the diagnosis and not only the verdict. That
entry is where a future reader meets this decision; this document is what it
points at.

No backlog item is filed, and that is the admission test operating rather than an
omission. An item that fits no section's promise has no demonstrated value; on
today's evidence none of the four fits one.

### 4.2 What would change the answer

Stated so a reversal needs new evidence rather than a new opinion.

- **§ 12 (glossary)** is the only candidate rejected purely for want of evidence
  rather than because a better mechanism holds the ground. Re-file under a new ID
  the first time a trace tags a document `unclear` for vocabulary — a reader who
  could not tell which sense of "child", "root", "native path" or "capability" was
  meant. The instrument already exists and needs no new mechanism: the tag, and
  the report that ranks it.
- **§ 2 (constraints)** reverses if BK-332's rehearsal runs at its stated cadence
  and the custom-backend guide's negative tags do *not* fall — currently 5 at
  `47f1b16`. That would mean the drift is not a rehearsal-frequency problem, and a
  differently-shaped home would be back in scope. Rules 1 and 8 would still bar a
  third prose copy, so the shape would have to be **generation** from spec 003,
  extending what `check_custom_backend_guide.py` already does structurally into
  the semantic half its docstring declares out of reach — not authorship beside
  it.
- **§ 10 (quality requirements)** reverses if a defect ships past all nine
  enforced dimensions and the post-mortem finds that a *stated* scenario would
  have caught it where the mechanisms did not. The near case is a performance
  regression in a backend the local baseline cannot see; the remedy there is a
  runner-captured baseline for the Docker backends, which is a gate change and
  not a document. A reversal needs the harder version: a quality this repo cares
  about that no mechanism expresses at all.

### 4.3 What this document does not claim

The reading of arc42 is of its published template and method pages, not of a
project run with it. Claims about how its sections behave in practice are
inferences from the template's own guidance, which is sufficient for the
adopt/reject decisions in § 3.4 — those turn on our evidence, not on arc42's —
and insufficient for any claim about how well arc42 serves its own users.

**The verdict is about this repository at this maturity, and says nothing about
arc42 generally.** Every "stronger" row in § 2.2 is stronger because something was
built there: 50 specs with stable IDs, 38 ADRs with a gated digest, a formal
layer, a promise-structured backlog, nine quality dimensions each wired to a
mechanism, and 22 `check_*.py` cross-artifact gates
(`ls scripts/check_*.py scripts/docs/check_*.py`). A repository
without those would find arc42's sections a considerable improvement on nothing,
and the same filter run there would return the opposite answer. What is being
rejected is a second description of ground already held normatively — not the
template.

**Two of the four dispositions were argued from an under-read of this repo before
review corrected them** (§ 3.4). That is worth stating as a limit on the method
and not only as a fixed defect: the mapping in § 2.2 is a *reading* of where each
answer lives, and a reading can be short in a direction its own author cannot
see. Both misses ran the same way — judging a section from its name against a
sample of its homes, rather than from the repo's own enumerations
(`CONTRIBUTING.md` § Scope, `README.md` § Quality & Testing,
`CI-OPERATIONS.md`'s gated inventory). Both made the rejected candidate look
*more* attractive than the evidence supports, so the direction of the error was
toward adopting, and the verdict survived correction in both rows. A future
reading that reverses one should check that enumeration first.

**§ 3.2's measure is agent-facing and bounded.** It counts what leaves a trace,
which is contributor and agent work. `docs-src/explanation/` is written for docs
site readers, who leave none. A low citation count there is evidence about the
agent-behaviour claim arc42 is being evaluated on, and is not evidence that the
page fails its own audience.
