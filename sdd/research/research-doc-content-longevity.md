# Research: Documentation Content Longevity

## Context

An analysis of the README revealed that several sections had drifted from the
source of truth they described, in some cases reversing the direction of a
claim (e.g., performance overhead that was actually a gain). The same structural
pattern — manually maintained prose projecting facts that live authoritatively
elsewhere — appears throughout `docs-src/`, `guides/`, and docstrings.

The root cause is not carelessness. It is the absence of a rule that distinguishes
stable content (principles, shape, intent) from volatile content (counts, figures,
enumerated lists). Without that distinction, every documentation edit is one
decision away from creating an undeclared copy.

## Problem patterns observed

**Pseudo-precise values in narrative.** Performance figures, method counts,
and capability enumerations hardcoded in prose. These drift silently: the
benchmark output is regenerated, the source is updated, but the prose is not.

**Exhaustive inline lists.** Listing every backend, every extension, or every
method in a document that is not the authoritative source. Each item is a
potential future discrepancy.

**Capability detail outside FEATURES.md.** The backends table in README
reproduced the same capability columns that FEATURES.md owns, creating two
surfaces to update and two ways to contradict the code.

**Source-code facts in narrative.** Method signatures and default values
copied into guides or README. When the signature changes, the guide stays wrong
until someone notices.

## Principles considered

The following principles were evaluated as a basis for rules:

- **The 6-month test.** "Would this sentence still be accurate in 6 months?"
  This is a reliable filter: if the answer is "maybe not", the content is
  volatile and belongs in a linked artefact, not in stable prose.

- **Stable core, referenced details.** The durable content of a document is
  its principles, shape, and intent. The volatile content — enumerations,
  figures, signatures — belongs in the authoritative location with a link
  from the narrative.

- **One copy per fact.** A copy is a future lie. Every fact that exists in
  two places will eventually be true in one and false in the other.

- **Shorter and more precise is better.** Long documents with exhaustive
  coverage are harder to keep current. A short document that links out is
  easier to verify and easier to maintain.

- **No pseudo-precision.** Exact numbers invite false confidence. Qualitative
  language ("significantly faster", "minimal overhead", "a small set of") ages
  better and is rarely wrong.

## Decision

These principles became five rules in `sdd/CONTENT-RULES.md`. The rules are
phrased in the same format as `sdd/TESTING.md`: numbered, review-enforced,
with bad→good examples to make the distinction concrete.

The existing `sdd/DOCUMENTATION.md` (structure and placement) was updated to
reference CONTENT-RULES.md and to tighten the README requirements so they no
longer mandate exhaustive tables.

A separate task will apply these rules to the existing README, guides, and
docstrings where the patterns above were found. That task is distinct from
establishing the rules: the research and rule-making happen first; cleanup
follows as a normal development task.

## What does not change

- **FEATURES.md** remains the authoritative snapshot of backends, extensions,
  capabilities, and extras for each release.
- **Benchmark output** remains auto-generated; the narrative links to it.
- **Docstring completeness rules** (Args/Returns/Raises) in `sdd/DOCUMENTATION.md`
  rule 3 are unchanged; a Notes-placement sentence was added there for
  supplementary context.
