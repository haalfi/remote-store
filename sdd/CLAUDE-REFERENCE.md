# Claude Code Reference
<!-- doc: repo-only -->

Lookup tables and detailed procedures for Claude Code sessions.
Scope: cross-file dependency checks, repo navigation, and layout.

---

<a id="ripple-check-table"></a>
## Ripple-check table

The ripple-check has two presentations of the same set of triggers, grouped by SDD lifecycle phase (specs and contract → code surface → tests → docs → release and meta):

- The **Pre-work index** below is a one-line-per-trigger scan you read **before starting work** that might touch any of the triggers. It exists because 3/9 sampled PRs missed ripples by consulting the table only at verify-end (`sdd/research/research-agent-workflow-substrate.md` § 2.3).
- The **Detailed checklist** below it lists the same triggers with the full ripple set, used at verify-end after the diff is complete and by PR reviewers.

Both presentations cover the same triggers in the same lifecycle order, but they are not strictly row-for-row identical: the Detailed checklist expands some triggers into finer rows (e.g. the gating dicts split into sync and async), so its row count runs a little higher. Trigger names are bare topics (no leading article). If you add, remove, rename, or re-order a trigger, update both presentations and any trace `section:` strings that cite the row by name.

This is machine-enforced by `scripts/check_ripple_parity.py` (in `lint` and `docs-gate`): every Pre-work index trigger must appear in the Detailed checklist under the same section, in the same order. The Detailed checklist may add expansion rows with no Pre-work twin (the gating splits), but may not drop or re-order a trigger, and an expansion may not precede its parent within a section. Two things the gate does not police, so mind them by hand: a trigger's *name* must be one bold leading cell (a name wrapped across two bold cells reads as two unknown triggers and fails the gate, so keep it on one row), and trace `section:` strings are not yet checked against live row names.

