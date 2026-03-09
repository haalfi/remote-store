# Release — Version Bump and Release Checklist

You are managing a version release for the remote-store project. This skill
guides you through the 6-phase release process defined in CONTRIBUTING.md.

The canonical release checklist lives in `CONTRIBUTING.md` § Release. If this
skill drifts from that checklist, CONTRIBUTING.md wins — update this skill.

## Arguments

The user should specify the bump level: `patch`, `minor`, or `major`.
If not provided, ask them. Refer to CONTRIBUTING.md § Versioning for guidance:

| Change type                          | Bump      |
|--------------------------------------|-----------|
| New public API, feature, or backend  | **minor** |
| Bug fix, internal refactor           | **patch** |
| Breaking API change (pre-1.0)        | **minor** |
| CI, docs, metadata-only             | **no bump** |

## Phase 0: Pre-flight

- [ ] Master is clean: `git status` shows no uncommitted changes
- [ ] CI is green on master (lint, typecheck, test 3.10-3.14, examples, docs, package)
- [ ] No open `[~]` items shipping in this release in `sdd/BACKLOG.md` — complete (`[x]`) or defer (`[ ]`)
- [ ] `[Unreleased]` section in CHANGELOG.md is non-empty
- [ ] Decide bump level (patch / minor / major)

## Phase 1: Content freeze

- [ ] CHANGELOG.md `[Unreleased]` is complete — every user-facing change listed with its backlog ID
- [ ] `sdd/BACKLOG.md`: all shipping items marked `[x]` with version (e.g. `(v0.8.0)`)
- [ ] README.md: backends table, installation extras, API table, badges are current
- [ ] Specs vs code: spot-check shipped features match their specs (`pytest -m spec` as proxy)
- [ ] Examples: `hatch run examples` passes; manually review notebooks if API surface changed
- [ ] Guides: new/changed backend guides are accurate
- [ ] DEVELOPMENT_STORY.md: add a section for this release (pre-1.0 only)

## Phase 2: Version bump (on a release branch)

- [ ] Create release branch: `git checkout -b release-vX.Y.Z`
- [ ] CHANGELOG.md: rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add fresh empty `[Unreleased]` above
- [ ] Update `date-released` in `CITATION.cff` to today (`bump-my-version` only updates `version:`, not this field)
- [ ] Tagline consistent: `pyproject.toml` = README.md = `docs-src/index.md` = `mkdocs.yml` = `CITATION.cff`
- [ ] Keywords consistent: `pyproject.toml` = `CITATION.cff`
- [ ] Conda recipe: update `context.version` in `packaging/conda-forge/recipe.yaml` to X.Y.Z
- [ ] `bump-my-version bump patch|minor|major` (modifies version in `pyproject.toml`, `__init__.py`, `CITATION.cff`)
- [ ] Review and commit: `git diff` to verify, then stage `pyproject.toml`, `src/remote_store/__init__.py`, `CITATION.cff`, `CHANGELOG.md`, `packaging/conda-forge/recipe.yaml` and commit as `Release vX.Y.Z`

**Important:** `bump-my-version` modifies files in-place without committing or
tagging. You control the commit and tag lifecycle manually.

## Phase 3: Validate

- [ ] `hatch run all` passes (lint + format-check + typecheck + test-cov + examples)
- [ ] `mkdocs build --strict` passes
- [ ] `python -m build && twine check dist/*` — package builds cleanly
- [ ] `pip install dist/*.whl && python -c "import remote_store; print(remote_store.__version__)"` — version matches
- [ ] Conda recipe: version in `packaging/conda-forge/recipe.yaml` matches release version

## Phase 4: Ship

- [ ] Push branch, open PR, wait for CI green
- [ ] Request PR review — wait for approval before merging
- [ ] Merge PR to master
- [ ] Wait for CI to pass on the merge commit
- [ ] Verify HEAD is the merge commit: `git log --oneline -1`
- [ ] Tag the merge commit: `git tag vX.Y.Z`
- [ ] Push the tag: `git push origin vX.Y.Z`
- [ ] Create GitHub Release from the tag — this triggers both `publish.yml` (PyPI) and versioned docs deploy
- [ ] Watch `publish.yml` — confirm it completes successfully
- [ ] Delete the release branch: `git push origin --delete release-vX.Y.Z`

## Phase 5: Post-release verification

- [ ] PyPI: `pip install remote-store==X.Y.Z` in a fresh venv, verify version and README renders
- [ ] GitHub Pages: check version switcher shows new version as "latest"
- [ ] ReadTheDocs: check https://docs.remotestore.dev/ shows correct version (requires RTD automation rule for tag-based builds)
- [ ] Conda recipe: fetch sha256 from PyPI (`curl -s https://pypi.org/pypi/remote-store/X.Y.Z/json | python -c "import sys,json; d=json.load(sys.stdin); print([f['digests']['sha256'] for f in d['urls'] if f['filename'].endswith('.tar.gz')][0])"`) and update `source.sha256` in `packaging/conda-forge/recipe.yaml`
- [ ] Commit recipe sha256 update via a branch and PR (branch protection requires PRs even for metadata-only changes)
- [ ] Conda-forge: if feedstock exists, verify bot opened a version-bump PR
- [ ] Announce if applicable

## Report

After completing all phases, output a summary:
- New version number
- Files modified
- CHANGELOG entries included
- Any warnings or inconsistencies found

## Important

- The v0.6.0 release missed the CHANGELOG update — that's why Phase 2
  explicitly calls it out.
- The tagline/keywords consistency check exists because PyPI, README, docs,
  and CITATION.cff have drifted in the past. Check all five files.
- `bump-my-version` does NOT commit or tag. You handle that in Phase 2/4.
- Tags go on the **merge commit on master**, not on the release branch.
