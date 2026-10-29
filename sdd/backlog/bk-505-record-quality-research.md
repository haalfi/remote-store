# BK-505 — An `/observe` record's freeze has no stopping rule: the record-quality report's checks are neither adopted nor rejected
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** RFC-0029 (BK-503, 2026-10-29): the faithfulness
research assumed a correct record, while OP-01's failure modes sat in the
record itself ([`research-spec-faithfulness.md`](../research/research-spec-faithfulness.md)
§ 3). The maintainer chose to start this research at once, with RFC-0028's
review and a table completeness check taken as given, rather than after
BK-504 has run (decision log
`sdd/decisions/7d282f9d-8eb6-48be-8d6c-9fc7641121cf.jsonl`). The report
landed on 2026-10-29 and is kept as
[`research-observe-record-quality.md`](../research/research-observe-record-quality.md).

## Research brief

Hand this section to the deep-research run, titled "Observation record
completeness and consistency". The research repository keeps it as given, its
headings one level up.

### 1. Question

A library's behaviour is decided in **prose observation records**, one per
operation, written in a design session between a maintainer and an agent.
A spec, formal models and an executable reference model are later built from
each record, so the record is the source of truth for everything downstream.

A record holds:
- an **Environment** list: the actions concurrent callers, out-of-band actors,
  the network and the runtime may take, fault actions included;
- **decisions**, each answering one question that a fixed checklist of 15
  axes raises. Each decision has a scenario, options with consequences, a
  recommendation with its source, an **Asked** line quoting the dialog that
  answered it, the decision, a consistency check and open items. Many
  decisions contain tables: an outcome partition by pre-state, a state ×
  operation table for a handed-out object, failure-category and phase tables,
  a non-promise register, and variation points by backend;
- an **Axis status** table and one **Open items** section.

**How can such a record be checked, as early as possible and mostly by
agents, for being:**

1. **Complete**: every question the axes raise is decided or explicitly open;
   every case split covers its domain; the Environment names every action
   that can affect the operation; and questions no axis raises are found.
2. **Internally consistent**: no two decisions contradict, including:
   - a table in one decision against prose in another;
   - the option text a decision adopts by reference against a later decision;
   - claims of extent ("only", a list read as complete) against decisions
     that add a member;
   - a decision's reason against an outcome elsewhere.
3. **Faithful to its dialog**: the decision text asserts nothing that the
   dialog it cites did not ask and answer.

Also: **when is a record done?** How can one tell that the remaining defects
are few enough to start the spec, rather than stopping when one more review
round finds nothing?

### 2. Context (kept minimal on purpose)

The first record is public, with its review history. Read these as evidence
and test material, pinned at commit `eb08d990e` of `haalfi/remote-store`
(use raw.githubusercontent.com):
- `sdd/observe/records/OP-01.md`: the record, with open items O14 to O44
  found after the session closed;
- `sdd/observe/axes.md`: the axes, the per-decision form and the reopen form;
- `sdd/audits/audit-025-op-01-record-review.md`: one reader's audit and its
  classification of the misses;
- `sdd/rfcs/rfc-0028-observe-record-review.md`: the review step now in use,
  with a small measurement of what each check found and missed.

Failure classes observed so far (RFC-0028 § Motivation):
1. A consistency check written once by the decision's author, naming a subset
   of earlier decisions, and never re-run.
2. Decision text that no dialog asked.
3. Backend, SDK and runtime behaviour that the design session cannot see,
   because it is deliberately kept from implementation detail.
4. Questions no axis raises.

Two blind readers on the same record found different subsets of the known
defects, and neither found all of them (RFC-0028 § Evidence). A later review
round still found new open items. Out of scope: anything after the record
(the spec, models and tests), which earlier research covered.

### 3. Already settled: build on, do not re-survey

From the research "Spec faithfulness and enforcement" (`haalfi/research`,
branch `research/spec-faithfulness-and-enforcement`, not to be read unless
the maintainer allows it):
- **Table completeness and disjointness checking over declared value
  domains** (SCR, Heitmeyer et al. TOSEM 1996: 17 real coverage errors that
  two review teams missed). Treat it as given for the record's tables. Its
  open part here is how a semi-formal table in prose declares its domain.
