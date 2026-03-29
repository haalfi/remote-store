# Research: Testing Best Practices for Long-Term Package Quality

**Date:** 2026-03-28
**Context:** Recurring test quality issues keep resurfacing in remote-store.
PR #301 is the latest fix round; audits and backlog items show a pattern of
the same anti-patterns returning after being fixed. This document compiles
lessons learned, industry best practices, and proposes enforceable guardrails.

---

## 1. Our History: What We Fixed and What Keeps Coming Back

### 1.1 Audit 001 (Adversarial Review, v0.5.0) Findings

| ID | Problem | Anti-Pattern | Status |
|----|---------|-------------|--------|
| M-12 | Azure HNS tested via unconstrained `MagicMock()` | Mock accepts any call/signature | **Open** |
| M-13 | `test_coverage_gaps.py` inflated coverage with `assert X is not None` | Pure-import assertions | Fixed (BK-014) |
| M-14 | Zero concurrency tests despite thread-safety spec claims | Missing behavioral tests | **Open** |
| M-16 | No tests for `PermissionDenied`/`BackendUnavailable` in S3/SFTP | Untested error paths | Fixed (AF-013) |
| M-17 | SFTP retry logic (tenacity) never tested | Untested retry paths | **Open** |
| L-18 | `test_list_files_round_trip` checks `len(data) == 3`, not content | Weak assertions | **Open** |
| L-19 | S3/S3-PyArrow ~500 lines near-identical copy-paste | Test duplication | Fixed (BK-011) |
| L-20 | No tests for Unicode paths, special chars, empty/large files | Missing edge cases | **Open** |

### 1.2 BK-014: Test Suite Deduplication (v0.19.0)

Reduced ~17,800 to ~16,300 lines (-8.6%) across 30 of 40 test files while
preserving 1,866 passed tests. Key techniques:

- Parametrized similar tests (error mapping, validation, operation variants)
- Extracted shared fixtures
- Merged single-method test classes into parent classes
- Consolidated repeated assertion patterns
- Reviewed `test_coverage_gaps.py` pure-import assertions (M-13)

### 1.3 PR #301: Fix Coverage and ResourceWarning (v0.20.0-dev)

- SQLBlob test fixtures now yield+close; engines disposed on teardown
- ProxyStore delegation coverage 68% -> 100% (new `test_proxy.py`, 33 tests)
- SQLAlchemy backend coverage 90% -> 99%
- `/pr` skill now gates on `hatch run test-cov` (95% threshold)

### 1.4 Pattern: What Keeps Recurring

Despite fixes, the **same categories** of bad tests reappear:

1. **Tests with no assertions** -- just call a method, assume "no crash = pass"
2. **`isinstance` as the only assertion** -- verifies type, not behavior
3. **Private attribute access** (`._backends`, `._ttl`, `._owns_backend`)
4. **Unconstrained mocks** (`MagicMock()` without `spec=`)
5. **Factory helpers duplicating constructor logic**

These recur because they are **not mechanically prevented**. A code reviewer
(human or AI) must catch them every time, and that is not sustainable.

---

## 2. Current Anti-Patterns in Our Codebase

Detailed audit of recurring anti-patterns with file-path evidence. Each
category maps to a proposed rule in section 4.1.

- **No assertions (~35 instances):** Tests that call a method but never
  assert on the outcome. Examples: `test_ping.py`, `test_proxy.py:205`,
  `test_config.py:82`. Mutation testing would flag all of these. → Rule 1.
- **`isinstance` as primary assertion (~100+ instances):** Verifies type,
  not behavior. A `FileInfo` with wrong path/size/timestamp passes
  `isinstance`. Examples: `test_store.py:136`, `test_sftp.py:130`. → Rule 2.
- **Private attribute access (~100+ instances):** `assert obj._field == x`
  couples tests to internals. Examples: `test_registry.py:61` (`_backends`),
  `test_cache.py:151` (`_ttl`), `test_arrow.py:75` (`_store`). → Rule 3.
- **Unconstrained mocks (~67 instances):** `MagicMock()` without `spec=`
  accepts any call (68 total, 1 with `spec=`). Examples: `test_azure.py`
  (46), `test_ping.py` (11), `test_depth_listing.py` (4). → Rule 4.

### Summary Statistics

| Anti-Pattern | Count | Severity |
|-------------|-------|----------|
| No assertions (void call only) | ~35 | High |
| `isinstance` as primary assertion | ~100+ | Medium |
| Private attribute access in assertions | ~100+ | Medium |
| Unconstrained `MagicMock()` | ~67 | Medium |
| Factory helpers duplicating constructors | ~6 | Low |

