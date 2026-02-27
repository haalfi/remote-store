# Release — Version Bump and Release Checklist

You are managing a version release for the remote-store project. This skill
guides you through the complete release workflow and validates consistency.

## Arguments

The user should specify the bump level: `patch`, `minor`, or `major`.
If not provided, ask them. Refer to CONTRIBUTING.md § Versioning for guidance:

| Change type                          | Bump      |
|--------------------------------------|-----------|
| New public API, feature, or backend  | **minor** |
| Bug fix, internal refactor           | **patch** |
| Breaking API change (pre-1.0)        | **minor** |
| CI, docs, metadata-only             | **no bump** |

## Release Steps

Execute each step in order. Do NOT skip steps. Check off each one as you go.

### Step 1: Pre-flight checks

- [ ] Confirm the working tree is clean (`git status`)
- [ ] Confirm all tests pass (`hatch run all`)
- [ ] Confirm `CHANGELOG.md` has an `[Unreleased]` section with content
- [ ] Confirm `sdd/BACKLOG.md` has no `[~]` in-progress items for this release

### Step 2: Version bump

Run `bump-my-version bump <level>`. This atomically updates:
- `pyproject.toml` (version field)
- `src/remote_store/__init__.py` (`__version__`)
- `CITATION.cff` (version + date-released)

After the bump, verify all three files show the new version.

### Step 3: CHANGELOG update

- Move the `[Unreleased]` content under a new heading: `## [X.Y.Z] - YYYY-MM-DD`
- Add a fresh empty `## [Unreleased]` section above the new version heading
- Ensure the heading format matches existing entries

### Step 4: Backlog update

- Mark any completed backlog items as `[x]` with `Done: vX.Y.Z: <description>`
- Move fully completed items to the Done section if appropriate
- Ensure no `[~]` items claim to be done when they aren't

### Step 5: Consistency checks

Verify these strings are consistent across files:

**Tagline** (must match across all 5):
- `pyproject.toml` → `description`
- `README.md` → subtitle line
- `docs-src/index.md` → intro paragraph
- `mkdocs.yml` → `site_description`
- `CITATION.cff` → `abstract`

**Keywords** (must match across both):
- `pyproject.toml` → `keywords`
- `CITATION.cff` → `keywords`

**Version** (must match across all 3 — should be automatic from step 2):
- `pyproject.toml` → `version`
- `src/remote_store/__init__.py` → `__version__`
- `CITATION.cff` → `version`

### Step 6: Final validation

- [ ] Run `hatch run all` (lint + typecheck + test-cov + examples)
- [ ] Run `mkdocs build --strict` (docs build)
- [ ] Review the git diff to confirm only expected files changed

### Step 7: Report

Output a summary:
- New version number
- Files modified
- CHANGELOG entries included
- Any warnings or inconsistencies found

## Important

- The v0.6.0 release missed the CHANGELOG update — that's why step 3 exists.
- The tagline consistency check exists because PyPI, README, docs, and CITATION.cff
  have drifted in the past. Check all five files.
- Do NOT create the git tag manually — `bump-my-version` handles that.
