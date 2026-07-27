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
5. **Replay.** Real backend SDK code paths against a recorded HTTP
   cassette (TEST-007). No live network, no Docker, no live cloud
   account. Distinct from mocked because no `MagicMock` is used; the
   real SDK pipeline runs and the transport layer alone is stubbed.

The canonical kind strings used in the fixture registry (TEST-004)
are the lowercased forms of these names: `"pure"`, `"mocked"`,
`"real-local"`, `"real-live"`, `"replay"`.

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

**Invariant:** A single, parametrised, cross-backend conformance test
set is the source of truth for the `Store` and `Backend` contracts
every backend must satisfy. Conformance tests reference only the
cross-backend `Store` and `Backend` API surface and parametrise over
the fixture registry (TEST-004). They contain no backend-specific
branching. See TEST-010 for the concrete location.

**Postcondition:** Adding a new backend that satisfies the `Backend`
or `AsyncBackend` ABC and registers a fixture (TEST-004) extends
conformance coverage automatically. No conformance test names a
concrete backend.

**Capability filtering:** Conformance tests gate on cross-backend
[`Capability`](../specs/003-backend-adapter-contract.md) values via
the mechanism in TEST-005. Backend fixtures that do not declare a
capability skip the corresponding tests silently.

**Out of scope for conformance:** behaviour expressible only in one
backend's protocol or storage model. See TEST-003.

---

## TEST-003: Backend-Specific Tests Are Isolated Per Backend

**Invariant:** Tests for behaviour that cannot be expressed in
cross-backend terms are isolated per backend, one home per concrete
backend. They parametrise only over fixtures of that backend
(registry filtered by `backend == "<x>"`). See TEST-010 for the
concrete location.

Behaviour belongs here when the contract is observable in only one
backend's protocol, vendor configuration, or storage model. Examples:
the Azure ADLS Gen2 hierarchical namespace and its directory-marker
semantics, S3 multipart-upload edge cases, SFTP key authentication
modes, SQL dialect particulars (PostgreSQL `bytea` versus Large
Objects, MySQL `LONGBLOB` limits).

**Postcondition:** No backend-specific test runs against a different
backend's fixture.

**Sync and async co-location:** Sync and async backend-specific tests
are co-located in the same per-backend home. The sync test file
parametrises over that backend's sync fixtures (registry filtered by
`is_async is False`); a sibling async submodule holds async test
files that parametrise over the async fixtures (`is_async is True`).
Test logic shared between the two is extracted to a `_helpers`
module imported by both. The async sibling is omitted when no
async-specific behaviour exists for the topic. Sync `def` and
`async def` test methods are not mixed in one file. See TEST-010 for
the concrete naming.

**Configuration tests** (construction options, opt parsing, registry
wiring) live in the same per-backend home.

**Replay tier for HTTP deviation suites:** a per-backend deviation suite
whose transport is HTTP may adopt the TEST-007 record/replay pattern so
its HTTP is captured once and replayed creds-free at Stage 1, exactly like
conformance. It registers a dedicated `<backend>_live_<topic>` /
`<backend>_replay_<topic>` fixture pair carrying the backend's
`cassette_profile` (so cassette routing, scrub, and the recorder all see it)
and the `conformance_excluded` flag (so it never enters the conformance
walk). The deviation suite's own conftest parametrises its tests over the
pair. The cassettes share the backend's `cassettes/<backend>/` directory
under a distinct alias. Example: the Azure HNS deviation suite's
`azure_live_hns` / `azure_replay_hns` pair (BK-303).

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
    kind: Literal["pure", "mocked", "real-local", "real-live", "replay"]
    capabilities: frozenset[Capability]
    is_async: bool                         # disambiguates the AnyBackend union for parametrize
    flat_namespace: bool = False           # true when the backend has no real directory entries
    self_op_supported: bool = True         # true when move(p,p)/copy(p,p) is a safe no-op
    transport: Literal["http", "ssh", "fs", "memory", "sql"] = "fs"
    container: Literal["minio", "azurite", "sftp", "none"] = "none"
    cleanup: Callable[[AnyBackend], None] | None = None
    aclose: Callable[[AnyBackend], Awaitable[None]] | None = None
