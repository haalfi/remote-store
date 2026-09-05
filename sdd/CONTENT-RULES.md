# Documentation Content Rules
<!-- doc: dual dest=explanation/design/content-rules.md -->

## Intent & Scope

Rules for writing documentation that stays accurate over time (rules 1–6),
applying to all content: README, guides, docstrings, and inline doc comments.
**Rule 7 is a second axis and carries its own narrower scope**: it is about
whether a section is understood well enough to write, not about staying accurate,
and it binds `sdd/` and `.claude/` only. That split is deliberate — see the note
in the rule.

Part of the documentation framework (see [`CLAUDE.md` § Documentation
framework](../CLAUDE.md#documentation-framework)): placement →
[`sdd/AUTHORING.md`](AUTHORING.md); structure →
[`sdd/DOCUMENTATION.md`](DOCUMENTATION.md).

<a id="rules"></a>
## Rules

1. <a id="six-month-test"></a>**The 6-month test.** [review-enforced]
   Before writing any sentence, ask: "Would this still be accurate in 6 months?"
   If not, it belongs in a linked SSoT or generated artefact, not in stable prose.

2. **Describe principles, not enumerations.** [review-enforced]
   Write what the system does and why. List 2–3 representative examples and link
   to the authoritative source. Never reproduce an exhaustive list inline.
   Copies become lies.

3. **No pseudo-precise values in narrative.** [review-enforced]
   Exact counts, latency figures, and percentages belong in generated artefacts
   (FEATURES.md, benchmark output, API reference). In prose: qualitative categories
   and a link. Write "significantly faster via caching" + link, not "+17% / 29×".
   Out of scope: counts in `sdd/` records, backlog items, commit messages and
   `.claude/skills/`, which are measured history rather than narrative and are
   bound by [`CLAUDE.md` principle 9](../CLAUDE.md#principles) instead.

4. **One copy per fact.** [review-enforced]
   Every fact lives in exactly one authoritative place; everywhere else is a link
   or a paraphrase of the principle. Authoritative homes: file placement in
   [`sdd/AUTHORING.md`](AUTHORING.md) Rule 1; content type homes in
   [`sdd/DOCUMENTATION.md` § 2](DOCUMENTATION.md#content-homes). README and
   guides link; they do not copy.

5. <a id="source-code-facts-stay-in-source"></a>**Source-code facts stay in source.** [review-enforced]
   API signatures, capability sets, type annotations, default values live in code.
   Docs describe the pattern and link to the reference; they do not reproduce the
   values.

6. <a id="code-examples-sourced"></a>**Code examples are sourced, not written.** [review-enforced]
   Doc code blocks come from `examples/snippets/` via `pymdownx.snippets`
   `--8<--` regions, so CI catches API drift. Hand-written fences are allowed
   only when the snippet cannot execute in CI (e.g. needs real credentials);
   note the reason inline.

7. <a id="kernsatz"></a>**Lead with the Kernsatz** — the core claim, stated first. [review-enforced]
   A new or substantially rewritten section in `sdd/` or `.claude/` opens with
   its core claim in at most three sentences, defining any term it coins or uses
   in a sense the reader cannot be assumed to hold. If those sentences will not
   come, the section is not yet understood well enough to write: return to the
   source — the material the section is about — instead of writing around the gap.
   What follows the Kernsatz is detail the Kernsatz earned. **A claim that is absent
   and a claim that arrives in paragraph four both fail this rule**; the first is
   the one it exists to catch, and the second is the one it is easiest to fix.
   **What triggers it.** A *section* is a heading-delimited unit of Markdown
   prose at any heading level; a list item, a table and a YAML block are not
   sections, and a section whose body is mostly a table still opens with the
   claim the table serves. *Substantially rewritten* means the section's claim
   changed, not its wording — **and a section that stated no claim before is
   substantially rewritten by definition**, since there was nothing for the
   rewrite to preserve.
   **Why the scope is narrow.** Rules 1–6 govern accuracy over time and apply
   everywhere; this one governs comprehension at writing time and is deliberately
   confined to the repo's own reasoning surfaces, where the author and reader are
   both contributors. Extending it to `docs-src/` and docstrings has not been
   argued for.
   **Defining a term does not mean restating an authority.** Rule 4 keeps facts in
   one place; a one-clause gloss plus a link satisfies both.

## Guides

### Examples (bad → good)

```text
# Rule 3 — no pseudo-precise values in prose
# bad
"For S3, reads add 0.7 ms (+15%) over boto3; listing is 29× faster."
# good
"S3 listing is significantly faster via s3fs caching. See the performance guide."

# Rule 2 — principle over exhaustive list
# bad
"Extensions: <ext-A>, <ext-B>, <ext-C>, <ext-D>, ... <ext-N>."
# good
"Extensions add observability, caching, and analytical integrations — see FEATURES.md."

# Rule 4 — one copy per fact
# bad: capability table in README copied from FEATURES.md
# good: "See the capabilities matrix for full backend support detail."

# Rule 5 — source-code facts stay in source
# bad in README: a method-by-method table listing every Store method
# good: "See the Store API reference for the full method list."

# Rule 7 — lead with the Kernsatz
# bad: three paragraphs circling what the retry policy is for, naming the cases
#      it covers and the ones it does not, and never saying what it decides
# also bad: the same claim stated correctly, but only in the last paragraph
# good: "A retry policy decides which failures are worth repeating. It repeats
#        the ones a later attempt could plausibly answer differently, and no
#        others." — then the cases, and only what that claim earned.
```

### How the rules interact

**Rules 1–6 are one axis; rule 7 is the other.** Rules 1–6 are expressions of a
single principle: **stable prose describes shape; volatile detail lives in its
authoritative location.** The positive side of the same coin: a document is the
SSoT for its own stable core — its purpose, principles, and design intent. Other
documents link to it for those things; they do not restate them. When in doubt on
any of those six, ask rule 1.

Rule 7 does not belong to that family and rule 1 cannot decide it: the 6-month
accuracy test says nothing about whether a section leads with its claim. When in
doubt on rule 7, try to write the three sentences — failing is the answer.

### Finding the documents that are failing readers

Agent traces tag any read that did not deliver (`sdd/traces/_schema.yml`
`outcome`). `hatch run report-trace-outcomes` aggregates those tags into a
ranking of the referenced files, with the traces and sections that cited each.
It is a report, never a gate: read it when asking which documents to improve,
not as a pass/fail. The script's module docstring states what it does not catch.

### Provenance

Derived from [`sdd/research/research-doc-content-longevity.md`](research/research-doc-content-longevity.md).
