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

### 2.1 Tests with No Assertions (~35 instances)

```python
# BAD: tests/test_ping.py
def test_default_check_health_is_noop(self) -> None:
    MemoryBackend().check_health()  # No assertion!

# BAD: tests/test_proxy.py:205
def test_ping(self, proxy: _TestProxy) -> None:
    proxy.ping()  # No assertion!

# BAD: tests/test_config.py:82
def test_registry_config_validate_passes() -> None:
    _valid_rc().validate()  # No assertion!
```

**Why it matters:** These tests pass even if the method silently corrupts
state, returns wrong values, or skips all work. They provide zero regression
safety. A mutation testing tool would flag every one of these as surviving
mutants.

**Fix pattern:**
```python
# GOOD: Verify the method actually did something
def test_ping_succeeds(self, proxy: _TestProxy) -> None:
    proxy.ping()  # Should not raise
    assert proxy.exists("hello.txt")  # Store is still functional

# GOOD: For void methods that should not raise, be explicit
def test_validate_accepts_valid_config() -> None:
    rc = _valid_rc()
    rc.validate()  # No exception = success
    assert rc.stores  # Config is usable after validation
```

### 2.2 isinstance as Primary Assertion (~100+ instances)

```python
# BAD: tests/test_store.py:136
files = list(store.list_files("lf"))
assert len(files) == 2
assert all(isinstance(f, FileInfo) for f in files)  # Type, not content

# BAD: tests/backends/test_sftp.py:130
assert isinstance(sftp_backend, SFTPBackend)  # Always true if we got here
```

**Why it matters:** `isinstance` checks tell you the constructor returned
the right class, not that the object works. A `FileInfo` with wrong path,
wrong size, and wrong timestamp passes `isinstance` just fine.

**Fix pattern:**
```python
# GOOD: Assert behavioral properties
files = list(store.list_files("lf"))
assert {f.name for f in files} == {"a.txt", "b.txt"}
assert all(f.size > 0 for f in files)
```

### 2.3 Private Attribute Access (~100+ instances)

```python
# BAD: tests/test_registry.py:61
assert len(reg._backends) == 0  # Coupled to internal dict

# BAD: tests/test_cache.py:151
assert cache(store, ttl=60.0)._ttl == 300.0  # Inspecting private field

# BAD: tests/test_arrow.py:75
assert h._store is store  # Internal wiring, not behavior
```

**Why it matters:** Any internal refactoring (rename `_backends` to
`_stores`, change `_ttl` storage format) breaks these tests even when
behavior is unchanged. This is the "Inspector" anti-pattern -- tests that
know too much about internals.

**Fix pattern:**
```python
# GOOD: Test through public API
reg.get_store("main")
assert "main" in reg.list_stores()  # Behavioral check

# GOOD: Verify TTL effect, not TTL storage
cached = cache(store, ttl=60.0)
# Write, wait, verify cache behavior -- not internal field value
```

### 2.4 Unconstrained Mocks

```python
# BAD: tests/backends/test_azure.py (multiple locations)
mock = MagicMock()  # Accepts literally any call
mock.get_blob_properties.return_value = MagicMock()  # Mock returning mock

# BAD: tests/test_depth_listing.py:276
backend._sftp = MagicMock()  # Replace internals with unspecified mock
```

**Why it matters:** `MagicMock()` without `spec=` accepts any attribute
access and any method call with any signature. If the real Azure SDK changes
its API, these tests keep passing. The mock and the real object can silently
diverge.

**Fix pattern:**
```python
# GOOD: Use spec= to constrain mock to real interface
mock = MagicMock(spec=BlobServiceClient)
# Now mock.nonexistent_method() raises AttributeError
```

### 2.5 Summary Statistics

| Anti-Pattern | Count | Severity |
|-------------|-------|----------|
| No assertions (void call only) | ~35 | High |
| `isinstance` as primary assertion | ~100+ | Medium |
| Private attribute access in assertions | ~100+ | Medium |
| Unconstrained `MagicMock()` | ~100+ | Medium |
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

BK-014 demonstrated that **test code bloat is itself an anti-pattern**.
Reducing ~17,800 to ~16,300 lines (-8.6%) with zero coverage loss and
identical pass/skip counts proved that the removed code was pure maintenance
burden -- it tested nothing that wasn't already tested.

**Why bloated test suites are dangerous:**

1. **Distraction.** When reviewing a 900-line test file, the 30 meaningful
   tests are buried among 50 trivial ones. Reviewers miss real issues.
