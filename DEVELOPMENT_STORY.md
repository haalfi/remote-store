# How We Built This Package: Human + AI Pair Programming

This document chronicles how `remote-store` was built as a collaboration between a human developer and [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's AI coding assistant. The goal is transparency: showing what worked, what surprised us, and what others can learn from the process.

## The Numbers

| Metric | Value |
|--------|-------|
| Source code | ~1,200 lines |
| Tests | 221 tests, ~1,860 lines |
| Specs & docs | ~1,400 lines |
| Examples | ~350 lines (6 scripts, 3 notebooks) |
| Coverage | 99.3% |
| Calendar time | 1 day of focused work |
| Commits | 13 |

## The Approach: Specs First, Code Second

The project follows **Spec-Driven Development (SDD)** -- every feature starts as a specification before any code is written. This turned out to be an excellent fit for AI-assisted development, because:

1. **Specs constrain the solution space.** Instead of asking "build me a storage library," the human wrote specs that defined exact method signatures, error conditions, and invariants. Claude Code then implemented against those contracts.

2. **Specs are reviewable.** The human could verify correctness at the spec level before any code existed. This caught design issues early, before they became refactoring problems.

3. **Specs enable traceability.** Every test is tagged with `@pytest.mark.spec("ID")`, linking it back to the spec section it validates. This makes it easy to verify completeness.

## The Timeline

### Phase 1: Foundation (human-led)

The human wrote the initial specs, architecture decisions, and project structure:

- 7 specifications covering Store API, Registry, Backend contract, Path model, Error model, Streaming I/O, and Atomic writes
- 3 ADRs documenting key architectural decisions
- RFC workflow for future contributions
- Code style conventions

This was deliberate. **The human defined the "what" and "why"; the AI would handle the "how."**

```
33a6dd2  Initial commit
e2e8ae3  Core files
```

### Phase 2: Implementation (AI-led, human-reviewed)

With specs in hand, Claude Code implemented the entire core in a single session:

- All source modules (`_store.py`, `_registry.py`, `_backend.py`, `_path.py`, `_errors.py`, `_models.py`, `_config.py`, `_capabilities.py`)
- The local filesystem backend as a reference implementation
- Full test suite with spec traceability
- CI pipeline (ruff, mypy, pytest across Python 3.10-3.13)

```
0105d61  Implement M0 scaffolding and M1 core abstractions with local backend
```

The human reviewed the implementation against the specs, checking for correctness, edge cases, and code style alignment.

### Phase 3: Documentation & polish (collaborative)

This is where the collaboration got interesting. The human asked for user-facing documentation, and Claude Code wrote:

- A new README.md (replacing the design spec)
- 6 runnable example scripts
- 3 Jupyter notebooks
- CHANGELOG, CONTRIBUTING updates

```
8a551c8  Add user-facing README, examples, and notebooks
```

### Phase 4: Discovery through dogfooding

While writing examples, Claude Code discovered a real API bug: `Store` couldn't accept an empty string `""` as a path for root-level operations like listing files. The examples exposed what the tests hadn't.

The human's response was characteristic of good pair programming: "yes, fix it, but let's afterwards check all public store methods whether we should check args (and fail) or normalize."

This led to a principled design decision:

- **Folder/query operations** (exists, list_files, list_folders, etc.) accept `""` to mean "the store root"
- **File-targeted operations** (read, write, delete, etc.) reject `""` because an empty path can't identify a file
- `delete_folder("")` is explicitly forbidden because deleting the store root is too destructive to allow by accident

The decision was documented as ADR-0004 and the spec was updated.

```
e9e75be  Allow empty path for folder ops, reject for file ops
cd3529d  Add ADR-0004 and update STORE-002 for empty path semantics
085b269  Update examples to use "" for root listing
```

### Phase 5: Production readiness audit

The human asked: "What is missing to make this a valuable Python package?" Claude Code audited the project against PyPI best practices and produced a prioritized list of 12 items. The human picked which ones to tackle.

Key work:
- **pyproject.toml metadata**: classifiers, keywords, authors, URLs
- **`__repr__`** on Store and Registry for debugging
- **CHANGELOG.md** following Keep a Changelog format
- **Coverage enforcement**: 53 new tests, coverage from 89% to 99%, `--cov-fail-under=95` in CI
- **Cross-platform fix**: `delete_folder` on Windows with non-English locales was using string matching on error messages ("not empty"), which failed in German. Fixed by checking `errno` codes instead.
- **Makefile** with common dev commands
- **Dev setup docs** in CONTRIBUTING.md

```
d56dc18  Polish package for release: metadata, repr, coverage, changelog
66c540a  Add Makefile and dev setup docs to CONTRIBUTING.md
```

## What Worked Well

### Specs as a shared contract

The specs gave both human and AI a shared, unambiguous definition of "done." When Claude Code implemented a method, the human could check it against the spec rather than forming expectations on the fly. This reduced review time and increased trust.

### AI excels at breadth tasks

Tasks like "write 53 tests to cover all uncovered code paths" or "create 6 example scripts demonstrating different API patterns" are tedious for humans but well-suited to AI. Claude Code could read the coverage report, identify gaps, and write targeted tests -- all in a single pass.

### Plan mode for alignment

Before large tasks, Claude Code entered "plan mode" -- proposing a detailed plan (files to create, structure, approach) for the human to review before any code was written. This prevented wasted work. The examples/notebooks plan, for instance, was reviewed and approved before a single file was created.

### Discovery through implementation

The empty path bug was found because writing examples forced real API usage. This is a well-known benefit of dogfooding, but it's worth noting that **AI-written examples caught an issue that human-written tests missed.** The tests were spec-compliant but the spec itself had a gap.

## What Was Surprising

### Cross-platform bugs surface unexpectedly

The Windows errno fix was discovered because Claude Code ran tests on a German-locale Windows machine. The `delete_folder` method was catching `OSError` and checking `if "not empty" in str(exc)` -- which fails when the OS returns "Das Verzeichnis ist nicht leer." The fix (checking `exc.errno` instead) is obvious in hindsight but easy to miss in an English-only development environment.

### The human's role shifts

With AI handling implementation, the human's role shifted toward:
- **Defining scope** ("do items 1 through 5")
- **Making judgment calls** ("fix it, but let's audit all methods first")
- **Architectural decisions** (spec-first, two-tier path resolution)
- **Quality gates** (reviewing code, approving plans)

This is closer to a tech lead role than a traditional developer role.

### Documentation quality requires iteration

The first pass of examples had issues: Unicode characters that broke on Windows consoles, f-string syntax not supported on Python 3.10, and `RemotePath("")` calls that triggered validation errors. Each required a fix-and-rerun cycle. **Generated documentation isn't done until it actually runs.**

## What Could Be Better

### Spec coverage of edge cases

The specs didn't address empty path semantics, which led to a runtime discovery. Specs could include an "Edge Cases" section explicitly listing boundary conditions (empty strings, None, very long paths, special characters).

### Test-before-spec updates

When we fixed the empty path handling, the code and tests were updated first, and the spec was updated afterward. In strict SDD, the spec should change first. In practice, the fix-then-document flow was faster for a bug-like issue, but it's a discipline worth noting.

## Lessons for Others

1. **Write specs before involving AI.** The clearer your specs, the better the AI's output. Vague requirements produce vague code.

2. **Use plan mode for anything non-trivial.** Having the AI propose a plan before writing code catches misalignment early.

3. **Run the examples.** Generated code that looks right may not be right. Run it, on your actual platform, with your actual Python version.

4. **Let the AI do breadth; you do depth.** AI is great at writing 50 tests or 6 example scripts. You're great at deciding whether the API design is right.

5. **Document decisions as you go.** ADRs and spec updates are cheap to write in the moment but expensive to reconstruct later. We documented the empty path decision as ADR-0004 immediately after making it.

6. **Audit before release.** Asking "what's missing?" and getting a structured, prioritized list is one of the highest-value uses of AI pair programming. It surfaces blind spots you've adapted to.

## Reproducing This Workflow

If you want to try this approach on your own project:

1. Write specs first (see `sdd/specs/` for examples of the format)
2. Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or a similar AI coding tool
3. Start with plan mode: describe the task, review the plan, then approve
4. Implement in phases: core first, then docs, then polish
5. Run everything after each phase (lint, typecheck, tests, examples)
6. Document decisions as ADRs when you make non-obvious choices

The full commit history of this project is the best documentation of the process. Each commit message describes what changed and why.
