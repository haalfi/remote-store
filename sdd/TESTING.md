# Testing Standards

## Intent & Scope

Authoritative source for test **quality** rules in `tests/`. Companion to
`sdd/DESIGN.md` § 11 (test style). Derived from
`sdd/research/research-testing-best-practices.md`.

## Rules

1. **Every test must have at least one meaningful assertion** [CI-enforced]
   — "no crash" is not a test. Public API methods need a failure-path test too
   (`pytest.raises` with `match=`).

2. **Assert behavior, not types** [review-enforced]
   — `isinstance` may accompany behavioral assertions but never as the sole check.

3. **Never assert on private attributes** [review-enforced]
   — verify through observable behavior. Exception: `# internal: no public observable`.

4. **Always use `spec=` with `MagicMock`** [CI-enforced]
   — `MagicMock()` without `spec` is banned; use `spec=RealClass` or `create_autospec`.

5. **Don't mock what you don't own** [review-enforced]
   — mock at our boundary (Backend ABC, wrapper, protocol), never third-party internals.

6. **Prefer real dependencies over mocks** [review-enforced]
   — `MemoryBackend`, in-memory SQLite, `pytest-httpserver` before reaching for mocks.

7. **Maximize behavioral coverage per line of test code** [review-enforced]
   — parametrize over copy-paste; delete tests subsumed by others (verify via coverage).

8. **Tests must survive refactoring** [review-enforced]
   — if renaming a private method breaks the test, the test is wrong.

## Guides

### Examples (bad → good)

```python
# Rule 2 — assert behavior, not types
assert isinstance(info, FileInfo)           # bad
assert info.path == "data.csv"              # good

# Rule 3 — no private attributes
assert store._ttl == 60                     # bad
assert backend.read_count == 1              # good (observable)

# Rule 4 — always use spec=
backend = MagicMock()                       # bad
backend = MagicMock(spec=Backend)           # good
```

### Testing Expert quick reference (BK-125)

| Rule | Check | Method |
|------|-------|--------|
| 1 | Has `assert` or `pytest.raises` | grep |
| 2 | No sole `isinstance` assertion | review |
| 3 | No `._private` in assertions | grep `\._[a-z]` in assert lines |
| 4 | `MagicMock(` has `spec=` | grep |
| 5 | Patches target our code | review |
| 6 | Mock could be a real dependency | review |
| 7 | 3+ similar methods → parametrize | review |
| 8 | Renaming internal breaks test? | review |

### Test code economy

Bloated suites bury meaningful tests, inflate coverage without behavioral
signal, and double refactoring cost. Delete tests that don't provide value
(BK-014: -8.6% code, zero coverage loss).

### Ruff PT rules (enabled)

| Rule | What it catches |
|------|----------------|
| PT011 | `pytest.raises()` without `match=` |
| PT018 | Composite assertions — use multiple `assert` statements |
| PT006/PT007 | Inconsistent `@pytest.mark.parametrize` style |
