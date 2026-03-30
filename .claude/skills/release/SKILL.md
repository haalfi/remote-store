---
name: release
description: Version bump and release checklist for remote-store
disable-model-invocation: true
argument-hint: "[patch|minor|major]"
---

Canonical checklist: `CONTRIBUTING.md` § Release. If this skill drifts, CONTRIBUTING.md wins.

Bump level: `$ARGUMENTS` (ask if missing). Minor = new API/feature/backend, patch = bugfix/refactor, no bump = CI/docs only.

## Phase 0: Pre-flight

- [ ] Master clean, CI green
- [ ] No shipping `[~]` items in `sdd/BACKLOG.md`
- [ ] `[Unreleased]` in CHANGELOG.md is non-empty

## Phase 1: Content freeze

- [ ] CHANGELOG `[Unreleased]` complete — every user-facing change with backlog ID
- [ ] `sdd/BACKLOG-DONE.md`: shipping items moved, marked `[x]` with version
- [ ] FEATURES.md: version, backends table, extensions table, extras current
- [ ] README: backends table, installation extras, API table, badges current
- [ ] Specs vs code: `pytest -m spec` as proxy
- [ ] `hatch run examples` passes; review notebooks if API changed
- [ ] Guides accurate for new/changed backends
- [ ] DEVELOPMENT_STORY.md section (pre-1.0 only)

## Phase 2: Version bump (release branch)

- [ ] `git checkout -b release-vX.Y.Z`
- [ ] CHANGELOG: rename `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD`, add fresh `[Unreleased]`
- [ ] `date-released` in CITATION.cff → today
- [ ] Tagline consistent: pyproject.toml = README = docs-src/index.md = mkdocs.yml = CITATION.cff
- [ ] Keywords consistent: pyproject.toml = CITATION.cff
- [ ] Conda recipe: `context.version` in `packaging/conda-forge/recipe.yaml` → X.Y.Z
- [ ] `bump-my-version bump patch|minor|major` (modifies pyproject.toml, __init__.py, CITATION.cff — does NOT commit or tag)
- [ ] `git diff`, stage changed files, commit as `Release vX.Y.Z`

## Phase 3: Validate

- [ ] `hatch run all` passes
- [ ] `mkdocs build --strict` passes
- [ ] `python -m build` + `twine check dist/*` clean
- [ ] `pip install dist/*.whl` → version matches
- [ ] Conda recipe version matches

## Phase 4: Ship

- [ ] Push branch, open PR, CI green, get review approval
- [ ] Merge to master, CI green on merge commit
- [ ] Tag **the merge commit**: `git tag vX.Y.Z` → `git push origin vX.Y.Z`
- [ ] Create GitHub Release from tag (triggers publish.yml + docs deploy)
- [ ] Confirm publish.yml succeeds
- [ ] Delete release branch

## Phase 5: Post-release verification

- [ ] PyPI: `pip install remote-store==X.Y.Z` in fresh venv
- [ ] GitHub Pages: version switcher shows new version
- [ ] ReadTheDocs: https://docs.remotestore.dev/ correct version
- [ ] Conda recipe: update sha256 from PyPI, commit via branch+PR
- [ ] Conda-forge feedstock: verify bot PR if applicable
