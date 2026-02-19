# How We Built This Package: Human + AI Pair Programming

This document chronicles how `remote-store` was built as a collaboration between a human developer and [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's AI coding assistant. The goal is transparency: showing what worked, what surprised us, and what others can learn from the process.

## The Numbers

| Metric | Value |
|--------|-------|
| Source code | ~2,400 lines (4 backends) |
| Tests | 453 tests, ~3,500 lines |
| Specs & docs | ~1,700 lines |
| Examples | ~350 lines (6 scripts, 3 notebooks) |
| Documentation site | MkDocs Material |
| Coverage | 95% |
| Calendar time | 3 days of focused work |
| Commits | 24 |

## Origin: Citizen Developers Shouldn't Need to Learn boto3

The idea for `remote-store` came from a simple observation: teams that include citizen developers -- analysts, scientists, domain experts who write Python but aren't software engineers -- kept getting stuck on file storage. Every cloud provider has its own SDK, its own auth dance, its own streaming quirks. The experienced devs on the team would write wrapper code, but it was never reusable across projects, and the citizen devs couldn't maintain it.

The goal was to give those teams a single API that hides the backend complexity entirely. A data analyst who can write `store.write("report.csv", data)` shouldn't need to understand S3 multipart uploads or SFTP channel management. The same code should work whether files live on a shared drive, an S3 bucket, or an SFTP server -- and switching between them should be a config change, not a code change.

That citizen-developer use case shaped every design decision: immutable config (so non-experts can't accidentally mutate state), clear error messages (no raw `botocore` tracebacks), capability declarations (so unsupported operations fail with an explanation, not a cryptic exception), and streaming by default (so large files just work without anyone tuning buffer sizes).

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

### Phase 6: S3 Backend (AI-led, human-reviewed)

The first remote backend. The human identified s3fs as the right abstraction layer and wrote the spec (`008-s3-backend.md`). Claude Code then implemented against it in plan mode:

- `S3Backend` using s3fs/aiobotocore (~210 lines)
- Session-scoped moto HTTP server for testing (avoiding Python 3.13 PEP 667 incompatibility with `mock_aws()`)
- S3-specific tests plus full conformance suite
- Logo design prompt (human picked the final version)

```
52d3799  Add S3Backend with s3fs, spec, tests, and logo
```

### Phase 7: Developer tooling (collaborative)

The human pushed for tighter development workflow. Claude Code set up:

- **Pre-commit hooks**: ruff lint+format and mypy, replacing manual `make lint` with automatic enforcement
- **MkDocs Material site**: Full documentation site with API reference, getting started guide, backend docs, and design docs
- **Hatch scripts**: Replaced Makefile with `pyproject.toml`-native scripts (`hatch run lint`, `hatch run test-cov`, etc.)

```
2e46651  Add pre-commit hooks for ruff and mypy
7fdde35  Add MkDocs Material documentation site
39ea749  Fix S3 backend status in README and add docs CI job
```

### Phase 8: SFTP Backend (AI-led, human-reviewed)

The most complex backend, using pure paramiko (not sshfs or fsspec's SFTPFileSystem, which hardcodes `AutoAddPolicy`). The human wrote a detailed plan covering:

- Host key policies (STRICT / TRUST_ON_FIRST_USE / AUTO_ADD)
- PEM key sanitization (Azure Key Vault quirk from legacy code)
- Simulated atomic writes (temp file + `posix_rename`, with documented orphan caveat)
- Tenacity retry with exponential backoff for transient SSH errors

Claude Code implemented the full stack in one session:

- Spec `009-sftp-backend.md` (27 spec items)
- In-process SFTP test server using paramiko's `ServerInterface` + `SFTPServerInterface`
- `SFTPBackend` (~420 lines) with lazy connection, staleness detection, and full Backend ABC compliance
- SFTP-specific tests plus conformance suite (453 total tests)

**The debugging was instructive.** Initial test runs had 24 failures -- all reads returning "Failure." A debug script isolated the issue to `SFTPHandle.stat()` in the test server: it used `SFTPServer.convert_errno(os.fstat(...))` instead of `SFTPAttributes.from_stat(os.fstat(...))`, causing `prefetch()` to fail because the handle stat returned errno codes as file metadata. A subtle API misuse that produced confusing errors far from the root cause.

**CI revealed a pip resolver surprise.** After pushing, CI failed with all S3 tests broken -- despite no S3 code changes. Investigation showed that botocore 1.42.50 had released between CI runs. The new version caused pip to silently downgrade s3fs from 2026.2.0 to 0.4.2 (ancient, no aiobotocore) rather than failing with a resolution error. The fix: pin `s3fs>=2024.2.0` to prevent the fallback.

**Cross-platform mypy differences.** The `before_sleep_log(log, ...)` call from tenacity had a type mismatch on local mypy (Logger vs LoggerProtocol) but not on CI. Using `# type: ignore[arg-type,unused-ignore]` handles both environments -- the combined codes suppress the error where it exists and silence the "unused ignore" warning where it doesn't.

```
f3b7df9  Add SFTPBackend with paramiko, spec, tests, and bump to v0.2.0
3956b4d  Fix CI: pin s3fs>=2024.2.0 and fix cross-platform type:ignore
```

### Phase 9: Going Public (collaborative)

Making the repository public exposed a category of problems that don't exist while a project is private: **everything that works "by reference" locally breaks "by value" on external platforms.**

The first casualty was the PyPI listing. The README logo used a relative path (`assets/logo.png`), which renders fine on GitHub but produces a broken image on PyPI -- their CDN proxies images through `pypi-camo.freetls.fastly.net` and can't resolve relative paths. The fix was straightforward (absolute raw GitHub URL), but the failure was invisible until the package was actually published and someone looked at the PyPI page.

The second issue was documentation hosting. The project had GitHub Pages set up via a CI workflow, but Read the Docs was missing. RTD provides versioned docs, search, and the familiar `readthedocs.io` URL that the Python community expects. The `.readthedocs.yaml` config had been written speculatively during setup but never activated -- the project needed to be imported on readthedocs.org, the build OS needed updating, and the `Documentation` URL in `pyproject.toml` was still pointing to GitHub Pages.

The third issue was subtler: the documentation site itself was out of date. Specs 010 (native path resolution) and 011 (S3-PyArrow backend) had been added to `sdd/specs/` during development, but never copied to `docs/design/specs/` or added to `mkdocs.yml` navigation. Same for ADR-0005. The docs site was shipping a version of the design documentation that was two specs and one ADR behind the actual source of truth. **When docs live in two places (source-of-truth in `sdd/` and rendered site in `docs/`), keeping them in sync is a manual step that's easy to forget.**

Finally, the `pyproject.toml` metadata changes (Documentation URL, README fixes) don't take effect on PyPI until a new version is published. PyPI serves whatever was in the sdist/wheel at upload time. This means every metadata fix requires a version bump and release -- there's no way to patch the PyPI listing in place.

**The lesson: "works on GitHub" is not the same as "works everywhere the package appears."** PyPI, Read the Docs, and GitHub each render the same source files differently, with different rules for resolving paths, images, and links. A pre-release checklist that includes checking the rendered output on each platform would have caught all of these issues before users did.

### Phase 10: The Streaming Audit (v0.4.3)

The README says "streaming by default" and spec SIO-001 mandates that `read()` returns a `BinaryIO` that streams from the backend. But when the human asked to **review whether streaming actually worked**, every single backend turned out to load the entire file into memory.

The pattern was the same in all four backends: `read()` called something that fetched the full content, wrapped it in `BytesIO`, and returned that. Callers got a `BinaryIO` that quacked correctly but had already consumed all the memory. Writes had the same problem — `BinaryIO` content was `.read()` into a `bytes` object before being written.

**The fixes were backend-specific but shared a theme:**

| Backend | Before | After |
|---------|--------|-------|
| Local | `BytesIO(path.read_bytes())` | `open(path, "rb")` — real file handle |
| S3 | `BytesIO(fs.cat_file(path))` | `fs.open(path, "rb")` — HTTP range requests |
| S3-PyArrow | `BytesIO(pa_fs.open_input_stream(...).read())` | Custom `_PyArrowBinaryIO(io.RawIOBase)` adapter + `BufferedReader` |
| SFTP | `BytesIO(sftp.file(...).read())` | Return `SFTPFile` directly (no `prefetch()`) |

For writes, all backends gained `shutil.copyfileobj()` for `BinaryIO` content, which copies in chunks without materializing the full stream.

**The PyArrow adapter was the trickiest.** PyArrow's `RandomAccessFile` doesn't implement Python's `BinaryIO` protocol — it has `read()` and `seek()` but no `readinto()`, which `io.BufferedReader` requires. The solution was a thin `io.RawIOBase` subclass that bridges `readinto()` → `read()`, wrapped in `BufferedReader` for buffering. About 20 lines to glue two ecosystems together.

**The lesson is uncomfortable: specs that aren't enforced by tests drift from reality.** Spec SIO-001 said "streaming," and every backend's `read()` signature returned `BinaryIO`, so mypy was happy and tests passed. But no test verified that the returned `BinaryIO` actually streamed from the backend rather than from a pre-filled buffer. The type system validated the interface; it couldn't validate the behavior behind it.

This session also caught two housekeeping issues:
- **ReadTheDocs deep links need `/en/latest/`**: The README linked to `readthedocs.io/api/store/` which 404'd because RTD requires a version prefix. Another instance of the Phase 9 lesson — "works on GitHub ≠ works everywhere."
- **Versioning docs were duplicated and diverged**: `CONTRIBUTING.md` had the current policy (bump-my-version, single source file), while `sdd/000-process.md` still described the old manual process. Consolidated to CONTRIBUTING.md with a pointer from process.md.

```
0fc7116  Fix streaming read/write to avoid loading entire files into memory
712950e  Consolidate versioning docs into CONTRIBUTING.md
7f1776a  Fix broken API reference link in README for PyPI
76ec1b3  Bump version to 0.4.3
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

### Detailed plans pay for themselves

The SFTP backend plan was unusually detailed -- specifying constructor params, region structure, temp file naming patterns, and even the test server architecture. This upfront investment meant the entire implementation (spec + server + backend + tests + wiring) was completed in a single session with no false starts. **The more complex the task, the more a detailed plan pays off.**

### Legacy code as a knowledge source

The SFTP backend drew from battle-tested legacy code (`legacy/sftp/sftp_store.py`) for PEM sanitization and host key handling. Claude Code extracted the proven patterns and adapted them to the new Backend ABC contract. **Pointing AI at working legacy code is often more effective than describing requirements from scratch.**

## What Was Surprising

### Cross-platform issues surface in layers

The Windows errno fix was discovered because Claude Code ran tests on a German-locale Windows machine. The `delete_folder` method was catching `OSError` and checking `if "not empty" in str(exc)` -- which fails when the OS returns "Das Verzeichnis ist nicht leer." The fix (checking `exc.errno` instead) is obvious in hindsight but easy to miss in an English-only development environment.

The SFTP work added another layer: mypy type-checking results differed between Windows (local) and Linux (CI) due to different tenacity stub versions. **Cross-platform doesn't just mean "runs on both OSes" -- it means the entire toolchain (linters, type checkers, dependency resolvers) behaves consistently.**

### The human's role shifts

With AI handling implementation, the human's role shifted toward:
- **Defining scope** ("do items 1 through 5")
- **Making judgment calls** ("fix it, but let's audit all methods first")
- **Architectural decisions** (spec-first, two-tier path resolution)
- **Quality gates** (reviewing code, approving plans)

This is closer to a tech lead role than a traditional developer role.

### Documentation quality requires iteration

The first pass of examples had issues: Unicode characters that broke on Windows consoles, f-string syntax not supported on Python 3.10, and `RemotePath("")` calls that triggered validation errors. Each required a fix-and-rerun cycle. **Generated documentation isn't done until it actually runs.**

### Unpinned dependencies are a time bomb

The s3fs downgrade incident was particularly insidious: pip silently installed a 2-year-old version instead of failing with a resolution error. The CI was green one day and broken the next, with zero code changes to the affected component. **Pin lower bounds on all non-trivial dependencies, especially in dev/CI configurations where transitive dependency trees are large.**

## What Could Be Better

### Spec coverage of edge cases

The specs didn't address empty path semantics, which led to a runtime discovery. Specs could include an "Edge Cases" section explicitly listing boundary conditions (empty strings, None, very long paths, special characters).

### Test-before-spec updates

When we fixed the empty path handling, the code and tests were updated first, and the spec was updated afterward. In strict SDD, the spec should change first. In practice, the fix-then-document flow was faster for a bug-like issue, but it's a discipline worth noting.

### Test server complexity

The in-process SFTP test server (~275 lines) is nearly as complex as some backends. The `SFTPHandle.stat()` bug showed that test infrastructure can harbor subtle bugs of its own. A dedicated debug script was needed to isolate the issue -- standard test output just showed "Failure" with no useful context. **Test servers deserve the same care as production code.**

### A living backlog beats a static roadmap

After the production readiness audit (Phase 5), we realized loose ideas were
scattered across commit messages and review comments. We created
`sdd/BACKLOG.md` as a single, tiered tracker:

| Tier | Prefix | Purpose |
|------|--------|---------|
| Release Blockers | `BL-NNN` | Must ship before the next PyPI publish |
| Backlog | `BK-NNN` | Committed work, queued behind blockers |
| Ideas | `ID-NNN` | Parking lot — not evaluated, not committed |
| Done | `DONE-NNN` | Completed items kept for reference |

Items graduate upward: an Idea becomes a Backlog item when someone scopes it
and commits to an RFC; a Backlog item becomes a Release Blocker when it's
required for the upcoming release. Code-changing items still go through the
full SDD pipeline (spec → tests → code); operational items (CI, branch
protection, dependency pins) are tracked and closed directly.

This turned out to be surprisingly useful for AI-assisted development.
**Giving Claude Code a structured backlog to read means it can propose
promotions, spot dependencies between items, and draft new entries in the
right tier with the right prefix** — without the human re-explaining the
prioritization scheme each session.

## Lessons for Others

1. **Write specs before involving AI.** The clearer your specs, the better the AI's output. Vague requirements produce vague code.

2. **Use plan mode for anything non-trivial.** Having the AI propose a plan before writing code catches misalignment early.

3. **Run the examples.** Generated code that looks right may not be right. Run it, on your actual platform, with your actual Python version.

4. **Let the AI do breadth; you do depth.** AI is great at writing 50 tests or 6 example scripts. You're great at deciding whether the API design is right.

5. **Document decisions as you go.** ADRs and spec updates are cheap to write in the moment but expensive to reconstruct later. We documented the empty path decision as ADR-0004 immediately after making it.

6. **Audit before release.** Asking "what's missing?" and getting a structured, prioritized list is one of the highest-value uses of AI pair programming. It surfaces blind spots you've adapted to.

7. **Pin your dependency lower bounds.** Unpinned deps in CI will eventually bite you. A `>=` pin costs nothing and prevents silent downgrades that produce baffling failures.

8. **Point AI at legacy code.** If you have working code that solves part of the problem, show it to the AI. It will extract the relevant patterns faster than you can describe them.

9. **Test behavior, not just interfaces.** A method that returns `BinaryIO` can satisfy mypy and pass functional tests while secretly loading everything into memory. If your spec promises streaming, write a test that proves it streams — e.g., verify that reading a large file doesn't allocate proportional memory, or that the returned handle reads lazily from the source.

10. **Periodically audit spec claims against implementation.** Specs drift. A dedicated "does the code still do what the spec says?" review caught four backends worth of non-streaming `read()` implementations hiding behind correct type signatures.

## Reproducing This Workflow

If you want to try this approach on your own project:

1. Write specs first (see `sdd/specs/` for examples of the format)
2. Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or a similar AI coding tool
3. Start with plan mode: describe the task, review the plan, then approve
4. Implement in phases: core first, then docs, then polish
5. Run everything after each phase (lint, typecheck, tests, examples)
6. Document decisions as ADRs when you make non-obvious choices

The full commit history of this project is the best documentation of the process. Each commit message describes what changed and why.
