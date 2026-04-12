---
name: audit
description: Systematic code quality audit. Report only — never fix.
disable-model-invocation: true
argument-hint: "[scope]"
---

## Arguments

`$ARGUMENTS` — what to audit (e.g., "extensions package", "error handling in S3 backend", "test coverage for Azure", "docs accuracy for SFTP guide"). Ask if missing.

## Step 1: Clarify scope

Confirm with the user: **target** (which files — code, tests, docs, specs, any project files), **focus** (bugs/security/spec/performance/consistency/docs-accuracy/all), **depth** (quick scan or line-by-line). If `$ARGUMENTS` answers all three, state your interpretation and ask for confirmation.

## Step 2: Audit

Read the target files. For each finding record: `file:line`, category (Bug/Security/Spec/Consistency/Performance/Docs), severity (High/Medium/Low), evidence.

**`Docs` findings:** apply `sdd/CONTENT-RULES.md`; cite the rule number in the evidence.

## Step 3: Report

```
## Audit: <target> — N findings
| # | Location | Category | Severity | Summary |
|---|----------|----------|----------|---------|
```

## Rules

- **Report only.** Do not fix, refactor, or modify any code or project files.
- After the report, ask the user what they want to do next.