2. **False confidence.** "We have 1,866 tests" sounds impressive, but if
   400 of them are single-method classes that duplicate parametrizable
   logic, the actual *distinct behavioral coverage* is lower than it
   appears.
3. **Maintenance drag.** Every refactoring requires updating more test
   code. When tests outnumber production code (our ratio is ~1.3:1 by
   lines), the tail wags the dog.
4. **Anti-pattern camouflage.** A no-assertion test hiding in a 50-test
   class is easy to miss. In a tight, parametrized suite it would stand
   out immediately.

**Techniques that reduce test code without reducing coverage:**

| Technique | Reduction | Example |
|-----------|-----------|---------|
| Parametrize similar tests | 3-10 tests -> 1 | `@pytest.mark.parametrize("op", ["move", "copy"])` |
| Merge single-method classes | N classes -> 1 | Combine `TestMoveOp` + `TestCopyOp` into `TestFileOps` |
| Extract shared fixtures | N inline setups -> 1 | `@pytest.fixture` in `conftest.py` |
| Remove tests subsumed by others | Delete | If `test_write_and_read` already covers write, `test_write_exists` adds nothing |
| Replace copy-paste with base classes | 2 files -> 1 + mixin | BK-011: `_S3Base` for S3/S3-PyArrow shared tests |

**The goal is not fewer tests, it's fewer lines per tested behavior.** A
parametrized test with 8 cases in 15 lines is strictly better than 8
separate test methods in 80 lines -- same coverage, one-eighth the
maintenance surface.

Jay Fields (*Working Effectively with Unit Tests*) makes this explicit:

> It's acceptable to delete tests that don't provide value. Tests are an
> investment; if the return is negative, cut your losses.

### 3.4 How Major Python Projects Test

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

### 3.5 Hynek Schlawack: "Don't Mock What You Don't Own"

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

### 3.6 Ned Batchelder: Coverage Is Necessary But Not Sufficient

