# Testing Standards

## Intent & Scope

Authoritative source for test **quality** rules in `tests/`. Companion to
`sdd/DESIGN.md` § 11 (test style). Derived from
`sdd/research/research-testing-best-practices.md`.

## Test Subpackage Placement

Each test file belongs in the subpackage matching its subject:

| Subject | Subpackage |
|---------|------------|
| Library source (`src/remote_store/`) | `tests/` root |
| Async variants of library tests | `tests/aio/` |
| Concrete backend conformance and integration | `tests/backends/` |
| End-to-end workflow tests (require Docker services) | `tests/e2e/` |
| `scripts/` utilities and build tooling | `tests/scripts/` |

Tests that load modules from `scripts/` via `sys.path` manipulation must live
in `tests/scripts/`. The `check-test-placement` lint enforces this for `sys.path`
patterns; tests using `importlib.util.spec_from_file_location` are review-enforced.

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

9. **Every `@given` test must assert on a non-rejection path** [review-enforced]
   — `try/except/return` to reject invalid inputs is fine, but the test
   must reach an `assert` for some generated inputs. 100% rejection = no-op.

10. **Use Hypothesis profiles, not inline `max_examples`** [review-enforced]
    — profiles: `dev` (50), `ci` (100), `nightly` (1000). Inline
    `@settings(max_examples=N)` only when suppressing a health check.

11. **PBT strategies at module scope** [review-enforced]
    — define as module-level constants for reuse. Inline `st.` chains
    only for trivial one-liners.

12. **Treat test warnings as latent bugs** [review-enforced]
    — investigate `RuntimeWarning`/`ResourceWarning` before suppressing.
    `filterwarnings("ignore:…")` only with a `# acceptable because …` comment.

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
| 9 | `@given` has `assert` on non-rejection path | review |
| 10 | No inline `max_examples` | grep `max_examples` |
| 11 | Strategies at module scope | review |
| 12 | No unjustified `filterwarnings("ignore:…")` | grep `filterwarnings.*"ignore:` |

### Test code economy

Bloated suites bury meaningful tests, inflate coverage without behavioral
signal, and double refactoring cost. Delete tests that don't provide value
(BK-014: -8.6% code, zero coverage loss).

### Property-Based Testing (Hypothesis)

PBT targets combinatorial input spaces with a clear oracle (roundtrip,
invariant, model equivalence). Use `@pytest.mark.parametrize` for known
edge cases; use `@given` when the interesting inputs are the ones you
haven't thought of. See rules 9–11.

### Ruff PT rules (enabled)

| Rule | What it catches |
|------|----------------|
| PT011 | `pytest.raises()` without `match=` |
| PT018 | Composite assertions — use multiple `assert` statements |
| PT006/PT007 | Inconsistent `@pytest.mark.parametrize` style |
