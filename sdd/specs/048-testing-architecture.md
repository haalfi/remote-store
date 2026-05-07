# Spec 048 — Testing Architecture

**Scope:** Build & CI tooling. Specifies the layout, fixture model,
capability-gating mechanism, stage selection, and HTTP cassette and
replay layer that govern the `tests/` tree. Not library source code.
The contracts here govern test organisation and the fixture and
runner machinery in `tests/backends/fixtures/` and
`tests/conftest.py`.

**Prefix:** `TEST`

**Companion docs:** [`sdd/TESTING.md`](../TESTING.md) governs test
quality rules (assertion depth, mock discipline, parametrize style).
This spec governs test architecture (where tests live, how backends
are wired in, how stages are selected). The two are complementary.
Quality rules apply uniformly across the architecture.

**Related decisions:** [ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md)
records the rationale for kind and stage axes and the HTTP-only
replay demotion mechanism.

**Tracks:** [BK-175](../BACKLOG-DONE.md). The design phase is
delivered by this spec and ADR-0028. Implementation phases are
tracked in [BACKLOG.md](../BACKLOG.md).

---

## TEST-001: Two Orthogonal Axes

**Invariant:** Every test executes against a fixture characterised by
two independent axes.

**Kind**, what the test wires up:

1. **Pure.** No backend, no fixture beyond pure code in the repo.
2. **Mocked.** Backend replaced by a `MagicMock(spec=...)`. Rare by
   [`TESTING.md`](../TESTING.md) Rule 6 (prefer real dependencies).
3. **Real-local.** Real backend code paths against a local fixture,
   library, or Docker service. Examples include `LocalBackend`,
   `MemoryBackend`, SQLite, Azurite, MinIO, and Dockerised SFTP.
4. **Real-live.** Real backend code paths against a live cloud
   service. Examples include real ADLS Gen2, real S3, and a live
   SSH server.

The canonical kind strings used in the fixture registry (TEST-004)
are the lowercased forms of these names: `"pure"`, `"mocked"`,
`"real-local"`, `"real-live"`.

**Stage**, the cost and availability tier the test runs in:

1. **Stage 1.** Repo only. Zero cost. No restriction on volume,
   amount, or frequency. Default when Docker is unavailable.
2. **Stage 2.** Requires Docker. Zero cost. No restriction on volume,
   amount, or frequency. Default when Docker is reachable.
3. **Stage 3.** Requires a live cloud account. Costs money. Run with
   care. Gated behind explicit env vars and not part of default CI.

**Postcondition:** No test combines kinds or stages implicitly. A
fixture declares exactly one kind and exactly one stage.

**Rationale:** [ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md)
§ Two orthogonal axes: kind and stage.

---

## TEST-002: Conformance is the Cross-Backend Spine

**Invariant:** `tests/backends/conformance/` contains the single, parametrised
behavioural test set that every backend must satisfy. Tests in
`tests/backends/conformance/` reference only the cross-backend `Store` and
`Backend` API surface and parametrise over the fixture registry
(TEST-004). They contain no backend-specific branching.

**Postcondition:** Adding a new backend that satisfies the `Backend`
ABC and registers a fixture (TEST-004) extends conformance coverage
automatically. No conformance test names a concrete backend.

**Capability filtering:** Conformance tests gate on cross-backend
[`Capability`](../specs/003-backend-adapter-contract.md) values via
the mechanism in TEST-005. Backend fixtures that do not declare a
capability skip the corresponding tests silently.

**Out of scope for conformance:** behaviour expressible only in one
backend's protocol or storage model. See TEST-003.

---

## TEST-003: Backend-Specific Tests Live in `tests/backends/<backend>/`

**Invariant:** Tests for behaviour that cannot be expressed in
cross-backend terms live in `tests/backends/<backend>/`, one folder
per concrete backend. These tests parametrise only over fixtures of
that backend.

Behaviour belongs here when the contract is observable in only one
backend's protocol, vendor configuration, or storage model. Examples:
the Azure ADLS Gen2 hierarchical namespace and its directory-marker
semantics, S3 multipart-upload edge cases, SFTP key authentication
modes, SQL dialect particulars (PostgreSQL `bytea` versus Large
Objects, MySQL `LONGBLOB` limits).

**Postcondition:** No `tests/backends/<backend>/` test runs against a
different backend's fixture. `tests/backends/<backend>/aio/` exists
only when sync and async semantics genuinely diverge. Otherwise the
sync file parametrises over both sync and async fixtures of the same
backend.

**Configuration tests** (construction options, opt parsing, registry
wiring) also live here in `tests/backends/<backend>/test_config.py`.

---

## TEST-004: Fixture Registry and Metadata Interface