From his [blog](https://nedbatchelder.com/blog/tag/coverage.html) and talks:

> 100% statement coverage doesn't mean much. There are dozens of ways your
> code or tests could still be broken. Statement coverage has taken you to
> the end of its road, and the bad news is, you aren't at your destination.

**Implication for us:** Our 95% coverage threshold is good as a floor, but
it doesn't prevent tests with no assertions from inflating the number. We
need quality metrics alongside quantity metrics.

### 3.7 Property-Based Testing (Hypothesis)

Hypothesis generates random inputs and checks invariant properties:

```python
from hypothesis import given, strategies as st

@given(st.binary())
def test_write_read_roundtrip(data: bytes) -> None:
    store = Store(MemoryBackend())
    store.write("test.bin", data)
    assert store.read_bytes("test.bin") == data
```

**Where it fits for us:**
- Round-trip properties: `write(path, data)` then `read_bytes(path) == data`
- Path normalization: `RemotePath(str(RemotePath(x))) == RemotePath(x)`
- Serialization: `Config.from_dict(config.to_dict()) == config`
- Batch operations: `batch_delete(files).succeeded | batch_delete(files).failed == files`

Hillel Wayne's insight: **Contracts + Property-Based Testing = Integration
Tests**. Define invariants as contracts, let Hypothesis find violations.

### 3.8 Mutation Testing

Mutation testing answers: "If a bug were introduced, would my tests catch it?"

**mutmut** (the leading Python tool) systematically mutates production code
and re-runs tests. Surviving mutants = potential undetected bugs.

```toml
# pyproject.toml
[tool.mutmut]
paths_to_mutate = "src/"
runner = "python -m pytest"
tests_dir = "tests/"
```

**Our "no assertion" tests would be flagged immediately** -- every mutant in
the tested function survives because nothing checks the output.

Mutation scores above 80% indicate strong fault-detection capability.
Consider running mutmut on a weekly CI schedule (it's too slow for every PR).

### 3.9 Testing Retry and Concurrency Behavior

Two known gaps (M-14 concurrency, M-17 retry) require specific patterns:

**Retry testing: controlled failure injection.**
Don't test retries with real timeouts or flaky network conditions. Instead,
build a deterministic fake that fails N times, then succeeds:

```python
class FailNThenSucceed:
    """Fake that raises on the first N calls, then returns normally."""
    def __init__(self, n: int, exc: Exception) -> None:
        self._remaining = n
        self._exc = exc

    def __call__(self, *args, **kwargs):
        if self._remaining > 0:
            self._remaining -= 1
            raise self._exc
        return "ok"

def test_retry_succeeds_after_transient_failures():
    fake = FailNThenSucceed(2, ConnectionError("transient"))
    result = retry_with_backoff(fake, max_retries=3)
    assert result == "ok"
    assert fake._remaining == 0  # all failures consumed
```

Assert **attempt count + final outcome**, never wall-clock time.

**Concurrency testing: invariant assertions under contention.**
Use `ThreadPoolExecutor` with deterministic assertions on invariants:

```python
def test_no_lost_writes_under_contention(store: Store):
    """10 threads write distinct keys; all 10 must be readable."""
    keys = [f"key_{i}.txt" for i in range(10)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda k: store.write(k, k.encode()), keys))
    for k in keys:
        assert store.read_bytes(k) == k.encode()
```

Invariants to test: no lost writes, no partial reads, no duplicate entries,
no deadlocks (use a timeout on the test itself).

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

### 4.4 CLAUDE.md Additions

Add to the CLAUDE.md `## Code conventions` or a new `## Testing` section:

```markdown
## Testing rules

**CI-enforced (automated):**
1. **Every test must assert something meaningful.** "No crash" is not a test.
   Every public API needs at least one failure-path test.
4. **Always use `spec=` with MagicMock.** Unconstrained mocks are banned.

**Review-enforced (human/AI review):**
2. **Assert behavior, not types.** No `isinstance` as the sole assertion.
3. **Never assert on private attributes** (`._field`). Test through public API.
   Exception only with `# internal: no public observable` + PR justification.
5. **Don't mock what you don't own.** Mock at our boundaries, not third-party APIs.
6. **Prefer real dependencies.** `MemoryBackend` > `MagicMock(spec=Backend)`.
7. **Maximize coverage per line of test code.** Parametrize, don't copy-paste.
   Delete tests subsumed by others. Less test code = less maintenance drag.
8. **Tests must survive refactoring.** If renaming a private method breaks a
   test, the test is wrong.

See `sdd/research/research-testing-best-practices.md` for rationale and examples.
```

This gives Claude (and human contributors) explicit, checkable rules rather
than relying on judgment calls that drift over time.

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
- Vladimir Khorikov, *Unit Testing: Principles, Practices, and Patterns* ([Manning](https://www.manning.com/books/unit-testing))
- Jay Fields, *Working Effectively with Unit Tests* ([Leanpub](https://leanpub.com/wewut))
- Harry Percival, *Test-Driven Development with Python* ([Obey the Testing Goat](https://www.obeythetestinggoat.com/))
- Harry Percival & Bob Gregory, *Architecture Patterns with Python* (O'Reilly)

### Articles & Talks
- Hynek Schlawack, ["Don't Mock What You Don't Own" in 5 Minutes](https://hynek.me/articles/what-to-mock-in-5-mins/)
- Hynek Schlawack, ["Why You Should Document Your Tests"](https://hynek.me/articles/document-your-tests/)
- Hynek Schlawack, ["Design Pressure"](https://hynek.me/talks/design-pressure/) (PyCon US 2025)
- Ned Batchelder, ["Flaws in Coverage Measurement"](https://nedbatchelder.com/blog/200710/flaws_in_coverage_measurement.html)
- Ned Batchelder, ["Getting Started Testing: pytest edition"](https://nedbatchelder.com/text/test3)
- Codepipes, ["Software Testing Anti-Patterns"](https://blog.codepipes.com/testing/software-testing-antipatterns.html)
- Hillel Wayne, ["Property Tests + Contracts = Integration Tests"](https://www.hillelwayne.com/post/pbt-contracts/)
- Yegor256, ["Unit Testing Anti-Patterns -- Full List"](https://www.yegor256.com/2018/12/11/unit-testing-anti-patterns.html)
- Randy Coulman, ["Tautological Tests"](https://randycoulman.com/blog/2016/12/20/tautological-tests/)
- Google Testing Blog, ["Test Behavior, Not Implementation"](https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html)

### Tools
| Tool | Purpose | Link |
|------|---------|------|
| Hypothesis | Property-based testing | [github.com/HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis) |
| mutmut | Mutation testing | [github.com/boxed/mutmut](https://github.com/boxed/mutmut) |
| pytest-smell | Test smell detection | [pypi.org/project/pytest-smell](https://pypi.org/project/pytest-smell/) |
| diff-cover | Delta coverage on PRs | [pypi.org/project/diff-cover](https://pypi.org/project/diff-cover/) |
| Ruff PT rules | Test style linting | [docs.astral.sh/ruff/rules/#flake8-pytest-style-pt](https://docs.astral.sh/ruff/rules/#flake8-pytest-style-pt) |
| pytest-httpserver | Real HTTP in tests | [pypi.org/project/pytest-httpserver](https://pypi.org/project/pytest-httpserver/) |
