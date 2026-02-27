# PR Preflight — Pre-Submission Validation

You are performing a pre-submission validation before creating or updating a
pull request. This skill checks that all PR requirements are met, catching
the issues that have historically slipped through.

## Instructions

Run all checks below and report results. Do NOT skip any check.

### Check 1: Tests pass

Run `hatch run test` and confirm all tests pass. If tests fail, report the
failures and stop — do not proceed with a failing test suite.

### Check 2: Lint and format

Run `hatch run lint` and confirm no issues. If there are lint errors, fix
them before proceeding.

### Check 3: Type checking

Run `hatch run typecheck` and confirm no errors. mypy strict mode must pass
on `src/`.

### Check 4: CHANGELOG updated

If any files in `src/` were modified (check with `git diff --name-only` against
the base branch), verify that `CHANGELOG.md` has a corresponding entry in the
`[Unreleased]` section.

**This check exists because 62% of code changes in this repo's history skipped
CHANGELOG updates.** Be strict about this.

Exceptions (no CHANGELOG needed):
- CI-only changes (`.github/`)
- Dev tooling changes (`pyproject.toml` scripts only)
- Test-only changes with no user-visible behavior change

### Check 5: BACKLOG.md updated

If any commit message references a backlog ID (AF-NNN, BK-NNN, BL-NNN, ID-NNN),
verify that `sdd/BACKLOG.md` was updated in the same PR to reflect the new status.

**This check exists because 7/9 backlog-tagged commits forgot to update the
backlog.** Check every referenced ID.

### Check 6: Spec traceability

If new test files or test classes were added, verify they include
`@pytest.mark.spec("ID")` markers. If new code was added that implements a
spec section, verify a test exists for that section.

Search for orphaned spec references:
```
grep -r '@pytest.mark.spec' tests/ | sort
```

### Check 7: Examples still work

If the public API changed (check `src/remote_store/__init__.py` diff), run
`hatch run examples` to verify example scripts still work.

### Check 8: Docs build

If any docs, guides, or navigation files changed, run `mkdocs build --strict`
to verify the docs build cleanly.

### Check 9: Ripple check

Run the equivalent of `/ripple-check` — for each modified file category,
verify cross-references are consistent. Focus especially on:
- Backend changes → README table, registry, guides, pyproject.toml
- Error changes → all backends' error mapping
- Version changes → all 3 version-bearing files + CITATION.cff

## Output Format

```
## PR Preflight Results

| Check                  | Status | Notes                        |
|------------------------|--------|------------------------------|
| Tests pass             | PASS/FAIL | ...                       |
| Lint and format        | PASS/FAIL | ...                       |
| Type checking          | PASS/FAIL | ...                       |
| CHANGELOG updated      | PASS/FAIL/N/A | ...                   |
| BACKLOG.md updated     | PASS/FAIL/N/A | ...                   |
| Spec traceability      | PASS/WARN | ...                       |
| Examples work          | PASS/SKIP | ...                       |
| Docs build             | PASS/SKIP | ...                       |
| Ripple check           | PASS/WARN | ...                       |

### Action items
- [ ] ...
```

## Important

- A FAIL on checks 1-3 is a hard blocker — do not submit the PR.
- A FAIL on checks 4-5 means the PR violates project principles — fix before
  submitting unless there's an explicit reason documented.
- WARN on checks 6-9 should be reviewed but may be acceptable with justification.
- This checklist mirrors `.github/PULL_REQUEST_TEMPLATE.md` but goes deeper.
