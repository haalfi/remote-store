---
name: orchestrate
description: Multi-agent orchestration — delegates to domain experts for complex tasks
disable-model-invocation: true
argument-hint: "[BACKLOG-ID] [optional: task description]"
---

Orchestrate a complex task by delegating to 4 domain experts in parallel.
See ADR-0019 for architecture rationale.

Parse `$ARGUMENTS`: first token is the backlog ID (e.g., `BK-123`, `ID-120`),
remainder is optional task description. Ask if missing.

## Step 1: Pre-check

1. Read `sdd/BACKLOG.md` — confirm item exists, note description and dependencies
2. Read linked specs and RFCs from the backlog entry
3. Read `sdd/CLAUDE-REFERENCE.md` § ripple-check table — identify triggered rows
4. Create feature branch: `git checkout -b <id>-<short-name>`

## Step 2: Plan architecture

Before spawning experts, decide and document:
- Class/function names, method signatures, file paths
- Spec IDs that each expert will implement or reference
- Which mode applies (see activation rules below)

This upfront plan lets experts work in parallel without conflicts. Share it
with each expert in their task prompt.

### Expert activation rules

**Code change (feature, refactor, bug fix):** All 4 experts activate.
Each evaluates from their domain — even if their files aren't directly touched.
For bug fixes scope is narrower, but every expert still evaluates.

**SDD-only change (spec/RFC/ADR/process):** All 4 experts **review** (not
implement) from their domain perspective.

## Step 3: Spawn experts

Spawn all needed experts in a **single message with multiple Agent tool calls**
so they run in parallel. Each expert gets the architecture plan from Step 2
plus their domain-specific prompt below.

### Store & Backend Expert

```
You are the Store & Backend expert for remote-store.

DOMAIN: src/remote_store/ and src/remote_store/backends/

FOUNDATION — read before writing:
- sdd/DESIGN.md (code conventions)
- Any specs and ADRs relevant to the task (orchestrator will list them,
  but read additional ones you discover are needed)

TASK: [orchestrator fills this from Step 2]

CONSTRAINTS:
- Specs are source of truth. Code contradicts spec → code is wrong.
- Follow Backend ABC contract, error mapping patterns, capabilities.
- Use existing backends as reference implementations.
- Only create/modify files under src/remote_store/.

OUTPUT: files created/modified, spec IDs implemented, issues found.
```

### Extension Expert

```
You are the Extension expert for remote-store.

DOMAIN: src/remote_store/ext/

FOUNDATION — read before writing:
- sdd/DESIGN.md (code conventions)
- sdd/adrs/0008-extension-architecture.md (if it exists)
- Any specs and ADRs relevant to the task

TASK: [orchestrator fills this — always includes: "Evaluate whether this
change impacts existing extensions. If breaking or behavior-changing,
adapt affected extensions."]

CONSTRAINTS:
- Follow ADR-0008 extension pattern.
- Lazy imports for optional dependencies.
- Even if no ext/ files change, report your impact assessment.

OUTPUT: impact assessment, files created/modified (if any), issues found.
```

### Testing Expert

```
You are the Testing expert for remote-store.

DOMAIN: tests/

FOUNDATION — read before writing:
- sdd/TESTING.md (8 quality rules — mandatory)
- sdd/DESIGN.md § 11 (test style — class grouping, spec markers)
- The task-specific spec (for spec IDs to trace)

TASK: [orchestrator fills this]

CONSTRAINTS:
- Every test gets @pytest.mark.spec("ID") tracing.
- MagicMock always with spec= (Rule 4).
- Prefer MemoryBackend over mocks (Rule 6).
- Failure-path tests required for public API methods (Rule 1).
- 95% coverage target.
- Parametrize 3+ similar test shapes (Rule 7).

OUTPUT: files created/modified, spec IDs covered, coverage impact.
```

### Documentation Expert

```
You are the Documentation expert for remote-store.

DOMAIN: docs-src/, examples/, guides/, docstrings in source files,
README.md, CHANGELOG.md

FOUNDATION — read before writing:
- sdd/DOCUMENTATION.md (Diataxis, content homes, cross-linking)
- sdd/DESIGN.md § 4 (docstring format)
- The task-specific spec

TASK: [orchestrator fills this — always includes: "Evaluate whether
behavior changes, guides, examples, troubleshooting, or API docs
need updating."]

CONSTRAINTS:
- Diataxis placement: tutorials, how-to, reference, explanation.
- Cross-link requirements (API ref ↔ guides ↔ examples).
- Update nav files (_nav.yml) if adding pages.
- Docstring completeness per DESIGN.md symbol type table.
- Even if no doc changes needed, report your assessment.

OUTPUT: assessment, files created/modified (if any), nav changes.
```

## Step 4: Post-process

After all experts complete:

1. **Ripple-check audit**: Walk `sdd/CLAUDE-REFERENCE.md` table. For each
   triggered row, verify target files were updated. Fix gaps directly.
2. **CHANGELOG**: Add entry under `[Unreleased]` with backlog ID.
3. **BACKLOG**: Mark item `[x]` or `[~]`, move completed parts to BACKLOG-DONE.
4. **Validate**: Run `hatch run all`. Fix failures, re-run until clean.

## Step 5: Commit & report

1. Stage all changes, commit with backlog ID prefix.
2. Push feature branch (never master).
3. Report: experts used, files changed, ripple-checks completed, validation status.

## Rules

- Never push to master. Push the feature branch.
- If an expert reports a spec contradiction, **stop and ask the user**.
- If `hatch run all` fails after 2 fix attempts, report the failure and stop.
- Commit message: `<BACKLOG-ID>: <short description>`.
- The orchestrator handles cross-domain files (CHANGELOG, BACKLOG, README tables,
  pyproject.toml extras, nav files). Experts stay in their domain.
