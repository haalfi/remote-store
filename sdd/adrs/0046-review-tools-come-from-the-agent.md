# ADR-0046: A Review Pass's Tools Come From Its Agent, Not From `allowed-tools`

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | ADR-0035 |

Amends one Consequences bullet of [ADR-0035](0035-vary-method-not-model.md):
the one crediting a solo `/rvw-pr` pass with "the skill's `allowed-tools`
withholding of `Edit` and `Write`". Its decision, method over model, and every
other consequence stand.

## Context

BK-431 moved `/ship`'s review passes onto a `reviewer` agent whose `tools:`
list has no editing tool. While writing it, the claim that `allowed-tools` had
been withholding tools rested only on the skills documentation, which says
`allowed-tools` "grants tools without prompts" and leaves open how that maps
onto a forked skill.

A probe settled it. A forked skill with `context: fork`, `allowed-tools: Read`
and no `agent:` line was asked to write `tmp/bk431-probe.txt`. It listed `Write`,
`Edit`, `Agent` and `Bash` among its tools, the write succeeded, and the file
was on disk with the requested content
([trace](../traces/bk-431-scoped-reviewer-input.yml)). So `allowed-tools`
pre-approves; it withholds nothing. Before BK-431, a solo `/rvw-pr` pass could
edit files, and the protection ADR-0035 described did not exist.

## Decision

- **Where a review pass must lack a tool, the restriction is the spawned
  agent's `tools:` list.** A skill's `allowed-tools` is never cited as one: it
  only spares the prompt for the tools it names. A skill that forks names its
  agent with `agent:`, and that agent's `tools:` is what the pass gets.
  *Reverse if* Claude Code makes `allowed-tools` restrict a forked skill,
  measured the same way.

Which agent carries the restriction, and whether a smaller reviewer input is
kept, is BK-431's open decision, recorded in `.claude/skills/ship/SKILL.md` §
Reviewer permissions and decided by a measured delivery.

## Consequences

- **Positive:** a reader of ADR-0035 learns from this record why solo passes
  lack editing tools, and that before BK-431 they did not.
- **Positive:** a maintainer granting a review pass a tool edits the list that
  takes effect; `rvw-pr`'s frontmatter comment says both lists change together.
- **Negative:** `Bash` stays in every review pass's list, so the restriction is
  still not read-only; the tree check in `/ship` remains what covers it.
- **Neutral:** the probe measured one Claude Code build; a later build may
  differ, which the reverse condition names.