<!-- Two-presentations-one-source: the same triggers appear in both, in the same
order; the Detailed checklist may expand one trigger into several rows, so the
row counts are not required to be equal. Trace section strings (sdd/traces/*.yml)
cite row names verbatim — renaming requires updating those too. Enforced by
scripts/check_ripple_parity.py (in `lint` and `docs-gate`): every Pre-work
trigger must appear in the Detailed checklist under the same section and order. -->

<a id="pre-work-index"></a>
### Pre-work index

Read this before starting. One line per trigger.

#### Spec & contract

| Trigger                       | Ripples (at a glance) |
|-------------------------------|-----------------------|
| Spec section                  | Tests tagged `@pytest.mark.spec("ID")`, BACKLOG if related |
| Capability                    | `003-backend-adapter-contract.md` spec, every backend's `capabilities()`, Store surface, capability matrix |
| Error type                    | `005-error-model.md` spec, every backend's error mapping + tests, docstring "raised by", troubleshooting guide |

#### Code surface

| Trigger                       | Ripples (at a glance) |
|-------------------------------|-----------------------|
| Backend                       | README backends table, `pyproject` extras, guides, docs nav, examples, specs, `_registry.py` |
| Store or Backend ABC          | All backend implementations, conformance tests |
| Public method signature       | Docstring (Args/Returns/Raises), examples that call it, guides referencing it |
| Store method                  | README Store API table + comparison count, `__init__.py` `__all__`, README examples table, `examples/`, spec, guides, CHANGELOG |
| Public API (`__all__`)        | README Store API table, `reference/api/*.md` directive + index summary + `_nav.yml`, `examples/`, user guides; check `backends/__init__.py` *and* `aio/__init__.py` `__all__` too. `index.md` parity machine-verified by `gen-api-check` (ID-173): every public symbol needs an index row (or an entry on the small `_INDEX_EXEMPT` backend-companion allowlist) |
| Extension                     | `__init__.py` exports (ADR-0013 rules), `pyproject` extras, README extensions table, `reference/api/extensions/*` + index + `_nav.yml`, guides, examples, CHANGELOG, BACKLOG |
| Dependency                    | `pyproject` extras + pins, README install, docs prerequisites |
| `CAPABILITIES` ClassVar       | `003-backend-adapter-contract.md` (BE-003), `test_capabilities.py`, `conformance/test_identity.py`, custom-backend guide, `examples/snippets/` |
| `_GATING` dict                | `001-store-api.md` (STORE-gate entries), `test_store.py`, guides if a method's cap docs change, `store.md` admonitions (verified by `gen-api-check`, ID-170). Two independent constants: sync in `_store.py`, async in `aio/_async_store.py` (ID-194); both verified against their pages (`store.md`, `aio/store.md`) by `gen-api-check` (ID-172); keep both in step with their classes |
| `_BACKEND_GATING` dict        | `003-backend-adapter-contract.md` (BE-027), `backend.md` admonitions (verified by `gen-api-check`, ID-171). Async counterpart `_ASYNC_BACKEND_GATING` (`gen_graph.py`, ASYNC-045a) → `aio/backend.md` `AsyncBackend` admonitions (verified by `gen-api-check`, ID-172) |
| `__mirror__` attribute        | Async spec (mirror invariant), `gen_graph.py` (mirrors-edge), `tests/` mirror test on add/remove |

#### Tests

| Trigger                       | Ripples (at a glance) |
|-------------------------------|-----------------------|
| New test file                 | OS-sensitive code? Add `pytestmark = pytest.mark.os_sensitive`; periodically re-audit |

#### Docs

| Trigger                       | Ripples (at a glance) |
|-------------------------------|-----------------------|
| Docs navigation               | Per-section `_nav.yml` files, `docs-src/guides/backends/index.md`, [AUTHORING Rule 1](AUTHORING.md#file-classification), [DOCUMENTATION § Content homes](DOCUMENTATION.md#content-homes) |
| API reference page            | [DOCUMENTATION § API page building blocks](DOCUMENTATION.md#api-page-building-blocks) + required sections |
| Example script                | README examples table, generated `tutorial/examples/<slug>.md`, `tests/test_examples.py` import |
| ADR                           | `preflight`'s `gen_adr_digest.py --check` gates digest freshness **and** supersession-graph consistency: a `STALE:` failure is fixed by `hatch run gen-adr-digest` + committing `sdd/adrs/DIGEST.md`; a `DRIFT:` failure is fixed by editing the ADR's `## Status` metadata (regenerating won't clear it); it also prints `ADVICE` notices for bloated `## Decision` sections (word budget, version pins, heading depth) — these do not change the exit code, but they are for acting on (relocate the mislocated detail), not ignoring: review-enforced, like `CONTENT-RULES` |
| Tracker ID in published prose | Any backlog/spec coordinate (`PREFIX-NNN`, `spec NNN`, `RFC-NNNN`, `ADR-NNNN`, `PR #NNN`) leaking into a docstring rendered by mkdocstrings or any `.md` under `docs-src/` (plus README, FEATURES, CONTRIBUTING); [CONTENT-RULES Rules 1 + 5](CONTENT-RULES.md#rules). Out of scope: `sdd/**`, CHANGELOG, DEVELOPMENT_STORY, source `#` comments |
| Local-machine reference in any committed file | Grep all changed file types (`.md`, `.py`, `.sh`, `.yml`, `.dfy`, `.tla`) for: `See memory `, `` captured as `<slug>.md` `` (Claude Code memory slugs), `[A-Z]:\\[A-Za-z]` (Windows drive paths — skip `\n`/`\r`/`\t` escape sequences), `~/.claude`, `.claude/projects`. Replace each with the principle it refers to, inline. Enforced by the shared [PR validation gates](#pr-validation-gates) that `/pr` and `/fix-pr` both run. |

#### Release & meta

| Trigger                       | Ripples (at a glance) |
|-------------------------------|-----------------------|
| Bug fix                       | BACKLOG item, CHANGELOG stub under `[Unreleased]`, failing test **before** fix, spec if invariant contradicted |
| Backlog item touched          | Live trace at `sdd/traces/<id>-<slug>.yml` ([CLAUDE.md § Trace authoring](../CLAUDE.md#trace-authoring)); schema at `sdd/traces/_schema.yml`; `audience` drives the CHANGELOG-required rule |
| CHANGELOG entry               | One-line `- <ID>: <Title>` at top of `[Unreleased]`; release skill expands and groups |
| Version number                | `bump-my-version` (drives `pyproject` file list), then `hatch run gen-graph`; full checklist in [CONTRIBUTING § Phase 2](../CONTRIBUTING.md#phase-2) |
| Source/test/spec counts       | README badge + CI coverage report (no manual table) |
| New authoritative process doc in `sdd/` | [CLAUDE.md § Documentation framework](../CLAUDE.md#documentation-framework) (if part of the trio), [CONTRIBUTING § Authoritative Document Format](../CONTRIBUTING.md#authoritative-document-format) (Scope subsection within), sibling authority back-references, `.claude/skills/*/SKILL.md` foundation lists, `docs-src/explanation/design/_nav.yml`, and this ripple-check |

<a id="detailed-checklist"></a>
### Detailed checklist

Read this at verify-end (after the diff is complete) and during PR review. Each row expands the Pre-work index above.

#### Spec & contract

| Trigger                    | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **Spec section**           | Tests with `@pytest.mark.spec("ID")`, BACKLOG if related  |
| **Capability**             | `sdd/specs/003-backend-adapter-contract.md`,              |
|                            | every backend's `capabilities()`, Store surface API,      |
|                            | capabilities matrix page                                  |
| **Error type**             | `sdd/specs/005-error-model.md`, all backends' error       |
|                            | mapping, tests for every backend,                         |
|                            | error docstring "raised by" list, troubleshooting guide   |

#### Code surface

| Trigger                    | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **Backend**                | README backends table, `pyproject.toml` extras,           |
|                            | `docs-src/guides/backends/`, docs nav, `examples/`,       |
|                            | `sdd/specs/`, `CONTRIBUTING.md` repo structure,           |
|                            | `src/remote_store/_registry.py` auto-registration         |
| **Store or Backend ABC**   | All backend implementations, conformance tests            |
| **Public method signature** | Docstring (Args, Returns, Raises), examples that         |
|                            | call it, guides that reference it                         |
| **Store method**           | README Store API table + comparison method count,         |
|                            | `__init__.py` `__all__`, README examples table (if new    |
|                            | example added), `examples/`, spec in `sdd/specs/`,        |
|                            | guides, CHANGELOG. If the method is **gated**, see the     |
|                            | `_GATING` row. If **ungated** (no `_gate()` call), it      |
|                            | becomes a graph method node with `gated: false` (DGM-014) |
|                            | → `hatch run gen-graph`, then add Returns/Description to    |
|                            | `_UNGATED_STORE_DETAILS` in `scripts/gen_features.py`      |
|                            | (drift-guarded) and `hatch run gen-features`               |
| **Public API** (`__all__`) | README Store API table, `docs-src/reference/api/*.md` directive |
|                            | (every `__all__` symbol needs a `:::` entry),             |
|                            | `docs-src/reference/api/index.md` summary table (every public |
|                            | class/function needs a row, unless it is on the small     |
|                            | `_INDEX_EXEMPT` backend-companion allowlist in            |
|                            | `scripts/check_api_docs.py`, e.g. `ArrowSerializer`),     |
|                            | `docs-src/reference/api/_nav.yml`, `examples/`, user guides. |
|                            | **Check**: `backends/__init__.py` *and* `aio/__init__.py` |
|                            | `__all__` too — secondary/async public API (`SFTPUtils`,  |
|                            | `AsyncStore`) is a co-equal source. `index.md` parity is  |
|                            | machine-verified by `hatch run gen-api-check` (ID-173),   |
|                            | bidirectionally (missing rows *and* stale links fail);    |
|                            | run under `hatch` so optional-dep symbols are present     |
| **Extension**              | `__init__.py` exports (pure-Python only; optional-dep     |
|                            | extensions are NOT re-exported — ADR-0013),               |
|                            | `pyproject.toml` extras (if optional dep),                |
|                            | README extensions table, `docs-src/reference/api/extensions/*.md` + |
|                            | `reference/api/extensions/index.md` + `reference/api/extensions/_nav.yml`, |
|                            | `docs-src/guides/`, `docs-src/` + `_nav.yml`,             |
|                            | `examples/`, CHANGELOG, BACKLOG                           |
| **Dependency**             | `pyproject.toml` extras + minimum pins, README install    |
|                            | instructions, docs prerequisites                          |
| **`CAPABILITIES` ClassVar** | `sdd/specs/003-backend-adapter-contract.md` (BE-003),    |
| (added/changed on a backend | `tests/test_capabilities.py` (class-attr parametrize),   |
| or ABC)                     | `tests/backends/conformance/test_identity.py` (subset invariant), |
|                            | `docs-src/guides/custom-backend-guide.md`, `examples/snippets/` |
| **`_GATING` dict**          | `sdd/specs/001-store-api.md` (STORE-gate entries),       |
| (key→Capability mapping     | `tests/test_store.py` (gate-fires parametrize list),     |
| in `_store.py`)             | `docs-src/guides/` if a method's capability docs change. |
|                            | `docs-src/reference/api/store.md` `!!! note "Requires …"` |
|                            | admonitions — verified by `hatch run gen-api-check`       |
|                            | (ID-170)                                                  |
| **`_GATING` dict** (async)  | `src/remote_store/aio/_async_store.py` mirrors the       |
| (key→Capability mapping     | sync constant minus `read_seekable` / `open_atomic`      |
| in `aio/_async_store.py`)   | (no async equivalents). Consumed at runtime by           |
|                            | `AsyncStore._gate()` and statically by                   |
|                            | `scripts/gen_graph.py` (ID-194). `aio/store.md`          |
|                            | `AsyncStore` admonitions verified by `hatch run          |
|                            | gen-api-check` (ID-172)                                   |
| **`_BACKEND_GATING` dict**  | `sdd/specs/003-backend-adapter-contract.md` (BE-027),    |
| (key→cap-name strings       | `docs-src/reference/api/backend.md` `!!! note            |
| in `scripts/gen_graph.py`)  | "Requires …"` admonitions — verified by `hatch run       |
|                            | gen-api-check` (ID-171). Lives in gen_graph.py            |
|                            | (static-extraction only; Backend has no runtime           |
|                            | `_gate()` equivalent).                                    |
| **`_ASYNC_BACKEND_GATING`** | `sdd/specs/029-async-store-backend-api.md` (ASYNC-045a), |
| (key→cap-name strings       | `docs-src/reference/api/aio/backend.md` `AsyncBackend` `!!! note  |
| in `scripts/gen_graph.py`)  | "Requires …"` admonitions — verified by `hatch run        |
|                            | gen-api-check` (ID-172). Mirrors `_BACKEND_GATING` minus  |
|                            | `read_seekable` / `open_atomic`; same gen_graph.py        |
|                            | static-extraction role (no runtime `_gate()`).            |
| **`__mirror__` attribute** | `sdd/specs/` async spec (async-mirror invariant),         |
| (on an async backend)      | `scripts/gen_graph.py` (mirrors-edge emission),           |
|                            | `tests/` mirror test if backend is added or removed       |

#### Tests

| Trigger                    | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **New test file**          | Ask: does it exercise OS-specific code (path separators,  |
|                            | `os.replace`, `tempfile`, local filesystem, atomic writes)?|
|                            | If yes → add `pytestmark = pytest.mark.os_sensitive` at   |
|                            | module level (or mark fixture params for parameterized     |
|                            | suites). Periodically re-audit existing files for          |
|                            | correctness — see `@pytest.mark.os_sensitive` in          |
|                            | `pyproject.toml` for rationale.                           |

#### Docs

| Trigger                    | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **Docs navigation**        | Per-section `_nav.yml` files in `docs-src/`,              |
|                            | `docs-src/guides/backends/index.md`,                      |
|                            | [AUTHORING.md Rule 1](AUTHORING.md#file-classification),  |
|                            | [DOCUMENTATION.md § Content homes](DOCUMENTATION.md#content-homes) |
| **API reference page**     | [DOCUMENTATION.md § API page building blocks](DOCUMENTATION.md#api-page-building-blocks) |
| (new or restructured)      | and building blocks for required sections                 |
| **Example script**         | README examples table, generated `tutorial/examples/<slug>.md` |
|                            | `tests/test_examples.py` import                           |
| **ADR**                    | `gen_adr_digest.py --check` in `preflight` is a drift     |
| (add / edit `sdd/adrs/*.md`) | gate over two independent failures. `STALE:` (the       |
|                            | committed `sdd/adrs/DIGEST.md` no longer matches a fresh   |
|                            | render) → run `hatch run gen-adr-digest`, commit the      |
|                            | digest. `DRIFT:` (supersession-graph inconsistency — a    |
|                            | one-sided `Supersedes`/`Superseded by` edge, status       |
|                            | drift, orphaned `Superseded`) → fix the ADR's `## Status` |
|                            | table; regenerating does **not** clear it. It also prints |
|                            | `ADVICE` notices for bloated `## Decision` sections (word |
|                            | budget, version pins, heading depth): these do not change |
|                            | the exit code, but are for acting on (relocate the        |
|                            | detail), not ignoring — review-enforced                  |
| **Tracker ID in published prose** | Any backlog or spec coordinate (`PREFIX-NNN`,      |
| (any prose change that touches | `spec NNN`, `RFC-NNNN`, `ADR-NNNN`, `PR #NNN`) leaking |
| docstrings of public symbols | into a docstring under `src/remote_store/` or any        |
| or `docs-src/` markdown)    | `.md` under `docs-src/` (plus README, FEATURES,           |
|                            | CONTRIBUTING). Per [CONTENT-RULES.md Rules 1 + 5](CONTENT-RULES.md#rules): |
|                            | rewrite the sentence in behavioural terms and put        |
|                            | the internal coordinate in the matching `sdd/specs/`    |
|                            | clause or the BACKLOG entry instead. Out of scope:      |
|                            | `sdd/**`, CHANGELOG, DEVELOPMENT_STORY, agent harness   |
|                            | files, generated artefacts under `docs-src/_data/`,     |
|                            | and `#` comments inside source files                    |
| **Local-machine reference in any committed file** | Grep every changed file type (`.md`, `.py`, `.sh`, |
| (private path or memory     | `.yml`, `.dfy`, `.tla`) for references unreachable from   |
| slug unreachable from the   | the repo: `See memory `, `` captured as `<slug>.md` ``    |
| repo)                       | (Claude Code memory slugs), `[A-Z]:\\[A-Za-z]` (Windows  |
|                            | drive paths, skipping the `\n`/`\r`/`\t` escape           |
|                            | sequences), `~/.claude`, `.claude/projects`. Replace     |
|                            | each with the principle it refers to, inline. Enforced   |
|                            | by the shared [PR validation gates](#pr-validation-gates) |
|                            | that `/pr` and `/fix-pr` both run.                        |

#### Release & meta

| Trigger                    | Also check / update                                       |
|----------------------------|-----------------------------------------------------------|
| **Bug fix**                | `sdd/BACKLOG.md` (item), `CHANGELOG.md` (stub line under  |
|                            | `[Unreleased]`), failing test **before** the fix, spec if |
|                            | the bug contradicts a spec invariant                      |
| **Backlog item touched**   | Live trace at `sdd/traces/<id>-<slug>.yml` per [CLAUDE.md § Trace authoring](../CLAUDE.md#trace-authoring) |
|                            | (mandatory). Created/updated as work                      |
|                            | proceeds (not retrospectively); ships in same PR; schema  |
|                            | at `sdd/traces/_schema.yml`. `audience` priority-sorted   |
|                            | drives the CHANGELOG-required rule.                       |
| **CHANGELOG entry**        | Add `- <ID>: <Title>` at the top of `[Unreleased]`.       |
|                            | One line, no details, no sections. Release skill          |
|                            | organises into sections and expands to prose.             |
| **Version number**         | Run `bump-my-version` (manages the files listed in        |
|                            | `[[tool.bumpversion.files]]` in `pyproject.toml`);        |
|                            | then `hatch run gen-graph` to re-stamp `graph.json`.      |
|                            | Full checklist: [CONTRIBUTING.md § Phase 2](../CONTRIBUTING.md#phase-2). |
| **Source/test/spec counts**| README badge + CI coverage report (no manual table)       |
| **New authoritative process doc in `sdd/`** | [CLAUDE.md § Documentation framework](../CLAUDE.md#documentation-framework) |
|                            | (if part of the trio), [CONTRIBUTING.md § Authoritative Document Format](../CONTRIBUTING.md#authoritative-document-format) |
|                            | (Scope subsection within), sibling authority docs         |
|                            | (back-references in their Intent & Scope),                |
|                            | `.claude/skills/*/SKILL.md` foundation lists,             |
|                            | `docs-src/explanation/design/_nav.yml`, and this ripple-check |

---

## Quick reference — "Where do I…?"

| I need to…                               | Go here                                              |
|------------------------------------------|------------------------------------------------------|
| Find out what work is pending            | `sdd/BACKLOG.md` (active), `sdd/BACKLOG-DONE.md` (archive) |
| Understand how a feature should behave   | `sdd/specs/` (NNN-topic.md; IDs use STORE-, S3-, ERR- etc.) |
| Learn why a design decision was made     | `sdd/adrs/`                                          |
| Propose a significant change             | Write an RFC in `sdd/rfcs/` (see [`sdd/templates/rfc-template.md`](templates/rfc-template.md)) |
| Explore feasibility of an idea           | Write a research doc in `sdd/research/`              |
| Record a new design decision             | Add an ADR in `sdd/adrs/`                            |
| Log a bug or improvement idea            | Append to `sdd/BACKLOG.md` (Ideas section)           |
| Document a user-facing change            | `CHANGELOG.md` — under `[Unreleased]` or version     |
| Share a process insight or lesson learned | `DEVELOPMENT_STORY.md`                               |
| Check or update code style conventions   | `sdd/DESIGN.md`                                      |
| Check or update testing quality rules    | `sdd/TESTING.md`                                     |
| Run a stage / live-cloud test / record cassettes | `sdd/TESTING-RUNBOOK.md`                     |
| Check or update doc content quality rules | `sdd/CONTENT-RULES.md`                              |
| Understand the full SDD workflow         | `sdd/000-process.md`                                 |
| Add or update a backend guide            | `docs-src/guides/backends/` + docs nav               |
| Run a quick smoke test                   | `examples/` — pick one and run it                    |
| Verify everything passes                 | `hatch run all` (see `pyproject.toml` for the constituent scripts)             |

---

<a id="github-pr-io-split"></a>
## GitHub PR I/O split

When reading or writing PR data — in the main session **or** inside a forked PR
skill (`/rvw-pr`, `/fix-pr`) — split by direction and tool availability. The
fork-vs-main distinction does **not** change the read tool; the only axis that
does is whether `gh` is on `PATH`. (`/pr` is out of scope here: it gathers
context from local git, not the PR API, and its only GitHub call is the
`create_pull_request` write — already on the MCP write path below.)

| Direction | Tool |
|-----------|------|
| Read PR **content** (diff, changed files, body, state) | `gh` CLI (`gh pr view`, `gh pr diff`, `gh pr view --json …`) **when available**; fall back to MCP `pull_request_read` when `gh` is absent (e.g. claude.ai/code) |
| Read review **feedback with resolution state** (`isResolved`/`isOutdated`) | MCP dual-fetch (`get_review_comments` + `get_comments`), or `gh api graphql` `reviewThreads` — but **not** plain `gh` content reads (`gh pr view`/`gh pr diff`), which omit resolution state |
| **Write** (post review, inline comments) | MCP (`pull_request_review_write`, `add_comment_to_pending_review`) |
| Resolve/unresolve **threads** | MCP where available; `gh api graphql` mutation for the resolve gap |
| Search **local repo code** | `Grep` / `Glob` / `Read` — never Bash, never Python |
| Read **any** PR data via Python | never |

**Why `gh`-preferred for content reads:** quick, skips the MCP round-trip, needs
no approval prompt. **Why MCP for writes:** posts without an approval prompt and
avoids the temp-JSON + `gh api --input` dance the no-pipes/no-redirect hook
forces on CLI writes. Identical in main session and forks.

---

<a id="branch-freshness"></a>
## Branch freshness check

Shared by `/pr` and `/fix-pr`. `<BASE>` is the PR base branch (default
`master`). Run `git fetch origin <BASE>`, then
`git rev-list --count origin/<BASE> ^HEAD`. A non-zero count means the branch is
behind `origin/<BASE>` — **stop and ask the user whether to rebase**. If
approved: `git rebase origin/<BASE>` then immediately
`git push --force-with-lease origin <current-branch>`, so later steps act on the
rebased remote state. Never rebase silently — `--force-with-lease` is
destructive to anyone tracking the branch. (`/fix-pr` fetches review comments
**after** any rebase: line numbers and the `isOutdated` flag triage against
current HEAD.)

---

<a id="pr-validation-gates"></a>
## PR validation gates

Shared by `/pr` (before creating the PR) and `/fix-pr` (before committing
fixes). `<BASE>` is the PR base branch (default `master`). "What validates a
change" is composed from hatch targets, never re-encoded; the mechanical gate
follows the same code-vs-docs split CI uses, so a non-code PR is not billed the
full test/examples/notebooks run CI itself skips for it. Each skill keeps its own
trace step (`/pr` verifies a trace exists, `/fix-pr` updates it).

- **Mechanical gate.** Classify the diff with
  `git diff origin/<BASE>...HEAD --name-only`, then run the matching target. Fix
  failures, re-run until clean.
    - **Touches `src/`, `tests/`, `examples/`, `scripts/`, `pyproject.toml`, or
      `.python-version`** → run `hatch run all`, the full pre-PR superset (its
      constituent scripts are the source of truth in `pyproject.toml`). These
      are the test-bearing and interpreter-defining members of CI's `CODE_PAT`;
      `scripts/` is among them because its guards live under `tests/scripts/`, which
      only the suite runs (a `scripts/`-only diff must still run it). The remaining
      `CODE_PAT` members are generated artefacts (FEATURES, the graph data — drift
      caught by `preflight` on this path) and CI config (workflows, actions —
      validated only by CI, which re-runs itself on those paths).
      `all` uses the no-Docker `test-cov-s1` variant (no 95% floor); that floor is
      deliberately CI/publish-only, so do **not** substitute `test-cov-strict`
      (see [CLAUDE.md § Coverage gate](../CLAUDE.md#coverage-gate)).
    - **No code touched** (docs / specs / skills / pure config only) → run
      `hatch run lint` + `hatch run docs-gate`. `lint` is the gate `/pr` used to
      skip — it holds the code, spec, docs, and trace check scripts (e.g.
      `check_spec_marks`, `check_formal_trace`, `check_no_tracker_refs`);
      `docs-gate` adds the strict mkdocs build, link scan, and tested-versions
      drift check. This skips the test suite, examples, and notebooks — none of
      which a non-code change exercises. The code path reaches these same
      docs / tracker / drift checks through `preflight` + `lint` + `check-links`,
      so the two paths stay equivalent on docs coverage despite composing
      different targets.
- **Local-machine reference gate.** Not covered by either target above. Grep
  changed files for private local-machine references unreachable from the repo,
  per the [ripple-check Local-machine reference row](#pre-work-index) (patterns +
  scope live there). Fix before finishing.
- **Qualitative review.** The `check_*`/`docs-check` scripts in the mechanical
  gate enforce the mechanical rules but not the judgment-based ones. Review the
  changed tests against [`TESTING.md`](TESTING.md) (assertion depth, mock
  discipline) and changed documentation against [`CONTENT-RULES.md`](CONTENT-RULES.md)
  (prose longevity). Report violations before finishing.

---

<a id="local-toolchain"></a>
## Local toolchain

`session-init.sh` auto-installs on Linux+root (claude.ai/code). On-prem: warn only.

| Tool  | Auto-install trigger       | Version | Manual fallback                  |
|-------|----------------------------|---------|----------------------------------|
| hatch | always (if missing)        | latest  | `uv tool install hatch`          |
| dafny | `sdd/formal/*.dfy` present | 4.11.0  | see `session-init.sh` for steps  |

---

## Repository layout

```
src/remote_store/          # Library source (backends, Store, errors, registry)
tests/                     # pytest suite — spec-traced via @pytest.mark.spec("ID")
examples/                  # Core runnable examples (run locally, no credentials)
examples/backends/         # Cloud backend examples (need services + credentials)
sdd/                       # Specs, ADRs, RFCs, research, audits, backlog, design docs
docs-src/tutorial/         # Tutorial pages (Diataxis) — getting-started + examples
docs-src/guides/           # User-facing guides (Diataxis)
docs-src/guides/backends/  # Backend configuration guides
docs-src/reference/api/    # API reference pages (mkdocstrings)
docs-src/explanation/      # Explanation pages (Diataxis)
docs-src/explanation/design/ # Design docs — sdd/ dual files rendered here
docs-src/reference/        # Reference pages, FEATURES.md, migration guide
docs-src/                  # MkDocs Material documentation source (prose + nav)
```

For backlog process, SDD workflow, and `sdd/` subtree details see `sdd/000-process.md`.
