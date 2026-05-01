# Documentation Content Rules

## Intent & Scope

Rules for writing documentation that stays accurate over time. Applies to
all content: README, guides, docstrings, and inline doc comments.

Part of the documentation framework (see `CLAUDE.md` § Documentation
framework): placement → `sdd/AUTHORING.md`; structure →
`sdd/DOCUMENTATION.md`.

Derived from `sdd/research/research-doc-content-longevity.md`.

## Rules

1. **The 6-month test** [review-enforced]
   — Before writing any sentence, ask: "Would this still be accurate in 6 months?"
   If not, it belongs in a linked SSoT or generated artefact — not in stable prose.

2. **Describe principles, not enumerations** [review-enforced]
   — Write what the system does and why. List 2–3 representative examples and link
   to the authoritative source. Never reproduce an exhaustive list inline —
   copies become lies.

3. **No pseudo-precise values in narrative** [review-enforced]
   — Exact counts, latency figures, and percentages belong in generated artefacts
   (FEATURES.md, benchmark output, API reference). In prose: qualitative categories
   and a link. Write "significantly faster via caching" + link — not "+17% / 29×".

4. **One copy per fact** [review-enforced]
   — Every fact lives in exactly one authoritative place; everywhere else is a link
   or a paraphrase of the principle. The authoritative home for each content type
   is in `sdd/DOCUMENTATION.md` § 2. README and guides link; they do not copy.

5. **Source-code facts stay in source** [review-enforced]
   — API signatures, capability sets, type annotations, default values live in code.
   Docs describe the pattern and link to the reference; they do not reproduce the
   values.

6. **Code examples are sourced, not written** [review-enforced]
   — Doc code blocks come from `examples/snippets/` via `pymdownx.snippets`
   `--8<--` regions, so CI catches API drift. Hand-written fences are allowed
   only when the snippet cannot execute in CI (e.g. needs real credentials);
   note the reason inline.

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
```

### How the rules interact

The detail rules are all expressions of the same principle: **stable prose describes
shape; volatile detail lives in its authoritative location.** The positive side
of the same coin: a document is the SSoT for its own stable core — its purpose,
principles, and design intent. Other documents link to it for those things; they
do not restate them. When in doubt, ask rule 1.
