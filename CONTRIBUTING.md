# Contributing to Remote Store
<!-- doc: dual dest=explanation/contributing.md -->

Scope: contributor workflow, development setup, release process, and consistency checklists for `remote-store`.

This project follows **Spec-Driven Development (SDD)**: every feature starts as a specification before any code is written. See [`sdd/000-process.md`](sdd/000-process.md) for the full methodology.

## Project Principles

The universal working principles for this repo are listed in
[`CLAUDE.md` § Principles](CLAUDE.md#principles). They apply to any contributor,
not only automated agents.

## Documentation framework

See [`CLAUDE.md` § Documentation framework](CLAUDE.md#documentation-framework) for placement, structure, and longevity rules.

<a id="authoritative-document-format"></a>
## Authoritative Document Format

Internal process and reference documents follow a fixed structure.

### Principle

Meaningful minimum. Each document covers one concern, states clear principles, and stops. No detailed instructions for every situation.

### Structure

1. **Intent & Scope**: What this document governs and who it is for. Max 5–10 lines. A reader must know: "this is THE source for topic X."
2. **Rules**: Numbered, mandatory constraints.
3. **Guides** *(optional)*: Heuristics, examples, lookup tables. Useful but not binding.

Sections 1 and 2 alone must be sufficient to understand the document's purpose and obligations.

### Scope

Applies to root-level process documents in `sdd/` ([`000-process.md`](sdd/000-process.md), [`AUTHORING.md`](sdd/AUTHORING.md), [`CI-OPERATIONS.md`](sdd/CI-OPERATIONS.md), [`DESIGN.md`](sdd/DESIGN.md), [`DOCUMENTATION.md`](sdd/DOCUMENTATION.md), [`TESTING.md`](sdd/TESTING.md), [`CONTENT-RULES.md`](sdd/CONTENT-RULES.md), [`CLAUDE-REFERENCE.md`](sdd/CLAUDE-REFERENCE.md)). Does not apply to specs, ADRs, RFCs, research, audits, [`BACKLOG.md`](sdd/BACKLOG.md), [`README`](README.md), [`CHANGELOG`](CHANGELOG.md), [`DEVELOPMENT_STORY`](DEVELOPMENT_STORY.md), [`CLAUDE.md`](CLAUDE.md), or [`CONTRIBUTING.md`](CONTRIBUTING.md) (which follow their own formats).

### Cross-check

Every sentence and section must pass this test: *"this would force different behavior in situation X."* If it does not, it is decoration — rewrite as a rule or remove.

### Exclusions

Authoritative documents must not contain:

1. Explanation or rationale (put in ADRs, specs, research docs, or `DEVELOPMENT_STORY.md`)
2. History or changelog-style notes
3. Meta-commentary about the document itself

## Spec-First Workflow

The full SDD pipeline is described in [`sdd/000-process.md`](sdd/000-process.md). For external contributions, start here:

1. **Propose**: Open a PR with an RFC in `sdd/rfcs/` (see [`rfc-template.md`](sdd/templates/rfc-template.md)). No code yet.
2. **Review**: Maintainers and community review for design fit and completeness.
3. **Accept**: The RFC graduates to a spec in `sdd/specs/`. It now defines the contract.
4. **Implement**: Open a follow-up PR with tests (referencing spec IDs) and implementation.

## Bug Fixes

Bug fixes follow a strict pipeline: BACKLOG → CHANGELOG → failing TEST → FIX →
COMMIT together. See [`sdd/000-process.md` § Rule 6](sdd/000-process.md#workflows) for
the canonical rule.

## Repository Structure

```text
sdd/
  000-process.md              # How specs work in this repo
  specs/                      # Accepted specifications (source of truth)
  adrs/                       # Architecture Decision Records
  rfcs/                       # Proposals under discussion
```

Browse `sdd/specs/` for the full list of specifications. Each spec file is
numbered and named after the feature it describes (e.g. `008-s3-backend.md`).

For spec format and ID prefixes, see [`sdd/000-process.md` § Spec format](sdd/000-process.md#spec-format).

<a id="adding-a-new-backend"></a>
## Adding a New Backend

See [Build Your Own Backend](docs-src/guides/custom-backend-guide.md) for a full
walkthrough of the `Backend` contract, error mapping, and capabilities.

1. Write a spec in `sdd/specs/` or as an addendum in `sdd/specs/backends/<name>.md`
2. Implement `Backend` ABC in `src/remote_store/backends/_<name>.py`
3. Register a fixture in `tests/backends/fixtures/` (declare it in `backends.toml` / `fixtures.toml` and add a per-fixture factory module)
4. The cross-backend conformance suite under `tests/backends/conformance/` (spec-traced per-topic files: `test_io.py`, `test_listing.py`, `test_atomic.py`, …) runs automatically against the new fixture; Dafny-derived cases carry `@pytest.mark.extended_conformance` and are validated by a Dafny-compiled oracle — see [`sdd/formal/README.md` § Compiled Oracle](sdd/formal/README.md#compiled-oracle)
5. Add user-facing guide in `docs-src/guides/backends/<name>.md` and add to `docs-src/guides/_nav.yml`
6. Update every backend enumeration — see **Backend order** below for how to find them all and what order they go in
7. Add backend config example to `examples/configuration/configuration.py`
8. If the backend needs an extra, add it to `pyproject.toml` `[project.optional-dependencies]`, and add the same floor to `run_constraints` in `packaging/conda-forge/recipe.yaml`

**Backend order (step 6).** Every enumeration lists backends in one order:

> local (Local, Memory) → cloud (S3, S3-PyArrow, Azure, Graph) → SFTP / SSH →
> special-purpose (HTTP, SQLBlob, SQLQuery)

Insert the new backend into its group; do not append it. Where a table carries
footnote markers, they run in first-appearance order, so re-sequence them when a
new row lands above an existing marker.

**Do not go looking for the enumerations — the gate knows where they are.**
`hatch run check-backend-order` reads every enumeration across the README, the
guides, the API reference, `context7.json`, and the conda recipe, and fails on any
that is out of order. It runs inside `hatch run lint` and `hatch run docs-gate`, so
CI enforces it on every PR. Add the backend, run the gate, fix what it names.

This replaced a `git grep`, and the reason is worth knowing before anyone proposes
another one: a grep for a backend *name* cannot see an enumeration that abbreviates
(one wrote plain `SQL`), and a grep scoped to a *path* cannot see the enumerations
outside it (two live in packaging and repo-root metadata). Both holes were real, and
both hid live defects. If you find yourself about to hand-maintain a list of places
to check, extend `scripts/check_backend_order.py` instead.

The gate proves **order**, not membership. Whether a list *should* name every
backend is a judgement it deliberately does not make: the API reference splits its
sync and async tables on purpose, and the README's comparison row abridges on
purpose. That one is on you and your reviewer.

Two things are deliberately out of scope. `FEATURES.md` is generated between
`BEGIN_GENERATED` markers and sorts alphabetically — never hand-edit it. The
tagline is a slogan rather than an enumeration, so the group order does not apply
to it; it is mirrored across packaging, citation, and docs-metadata files, and
`git grep "Write file storage code once"` is the way to find every copy. Do not
work from a memorised list — the mirrors outnumber the ones anyone remembers, and
the forgotten copies are the ones that go stale.

<a id="adding-an-extension"></a>
## Adding an Extension

Extensions live in `src/remote_store/ext/` and follow the contract in the [extension architecture ADR](sdd/adrs/0008-extension-architecture.md). Full checklist:

1. Write an RFC in `sdd/rfcs/`, get it accepted as a spec in `sdd/specs/`
2. Implement in `src/remote_store/ext/<name>.py` — define `__all__`
3. Use only the public `Store` / `Backend` API (never `_backend`). Use `unwrap()` for native access
4. Do not own Store lifecycle — never call `store.close()` or use `with store:`
5. Let `CapabilityNotSupported` propagate — do not catch and suppress it
6. Add tests in `tests/ext/test_<name>.py` with `@pytest.mark.spec("ID")`
7. Write a user guide in `docs-src/guides/<name>.md`
8. Add the page to `docs-src/guides/_nav.yml` (under the Extensions section)
9. Add a runnable example in `examples/`
10. The example docs page is auto-generated at `tutorial/examples/<slug>.md` from the module docstring via `gen_pages.py` — no manual wrapper file needed
11. If the extension needs an extra, add it to `pyproject.toml` `[project.optional-dependencies]`, and add the same floor to `run_constraints` in `packaging/conda-forge/recipe.yaml` — that block covers *every* extra, backend and extension alike, and a dependency missing from it is silently unconstrained for conda users
12. Update `CHANGELOG.md` and `sdd/BACKLOG.md` (or `sdd/BACKLOG-DONE.md`) in the same commit

### Export patterns

**Pure Python (no extra dependencies)** — export unconditionally from `remote_store.__init__`:

```python
# In remote_store/__init__.py:
from remote_store.ext.<name> import Foo, bar
```

**Optional dependency** — two guards are needed:

1. In the extension module, raise a helpful error if the dependency is missing:

```python
# In ext/<name>.py:
try:
    import some_lib
except ModuleNotFoundError as _exc:
    raise ModuleNotFoundError(
        "some_lib is required for the <name> extension. "
        "Install it with: pip install 'remote-store[<name>]'"
    ) from _exc
```

2. In `remote_store/__init__.py`, conditionally re-export with a silent guard:

```python
try:
    from remote_store.ext.<name> import Foo, bar
    __all__ += ["Foo", "bar"]
except ImportError:
    pass
```

Add the optional dependency as an extra in `pyproject.toml [project.optional-dependencies]`.

## Third-Party Extensions

External packages should use the naming convention `remote-store-<name>` and:

- Use only the public `Store` / `Backend` API
- Use `register_backend()` for backend registration (if applicable)
- Use `unwrap()` for native handle access
- For backend extensions: reuse the conformance test suite by importing and parameterizing it

## Development Setup

The repo pins its priority interpreter in `.python-version` (the version CI's
coverage lane runs on), so `uv` and `pyenv` select it automatically and your
local `hatch run all` reproduces what CI gates on. It is the single source for
the priority Python across CI: workflows that need it read it (`setup-python`'s
`python-version-file`, or `ci.yml`'s `setup` job for the matrix), so bumping the
development version is a one-line edit there. (The full-matrix `ci-full.yml`
backstop runs *every* supported interpreter, not the priority one, from a list
kept equal to `ci.yml`'s `ALL_PYTHONS` by `scripts/check_ci_full_matrix.py`.)

The default hatch env is configured with `path = ".venv"`, so `hatch run`
creates and owns `.venv/` at the repo root via uv. A separate
`python -m venv` or `pip install -e ".[dev]"` step duplicates the env that
`hatch run` would build, and a stdlib-built `.venv` may not match the shape
hatch expects.

```bash
# Clone and enter the repo
git clone https://github.com/haalfi/remote-store.git
cd remote-store

# Install hatch (skip if you already have it). Any of these work:
uv tool install hatch    # recommended if you use uv
pipx install hatch
pip install --user hatch

# Run any hatch script — .venv/ is auto-built on first invocation:
hatch run all    # or run individual steps:
hatch run lint
hatch run typecheck
hatch run test-cov         # coverage variants — see pyproject.toml comments for which to use when
hatch run examples
```

All dev scripts are defined in `pyproject.toml` under `[tool.hatch.envs.default.scripts]`. Run `hatch run` to see available commands.

### Bundling a code skeleton for an LLM (optional)

To orient a coding agent on a subtree without spending tokens on full bodies,
[`lx`](https://github.com/rasros/lx) (Go, MIT) emits an AST-level skeleton —
class/method signatures, type fields, and docstrings only. For
`src/remote_store/` that is ~80k tokens versus ~265k for the full source, and
there is no concise `git archive` / `cat` equivalent. This is the one job `lx`
does that is awkward to reproduce by hand; for whole-file context just let the
agent read the files. As a contributor's skeleton tool `lx` is a purely local
convenience: **not** a project dependency and **not** installed by any `hatch`
script. (Separately, the Read the Docs build fetches a pinned `lx` binary to
generate the published `llms-api.txt` API skeleton — see `.readthedocs.yaml`;
that is an automated publish step, not part of local development.)

```bash
go install github.com/rasros/lx/cmd/lx@latest          # one-time

lx --xml -u -Y src/remote_store/   # skeleton: signatures + types only
git diff --name-only | lx -c       # bundle just the changed files to the clipboard
```

It honours `.gitignore` and estimates tokens. Point it at a subtree, not the
repo root (a whole-repo walk is ~3.7M tokens, mostly `tests/` and `sdd/`); no
`.lxignore` is committed, so use `-e <glob>` for ad-hoc excludes.

> **Fixed in `lx` v1.2.2 (affected `lx` ≤ v1.2.1).** Earlier releases could
> silently drop the `class` header of decorated dataclasses from the `-u -Y`
> skeleton. On `src/remote_store/_models.py`, `lx` v1.2.1 dropped 4 of the 5
> public data-model classes (`FileInfo`, `WriteResult`, `FolderEntry`,
> `FolderInfo`), orphaning their fields under `ContentDigest` and losing some
> fields entirely; the output still looked like valid Python, so the loss was
> easy to miss. `lx` v1.2.2 fixes it: re-running `lx --xml -u -Y
> src/remote_store/` now emits every public class with its fields (0 public
> classes dropped across the whole subtree). **Upgrade to ≥ v1.2.2**
> (`go install github.com/rasros/lx/cmd/lx@latest`); on `lx` ≤ v1.2.1 only, work
> around it by bundling the data models as full source
> (`lx --xml src/remote_store/_models.py`, ~1.7k tokens). Full-source and
> changed-file bundles were never affected. Upstream report:
> [rasros/lx#76](https://github.com/rasros/lx/issues/76).
>
> The `-u -Y` skeleton shows the **public** API only: `lx` intentionally omits
> leading-underscore (`_Foo`) classes and functions, so private helpers will not
> appear — expected, not the bug above.

### Migrating an existing checkout

If you previously created `.venv/` with `python -m venv` or via IDE
auto-discovery, delete it before the first `hatch run`. Hatch's behaviour
on a pre-existing non-uv venv is not guaranteed (it may reuse, rebuild, or
fail depending on what metadata it finds), and a reused stdlib venv will
be missing the `dev` / `docs` / `bench` feature installs.

On Windows, close any IDE / language server / running pytest that has
file handles inside `.venv\` before deleting — otherwise the delete fails
with WinError 32 (file in use).

```bash
rm -rf .venv                       # Linux / macOS
Remove-Item -Recurse -Force .venv  # PowerShell
```

## Commit Signing

All commits should be signed for supply chain transparency. GitHub Vigilant
Mode is enabled on the repository — unsigned commits show as "Unverified".

### Setup (SSH signing, one-time)

```bash
# Tell Git to use SSH for signing
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/<your-key>.pub
git config --global commit.gpgSign true
git config --global tag.gpgSign true
```

Then upload your public key to GitHub as a **Signing Key** (not Authentication):
Settings > SSH and GPG keys > New SSH key > Key type: **Signing Key**.

### SSH agent (avoid passphrase prompts)

If your key has a passphrase, start the SSH agent so signing happens silently:

```bash
eval $(ssh-agent -s)
ssh-add ~/.ssh/<your-key>
```

On Windows, you can also enable the OpenSSH Authentication Agent service
(via `Set-Service ssh-agent -StartupType Automatic` in an elevated PowerShell)
for persistence across sessions.

Verify with `echo "test" | git commit-tree HEAD^{tree} -S` — a commit hash without passphrase prompt means signing works.

### Verify signatures locally (one-time)

Producing signatures and *verifying* them locally are separate steps. Without an
allowed-signers file, `git log --show-signature` (and `%G?`) reports `N` for your
own SSH-signed commits — they are signed, but Git has nothing to verify against.
To make local verification resolve to `G`:

```bash
echo "$(git config user.email) $(cat ~/.ssh/<your-key>.pub)" >> ~/.ssh/allowed_signers
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

This is purely local; GitHub verifies independently regardless. Note: commits
merged via GitHub's squash button are re-signed with GitHub's own key and show
`E` locally ("no public key") — that is expected, not a failure.

## Code Style

See [`sdd/DESIGN.md`](sdd/DESIGN.md) for the full code style conventions.

- **Formatter/linter:** ruff (line-length 120)
- **Type checking:** mypy strict mode
- **Tests:** pytest with `@pytest.mark.spec("ID")` markers for spec traceability
- **Coverage:** Target >= 95%

## Test Requirements

See [`sdd/TESTING-RUNBOOK.md`](sdd/TESTING-RUNBOOK.md) for how to run the test
stages, invoke live-cloud tests, and record or refresh cassettes. See
[`sdd/TESTING.md`](sdd/TESTING.md) for testing quality rules. Spec
traceability and test-per-spec obligations are in
[`sdd/000-process.md` § Rules](sdd/000-process.md#rules) (Rules 1–2 cover spec-test traceability).

- Run `pytest -m spec` to verify all spec-derived tests pass
- Run `pytest --cov=remote_store` for coverage reports

Tests gated on `RS_TEST_LIVE_HNS=1` require a real Azure Data Lake Storage
Gen2 account. See [Azure HNS account setup](docs-src/guides/backends/azure-hns-setup.md)
for the provisioning recipe.

Tests gated on `RS_TEST_LIVE_S3=1` require a real AWS S3 account. See the
"Required IAM permissions" section in
`tests/backends/fixtures/s3_live.py` for the IAM policy needed by the
test user.

## Examples and Notebooks

The `examples/` directory contains runnable Python scripts that are validated in CI. Example scripts must remain self-contained and use `tempfile.TemporaryDirectory` for cleanup.

Jupyter notebooks in `examples/notebooks/` are validated in CI via
`hatch run notebooks` (code cells executed with `exec()`, no Jupyter needed).
Visual output is not checked — the runner validates that cells execute without
errors.

## Dependency drift guard

The drift guard is one of the scheduled/automated CI guards; for the full
inventory of those guards, where each one's finding lands, and the durable-TODO
principle they follow, see [`sdd/CI-OPERATIONS.md`](sdd/CI-OPERATIONS.md).

Every `[<extra>]` in `pyproject.toml` declares a floor, and a ceiling only
where a known-incompatible major looms — see the comment on
`[project.optional-dependencies]` in `pyproject.toml` for the authoritative
per-extra ranges. `.github/workflows/drift-guard.yml` runs weekly (Monday 07:00 UTC):
it re-resolves each `remote-store[<extra>]` with `pip install --upgrade --pre`,
diffs against the committed baselines in `infra/drift-locks/`, runs the
smoke targets in `scripts/drift_smoke_map.py` for any extra that drifted,
and reconciles a single rolling GitHub issue. The workflow never edits
`pyproject.toml` and never opens a pin-update PR — it is early warning,
not automated remediation.

When you deliberately bump a floor (e.g. `paramiko>=3.0` after a
known-breaking upstream release), refresh the baseline in the same PR:

```
hatch run drift-check refresh-baseline <extra>     # regenerate the lock
hatch run drift-check render-docs                  # regenerate the docs page
```

Then commit `infra/drift-locks/<extra>.txt` and
`docs-src/reference/tested-versions.md`. Run on Python 3.13 (matching the
workflow's runner) so the lock is comparable.

`hatch run drift-check refresh-baseline all` refreshes every extra at once.

<a id="versioning"></a>
## Versioning

This project follows [Semantic Versioning](https://semver.org/). Pre-1.0, minor bumps may contain breaking changes. The public API surface is everything in `remote_store.__init__.__all__`.

### When to bump

| Change type | Bump | Examples |
|-------------|------|----------|
| New public API, feature, or backend | **minor** (`0.X.0`) | `Store.to_key()`, new backend, new config loader |
| Bug fix, internal refactor | **patch** (`0.0.X`) | Fix round-trip bug, update retry logic |
| Breaking API change (pre-1.0) | **minor** (`0.X.0`) | Remove method, rename parameter |
| Breaking API change (post-1.0) | **major** (`X.0.0`) | — |
| CI, docs, metadata-only | **no bump** | Add classifier, update README |

### Stability tiers

| Label | Meaning |
|-------|---------|
| **Alpha** (pre-0.11) | API may change freely between releases |
| **Beta** (0.11+) | Core API (`Store`, `Registry`, `Backend`, models, errors) is stable. Breaking changes are documented in CHANGELOG and avoid gratuitous churn. Extensions (`ext.*`) may evolve more freely. |
| **Stable** (1.0+) | Full SemVer: breaking changes require a major bump |

### How to bump

Version is managed with [`bump-my-version`](https://github.com/callowayproject/bump-my-version). It modifies the files listed in `[[tool.bumpversion.files]]` in `pyproject.toml` in-place without committing or tagging. The release checklist below handles the commit and tag lifecycle.

Quick reference for the command syntax:

```bash
bump-my-version bump patch   # 0.4.1 → 0.4.2
bump-my-version bump minor   # 0.4.1 → 0.5.0
bump-my-version bump major   # 0.4.1 → 1.0.0
```

## Consistency Checklists

Documentation, examples, and metadata live in many places. Use these to keep them in sync.

- **New backend**: see [§ Adding a New Backend](#adding-a-new-backend) above.
- **New extension**: see [§ Adding an Extension](#adding-an-extension) above (12-step checklist).
- **New Store method / cross-reference validation**: see the ripple-check table in `sdd/CLAUDE-REFERENCE.md`.
- **Pre-PR validation**: run the [PR validation gates](sdd/CLAUDE-REFERENCE.md#pr-validation-gates) — `hatch run all` for a code change, or the lighter `hatch run lint` + `hatch run docs-gate` for a docs/specs-only change — then verify CHANGELOG and BACKLOG are updated and check the ripple-check table in `sdd/CLAUDE-REFERENCE.md`. Running `hatch run all` is always a safe superset if you would rather not classify the diff.

<a id="release"></a>
## Release

### Phase 0: Pre-flight

- [ ] Master is clean: `git status` shows no uncommitted changes
- [ ] CI is green on master: `ci.yml` (lint, typecheck, the tiered test jobs, examples, docs, package) **and** the `ci-full.yml` full live-backend matrix on every supported interpreter — the full live-backend guarantee runs in `ci-full.yml`, not `ci.yml`
- [ ] `hatch run all` passes **locally** (constituent scripts in `pyproject.toml`; the pre-commit gate variant deliberately does not enforce the 95% floor — CI does)
- [ ] No open `[~]` items shipping in this release in `sdd/BACKLOG.md` — complete and move to `BACKLOG-DONE.md`, or defer (`[ ]`)
- [ ] `[Unreleased]` section in CHANGELOG.md is non-empty
- [ ] Decide bump level (patch / minor / major) per the table above

### Phase 1: Content freeze

- [ ] CHANGELOG.md `[Unreleased]` is complete — every completed item has a stub line (see ripple-check row **CHANGELOG entry**)
- [ ] CHANGELOG completeness cross-check: `gh api repos/haalfi/remote-store/releases/generate-notes -f tag_name=vX.Y.Z -f previous_tag_name=vPREV -f target_commitish=master --jq .body` lists every merged PR since `vPREV` — confirm each **user-facing** PR maps to a CHANGELOG `[Unreleased]` entry (internal/tooling/dependabot PRs need none). Safety net over the per-PR CHANGELOG discipline; the generated text is **discarded**, not used for the release body (which stays CHANGELOG-derived — Phase 4)
- [ ] CHANGELOG.md `[Unreleased]` condensed — stubs expanded to prose at release time (release skill Phase 1)
- [ ] `sdd/BACKLOG-DONE.md`: all shipping items moved here under the `## Unreleased` heading, each marked `[x]` (Phase 2 versions the heading)
- [ ] `FEATURES.md` updated for this release: backends, extensions, capabilities, extras — this is the only time FEATURES.md is edited (do NOT update the version header; `bump-my-version` handles it in Phase 2)
- [ ] README.md: backends table, installation extras, API table, badges are current
- [ ] Specs vs code: spot-check shipped features match their specs (`pytest -m spec` as proxy)
- [ ] Examples: `hatch run examples` passes; manually review notebooks if API surface changed
- [ ] Guides: new/changed backend guides are accurate
- [ ] DEVELOPMENT_STORY.md: add a section for this release (pre-1.0 only)

<a id="phase-2"></a>
### Phase 2: Version bump (on a release branch)

- [ ] Create release branch: `git checkout -b release-vX.Y.Z`
- [ ] CHANGELOG.md: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add fresh empty `[Unreleased]` above
- [ ] `sdd/BACKLOG-DONE.md`: rename `## Unreleased` to `## vX.Y.Z`, add a fresh empty `## Unreleased` (`*(none)*`) above
- [ ] Update `date-released` in `CITATION.cff` to today (bump-my-version only updates `version:`, not this field)
- [ ] Tagline consistent across every mirror: `git grep "Write file storage code once"` — check them all, do not work from a remembered list; the copies nobody lists are the copies that go stale. Historical quotes in `sdd/research/` are the one exemption
- [ ] Keywords consistent: `pyproject.toml` = `CITATION.cff`
- [ ] Conda recipe: update `context.version` in `packaging/conda-forge/recipe.yaml` to X.Y.Z
- [ ] `bump-my-version bump patch|minor|major --allow-dirty` (modifies the files listed in `[[tool.bumpversion.files]]` in `pyproject.toml` — does NOT commit or tag; `--allow-dirty` is required because the Phase 1/2 edits above are still uncommitted)
- [ ] `hatch run gen-graph` (stamps `source_version` + `snapshot` in `docs-src/_data/graph/graph.json` from the bumped version)
- [ ] `hatch run gen-features` (regenerates mechanical sections of `FEATURES.md` from updated `graph.json`)
- [ ] `hatch run gen-graph-viz` (regenerates `docs-src/explanation/graph_viz.html` from `graph.json`; `hatch run all` gates on its freshness, so skipping it fails Phase 3)
- [ ] Review and commit: `git diff` to verify nothing unexpected, then `git add -A` and commit as `Release vX.Y.Z`

### Phase 3: Validate

- [ ] `hatch run all` passes (constituent scripts in `pyproject.toml`)
- [ ] `hatch run test-cov-strict` passes locally with Azurite running (enforces the 95% floor that `hatch run all` deliberately skips)
- [ ] `mkdocs build --strict` passes
- [ ] `hatch build && hatch run twine check dist/*` — package builds cleanly (not `python -m build`: `build` is not in the hatch env)
- [ ] `pip install dist/*.whl && python -c "import remote_store; print(remote_store.__version__)"` — version matches
- [ ] Conda recipe: version in `packaging/conda-forge/recipe.yaml` matches release version

### Phase 4: Ship

_Automated by skill agent (`/release`). User role: review and merge PR only._

- [ ] **[Agent]** Push release branch to origin
- [ ] **[Agent]** Create PR with link to checklist
- [ ] **[User]** Review, approve, and merge PR to master — then notify agent
- [ ] **[Agent]** Confirm CI green on merge commit — including the Codecov upload from the `coverage-gate` job (the badge reuses this run; `publish.yml` no longer recomputes coverage)
- [ ] **[Agent]** Create GitHub Release directly on GitHub using template (no local tags) — this triggers `publish.yml` (PyPI) and versioned docs deploy
- [ ] **[Agent]** Watch `publish.yml` — confirm it completes successfully (PyPI publish)
- [ ] **[Agent]** Delete the release branch

_Release template: title = version, description = "What's Changed" header with condensed sections (Added, Fixed, Internal), two links (CHANGELOG.md + git version diff). See `.claude/skills/release/SKILL.md` § Phase 4 for full template._

### Phase 5: Post-release verification

- [ ] PyPI: `pip install remote-store==X.Y.Z` in a fresh venv, verify version and README renders on pypi.org
- [ ] GitHub Pages: check version switcher shows new version as "latest"
- [ ] ReadTheDocs: check https://docs.remotestore.dev/stable/ shows the new version (RTD automation rule activates tag-based builds; `stable` is the default version)
- [ ] Conda recipe: fetch sha256 from PyPI (`curl -s https://pypi.org/pypi/remote-store/X.Y.Z/json | python -c "import sys,json; d=json.load(sys.stdin); print([f['digests']['sha256'] for f in d['urls'] if f['filename'].endswith('.tar.gz')][0])"`) and update `source.sha256` in `packaging/conda-forge/recipe.yaml`
- [ ] Commit `packaging/conda-forge/recipe.yaml` sha256 update in this repo via a branch and PR
- [ ] **Until conda-forge/staged-recipes PR #32401 is merged:** update `haalfi/staged-recipes`
      branch `add-remote-store` via a local clone (not the GitHub API — API commits are
      unverified); push with `--force-with-lease` and post a bump comment on
      conda-forge/staged-recipes PR #32401 mentioning `@conda-forge/help-python`
- [ ] **After feedstock exists:** verify bot opened a version-bump PR
- [ ] Announce if applicable (tracking issues, users)
