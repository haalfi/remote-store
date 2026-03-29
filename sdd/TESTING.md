# Testing Standards

## Intent & Scope

Authoritative source for test **quality** rules in `tests/`. Companion to
[DESIGN.md](DESIGN.md) section 11, which covers test **style** (class grouping,
spec markers, naming). This document covers what makes a test *meaningful*.

Applies to all new and modified tests. Existing violations are tracked
separately (BK-124b). Derived from
[research-testing-best-practices](research/research-testing-best-practices.md).

## Rules

### 1. Every test must have at least one meaningful assertion [CI-enforced]

"No crash" is not a test. If the method returns void, assert a post-condition
proving the system reached the expected state. Every public API method should
also have at least one failure-path test (`pytest.raises` with `match=`).

### 2. Assert behavior, not types [review-enforced]

Replace `assert isinstance(x, FileInfo)` with assertions on `x.path`, `x.size`,
or `x.name`. The type is already guaranteed by the type checker. `isinstance`
may appear alongside behavioral assertions, but never as the sole check.

### 3. Never assert on private attributes [review-enforced]

`assert obj._field == x` is banned in new tests. If you need to verify internal
state, either expose it through a public API or verify it through observable
behavior. Exception: if no public observable exists, annotate with
`# internal: no public observable` and justify in the PR.

### 4. Always use `spec=` (or `spec_set=`) with `MagicMock` [CI-enforced]

`MagicMock()` without `spec` is banned. Use `MagicMock(spec=RealClass)` or
`create_autospec(RealClass)` to constrain mocks to real interfaces. This
prevents tests from passing when the real class changes its API.

### 5. Don't mock what you don't own [review-enforced]

Never `patch("boto3.client")` or `patch("paramiko.SFTPClient")`. Mock at our
own boundary: the Backend ABC, a wrapper function, or a protocol. Third-party
behavior changes silently; mocking their internals hides the breakage.

### 6. Prefer real dependencies over mocks [review-enforced]

Use `MemoryBackend` or in-memory SQLite over mocked backends. Use
`pytest-httpserver` over mocked HTTP clients. Reserve mocks for external
services that cannot be run locally.

### 7. Maximize behavioral coverage per line of test code [review-enforced]

Parametrize similar tests instead of writing separate methods. Merge
single-method test classes. Delete tests subsumed by others. When removing a
test, verify via coverage that the deleted path is still exercised. Three
parametrized cases in 10 lines beat three methods in 30 lines.

### 8. Tests must survive refactoring [review-enforced]

If renaming a private method or changing internal data structures would break a
test without changing behavior, the test is coupled to implementation. Fix the
test, not the production code.

## Guides

### Good vs bad examples

**Rule 2 -- Assert behavior, not types:**

```python
# Bad: type check only
info = store.get_file_info("data.csv")
assert isinstance(info, FileInfo)

# Good: behavioral assertions
info = store.get_file_info("data.csv")
assert info.path == "data.csv"
assert info.size > 0
```

**Rule 3 -- No private attributes:**

```python
# Bad: coupled to internals
store = CachedStore(backend, ttl=60)
assert store._ttl == 60

# Good: verify through observable behavior
store = CachedStore(backend, ttl=60)
store.read_bytes("key")           # cold read
store.read_bytes("key")           # warm read (cache hit)
assert backend.read_count == 1    # only one backend call
```

**Rule 4 -- Always use `spec=`:**

```python
# Bad: accepts any call, even misspelled methods
backend = MagicMock()
backend.raed_bytes("key")  # typo passes silently

# Good: constrained to real interface
backend = MagicMock(spec=Backend)
backend.raed_bytes("key")  # AttributeError — caught immediately
```

### Testing Expert quick reference

Lookup table for the BK-125 Testing Expert agent. Each rule maps to a
concrete check the expert should perform when writing or reviewing tests.

| Rule | What to check | How |
|------|--------------|-----|
| 1 | Test has `assert` or `pytest.raises` | AST / grep |
| 2 | No `isinstance`-only assertions | Review: sole `isinstance` without behavioral follow-up |
| 3 | No `._private` in assertions | Grep for `\._[a-z]` in `assert` lines |
| 4 | `MagicMock(` always has `spec=` | Grep for `MagicMock(` without `spec` |
| 5 | No `patch("third_party.` | Review: patches target our code, not third-party |
| 6 | Mocks justified | Review: could a real backend or fixture replace the mock? |
| 7 | No duplicate test shapes | Review: 3+ similar methods should be parametrized |
| 8 | No private-method coupling | Review: would renaming an internal break this test? |
