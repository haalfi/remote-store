# Documentation Content Rules
<!-- doc: dual dest=explanation/design/content-rules.md -->

## Intent & Scope

Rules for writing documentation that stays accurate over time (rules 1–6),
applying to all content: README, guides, docstrings, and inline doc comments.
**Rule 7 is a second axis and carries its own narrower scope**: it is about
whether a section is understood well enough to write, not about staying accurate,
and it binds `sdd/` and `.claude/` only. That split is deliberate — see
[Rule 7 in detail](#rule-7-detail). **Rule 8 is a third axis** and applies to
all content like rules 1–6: it is about which change owns a claim, not how long
the claim stays accurate.

Each rule is one sentence. Where a rule needs more to be applied, its detail is
in [Rules in detail](#rules-in-detail), linked from the rule.

Part of the documentation framework (see [`CLAUDE.md` § Documentation
framework](../CLAUDE.md#documentation-framework)): placement →
[`sdd/AUTHORING.md`](AUTHORING.md); structure →
[`sdd/DOCUMENTATION.md`](DOCUMENTATION.md).

<a id="rules"></a>
## Rules

1. <a id="six-month-test"></a>**The 6-month test.** [review-enforced]
   Before writing any sentence, ask whether it will still be accurate in six
   months; if not, link to its authoritative source or generate it from there
   instead of putting it in stable prose.

2. **Describe principles, not enumerations.** [review-enforced]
   Explain what the system does and why, give 2–3 representative examples, and
   link to the authoritative source rather than copying an exhaustive list,
   which goes stale.

3. **No pseudo-precise values in narrative.** [review-enforced]
   Exact counts, latency figures and percentages belong in generated artefacts,
   and prose uses qualitative categories plus a link; measured history in
   `sdd/` records, backlog items, commit messages and `.claude/skills/` is
   exempt and bound by [`CLAUDE.md` principle 9](../CLAUDE.md#principles)
   instead.

4. **One copy per fact.** [review-enforced]
   Every fact lives in exactly one authoritative place, and everywhere else
   links to it or paraphrases the principle ([where the homes are
   defined](#rule-4-detail)).

5. <a id="source-code-facts-stay-in-source"></a>**Source-code facts stay in source.** [review-enforced]
   API signatures, capability sets, type annotations and default values live
   in code or a generated reference; docs describe the pattern and link to
   them.

6. <a id="code-examples-sourced"></a>**A fenced block in published prose is generated or sourced, not typed.** [review-enforced]
   Runnable code comes from `examples/snippets/`, repository-derived artefacts
   come from checked `gen_*` scripts, and a hand-written fence is allowed only
   for a snippet that cannot run in CI or an illustration of markup, with the
   reason stated ([detail](#rule-6-detail)).

7. <a id="kernsatz"></a>**Lead with the Kernsatz** — the core claim, stated first. [review-enforced]
   A new or substantially rewritten section in `sdd/`, `.claude/` or a
   root-level process doc opens with its core claim in at most three
   sentences; if the claim will not come, the section is not yet understood
   well enough to write, so return to the source instead of writing around the
   gap ([detail](#rule-7-detail)).

8. <a id="change-details-what-it-changes"></a>**A change details only the behaviour it owns.** [review-enforced]
   Text a change writes describes in detail only behaviour the change alters,
   including behaviour it introduces, or exists to document; anything else gets
   at most a one-line pointer to its home, and a finding on such detail is fixed
   by deleting it or replacing it with the pointer, never by narrowing it,
   while a refuted premise the change relies on is fixed in the change or filed
   ([detail](#rule-8-detail)).

## Guides

<a id="rules-in-detail"></a>
### Rules in detail

**The rules above are complete as stated; this section holds what a writer or
reviewer needs to apply four of them.** Rules 1, 2, 3 and 5 need nothing more.

<a id="rule-4-detail"></a>
#### Rule 4: where the homes are defined

**Finding a fact's home is a lookup, not a judgement.** File placement is
[`sdd/AUTHORING.md`](AUTHORING.md) Rule 1, and content type homes are
[`sdd/DOCUMENTATION.md` § 2](DOCUMENTATION.md#content-homes). README and guides
link; they do not copy.

<a id="rule-6-detail"></a>
#### Rule 6: the two homes and the one escape

**A fenced block has a home by what it is, and a typed copy of either kind
drifts without anything noticing.** **Runnable code** comes from
`examples/snippets/` via `pymdownx.snippets` `--8<--` regions, so CI catches API
drift. A **generated non-code artefact** — a diagram whose content is derived
from the repository, such as the support-window chart on the dependency-policy
page — comes from a `gen_*` script with a `--check` gate, and is committed under
`docs-src/_data/` and included the same way; a diagram with dates in it is a
Rule 1 violation the moment it is typed by hand. A hand-written fence notes its
reason inline: a snippet that cannot execute in CI (e.g. it needs real
credentials), or an illustration of markup rather than a thing being described.
An illustration containing a literal `--8<--` must escape it with a leading `;`,
or `pymdownx.snippets` expands it — silently, until `check_paths: true` made a
missing target fail the build.

<a id="rule-7-detail"></a>
#### Rule 7: what triggers it, and why its scope is narrow

**A claim that is absent and a claim that arrives late both fail Rule 7**; the
first is the one it exists to catch, the second the easiest to fix. The opening
also defines any term it coins or uses in a sense the reader cannot be assumed
to hold.

- **What triggers it.** A *section* is a heading-delimited unit of Markdown
  prose at any heading level; a list item, a table and a YAML block are not
  sections, and a section whose body is mostly a table still opens with the
  claim the table serves. *Substantially rewritten* means the section's claim
  changed, not its wording — **and a section that stated no claim before is
  substantially rewritten by definition**, since there was nothing for the
  rewrite to preserve.
- **Why the scope is what it is.** Rules 1–6 govern accuracy over time and
  apply everywhere; this one governs comprehension at writing time and is
  confined to the repo's own reasoning surfaces, where author and reader are
  both contributors. Those are `sdd/`, `.claude/`, and the root-level process
  docs (`CLAUDE.md`, `CONTRIBUTING.md`, `AGENTS.md`). Intent & Scope names the
  first two; the third is named here because the rationale selects it and an
  author rewriting a principle should not have to infer that. Extending it to
  `docs-src/` and docstrings has not been argued for: those readers are not
  contributors, and § 9.5 of the record in [Provenance](#provenance) argues
  they need *more* context rather than a tighter opening.
- **Defining a term does not mean restating an authority.** Rule 4 keeps facts
  in one place; a one-clause gloss plus a link satisfies both.

<a id="rule-8-detail"></a>
#### Rule 8: what a change owns, and why a claim is never narrowed

**Detail about behaviour a change does not own is a claim it had no reason to
measure, and narrowing it only moves the refutation.**

- **Owns and leaves alone.** Documenting is owning: a guide for an existing
  feature or a docstring made accurate owns what it describes. The rule binds
  any text the change writes, such as a docstring, a spec clause, a guide, a
  migration note or a dossier. The home a pointer goes to is the code (Rule 5)
  and the item, spec or ADR that governs the behaviour.
- **Why never narrow.** Such detail is the claim a review refutes on the
  interpreter or platform nobody ran, and a narrower claim is refuted the same
  way somewhere else.
- **Description, not premise.** A premise is a claim the change relies on,
  such as the behaviour its code assumes or the reason it gives for itself.
  Deleting a refuted one would ship the code built on it, so it is filed as a
  backlog item if not fixed in the change.
- The fix shapes this restricts are in
  [`/fix-pr` Step 3](../.claude/skills/fix-pr/SKILL.md#step-3-fix).

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

# Rule 8 — a change details only the behaviour it owns
# bad, in a PR that fixes single-level listing only: a docstring paragraph on
#      how the recursive walk behaves per interpreter and platform
# good: "Recursive walks are unchanged; see <owning item>."
```

### How the rules interact

**Rules 1–6 are one axis; rules 7 and 8 are two others.** Rules 1–6 are expressions of a
single principle: **stable prose describes shape; volatile detail lives in its
authoritative location.** The positive side of the same coin: a document is the
SSoT for its own stable core — its purpose, principles, and design intent. Other
documents link to it for those things; they do not restate them. When in doubt on
any of those six, ask rule 1.

Rule 7 does not belong to that family and rule 1 cannot decide it: the 6-month
accuracy test says nothing about whether a section leads with its claim. When in
doubt on rule 7, try to write the three sentences — failing is the answer.

Rule 8 does not belong to that family either, and rule 1 decides it wrongly: a sentence
about behaviour the change leaves alone can stay accurate for six months and
still break rule 8, which asks whether this change owns what the sentence
describes. When in doubt on rule 8, ask whether the diff changes that
behaviour, exists to document it, or relies on it; if none, the sentence is a
pointer or nothing.

### Finding the documents that are failing readers

Agent traces tag any read that did not deliver (`sdd/traces/_schema.yml`
`outcome`). `hatch run report-trace-outcomes` aggregates those tags into a
ranking of the referenced files, with the traces and sections that cited each.
It is a report, never a gate: read it when asking which documents to improve,
not as a pass/fail. The script's module docstring states what it does not catch.

<a id="provenance"></a>
### Provenance

Rules 1–6 derive from
[`sdd/research/research-doc-content-longevity.md`](research/research-doc-content-longevity.md).
Rule 7 derives from
[`sdd/research/research-appropriate-level-of-detail.md`](research/research-appropriate-level-of-detail.md),
which argues it and marks what it does not establish.
Rule 8 derives from
[`sdd/research/token-usage/report.md` § Run B baseline](research/token-usage/report.md#run-b-baseline-run-as-route-2).
