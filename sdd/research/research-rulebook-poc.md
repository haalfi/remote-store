# Research: Compiling the repo's rules into a single rulebook

**Date:** 2026-07-30
**Status:** Point-in-time PoC record. **Negative result**: the artefact under test
failed its own pre-registered success criterion and is not recommended for
adoption in the form built. No backlog items were created; § 8 lists three
findings that a maintainer may want to action separately.
**Scope:** Whether the repo's binding rules can be compiled into one document
that an agent reads *instead of* the source process docs. Covers the artefact
built, a static coverage analysis over the trace corpus, and a 16-run A/B replay
experiment. The artefact **as tested** was `sdd/RULEBOOK.md`, 294 lines; it
**ships** at [`rulebook-poc/RULEBOOK.md`](rulebook-poc/RULEBOOK.md), relocated
because it was not adopted and longer than 294 lines because its header was twice
revised, in response to § 6 and then to review. § 1 and § 6 describe the tested
version, not the shipped one; the header they turn on is reproduced verbatim in
[`rulebook-poc/README.md` § The header as tested](rulebook-poc/README.md), since
the branch commit that carried it will not survive a squash merge. Does not cover generator tooling, drift gating, or any change to the
source docs; none were built.
**Related:** [`CLAUDE.md` § Principles](../../CLAUDE.md#principles),
[`CONTRIBUTING.md` § Authoritative Document Format](../../CONTRIBUTING.md#authoritative-document-format),
[`sdd/adrs/DIGEST.md`](../adrs/DIGEST.md) (the generated analogue this imitated),
[`sdd/traces/_schema.yml`](../traces/_schema.yml) (the ground truth),
[`research-inconsistency-detection-multi-artifact.md`](research-inconsistency-detection-multi-artifact.md).
**Evidence:** [`rulebook-poc/`](rulebook-poc/README.md) — pre-registration, 16 raw
run outputs, and the four analysis scripts.

**Context:** Ten documents state binding rules for this repo: `CLAUDE.md`, the
eight `sdd/` process docs that follow the Intent & Scope / Rules / Guides format,
and `CONTRIBUTING.md`, whose Authoritative Document Format section defines that
format and is what § 8 finding 1 turns on. `sdd/adrs/DIGEST.md` already proves that compiling a scattered artefact
class into one generated document is useful for ADRs. This PoC asked whether the
same move works for rules, hand-built first to learn the shape before writing a
generator.

## 1. What was built

294 lines compiled from roughly 1,680 lines of source.
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
  on conflict. (Revised after this document was written; see § 6 and § 7.)

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

Computed over the trace corpus at commit `297c79d`: **260 traces** carrying 3,647
steps, of which 1,468 are gates. The corpus grows, so these are a snapshot;
`trace_stats.py` and `section_coverage.py` both print the trace count they
scanned, so a reader whose numbers differ can tell newer traces from a bug.

| Measure | Value |
|---|---|
| Gate steps landing in a compiled doc | 288 of 1,468 (20%) |
| …of those, citing a section the rulebook carries | 202 (70%) |
| …citing a section the rulebook drops | 77 (27%) |
| …whole-doc reads | 9 (3%) |
| **Gate reads the rulebook can address at all** | **202 of 1,468 (14%)** |

The single most-read gate file in the corpus is `sdd/BACKLOG.md` at 165 gates,
more than any compiled doc, and it is out of scope by construction.

The 77 split **47 `## Guides` hits and 30 other non-Rules hits**. Both cluster on
the lookup tables the compilation convention chose to link rather than copy, but
the distinction matters because § 8 finding 1 is about Guides specifically:
`CONTRIBUTING.md` has no Guides block at all, and
`TESTING.md :: Test Subpackage Placement` sits between Intent & Scope and Rules.
The rulebook drops both; neither is Guides content.

| Hits | Bucket | Dropped gate section |
|---|---|---|
| 22 | other | `sdd/TESTING.md :: Test Subpackage Placement` |
| 21 | Guides | `sdd/000-process.md :: Test traceability` |
| 7 | Guides | `sdd/AUTHORING.md :: Directory defaults` |
| 6 | other | `CONTRIBUTING.md :: Adding a New Backend` |
| 5 | Guides | `sdd/AUTHORING.md :: Where does my new file go?` |
| 5 | Guides | `sdd/000-process.md :: Document types` |
| 5 | Guides | `sdd/000-process.md :: Spec format` |

## 4. Replay results

| Arm | Recall (all gates) | Strict recall | Recall (in-scope) | Escapes per run | Gates cited |
|---|---|---|---|---|---|
| **A** (rulebook only) | 49% | **29%** | 51% | 6.6 | 18.6 |
| **B** (source docs) | 71% | 71% | 85% | — | 19.2 |

Per item:

| Item | A recall | A strict | B recall | A escapes |
|---|---|---|---|---|
| BK-167 | 69% | 19% | 100% | 7.5 |
| BK-167a | 33% | 33% | 72% | 9.5 |
| BK-171 | 50% | 20% | 65% | 5.5 |
| BUG-199 | 44% | 44% | 46% | 4.0 |

Arm A lost on every item. Both arms cited a comparable number of gates, so arm A
was not simply terser; it cited a *different and worse* set.

**Strict recall** does not credit a run for a gate it also listed as an escape.
Several arm-A runs name a gate and, in the same output, record that they could
not open the doc that satisfies it — `A_BK-167_run2` does this four times.
Crediting those inflates arm A one-sidedly, because every arm-B escape block is
`NONE`. Under the strict count the gap widens from 49-vs-71 to **29-vs-71**. The
plain figure is kept alongside because it is the one the pre-registration
implied; the strict figure is the more honest read of the same runs.

## 5. Hypotheses

| ID | Hypothesis | Outcome |
|---|---|---|
| H1 | Arm A recall >= Arm B | **False.** 49% against 71%, or 29% against 71% not crediting escaped gates; A lost on all four items either way. |
| H2 | A's escapes concentrate in condensed sections and table-bodied rules | **Confirmed.** |
| H3 | The 20% in-scope ceiling is hard (predicted false) | **False, as predicted.** Arm A routed itself to specs, ADRs, `BACKLOG.md`, `CLAUDE-REFERENCE.md` and source code without difficulty. |
| H4 | Recall depressed by gates citing `## Guides` sections | **Confirmed.** |

The pre-registered decision rule for "H1 false plus high escape rate" was
*abandon*. H3's failure would normally redeem the artefact as an index rather
than a substitute, but arm B routed *better* using the pointers `CLAUDE.md`
already carries, so the rulebook does not win as an index either.

## 6. The unpredicted finding: the disclaimer paradox

Arm A agents declined to rely on the rulebook and, in **5 of the 8 arm-A runs**,
cited its own non-authoritative header as the reason. Every escape and its stated
reason is transcribed in
[`rulebook-poc/results/escape-reasons.md`](rulebook-poc/results/escape-reasons.md),
so the count is checkable rather than asserted. Two verbatim examples:

> RULEBOOK is explicitly non-authoritative and hand-compiled, so the exact
> normative wording cannot be edited from the digest.

> substituted `sdd/RULEBOOK.md` § 0, which self-declares non-authoritative and
> hand-compiled.

The other 3 runs escape on **condensation** rather than authority — "condenses
this to a link", "explicitly defers the table", "only summarises and links out".
Both are refusals to rely on the digest, but only the first group is evidence for
the paradox below; the second is evidence for H2.

This is structural, not a wording defect. Label the digest honestly and a careful
reader correctly refuses to act on it wherever the exact rule text is
load-bearing. Remove the label and it becomes the stale competing authority that
[`CLAUDE.md` principle 4](../../CLAUDE.md#principles) forbids. The safety
property and the substitution use case are in direct opposition.

H1's failure is therefore partly self-inflicted: some of arm A's misses are the
digest being disbelieved rather than misread. How much is **not measured** —
nothing here separates a gate missed through distrust from one missed because the
rule was condensed away, and no design in this experiment could, since a single
escape often cites both.

## 7. Verdict

Not recommended for adoption as built. A rule digest that must be labelled
non-authoritative cannot substitute for the sources, and the routing job it might
otherwise do is already done better by `CLAUDE.md`.

One correction was applied after this document was written, in response to § 6:
the header no longer calls the document non-authoritative. It now separates the
*rules*, which bind exactly as they do in their source docs, from the
*transcription*, which is what may drift. This removes the stated grounds on
which arm A refused the digest, but **the effect is unmeasured** — no replay was
re-run against the revised header, so every number in § 4 belongs to commit
`b3a71a3` and none of them should be read as evidence for or against the
revision.

**The predicted drift arrived before merge.** BK-329 (#941) landed on master
while this PR was open and amended five of the rules the artefact compiles:
`CLAUDE.md` principle 5 and `000-process.md` Rule 3 both gained a qualifier,
`000-process.md` gained an entirely new Rule 7, and `DRIFT-RULES.md` rules 4 and
6 were rewritten. The digest was stale on all five within roughly a day of being
written, and the artefact's own Sources table still counted six rules where the
source had seven. The same PR added a ripple-check row, *Authority direction
amended*, whose purpose is to grep out copies of the authority direction — which
is exactly what this artefact is, and it would have been found by that row rather
than by anyone reading it.

This is the strongest single piece of evidence in the PoC and it was not
solicited: the failure mode was predicted in § 1's conventions, and it
materialised unprompted, on the shortest possible timescale, on the highest-value
rules in the repo. It is also why the shipped artefact is frozen at `83e22a3`
rather than maintained. Re-synced there once, for merge honesty; not a standing
obligation.

Two further paths remain open, neither pursued here:

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
The trace record shows Guides sections cited as `gate` **47 times** (of 77
dropped-section gates in total; the other 30 are non-Rules content that is not
Guides, per § 3).
`sdd/000-process.md :: Test traceability`, which carries the
`@pytest.mark.spec("ID")` obligation, is a gate 21 times while being formally
non-binding. The contract misclassifies part of its own binding material, and
every consumer inherits the error. This PoC dropped Guides *because the contract
said they were not binding*, so the rulebook's largest gap is a faithful
reproduction of a defect in the source framework.

**2. A trace cited a file that never held the content — now fixed.**
`sdd/traces/bug-199-azure-folder-info-hns-dir-count.yml` recorded four gates and
one `surprising_ripples` entry at `sdd/TESTING.md`, citing
`:: Cassette-First Bug Investigation` and `:: Cassette Refresh`. That content is
in [`sdd/TESTING-RUNBOOK.md`](../TESTING-RUNBOOK.md) (§ Cassette record & refresh,
§ Cassette-first bug investigation).

Not drift: `git log -S Cassette -- sdd/TESTING.md` returns nothing across all
history, so `TESTING.md` never held it. The trace was **wrong when authored**,
which is the worse failure of the two, because nothing about the passage of time
signals it and the file validates against its schema either way. Both experiment
arms cited the runbook correctly and were scored as misses until the key was
corrected.

Disposition: corrected in the trace itself in this PR, rather than worked around
in the scorer. The earlier fix remapped the file but not the section name, so
`Cassette Refresh` still failed to match the runbook's actual
`Cassette record & refresh` heading and one correct citation stayed scored as a
miss. Fixing the data removed the workaround entirely — see
[`scripts/score.py`](rulebook-poc/scripts/score.py), which no longer carries a
correction layer. This is the one finding of the three that was a factual error
in a data file this PR had already verified, so leaving it for triage would have
shipped a known-wrong answer key against principle 3.

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
- **Scoring is fuzzy, and every fuzz favours the run being scored.** Sections
  match on a normalised head token; non-Markdown files match at file level only,
  so one citation of a code file satisfies every gate recorded in it; and a
  `whole file` citation on either side is a wildcard satisfying every recorded
  gate section in that document. The normalisation is shared by all three scripts
  ([`scripts/_common.py`](rulebook-poc/scripts/_common.py)) rather than written
  per script, after review found the two copies had already diverged on whether
  `whole file` meant a whole-document read.
- **§ 3's dropped count is a lower bound.** A cited section matching no literal
  heading is counted as carried, and `key()` collapses numbered citations to
  `RULES`, which is carried unconditionally. 32 of the 288 in-scope gates take the
  unmatched-heading path. Both biases run toward the artefact, so the true
  dropped figure is above 77. `section_coverage.py` prints this bound with its
  output, per DRIFT-RULES rule 7.
- **A scanner bug hid the Guides split until review.** The heading walker was not
  fence-aware, and `000-process.md` carries a `## <PREFIX>-NNN: <Rule Title>`
  line inside a fenced template. Treating that as a real heading reset the
  section walker and misfiled every heading after it, which is why an earlier
  draft of § 3 reported the Guides share as 20 rather than 47.
- **`CLAUDE.md`'s carried/dropped split is hand-enumerated.** It has no `## Rules`
  block to derive the § 3 classification from, unlike the eight process docs, so
  its dropped set is a judgement call in `_common.py`. Review flagged that an
  earlier version asserted the whole file was carried, which would have biased
  § 3 toward the artefact. Correcting it moved nothing: no `CLAUDE.md` gate in the
  corpus cites a dropped section, so the 202/77/9 split is unchanged. The
  assumption was unwarranted; the number it produced happened to be right.
- **Item selection favours the artefact.** Three of four items are
  docs-framework work, the rulebook's strongest zone, chosen deliberately on the
  reasoning that failure there is decisive. It lost there anyway.

## 10. Reproducing

From the repo root:

    python sdd/research/rulebook-poc/scripts/trace_stats.py       # § 3 corpus stats
    python sdd/research/rulebook-poc/scripts/section_coverage.py  # § 3 section coverage
    python sdd/research/rulebook-poc/scripts/ground_truth.py      # the answer key
    python sdd/research/rulebook-poc/scripts/score.py             # § 4 replay scores

The scripts read the live `sdd/traces/` tree, so § 3 reproduces exactly only at
corpus commit `297c79d` (260 traces). `trace_stats.py` and `section_coverage.py`
print the trace count they scanned; if it differs from 260, the corpus has moved
and so will every § 3 number.

§ 4 is **not** insulated from this. `score.py` pins the four replayed traces by
*name*, not by content, and this PR is the counter-example: correcting the BUG-199
trace moved arm B's recall for that item from 44% to 46%. Editing any of the four
moves a § 4 number with nothing in the output to signal it.

Agent prompts are reproduced in
[`rulebook-poc/README.md`](rulebook-poc/README.md); the runs themselves are not
re-executable, and the 16 recorded outputs are the primary evidence.
