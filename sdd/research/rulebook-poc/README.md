# Rulebook PoC — evidence

<!-- doc: repo-only -->

Raw evidence for
[`research-rulebook-poc.md`](../research-rulebook-poc.md). Kept as recorded: the
run outputs are transcribed verbatim from the agents, not cleaned up. Read the
research doc first; this folder exists so its numbers can be checked.

## Contents

| Path | What it is |
|---|---|
| [`RULEBOOK.md`](RULEBOOK.md) | The artefact under test. Lived at `sdd/RULEBOOK.md` during the experiment; moved here afterwards because it was not adopted, header revised per research doc § 7, and re-synced once to master `83e22a3` after BK-329 amended five of the rules it compiles. **Frozen there** — it is evidence, not a maintained document |
| [`PREREG.md`](PREREG.md) | Hypotheses, method, and decision rule, written **before** any agent launched |
| `results/<arm>_<item>_<run>.txt` | 16 recorded gate lists, one per run |
| `scripts/_common.py` | Shared `COMPILED` set and section normalisation, imported by all three analysis scripts so the vocabulary exists once |
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

## Defect found in the ground truth, and fixed

The BUG-199 trace cited `sdd/TESTING.md` for four cassette gates and one
`surprising_ripples` entry. That content is in `sdd/TESTING-RUNBOOK.md`
(§ Cassette record & refresh at line 160, § Cassette-first bug investigation at
line 277), and `git log -S Cassette -- sdd/TESTING.md` shows `TESTING.md` never
held it, so the trace was wrong when authored rather than aged into wrongness.

**Corrected in the trace itself**, so the answer key is right at source and
`score.py` carries no correction layer. An interim fix inside `score.py` remapped
the file but not the section name, which left `Cassette Refresh` unable to match
the runbook's actual `Cassette record & refresh` heading — so
`results/B_BUG-199_run2.txt`, which cites that exact heading, stayed scored as a
miss. Fixing the data rather than the scorer removed both the residual and the
workaround. Effect on the published numbers: arm B's BUG-199 `recall_all` rises
from 44% to 46% and its in-scope recall reads 100%; arm A is unaffected.
