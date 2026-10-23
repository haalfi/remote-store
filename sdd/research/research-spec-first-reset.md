# Research: A spec-first reset toward v1, and how its specs are written (BK-485)

**Date:** 2026-10-23
**Backlog items:** BK-485 (The v1 Store API has no observable-semantics specs, so implementation runs ahead of decided behaviour)
**Status:** Research complete — ready for the reset RFC. A point-in-time
decision record of one maintainer session (2026-10-22 to 2026-10-23): the
decisions taken, the options they rejected, the two external research results
they rest on, and what is still open. Two RFCs are to follow from it: the reset
RFC (§ 2 to § 4) and the format RFC (§ 5 to § 6), which amends
[`sdd/SPEC-DESIGN.md`](../SPEC-DESIGN.md). Next: § 9's order, from step 1.
Decision log, for the dialogs it captured:
`sdd/decisions/406930fa-086e-5256-a50d-e95aa881810e.jsonl`. Decisions taken
after a worker restart on 2026-10-23 (F1 revised, F4 to F6, the deviation
warning) are not in that log; this document is their only record.

**Core claim.** remote-store v1 is specified first as observable semantics, what
a caller can see at the Store boundary with the implementation treated as a
black box, and only then implemented as kernel, driver and session. The specs
are designed one operation at a time in unprimed sessions, grounded in prior
art and in the accepted abstract layer, never in 0.33. Each clause takes the
most precise short form its category needs, carries a counterexample and a
named check, and lets backends vary only through declared, queryable
deviations from a normal value the contract states.

---

## 1. Why a reset

