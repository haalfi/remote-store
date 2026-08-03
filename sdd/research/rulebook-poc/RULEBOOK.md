# Repo Rulebook (POC)
<!-- doc: repo-only -->

Every binding rule in this repo, compiled into one pass and ordered by when you
hit it during a change: always-on conduct first, then plan, build, test,
document, guard, ship.

**Status: PoC artefact, not adopted.** This document has no standing as a repo
process doc, which is why it lives beside its evidence rather than in `sdd/`. It
was tested and did not earn adoption; see
[`research-rulebook-poc.md`](../research-rulebook-poc.md) for the result. That is
a fact about *this document*, not about the rules below.

**These rules bind; this file is not where they bind from.** Every rule below is
authoritative **in its source doc**, and compiling it here neither strengthens
nor weakens it. This document is a *record* of those rules as they read at one
commit — not an instruction to follow, and not a place to look a rule up. Go to
the source.

**Synced to master `83e22a3`, and frozen there.** Following the PoC-folder
convention (cf. [`bk-181-poc/README.md`](../bk-181-poc/README.md), which freezes
once its finding lands), this artefact carries **no ongoing maintenance
obligation**. Divergence from the sources after `83e22a3` is expected and is not
a defect to file — see the research doc § 7, where exactly that happened within a
day and became the PoC's strongest evidence.