**Invariant:** Every backend fixture is a record with the following
shape, registered in `tests/backends/fixtures/registry.py`:

```python
AnyBackend = Backend | AsyncBackend  # type alias spanning both ABCs

@dataclass(frozen=True)
class BackendFixture:
    name: str                              # unique fixture id, e.g. "azure_live"
    backend: str                           # backend family, e.g. "azure"
    factory: Callable[[], AnyBackend]      # produces a fresh isolated instance
    stage: int                             # 1, 2, or 3 per TEST-001
    kind: Literal["pure", "mocked", "real-local", "real-live"]
    capabilities: frozenset[Capability]
    is_async: bool                         # disambiguates the AnyBackend union for parametrize
    cleanup: Callable[[AnyBackend], None] | None = None
```

**Postcondition:** Conformance parametrize is auto-generated by
walking the registry, filtered by stage (TEST-006) and capability
(TEST-005). Backend-specific tests in `tests/backends/<backend>/`
walk the registry filtered by `backend == "<x>"`.

**Isolation:** `factory()` returns a fresh backend instance scoped to
each test. `cleanup()` runs in fixture teardown. Cross-test state
sharing is forbidden.

---

## TEST-005: Capability Gating Uses Native Pytest Mechanisms

**Invariant:** Conformance tests gate on capabilities and stages via
native `pytest.mark.skipif` and parametrize-id filters. No custom
`@requires(...)` marker layer is introduced.

**Mechanism:** A test asserting an `ATOMIC_WRITES` contract is
parametrised over the registry. The parametrize id-filter excludes
fixtures whose `capabilities` set does not contain
`Capability.ATOMIC_WRITES`. Excluded fixtures appear as
`SKIPPED [reason]` in `-v` output.

**Postcondition:** No special pytest plugin is required to read the
gating logic. A reader can trace the skip from the parametrize source
to the registry without indirection.

**Rationale:** [ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md)
§ Capability gating uses native pytest mechanisms.

---

## TEST-006: Stage Selection

**Invariant:** A `--stage=N` pytest CLI option selects which fixtures
are included. Bare `pytest` auto-detects: Stage 2 when a Docker daemon
is reachable, Stage 1 otherwise. Each stage includes all lower stages.

| Stage flag | Fixtures included | Required environment |
|---|---|---|
| `--stage=1` | pure, mocked, plus replay (when cassettes present) | none |
| `--stage=2` | Stage 1 plus Docker fixtures | Docker daemon reachable |
| `--stage=3` | Stage 2 plus live fixtures | per-backend live env vars (e.g. `RS_TEST_LIVE_HNS=1`) |

**Postcondition:** `pytest` with no flags runs Stage 2 when Docker is
reachable and Stage 1 otherwise; the auto-detection is the same on
developer machines and in CI. A developer with Docker available can
still opt down with `--stage=1`. Stage 3 is never implicit. Missing
env vars cause Stage 3 fixtures to skip loudly with a fixture-level
`pytest.skip(...)` referencing the missing variable.

**CI mapping:** The default-CI job runs Stage 2. A separate
manually-triggered or scheduled job runs Stage 3. Per-backend cost
guardrails for Stage 3 are out of scope for this spec. See Notes.

---

## TEST-007: HTTP Cassette and Replay Layer

**Invariant:** Backends whose transport is HTTP support a
`<backend>_replay` Stage 1 fixture that exercises the same SDK code
path as the corresponding `<backend>_live` Stage 3 fixture, with the
HTTP transport stubbed by recorded cassette files in
`tests/backends/cassettes/<backend>/`.

**Demotion flow:**

1. A Stage 3 test runs against `<backend>_live` with `--record`.
2. The recording layer writes a cassette keyed by test name, scrubbed
   of credentials, tokens, request IDs, and other per-run identifiers.
3. The cassette is committed under `tests/backends/cassettes/<backend>/`.
4. Subsequent Stage 1 runs of the same test execute against
   `<backend>_replay`, which reads the cassette instead of issuing
   network requests.

**Postcondition:** A test that originally required a live cloud
account to validate runs at zero cost in every default CI run, while
the live fixture remains the source of truth. If a cassette is
missing for a test, the replay fixture skips that parametrize id
rather than failing.

**Implementation choice** (cassette tech, scrubbing rules, async
pipeline coverage) is deferred to the implementing BK item. This
spec fixes the contract, not the mechanism.

---

## TEST-008: Replay Scope is HTTP-Transport Only

**Invariant:** The cassette and replay mechanism (TEST-007) applies
exclusively to backends whose transport is HTTP(S). It does not
apply to:

- **SFTP.** paramiko speaks SSH binary protocol. No HTTP capture is
  possible. Stage 2 (Dockerised SSH server) is the lowest stage
  available for SFTP truth.