Spec 051 and the key-model research (PR #1173) stated structure and keys without
side effects from any implementation, and that worked. The specs before 051 do
not: they mix what an observer sees with how a backend achieves it, which is
the source of the contradictions recorded under BK-456 and BK-457. The library
also began without a kernel, driver and session split; RFC-0017 corrects that
in place, but its migration steps still run against specs that describe 0.33.
The maintainer considered forking the repo at v0.33.0 for spec-only work; § 2
records why the reset stays in this repo instead.

A ChatGPT session on 2026-10-21 showed the working method this record keeps:
describe one operation's situation, analyse the observable options, present
them with consequences, decide, record. Its `read()` decisions are kept in § 7
as input, not as decided semantics.

---

## 2. Reset decisions

| D | Decision | Rejected alternative and what it would change |
|---|---|---|
| D1 | **Goal:** consistent observable semantics for the v1 Store API. Behaviour may change relative to 0.33; every change gets a break record and a migration note. | Formalize 0.33 as it is: safest for users, but bakes in the design being revisited. |
| D2 | **Topology:** the spec work runs on master; `release/0.33.x` takes fixes only. | A fork: a clean break, but backlog, CI and `sdd/` tooling duplicated or abandoned. |
| D3 | **Evidence in the spec phase:** formal models, executable reference models with property tests, spikes and live probes. No production kernel or driver code. | Formal models only: nothing ties the specs to real backends. |
| D4 | **Method:** unprimed design sessions per operation (§ 4). | Free sessions with repo access: the drift the spec 051 work had to fight. |
| D5 | **Order:** the `read()` slice end to end first; shared layers (key, error, lifecycle, consistency) grow from what read needs. | Foundations first: shared layers designed without an operation pushing on them. |
| D6 | **Backend reality:** specs define abstract axes; a profile table per axis records Memory, Local, S3 and SFTP, each cell citing a dated probe or vendor document, kept beside the spec. | Per-backend spec sections: reality moves back into the specs being rewritten. |
| D7 | **Specs 001 to 050:** each gets a header marking it as 0.33 behaviour being superseded; each new spec names the sections it supersedes; a file emptied this way is deleted, with a register entry mapping old IDs to new. | Frozen as a legacy set: two spec sets coexist indefinitely. |
| D8 | **Comparison with 0.33:** a separate pass after the decisions. The conformance suite is the evidence of what 0.33 does; a difference becomes a break record or a bug. The pass never changes a decision; no test cell is removed until a new one replaces it. | Rewrite the suite to the v1 target at once: red until implementation resumes. |
| D9 | **Release:** one 1.0.0 cut; master publishes nothing until v1 is implemented. | 0.x pre-releases per operation: users migrate repeatedly. |
| D10 | **When kernel and driver work resumes:** open, postponed by the maintainer. | — |
| D11 | **Ground register:** one file lists every ground artifact, the flow that admitted it and its status (`active` or `reopened`); the design hook reads its allowlist from it (§ 3). | A fixed allowlist: cannot grow with each completed flow. |

---

## 3. The flow and the ground

A flow takes one operation from design to an accepted spec:

1. **Design:** an unprimed session (§ 4) decides the observable questions.
2. **Record:** the decisions go into the operation's research doc, with
   rejected options and open items.
3. **Spec:** the spec and its formal model are written in the format § 6
   fixes, with the per-axis profile tables (D6) beside it.
4. **Compare:** a separate pass against 0.33 (D8).

**The ground** is what a design session may read: prior art and the accepted
abstract layer. It grows with each flow but only from the new layer; 0.33's
code, tests and specs 001 to 050 are never ground. A flow's output joins the
ground once its spec and formal model are accepted; the comparison with 0.33
does not block admission, since it cannot change a decision. When a later
session finds a ground artifact wrong, it stops on that point and records a
reopen decision; the artifact goes through its own flow again, and the register
flags the flows that depend on it. A session never changes ground on the side.

At the start the ground holds prior art and spec 051. PR #1173's key model is
research, not an accepted spec, so it is not ground until the spec between 051
and 004 is accepted (open point 8).

---

## 4. The design method (working name `/observe`)

| S | Decision | Rejected alternative |
|---|---|---|
| S1 | **Ground:** prior art, the accepted abstract layer, the skill's own earlier decisions. Never 0.33's code, tests or specs. | Grounding in the existing specs and suite: the priming the spec 051 work fought. |
| S2 | **Enforcement:** a fresh agent, and a PreToolUse hook that denies reads outside an allowlist. | A strict prompt only: "don't look" did not hold in practice. |
| S3 | **Allowlist:** the ground register (D11) plus files the maintainer names when a session starts. | Maintainer names every input each time: more friction, less reproducible. |
| S4 | **Scope:** ends when every axis is decided or explicitly open, written to the operation's research doc. Comparison with 0.33 and spec drafting are later, separate steps. | Through the spec draft: mixes deciding and writing. |
| S5 | **Loop:** observation axes, then per question a concrete scenario, options with consequences, a recommendation, a decision with an ID, a consistency check against earlier decisions and the ground; open items stay visible. | Questions improvised per session: coverage depends on the run. |

---

## 5. Format research

**Brief.** An unprimed research brief: find a well-founded method, anchored in
Design by Contract, for specifying observable behaviour at a black-box
boundary, combined with measured evidence on which spec forms coding agents
implement and check reliably. Its core question: which spec categories a
boundary needs, the right level of abstraction per category, and the form per
category and level, given as a rule. It states five lessons as principles
(P1 what not how; P2 one claim per unit, one home per rule; P3 per-reality
detail bounded and apart; P4 a claim nothing checks is undecided; P5 the
method works unprimed) and adds a method excerpt from
[`research-store-model-axioms.md`](research-store-model-axioms.md)
(§ 1, § 5, § 6, § 8, without notation or axioms). The brief is kept verbatim
in the research repository (below).

**Two independent runs on the same brief:**

| Run | Where | Evidence handling |
|---|---|---|
| Claude Code, in an empty repository | `haalfi/research`, branch `research/black-box-boundary-spec`, `reports/Black box boundary spec methods.md` (v2) | Sources graded A to D; a verification pass over full texts, as the report states: 170 claims checked, 101 confirmed, 41 corrected, 5 refuted, 7 not found, 15 unverifiable, 1 C/D row not re-read |
| ChatGPT deep research | [shared result](https://chatgpt.com/s/t_6adb2684b1ec8191a63dd80f34ab1e86) | No source grades and no verification pass, which the brief required |

**Where both agree independently:** Design by Contract extended with traces,
assume-guarantee and refinement, no new formalism; three named observers
(caller, concurrent caller, out-of-band actor); nearly the same category cut;
a form rule that picks the weakest adequate form per category (Claude: "choose
the form by what the claim quantifies over"; ChatGPT: "the smallest model of
observation needed to distinguish a conforming behaviour from a
counterexample"); a counterexample and a named check per clause; one contract
whose profiles only select declared values; for agents, no measured ranking of
formats, but executable checks outside the agent's write scope.

**Where they differ,** and what § 6 took: the normative form (F1), whether the
reference model governs (F4), non-promises as their own category (F5), and the
scope of the failure category (F6).

**Further evidence read in the session:** Tufano et al.,
[Grounding AI Agents in Contracts](https://arxiv.org/abs/2608.17177) (Google,
SpecOps '26, workshop paper). On 90 historical Google bugs, an agent that first
wrote pre- and postconditions, each marked tested or untested, found 63.2% of
the bugs against the baseline's 53.4% at five runs (p = 0.035; not significant
at one run). Where its spec captured the violated contract, its tests caught
the bug in 54.9% of runs, otherwise in 19.4%. Missing error handling was the
second most common reason a spec missed a bug (32 runs). The specs were
inferred from the fixed code, so the paper measures the spec as a scaffold for
test writing, not as an authority. Figures are from the paper's Tables 2 to 4
and § 5.3.

---

## 6. Decisions from the format research

| F | Decision | Rejected alternative and what it would change |
|---|---|---|
| F1 | **Normative form.** The normative claim takes the most precise form its category needs, kept short: one formula, one table row or one transition, never a paraphrase in a second notation. Each unit carries a one-sentence plain reading as a non-normative label. | Always one sentence of prose (the Claude report): the authority sits in the less precise of two statements, which can drift apart. |
| F2 | **Categories, provisional:** structure; value function; single call; resource life; environment; multi-observer guarantee; failures (F6); profile; non-promise register (F5). Revisited after the `read()` slice. | Fixed now: the cut is unproven on a real operation. |
| F3 | **Non-commitment vocabulary** inside clauses: unspecified, profile-declared, optional (MAY), indeterminate, deliberately not promised. "Undefined" is not allowed at the boundary, since no check can be written against it. | Keep "undefined" for caller-contract violations. |
| F4 | **Profiles.** Variation points belong to the operation, and a profile holds values per operation and per guarantee, never a kind of backend. The contract states each variation point's normal value; the reference model only implements it and is checked against it. A reality that delivers less declares a deviation: queryable like `supports()`, listed in the generated docs, and announced by a dedicated `DeviationWarning` once per store instance, operation and deviation, silenced only through Python's warnings filters. The formal range is the normal value plus all declared deviations, and no reality goes outside it. | The reference model's default profile as the normal value: the model becomes a second authority that can silently choose among unspecified outcomes. Widening profiles: a caller written against the contract breaks silently on one backend. |
| F5 | **Non-promise register.** Each deliberate non-promise (latency, buffering, request count, and the like) has an ID and a scope in one register; a check confirms no test asserts what is not promised. | Vocabulary only: the same non-promise restated in several clauses, with no list to audit tests against. |
| F6 | **Failure category.** Per failure: the category the caller sees, the phase in which it can be reported, what an observer may conclude about the effect, and whether a retry could repeat it. Temporal or multi-observer parts reference the lifecycle or history category. | Recovery class only: effect certainty and failure phase without a home. |

---

## 7. Input for the `read()` design session

The 2026-10-21 ChatGPT session decided these for `read()` before the method
existed, from a primed context. They are candidate answers for the first
design session to confirm or replace, not decided semantics.

| ID | Candidate decision |
|---|---|
| R-1 | Stability of an open stream under concurrent modification is backend-qualified. |
| R-2 | `read()` establishes access to the target before it returns; errors while consuming the stream remain possible. |
| R-3 | Standard stream semantics: an I/O failure is raised, never reported as end of file. |
| R-4 | `LAZY_READ` means the stream is returned without first acquiring the whole content; no memory bound is promised. |
| R-5 | The stream depends on the store: closing the store may invalidate open streams. |
| R-6 | Stable public error categories; "not found" only where the backend can tell. |
| open | Whether a stream must deliver bytes from one version of the item for its whole life. |

Both research reports offer witness values for these axes, for example Hadoop
`open()` against `openFile()` for R-2, and S3 GET against Hadoop's stream
contract for R-1 and the open question.

---

## 8. Open points

1. **D10:** when kernel and driver work resumes.
2. When a variation point is better split into a second operation than given
   more deviations (precedent: Hadoop `open()` and `openFile()`).
3. Scoping the bake-off: the Claude report's § 7.3 design is costly (several
   fresh agents per form, mutation scores, a tamper protocol).
4. The cut of the `read()` slice.
5. The reset's relationship to RFC-0017: pause, amend or re-decide its
   migration steps, and what happens to the Memory driver already on the
   kernel.
6. The observation axes for `/observe`: where they live, and who drafts them
   unprimed.
7. The signal that lets the design hook restrict only the design agent.
8. PR #1173's key model as ground: finish the key spec before the `read()`
   flow, or name it as a session addition.
9. The break-record format, and how break records reach the migration guide.
10. Open backlog items that depend on 0.33 behaviour: keep, close, or move to
    `release/0.33.x`.
11. How the two research reports enter this repo as input for the format RFC.

---

## 9. Results and recommendation

**Result.** Two independent research runs on one unprimed brief (§ 5) agree on
the method: Design by Contract extended with traces, assume-guarantee and
refinement; named observers and an explicit environment; a form chosen per
category as the weakest that still tells a conforming behaviour from a
counterexample; a counterexample and a named check per clause; one contract
whose profiles only select declared values. Neither finds a measured ranking
of spec formats for coding agents; both find that executable checks outside
the agent's write scope are what agents conform to. F1 to F6 (§ 6) take this
into decisions; D1 to D11 and S1 to S5 (§ 2, § 4) fix the process around it.

**Recommendation.** Make the reset binding with two small decisions, build the
design tool, then run one complete flow on `read()` before anything is scaled.
That flow is also the cheapest experiment for the open format question, so no
separate bake-off precedes it. BK-485 tracks the steps.

| Step | Work | Why here |
|---|---|---|
| 1 | Cut `release/0.33.x` (D2). Pause RFC-0017's migration steps: the Memory driver stays on the kernel, no further backend moves onto it until its specs exist (open point 5). | Kernel code is otherwise written against the specs being replaced. Both reports put the spec and an independent oracle before the implementation. |
| 2 | The reset RFC: D1 to D11, with D10 recorded as open, and open points 5, 9 and 10. Process only; format is step 6. | Turns this record into binding process. |
| 3 | `/observe` with its hook, the ground register and the observation axes (S1 to S5, D11). The axes are drafted unprimed, from the reports' categories and F1 to F6. | Every later design session needs it. |
| 4 | The key spec between 051 and 004 (BK-484; open point 8). | Recommended so the key layer is accepted ground before `read()` leans on it. D5 would also let key questions be decided inside the `read()` flow, and S3 lets the key research be named as a session addition; open point 8 keeps that choice. |
| 5 | The first flow, `read()`: an `/observe` session with § 7 as candidate input; the spec in the provisional F1 to F6 format; a reference model written fresh from the spec, with its counterexample mutants; the profile tables for Memory, Local, S3 and SFTP; the comparison with 0.33. | Tests the category cut and the form rule, both unproven on a real operation in both reports. Puts the independent check before any implementation, the one point where the agent evidence is strong. |
| 6 | A minimal bake-off on the finished slice: the same clauses as normative prose with a conformance suite (the Claude report's shortlist 3), fresh agents implementing against each, scored on mutants killed and guarantees invented. Then the format RFC amends `SPEC-DESIGN.md` with F1 to F6 and the category list. | Holds the decisions fixed and varies only the form, which both reports name as the missing measurement. |

Steps 3 and 4 can run in parallel; every other step closes a dependency of
the next.

**Not yet.** The "being superseded" header (D7) goes onto an old spec only
when a new spec replaces its sections, not onto all fifty now. The Claude
report's full bake-off design (several agents per form, a tamper protocol)
waits until a slice exists. D10 is decided with the `read()` flow's evidence
in hand.

---

## Sources

- ChatGPT session "Architecture proposal for remote-store", 2026-10-21:
  https://chatgpt.com/share/6ada045e-5c90-83eb-8340-f4d07c592907
- Claude Code deep research, report and brief:
  https://github.com/haalfi/research/tree/research/black-box-boundary-spec
  (private repository)
- ChatGPT deep research, same brief:
  https://chatgpt.com/s/t_6adb2684b1ec8191a63dd80f34ab1e86
- Tufano et al., Grounding AI Agents in Contracts: An Empirical Evaluation of
  Spec-Driven Test Generation, SpecOps '26: https://arxiv.org/abs/2608.17177
- In this repo: [spec 051](../specs/051-store-tree.md),
  [`research-spec-design.md`](research-spec-design.md),
  [`research-store-model-axioms.md`](research-store-model-axioms.md),
  [RFC-0017](../rfcs/rfc-0017-contract-kernel-over-thin-drivers.md),
  [RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md).
