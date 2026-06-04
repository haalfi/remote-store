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

### Cassette Refresh (HTTP-transport backends)

Cassettes under `tests/backends/cassettes/<backend>/` are committed
snapshots of real HTTP traffic. Refresh them when the backend SDK,
the scrubbing layer, or the real service responses change.

**Prerequisite (Azure):** see [Azure HNS account setup](../docs-src/guides/backends/azure-hns-setup.md)
for credential and `.env` configuration. The recording needs the live
opt-in flag set in the invoking shell — keeping it out of `.env` is
deliberate so a default `hatch run test` never touches a real account.

```bash
RS_TEST_LIVE_HNS=1 hatch run record-azure
```

`scripts/record_cassettes.py --backend azure` deletes existing cassettes, re-records
sync and async fixtures against a live ADLS Gen2 account, verifies no credentials
survived scrubbing, and runs a Stage 1 replay smoke test. Pass `--verify-only` to
skip recording and re-run only the verification steps.

To record or refresh a **single** cassette without the all-or-nothing tree-wipe,
pass `--node` with the live-variant node id (`hatch run` forwards the flag, or
call the script directly):

```bash
RS_TEST_LIVE_HNS=1 hatch run record-azure \
  --node "tests/backends/conformance/test_errors.py::TestX::test_y[azure_live]"
```

This skips the Step-1 delete and the min-cassette guard, records only the named
test, then runs the same scrub-verify + Stage 1 replay over the whole corpus.
Use it for a focused PR diff: every other cassette's volatile headers stay put.

Per [TEST-009](specs/048-testing-architecture.md#test-009-cassette-refresh-is-explicit):
CI does not auto-record; a refresh is a normal PR diff.

### Cassette-First Bug Investigation

When investigating a bug in an HTTP-transport backend whose live
behaviour is recorded as a cassette, default to **replay-first**: work
on the committed cassette until root cause is clear, escalate to a
fresh recording only if the cassette cannot carry the diagnosis. Final
sign-off always runs against the live service.

The architecture under this workflow is
[ADR-0028](adrs/0028-testing-architecture-kind-stage-replay.md); this
section is the procedural recipe.

**Step 1 — Reproduce on the cassette.** Run the failing conformance
test against the `<backend>_replay` (and `<backend>_replay_async`)
fixture. No credentials, no network, no Docker. For Azure HNS bugs the
cassette already exists for every conformance test that was active
when [BK-181](BACKLOG-DONE.md) landed.

```bash
hatch run python -m pytest "<nodeid>[azure_replay]" -v --tb=short
```

If the test is already marked `xfail(strict=False)` against real-Azure
fixture ids (the BK-180 follow-up parked confirmed defects this way
to keep CI green), pytest reports `XFAIL` and you cannot see the
assertion. Force the underlying failure with `--runxfail`:

```bash
hatch run python -m pytest "<nodeid>[azure_replay]" --runxfail -v --tb=short
```

The xfail roster lives at the top of
[`tests/backends/conformance/conftest.py`](../tests/backends/conformance/conftest.py);
look for the `pytest_collection_modifyitems` hook and the constants it
applies. Removing a test function name from the roster un-xfails it for
all real-Azure fixture ids in one place.

**Step 2 — Classify cassette sufficiency.** Read the backend code
that the failing test exercises and ask: does the fix require any
HTTP call the cassette does not already contain?

| Fix shape | Cassette sufficiency | Action |
|-----------|---------------------|--------|
| In-process filter / mapping over data the SDK already returns | Sufficient | Proceed to step 3 |
| Adds, removes, or reorders SDK calls | Insufficient | Refresh the cassette (needs Stage 3 live access), then resume on the new one. Use `hatch run record-azure --node "<nodeid[azure_live]>"` for a single test to avoid churning the whole corpus, or plain `hatch run record-azure` to re-record everything |

The decision is mechanical: list the SDK calls the fix introduces, grep
the cassette `interactions:` list for matching `method` + `uri`
patterns, and proceed only when every needed call is already recorded.
For example, a fix that adds a per-entry HEAD on directory blobs is
sufficient if `rg "method: HEAD" tests/backends/cassettes/azure/<test>.yaml`
already shows the matching `uri:` lines.

**Step 3 — Fix.** Implement the change in the backend module(s).

**Step 4 — Verify on replay.** Remove the test function name from the
xfail roster (same file referenced in Step 1) and re-run the same
nodeid without `--runxfail`. Green = the fix is consistent with the
recorded wire behaviour.

**Step 5 — Final verification on live.** Run the test against the
`<backend>_live` / `<backend>_live_async` fixture before merge:

```bash
RS_TEST_LIVE_HNS=1 hatch run python -m pytest "<nodeid>[azure_live]" \
    --stage=3 -m live -v --tb=short
```

Live is the source of truth; the cassette is only a faithful recording
of a single trajectory. Account-config variance, eventual consistency,
and timing-dependent SDK paths can hide behind a green replay.

Per [TEST-006](specs/048-testing-architecture.md#test-006-stage-selection):
live tests run only at `--stage=3` with the matching per-backend opt-in
env var (`RS_TEST_LIVE_HNS=1` for Azure); CI never runs them.

### Provenance

Derived from [`sdd/research/research-testing-best-practices.md`](research/research-testing-best-practices.md).
