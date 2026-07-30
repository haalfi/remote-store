# Research: Compiling the repo's rules into a single rulebook

**Date:** 2026-07-30
**Status:** Point-in-time PoC record. **Negative result**: the artefact under test
failed its own pre-registered success criterion and is not recommended for
adoption in the form built. No backlog items were created; § 8 lists three
findings that a maintainer may want to action separately.
**Scope:** Whether the repo's binding rules can be compiled into one document
that an agent reads *instead of* the source process docs. Covers the artefact
built (`sdd/RULEBOOK.md`, branch `claude/principles-rules-rulebook-poc-euimxw`),
a static coverage analysis over the trace corpus, and a 16-run A/B replay
experiment. Does not cover generator tooling, drift gating, or any change to the
source docs; none were built.
**Related:** [`CLAUDE.md` § Principles](../../CLAUDE.md#principles),
[`CONTRIBUTING.md` § Authoritative Document Format](../../CONTRIBUTING.md#authoritative-document-format),
[`sdd/adrs/DIGEST.md`](../adrs/DIGEST.md) (the generated analogue this imitated),
[`sdd/traces/_schema.yml`](../traces/_schema.yml) (the ground truth),
[`research-inconsistency-detection-multi-artifact.md`](research-inconsistency-detection-multi-artifact.md).
**Evidence:** [`rulebook-poc/`](rulebook-poc/README.md) — pre-registration, 16 raw
run outputs, and the four analysis scripts.

**Context:** Nine documents state binding rules for this repo: `CLAUDE.md` and
the eight `sdd/` process docs that follow the Intent & Scope / Rules / Guides
format. `sdd/adrs/DIGEST.md` already proves that compiling a scattered artefact
class into one generated document is useful for ADRs. This PoC asked whether the
same move works for rules, hand-built first to learn the shape before writing a
generator.

## 1. What was built

`sdd/RULEBOOK.md`, 294 lines compiled from roughly 1,680 lines of source.
Ordered by working process rather than by filename: always-on conduct, plan,
build, test, document, guard, ship. One section per source doc, each a short
scope line plus that doc's rules, with source rule numbering preserved so
existing references such as "TESTING rule 4" still resolve.

Compilation conventions, which turned out to be the decisive design choice:

- Flat prose rules verbatim.
- Rules whose body is a lookup table, code example, or multi-paragraph
  exposition **condensed** to their normative sentences with the source linked,
  because copying the tables would breach
  [CONTENT-RULES rule 4](../CONTENT-RULES.md) inside a document meant to make
  rules easier to obey.
- `## Guides` sections, examples, rationale and provenance dropped.
- Header marks the document non-authoritative and hand-compiled: source docs win
  on conflict.

## 2. Method

Usefulness was not assessed by reading the artefact. `sdd/traces/*.yml` records,
per completed backlog item, every file and section a real worker actually read,
tagged `read_type: gate | reference | verify`, where `gate` means the phase
cannot proceed until it is satisfied. That is a recorded answer to "what did this
work require", so it serves as ground truth.

**Trace replay, A/B, pre-registered.** Each agent received only a trace's
`trigger` field and produced the ordered gate list it would satisfy. Scored
against that trace's recorded `gate` steps. `sdd/traces/` was withheld from every
agent as the answer key.

- **Arm A**: may read `sdd/RULEBOOK.md`; may not open the eight compiled `sdd/`
  process docs or `CONTRIBUTING.md`. Wanting one is recorded as an *escape*.
- **Arm B**: may read the source docs; may not open `sdd/RULEBOOK.md`.

Both arms could read specs, code, tests and `BACKLOG.md`. Four items, two arms,
two runs each. Hypotheses and the decision rule were written to
[`rulebook-poc/PREREG.md`](rulebook-poc/PREREG.md) before any agent launched.

Items: BK-167a (9 of 9 gates in rulebook scope), BK-171 (9 of 10), BK-167 (8 of
8), BUG-199 (6 of 26, the ceiling case).

## 3. Static coverage, measured before the experiment

Over 259 traces carrying 3,621 steps, of which 1,461 are gates:

| Measure | Value |
|---|---|
| Gate steps landing in a compiled doc | 288 of 1,461 (20%) |
| …of those, citing a section the rulebook carries | 202 (70%) |
| …citing a section the rulebook drops | 77 (27%) |
| …whole-doc reads | 9 (3%) |
| **Gate reads the rulebook can address at all** | **202 of 1,461 (14%)** |

The single most-read gate file in the corpus is `sdd/BACKLOG.md` at 164 gates,
more than any compiled doc, and it is out of scope by construction.

Every one of the 77 dropped-section hits is `## Guides` content, clustering on
exactly the lookup tables the compilation convention chose to link rather than
copy:

| Hits | Dropped gate section |
|---|---|
| 22 | `sdd/TESTING.md :: Test Subpackage Placement` |
| 21 | `sdd/000-process.md :: Test traceability` |
| 7 | `sdd/AUTHORING.md :: Directory defaults` |
| 6 | `CONTRIBUTING.md :: Adding a New Backend` |
| 5 | `sdd/AUTHORING.md :: Where does my new file go?` |
| 5 | `sdd/000-process.md :: Document types` |
| 5 | `sdd/000-process.md :: Spec format` |

## 4. Replay results

| Arm | Recall (all gates) | Recall (in-scope) | Escapes per run | Gates cited |
|---|---|---|---|---|
| **A** (rulebook only) | 49% | 51% | 6.6 | 18.6 |
| **B** (source docs) | 70% | 85% | — | 19.2 |

Per item:

| Item | A recall | B recall | A escapes |
|---|---|---|---|
| BK-167 | 69% | 100% | 7.5 |
| BK-167a | 33% | 72% | 9.5 |
| BK-171 | 50% | 65% | 5.5 |
| BUG-199 | 44% | 44% | 4.0 |

Arm A lost on every item. Both arms cited a comparable number of gates, so arm A
was not simply terser; it cited a *different and worse* set.

## 5. Hypotheses

| ID | Hypothesis | Outcome |
|---|---|---|
| H1 | Arm A recall >= Arm B | **False.** 49% against 70%; A lost on all four items. |
| H2 | A's escapes concentrate in condensed sections and table-bodied rules | **Confirmed.** |
| H3 | The 20% in-scope ceiling is hard (predicted false) | **False, as predicted.** Arm A routed itself to specs, ADRs, `BACKLOG.md`, `CLAUDE-REFERENCE.md` and source code without difficulty. |
| H4 | Recall depressed by gates citing `## Guides` sections | **Confirmed.** |

The pre-registered decision rule for "H1 false plus high escape rate" was
*abandon*. H3's failure would normally redeem the artefact as an index rather
than a substitute, but arm B routed *better* using the pointers `CLAUDE.md`
already carries, so the rulebook does not win as an index either.

## 6. The unpredicted finding: the disclaimer paradox

Arm A agents repeatedly declined to rely on the rulebook and cited its own
non-authoritative header as the reason. Two verbatim examples from
[`rulebook-poc/results/`](rulebook-poc/README.md):

> RULEBOOK is explicitly non-authoritative and hand-compiled, so the exact
> normative wording cannot be edited from the digest.

> substituted `sdd/RULEBOOK.md` § 0, which self-declares non-authoritative and
> hand-compiled.

This is structural, not a wording defect. Label the digest honestly and a careful
reader correctly refuses to act on it wherever the exact rule text is
load-bearing. Remove the label and it becomes the stale competing authority that
[`CLAUDE.md` principle 4](../../CLAUDE.md#principles) forbids. The safety
property and the substitution use case are in direct opposition.

A consequence worth stating plainly: H1's failure is partly self-inflicted. The
digest was *disbelieved* at least as often as it was misread, so 49% measures
trust as much as content.

## 7. Verdict

Not recommended for adoption as built. A rule digest that must be labelled
non-authoritative cannot substitute for the sources, and the routing job it might
otherwise do is already done better by `CLAUDE.md`.

Two paths remain open, neither pursued here:

- **Generate it.** `DIGEST.md` escapes the paradox because a generator plus a
  drift gate make "do not edit by hand" enforceable rather than aspirational. A
  generated rulebook would inherit that warrant. The condensed sections (§ 1) are
  the part a generator cannot produce mechanically, so that problem must be
  solved first, most likely by reshaping `DESIGN.md` and `DOCUMENTATION.md` into
  flat numbered rules.
- **Fix the source framework instead.** § 8 finding 1 suggests the compilation
  difficulty is a symptom of a defect in the format contract, not of the digest
  idea.

## 8. Findings that outlive the PoC

**1. `## Guides` sections are load-bearing, contradicting the format contract.**
[`CONTRIBUTING.md` § Authoritative Document Format](../../CONTRIBUTING.md#authoritative-document-format)
defines Guides as "heuristics, examples, lookup tables. Useful but not binding."
The trace record shows Guides sections cited as `gate` 77 times.
`sdd/000-process.md :: Test traceability`, which carries the
`@pytest.mark.spec("ID")` obligation, is a gate 21 times while being formally
non-binding. The contract misclassifies part of its own binding material, and
every consumer inherits the error. This PoC dropped Guides *because the contract
said they were not binding*, so the rulebook's largest gap is a faithful
reproduction of a defect in the source framework.

**2. A trace cites a file that does not hold the content.**
`sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml` records four gates at
`sdd/TESTING.md :: Cassette-First Bug Investigation` and `:: Cassette Refresh`.
That content is in [`sdd/TESTING-RUNBOOK.md`](../TESTING-RUNBOOK.md) (§ Cassette
record & refresh, § Cassette-first bug investigation). Both arms correctly cited
the runbook and were scored as wrong until the ground truth was corrected; the
correction is implemented and commented in
[`scripts/score.py`](rulebook-poc/scripts/score.py). Traces drift, which matters
because they are the intended input to any future aggregator.

**3. The quick-reference table has no row for two framework docs.**
`sdd/CLAUDE-REFERENCE.md` § "Where do I…?" carries rows for DESIGN, TESTING,
CONTENT-RULES and DRIFT-RULES but none for `AUTHORING.md` or `DOCUMENTATION.md`.
Surfaced incidentally by an arm-A agent.

## 9. Limits

Read the numbers against these before reusing them.

- **`CLAUDE.md` is a confound.** It is injected into every subagent as project
  instructions and cannot be withheld, so both arms had it free. The experiment
  measures what the rulebook adds *on top of* `CLAUDE.md`, and rulebook § 0 is
  not under test.
- **Escapes measure declared intent, not failure.** Arm A was forbidden from
  opening sources; a real agent would simply open them. A high escape rate means
  "the digest did not settle the question", not "the agent was blocked".
- **Small N.** Two runs per cell, not the three originally proposed; the
  deviation is recorded in the pre-registration. Single model, single session.
- **Ground truth is imperfect.** Traces are human-authored and demonstrably
  drift, per finding 2. One error was found and corrected; others may remain.
- **Scoring is fuzzy.** Sections are matched on a normalised head token, and
  non-Markdown files match at file level only.
- **Item selection favours the artefact.** Three of four items are
  docs-framework work, the rulebook's strongest zone, chosen deliberately on the
  reasoning that failure there is decisive. It lost there anyway.

## 10. Reproducing

From the repo root:

    python sdd/research/rulebook-poc/scripts/trace_stats.py       # § 3 corpus stats
    python sdd/research/rulebook-poc/scripts/section_coverage.py  # § 3 section coverage
    python sdd/research/rulebook-poc/scripts/ground_truth.py      # the answer key
    python sdd/research/rulebook-poc/scripts/score.py             # § 4 replay scores

Agent prompts are reproduced in
[`rulebook-poc/README.md`](rulebook-poc/README.md); the runs themselves are not
re-executable, and the 16 recorded outputs are the primary evidence.