---

## 3. Industry Best Practices

### 3.1 The Core Principle: Test Behavior, Not Implementation

Vladimir Khorikov (*Unit Testing: Principles, Practices, and Patterns*,
Manning) defines the key insight:

> Tests should verify **units of behavior** -- something meaningful for the
> problem domain -- not units of code. The number of classes it takes to
> implement that behavior is irrelevant.

His four pillars of a good test:
1. **Protection against regressions** -- catches real bugs
2. **Resistance to refactoring** -- doesn't break on harmless changes
3. **Fast feedback** -- runs quickly
4. **Maintainability** -- easy to read and change

Most of our anti-patterns violate pillar 2 (private attribute access,
implementation-coupled mocks) or pillar 1 (no assertions, isinstance-only).

**Important nuance:** Khorikov's "the number of classes is irrelevant"
applies to *what you test* (a unit of behavior may span classes). It does
**not** mean the volume of test code is irrelevant. Pillar 4
(maintainability) directly addresses this -- and our own history proves it.

### 3.2 Test Code Economy: Less Code, Same Coverage, Better Signal

**Why bloated test suites are dangerous:**

1. **Distraction.** Meaningful tests buried among trivial ones; reviewers miss real issues.
2. **False confidence.** High test count masks low distinct behavioral coverage.
3. **Maintenance drag.** At ~1.3:1 test-to-production line ratio, refactoring costs double.
4. **Anti-pattern camouflage.** No-assertion tests hide in large classes but stand out in tight parametrized suites.

Jay Fields (*Working Effectively with Unit Tests*):

> It's acceptable to delete tests that don't provide value. Tests are an
> investment; if the return is negative, cut your losses.

BK-014 validated this: -8.6% test code, zero coverage loss (see section 1.2).

### 3.3 How Major Python Projects Test

| Project | Key Strategy | Mocking Approach |
|---------|-------------|-----------------|
| **requests** | Real local HTTP server (pytest-httpbin) | Adapter pattern as natural mock point |
| **SQLAlchemy** | In-memory SQLite for fast real DB tests | Almost never mocks own internals |
| **Django** | Transaction-wrapped tests with auto-rollback | `--shuffle` flag to detect isolation bugs |
| **FastAPI** | `TestClient` + dependency overrides | DI as the testability mechanism |
| **Pydantic** | Extensive parametrization, property-based tests | Minimal mocking |

**Common theme:** Prefer real dependencies over mocks. Use architecture
(dependency injection, adapter pattern, functional core) to make code
testable without mocks.

### 3.4 Hynek Schlawack: "Don't Mock What You Don't Own"

