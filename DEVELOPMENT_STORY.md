# How We Built This Package: Human + AI Pair Programming
<!-- doc: dual dest=explanation/development-story.md -->

This document chronicles how `remote-store` was built as a collaboration between a human developer and [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's AI coding assistant. The goal is transparency: showing what worked, what surprised us, and what others can learn from the process.

## Origin: Citizen Developers Shouldn't Need to Learn boto3

Teams with citizen developers (analysts, scientists, domain experts who write Python but aren't software engineers) kept getting stuck on file storage. Every cloud provider has its own SDK, its own auth dance, its own streaming quirks.

The goal: a single API that hides all of it. `store.write("report.csv", data)` should work whether files live on a shared drive, an S3 bucket, or an SFTP server. Switching backends should be a config change, not a code change.

## The Approach: How I Learned to Work with AI

This isn't about the project's methodology. It's about the human side: how I found a way of working that turns AI pair programming from "faster typing" into something qualitatively different.

**It started with a conversation.** The initial concept came from chatting with ChatGPT. Not code, just ideas. That conversation produced a project brief and a rough `src/` layout.

**The methodology was Spec-Driven Development (SDD) from day one.** I came with the idea of what each spec should cover; Claude Code brought the details, method signatures, error conditions, and invariants. We refined together, reworked drafts, and landed on contracts that both sides could implement and verify against. Specs constrain the solution space, are reviewable before code exists, and enable traceability (`@pytest.mark.spec("ID")`). The human defines the *what* and *why*; the AI handles the *how*.

**Then Claude Code entered the picture.** VSCode terminal, repo open beside it. At this stage I was still thinking like a developer who happens to have a fast typist.

**The way of working changed gradually.** My time was better spent on *how we work* than on *what we build*. I invested in process artifacts: `CLAUDE.md` with project rules, `DESIGN.md` with code conventions, `TESTING.md` with quality standards. Every artifact made the next session start from a higher baseline.

**A big part of that was learning from others.** `TESTING.md` came from studying pytest best practices, mutation testing, and how FastAPI and SQLAlchemy structure their test suites. `DOCUMENTATION.md` was built on Diataxis and mkdocstrings conventions. None of the process infrastructure was invented from scratch. It was curated from the ecosystem and made specific to our workflow.

**Then came the split-brain pattern.** [claude.ai/code](https://claude.ai/code) for research and thinking: it has full repo access but is less dangerous to let loose searching the internet. Claude Code terminal for execution. Research produces decisions; execution implements them.

**Local hardware became part of the workflow.** The ollama MCP server delegates bulk tasks to local GPU-accelerated models, parallelizing mechanical work without burning API budget.

**Eventually I switched to pure terminal.** Claude Code in the terminal, browser for monitoring. No more IDE. The terminal *is* the IDE when your AI partner can read, write, search, and run anything.

**The compound payoff arrived with orchestration: "ask the experts" mode.** The `/orchestrate` skill decomposes tasks into parallel tracks, each handled by a domain-expert agent. These agents do real refinement. They change the plan when they find a better approach, and explain why. Their reviews focus on their expertise and almost always find things the normal `/review-pr` skill misses. Features flow the way they should, with quality built in at every step. It feels like reinvented scrum: a sprint's worth of coordinated expert work in a single session.

**Where it stands now.** I stopped optimizing for output and started optimizing for how I work. Output became a byproduct. The most valuable artifacts aren't the 16,000 lines of source code. They're the process documents, skills, memory system, and conventions that make every future session start where the last one ended. We're not done. The workflow keeps evolving.

## Lessons for Others

If this project has one recurring lesson, it's that **correctness at the interface is not correctness at the behavior.** Python's duck typing means anything that quacks correctly gets through. We found, repeatedly, that the gap between "passes type checks and tests" and "actually does what it claims" is where the real bugs live.

| What looked correct | What was actually wrong |
|---|---|
| `read()` returns `BinaryIO`, mypy happy, tests pass | Every backend loaded the entire file into memory |
| `Capability.GLOB` declared on 4 backends | No `glob()` method existed anywhere |
| `"strict"` passed as host key policy | `"strict" != HostKeyPolicy.STRICT`, silently degrades to least-secure mode |
| Quick Start in README shows S3 usage | `_register_builtin_backends()` only registers local+azure |
| `bytes(None)` in stream wrapper | Silently produces `b'\x00\x00\x00\x00'` instead of propagating error |
| `Example::` in every docstring | RST literal blocks, no syntax highlighting in mkdocstrings. Uniform wrongness looks intentional |
| Azure benchmark: 107x slower than adlfs | fsspec caching artifact; real overhead was 1.2x |
| 95% test coverage, green CI | Includes `assert WritableContent is not None`, hitting import lines, not behavior |
| `list_folders()` returns strings | Every other listing method returns typed objects. Strings cooperate *just enough* |

The type system validates the interface; it can't validate the behavior behind it. The lessons below are organized in two groups: how to work with AI, and how to build with AI.

### Way of Working

1. **Invest in your way of working. It compounds faster than features.** `CLAUDE.md` with project rules, skills for repeatable workflows, a memory system for cross-session continuity, research docs for front-loading decisions. Each one was small when created, but together they shifted the bottleneck from "how do we do this?" to "what should we do next?"

2. **Codify lessons as executable guardrails, not prose.** After ~165 commits, data showed prose rules weren't enough: 7 of 9 audit-fix commits forgot the backlog, 62% of code changes skipped the CHANGELOG. Slash-command skills (`.claude/commands/`) turned those failure patterns into executable checklists the AI follows without re-deriving.

3. **Split research and execution into separate modes.** They need different thinking. claude.ai/code for exploring trade-offs and writing research documents; Claude Code terminal for implementation. Research produces decisions with evidence; execution implements them without re-litigating.

4. **Write research documents before implementation specs.** Mapping the design space on paper prevents mid-implementation pivots. Our config-loaders research caught a real security bug (`"strict" != HostKeyPolicy.STRICT`) that was invisible to mypy, tests, and code review. Thinking through integration scenarios is cheaper than debugging them in production.

5. **"No" is a valid research outcome.** Two research documents concluded "don't build this": async would double the codebase, Dagster v1 should be thin. Both live in `sdd/research/` as a link for anyone who asks "why not?", saving the next person from re-investigating.

6. **Review in a separate session from authoring.** A fresh session reads your output cold. It doesn't inherit the author's assumptions. The context boundary between sessions is the "different person" that review traditionally requires. Same model, different role, different results.

7. **Use plan mode for anything non-trivial.** Have the AI propose a detailed plan before writing code. The SFTP backend plan specified constructor params, test server architecture, and temp file naming. The entire implementation completed in one session with no false starts.

8. **Let the AI do breadth; you do depth.** AI writes 53 tests or 6 example scripts. You decide whether the API design is right, whether the research covers real alternatives, whether the messaging resonates. Tech lead, not typist.

### Building with AI

9. **Test behavior, not just interfaces.** A method that returns `BinaryIO` can satisfy mypy while secretly loading everything into memory. If your spec promises streaming, write a test that proves it. We didn't, and every backend was faking it.

10. **Run the code, on your actual platform.** Unicode crashed on Windows cp1252, f-strings failed on Python 3.10, em dashes hid in unchecked table cells. If your CI is more forgiving than your users' environments, your CI is testing itself, not your software.

11. **Run adversarial audits after major milestones.** PR reviews catch local issues; adversarial audits catch systemic ones. Cross-backend inconsistencies, ghost capabilities, and docs-to-code drift are invisible at the PR level because each PR is internally consistent.

12. **Audit findings are hypotheses. Verify before fixing.** Our third audit produced 19 findings; three were non-defects. One "missing docstring" finding was actually a one-line config gap, not 40 boilerplate edits. Completeness is not correctness.

13. **Pin your dependency lower bounds.** pip silently installed a 2-year-old s3fs instead of failing with a resolution error. CI was green one day, broken the next, zero code changes. A `>=` pin costs nothing.

14. **Point AI at legacy code.** The SFTP backend drew proven patterns from battle-tested legacy code for PEM sanitization and host key handling. Working code communicates requirements more effectively than describing them from scratch.

15. **Systematic pattern errors are invisible because they look intentional.** Every docstring used RST `Example::` blocks with no syntax highlighting in mkdocstrings. Because *every* docstring was wrong the same way, it looked deliberate. Only a human browsing the rendered docs noticed.

16. **Document decisions as you go.** ADRs and spec updates are cheap in the moment but expensive to reconstruct later. The growing collection became the project's institutional memory.

17. **Adopt structural decisions early.** We retrofitted Diataxis onto an existing flat docs site, reclassifying every page and rebuilding navigation. Any structural decision is cheapest before content accumulates.

18. **Benchmarks must measure honestly.** Our Azure benchmark showed 107x slower than adlfs, damning until we found it was a caching artifact. Real overhead: 1.2x. Present numbers (ms, %), not judgments, and understand what you measured.

19. **Deduplication compounds.** v0.19.0 removed ~300 lines of library code and ~1,500 lines of tests while improving navigability. Each small cleanup created helpers that made the next cleanup trivial.

## What Worked Well

**Specs as a shared contract.** The human verifies correctness at the spec level before code exists; Claude Code implements against it. This made "done" unambiguous and reduced review to checking contracts, not forming expectations on the fly.

**Discovery through dogfooding.** AI-written examples found an API bug that human-written tests missed. The streaming audit, triggered by simply asking "does it actually stream?", found every backend faking it. Running the code is where the real bugs surface.

**Process infrastructure compounds.** Skills codified repeatable workflows, research docs front-loaded decisions, quality gates caught regressions. Together they enabled v0.20.0's feature explosion: more output in one cycle than any previous release, because cross-cutting concerns were handled automatically.

**A living backlog beats a static roadmap.** A tiered `BACKLOG.md` (Release Blockers → Backlog → Ideas) gives Claude Code structured context to work from. It proposes promotions, spots dependencies, and drafts entries in the right tier without re-explanation.

**Legacy code as a knowledge source.** Pointing AI at battle-tested legacy code for the SFTP backend was more effective than describing requirements. The AI extracted proven patterns and adapted them to the new contract.

**Parametrize tests, but only after they exist.** Write verbosely first, compress once patterns emerge. The slim-tests effort saved ~940 lines while preserving every test case.

## What Was Surprising

**Cross-platform means the entire toolchain.** Not just "runs on both OSes": errno codes on German Windows, mypy stubs differing between platforms, Unicode crashing cp1252 consoles, em dashes rendering differently per OS. Each layer surfaced a new category of problems.

**Session isolation is a genuine review mechanism.** A reviewing session with no memory of the authoring session's reasoning approached the same artifacts as a genuinely independent reader. It caught things that were *missing*, not things that were *wrong*. Exactly what code review is supposed to provide.

**The human's role shifts to tech lead.** Defining scope, making judgment calls, architectural decisions, quality gates. Less "write the code," more "decide what's worth building and whether it's right."

**Uniform wrongness is invisible.** When every docstring has the same rendering bug, or every backend loads files into memory the same way, it looks like a deliberate choice. Only checking the rendered output or actual behavior reveals the truth.

**"No" produces as much value as "yes."** Two research documents that concluded "don't build this" saved more time than features that shipped, by preventing the question from being re-asked.

**Benchmarks can lie without being wrong.** The 107x Azure slowdown was a real measurement of a caching artifact. Understanding *what* you measured matters more than the number.

## What Could Be Better

**Rendered-output checking.** Too many bugs were only visible in deployed docs, the PyPI listing, or actual terminal output. RST rendering, broken images, encoding issues. All passed CI. A pre-release step checking what users actually see would catch an entire class of issues.

**Cross-backend semantic contracts.** Error handling is where backend interchangeability matters most. `get_folder_info` on empty folders succeeds on Local but raises `NotFound` on S3/SFTP/Azure. The backends still disagree in the edge cases that matter.

**Spec coverage of edge cases.** The specs didn't address empty path semantics, leading to a runtime discovery. An explicit "Edge Cases" section in each spec would catch boundary conditions at design time.

**Test server complexity.** The in-process SFTP test server (~275 lines) is nearly as complex as some backends. A `SFTPHandle.stat()` bug in the test server produced 24 test failures with misleading error messages. Test infrastructure deserves the same care as production code.

## The Timeline

The log below is chronological: each phase as it happened, with commit hashes, bugs encountered, and lessons learned in context.

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

**The debugging was instructive.** Initial test runs had 24 failures — all reads returning "Failure." A debug script isolated the issue to `SFTPHandle.stat()` in the test server: it used `SFTPServer.convert_errno(os.fstat(...))` instead of `SFTPAttributes.from_stat(os.fstat(...))`, causing `prefetch()` to fail because the handle stat returned errno codes as file metadata. A subtle API misuse that produced confusing errors far from the root cause.

**CI revealed a pip resolver surprise.** After pushing, CI failed with all S3 tests broken — despite no S3 code changes. Investigation showed that botocore 1.42.50 had released between CI runs. The new version caused pip to silently downgrade s3fs from 2026.2.0 to 0.4.2 (ancient, no aiobotocore) rather than failing with a resolution error. The fix: pin `s3fs>=2024.2.0` to prevent the fallback.

**Cross-platform mypy differences.** The `before_sleep_log(log, ...)` call from tenacity had a type mismatch on local mypy (Logger vs LoggerProtocol) but not on CI. Using `# type: ignore[arg-type,unused-ignore]` handles both environments — the combined codes suppress the error where it exists and silence the "unused ignore" warning where it doesn't.

```
f3b7df9  Add SFTPBackend with paramiko, spec, tests, and bump to v0.2.0
3956b4d  Fix CI: pin s3fs>=2024.2.0 and fix cross-platform type:ignore
```

### Phase 9: Going Public (collaborative)

Making the repository public exposed a category of problems that don't exist while a project is private: **everything that works "by reference" locally breaks "by value" on external platforms.**

The first casualty was the PyPI listing. The README logo used a relative path (`assets/logo.png`), which renders fine on GitHub but produces a broken image on PyPI — their CDN proxies images through `pypi-camo.freetls.fastly.net` and can't resolve relative paths. The fix was straightforward (absolute raw GitHub URL), but the failure was invisible until the package was actually published and someone looked at the PyPI page.

The second issue was documentation hosting. The project had GitHub Pages set up via a CI workflow, but Read the Docs was missing. RTD provides versioned docs, search, and the familiar `readthedocs.io` URL that the Python community expects. The `.readthedocs.yaml` config had been written speculatively during setup but never activated — the project needed to be imported on readthedocs.org, the build OS needed updating, and the `Documentation` URL in `pyproject.toml` was still pointing to GitHub Pages.

The third issue was subtler: the documentation site itself was out of date. Specs 010 (native path resolution) and 011 (S3-PyArrow backend) had been added to `sdd/specs/` during development, but never copied to `docs/design/specs/` or added to `mkdocs.yml` navigation. Same for ADR-0005. The docs site was shipping a version of the design documentation that was two specs and one ADR behind the actual source of truth. **When docs live in two places (source-of-truth in `sdd/` and rendered site in `docs/`), keeping them in sync is a manual step that's easy to forget.**

Finally, the `pyproject.toml` metadata changes (Documentation URL, README fixes) don't take effect on PyPI until a new version is published. PyPI serves whatever was in the sdist/wheel at upload time. This means every metadata fix requires a version bump and release — there's no way to patch the PyPI listing in place.

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

**The PyArrow adapter was the trickiest.** PyArrow's `RandomAccessFile` doesn't implement Python's `BinaryIO` protocol — it has `read()` and `seek()` but no `readinto()`, which `io.BufferedReader` requires. The solution was a thin `io.RawIOBase` subclass that bridges `readinto()` -> `read()`, wrapped in `BufferedReader` for buffering. About 20 lines to glue two ecosystems together.

**The lesson is uncomfortable: specs that aren't enforced by tests drift from reality.** Spec SIO-001 said "streaming," and every backend's `read()` signature returned `BinaryIO`, so mypy was happy and tests passed. But no test verified that the returned `BinaryIO` actually streamed from the backend rather than from a pre-filled buffer. The type system validated the interface; it couldn't validate the behavior behind it.

This session also caught two housekeeping issues:
- **ReadTheDocs deep links need `/en/latest/`**: The README linked to `readthedocs.io/api/store/` which 404'd because RTD requires a version prefix. Another instance of the Phase 9 lesson — "works on GitHub != works everywhere."
- **Versioning docs were duplicated and diverged**: `CONTRIBUTING.md` had the current policy (bump-my-version, single source file), while `sdd/000-process.md` still described the old manual process. Consolidated to CONTRIBUTING.md with a pointer from process.md.

```
0fc7116  Fix streaming read/write to avoid loading entire files into memory
712950e  Consolidate versioning docs into CONTRIBUTING.md
7f1776a  Fix broken API reference link in README for PyPI
76ec1b3  Bump version to 0.4.3
```

### Phase 11: AI Reviewing AI (AI-reviewed)

After 14 PRs, the human asked Claude Code to review the merged pull requests — looking for patterns, missed issues, and quality gaps. The twist: **both the PRs and the reviews were produced by Claude Code, just in different sessions.** The authoring sessions wrote specs, code, and documentation; a separate reviewing session evaluated them cold.

Only 2 of the 14 PRs had received substantive review. But those two reviews caught real issues:

- **PR #1** (backlog + README rewrite): 3 non-blocking items — a dead documentation URL (`readthedocs.io` referenced before hosting existed), stale `mkdocs.yml` description, and misleading `pyproject.toml` keywords.
- **PR #11** (Azure backend RFC + spec): 6 critical issues + 4 minor notes — wrong RFC numbering, invalid markdown checkbox syntax, 7 Backend ABC methods with no spec coverage, GLOB capability declared but unexplained, cross-references instead of inline explanations, ambiguous return types.

All 6 critical issues on PR #11 were fixed before merge. The 12 unreviewed PRs shipped as-is.

**The most revealing pattern was the authoring session's blind spot: completeness, not correctness.** The reviewing session didn't find things that were *wrong* — it found things that were *missing*. Seven abstract methods without invariants, a capability declared but never specified, return types left ambiguous. The authoring session "knew" how those would work and didn't realize the output was incomplete. A second session, reading the artifacts without that context, immediately spotted the gaps.

**Same model, different role, different results.** Both sessions had identical capabilities, but the reviewing session found issues the authoring session created. The difference wasn't intelligence — it was framing. The author optimizes for producing; the reviewer optimizes for interrogating. Session isolation prevented the reviewer from inheriting the author's assumptions, which is exactly what code review is supposed to provide.

**The practical implication for solo maintainers:** separate sessions simulate a two-person team. The context boundary between sessions acts as the "different person" that review traditionally requires. The cost of a review session is low; the 2 PRs that received reviews caught issues that would have persisted in the 12 that didn't.

### Phase 12: Adversarial Audit (AI-vs-AI)

Phase 11 used a second AI session as a code reviewer. Phase 12 took it further: the human asked a fresh Claude Code session to act as an adversary — "prove this package wrong." Four parallel AI agents independently audited security, test quality, API design, and CI/docs, then the human consolidated findings.

The audit produced 47 findings across four severity tiers. Two were critical (after post-audit verification downgraded one from Critical to High):

1. **The README Quick Start for S3 doesn't work.** `_register_builtin_backends()` only registers `local` and `azure`. S3, SFTP, and S3-PyArrow must be manually imported and registered. The documented happy path for the three most common remote backends crashes on first use.
2. **The GLOB capability is a ghost.** Four backends declare support; no `glob()` method exists anywhere. The capability system says "yes" to something the code can't do.

A third finding — `S3Backend.close()` calling a process-wide `clear_instance_cache()` — was initially rated Critical but downgraded to High after verification showed existing filesystem references remain valid (the cache is a lookup table, not a lifecycle manager).

Beyond the critical items, the audit exposed a pattern: **the "unified interface" promise breaks down at the edges.** `get_folder_info` on empty folders returns success on LocalBackend but raises `NotFound` on S3/SFTP/Azure. `delete_folder` on non-empty folders raises `NotFound` (wrong type) on local but `RemoteStoreError` (base class) on others. These are the exact scenarios where backend interchangeability matters most — error handling — and the backends disagree.

The audit also found that thread safety (claimed by STORE-007) has zero implementation (no locks on lazy init) and zero tests (no concurrency tests exist). The 95% test coverage includes tests like `assert WritableContent is not None` that hit import lines without verifying behavior.

**The lesson: reviewing PRs catches local issues; adversarial auditing catches systemic ones.** PR review asks "is this change correct?" Adversarial auditing asks "does the whole thing hold together?" The TOCTOU race conditions, cross-backend semantic inconsistencies, and docs-to-code drift were invisible at the PR level because each PR was internally consistent. They only became visible when looking at the system as a whole.

Full findings: `sdd/audits/audit-001-adversarial-review.md`. Backlog items: `sdd/BACKLOG.md` section "Audit Findings (AUD-001)".

### Phase 13: Fixing the Audit (v0.6.0)

Phase 12 found the problems; Phase 13 fixed them. The human took the 7 highest-severity findings from the adversarial audit (2 Critical, 5 High) and wrote a detailed implementation plan. Claude Code executed it in a single branch (`fix/audit-critical-high`), producing one commit per finding.

**The seven fixes, in merge order:**

| Finding | Severity | Fix |
|---------|----------|-----|
| AF-005 | High | New `DirectoryNotEmpty` error type, replacing generic `NotFound` when deleting non-empty folders |
| AF-002 | Critical | Removed `Capability.GLOB` and `Capability.RECURSIVE_LIST` — enum members with no corresponding methods |
| AF-001 | Critical | `_register_builtin_backends()` now auto-registers S3, SFTP, and S3-PyArrow (not just local/azure) |
| AF-003 | High | `S3Backend.close()` no longer calls `clear_instance_cache()`, which was a process-wide side-effect |
| AF-004 | High | SFTP `get_folder_info()` on empty folders returns `FolderInfo(file_count=0)` instead of raising `NotFound` |
| AF-006 | High | `_ErrorMappingStream(io.RawIOBase)` proxy wraps all `read()` return values, catching `OSError` during lazy reads and mapping them through each backend's error classifier |
| AF-007 | High | Azure backend guide wired into docs site navigation |

**The stream wrapper (AF-006) was the most substantial change.** The problem: `Backend.read()` opens a stream inside an `_errors()` context manager, but the caller reads from the stream *after* the context manager exits. Any `OSError` raised during `stream.read()` would leak as a raw exception instead of being mapped to a `RemoteStoreError` subtype. The fix was a `io.RawIOBase` proxy that intercepts `read()`, `readline()`, `seek()`, and iteration, catching `OSError` and routing it through the backend's error classifier.

**The review cycle was instructive.** The initial PR had all 7 fixes in a single commit. The repo owner's review returned 12 points, several of them genuine bugs:

1. **Double-buffering**: Azure and S3-PyArrow were wrapping `BufferedReader(RawIOBase)` in `_ErrorMappingStream` then wrapping *that* in another `BufferedReader`. Two layers of buffering for no benefit.
2. **Exception scope too broad**: The stream wrapper caught bare `Exception`, which would silently swallow programming errors like `TypeError` or `AttributeError`. Narrowed to `OSError` only.
3. **`bytes()` wrapping masked `None`**: `read()` returning `bytes(None)` silently produces `b'\x00\x00\x00\x00'` (length of None's repr) instead of propagating the sentinel. Removed the wrapper.
4. **`from None` suppressed diagnostics**: Changed to `from exc` to preserve the original traceback for debugging.
5. **Inline imports**: Moved `_ErrorMappingStream` imports from inside methods to module top-level.
6. **SFTP error mapping duplication**: The new `_map_exception()` method duplicated logic from `_errors()`. Refactored `_errors()` to delegate to `_map_exception()`.

After addressing all 12 points, the single commit was split into 7 per-finding commits and force-pushed.

**A CI-only mypy failure added a cross-version wrinkle.** The `_ErrorMappingStream` class extends `io.RawIOBase`, but Python 3.13's typeshed stubs define `BufferedReader`'s constructor with a type variable that mypy (strict mode) doesn't accept for custom `RawIOBase` subclasses. Local mypy (Windows, Python 3.12 stubs) passed; CI mypy (Linux, Python 3.13 stubs) failed. Using `type: ignore[type-var]` would pass CI but fail locally (unused-ignore). The fix: `cast("io.RawIOBase", stream)` works on both. **Yet another instance of "cross-platform" meaning the entire toolchain, not just the runtime.**

**The rebase surfaced a docs architecture change.** Between the audit PR and the fix PR, master had migrated from `generate_docs.py` + `docs/` to `gen_pages.py` + `docs-src/` (ADR-0007). The AF-007 commit's changes to the deleted `generate_docs.py` were dropped during conflict resolution; the Azure guide was already in the new nav structure.

```
85b8c9c  AF-005: Add DirectoryNotEmpty error type
2fd16ab  AF-002: Remove ghost GLOB and RECURSIVE_LIST capabilities
305243d  AF-001: Auto-register S3, SFTP, and S3-PyArrow backends
f3b0152  AF-003: Remove clear_instance_cache() from S3 close()
688f996  AF-004: Fix SFTP get_folder_info on empty folders
c56aca2  AF-006: Map native exceptions from lazy read streams
fade101  AF-007: Wire Azure guide into docs site
309b00b  Bump version: 0.5.0 -> 0.6.0
```

### Phase 14: Release Checklist (process improvement)

Expanded the 5-item release checklist into a 6-phase process (pre-flight, content freeze, version bump, validate, ship, post-release verification). The motivation: despite thorough process documentation — specs, CLAUDE.md principles, CONTRIBUTING.md conventions, PR templates — past releases still had preventable errors (v0.6.1 bumped but never published, CITATION.cff dates missed, no post-publish verification). Process docs govern how to build; a release checklist governs how to ship. One doesn't replace the other.

### Phase 15: Reusable Skills (collaborative process mining)

After ~165 commits of human-AI pair programming, recurring friction points had become visible in the data: 7 of 9 audit-fix commits forgot to update the backlog, 62% of code changes skipped the CHANGELOG, version-file sync was missed repeatedly, and cross-reference consistency (the "ripple check") was manual and error-prone. These weren't knowledge gaps — the rules existed in CLAUDE.md, CONTRIBUTING.md, and PR templates — but they lived in prose that had to be re-read and re-applied every session.

The fix was to extract the patterns into executable checklists: 6 slash-command skills in `.claude/commands/` that Claude Code can invoke directly. Each skill codifies a workflow that had been learned through trial and error across multiple sessions:

- **`/ripple-check`** — the cross-reference table from CLAUDE-REFERENCE.md, turned into an actionable checklist
- **`/release`** — the 6-phase release process, with every file and command spelled out
- **`/add-backend`** — 12-step backend scaffolding (the exact sequence that tripped up AF-001)
- **`/backlog-sync`** — enforces "same commit" backlog updates
- **`/pr-preflight`** — 11 checks covering the historically-missed items
- **`/add-spec`** — SDD spec + test scaffolding with the right markers

The interesting insight: **the skills weren't designed top-down — they were mined from failure patterns.** The commit history told us exactly which steps got forgotten and how often. The backlog-sync skill exists because 78% of tagged commits forgot the backlog. The CHANGELOG check in pr-preflight exists because the majority of code changes skipped it. Each skill is a scar from a past mistake, formalized so it doesn't recur.

This is a natural evolution of the human-AI workflow: the human defines principles (CLAUDE.md), the pair discovers where those principles get violated in practice (PR reviews, audits), and the violations get codified into guardrails (skills) that the AI can follow without re-deriving them each session. The principles stay high-level; the skills handle the mechanical enforcement.

### Phase 16: Extensions and Ecosystem (v0.9.0)

Three new capabilities shipped in a single minor release, all following the `ext.*` pattern established by the PyArrow adapter:

- **`ext.batch`** (ID-022) — `batch_delete`, `batch_copy`, `batch_exists` with error aggregation via `BatchResult`. The pattern of "call Store methods one-by-one, collect errors into a result" proved clean enough to template future extensions.
- **`ext.transfer`** (ID-023) — `upload`, `download`, `transfer` for local-file-to-store and cross-store data movement. Unified two long-standing backlog items (ID-001 cross-store transfer, ID-009 upload/download) into three streaming functions with progress callbacks. The `_ProgressReader` wrapper reuses the `cast("BinaryIO", ...)` + `__getattr__` delegation pattern from the PyArrow adapter.
- **PyArrow FileSystem adapter Phase 1** (ID-016) — `StoreFileSystemHandler` wraps any Store into a `pyarrow.fs.PyFileSystem`, enabling interop with Parquet, Pandas, Polars, DuckDB, and dataset discovery. The tiered read strategy (BufferReader for small files, PythonFile for large seekable files) and `_StoreSink` spill-to-disk write buffer were the most architecturally complex additions since the backends themselves.

Supporting work included a concurrency guide (AF-010), capability gating tests (AF-012), error path tests for S3/SFTP (AF-013), a CI gate on the publish workflow (AF-014), and cleanup of stale capability declarations (ID-019).

The `ext.*` namespace is proving to be a good layering decision: extensions compose on the public Store API without backend coupling, so they work with `Store.child()`, capability gating, and any future backend. Each extension is pure Python (except PyArrow which requires its optional dep), independently testable, and unconditionally exported from the top-level package.

### Phase 17: Instrumentation and Optimization (v0.10.0)

Four infrastructure improvements shipped together: the extension namespace contract (ADR-0008) formalized `ext.*` rules that had been implicit, the S3-PyArrow read path optimization (RFC-0003) eliminated double-buffering in streaming reads, benchmark tiered modes replaced the binary slow/not-slow split with three tiers (quick/standard/full) plus comparative reporting, and the release/docs CI was unified around GitHub Releases as the single trigger.

### Phase 18: Beta and Glob (v0.11.0)

Two milestones in one release. The glob feature (ADR-0009) introduced a three-tier design: universal `fnmatch` filtering via `list_files(pattern=)`, capability-gated native `Store.glob()` (Local-only initially), and a portable `ext.glob.glob_files()` fallback with recursive `**` patterns. S3/Azure native glob remains planned.

The project also graduated from Alpha to Beta. After 18 specs, 9 ADRs, 1040+ tests, and 4 extensions, the core API surface (`Store`, `Registry`, `Backend`, models, errors) was declared stable. A stability tiers table was added to CONTRIBUTING.md to formalize the contract: Beta means breaking changes are documented and avoided where possible, while extensions may evolve more freely.

### Phase 19: Cloud Glob and Conda (v0.12.0)

The glob story completed. v0.11.0 shipped with native glob only for LocalBackend; now S3, S3-PyArrow, and Azure all override `Backend.glob()` with prefix-optimized listing and client-side regex filtering (GLOB-018/019/020). Shared helpers were extracted to an internal `_glob.py` module to avoid duplicating prefix extraction and regex compilation across backends. All four file-capable backends now declare `Capability.GLOB`.

On the infrastructure side, a conda-forge recipe was added (`packaging/conda-forge/recipe.yaml`, v1 CEP-13 format) with CI validation via `rattler-build --render-only`. The release checklist gained conda-specific steps: version bump in Phase 2, version match check in Phase 3, and sha256 update in Phase 5. Benchmark fixtures were fixed to invalidate fsspec listing caches (ID-032), and the 1000-file listing test was moved from quick to standard tier (ID-033).

This release also demonstrated iterative self-review: the `/review-pr` skill (added in PR #76) was used to review its own PR and subsequent conda PRs, catching real consistency gaps each time — including a non-existent GitHub Action, a premature version bump, and a missing staging step in the release checklist.

### Phase 20: Research Before Implementation (post-v0.12.0)

Three backlog items (ID-002 YAML config, ID-003 Pydantic adapter, ID-005 TOML config) had been sitting in the Ideas tier for months. Rather than jumping to implementation, the approach was to write a research document first: `sdd/research/research-store-config.md`. The document mapped the design space — config formats, library choices, API surface, ecosystem compatibility — before committing to any implementation decisions.

**The research went through four review rounds, and each round found real problems:**

| Round | Approach | Findings |
|-------|----------|----------|
| 1 | Substantive review (fresh session) | 10 gaps: no fsspec analysis, no credential chain patterns, no Airflow/Hydra/dynaconf evaluation, secrets management hand-waved |
| 2-3 | Inline review comments | Factual errors: `boto3` attribution wrong (S3Backend uses `s3fs` -> `aiobotocore` -> `botocore`), `endpoint_url` placement incorrect, `HostKeyPolicy` Enum case wrong |
| 4 | Challenge review (adversarial session) | 7 gaps: `from_dict()` silently ignores unknown keys, YAML import precedence undermines YAML 1.2 intent, `SecretStr` + `model_dump()` negates secret protection, config discovery and schema versioning unaddressed |

**The most valuable discovery was a real pre-existing bug.** The research process — not a test, not a linter, not a code review — found that `SFTPBackend.__init__` stores `host_key_policy` as a raw string without Enum coercion. When config loaders pass `"strict"` (a string from TOML/YAML), the Enum comparisons in `_create_ssh_client()` silently fail because `"strict" != HostKeyPolicy.STRICT` in Python. The result: host key verification silently degrades to the least secure mode. This bug existed since v0.2.0 and was invisible to every test, type checker, and code review because no test exercised the string-to-Enum path — they all used the Enum directly.

**The lesson has two parts:**

First, **research documents catch design-level bugs that code-level tools miss.** The Enum coercion bug was invisible to mypy (both types are valid kwargs), invisible to tests (tests use Enum values, not strings), and invisible to code review (the constructor looks correct in isolation). Only by thinking through "what happens when a TOML parser sends a string here?" did the failure path become apparent. Thinking through integration scenarios on paper is cheaper than debugging them in production.

Second, **research quality improves dramatically under adversarial review.** The first draft was described as "an implementation plan wearing a research hat" — it proposed solutions before demonstrating that alternatives were studied. Four rounds of review transformed it into a genuine landscape analysis with explicit decisions, documented trade-offs, and scoped-out concerns. Each round found issues the previous round missed because each reviewer brought a different framing: the first focused on external landscape completeness, the second on factual accuracy, the third on internal consistency, the fourth on edge cases and missing explicit decisions.

The final document (1,250 lines) covers 8+ ecosystem tools, maps all 6 backends' config surfaces, provides implementation sketches, resolves ADR-0002 tension with Pydantic, and captures 9 open design questions with reasoned recommendations. All of this exists before a single line of implementation code is written — and the implementation spec can now cite specific decisions with ecosystem evidence rather than asserting them without context.

### BUG-001: When Your Value Object Has No Word for "Here" (post-v0.12.0)

`RemotePath` — the immutable path value object at the heart of every Store operation — could represent any path *except* the root folder. Both `RemotePath("")` and `RemotePath(".")` raised `InvalidPath` by design (PATH-008). This was fine until `get_folder_info("")` needed to return metadata about the root folder itself. All six backends tried to construct `FolderInfo(path=RemotePath(""))` and crashed.

The fix was a class-level sentinel: `RemotePath.ROOT`, created via `object.__new__` to bypass `__init__` validation, with an internal path of `"."`. The constructor still rejects `""` and `"."` — `ROOT` is the only way to get a root-folder path, and it's a singleton.

**The interesting part was the bug's discovery path.** It wasn't found by tests, type checking, or code review. It was found by an external code analysis tool scanning for edge cases in `RemotePath` construction across all backends. The four regression tests were written *before* the fix — a pattern that made the fix trivially verifiable. Write the failing test first, then make it pass.

The fix also surfaced two related consistency issues (now tracked as ID-040 and ID-041): `move(src, dst)` behaves inconsistently when `src == dst` across backends, and `Registry.get_store()` returns stores that can accidentally close a shared backend. Neither crashes today, but both are foot-guns waiting for the right trigger. **Edge-case audits don't just find the bug you're looking for — they find the bugs next to it.**

### Phase 21: Observability and Credential Hygiene (v0.13.0)

This release shipped two new extensions and a security hardening layer, all following the established `ext.*` pattern:

- **`ext.observe`** (ID-024) — callback-based observability hooks. `observe(store, on_read=..., on_write=..., on_any=..., around=...)` wraps a Store in an `ObservedStore` proxy that fires `StoreEvent` callbacks after each operation. A `BufferedObserver` queues events for batched delivery on a background thread. A drift-protection test ensures new Store methods cannot silently bypass observation.
- **`ext.otel`** (ID-024) — pre-built OpenTelemetry bridge. `otel_observe(store)` wraps a Store with distributed tracing spans and three metric instruments (operations counter, errors counter, duration histogram). Depends only on `opentelemetry-api` for zero-cost no-ops without an SDK configured. New optional extra: `pip install "remote-store[otel]"`.
- **`Secret` wrapper** (ID-039) — credential hygiene layer in `_config.py`. `Secret` wraps sensitive strings so that `repr()` and `str()` return `'***'` while `.reveal()` returns the plain value. `RegistryConfig.from_dict()` auto-wraps known sensitive keys. All backends accept `str | Secret` via `_reveal()`. A `SecretRedactionFilter` logging filter scrubs secrets from log output.

The `Secret` wrapper emerged from the config loaders research (Phase 20). While mapping out how TOML/YAML config values flow into backend constructors, the research identified that credential strings were stored and logged in plain text throughout the library. Rather than waiting for config loaders to ship, the credential hygiene layer was extracted as a standalone improvement — a case of research producing immediate value before its primary deliverable.

The release also fixed BUG-001 (`get_folder_info("")` crashing for root folders) and added intrinsic stdlib logging to all modules (ID-004), completing the three-layer observability stack: Layer 1 (stdlib logging), Layer 2 (`ext.observe` callbacks), Layer 3 (`ext.otel` OpenTelemetry).

### Phase 22: Config Loaders and Consolidation (v0.14.0)

Phase 20's research document finally paid off. Three config loaders shipped in a single PR: `RegistryConfig.from_toml()` (zero-dep on 3.11+, `tomli` backport for 3.10), `RegistryConfig.from_yaml()` (pyyaml or ruamel.yaml), and `pydantic_to_registry_config()` in the new `ext/pydantic.py` module. The research had mapped every design decision in advance — format precedence, library fallback chains, `SecretStr` interaction, unknown-key detection — so implementation was a matter of following the blueprint. `from_dict()` also gained a `UserWarning` for unrecognized top-level keys like `"backend"` (typo for `"backends"`), a gap the Phase 20 adversarial review had flagged.

Alongside the loaders, three "Tier 1" fixes addressed foot-guns the research had surfaced: `Registry.get_store()` no longer owns the shared backend (ID-041), `move()`/`copy()` short-circuit when `src == dst` (ID-040), and `_stacklevel` was removed from the public `from_dict()` signature (ID-043). The last one was a strict application of a project rule: no private parameters on public APIs, ever.

**The consolidation work was as significant as the features.** Both SFTP and Memory backends reached 100% test coverage (BK-005, BK-006) — 65 new tests covering every uncovered branch. The slim-tests effort (PR #116) then went the other direction: collapsing verbose test functions into `@pytest.mark.parametrize` tables and extracting a shared `RestrictedBackend` fixture into `conftest.py`, saving ~940 lines while preserving every test case. This was lesson #15 in practice — write tests verbosely, then compress once patterns emerge.

A design-compliance audit (AF-016 through AF-021) swept the codebase for spec drift: glob capabilities missing from three backend specs, method ordering violations in `_store.py` and all six backends, an unlinked TODO in `ext/arrow.py`. These were individually minor but collectively represented the kind of slow rot that compounds across releases.

Three more research documents were added to the `sdd/research/` collection: unified retry policy (ID-010), v1 communication strategy, and example testing patterns across language ecosystems. The research-first pattern from Phase 20 was becoming habitual — map the space on paper before committing to implementation.

The data lake patterns guide (ID-034) demonstrated that existing features could combine into something greater than the sum of their parts. `Store.child()` + `ext.arrow` + `ext.transfer` already supported Bronze/Silver/Gold medallion architectures — the guide just documented the patterns. No new code was needed; the API surface was already sufficient.

### Phase 23: Extensions and Documentation (v0.15.0)

This release was the most extension-heavy yet — three new extensions and major enhancements to an existing one, all backed by specs and full test suites.

**Streaming atomic writes** (`Store.open_atomic()`, ID-026) extended the existing `write_atomic()` with a context manager that yields a writable file object, eliminating the need to buffer large files in memory before writing. The implementation required careful attention to error mapping boundaries: SFTP's context manager had to yield *outside* the `_errors()` scope so user exceptions wouldn't get remapped as storage errors. RFC-0004 documented the design, and all six backends got per-backend temp-path strategies.

**Store-level caching** (`ext.cache`, ID-025) added TTL-based read caching with automatic invalidation on mutations. A subtle CPython dict behavior bit us: `dict.__setitem__` on an existing key does *not* move it to the end, breaking LRU eviction. The fix — `del` then re-insert — was simple but the bug was invisible in unit tests and only appeared under specific access patterns.

**Parallel batch operations** (ID-035) added `concurrent=True` to `batch_delete`, `batch_copy`, and `batch_exists`, using `ThreadPoolExecutor` from stdlib. The design explicitly made `stop_on_error` incompatible with concurrency — a `ValueError` rather than silent misbehavior.

**Hive-style partition helpers** (`ext.partition`, ID-036) provided pure-Python path builders and parsers for partition schemes like `year=2026/month=03/data.parquet`. A review caught that `=` in partition values would break round-trip parsing — rejected at construction time.

**PyArrow Tier 1 native fast-path** (ID-037) completed the PyArrow adapter's Phase 2: `StoreFileSystemHandler` now probes for a native PyArrow filesystem at construction and dispatches reads directly to C++ for zero-GIL overhead. Benchmarks showed 1.6-2x improvement on S3-PyArrow.

**The documentation overhaul** (DOC-001) was the largest non-code effort yet: full Diataxis restructure, 9 extension API reference pages, 7 new content pages, docstring audit for Store/Backend/errors, and cross-links throughout. Lesson #16 emerged: adopt a documentation framework early. Retrofitting Diataxis onto an existing flat site required reclassifying every page and rebuilding navigation.

**E2E integration tests** (ID-050) validated six extensions working together in a full data lake pipeline against Docker backends (MinIO, Azurite). A cross-layer assertion lesson: don't assert `gold_bytes < silver_bytes` — aggregation adds computed columns that can make Gold larger despite fewer rows. Use row counts for aggregation invariants.

### Phase 24: Developer Experience and Tooling (post-v0.15.0)

Four PRs (#170--#173) landed in a single day, each small but collectively shaping the developer experience story.

**API ergonomics through convention** (ID-056, ID-055). `read_text()` and `iter_children()` followed pathlib's API conventions deliberately — same parameter names (`encoding`, `errors`), same return semantics. The lesson: when your audience is citizen developers, matching stdlib patterns reduces the API surface they need to learn to zero.

**Learning from other projects' toolchains** (#171, #173). A research pass on FastAPI's documentation setup (PR #171) revealed that mkdocstrings already supported colored, cross-linked type annotations — just not enabled. A 4-line config change (`separate_signature`, `signature_crossrefs`, `show_symbol_type_heading`, `show_symbol_type_toc`) in PR #173 gave the API reference the same visual quality that FastAPI is known for. Lesson: before building, check if your existing tools already support the feature.

**uv adoption, incrementally** (#173). CI moved from pip to uv across three workflows (ci.yml, publish.yml, then docs.yml). The key insight: uv replaces pip *for installation speed in CI*, not hatch for local development. Locally, `hatch run` remains the interface — it manages environments, scripts, and matrix testing. uv is a CI concern only, cutting install steps from ~45s to ~8s.

**Cross-platform as a first-class constraint.** The Win/macOS/Linux test matrix surfaced patterns that became project conventions: errno codes instead of string matching (German locale breaks English error messages), closing streams before `shutil.rmtree()` (Windows file locking), ASCII-only `print()` (cp1252 codec), and em-dash avoidance in Markdown titles (mojibake via MkDocs). These aren't edge cases — they're the default experience for half the target audience.

**Ripple-check strengthening** (#172). The CLAUDE-REFERENCE.md ripple-check table gained more specific verification targets: Store method changes now explicitly require README API table + method count updates, extension changes require docs nav + API reference pages. The README audit in the same PR caught 3 missing examples and a stale method count — exactly the kind of drift the table is designed to prevent.

### Phase 25: API Conveniences and Documentation Quality (v0.16.0)

The v0.16.0 release bundled the post-v0.15.0 work into a cohesive minor release: new convenience APIs (`read_text()`, `iter_children()`, `ping()`), the `RetryPolicy` configuration surface, the YAML config loader move to `ext.yaml`, and a documentation quality audit (Audit 003) that fixed 16 findings across guides, docstrings, and examples. The `SFTPUtils` public utility class replaced private imports in user-facing code, and `from_yaml()` moved to the extension layer for consistency with the Pydantic adapter.

The release also shipped colored type annotations in the docs site (mkdocstrings config), uv-based CI installs across all workflows, and cross-platform CI (Windows + macOS). The documentation audit reinforced Principle 17 from the lessons section: audit findings are hypotheses, not prescriptions. Three of the 19 findings were closed as non-defects after investigation.

### Phase 26: The Polish Phase — What Happens After "Feature Complete" (post-v0.16.0)

After v0.16.0, the project had every feature it needed for beta. What followed was not a cooldown — it was the densest learning period yet. Twelve PRs in four days exposed problems that only become visible when you stop adding features and start examining what you already have.

**Consistency bugs are invisible to tools.** `list_folders()` had been returning plain strings since v0.1.0 while every other listing method returned typed objects. Tests passed, mypy was happy — strings cooperate just enough. Only a systematic cross-method API audit (ID-074) surfaced the gap. The fix introduced `FolderEntry` and a `PathEntry` protocol unifying all listing return types. **Each callsite is locally correct; only a cross-method comparison reveals the inconsistency.**

**Research that says "no" is not wasted.** Two research documents produced the explicit decision *not* to build what they investigated. The async API research (ID-013) found it would double codebase/surface/docs with no clear audience benefit. The Dagster extension research (ID-073) concluded v1 should be a thin adapter — only if someone actually needs it. Both documents live in `sdd/research/`, so when someone asks "why no async?", the answer is a link, not a re-investigation.

**Fast failures that leave a record.** The Claude Code GitHub Action for automated PR review (ID-069) hit 18 sandbox permission denials, took ~10 minutes, and cost ~$2 per trivial PR. Added in one commit, reverted in the next. The revert documents the specific failure modes so nobody repeats the experiment.

**Choose docstring style by what your toolchain renders, not what looks best in source.** Sphinx `:param:` markers, `:class:` cross-references, and `.. note::` directives all rendered as plain text in mkdocstrings. The migration to Google style (ID-080, 367+ markers across 25 files) was driven entirely by rendered output, not preference. Review caught that dataclass docstrings need `Attributes:` not `Args:` — a distinction only visible in the rendered docs.

**Include-markdown makes every link potentially circular.** The README restructuring (ID-081) replaced the inline extras list with a link to getting-started. But `getting-started.md` includes README content via `include-markdown` — so the link would point back to itself. **The authoring context (README standalone) and rendering context (README included inside another page) see different link targets.**

**Encoding bugs survive by hiding in unchecked cells.** Em dashes were caught and fixed three times in the same PR — prose, then table headers, then table N/A cells. Each review round fixed the instances the reviewer checked; the rest survived. Em dashes render fine on Linux CI but produce mojibake on Windows cp1252. **Systematic encoding issues don't announce themselves — they hide in the specific cells you didn't look at.**

**Benchmark numbers without understanding the measurement are dangerous.** Azure comparative benchmarks showed remote-store 107x slower than `adlfs` at listing. Investigation revealed a fsspec caching artifact: `adlfs` caches after the first call, remote-store hits Azurite every iteration. Real overhead: 1.2x vs raw SDK — FileInfo/RemotePath construction cost. **The 107x would have been damning; the 1.2x is an acceptable design trade-off.**

**"Defensive" code that duplicates library guarantees is just overhead.** Three S3 listing methods had `exists()` guards before every call — an extra HEAD request each time. But `s3fs.ls()` already raises `FileNotFoundError` for missing prefixes. The guards doubled round-trips for zero benefit. **Know what your dependencies promise before adding safety nets.**

### Phase 27: Listing Normalization and API Consistency (v0.17.0)

The v0.17.0 release completed the API consistency work that Phase 26 identified. The headline change was listing normalization (ID-072): `list_folders()` shifted from returning bare strings to `FolderEntry` objects, and `iter_children()` from `FileInfo | str` to `FileInfo | FolderEntry`. A new `PathEntry` protocol unified all listing return types. `FolderInfo` gained a `.name` property (ID-079) so it also satisfies `PathEntry`. These changes made the listing API uniform — every method that returns path-bearing objects now returns typed objects with `.name` and `.path`.

Azure got `max_concurrency` support (ID-076), threading a single constructor parameter through all five SDK call sites. Benchmarks showed ~50% write and ~25% read improvement on 100MB payloads. `Store.write_text()` (ID-074) rounded out the convenience API started by `read_text()` in v0.16.0.

On the docs side, the full Sphinx-to-Google docstring migration (ID-080, 367 markers across 25 files) unlocked proper rendering in mkdocstrings. The README got a medium pass (ID-081) streamlining onboarding, and the docs site gained Fira Code, sticky tabs, and property type annotations (ID-064). S3 listing methods dropped their redundant `exists()` guards (ID-062) — a one-line change per method that halved round-trips.

### Phase 28: Middleware, Integrity, and "Eat Your Own Dogfood" (v0.18.0)

v0.18.0 was the middleware release. ADR-0014 introduced `ProxyStore` as an internal delegation base for `ObservedStore` and `CachedStore`, centralizing the boilerplate that both proxies duplicated. Two new extension modules landed alongside it: `ext.streams` (composable `BinaryIO` wrappers — `ProgressReader`, `ProgressWriter`, `ChecksumReader`, `ChecksumWriter`) and `ext.integrity` (store-level checksum verification via `checksum()`, `verify()`, `verify_hex()`). The `ContentDigest` frozen dataclass replaced the informal `FileInfo.checksum` field with typed `digest` and `etag` fields, and S3/Azure backends learned to populate them from server-side checksums.

The biggest lesson came from the BK-008 Medallion + Dagster showcase — a self-contained example composing four extensions over live MeteoSwiss weather data. AI-generated showcase code had three bugs that only surfaced when running against the real API: wrong data URLs, wrong column names and timestamp formats, and a cache bypass where `transfer()` uses streaming `read()` which `CachedStore` doesn't cache. All three passed type checking and looked plausible in review. **Running the code against live data caught what static analysis and code review could not.** This reinforced the project principle "run it, don't just type-check it" — and extended it to examples and showcases, not just library code.

The HTTP backend gained HEAD fallback (ID-085): when a CDN blocks HEAD requests with 401/403, the backend retries with `GET + Range: bytes=0-0` and caches the result. Discovered during live testing against opentransportdata.swiss. The docs site got a purpose-built landing page (ID-090) replacing the README include, and the API reference gained dedicated sections for backends (ID-088) and extensions (ID-089).

### Phase 29: Consolidation and Code Hygiene (v0.19.0)

v0.19.0 was a housekeeping release — no new features, just making the existing codebase smaller, more consistent, and easier to maintain.

The biggest theme was **deduplication across three layers.** BK-011 extracted `_S3Base` from the two S3 backends, consolidating 155 lines of duplicated listing, error handling, and FileInfo construction into a single base class (net -94 lines). BK-012 did the same for extensions: `_StreamWrapper` in `ext/streams.py` eliminated close/context-manager boilerplate from four stream wrappers, `_run_batch()` in `ext/batch.py` replaced two near-identical sequential/concurrent executors, and `_deprecated_alias()` in `ext/_helpers.py` turned three hand-written deprecation wrappers into one-liners. BK-014 then tackled the test suite: 30 of 40 test files were refactored (~17,800 -> ~16,300 lines, -8.6%) through parametrization, fixture extraction, and class merging — all while preserving identical coverage.

The naming pass (BK-010) renamed three extension factory functions (`pydantic_to_registry_config` -> `from_pydantic`, `remote_store_io_manager` -> `dagster_io_manager`, `cached_store` -> `cache`) to match existing `from_*` and bare-verb patterns. Old names remained as deprecated aliases — a one-line helper `_deprecated_alias()` (itself a product of BK-012) made this trivial.

Documentation got the same treatment. ID-057 introduced single-source code snippets (`examples/snippets/` with pymdownx named regions) so docs and tested code can't diverge. ID-058 automated example doc wrappers via `scripts/gen_pages.py` — scanning `examples/*.py`, extracting docstrings, generating pages. BK-013 added `## See also` sections to all 57 docs pages and linked backend names in comparison tables. And ID-099 consolidated SDD document categories from 7 to 5, merging `proposals/` into `rfcs/` and `plans/` into `research/`.

**The lesson from this phase is that deduplication compounds.** Each individual change was small, but together they removed ~300 lines of library code and ~1,500 lines of tests while making the codebase more navigable. The `_deprecated_alias()` helper that made BK-010 trivial only existed because BK-012 created it. The auto-generated example wrappers that eliminated a class of "forgot to add a wrapper" bugs only worked because BK-013 had already established cross-linking conventions. Housekeeping releases aren't exciting, but they create the infrastructure that makes future feature work faster.

### Phase 30: The Feature Explosion (v0.20.0)

v0.20.0 was the largest feature release since the project's inception — landing SQL backends, Parquet datasets, Dagster v2, a resolution introspection API, performance benchmarking infrastructure, and depth-limited listing in a single cycle.

**The output wasn't luck — it was infrastructure.** The previous three releases had built up the process scaffolding that made this pace possible. SDD guiding documents (specs, RFCs, research docs, TESTING.md, DESIGN.md) meant every feature started with a shared definition of "done" rather than ad-hoc discovery. The `/orchestrate` skill (BK-125, BK-128) let complex multi-concern tasks — like the SQL backends, which touched code, tests, docs, and specs simultaneously — be decomposed and executed with domain-expert agents in parallel. Skills codified repeatable workflows (release, audit, PR review) so process steps weren't reinvented each time. The compounding effect: each feature took roughly the same wall-clock time as a single-concern change in earlier releases, because the tooling handled the cross-cutting concerns that used to dominate elapsed time.

**Two SQL backends from one research spike.** ID-119 started as "should we use SQLAlchemy?" and produced two complementary backends sharing `_SQLAlchemyBaseBackend`: `SQLBlobBackend` (full read-write key-value store) and `SQLQueryBackend` (read-only query materializer). The blob backend exercises all 10 capabilities; the query backend introduces a new `ResultSerializer` protocol that maps path extensions to output formats. Research drove the split — one backend doing both jobs would have been an uncomfortable abstraction.

**Parquet datasets needed their own error hierarchy.** `ParquetDatasetStore` (ID-122) manages manifests, `_SUCCESS` markers, and atomic-commit semantics on top of Store primitives. Its failure modes (`DatasetIncomplete`, `ManifestCorrupted`) are domain-specific — they don't map to the generic `StorageError` hierarchy. Placing them in `ext.parquet` rather than `_errors.py` established the pattern that extension-specific errors belong in their extension modules.

**`resolve()` makes the invisible visible.** The `ResolutionPlan` API (ID-120) answers "how would this key be resolved?" without performing I/O. Every backend returns a frozen dataclass describing the storage location, backend identity, and backend-specific context. Security was non-negotiable: no credentials in details, userinfo stripped from URLs. The design anticipated `CompositeStore` (ID-121) — resolution plans compose naturally across backend tiers.

**Depth-limited listing required three specs in one.** ID-107 (Store-level `list_files`), ID-108 (`list_folders`), and ID-107b (backend-native optimization) delivered one user-facing feature — `max_depth=N` — but the implementation split across Store filtering, BFS traversal, and backend pruning. Local, SFTP, and Memory backends prune natively; S3/Azure accept the parameter but defer to Store-level filtering. The three-layer approach kept the Backend ABC change optional.

**Benchmarks that measure honestly.** The benchmark suite (ID-103, ID-104) was designed to present numbers (ms, %), not judgments ("negligible", "minimal"). Overhead-vs-RTT charts showed that remote-store's fixed cost becomes irrelevant at real-world latencies. The S3-PyArrow comparison revealed its strength is analytical workloads, not raw throughput — a distinction the messaging previously blurred.

**Dagster v2 rewrote the integration model.** The original `dagster_io_manager()` wrapper (v1, ID-075) was a function-based adapter. v2 (ID-083) introduced `DagsterStoreResource` (ConfigurableResource) for direct Store access and `RemoteStoreIOManager` (ConfigurableIOManagerFactory) for config-driven IO management. The migration exposed Dagster-Pydantic quirks: `PrivateAttr` must come from `pydantic` not `dagster`, `ResourceDependency` needs runtime wiring, and docstrings use `Attributes:` not `Args:`.

**Test quality enforcement closed the loop.** BK-126 added AST-based CI checks for assertions and mock specs, then migrated all 67 unconstrained mocks and 87 assertion-less tests. Combined with mutation testing scripts (BK-131) and Ruff PT rules (BK-124b), the test suite went from "tests exist" to "tests prove something." The deprecated aliases removed in BK-130 were the last remnants of the v0.19.0 naming cleanup — pre-v1, no shim needed.

### Phase 31: Async, Config, and Quality Hardening (v0.21.0)

v0.21.0 was an async-first release — the first to ship a fully native async storage layer alongside config ergonomics and a behavioral correction in the Parquet serializer.

**Async arrived in two deliberate phases.** Phase 1 (ID-013) delivered the `remote_store.aio` module: `AsyncStore`, `AsyncBackend` ABC, `SyncBackendAdapter` (thread-pool wrapper for any sync backend), and `AsyncMemoryBackend` for testing. Phase 2 landed `AsyncAzureBackend` — the first native async backend, using Azure SDK async clients (`azure.storage.blob.aio`, `azure.storage.filedatalake.aio`) for true non-blocking I/O. Shared helpers extracted to `_azure_common.py` kept the sync and async Azure backends DRY. **Phasing meant each layer was tested and reviewed independently, rather than shipping a monolithic async rewrite.** Phase 3 (async extensions) is deferred — Dagster has no public async IO manager interface yet, so there's nothing to wrap.

**`resolve_env()` closed the last config gap.** ID-126 added `${VAR}` and `${VAR:-default}` interpolation for config dicts. `from_toml()` and `from_yaml()` gained `resolve_env_vars=True`; a standalone `resolve_env()` function is exported for custom loaders. The design deliberately avoids recursive resolution and fails loudly on unresolved placeholders — security over convenience.

**A hidden pandas dependency surfaced in the Parquet serializer.** BUG-135 found that `ParquetSerializer.deserialize()` called `table.to_pandas()`, silently requiring pandas for `remote-store[dagster,arrow]` users. The fix returns `pyarrow.Table` directly — framework-neutral, no hidden dependencies. This was the project's first behavioral breaking change to an extension, handled via migration guide rather than a deprecation cycle (pre-v1 policy).

**Dagster multi-partition loading completed the IO manager story.** ID-124 taught `load_input` to return `dict[str, Any]` when the input context carries multiple partition keys (time-window aggregation), covering the last gap deferred from the v0.20.0 Dagster v2 work.

**Test quality hardening was the quiet backbone.** BK-137 audited the new async and Dagster tests against TESTING.md rules, fixing behavioral assertion gaps and parametrizing copy-paste tests. BK-134 replaced `isinstance`-only assertions and private attribute checks across 10 test files. BK-135 fixed 72 `ResourceWarning: unclosed database` warnings in SQL tests. Coverage for `_azure_common` went from 69% to 100%. **The test suite grew from ~2,500 to ~3,100 tests while getting stricter about what each test actually proves.**

### Phase 32: Backend Hardening (v0.21.1)

v0.21.1 was a pure bugfix release — no new features, no API changes. A systematic audit examined every backend for error-handling gaps, resource leaks, and behavioral inconsistencies. The result: 22 bugs filed, 21 fixed, 1 closed as non-defect (BUG-149).

**Defensive cleanup at the boundary.** The most common pattern was resources leaking when stream-wrapping failed. SFTP (BUG-142) and Azure (BUG-158) both had code paths where `_ErrorMappingStream` or `BufferedReader` construction could fail after acquiring a file handle, leaving the underlying handle unclosed. The fix was uniform: acquire, wrap in try/except, close on failure.

**Error suppression scope was consistently too broad.** SFTP's `listdir_attr` (BUG-146), `_ensure_parent_dirs` (BUG-145), and `delete_folder` (BUG-147) all caught generic `IOError` when they should have caught only ENOENT or EEXIST. The pattern: tighten exception handling to the narrowest errno that the code path actually needs to suppress. The same discipline applied to `LocalBackend`'s `IsADirectoryError` leaks (BUG-153, BUG-154) — the fix was mapping to the correct `RemoteStoreError` subclass rather than letting platform-specific exceptions escape.

**`max_depth` was a specification gap.** S3 (BUG-152) and Azure (BUG-155) both accepted `max_depth` but ignored it during listing traversal. The BFS implementations needed depth tracking at the traversal level, not post-hoc filtering. Local and Memory backends already had this right — the fix was aligning the cloud backends to match.

**`CachedStore` had two invalidation blind spots.** Writing a nested path didn't invalidate ancestor directory metadata (BUG-137), and `child()` created an isolated cache instead of sharing the parent's (BUG-138). Both are subtle because they only manifest in multi-level directory structures with interleaved reads and writes.

**Housekeeping shipped alongside.** Examples were reorganized from a flat directory into seven topical subdirectories. The Pygments upper-bound pin was removed after pymdown-extensions fixed the upstream bug. `pyproject.toml` dependency lists were deduplicated via Hatch's `features` key (BK-138).

### Phase 33: Formal Verification as a Quality Gate (v0.22.0)

v0.22.0 crossed a line the previous releases were building toward: mathematically verified correctness running as part of the regular test suite.

**The Dafny oracle became a conformance gate.** The formal `MemoryBackend.dfy` (53 verified proofs, 0 errors) was compiled to Python via `dafny translate py` and registered as `DafnyOracleBackend`. It now runs through all 150 conformance tests on every CI run. If the oracle passes a test, the test is known-correct by construction — the test suite validates itself against a machine-verified reference. Handwritten oracle prototypes from the POC phase were deleted; the compiled oracle supersedes them.

**A new capability flag exposed an atomicity gap.** `Capability.ATOMIC_MOVE` was added to mark backends where `move()` is guaranteed atomic under concurrent access. Local, Memory, and SQLBlob declare it; S3, S3-PyArrow, Azure, and SFTP do not (all use copy-then-delete semantics). This made atomicity a queryable property — `store.supports(Capability.ATOMIC_MOVE)` — rather than documentation-only knowledge. The Dafny formal layer was updated in parallel.

**Extended conformance: postconditions become tests.** 42 new test functions (~53 parameterized cases per backend) were derived directly from Dafny `BackendContract.dfy` postconditions. They cover error fidelity, precondition ordering, listing completeness, depth filtering, move/copy semantics, resource cleanup, and operational consistency. Marked `@pytest.mark.extended_conformance` for CI isolation. Error fidelity testing at this level immediately surfaced `InvalidPath` vs `NotFound` inconsistencies across backends (ID-131).

**Type-mismatch errors were systematically wrong.** `read()`, `read_bytes()`, `delete()`, and related methods on wrong path types (file vs. directory) raised `NotFound` in several backends when the Dafny postconditions required `InvalidPath`. Fixed uniformly across LocalBackend, MemoryBackend, and SFTPBackend. Self-move and self-copy were also fixed: `src == dst` is now a no-op rather than leaking `SameFileError` or losing data.

**Two bug-prevention mechanisms shipped.** `ResourceWarning` `__del__` guards were added to SFTPBackend, AzureBackend, and AsyncAzureBackend — if `.close()` was never called, Python's garbage collector now emits a warning at the object boundary rather than silently leaking connections. The Ruff `BLE001` rule (blind exception) was enabled across the codebase; 44 intentional broad catches were annotated with `# noqa: BLE001`, making accidental new catches visible immediately.

**What changed in the way of working.** This release showed that formal verification and test generation aren't separate activities — the same Dafny spec that proves the algorithm correct also produces the test oracles and reveals the gaps in the real backends. The investment in `sdd/formal/` from BK-140 paid a concrete dividend: the compiled oracle and the extended conformance suite are direct outputs of the formal layer, not additional work.

### Phase 34: Security Hardening (v0.22.1)

v0.22.1 was a pure security and code-quality patch — no new features, no API changes.

**Static analysis caught real issues.** Enabling the CodeQL `security-and-quality` query suite (BK-142) surfaced 31 findings. Most were code style (unused imports, `...` no-ops in Protocol stubs), but a handful were genuine: SFTP `known_hosts` was created with `0o644` instead of `0o600`, making it world-readable; `__del__` cleanup logic was complex enough to risk exceptions swallowing errors; `ProxyStore` skipped `super().__init__()`; empty `except/pass` blocks swallowed exceptions silently. All 31 were resolved in BK-143.

**The ruff/CodeQL interaction was non-obvious.** A follow-up pass fixed a subtle interplay: ruff's `TCH003` rule moves `BinaryIO` to a `TYPE_CHECKING` block and `TC006` auto-quotes `cast(BinaryIO, x)` → `cast("BinaryIO", x)`. Both transformations make `BinaryIO` appear unused to CodeQL at runtime. Fix: suppress both rules so the symbol stays as a live runtime import directly referenced by `cast()`.

**Patch releases keep the codebase trustworthy.** Not every release adds features. v0.22.1 demonstrates that security findings from static analysis are worth a PyPI publish — users running automated vulnerability scans should see clean results.

### Phase 35: Streaming Hardening and Documentation Systems (v0.23.0)

v0.23.0 fixed a deep-seated streaming problem that had been latent since the Azure backend was first written, then invested heavily in preventing the same class of problem from appearing in documentation.

**Azure was silently buffering entire files.** `AzureBackend.write()` called `upload_blob()` after reading the full stream into a single `bytes` buffer (BUG-161). For large files this was an OOM waiting to happen, and it violated the streaming contract the library promised. The fix introduced staged-block upload with a configurable `max_block_size` default — the same pattern the Azure SDK recommends for production workloads. The companion `BUG-162` fix standardized the copy-layer buffer to 256 KiB across all backends: the Windows default of 1 MiB was causing the end-to-end pipe tests to show two simultaneous live chunks rather than one.

**`Capability.LAZY_READ` made streaming quality queryable.** The distinction between "fetches data on demand" (S3, SFTP, Azure, Local, HTTP) and "loads the file before returning a stream" (Memory, SQLBlob, SQLQuery) had always been true but was invisible to callers. Adding `LAZY_READ` as a quality flag made it explicit — `store.supports(Capability.LAZY_READ)` is now a first-class check, not documentation archaeology. The Dafny formal layer was extended in parallel to verify the `GetFolderInfo` aggregate postcondition (`file_count == |ChildFiles(fs, path)|`, `total_size == SumSizes(…)`) — the first spec item that required ghost set tracking and a bespoke induction lemma.

**Documentation content rules codified a practice that was already working.** The project had been pulling code examples from `examples/snippets/` rather than writing them inline for several releases. BK-148 wrote that down as `sdd/CONTENT-RULES.md` — six rules about longevity: no exhaustive enumerations, no pseudo-precise counts, no copy-paste of things that have a single source of truth. BK-149 applied those rules retroactively to the existing guides, removing stale counts and replacing hardcoded lists with shape descriptions. The lesson: good practices need to be rule-codified before they can be enforced, not after.

### Phase 36: WriteResult, Async Bridges, and the Audit Flywheel (v0.24.0)

v0.24.0 was the largest API surface addition since the async layer in v0.21.0. It completed the write story — every write operation now returns structured metadata — and finished the two-direction async bridge needed to unblock future backend work.

**WriteResult closed the "write is a void" gap.** Before v0.24.0, callers who needed the etag, digest, or modified timestamp of what they had just written had to perform a separate `get_file_info()` round trip. `WriteResult` collapsed that: `write()`, `write_atomic()`, and their `open_atomic` counterpart all return a frozen dataclass with `path`, `size`, `source`, `digest`, `etag`, `version_id`, `last_modified`, and `metadata`. Two new capability flags accompanied it: `WRITE_RESULT_NATIVE` signals that rich fields come from the backend's write response (no extra round trip); `USER_METADATA` gates the `metadata=` kwarg so callers know whether attached key/value pairs will be persisted. `Store.head()` rounded out the feature: metadata retrieval without a content read. The Dafny `BackendContract.dfy` was widened in parallel to encode `WriteResult` postconditions as machine-verified obligations — the formal layer kept pace with the API.

**`AsyncBackendSyncAdapter` completed the bridge picture.** `SyncBackendAdapter` (v0.21.0) let sync backends be used from async code via `asyncio.to_thread`. The missing direction — using an async backend from sync code — now has `AsyncBackendSyncAdapter`: a public class that runs the async backend on a private daemon-thread event loop. The design required solving non-trivial problems: streaming reads across the thread boundary (`_ChunkPullReader` as `io.RawIOBase`), `open_atomic` synthesis from `write_atomic`, capability translation (masking `SEEKABLE_READ`, forwarding the rest), a fail-fast guard for callers already on an event loop, and a best-effort GC-path cleanup via `__del__`. The resulting spec block (ASYNC-080…093) was the most detailed in the codebase.

**The audit flywheel accelerated.** The project ran two overlapping audit cycles during this release. Audit-009 (backend-specifics visibility) produced 20 findings; BK-153 resolved them all by adding a three-tier admonition vocabulary to the API reference. Audit-011 (v0.23.0+ doc gaps) found 16 gaps introduced since the last release — new API surface (WriteResult, metadata=, aio.ext.write) that hadn't made it into the guides. BK-162 resolved all 16. The pattern that emerged: audit → findings → BK item → resolution within the same release cycle. At this cadence, documentation debt doesn't compound.

**TLA+ moved from PoC to a live layer.** The TLA+ work from v0.22.0's research phase (ID-147b) produced `Observer.tla` — six invariants covering the observer dispatch protocol (OBS-003 step 6/7 outcome routing). The formal layer now has two distinct tools: Dafny for per-operation contracts, TLA+ for cross-layer protocol properties. A non-blocking `verify-tla` CI job runs the TLC model checker on every push, with a revisit cadence (ID-150) to decide whether to promote it to a gate once a real regression is caught.

### Phase 37: The Documentation Graph and a Repeat S3 Bug (v0.24.1)

v0.24.1 was the first release driven primarily by *generators* rather than features. Most of the changelog is internal infrastructure: a graph IR over the codebase, projections back into `FEATURES.md`, and verifiers that compare the rendered API reference against that IR.

**The graph IR closed the loop between code and docs.** RFC-0012 introduced a single `graph.json` artifact (capability/class/extra/method/requirement/package nodes; declares/gates/of/enables/mirrors/inherits edges) generated by `scripts/gen_graph.py`. Three preconditions made static extraction possible: every backend now declares `CAPABILITIES: ClassVar[CapabilitySet]`, the gate map lives as `_GATING: dict[str, Capability]` in `_store.py`, and async backends point at their sync peer via `__mirror__`. With the IR in place, two projections fell out: `gen_features.py` regenerates the mechanical sections of `FEATURES.md`, and `check_api_docs.py` walks `graph.json` and the rendered API pages in parallel and flags missing `:::` directives or capability admonitions that drift from `_GATING`. The first run caught a misplaced `Capability.GLOB` admonition in `store.md` — a class of drift that previously needed a human reviewer to spot. An interactive D3 visualisation of the graph (`gen_graph_viz.py`) ships as a static HTML artifact for navigation.

**BUG-185: the same class of bug landing twice.** v0.24.0 fixed BUG-178 (S3 `config_kwargs` collision) by routing every botocore Config option through `client_kwargs["config"]`. That fix held against the unit suite — but the unit suite mocked at the `s3fs.S3FileSystem` boundary, one layer above where the actual collision fires. When a user reported `TypeError: got multiple values for keyword argument 'config'` against an internal MinIO endpoint, the cause was that s3fs's own `set_session()` always passes `config=AioConfig(**self.config_kwargs)` to `aiobotocore.create_client()`, so any `client_kwargs["config"]` injected by us duplicated `config=`. The fix this time routes every Config option through `opts["config_kwargs"]` (a plain dict) and rejects pre-built `Config` objects in `client_kwargs` with a `ValueError` at construction time — silent rewriting hid both bugs and is no longer permitted. The lesson, captured as `feedback_test_at_real_boundary.md`: when a bug is about wiring between layers, mock at the lower layer where the failure surfaces. New `TestAiobotocoreCreateClientBoundary` patches `aiobotocore.session.AioSession.create_client` directly; a future variant of the same bug class fails the unit suite. Follow-up moto-backed e2e coverage tracked as BK-166.

**Diátaxis docs reorg.** The `guides/` and repo-root docs prose moved into `docs-src/<bucket>/` (`how-to`, `explanation`, `reference`, `further`); the intermediate `docs/` layer was collapsed and removed in the same release. `mkdocs build --strict` passes with 0 warnings. Bookmarks to specific guide URLs may need updating.

### Phase 38: What Azurite Forgave That Real ADLS Did Not (v0.25.0)

v0.25.0 was the release where an emulator finally stopped being the source of truth. Azurite — the local Azure Storage emulator the conformance suite had used since the Azure backend landed — is convenient, free, and wrong about Hierarchical Namespace. ADLS Gen2 with HNS enforces directory semantics that flat blob storage does not, and Azurite quietly forgave a long tail of mismatches: `read_bytes` on a directory blob returned `b""`; `delete` on a directory blob destroyed the marker silently; `is_folder` returned `True` for HNS file paths because `get_directory_properties()` happened to succeed on them too; `write_atomic` of a streaming payload omitted `position=` on `flush_data` because the unseekable wrapper hid the size, and Azurite accepted the malformed request anyway. None of this surfaced under `hatch run all`. All of it surfaced the first time a Stage 3 cassette was recorded against a real account.

**Stage 3 was infrastructure before it was a test pass.** Spec 048 had laid out a three-stage testing model in v0.24.0 (repo-only / Docker / live cloud), but Stage 3 was just a header until v0.25.0 wired the fixtures: `azure_live`, `azure_live_async`, and `s3_live` provision per-call ephemeral resources (`conformance-<uuid>` filesystems, `rs-conformance-<uuid>` buckets), `BackendFixture.aclose` gained an async cleanup channel, and HTTP cassette replay (Phase 3) let CI run a Stage-2 approximation against recorded traffic. The fixtures also produced a *physical* fixture/backend registry (BK-185, BK-186) — per-fixture flat-namespace and self-op flags replaced the scattered identity-keyed sets that had drifted whenever a new backend was added. Single source of truth, finally.

**Twelve HNS fixes in one release.** Once the Stage 3 suite ran against a real account, the failures came in a coordinated wave. `read`, `read_bytes`, `read_seekable`, `delete` (BUG-197, **data-loss fix**) — the data-loss `delete` was the one that mattered most: a file-API `delete()` on what the caller believed was a file but was actually an HNS directory destroyed account state without surfacing an error. `write_atomic` streaming (BUG-194, BUG-202) failed with `MissingRequiredQueryParameter` and had to be rewritten to drive the DataLake DFS protocol directly (`create_file` → `append_data(offset, length)` → `flush_data(position)`). And then the long tail of directory-vs-file fidelity: `get_file_info`, `is_folder`, `get_folder_info`, `delete_folder`, `move`/`copy`, `open_atomic`, `write`/`write_atomic` — each raised the wrong typed error or returned the wrong boolean on HNS where the path didn't match the operation's expected node type. All twelve fixes probe `hdi_isfolder` metadata before invoking the SDK, and sync and async siblings are kept in lockstep. The migration guide carries a table mapping the old wrong errors to `InvalidPath` for callers that had structured their catch clauses around the previous behaviour.

**The lesson, captured as `gotcha_azurite_vs_adls_gen2.md`:** an emulator is a test convenience, not a contract. The conformance suite must run against the thing the code claims to support, on the cadence that release scope demands. Stage 3 is opt-in (`RS_TEST_LIVE_HNS=1`) and cost-gated, but every release that ships changes to the Azure backend now has a documented gate at `hatch run pytest --stage=3 -m "live or not live"` before the version bump.

**Smaller items that rode along.** `SFTPUtils` gained four preflight helpers (`scan_host_keys`, `scan_host_algorithms`, `enable_ssh_rsa_compat`, `HostKeyPolicy` enum-name aliases) for diagnosing `IncompatiblePeer` failures and supporting paramiko 5+ legacy-server quirks; `Store.list_folders(pattern=…)` mirrors `list_files(pattern=…)`; `MemoryBackend.copy()` finally preserves user metadata (a silent drop that had been latent since the metadata work in v0.24.0); `SFTPBackend.exists()` / `is_file()` / `is_folder()` stopped swallowing connect-time `PermissionError` as "not found"; `S3Backend.check_health()` stopped being a silent no-op caused by an unawaited `aiobotocore` coroutine; the `[sftp]` extra requires `paramiko>=3.0` for the `channel_timeout=` kwarg the backend has used since paramiko 3 shipped. The `tests/` root cleanup (BK-188/189/190 plus six BK-191 slices) reshaped the per-backend test layout and wired placement checks (`scripts/check_test_placement.py`) into CI lint, so future drift fails the gate instead of being caught at review.

## Reproducing This Workflow

If you want to try this approach on your own project:

1. Write specs first (see `sdd/specs/` for examples of the format)
2. Use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or a similar AI coding tool
3. Start with plan mode: describe the task, review the plan, then approve
4. Implement in phases: core first, then docs, then polish
5. Run everything after each phase (lint, typecheck, tests, examples)
6. Document decisions as ADRs when you make non-obvious choices
7. Invest in process artifacts (`CLAUDE.md`, skills, research docs) — they compound across sessions
8. Use separate sessions for authoring and reviewing — context isolation is your best free reviewer

The full commit history of this project is the best documentation of the process. Each commit message describes what changed and why.