Being a record rather than an instruction is what keeps this file inside the
[ripple-check](../../CLAUDE-REFERENCE.md#pre-work-index) *Authority direction
amended* skip for `sdd/research/`, and is why a frozen artefact owes
[`DRIFT-RULES.md` rule 6](../../DRIFT-RULES.md#tolerated) no register entry: it
has nothing to keep in sync. A document that claimed to be a live instruction
*and* declared its own divergence expected would be precisely the stale competing
authority [`CLAUDE.md` principle 4](../../../CLAUDE.md#principles) forbids.

**Compilation conventions.**

- Rules keep their source numbering, so "TESTING rule 4" still resolves.
- Flat prose rules are **verbatim**. Enforcement tags (`[CI-enforced]`,
  `[review-enforced]`) are preserved: they tell you whether a gate catches a
  violation or only a reviewer does.
- Rules whose body is a lookup table, a code example, or multi-paragraph
  exposition are **condensed** to their normative sentences, with the source
  section linked. Sections where this applies are marked *(condensed)*. Copying
  the tables would breach [CONTENT-RULES rule 4](../../CONTENT-RULES.md) inside a
  document whose whole purpose is to make the rules easier to obey.
- Omitted: `## Guides` sections, bad→good examples, rationale, provenance.

---

## 0. Always on — [`CLAUDE.md`](../../../CLAUDE.md) *(condensed below Audits)*

**Scope.** Working principles and operating rules for all work in this repo.
The principles are universal and apply to any contributor, not only agents
([`CONTRIBUTING.md` § Project Principles](../../../CONTRIBUTING.md)).

### Principles

1. **Ship complete**: a change is finished when everything it touches is consistent: code, tests, docs, CHANGELOG, BACKLOG. Track gaps as `[~]`. For releases, follow the full checklist in [`CONTRIBUTING.md` § Release](../../../CONTRIBUTING.md#release).
2. **Verify beyond the diff**: search for what references the thing you changed. The ripple-check in `sdd/CLAUDE-REFERENCE.md` has a Pre-work index (read **before starting** to anticipate ripples) and a Detailed checklist (read **before committing** to verify them). You MUST consult both presentations for changes that touch backends, errors, capabilities, versions, specs, or dependencies.
3. **Repo describes reality at every commit**: docs, backlog, and CHANGELOG reflect current state, not future intent. Same commit, or mark `[~]`.
4. **Single source of truth**: Authoritative references live in one place: link to them, don't copy. Examples: ripple-check, CHANGELOG section order, backlog ID format. Copies become stale.
5. **Specs are source of truth**: code vs spec conflict: code is wrong — unless no test ever asserted that clause for the backend in question, which [`sdd/000-process.md` Rule 7](../../000-process.md#intent-attribution) qualifies (that makes the claim undecided, not the code right), along with prose vs Dafny vs conformance generally. Backlog vs history conflict: backlog is wrong. Fix the less authoritative side.
6. **Run it, don't just type-check it**: verify behavior, not signatures. Reproduce bugs before claiming fixes. Test what matters, not just what type-checks.
7. **Be critical, not agreeable**: challenge assumptions, question completeness, flag what's missing. Especially in reviews: a rubber-stamp is worse than no review. Ask what's untested, what could break, what's absent from the checklist.
8. **Minimize mismatched detail, not detail**: durable artifacts — code, docs, specs, tests — keep the detail whose change-rate and correctness-locus fit the artifact, and relocate detail that belongs to another layer to its authoritative home (per principle 4). Brevity is a byproduct of correct placement, never the target: never delete a load-bearing reason to hit a length budget.

### Audits

1. **Report only.** Present findings with evidence. Do not fix anything.
2. **User decides next steps** — what to fix, whether to create backlog items or an audit doc.
3. **An audit's authority is its diagnosis; its prescription is advisory.** When implementing a follow-up, re-evaluate the proposed disposition against the diagnosed pain — diverge if a different path fits better.

### Bug-fix protocol

Canonical pipeline: [`000-process.md` rule 6](../../000-process.md#workflows). Per
principle 6, **write the failing test, run it, see it fail** before implementing
the fix.

### Backlog (mandatory)

- See `sdd/BACKLOG.md` for workflow rules, ID prefixes, completing-work procedure, and active items. Completed items are in `sdd/BACKLOG-DONE.md`.
- Commit messages start with item ID when applicable (e.g., `AF-008: Add credential masking`).

### Trace authoring (mandatory)

When working on a backlog item, maintain `sdd/traces/<id>-<slug>.yml` as you work, not after merge. Schema: `sdd/traces/_schema.yml`. **"Working on" means implementing or closing the item.** A pure advisory annotation to a body that neither implements nor closes the item does not require a trace.

- **Before starting:** open the trace if it exists, otherwise create one from the schema example.
- **As you read:** record each gate and reference read as a step. Tag `outcome: unclear | misleading` on any read that did not deliver.
- **As events occur:** fill `discovery_followups`, `surprising_ripples`, `co_shipped_items`.
- **Before submitting:** tag `audience` priority-sorted; the CHANGELOG-required rule derives from it.
- **Ship the trace in the same PR as the work.** Not a separate later commit.

### Dev commands

`hatch run all` is the pre-commit gate. Claude-specific shell constraints:

- **No `&&`, `||`, or `;`.** Split into separate Bash tool calls for auto-approval.
- **No shell redirects or pipes (`>`, `2>&1`, `| tee`).** Run commands plain and read output from the tool result for auto-approval.
- **No heredoc in git commits.** Use multiple `-m` flags instead.
- **No `/tmp/`.** Use `./tmp/` instead (gitignored).

### Coverage gate

If `test-cov-strict` fails locally on coverage, **do not loop on "master is passing it, let me re-run"** — start Azurite or treat the strict gate as CI-only.

### Parallel tests

Don't reintroduce `--dist loadgroup`, MaxStartups tuning, or banner retries: the simpler carve-out is the entire stabilisation story. The suite uses **no GPU**; bound concurrent ollama/MCP sessions, not the test workers.

### Branching

- **Never commit or push directly to master.** Always create a feature branch.
- Branch naming: `id-021-store-child`, `fix-streaming-io`, `af-008-credential-masking`, etc.
- Push the feature branch; the user will create PRs or ask you to.

### Response style

Use em dashes (`—`) sparingly in prose responses. Default to periods, colons, or commas. Never use `--` as an em dash substitute anywhere in written output.

In tables, `—` (em dash U+2014) is the standard N/A / none value. Never `--` or `No`. Applies to all capability, feature, and comparison tables.

Preserve `--` only in: shell end-of-options separators, spec-ID ranges, Mermaid edge syntax, `--8<--` snippet includes, and code/SQL comments inside fenced blocks. Table separator rows are structural Markdown.

### Documentation framework

Three authority docs govern documentation. **Apply in order:**
[`AUTHORING.md`](../../AUTHORING.md) (placement) → [`DOCUMENTATION.md`](../../DOCUMENTATION.md) (structure) → [`CONTENT-RULES.md`](../../CONTENT-RULES.md) (longevity).

### GitHub operations

PR workflows are codified as skills: `/pr`, `/rvw-pr`, `/fix-pr`. Use those instead of ad-hoc `gh` commands. Use `/rvw-pr` for PR reviews, not the built-in `/review` CLI command.

Ignore AGENTS.md; `CLAUDE.md` defines Claude Code behavior for this repo.

---

## 1. Plan & spec — [`sdd/000-process.md`](../../000-process.md)

**Scope.** Authoritative source for the Spec-Driven Development workflow,
spec/ADR/RFC formats, backlog tiers, and test traceability. Governs all `sdd/`
content.

1. **No code without a spec**: every testable contract must have a spec section ID.
2. **No spec without tests**: every spec section must have at least one test with `@pytest.mark.spec("ID")`.
3. **Specs are authoritative**: if code and spec disagree, the code is wrong — unless no test ever asserted that clause for the backend in question, which [Rule 7](../../000-process.md#intent-attribution) qualifies: that makes the claim undecided, not the code right.
4. **ADRs are immutable once Accepted**: supersede an Accepted ADR, never edit it. Drafts may be refined before acceptance.
5. **IDs are stable**: once assigned, a section ID never changes meaning. Deprecated sections are marked `[DEPRECATED]`, not removed.
6. **Workflows**:
   - **Features**: SPEC → TEST → IMPLEMENT → VALIDATE → DOCS. Operational items (CI, docs, pins) skip the spec step.
   - **Bug fixes**: BACKLOG → CHANGELOG → failing TEST → FIX → COMMIT together. If the bug contradicts a spec invariant, update the spec.
7. **Prose records the resolution; it does not win the argument**: when spec prose, a Dafny postcondition and a conformance test disagree, the decision is written into the prose — but prose carries no presumption of correctness against a verified postcondition or against a claim the conformance suite never asserted. See [§ Attribution inside the intent domain](../../000-process.md#attribution-inside-the-intent-domain).

The four defeaters that strip prose's presumption (unsatisfiable, over-specified,
under-determined, unenforced) are a lookup table in that section, linked rather
than copied. Exit criteria per feature type (contract-expanding, bridge/adapter) are
checklists, not rules: [§ Feature-type Definition of Done](../../000-process.md#feature-type-definition-of-done).

---

## 2. Build — [`sdd/DESIGN.md`](../../DESIGN.md) *(condensed)*

**Scope.** Coding conventions for all `src/`, `tests/`, and `examples/` code.
All code must pass `ruff check`, `ruff format`, and `mypy --strict`.

1. **Formatting & linting.** Formatter/linter: ruff (line-length 120). Type checking: mypy strict mode. `from __future__ import annotations` in every module.
2. **Module & package descriptions.** Every module starts with a 1-2 sentence docstring explaining *why it exists*. Package `__init__.py` files follow the same rule.
3. **Type annotations.** Public method signatures use PEP 604 union syntax (Python >=3.10). Required args are positional; behavior flags are keyword-only (`*`). `X | None` replaces `Optional[X]`, `X | Y` replaces `Union[X, Y]`. `typing` imports only for generics not yet built-in.
4. **Docstrings.** Google style (`Args:`, `Returns:`, `Raises:`). Short and purpose-focused. RST inline roles (colon-word-colon-backtick patterns) are banned; `scripts/check_rst_roles.py` enforces this in `hatch run lint` and via the `no-rst-roles` pre-commit hook.
5. **Code organisation comments.** **Regions** (`# region:` / `# endregion`) group related items by concern; paired markers that IDEs can fold. **Never** wrap a single class or function — those are already collapsible on their own. **Headlines** (box dividers) introduce a new section at module level; single marker, purely visual. Use headlines in modules with multiple top-level classes or logical sections. Do not use inside classes — use regions there instead.
6. **Method ordering.** Within a class: class variables/constants → `__init__` → properties → public methods (grouped by domain) → dunder methods → private helpers.
7. **Comments.** Minimal, long-term value only. Do not comment *what* the code does — comment *why* when the reason is non-obvious. No TODO comments without a linked issue.
8. **Constants.** Public: `UPPER_SNAKE_CASE`. Private: `_UPPER_SNAKE_CASE`.
9. **`__all__`.** Declared only in public-facing `__init__.py` modules. Internal modules do not need `__all__` — the underscore prefix signals "internal".
10. **Error messages.** f-strings with context for human-readable tracebacks. Structured attributes for programmatic access.
11. **Test style.** Tests are grouped into classes by spec aspect. The class docstring references the spec IDs covered. Each test method carries a `@pytest.mark.spec("ID")` marker for traceability.
12. **Extension API contract.** Extensions in `remote_store.ext.*` and `remote_store.aio.ext.*` are core-adjacent modules, not external consumers. **MUST:** use the public import path when one exists. **SHOULD avoid:** importing from private modules (`remote_store._*`) when no public path exists; when unavoidable due to tight architectural coupling, add an inline comment explaining why. `test_no_private_module_imports` enforces the MUST tier.

---

## 3. Test — [`sdd/TESTING.md`](../../TESTING.md)

**Scope.** Authoritative source for test **quality** rules and top-level
**placement** of test files in `tests/`. Companion to DESIGN rule 11. For test
*architecture*, see [spec 048](../../specs/048-testing-architecture.md) and ADR-0028.

Placement is a lookup table plus three `check-test-placement` lint rules (S, B,
E): [§ Test Subpackage Placement](../../TESTING.md).

1. **Every test must have at least one meaningful assertion** [CI-enforced] — "no crash" is not a test. Public API methods need a failure-path test too (`pytest.raises` with `match=`).
2. **Assert behavior, not types** [review-enforced] — `isinstance` may accompany behavioral assertions but never as the sole check.
3. **Never assert on private attributes** [review-enforced] — verify through observable behavior. Exception: `# internal: no public observable`.
4. **Always use `spec=` with `MagicMock`** [CI-enforced] — `MagicMock()` without `spec` is banned; use `spec=RealClass` or `create_autospec`.
5. **Don't mock what you don't own** [review-enforced] — mock at our boundary (Backend ABC, wrapper, protocol), never third-party internals.
6. **Prefer real dependencies over mocks** [review-enforced] — `MemoryBackend`, in-memory SQLite, `pytest-httpserver` before reaching for mocks.
7. **Maximize behavioral coverage per line of test code** [review-enforced] — parametrize over copy-paste; delete tests subsumed by others (verify via coverage).
8. **Tests must survive refactoring** [review-enforced] — if renaming a private method breaks the test, the test is wrong.
9. **Every `@given` test must assert on a non-rejection path** [review-enforced] — `try/except/return` to reject invalid inputs is fine, but the test must reach an `assert` for some generated inputs. 100% rejection = no-op.
10. **Use Hypothesis profiles, not inline `max_examples`** [review-enforced] — profiles: `dev` (50), `ci` (100), `nightly` (1000). Inline `@settings(max_examples=N)` only when suppressing a health check.
11. **PBT strategies at module scope** [review-enforced] — define as module-level constants for reuse. Inline `st.` chains only for trivial one-liners.
12. **Treat test warnings as latent bugs** [review-enforced] — investigate `RuntimeWarning`/`ResourceWarning` before suppressing. `filterwarnings("ignore:…")` only with a `# acceptable because …` comment.
13. **An inherited ABC default must be opt-in, not opt-out** [review-enforced] — where an ABC method is concrete with a default, conformance asserts *override-or-declared-exemption*, both directions. Not overriding is a decision that must cost a list entry and a spec citation; otherwise forgetting is indistinguishable from deciding.

---

## 4. Document — placement, then structure, then longevity

### 4a. [`sdd/AUTHORING.md`](../../AUTHORING.md) — placement

**Scope.** Authoritative source for where documentation files belong. Governs
the placement of all `.md` content in the repository.

1. **File classification.** Every `.md` belongs to exactly one class. Classification follows a marker on the file or a directory default when no marker is present. A file with no marker and no matching default is unclassified and fails G-01.
2. **Single home.** Each `.md` lives at exactly one path. Other presentations are derived from that path, never copied.
3. **On-disk links.** Every relative `](../../path)` link in every `.md` must resolve to a real on-disk file in the repo. External URLs and pure anchors are exempt. Dual files additionally use only plain Markdown; see CONTENT-RULES rule 6 for the one snippet exception.
4. **One bridge mechanism.** The bridge presents dual files on the docs site and rewrites on-disk links in docs-only files to docs-site URLs at build time. Exactly one bridge applies; new mechanisms are not added.
5. **PR-time enforcement.** A PR-blocking check verifies every framework rule. Failures block merge.

Marker forms (`dual` / `repo-only` / `docs-only`) and directory defaults:
[§ Classification markers](../../AUTHORING.md#classification-markers). If unsure, declare dual.

### 4b. [`sdd/DOCUMENTATION.md`](../../DOCUMENTATION.md) — structure *(condensed)*

**Scope.** Authoritative source for documentation structure and standards.
Governs the shape and quality of all docs work: new pages, restructuring,
reviews.

1. **Diataxis placement.** Every user-facing page belongs to exactly one category: learn → Tutorial; accomplish a task → Guides; look something up → Reference; understand why → Explanation. If unsure, it is probably a Guide. Pages that try to be two things at once must be split.
2. **Content homes.** Each content type has one source location: [§ 2](../../DOCUMENTATION.md#content-homes).
3. **Docstring completeness.** Required `Args`/`Returns`/`Raises`/Example per symbol type: [§ 3](../../DOCUMENTATION.md). No TODOs or placeholders in published docstrings.
4. **Cross-linking requirements.** Link target follows the presentation hosting the destination: **documentation** (guides, API reference, explanation) → ReadTheDocs `/stable/`; **source files** (specs, ADRs, examples, source, CHANGELOG) → the GitHub repository. Within the docs site, always use relative links. Minimum per page: every guide links to at least one API reference page; every guide links to its matching example script (if one exists); every API class page links to its primary guide. Required-cross-link table: [§ 4](../../DOCUMENTATION.md#cross-linking-requirements).
5. **README requirements.** The README must contain: project description; who it is for; when NOT to use it; installation (base + extras); minimal working example with expected output; Store API overview (summary + link, not a method table); supported backends (name, install extra, underlying library, with capability detail linked); links to the docs site, CHANGELOG, and CONTRIBUTING; license, supported Python versions, project status badge.
6. **Typography.** Prose dashes: `—` (U+2014) sparingly as a parenthetical aside; never `--` as a substitute. Table N/A value: `—`, never `--` or `No`. Preserve `--` only in shell flag syntax inside code blocks, spec-ID ranges, Mermaid edge syntax, `--8<--` snippet includes, and code/SQL comments inside fenced blocks.
7. **URL alignment.** URL paths must correspond to navigation position.
8. **Link integrity.** All internal links must resolve in their target presentation. Broken links fail the build, not warn.
9. **Top-level nav structure.** `docs-src/_nav.yml` has only the four Diataxis quadrants as top-level content sections. `Home:` is permitted for the site index; it is not a content section. No other top-level section is allowed.

### 4c. [`sdd/CONTENT-RULES.md`](../../CONTENT-RULES.md) — longevity

**Scope.** Rules for writing documentation that stays accurate over time.
Applies to all content: README, guides, docstrings, inline doc comments.

1. **The 6-month test.** [review-enforced] Before writing any sentence, ask: "Would this still be accurate in 6 months?" If not, it belongs in a linked SSoT or generated artefact, not in stable prose.
2. **Describe principles, not enumerations.** [review-enforced] Write what the system does and why. List 2–3 representative examples and link to the authoritative source. Never reproduce an exhaustive list inline. Copies become lies.
3. **No pseudo-precise values in narrative.** [review-enforced] Exact counts, latency figures, and percentages belong in generated artefacts. In prose: qualitative categories and a link.
4. **One copy per fact.** [review-enforced] Every fact lives in exactly one authoritative place; everywhere else is a link or a paraphrase of the principle. README and guides link; they do not copy.
5. **Source-code facts stay in source.** [review-enforced] API signatures, capability sets, type annotations, default values live in code. Docs describe the pattern and link to the reference; they do not reproduce the values.
6. **Code examples are sourced, not written.** [review-enforced] Doc code blocks come from `examples/snippets/` via `pymdownx.snippets` `--8<--` regions, so CI catches API drift. Hand-written fences are allowed only when the snippet cannot execute in CI; note the reason inline.

---

## 5. Guard consistency — [`sdd/DRIFT-RULES.md`](../../DRIFT-RULES.md)

**Scope.** THE source for how a check that compares two descriptions of the same
thing is designed and reviewed. Applies whenever a change adds a `check_*` gate,
adds a second description of something already described, or sets how often a
recurring check runs. "Drift" here is artifacts disagreeing with each other, not
the storage-consistency sense used in the library's own contracts.

1. **Prefer one normative description driving N artifacts over N² pairwise checks.** [review-enforced] Drive every implementation from one shared suite rather than comparing implementations to each other. Use a pairwise parity assertion only when the two artifacts are genuinely two renderings for two audiences. Pairwise consistency does not compose.
2. **A check must localize, not merely fail.** [review-enforced] Report *which* element differs, not that a difference exists. A gate that cannot name the differing element is not ready to add.
3. **Enumerate the claim space from a canonical artifact, and require an accounted-for result per claim.** [review-enforced] The enumeration must be **derived** from the authoritative artifact, not maintained beside it, and requires stable identifiers. State the granularity: the check reaches no further than the enumeration does.
4. **Declare the authority rule per artifact pair, in writing, before the check exists.** [review-enforced] Which side governs is a decision, not a fact. Declare it in the document that owns the pair, next to the contract it arbitrates — [`000-process.md` Rules 3 and 7](../../000-process.md#rules), [`CLAUDE.md` principles](../../../CLAUDE.md#principles) and [`sdd/formal/README.md`](../../formal/README.md) each carry theirs. Do not restate them here: a second copy of a direction is a second thing to get backwards.
5. **Prefer the mandatory path; when a check is deliberately advisory, state why.** [review-enforced] Default a new check into `preflight`, `lint` or CI. Advisory checks are legitimate under the durable-TODO principle; record the reason a check is not gating.
6. **Distinguish tolerated from unnoticed, structurally.** [review-enforced] Every accepted divergence gets a register entry with an owner and a rationale. An xfail entry, a `[~]` marker and a baseline allow-list are the usual forms; the list is not closed, so any durable home carrying both an owner and a rationale qualifies. A check with no such register will be switched off instead.
7. **State the bound, and estimate the miss rate.** [review-enforced] Document in the check itself what it does not catch. Where feasible, seed known discrepancies and report what fraction was caught. An unstated bound gets trusted past its range.
8. **Verify independence of derivation path; never assume it.** [review-enforced] When adding a second description, record what it was derived from. Independent authors do not produce independent errors.
9. **Set the period from the drift rate, not the calendar.** [review-enforced] Anchor a recurring check to the events that can invalidate the artifact, not to a date. Cost decides how often you look, never what is detectable.

---

## 6. Ship — [`sdd/CI-OPERATIONS.md`](../../CI-OPERATIONS.md)

**Scope.** THE operations handbook for scheduled and automated CI guards: what
each does, when it runs, where its finding shows up, how to act. Covers every
workflow that runs without a contributor present, plus dependabot streams and
Read the Docs. Gating push/PR test and coverage lanes are merge gates, not
maintenance guards, and live in [`CONTRIBUTING.md`](../../../CONTRIBUTING.md).

1. **Durable-TODO principle.** Every scheduled-maintenance guard emits a durable GitHub Issue as its TODO and has a triage entry point (a skill or a runbook in this doc). A red X, a green check, and GitHub's actor email are insufficient alone: each is transient or filterable, so a guard whose only output is one of those is not a guard a maintainer can rely on.
2. **Three layers, kept in agreement.** Every guard is documented in three places: the workflow file header, the runbook, and its triage skill where one exists. Adding or changing a guard means updating all three in the same change.
3. **Exceptions are recorded, never implicit.** A guard that deliberately does not satisfy rule 1 — because it reports to a channel GitHub owns — is listed as an exception with its reason and review cadence. An undocumented scheduled or review-triggered workflow fails `scripts/check_ci_inventory.py`.

---

## 7. Document format — [`CONTRIBUTING.md` § Authoritative Document Format](../../../CONTRIBUTING.md#authoritative-document-format) *(condensed)*

**Scope.** The fixed structure of the process docs compiled above. Applies to
root-level `sdd/` process documents. Does not apply to specs, ADRs, RFCs,
research, audits, `BACKLOG.md`, `README`, `CHANGELOG`, `DEVELOPMENT_STORY`,
`CLAUDE.md`, or `CONTRIBUTING.md`, which follow their own formats.

- **Principle.** Meaningful minimum. Each document covers one concern, states clear principles, and stops. No detailed instructions for every situation.
- **Structure.** 1. **Intent & Scope** — what this document governs and who it is for, max 5–10 lines. 2. **Rules** — numbered, mandatory constraints. 3. **Guides** *(optional)* — heuristics, examples, lookup tables; useful but not binding. Sections 1 and 2 alone must be sufficient to understand the document's purpose and obligations.
- **Cross-check.** Every sentence and section must pass this test: *"this would force different behavior in situation X."* If it does not, it is decoration — rewrite as a rule or remove.
- **Exclusions.** Authoritative documents must not contain: 1. explanation or rationale; 2. history or changelog-style notes; 3. meta-commentary about the document itself.

---

## Sources

| Section | Source | Rules |
|---|---|---|
| 0 | [`CLAUDE.md`](../../../CLAUDE.md) | 8 principles + operating rules |
| 1 | [`sdd/000-process.md`](../../000-process.md) | 7 |
| 2 | [`sdd/DESIGN.md`](../../DESIGN.md) | 12 |
| 3 | [`sdd/TESTING.md`](../../TESTING.md) | 13 |
| 4a | [`sdd/AUTHORING.md`](../../AUTHORING.md) | 5 |
| 4b | [`sdd/DOCUMENTATION.md`](../../DOCUMENTATION.md) | 9 |
| 4c | [`sdd/CONTENT-RULES.md`](../../CONTENT-RULES.md) | 6 |
| 5 | [`sdd/DRIFT-RULES.md`](../../DRIFT-RULES.md) | 9 |
| 6 | [`sdd/CI-OPERATIONS.md`](../../CI-OPERATIONS.md) | 3 |
| 7 | [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#authoritative-document-format) | format contract |

Not compiled: [`sdd/CLAUDE-REFERENCE.md`](../../CLAUDE-REFERENCE.md) (lookup tables,
not rules), [`sdd/BACKLOG.md`](../../BACKLOG.md) (workflow conventions), specs, ADRs
(see [`adrs/DIGEST.md`](../../adrs/DIGEST.md)), RFCs, and the `## Rules` blocks in
`.claude/skills/`.