Key principles from [hynek.me](https://hynek.me/articles/what-to-mock-in-5-mins/):

1. **Never mock third-party code directly** -- wrap it in your own function,
   mock that wrapper
2. **Keep test code paths close to production** -- an in-process test server
   is closer to reality than magically replacing a client with a fake
3. **Use verified fakes** over unconstrained mocks
4. **Heavy mocking signals architectural problems**, not testing problems

His talk "Design Pressure" (PyCon US 2025) extends this: if you need many
mocks, your code has a design problem. Push I/O to the edges ("Functional
Core, Imperative Shell") and the core becomes trivially testable.

### 3.5 Ned Batchelder: Coverage Is Necessary But Not Sufficient

From his [blog](https://nedbatchelder.com/blog/tag/coverage.html) and talks:

> 100% statement coverage doesn't mean much. There are dozens of ways your
> code or tests could still be broken. Statement coverage has taken you to
> the end of its road, and the bad news is, you aren't at your destination.

**Implication for us:** Our 95% coverage threshold is good as a floor, but
it doesn't prevent tests with no assertions from inflating the number. We
need quality metrics alongside quantity metrics.

### 3.6 Property-Based Testing (Hypothesis)

Hypothesis generates random inputs and checks invariant properties.
Hillel Wayne's insight: **Contracts + Property-Based Testing = Integration
Tests** -- define invariants as contracts, let Hypothesis find violations.

Candidate invariants for remote-store: write/read round-trip, path
normalization idempotency, config serialization round-trip, batch operation
completeness. Implementation details belong in the PR that adds these tests.

### 3.7 Mutation Testing (mutmut)

Mutation testing answers: "If a bug were introduced, would my tests catch it?"
**mutmut** systematically mutates production code and re-runs tests.
Surviving mutants = potential undetected bugs. Our "no assertion" tests
would be flagged immediately -- every mutant survives because nothing checks
the output. Too slow for per-PR CI; run on a weekly schedule.

### 3.8 Testing Retry and Concurrency Behavior

Two known gaps (M-14 concurrency, M-17 retry) require specific patterns:

- **Retry testing:** Controlled failure injection -- a deterministic fake
  that fails N times then succeeds. Assert attempt count + final outcome,
  never wall-clock time.
- **Concurrency testing:** Invariant assertions under contention --
  `ThreadPoolExecutor` with deterministic checks for no lost writes, no
  partial reads, no duplicate entries, no deadlocks (timeout on the test).

Full code examples belong in the PR that implements these tests.

---

## 4. Proposed Testing Rules for remote-store

### 4.1 The Eight Rules

These rules should be added to `sdd/DESIGN.md` section 11 (Test Style) and
enforced in code review:

**Rule 1: Every test must have at least one meaningful assertion.** [CI-enforced]
"No crash" is not a test. If the method returns void and the point is that
it doesn't raise, add a post-condition assertion proving the system is in
the expected state. Every public API method should also have at least one
failure-path test (`pytest.raises` with `match=`).

**Rule 2: Assert behavior, not types.** [review-enforced]
Replace `assert isinstance(x, FileInfo)` with assertions on `x.path`,
`x.size`, or `x.name`. The type is already guaranteed by the type checker.

**Rule 3: Never assert on private attributes.** [review-enforced]
If you need to verify internal state, either (a) expose it through a public
API, or (b) verify it through observable behavior. `assert obj._field == x`
is banned in new tests. Exception: if no public observable exists, annotate
with `# internal: no public observable` and justify in the PR.

**Rule 4: Always use `spec=` (or `spec_set=`) with MagicMock.** [CI-enforced]
`MagicMock()` without spec is banned. Use `MagicMock(spec=RealClass)` or
`create_autospec(RealClass)` to constrain mocks to real interfaces.

**Rule 5: Don't mock what you don't own.** [review-enforced]
Never `patch("boto3.client")` or `patch("paramiko.SFTPClient")`. Instead,
mock at our own boundary (the Backend ABC or a wrapper function).

**Rule 6: Prefer real dependencies over mocks.** [review-enforced]
Use `MemoryBackend` or in-memory SQLite over mocked backends. Use
`pytest-httpserver` over mocked HTTP clients. Reserve mocks for external
services that can't be run locally.

**Rule 7: Maximize behavioral coverage per line of test code.** [review-enforced]
Parametrize similar tests instead of writing separate methods. Merge
single-method test classes. Delete tests subsumed by others. Three
parametrized cases in 10 lines beat three methods in 30 lines -- same
coverage, one-third the maintenance surface. (See BK-014: -8.6% test
code, zero coverage loss.) When removing a test, verify via coverage that
the deleted path is still exercised by remaining tests.

**Rule 8: Tests must survive refactoring.** [review-enforced]
If renaming a private method or changing internal data structures would
break a test without changing behavior, the test is coupled to
implementation. Fix the test.

### 4.2 Ruff PT Rules (Mechanical Enforcement)

Add to `pyproject.toml`:

```toml
[tool.ruff.lint]
extend-select = ["PT"]  # flake8-pytest-style

[tool.ruff.lint.flake8-pytest-style]
raises-require-match-for = [
    "ValueError", "TypeError", "KeyError", "RuntimeError",
    "NotFound", "AlreadyExists", "CapabilityNotSupported",
    "BackendUnavailable", "PermissionDenied",
]
```

Key PT rules that catch our recurring issues:
- **PT011**: `pytest.raises()` too broad (no `match=`) -- prevents lazy
  exception checks
- **PT018**: Composite assertions should use multiple `assert` statements
- **PT006/PT007**: Consistent parametrize style

### 4.3 CI-Enforced Checks

| Check | Rule | Phase | Effort |
|-------|------|-------|--------|
| AST check: test has no `assert` and no `pytest.raises` | Rule 1 | **1** | Low (script) |
| Grep: `MagicMock(` without `spec=` or `autospec=` | Rule 4 | **1** | Low (grep) |
| `--cov-branch` | Coverage quality | **1** | Low (flag) |
| `diff-cover --fail-under=90` | New code without tests | **2** | Low (pip) |
| `mutmut` baseline run (diagnostic, not blocking) | Assertion quality | **2** | Medium |
| `pytest-smell --ci` | 17 types of test smells | **3** | Low (pip) |
| `mutmut` weekly with threshold | Assertion quality gate | **3** | Medium |

### 4.4 PR Review Checklist

Add to the PR template as a reviewer aid:

```markdown
### Test review
- [ ] Every new test has at least one `assert` or `pytest.raises`
- [ ] Assertions are behavioral (not `isinstance`-only, not type-only)
- [ ] No new `._private` attribute access in assertions (or justified)
- [ ] Mocks use `spec=` or `create_autospec`
- [ ] Failure path covered for new/changed public API methods
```

### 4.5 CLAUDE.md Additions

Add a `## Testing rules` section to CLAUDE.md summarizing the 8 rules above
with CI/review enforcement tags. See section 4.1 for the full text. The
actual CLAUDE.md edit will be reviewed in its own implementation PR.

---

## 5. Phased Adoption Plan

### Phase 1: Prevent New Anti-Patterns (Immediate)

- [ ] Add the 8 testing rules to `sdd/DESIGN.md` section 11
- [ ] Add testing rules summary (with CI/review tags) to `CLAUDE.md`
- [ ] Enable Ruff `PT` rules in `pyproject.toml`
- [ ] Switch coverage to branch mode (`--cov-branch`)
- [ ] Add CI check: fail if test function has no `assert` and no `pytest.raises`
- [ ] Add CI grep check: fail if `MagicMock(` appears without `spec=`
- [ ] Add PR review checklist to PR template (section 4.4)

### Phase 2: Fix Existing Anti-Patterns + Diagnostics (Next Sprint)

- [ ] Fix all ~35 "no assertion" tests (add meaningful post-conditions)
- [ ] Replace top ~20 `isinstance`-only assertions with behavioral checks
- [ ] Add `spec=` to all existing `MagicMock()` calls
- [ ] Replace private attribute assertions in `test_registry.py`,
  `test_cache.py`, `test_proxy.py` with public API checks
- [ ] Add `diff-cover` to PR CI (fail-under=90 for new code)
- [ ] Run `mutmut` baseline (diagnostic only, establish starting score)
- [ ] Add concurrency test suite for thread-safety claims (M-14)

### Phase 3: Advanced Quality Measures (Future)

- [ ] Add `mutmut` to weekly CI schedule with threshold gate
- [ ] Add `pytest-smell --ci` to lint step
- [ ] Add retry testing with controlled failure injection fakes (M-17)
- [ ] Explore Hypothesis for round-trip and path normalization properties
  (provide 2-3 canonical examples in-repo)
- [ ] Create a `TestingBackend` (controlled fake) to replace mock injection
  in tests like `test_registry.py:119`

---

## 6. References

### Books
- Vladimir Khorikov, *Unit Testing: Principles, Practices, and Patterns* ([Manning](https://www.manning.com/books/unit-testing)) — cited in §3.1
- Jay Fields, *Working Effectively with Unit Tests* ([Leanpub](https://leanpub.com/wewut)) — cited in §3.2

### Articles & Talks
- Hynek Schlawack, ["Don't Mock What You Don't Own" in 5 Minutes](https://hynek.me/articles/what-to-mock-in-5-mins/) — cited in §3.4
- Hynek Schlawack, ["Design Pressure"](https://hynek.me/talks/design-pressure/) (PyCon US 2025) — cited in §3.4
- Ned Batchelder, ["Flaws in Coverage Measurement"](https://nedbatchelder.com/blog/200710/flaws_in_coverage_measurement.html) — cited in §3.5
- Hillel Wayne, ["Property Tests + Contracts = Integration Tests"](https://www.hillelwayne.com/post/pbt-contracts/) — cited in §3.6
- Google Testing Blog, ["Test Behavior, Not Implementation"](https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html) — cited in §3.1

### Tools
| Tool | Purpose | Link |
|------|---------|------|
| Hypothesis | Property-based testing | [github.com/HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis) |
| mutmut | Mutation testing | [github.com/boxed/mutmut](https://github.com/boxed/mutmut) |
| pytest-smell | Test smell detection | [pypi.org/project/pytest-smell](https://pypi.org/project/pytest-smell/) |
| diff-cover | Delta coverage on PRs | [pypi.org/project/diff-cover](https://pypi.org/project/diff-cover/) |
| Ruff PT rules | Test style linting | [docs.astral.sh/ruff/rules/#flake8-pytest-style-pt](https://docs.astral.sh/ruff/rules/#flake8-pytest-style-pt) |
| pytest-httpserver | Real HTTP in tests | [pypi.org/project/pytest-httpserver](https://pypi.org/project/pytest-httpserver/) |
