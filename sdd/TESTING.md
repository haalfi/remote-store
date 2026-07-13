# Testing Standards
<!-- doc: dual dest=explanation/design/testing.md -->

## Intent & Scope

Authoritative source for test **quality** rules and top-level
**placement** of test files in `tests/`. Companion to
[`sdd/DESIGN.md` § 11 (test style)](DESIGN.md#test-style).

For test **architecture** (the shape of the test tree and how backends
are wired into it), see
[`sdd/specs/048-testing-architecture.md`](specs/048-testing-architecture.md)
and [ADR-0028](adrs/0028-testing-architecture-kind-stage-replay.md).

## Test Subpackage Placement

Each source subpackage maps 1:1 to a test subpackage at the parallel path
([TEST-010](specs/048-testing-architecture.md) is the canonical
reference). Backends are the only exemption: `src/remote_store/backends/`
fans out into one test subpackage per concrete backend under
`tests/backends/<backend>/` to satisfy TEST-003. The table below restates
the invariant in lookup form.

| Subject | Subpackage | Naming |
|---------|------------|--------|
| Core library source (`src/remote_store/_<x>.py`) | `tests/` root | `test_<x>.py` (or feature-named for cross-cutting) |
| Sync ext-module source (`src/remote_store/ext/<x>.py`) | `tests/ext/` | `test_<x>.py` (no `ext_` prefix; mirrors src layout) |
| Async ext-module source (`src/remote_store/aio/ext/<x>.py`) | `tests/aio/ext/` | `test_async_<x>.py` |
| Async cross-cutting tests (drift guard, adapters, async Store/Backend ABC) | `tests/aio/` | `test_async_*.py` |
| Cross-backend conformance (parametrised over the registry) | `tests/backends/conformance/` | per spec 048 TEST-002 |
| Backend-specific tests (one home per backend, sync + per-backend `aio/`) | `tests/backends/<backend>/` | per spec 048 TEST-003 / TEST-010 |
| Shared backend helper not owned by one backend (`src/remote_store/backends/_<x>.py`, e.g. `_flat_ns`) | `tests/backends/` root | `test_<x>.py` (the only bare test file allowed there; spec 048 TEST-010 "Shared backend helpers") |
| Backend fixture registry + per-backend factories | `tests/backends/fixtures/` | — |
| HTTP cassettes (BK-181 onward; HTTP-transport backends only) | `tests/backends/cassettes/<backend>/` | — |
| End-to-end workflow tests (require Docker services) | `tests/e2e/` | — |
| `scripts/` utilities and build tooling | `tests/scripts/` | `test_<script>.py` |

The `check-test-placement` lint
([`scripts/check_test_placement.py`](../scripts/check_test_placement.py))
enforces three rules at CI time, all derived from spec 048:

- **S** — tests that load modules from `scripts/` via `sys.path` manipulation
  must live in `tests/scripts/`. Tests using
  `importlib.util.spec_from_file_location` are review-enforced.
- **B** — top-level `tests/test_*.py` and `tests/aio/test_async_*.py` may
  import from `remote_store.backends` only the in-process backend modules
  (`_memory`, `_local`) and the shared `_fileinfo` helper module; every
  symbol in those modules is allowed. Concrete cloud / network backends
  belong under `tests/backends/<backend>/` per TEST-003. The banned-class
  roster is derived at script import via a static AST scan of
  `src/remote_store/backends/` and `src/remote_store/aio/backends/`
  (see `_discover_banned_backend_names`); a new backend file added under
  either directory joins the banned set automatically. Wildcard imports
  (`from remote_store.backends import *`) are flagged unconditionally
  because they may pull in any current or future banned class. The
  grandfathered allow-list (`_BACKEND_AT_ROOT_GRANDFATHERED`) is
  self-pruning: an entry whose underlying file no longer triggers a
  violation is reported as a stale entry, so the list shrinks
  monotonically without manual audits. Per-file migration is tracked as a
  follow-up audit.
- **E** — ext-module tests live at `tests/ext/test_<x>.py` (mirroring
  `src/remote_store/ext/`). Top-level `tests/test_ext_*.py` is banned, and
  every `tests/ext/test_<x>.py` must have a matching
  `src/remote_store/ext/<x>.py`. The single namespace-wide contract test
  (`tests/ext/test_contract.py`) is on the script's allow-list.

<a id="rules"></a>
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

6. <a id="prefer-real-dependencies"></a>**Prefer real dependencies over mocks** [review-enforced]
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

13. **An inherited ABC default must be opt-in, not opt-out** [review-enforced]
    — where an ABC method is concrete with a default, conformance asserts
    *override-or-declared-exemption*, both directions. Not overriding is a
    decision that must cost a list entry and a spec citation; otherwise
    forgetting is indistinguishable from deciding. See
    [§ Declaring an exemption](#declaring-an-exemption).

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
| 13 | Concrete ABC default → conformance asserts override-or-exemption | review |

### Test code economy

Bloated suites bury meaningful tests, inflate coverage without behavioral
signal, and double refactoring cost. Delete tests that don't provide value
(BK-014: -8.6% code, zero coverage loss).

### A green test can be vacuous

A passing test proves nothing if it never ran the code under test, or only
confirmed your own assumptions. Five ways a test lies green:

- **It was skipped, not run.** A conformance suite that silently skips when its
  emulator or live account is unavailable is vacuous, not passing. Verify the
  path actually executed (e.g. that the parametrization collected the fixture and
  the test was not deselected), not just that the process exited zero.
- **A mock encodes your assumptions, not the dependency's behaviour.** `spec=`
  (Rule 4) constrains attribute *names*, but `MagicMock(spec=Backend)` still
  accepts any *call shape* and returns a mock — an invalid SDK call signature
  passes silently. For anything you don't own (Rule 5), pin behaviour against a
  real or recorded dependency and verify the call shape against the live service,
  because a mock will never reject a call the real service would.
- **No positive control.** Trust a zero-failure result only after the same
  harness, on the same machine, has produced a *known* failure. A repro that
  cannot fail is not exercising what you think it is.
- **It asserts the wrong signal.** To prove a blocking call was offloaded to a
  worker thread, assert it ran off the event-loop thread (thread identity), not
  that it completed "fast enough" — timing is flaky and proves nothing.
- **An inherited default satisfies the assertion.** When an ABC method is
  *concrete with a default* (`check_health()`, and any other `# noqa: B027`
  no-op), a conformance assertion loose enough to admit the default — "returns
  `None` **or** raises a mapped error" — is satisfied by a backend that never
  implemented the method at all. Participation in the fixture proves nothing
  here: the backend is collected, exercised, and green, and the suite still
  cannot see that the probe does not exist. See Rule 13.

### Declaring an exemption (Rule 13) { #declaring-an-exemption }

An ABC method that is concrete with a default has two silent readings, and
the code cannot tell them apart. `MemoryBackend` does not override
`check_health()` because an in-memory store is always healthy; a network
backend that does not override it has *no health check at all*. Both are the
same absence. Asking "does it override?" therefore flags both or neither, and
neither answer is useful.

So do not ask the code for intent — make the intent declared, and check the
declaration in both directions:

```python
# The exemption is the artifact. An entry costs a spec ID and a reason.
_NO_PROBE = {
    "memory": "PING-008 — in-memory, always healthy",
}

# Resolve the class that actually supplies the method. Do NOT compare against a
# single hardcoded ABC (`type(backend).check_health is not Backend.check_health`):
# the library has two backend ABCs, and an async backend inheriting
# `AsyncBackend`'s no-op is `is not Backend.check_health` — trivially true. That
# form reports "overrides" for a backend with no probe at all, so it fails open
# for precisely the case it is meant to catch.
_ABC_DEFAULTS = (Backend, AsyncBackend)

def _has_own_probe(cls: type) -> bool:
    owner = next(k for k in cls.__mro__ if "check_health" in k.__dict__)
    return owner not in _ABC_DEFAULTS

def test_health_probe_is_declared(backend: Backend, backend_name: str) -> None:
    overrides = _has_own_probe(type(backend))
    if backend_name in _NO_PROBE:
        # Direction 2: an exemption that grew a real probe is stale.
        assert not overrides, f"{backend_name} now probes; drop it from _NO_PROBE"
    else:
        # Direction 1: silence is not consent.
        assert overrides, f"{backend_name} inherits the no-op default; probe it or declare it"
```

Direction 1 is the one that catches the bug: a new backend cannot reach green
by omission, because the default is no longer reachable without saying so.
It only works if the predicate asks *which class supplied the method*, not
*is it unequal to one particular ABC* — see the comment above, and note that
the sync/async ABC split is itself the trap the rule exists to close.
Direction 2 is what stops `_NO_PROBE` rotting into a junk drawer — the list
is pinned to reality, so it shrinks when a backend earns a probe instead of
silently carrying a lie. `scripts/check_test_placement.py` already uses this
shape: its grandfathered allow-list is self-pruning, reporting an entry whose
file no longer violates, so the list "shrinks monotonically without manual
audits."

The general form, beyond health checks: **when the base class supplies a
usable default, the conformance suite must assert on the presence of a
decision, not on the outcome of the call.** An outcome assertion loose enough
to accept the default cannot distinguish a backend that implemented the
contract from one that ignored it. This applies to any `# noqa: B027` method
the ABC grows.

**Rule 13 does not replace a behavioural test.** It is a presence-of-decision
check: it passes the moment an override *exists*, and cannot see whether that
override does anything — a stub, or one that swallows the error it should
raise, satisfies it. Pairing is the point: Rule 13 proves the implementation
is *there* (and keeps the next backend from omitting it), while a per-backend
outcome test proves it *works*. Substituting one for the other reintroduces
the original defect at a different altitude, because presence is not
behaviour.

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

### Running stages, live tests, and cassettes

The operational recipes — stage selection, live-cloud invocation, and cassette
record/refresh/replay — live in the repo-only
[`sdd/TESTING-RUNBOOK.md`](TESTING-RUNBOOK.md). This page stays standards-only so
the runnable commands are not dual-published to the docs site.

### Provenance

Derived from [`sdd/research/research-testing-best-practices.md`](research/research-testing-best-practices.md).
