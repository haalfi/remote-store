# Audit — Code Quality Review

Systematic audit of a codebase area. Report only — never fix.

## Arguments

`$ARGUMENTS` — free-text describing what to audit (e.g., "extensions package", "error handling in S3 backend"). Ask if missing.

## Step 1: Clarify scope

Before reading any code, confirm with the user:

1. **Target** — which packages / modules / files?
2. **Focus** — bugs, security, spec compliance, performance, consistency, or all?
3. **Depth** — quick scan or thorough line-by-line?

If `$ARGUMENTS` is specific enough to answer all three, state your interpretation and ask for confirmation. Do not proceed until the user confirms.

## Step 2: Audit

Read the target code. For each finding, record:

- **Location** — `file:line`
- **Category** — Bug / Security / Spec / Consistency / Performance
- **Severity** — High / Medium / Low
- **Evidence** — what's wrong and why

## Step 3: Report

Present findings in a summary table, then detail per finding. If nothing found, say so.

```
## Audit: <target> — N findings
| # | Location | Category | Severity | Summary |
|---|----------|----------|----------|---------|
```

## Rules

- **Report only.** Do not fix, refactor, or modify any code.
- **Do not** create backlog items, changelog entries, or commits.
- After the report, ask the user what they want to do next (fix, backlog, audit doc, nothing).
