# ADR-NNNN: <Title>

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Proposed |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

`Status` is one of `Proposed`, `Accepted`, `Superseded`. Fill the link rows with
bare ADR ids (e.g. `ADR-0007`), comma-separated, or `—` when none:

- `Supersedes` / `Superseded by` — whole-ADR supersession. When this ADR
  supersedes another, set that ADR's `Status` to `Superseded` and its
  `Superseded by` to this one; `gen-adr-digest` flags one-sided edges.
- `Amends` — a clause-level change that leaves the target ADR otherwise in
  force. Name the specific clause in prose below the table (see ADR-0015,
  ADR-0029).

`scripts/gen_adr_digest.py` parses this table into `sdd/adrs/DIGEST.md`.

## Context

What problem or tension led to this decision? Include relevant constraints —
performance, API compatibility, dependency rules, team/process considerations.
Name the forces in play, not the solution.

## Decision

> **Placement principle (ID-232 research).** Minimize *mismatched* detail, not
> detail. Brevity is a byproduct of correct placement, never the target — never
> delete a load-bearing reason to hit a length budget. A fact stays in
> `## Decision` only if it passes the three-condition gate: its change-rate fits
> the ADR's heavy revision cost, its correctness matters at this layer, **and**
> it justifies or constrains the decision. Read each Decision alone, no links
> followed: a competent engineer must be able to see *why* the choice was made
> and *when* to reverse it.

**Structure each decision as its own scannable unit** — a bulleted item or a
short bolded sub-heading, not a prose blob — so a reader can see where one
decision ends and the next begins. Lead with the decision; do not restate the
context.

The **entire `## Decision` section** (up to the next `##`) is lifted verbatim
into `sdd/adrs/DIGEST.md`, so keep it to the decision and its essential detail;
anything you would not want in the digest belongs under `## Consequences` or a
later `##` section. Internal `###` sub-headings are demoted automatically to
nest under the digest entry.

Place by the gate, not by size: the choice, the reasons that would reverse it,
and constraint-bearing facts (e.g. a CVE floor, a hard compatibility
requirement) **stay** even when they name a version. Bookkeeping spec detail —
routine pins, contracts, wire mechanics — moves to its authoritative home (the
spec, `pyproject.toml`, or the code); consequence-rate content (realized
tradeoffs, escalation triggers) goes under `## Consequences`. `gen-adr-digest`
emits an advisory size/spec-detail check to help keep this honest — it is a
smell detector for human judgment, not the target.

## Consequences

What becomes true after this decision?

- Positive: what improves or becomes possible.
- Negative: what is harder, ruled out, or incurs ongoing cost.
- Neutral: changes in practice that are neither good nor bad by themselves.
