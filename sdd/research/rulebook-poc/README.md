# Rulebook PoC — evidence

<!-- doc: repo-only -->

Raw evidence for
[`research-rulebook-poc.md`](../research-rulebook-poc.md). Kept as recorded: the
run outputs are transcribed verbatim from the agents, not cleaned up. Read the
research doc first; this folder exists so its numbers can be checked.

## Contents

| Path | What it is |
|---|---|
| [`RULEBOOK.md`](RULEBOOK.md) | The artefact under test. Lived at `sdd/RULEBOOK.md` during the experiment; moved here afterwards because it was not adopted, and its header was revised per research doc § 7 |
| [`PREREG.md`](PREREG.md) | Hypotheses, method, and decision rule, written **before** any agent launched |
| `results/<arm>_<item>_<run>.txt` | 16 recorded gate lists, one per run |
| `scripts/trace_stats.py` | Corpus aggregate over `sdd/traces/*.yml` (research doc § 3) |
| `scripts/section_coverage.py` | Section-level carried-vs-dropped split (§ 3) |
| `scripts/ground_truth.py` | Dumps the four items' triggers and recorded gates |
| `scripts/score.py` | Scores `results/` against the traces (§ 4) |

Run every script from the repo root. They need `pyyaml`, already a dev
dependency.

## Result file format

One `<file> :: <section>` per line, gates first, then a `###ESCAPES###` marker,
then the escapes (or `NONE`). An **escape** is a doc arm A wanted but was
forbidden to open. Filenames encode arm, item, and run: `A_BK-167a_run1.txt`.

Arm A could read `sdd/RULEBOOK.md` but not the eight compiled `sdd/` process docs
or `CONTRIBUTING.md`. Arm B could read those but not the rulebook. Both were
denied `sdd/traces/`, the answer key.

## Agent prompt

Every run used this prompt with the arm-specific constraint block substituted.
`<TRIGGER>` is the item trace's `trigger` field verbatim, and was the only
description of the task the agent received.

    You are planning a work item in the remote-store repo. Output a gate list
    only. Do NOT implement anything.

    TASK TRIGGER: "<TRIGGER>"

    CONSTRAINTS (strict):
    <ARM CONSTRAINTS>
    - You MAY NOT open anything under sdd/traces/ (this is an answer key).

    Produce EXACTLY this format, nothing else:

    ## GATES
    (ordered list, one per line, format: `<repo-relative-file> :: <section>`)

    ## ESCAPES
    (one per line: `<forbidden file> :: <section you wanted> :: <why>`;
     write NONE if none)

    ## PLAN
    (max 6 bullets)

Arm A constraints:

    - You MAY read sdd/RULEBOOK.md.
    - You MAY NOT open any of: sdd/000-process.md, sdd/DESIGN.md,
      sdd/TESTING.md, sdd/AUTHORING.md, sdd/DOCUMENTATION.md,
      sdd/CONTENT-RULES.md, sdd/DRIFT-RULES.md, sdd/CI-OPERATIONS.md,
      CONTRIBUTING.md.
    - You MAY read specs, source code, tests, sdd/BACKLOG.md,
      sdd/CLAUDE-REFERENCE.md.
    - If you find you need a forbidden doc, DO NOT open it. Record it as an
      escape.

Arm B constraints:

    - You MAY NOT open sdd/RULEBOOK.md.
    - You MAY read anything else: the sdd/ process docs, CONTRIBUTING.md,
      specs, source code, tests, sdd/BACKLOG.md, sdd/CLAUDE-REFERENCE.md.

The prompt paths above name `sdd/RULEBOOK.md` because that is where the file was
when the runs happened. They are transcripts, not instructions, and are otherwise
left as recorded. One substitution: the two arm constraint lines named the
rulebook by absolute path in the original prompts; that path is specific to the
machine the runs executed on and is repo-relative here.

## Transcription note

`results/*.txt` carry the `file :: section` pairs only. The agents also returned
a `## PLAN` block and, for escapes, a free-text reason. Plans were not scored.
Escape reasons are not in the result files; the two quoted in research doc § 6
are transcribed there verbatim from the arm-A BK-171 run 1 and BUG-199 run 2
outputs.

## Known defect in the ground truth

The BUG-199 trace cites `sdd/TESTING.md` for four cassette gates whose content
lives in `sdd/TESTING-RUNBOOK.md`. `scripts/score.py` corrects this in
`correct()`, with the reason in its docstring. Without the correction both arms
are marked wrong for citing the file that actually holds the content, and arm B's
BUG-199 in-scope recall reads 33% instead of 100%.