- **Per-operation response existence** ("for every environment move some
  allowed response exists", Event-B FIS/DLF, AGREE viability) as a
  cross-table check.
- **Round-trip and dual formalization** catch divergent readings and miss
  shared ones; LLM judges both over-accept and over-reject.
- **Separating information flow is necessary, not sufficient**: separately
  written versions fail together on hard inputs (Knight; Eckhardt & Lee).

In place in the project, so build on it:
- a script that pairs each decision with its answered dialog;
- two unprimed readers per record, findings unioned;
- a primed review against backend behaviour;
- a whole-record re-check at the end of the design session.

Ask what these miss and what would replace or strengthen them. Do not
re-describe them.

### 4. Tracks

One notes file per track. T1 to T3 in depth; T4 and T5 shorter.

#### T1. Completeness of a decision record

- Requirements completeness checking beyond tables: RSML and Heimdahl &
  Leveson's completeness criteria, the Jaffe/Leveson completeness criteria
  for state-based requirements, and coverage of an environment or fault model
  (hazard analysis, FMEA- or STPA-style enumeration of environment actions
  and their exposure).
- **Finding questions no checklist raises**: elicitation techniques that
  surface unasked questions (scenario-based, goal obstacles in
  van Lamsweerde's KAOS, negative scenarios), and whether any has been
  measured.
- How a checklist (here, the axes) is itself validated for coverage.

#### T2. Internal consistency of semi-structured prose

- Inspection reading techniques: checklist-based, perspective-based (PBR),
  defect-based and scenario-based reading. Measured yield on requirements
  documents, and on documents mixing prose and tables.
- **Contradiction detection by LLMs** in requirements and specifications:
  NLI-based conflict detection, LLM requirement-conflict studies. Precision
  and recall, false-alarm cost, and whether pairwise checks miss conflicts
  that need three or more statements.
- **Extracting a record into a structured form** (decision tables, typed
  claims, a claim graph) so that consistency becomes mechanical. Does the
  extraction step itself introduce or hide errors? How is it validated?
- Specifically: claims of extent ("only", "every", a list given as complete)
  and adopted-by-reference option text. Any technique that tracks them.

#### T3. Fidelity of a decision to its elicitation dialog

- Verifying a recorded requirement against the interview, meeting or
  transcript it came from: requirements traceability to elicitation sources,
  and summarisation faithfulness and hallucination detection on dialogue.
- **Added-commitment detection**: a decision that asserts more than the
  answer did. Measured methods, including LLM-based ones, and their error
  rates.

#### T4. Stopping rules (shorter)

- **Capture-recapture and other estimators** of remaining defects from
  overlapping reviewer findings (Eick et al.; Briand, El Emam et al.; Petersson
  et al.'s reviews), including the conditions they need (reviewer
  heterogeneity, number of reviewers) and their measured accuracy.
- Whether two LLM readers' overlap can feed such an estimator, and which
  assumptions break.

#### T5. Reviewer diversity (minimal)

Only as far as T2 to T4 need it: diverse perspectives vs diverse models vs
more readers of the same kind, for finding inconsistencies in one document.

### 5. Disconfirming searches

Run each and report the result:
- (a) Evidence that structured reading techniques (checklist, PBR) do **not**
  beat ad hoc reading for finding requirements defects.
- (b) Evidence that LLM contradiction or conflict detectors on requirements
  produce more false alarms than useful findings.
- (c) Evidence that capture-recapture estimates are unreliable at small
  reviewer counts (two to four).
- (d) Any published process that checks decision records (ADRs, design
  rationale, elicitation records) for completeness and consistency before
  specification. If one exists, compare against it instead of synthesising.

### 6. Evidence rules

- Verdicts rest on full texts. Search extracts are leads only. Label a source
  whose full text could not be fetched as **[unreachable]**, and your own
  reasoning as *Inference*.
- Grades:
  - A: peer-reviewed or measured. A-pre: arXiv preprint. A-workshop: workshop
    paper.
  - B: documented industrial practice with data, or normative standards and
    official docs.
  - C: practitioner report without data.
  - D: opinion or marketing.
- For each method, state whether **agents** were measured doing that step,
  and with which result. Otherwise mark the method "human-only evidence".
- Prefer measured figures. Give n, the setting, and what "correct" meant.
- Flag tool authors evaluating their own tool.
- **Own trials on OP-01 are welcome but labelled "own trial"**, with the
  script committed. Example: run a technique on the record pinned above and
  compare its findings with open items O14 to O44, treating those as a known
  defect set. That set is incomplete: say so, and report findings outside it
  separately, unverified.

### 7. Deliverable

`reports/Observation record completeness and consistency.md`:

1. **Kernsatz**: at most three sentences.
2. **Per track (T1 to T4)**:
   - the options with their evidence and grade;
   - what each catches and misses;
   - cost;
   - agent applicability.
3. **A check map**: for each element of a record (Environment, decision,
   adopted option, each table kind, the non-promise register, variation
   points, open items, Asked lines), which completeness, consistency and
   fidelity check applies, mechanical or judged, and whether it can run
   during the design session or only after it.
4. **A stopping rule** for record review, with its assumptions and what
   would invalidate it.
5. **Open questions and verification debt.**
6. **Sources** with grades.

### 8. Delivery

- Branch `research/observation-record-quality` from origin/main.
- Title: `Observation record completeness and consistency`.
- Follow the repository's CLAUDE.md for layout and running.