```

``aclose`` is awaited in the async indirect fixture's teardown when set;
sync fixtures and async fixtures whose teardown is purely synchronous
leave it ``None``. Sync ``cleanup`` and async ``aclose`` are independent:
a fixture may set both when it has both sync resources to release and an
async pool to close.

The four declarative flags after ``is_async`` describe per-fixture
behaviour that conformance helpers consult to gate test bodies
(``flat_namespace`` / ``self_op_supported``) or that downstream tooling
reads to derive scopes (``transport`` / ``container``). They make the
fixture record self-describing: a flat-namespace skip no longer requires
a hand-maintained backend-name set in conformance helpers, so the
Azurite emulator (flat) and live ADLS Gen2 (HNS) — both
``backend == "azure"`` — disagree correctly.

**Source of truth.** The static fields are loaded from two TOML files
in the fixture package: ``tests/backends/fixtures/backends.toml`` (per
backend family) and ``tests/backends/fixtures/fixtures.toml`` (per
fixture, with overrides on top of the family defaults). The pure
loader at ``tests/backends/fixtures/_loader.py`` validates closed
enums (``stage``, ``kind``, ``transport``, ``container``) at parse
time. Per-fixture Python modules supply only the runtime callables —
``factory``, ``cleanup``, ``aclose``, ``capabilities``, ``marks`` —
and splat the loader's ``to_kwargs()`` for the rest.

**Postcondition:** Conformance parametrize is auto-generated by
walking the registry, filtered by stage (TEST-006) and capability
(TEST-005). Backend-specific tests walk the registry filtered by
`backend == "<x>"`.

**Isolation:** `factory()` returns a fresh backend instance scoped to
each test. `cleanup()` runs in fixture teardown. Cross-test state
sharing is forbidden.

---

## TEST-005: Capability Gating Uses Native Pytest Mechanisms

**Invariant:** Conformance tests gate on capabilities and stages via
parametrize-id filtering at registry walk time. Runtime conditions
(env vars, infrastructure availability) gate via native
`pytest.mark.skipif` or fixture-level `pytest.skip(...)`. No custom
`@requires(...)` marker layer is introduced.

**Capability and stage gating (id-filter):** A test
asserting an `ATOMIC_WRITES` contract is parametrised over the
subset of the registry whose `capabilities` set contains
`Capability.ATOMIC_WRITES` and whose `stage <= --stage`. Fixtures
that do not match the filter produce no parametrize id at all; they
are absent from the test session and emit no `SKIPPED` line. Both
`stage` and `capabilities` are static per fixture, so the filter is
applied once at collection time.

**Runtime gating (skipif / fixture skip):** Conditions
that depend on per-run state (env vars set, Docker daemon reachable,
cassette file present) gate via `pytest.mark.skipif` on the test or
`pytest.skip(...)` inside the fixture's `factory()`. These do emit
visible `SKIPPED [reason]` entries because the test was registered
in the parametrize before the skip resolved.

**Postcondition:** No special pytest plugin is required to read the
gating logic. A reader can trace either gate (id-filter or skipif)
from the parametrize source or the fixture body to the registry
without indirection.

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

**Explicit stage with missing infrastructure:** When an explicit
`--stage=N` selects a tier whose infrastructure is unavailable on
the running machine (e.g. `--stage=3` without Docker, or `--stage=2`
without Docker), fixtures of the unavailable tier skip via their
fixture-level `pytest.skip(...)` reason. Collection still succeeds
and tests parametrised over fixtures of available tiers run. The CLI
flag does not abort the session.

**Running Stage-3 (live) fixtures needs `-m live` as well.** Live
fixtures additionally carry `pytest.mark.live`, and the default
`addopts` carry `-m 'not live'`. So `--stage=3` alone is not enough —
a live run needs `--stage=3` **and** `-m live` together (plus the
per-backend opt-in env var). `--stage=3` without `-m live` collects
the live fixtures but deselects every live-marked node; `-m live`
without `--stage=3` finds none (the stage filter excludes them). For a
single backend's live conformance, e.g.:
`RS_TEST_LIVE_GRAPH=1 pytest tests/backends/conformance -k graph_live --stage=3 -m live`.

**CI mapping:** Per PR (`ci.yml`), the primary interpreter runs Stage 2
(`test-primary` / `test-primary-sftp`) and the non-primary interpreters
run Stage 1 (`test`); the full Stage-2 suite on every supported
interpreter runs in the scheduled/on-master `ci-full.yml` backstop. This
tiering (BK-319, [ADR-0032](../adrs/0032-tiered-ci-gate-with-full-matrix-backstop.md))
keeps the per-PR gate under five minutes; the stage invariant itself is
unchanged. A separate manually-triggered or scheduled job runs Stage 3.
Per-backend cost guardrails for Stage 3 are out of scope for this spec.
See Notes.

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
pipeline coverage) is specified separately: this spec fixes the
contract, not the mechanism. See
[spec 049](049-live-recording-architecture.md) for the recording
transport — the scrub core, per-backend cassette profiles, pre-signed
URL policy, and audit gates.

**Scope:** [TEST-008](#test-008-replay-scope-is-http-transport-only)
narrows this invariant — see its "Noted exception — S3" paragraph for
the one HTTP backend that does not ship a `<backend>_replay` fixture.

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

**Noted exception — S3.** S3 is HTTP-transport but does not currently
ship a `s3_replay` fixture. The implementing recording library
(vcrpy; diagnosed on 8.1.1, re-test tracked as BK-327) cannot drive
the `aiobotocore` request/response wrappers that `s3fs` rides on,
and `s3fs` exposes no equivalent of
the `azure.core` transport injection that solves the analogous
async-aiohttp problem for Azure. The `s3_moto` Stage-1 fixture
provides in-process S3 coverage for the conformance surface, so the
gap that motivates cassettes for Azure (Azurite cannot emulate the
Hierarchical Namespace) does not apply. Diagnosis in
[`sdd/research/research-bk-181-s3-cassette-infeasibility.md`](../research/research-bk-181-s3-cassette-infeasibility.md).

**Postcondition:** `tests/backends/cassettes/` contains
subdirectories only for HTTP-transport backends. Backends excluded
by this invariant rely on Stage 2 Docker fixtures as their cheapest
source of truth, with no Stage 3 to Stage 1 demotion path. The noted
S3 exception relies on `s3_moto` (Stage 1) plus `s3_live` (Stage 3).

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

**Invariant:** Each source subpackage has exactly one corresponding
test subpackage at a parallel path: `src/remote_store/<x>/` ↔
`tests/<x>/`, with `src/remote_store/` as the core root mapping to
`tests/`. Each source file `src/remote_store/<x>/<f>.py` has at most
one test file at `tests/<x>/test_<f>.py`. The `tests/` tree groups
files by concern, and the concerns are the source subpackages.

**Backend exemption.** `src/remote_store/backends/` and
`src/remote_store/aio/backends/` map to *N* test subpackages — one per
concrete backend at `tests/backends/<backend>/` (sync) and
`tests/backends/<backend>/aio/` (async) — to satisfy TEST-003. Sibling
subtrees `tests/backends/conformance/`, `tests/backends/fixtures/`,
and `tests/backends/cassettes/` are infrastructure for the backend
exemption (cross-backend conformance, fixture registry, HTTP recordings),
not additional source-to-test correspondences. No other source
subpackage may break the 1:1 rule; new exemptions require a spec
amendment.

**Shared backend helpers.** Some modules under
`src/remote_store/backends/` (and `src/remote_store/aio/backends/`) are
not a concrete backend but a helper shared across several — e.g.
`_flat_ns.py`, `_fileinfo.py`, `_azure_common.py`, `_s3_base.py`. These
have no single per-backend home. When a behaviour is expressible only as
a white-box unit test of the helper (not as cross-backend conformance),
the test lives at the backends package root as
`tests/backends/test_<f>.py`, mirroring the way a core module
`src/remote_store/_<x>.py` maps to `tests/test_<x>.py`. This is the one
place a bare `test_*.py` file is permitted directly under
`tests/backends/`. Today only `_flat_ns.py` (ID-211) carries such a test
(`tests/backends/test_flat_ns.py`); the rule B import restriction in
`check_test_placement.py` does not apply below the `tests/` root, so a
helper test may import its helper module directly.

**Top-level scope.** Top-level non-backend tests
(`test_store.py`, `test_path.py`, etc.) do not import the fixture
registry and do not parametrise across backends. They use a single
concrete backend (typically `MemoryBackend`) when one is needed.

```
tests/
  test_store.py                  # non-backend concerns at top level
  test_path.py
  test_registry.py
  ...
  ext/                           # mirrors src/remote_store/ext/. TEST-002.
    test_arrow.py                # one file per ext module, naming matches src
    test_batch.py
    ...
    test_contract.py             # namespace-wide contract (allow-listed; no ext/<x>.py pair)
  aio/                           # async variants of non-backend tests
    test_*.py
    ext/                         # mirrors src/remote_store/aio/ext/
      test_async_*.py
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
      backends.toml              # per-backend-family declarative facts (SSoT)
      fixtures.toml              # per-fixture declarative facts (SSoT)
      _loader.py                 # pure TOML loader; closed-enum validation
      registry.py                # ``BackendFixture`` record + register/fixtures
      _state.py                  # ``current_stage`` / ``INFRA`` runtime state
      _live_env.py               # Stage 3 env-var preconditions
      test_registry.py           # spec-marker tests for the registry itself
      memory.py                  # representative per-fixture factory modules
      local.py
      azurite.py
      sftp_docker.py
      azure_live.py
      azure_live_async.py
      s3_live.py
      ...                        # full set in fixtures.toml
    cassettes/                   # HTTP recordings. TEST-007. HTTP backends only.
      azure/
      s3/
  scripts/                       # tests for scripts/ utilities
  e2e/                           # end-to-end workflows
```

**Backend isolation:** Only files inside the backend subtree may
import from the fixture registry. A concrete backend's name appears
only inside that backend's own home, in registry/fixture/cassette
files dedicated to it, or in registry code that enumerates all
backends. Cross-concern tests reach backends through the registry,
never by direct backend import.

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
