# ADR-0036: Select Reviewers by Subject and Method, Not by Domain Persona

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0020, ADR-0035 |

Amends the review half of
[ADR-0020](0020-orchestrate-iterative-convergence.md)'s *Carry forward
ADR-0019's delegation structure* clause — per-domain boundaries continue to
govern **authoring** in `/orchestrate` and stop governing **review** there — and
extends [ADR-0035](0035-vary-method-not-model.md)'s lens-and-method selection
from `/ship` to `/orchestrate`, adding one lens. ADR-0033 and ADR-0034 are
untouched.

## Context

BK-338 asked whether `/rvw-pr` and `/orchestrate` should select the experts a
change requires rather than run a fixed numbered list. It was filed on one
delivery (PR #944) and a first attempt was reverted for deciding on that
evidence. Four deliveries have since run under the `/ship` convergence loop
(PRs #946, #949, #952 and #954), each leaving a trace.

**Two measurements decide it, over two different samples and by two different
methods.** Both are measured rather than argued, and the samples are not the same
set — conflating them is what a reader trying to re-derive either would trip on:

1. **Persona lenses reach a minority of findings.** Sample: the **two richest**
   of those four traces, PR #952 and PR #954 — richest, not the only ones with
   round-by-round detail, which many traces outside the loop also carry. Method:
   classifying every review
   finding recorded there by whether a persona lens, scoped
   as its `.claude/agents/` file scopes it, would plausibly have caught it —
   a per-finding judgement, not a count.
   PR #952, 19 findings — 7 reachable, 7 inside the persona's domain but
   reachable only by execution the persona is not briefed to do, 5 reachable by
   no single lens. PR #954, 12 findings — 3 reachable, 9 not. Across both,
   roughly half of all verdicts were reached by executing.

2. **The five domains do not cover the repository.** The `DOMAIN:` lines are
   `src/remote_store/`, `src/remote_store/ext/`, `tests/`, `docs-src/` +
   `examples/` + `docs/`, and `sdd/`; everything else is uncovered, `scripts/`,
   `.claude/`, `pyproject.toml`, `.github/`, `infra/`, `benchmarks/` and the root
   files among it. Sample: **five** deliveries — PRs #944, #945, #949, #952 and
   #954. Not the four above: #944 and #945 predate the loop, and #946 is the
   delivery that created it rather than one run under it, so file-level coverage
   was measured over the wider set that has changed-file data. Method:
   `git show --name-only` per merge SHA,
   bucketing each path by longest-matching `DOMAIN:` prefix — mechanical, and
   re-derivable from the recipe in
   [`sdd/traces/bk-338-review-roster.yml`](../traces/bk-338-review-roster.yml).
   Result: 20 of 135 changed files (15%) fall outside every
   domain; for the two process deliveries it is 45% and 31%. Nine of PR #954's
   twelve findings landed there. A process delivery is invisible to a persona
   roster by construction.

The two between-lenses cases sharpen the first measurement, because in both the
owning persona existed. `GraphBackend` is the store-backend expert's, and went
unnamed for six rounds because the diff never touched it. The `missing_ok`
docstring claim sits between documentation, which owns docstrings, and
store-backend, which owns whether the claim is true across backends; neither
lens asks whether a docstring's claim holds elsewhere.

`/ship` already selects by lens and method, and ADR-0035 recorded that BK-338's
roster question was untouched at the time — this record is what closes it, so
that Consequences bullet now points here. The live instance is `/orchestrate`
alone, whose Steps 3 and 6 spawn all five experts to review.

## Decision

- **A reviewer is selected by the subject set it is aimed at and the method it
  uses, never by which directory it owns.** Domain personas remain a way to
  *staff* a scoped lens; they stop being the unit of selection. The measured
  reachability of a persona lens is a minority of findings, and identity is the
  axis [ADR-0035](0035-vary-method-not-model.md) already found unpaying.
  *Reverse if* a delivery's findings cluster by domain such that a persona
  roster would have reached them and a subject-and-method selection did not.

- **`/orchestrate`'s review steps select by lens and method; its authoring
  fan-out stays persona-based.** Authoring genuinely is domain-partitioned — a
  backend change is written in `src/remote_store/`, and ADR-0020's delegation
  structure holds for that half. Review is not, which is what the measurements
  show. This keeps one review model across both skills instead of two.
  *Reverse if* `/orchestrate`'s reviews become materially more expensive without
  finding more than the five-persona fan-out did.

- **The repository's own tooling and process contract is a lens, not a
  domain.** Its extent is *everything no `DOMAIN:` line contains* — derived per
  path, never enumerated, because an enumeration read as exhaustive is how an
  unlisted file gets handed to a persona that excludes it. A sixth persona was
  rejected: the surface needs looking at, not owning, and a persona whose domain
  is "everything left over" grows the roster on the axis with no yield.
  *Reverse if* the lens is reliably selected for the same deliveries a domain
  assignment would have covered, at which point the assignment is cheaper.

- **The main loop fixes and owns the sweep; delegation to a domain expert is by
  depth, not by default.** [ADR-0034](0034-ship-panel-rounds-and-unprimed-exit.md)
  puts the sibling sweep on the fixer, and the sweeps that paid across both
  traces were cross-file — a claim in five homes spanning `sdd/`, `CHANGELOG.md`
  and a guide; a fifth restatement in a different skill. A domain-scoped fixer
  cannot perform those. Delegate when the fix needs depth inside one file tree.
  *Reverse if* delegated fixes stop producing the divergences that motivated the
  sweep obligation.

The step sequences, the lens menu, and the brief requirements are operational
contract and live in `.claude/skills/orchestrate/SKILL.md` and
`.claude/skills/ship/SKILL.md`.

## Consequences

- **Positive:** process and tooling deliveries stop being invisible to review
  selection. The surface carrying 75% of PR #954's findings is now nameable in a
  brief.
- **Positive:** one review model across `/ship` and `/orchestrate`. Before this,
  the same repository selected reviewers two incompatible ways depending on
  which skill was invoked, and only one of them had a record behind it.
- **Positive:** the fixer role stops contradicting the sweep obligation it is
  supposed to discharge.
- **Negative:** selection becomes a judgement where it was a list. "All 5
  experts activate" needs no thought and cannot be under-selected; a lens choice
  can be, and an under-selected review looks exactly like a clean one.
- **Negative:** the persona files keep DOMAIN lines that no longer bound
  anything at review time, only at authoring time. The asymmetry is real and is
  stated in each skill rather than resolved.
- **Negative:** the finding-level classification behind measurement 1 is a
  per-finding judgement, not a mechanical count, and it was made by the same
  agent proposing the decision. The file-level measurement is mechanical and
  corroborates it, but it is the weaker of the two.
- **Neutral:** `/orchestrate` moves closer to `/ship` in review shape while
  keeping the boundary ADR-0020 owns — a capped consolidation, not an
  open-ended convergence loop.