- **SQL backends other than SQLite.** PostgreSQL, MySQL, and other
  client-server SQL dialects speak their own wire protocols. Stage
  2 (Dockerised database) is the lowest stage available. SQLite is
  in-process and is already a Stage 1 fixture by construction.
- **Local filesystem.** Already Stage 1. No demotion needed.

**Postcondition:** `tests/backends/cassettes/` contains
subdirectories only for HTTP-transport backends. Backends excluded
by this invariant rely on Stage 2 Docker fixtures as their cheapest
source of truth, with no Stage 3 to Stage 1 demotion path.

**Rationale:** [ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md)
§ HTTP cassette and replay as a Stage 1 fixture, scoped to HTTP backends.

---

## TEST-009: Cassette Refresh is Explicit

**Invariant:** Cassettes are regenerated by an explicit developer
action, not by a scheduled CI job. The action is `pytest --stage=3
--record`, which runs Stage 3 fixtures in recording mode, writes
cassettes, and reports the diff.

**Postcondition:** A cassette refresh is reviewable as a normal PR
diff. CI does not silently re-record. Drift between cassettes and
real-service responses is detected by the next manual refresh, not
by production traffic.

**Schedulable later:** A scheduled `verify-cassettes-still-replay`
Stage 1 job and a scheduled refresh job may be added once empirical
drift data is available. This spec does not mandate either.

---

## TEST-010: Directory Layout

**Invariant:** The `tests/` tree groups files by concern. The
backend concern is one self-contained subtree under
`tests/backends/`. Other concerns (`Store`, `RemotePath`, registry,
errors, capabilities) live at the top level alongside their own
helpers.

```
tests/
  test_store.py                  # non-backend concerns at top level
  test_path.py
  test_registry.py
  ...
  aio/                           # async variants of non-backend tests
    test_*.py
  backends/                      # the backend concern, self-contained
    conformance/                 # cross-backend parametrised tests. TEST-002.
      test_io.py
      test_listing.py
      test_atomic.py
      test_metadata.py
      test_streaming.py
      test_errors.py
    azure/                       # backend-specific. TEST-003.
      test_config.py
      test_hns.py
      aio/
        test_hns.py              # only when sync and async behaviour diverges
    s3/
      test_config.py
      test_pyarrow.py
    sftp/
      test_config.py
    sqlblob/
      test_config.py
    fixtures/                    # registry and factories. TEST-004.
      registry.py
      memory.py
      local.py
      azurite.py
      minio.py
      sftp_docker.py
      azure_live.py
      azure_replay.py
      s3_live.py
      s3_replay.py
    cassettes/                   # HTTP recordings. TEST-007. HTTP backends only.
      azure/
      s3/
  scripts/                       # tests for scripts/ utilities
  e2e/                           # end-to-end workflows
```

**Backend concern isolation:** Everything backend-related lives
under `tests/backends/`. Conformance, backend-specific tests,
fixtures, and cassettes share that one subtree because they share
the backend concern. Top-level non-backend tests (`test_store.py`,
`test_path.py`, etc.) do not import the fixture registry and do not
parametrise across backends. They use a single concrete backend
(typically `MemoryBackend`) when one is needed.

**Postcondition:** No file outside `tests/backends/` imports from
`tests/backends/fixtures/registry.py`. No file in `tests/`
references a concrete backend by name outside
`tests/backends/<backend>/`, `tests/backends/fixtures/`, or
`tests/backends/cassettes/<backend>/`. Cross-concern tests (`e2e/`)
that touch backends do so via the registry, not by direct backend
import.

---

## Notes

### Migration from current layout

The current `tests/backends/` mixes conformance, backend-specific,
and HTTP-emulator code in a flat structure. Adoption of this spec is
an incremental migration. Implementation BK items track each phase.
Until migration completes, [`sdd/TESTING.md`](../TESTING.md) "Test
Subpackage Placement" remains authoritative for the current state.

### Cost guardrails

Per-test transaction budgets, per-run dollar caps, and Stage 3
scheduling policy are intentionally not specified. Empirical Stage
3 runs are required before fixed numbers can be defended. The spec
is amended once data exists.

### Async parallel structure

Async fixtures are first-class entries in the registry (TEST-004
`is_async=True`) and run in the same conformance tree as their sync
counterparts. The conformance test parametrises over both.
Per-backend `aio/` carve-outs (TEST-003) exist only where sync and
async semantics genuinely differ, not as a default mirror tree.

### Tests

Implementation BK items add the corresponding `tests/scripts/`
coverage for the fixture registry, the parametrize generators, the
recording layer, and the cassette scrubbing rules. Each test traces
back via `@pytest.mark.spec("TEST-NNN")` per
[`000-process.md`](../000-process.md) Rule 2.
