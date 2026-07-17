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

State the decision in one clear sentence or short paragraph, wrapped in an
`<!-- adr:decision -->` … `<!-- /adr:decision -->` fence so the digest can lift
it verbatim:

<!-- adr:decision -->
The one-sentence decision goes here.
<!-- /adr:decision -->

Then explain the chosen design below the fence. Use diagrams, code sketches, or
bullet lists where they aid precision. Avoid restating the context.

## Consequences

What becomes true after this decision?

- Positive: what improves or becomes possible.
- Negative: what is harder, ruled out, or incurs ongoing cost.
- Neutral: changes in practice that are neither good nor bad by themselves.
