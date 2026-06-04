<!-- doc: repo-only -->
# ID-127 Plan — Microsoft Graph Backend Implementation Roadmap

> **Temporary artefact. Delete when ID-127 closes.** This plan is a
> point-in-time decomposition of the implementation, not a living
> contract. The authoritative baseline is spec
> [044](../specs/044-graph-backend.md), [RFC-0010](../rfcs/rfc-0010-graph-backend.md),
> and ADRs [0021](../adrs/0021-graph-sdk-choice.md)..[0024](../adrs/0024-resource-locked-error.md).
> When those and this plan disagree, the spec/ADR wins and this file is
> wrong (principle 5). On ID-127 close, this file is removed in the same
> PR that moves ID-127 to `BACKLOG-DONE.md`.

## Purpose

Decompose the Graph backend into a sequence of **independently
reviewable, independently mergeable PRs**, each small enough that a
reviewer can hold the whole change in their head. There is no separate
verification gate: **each PR is the verification step**. Every step
below names a commit-message / PR-body tag (e.g. `GR-CORE`) that the
implementing PR must cite.

The backend is built as a contract-expanding feature (BK-237 DoD,
000-process.md § Feature-type Definition of Done). The shape of the
roadmap follows that DoD: the conformance contract and test spine land
**before** the first backend implementation, so the backend moves
itself off an xfail registry against a contract that already exists.

## Sequencing at a glance

```
GR-FOUNDATION ──► GR-CONTRACT ──► GR-CORE ──┬─► GR-READ ──┐
   (1)               (2)            (3)      ├─► GR-WRITE ─┼─► GR-DOCS-E2E ──► GR-DONE
                                            └─► GR-MUTATE ┘     (7)             (8)
                                               (4/5/6)
```

A **real, Graph-enabled M365 tenant provisioned in Step 1 underlies
every later step** — each backend step is reality-checked against the
live (Stage 3) tier, the authoritative tier for Graph (no emulator
exists; RFC-0010 § Test plan), and Stage-3 discoveries are cassetted
back into `graph_replay` so default CI catches the regression at
Stage-1 cost.

GR-READ / GR-WRITE / GR-MUTATE all depend on GR-CORE and are mutually
independent (they fill in disjoint method bodies and clear disjoint
conformance slices); they may merge in any order or in parallel — with
**one soft ordering caveat**: GR-MUTATE's full `close()` acceptance
(GR-051) cannot exercise the *upload-session abort* half until GR-WRITE's
session driver exists, so that one assertion is split (see GR-MUTATE /
GR-WRITE) and the combined `close()` is pinned in GR-DONE.
GR-WRITE additionally realises the async `WriteResult` contract authored
in GR-CONTRACT — transitively pulled in via GR-CORE, but a direct
semantic dependency worth scheduling against. The diagram routes all
three of GR-READ/WRITE/MUTATE into GR-DOCS-E2E as "all backend ops
complete" sequencing; the e2e streaming-integrity *test* itself only
needs READ + WRITE (see GR-DOCS-E2E Dependencies).

## Where the spec-obligated work lands

The merged PR #747 surfaced eight items that must be explicitly owned.
This table is the index so none is buried; each is also called out as a
named acceptance criterion in its owning step.

| Obligated item | Owning step |
|---|---|
| Cassette-spine generalisation (per-backend dir, id-alias, **bearer-token scrub**, record script, httpx-streaming-replay) | **GR-FOUNDATION (1)** |
| Setup guide `graph-setup.md` (doubles as the live-provisioning runbook) | **GR-FOUNDATION (1)** |
| Async `TestWriteResultConformance` decision | **GR-CONTRACT (2)** |
| `ResourceLocked` bundle (runtime + Dafny variant + `_raise_if_err`) | **GR-CONTRACT (2)** |
| `_SENSITIVE_KEYS` widening (`client_secret`, `client_certificate`) | **GR-CORE (3)** |
| `__all__` ↔ `index.md` parity (ID-173) for the four public symbols | **GR-CONTRACT (`ResourceLocked`) + GR-CORE (the three Graph symbols)** |
| e2e wiring into `test_async_streaming_integrity.py` | **GR-DOCS-E2E (7)** |
| BK-237 contract-expanding-feature DoD umbrella checklist | **GR-DONE (8)** |

(The usage guide `graph.md`, examples, and README line are ordinary
deliverables, not part of the surfaced eight; they land in GR-DOCS-E2E.)

## Cross-cutting decisions made here

- **Reality-check against a real tenant from the very beginning.**
  Step 1 provisions a real Graph-enabled M365 tenant + app registration
  + target drive (via the `graph-setup.md` runbook it also writes), so
  every later step is validated against the live Graph API, not only
  respx replay. This matches the RFC's own statement that Stage 3 is the
  authoritative tier for Graph. The live (Stage 3) tier is the
  reality-check substrate; Stage-1 `graph_replay` cassettes are recorded
  *from* those live runs so default CI catches regressions cheaply.
- **Setup guide is front-loaded and dogfooded.** `graph-setup.md` is
  written in Step 1 and walked end-to-end to provision the tenant —
  satisfying the self-validated / proven authoring contract — because
  onboarding is the single largest UX hurdle and provisioning gates
  every live reality-check. The *usage* guide `graph.md` stays late
  (GR-DOCS-E2E): its capability/usage prose depends on the API surface
  that lands in steps 4–6.
- **Cassette spine lands FIRST (before the backend), alongside the live
  credentials.** The scrub layer is security-critical: a cassette
  recorded before a Graph-aware scrub list exists would leak a live
  `Authorization: Bearer` token into a committed file. Landing the scrub
  and the live credentials together means the moment recording is
  possible, leaking is not. The spine also de-risks the unproven
  httpx-streaming-replay path before backend ops depend on it — and
  because live works from Step 1, that proof uses a **real** recorded
  stream, not a synthetic one. See GR-FOUNDATION risk note for the
  documented fallback.
- **Async `TestWriteResultConformance`: option (a).** Land an
  async-parametrised `TestWriteResultConformance` so WR-001a / 004 / 005
  / 012 / 013 exist for `AsyncBackend` (validated against the existing
  `AsyncMemory` / `AsyncAzure` fixtures) before Graph plugs in. Option
  (b) — wrapping `GraphBackend` in `AsyncBackendSyncAdapter` for the sync
  suite — is rejected: it would test the adapter's spool-and-pump
  conversion rather than the backend's native `driveItem`-from-response
  population, which is the actual GR-018 / GR-019 contract.
- **Capabilities declared up front, operations move off xfail
  incrementally.** GR-CORE declares the full GR-003 capability set and
  registers Graph in the conformance fixture registry with the
  operation slices xfail'd. GR-READ / GR-WRITE / GR-MUTATE each clear
  their own slices. This is exactly the DoD "move off the xfail list"
  pattern.
- **`ResourceLocked` lands in GR-CONTRACT, not with the backend.** The
  bundle is fully backend-independent, so it goes in the "contract before
  the backend" step (where the error contract belongs) rather than
  GR-CORE — de-bloating the heaviest step and giving GR-CORE's 423 mapper
  an already-existing class to reference. This **honours ADR-0024's
  intention**, not just its letter: the ADR's concern is that the Dafny
  variant must not be orphaned (shipped as standalone formal work for
  behaviour no code exhibits — the folded-in ID-189 scenario), so it
  "ships together with the Graph backend implementation." Here the bundle
  stays coupled (class + variant + dispatch together) **and** the backend
  that raises it lands in the very next steps of the same ID-127 delivery.
  ADR-0024's literal "same PR as the sub-package" is its wording under a
  one-PR assumption; splitting it across GR-CONTRACT → GR-CORE is the same
  kind of decomposition as splitting the backend across GR-CORE..GR-MUTATE.
  See *Alignment notes*.

---

## Step 1 — GR-FOUNDATION: live tenant, setup guide, and cassette spine

**Scope.** Stand up the substrate that makes every later step
reality-checkable against the real Graph API: provision a live
Graph-enabled M365 tenant (documented as the `graph-setup.md` runbook),
land the two-layer live-credential plumbing, and generalise the
Azure-hardcoded Stage-1 replay machinery with a Graph-aware
(bearer-token) scrub layer so cassettes can be recorded from live
without leaking secrets. No backend code yet.

**Files touched.**
- `docs-src/guides/backends/graph-setup.md` (new — onboarding/provisioning
  runbook modelled on `azure-hns-setup.md`: M365 Developer Program (or
  paid tenant), Entra app registration, redirect URIs, client-secret vs
  certificate, admin-consent URL, scopes, `AADSTS*` errors, token-cache
  location, plus a copy-pasteable **verification snippet** — raw httpx
  token + `GET /me/drive` / site / channel — that proves all three
  `resolve_drive_id` target shapes against the live tenant).
- `docs-src/guides/backends/_nav.yml`, `index.md` (nav entry for the
  setup guide).
- `tests/backends/fixtures/_live_env.py` (Graph two-layer gate:
  `RS_TEST_LIVE_GRAPH=1` **plus** `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` /
  `GRAPH_CLIENT_SECRET` / `GRAPH_DRIVE_ID`; emulator-style guard N/A but
  mirror the Azure helper shape).
- `tests/backends/fixtures/fixtures.toml` (`graph_live` / `graph_replay`
  fixture *entries* in the Azure shape — the conformance fixture *factory*
  that instantiates a backend is deferred to GR-CORE).
- `tests/backends/conformance/conftest.py` (`vcr_cassette_dir`:
  per-backend dispatch instead of unconditional `CASSETTE_DIR_AZURE`;
  extend `_CASSETTE_ID_ALIASES` for `graph_*`).
- `tests/backends/fixtures/registry.py` (generalise the
  `_AZURE_REAL_FIXTURE_IDS` set and missing-cassette → skip hook to
  recognise `graph_*` ids).
- `tests/backends/fixtures/_cassettes.py` (Graph scrub profile: redact
  `Authorization: Bearer`, drop/redact the pre-signed
  `@microsoft.graph.downloadUrl` host + query, scrub `client-request-id`
  / correlation headers; introduce `CASSETTE_DIR_GRAPH`).
- `tests/backends/fixtures/graph_replay_async.py` (new — **new httpx
  streaming-replay plumbing, built from scratch**, not a copy of
  `azure_replay_async.py`. The Azure file swaps in an `azure.core`
  `AsyncioRequestsTransport` because vcrpy's aiohttp stub deadlocks on a
  streamed body; but `GraphBackend` uses a bare `httpx.AsyncClient`
  (`.stream()`, GR-012/GR-015) with no `azure.core` transport seam, so the
  httpx capture/replay path has no equivalent shim to borrow. Azure is the
  *role* model only — see the unproven-streaming risk below; budget this
  as new transport work, not "mirror the Azure file").
- `scripts/record_cassettes.py` (add a `graph` entry to `_BACKENDS`).

**Spec IDs covered.** TEST-007 (per-backend cassette dirs), TEST-009
(record recipe), ADR-0028 (Stage-1 replay recipe); documentation
deliverable `graph-setup.md` (RFC § Documentation deliverables). No GR-*
runtime behaviour yet.

**Acceptance criteria.**
- **Live provisioning is real and dogfooded (named obligation):** the
  `graph-setup.md` verification snippet runs against the provisioned
  tenant and resolves a `drive_id` for at least one target shape; the
  PR records the dogfood evidence (a trace/artifact, secrets redacted).
- **`graph-setup.md` (named obligation)** present, parity-clean against
  the API reference, all on-disk links resolve (AUTHORING Rule 3), and
  the docs-framework check passes.
- The Graph two-layer live gate skips cleanly when either layer is
  missing (unit test), mirroring the Azure pattern; real
  `GRAPH_CLIENT_SECRET` lives only in the gitignored `.env`, never
  committed.
- `vcr_cassette_dir` returns `cassettes/graph/` for a `graph_*` fixture
  id and still `cassettes/azure/` for Azure ids (unit test).
- A scrub-layer unit test feeds a cassette carrying a fake `Bearer`
  token and a `downloadUrl` and asserts neither survives the scrub.
  **This is the security gate for the step.**
- `python scripts/record_cassettes.py --list` (or equivalent) shows the
  `graph` backend.
- The streaming shim replays a chunked `httpx.AsyncClient.stream()`
  cassette round-trip — ideally a **real** recorded stream against the
  live tenant — proving the mechanism before GR-012/GR-015 need it.
- `hatch run lint` clean; existing Azure replay tests still pass.

**Dependencies.** None (this is the substrate).

**Risk / surprises.**
- **Tenant access is the gating prerequisite.** Client-credentials needs
  a tenant admin to grant admin consent for `Files.ReadWrite.All` /
  `Sites.ReadWrite.All`. The free Microsoft 365 Developer Program (E5
  sandbox) is the standard path; a paid tenant needs elevated rights
  (cf. ID-199's Azure-access gating). **If no tenant can be provisioned**,
  the live reality-check is unavailable: later steps fall back to
  respx-only validation, the setup guide cannot be dogfood-verified
  (mark it `[~]` and defer the walk-through to whoever has access), and
  this is called out explicitly — do not fake the dogfood evidence.
- **httpx-streaming-replay is unproven** (RFC-0010 § Test plan): vcrpy
  8.1.1 needed a bespoke transport shim for Azure async, and whether it
  can capture/replay `httpx.AsyncClient.stream()` is open; `respx` has
  no record mode. **If the streaming shim cannot be made to work**, fall
  back per RFC: shrink Stage-1-replay to non-streaming operations and run
  GR-012 / GR-015 (and the round-trip) at Stage 3 only — say so in the
  PR. Does not block later steps (respx still covers request construction).

---

## Step 2 — GR-CONTRACT: async conformance + `ResourceLocked` contract before the backend

**Scope.** Land the contract surface Graph will move onto, all validated
against existing fixtures with no Graph backend code yet: an async
`TestWriteResultConformance`, a capability-matrix assertion, the
`USER_METADATA` strict-gate test, **and the backend-independent
`ResourceLocked` bundle** (runtime class + Dafny variant + `_raise_if_err`
dispatch + ERR-013 test).

**Files touched.**
- `tests/backends/conformance/test_async_extended.py` (or a new
  `test_async_atomic.py`): async-parametrised `TestWriteResultConformance`
  covering WR-001a / 004 / 005 / 012 / 013 for `AsyncBackend`.
- `tests/backends/conformance/` capability-matrix test (assert declared
  set matches a per-backend expected set; unsupported capabilities raise
  `CapabilityNotSupported`).
- `USER_METADATA` strict-gate test (non-empty `metadata=` →
  `CapabilityNotSupported`; `{}` / `None` are no-ops) at the Store layer.
- `src/remote_store/_errors.py` (`ResourceLocked` class + `__all__`).
- `sdd/formal/BackendContract.dfy` (`Error.ResourceLocked(path, backend)`
  variant) + re-translated `sdd/formal/MemoryBackend-py/module_.py` +
  `tests/backends/dafny/_helpers.py::_raise_if_err` dispatch + a direct
  unit test of the `ResourceLocked` dispatch arm (the MemoryBackend
  oracle never raises 423, so conformance never exercises it).
- `docs-src/reference/api/index.md` (parity entry for `ResourceLocked`,
  same commit as the `__all__` addition).
- `tests/backends/fixtures/registry.py` / `fixtures.toml` if an xfail /
  expected-capability registry entry shape needs to exist for backends
  to register against.

**Spec IDs covered.** WR-001a/004/005/010/011/012/013, ASYNC-008/010/021,
GR-003 (matrix shape, exercised by existing backends here; Graph slots in
at GR-CORE), **ERR-013** (`ResourceLocked` runtime class + Dafny variant).

**Acceptance criteria.**
- New async `TestWriteResultConformance` passes against `AsyncMemory`
  and `AsyncAzure` (proves the contract is real before Graph exists).
- Capability-matrix and metadata-gate tests pass against existing
  backends.
- **`ResourceLocked` bundle** (named obligation): runtime class, Dafny
  variant, and `_raise_if_err` dispatch land **together**; Dafny suite
  re-verifies; an ERR-013 unit test covers construction, `path`/`backend`,
  `__all__` membership, and the flat-hierarchy parent, plus a direct
  `_raise_if_err` dispatch-arm test. `check_api_docs.py` passes with
  `ResourceLocked` in both `__all__` and `index.md` (same commit).
- `filterwarnings = error` suite stays clean.
- `hatch run lint` clean (incl. `check_formal_trace` / `check_capability_parity`
  after the Dafny variant lands).

**Dependencies.** None hard; pairs naturally after GR-FOUNDATION. The
`ResourceLocked` bundle is fully backend-independent — it is placed here
(rather than GR-CORE) so the error contract exists before the GR-CORE
`http.py` 423→`ResourceLocked` mapping references it, and to keep the
already-heavy GR-CORE step focused. This honours ADR-0024's intention
because the Graph backend (its only raiser) lands in the immediately
following steps of the same ID-127 delivery — see *Alignment notes*.

**Risk / surprises.**
- Option (a) modifies a **shared** conformance class, so every async
  backend must satisfy the newly-asserted WR slices — if `AsyncAzure`
  does not already populate a rich field the async suite now checks, that
  is a pre-existing gap this step surfaces (record it, do not silently
  weaken the assertion — principle 7). May force a small `AsyncAzure`
  follow-up; flag it rather than absorb it.
- The Dafny re-translation needs the Dafny toolchain to regenerate
  `MemoryBackend-py/module_.py`; if unavailable in dev/CI, land the
  variant + dispatch as a hand-checked translation matching the existing
  variant shape and flag the toolchain status in the PR.

---

## Step 3 — GR-CORE: `_graph` sub-package public surface + foundation

**Scope.** Land the full public API surface and request/error foundation
of the backend with operation bodies stubbed and their conformance
slices xfail'd: construction, capabilities, addressing, HTTP+error
mapping, auth, utils, masking. (The `ResourceLocked` class itself already
exists — it landed in GR-CONTRACT; GR-CORE's `http.py` only wires the
423→`ResourceLocked` mapping.)

**Files touched.**
- `src/remote_store/aio/backends/_graph/` (new sub-package):
  `__init__.py`, `backend.py` (construction GR-001/004/005, name GR-002,
  capability decl GR-003, `to_key`/`native_path` GR-036/036a, `unwrap`
  GR-037, `close` GR-051 baseline, addressing GR-009/010, stubbed ops),
  `http.py` (httpx wrapper, pagination GR-016, error-mapping table
  GR-028..034/045/054/055/046 — mapping `423`→the `ResourceLocked` class
  from GR-CONTRACT, masking GR-035), `auth.py` (`GraphAuth`
  GR-006/007/008), `utils.py` (`GraphUtils.resolve_drive_id` /
  `aresolve_drive_id` GR-057).
- `src/remote_store/aio/backends/__init__.py` (guarded re-export of
  `GraphBackend`, `GraphAuth`, `GraphUtils`).
- `src/remote_store/_config.py` (`_SENSITIVE_KEYS` += `client_secret`,
  `client_certificate`) **and its spec `sdd/specs/020-credential-hygiene.md`
  § SEC-003** — SEC-003 inlines the literal key set in prose (lines 42-45)
  and carries a Forward note (46-50) anticipating this exact ID-127
  addition. The widening makes the inline list stale, so update it (or
  repoint at `_config._SENSITIVE_KEYS` per principle 4) **and** resolve the
  now-satisfied Forward note in the same commit. This is the primary spec
  of the change, not a downstream consumer.
- `sdd/specs/031-ext-dagster.md` § DAG-033 (**downstream consumer**):
  `ext/dagster.py::_build_store` *imports* `_SENSITIVE_KEYS` (no code
  change needed), but DAG-033 **hard-enumerates the literal key set in
  prose** too, equally stale after the widening. Repoint at the single
  source per principle 4. So the widening has **two stale-prose sites —
  SEC-003 and DAG-033** — plus the zero-change Dagster code consumer; both
  prose sites are fixed in this commit.
- `docs-src/reference/api/index.md` (parity entries for the three Graph
  symbols `GraphBackend` / `GraphAuth` / `GraphUtils`; `ResourceLocked`
  parity landed in GR-CONTRACT) ; `pyproject.toml` (`graph` extra per
  ADR-0021) ; `FEATURES.md` (Graph row, capability columns per GR-003).
- `tests/backends/fixtures/fixtures.toml` / `registry.py` (the
  conformance fixture *factory* that instantiates `GraphBackend` for the
  `graph_live` / `graph_replay` entries declared in GR-FOUNDATION; xfail
  registry for unimplemented op slices).

**Spec IDs covered.** GR-001..GR-011, GR-016, GR-028..GR-037, GR-045
(mapper test; the class + ERR-013 are GR-CONTRACT's), GR-050..GR-053,
GR-057, RET-015 (mapping table), SEC-003, DAG-033 (ripple). The
error-mapping *table* GR-CORE's `http.py` authors covers 054/055/046 as
code, but GR-054/055/056's behaviour + test ownership sits in GR-WRITE
(GR-054), GR-READ (GR-055), and GR-MUTATE (GR-056) — so they are
deliberately **not** claimed here, keeping one unambiguous owner per ID
for GR-DONE's traceability sweep. **GR-046 is the deliberate exception:**
it is a **shared umbrella** ID (spec 044 enumerates per-operation failure
postconditions in one section), intentionally sliced across GR-READ /
GR-WRITE / GR-MUTATE — each owning its operation's failure paths, with the
mapping table here. GR-DONE's `@pytest.mark.spec("GR-046")` sweep should
therefore expect **multiple** owners and not flag the multi-owner as an
inconsistency (unlike 054/055/056, which are single-owner by design).

**Acceptance criteria.**
- **`_SENSITIVE_KEYS` widening** (named obligation): config-loaded Graph
  backends auto-wrap `client_secret` / `client_certificate`; test asserts
  it, plus no regression for other backends' keys. **Both stale-prose
  sites updated in the same commit** — spec 020 § SEC-003 (the spec of the
  `from_dict` wrapping, including resolving its now-satisfied Forward note)
  and spec 031 § DAG-033 — each repointed at `_config._SENSITIVE_KEYS` per
  principle 4. Dagster masking (`ext/dagster.py`) inherits the widening
  automatically (it imports the set; no code change).
- `423`→`ResourceLocked` mapping: a respx unit test feeds a `423`
  response and asserts the `ResourceLocked` class (from GR-CONTRACT) is
  raised with `backend="graph"` (GR-045 mapper test; mid-session 423 is
  GR-WRITE's).
- **`__all__` ↔ `index.md` parity** (named obligation, Graph share):
  `check_api_docs.py` passes with `GraphBackend`, `GraphAuth`,
  `GraphUtils` present in both `__all__` and `index.md`, in the **same
  commit** as the `__all__` additions (hard CI gate). `ResourceLocked`'s
  parity entry already landed in GR-CONTRACT.
- Credential masking: a bearer token never appears in `str`/`repr` of any
  raised error or in any backend log record at any level (GR-035 anchors).
- `import remote_store` works without the `graph` extra installed (guarded
  import); capability-matrix test passes for Graph.
- respx unit tests for `GraphUtils.resolve_drive_id` (all three target
  shapes) and the error-mapping table pass.
- `hatch run lint` clean.

**Dependencies.** GR-FOUNDATION (fixture entries + live gate + scrub
spine; first live reality-check of `resolve_drive_id` happens here),
GR-CONTRACT (capability-matrix + metadata-gate contract to register
against, **and the `ResourceLocked` class** the 423 mapper references).

**Risk / surprises.** `import remote_store` must stay clean without the
`graph` extra (guarded import); a missing guard would break the base
install. The `httpx`-streaming dependence of read/write ops is deferred
to those steps. ADR-0024 alignment (`ResourceLocked` landed in
GR-CONTRACT): see *Alignment notes* below.

---

## Step 4 — GR-READ: read, list, metadata, range download

**Scope.** Implement all read-path operations and clear their conformance
slices.

**Files touched.** `src/remote_store/aio/backends/_graph/backend.py`
(`read` GR-012, `get_file_info` GR-013, `list_files`/`list_folders`/
`iter_children` GR-014), `transfer.py` (range-download driver GR-015,
downloadUrl expiry+eTag re-fetch GR-017, `416` mapping GR-055), retry
honouring GR-047/048 on the read path; `file.hashes` → `FileInfo.extra`
GR-049. Tests under `tests/backends/` (respx unit + Stage-1 replay where
streaming-replay is available; integration markers for GR-* listed
integration-only).

**Spec IDs covered.** GR-012..GR-017, GR-046 (read/list/range slices),
GR-049, GR-055; GR-047/048 on read.

**Acceptance criteria.**
- Graph moves off xfail for READ / LIST / METADATA / LAZY_READ
  conformance slices.
- respx tests cover pagination across ≥2 pages (incl. empty `value` +
  `nextLink`), missing/ malformed `nextLink` → `BackendUnavailable`,
  downloadUrl expiry mid-read with eTag-unchanged resume and eTag-changed
  → `BackendUnavailable`, SharePoint range-fallback (WARNING marker +
  `FileInfo.extra["graph.read.range_fallback"]`).
- `read`/`get_file_info` on a folder → `InvalidPath`; missing path on
  list → yields nothing (never raises).
- **Reality-checked against the live tenant** (GR-FOUNDATION): the
  read/list/range paths run green at Stage 3, and a representative live
  run is cassetted back into `graph_replay`.
- `hatch run lint` clean; `filterwarnings = error` clean.

**Dependencies.** GR-CORE.

**Risk / surprises.** SharePoint range behaviour is the unstable area
(GR-015/GR-017): the fallback-to-spool path is asserted via log + `extra`
because the backend has no `StoreEvent` handle (OBS layering). If
streaming-replay (GR-FOUNDATION) was deferred, the streaming slices run
Stage-3-only and the respx unit layer carries the request-construction
assertions.

---

## Step 5 — GR-WRITE: small write, upload session, write_atomic

**Scope.** Implement the write path and clear its conformance slices,
including the native `WriteResult` population both async-conformance
classes from GR-CONTRACT now check.

**Files touched.** `backend.py` (`write` GR-018/019, `write_atomic`
GR-040, auto-mkdir GR-039, BE-008 409 discrimination), `transfer.py`
(upload-session driver: alignment GR-020, chunk PUT GR-021, retry
GR-022, resume from `nextExpectedRanges` GR-023, abort GR-024, token
expiry mid-session GR-038, spool for unknown-length iterators with
`graph.upload.spool_spilled` DEBUG marker), `http.py` (`423`→
`ResourceLocked` mid-session GR-045). Tests as above.

**Spec IDs covered.** GR-018..GR-024, GR-038..GR-040, GR-045 (write
path), GR-046 (write slices), GR-051 (session-abort half), WR-001..WR-013
for Graph, GR-054.

**Acceptance criteria.**
- Graph moves off xfail for WRITE / ATOMIC_WRITE / WRITE_RESULT_NATIVE
  conformance slices; both small-file and upload-session paths populate
  `WriteResult` rich fields (`size`/`etag`/`last_modified`/`version_id`)
  from the `driveItem` response, `source="native"`, `digest=None`.
- respx tests cover exact-320-KiB-boundary chunking, mid-session
  retry/resume, abort (`DELETE {sessionUrl}`), `409` discrimination
  (target-folder / ancestor-file / file-exists), spool spill marker.
- `metadata=` strict gate verified at Store layer (CapabilityNotSupported);
  `{}`/`None` no-op.
- **`close()` upload-session-abort half (GR-051):** with the session
  driver now present, `close()` issues best-effort `DELETE {sessionUrl}`
  for any in-flight session (mirrors GR-024); test asserts the abort
  fires and that `close()` never raises on cleanup. (The poller-cancel
  half of GR-051 is owned by GR-MUTATE; the combined assertion is pinned
  in GR-DONE.)
- **Reality-checked against the live tenant** (GR-FOUNDATION): small and
  upload-session writes run green at Stage 3, including the real chunk
  alignment (GR-020) that respx cannot enforce; the 10 MiB round-trip is
  Stage-3-only and Stage-1 records one representative round-trip.
- `hatch run lint` clean; `filterwarnings = error` clean.

**Dependencies.** GR-CORE **and GR-CONTRACT** — the async
`WriteResult` slices this step clears (WR-001a/004/005/012/013 for
`AsyncBackend`, `WRITE_RESULT_NATIVE` from the `driveItem` response) only
exist once GR-CONTRACT's async `TestWriteResultConformance` has landed.
The chain is transitively satisfied via GR-CORE (which depends on
GR-CONTRACT), but the coupling is named here so the step schedules
correctly. GR-READ is optional, but the 10 MiB round-trip test needs
read-back, so order GR-READ → GR-WRITE if validating it here.

**Risk / surprises.** Unknown-length `AsyncIterator` forces a spool pass
(Graph requires a known total in `Content-Range`); the spool uses system
temp (no `dir=`) — `TMPDIR` redirection is a documentation obligation
(GR-019), tracked in GR-DOCS-E2E. Chunk-alignment (GR-020) is
integration-only — respx accepts any `Content-Range`.

---

## Step 6 — GR-MUTATE: delete, copy, move, monitor poller

**Scope.** Implement delete / move / copy and the backend-local monitor
poller; clear the mutate conformance slices.

**Files touched.** `backend.py` (`delete` GR-041, `delete_folder`
GR-042/043, `copy` GR-025, `move` GR-027, self-op short-circuit GR-044,
cross-drive vacuous GR-056), `monitor.py` (new — poller per ADR-0023 /
GR-026, `parse_graph_monitor_response`). Tests as above.

**Spec IDs covered.** GR-025..GR-027, GR-041..GR-044, GR-046 (mutate
slices), GR-051 (poller-cancel half), GR-056.

**Acceptance criteria.**
- Graph moves off xfail for DELETE / MOVE / COPY conformance slices.
- respx tests cover copy `202`→monitor poll success and failure
  (error.code mapped via the standard table; unknown → `BackendUnavailable`),
  `copy_timeout` expiry → `BackendUnavailable` with monitor URL + poll
  count + `last_status` token, `Retry-After` precedence, transient-5xx-as-
  pending, cancellation propagation, sync move + may-be-async move,
  self-copy/self-move single-GET short-circuit, `delete_folder(recursive=
  False)` non-empty → `DirectoryNotEmpty`.
- Poller `graph.copy.poll_complete` DEBUG marker asserted via `caplog`.
- **`close()` poller-cancel half (GR-051):** `close()` cancels pending
  monitor pollers cooperatively; test asserts cancellation without leak.
  The *upload-session abort* half of GR-051 is owned by GR-WRITE (it needs
  the session driver), so this step does **not** assert it — avoiding a
  hidden dependency on GR-WRITE. The combined fully-assembled `close()`
  (pollers **and** sessions) is verified in GR-DONE.
- **Reality-checked against the live tenant** (GR-FOUNDATION): copy
  `202`→monitor polling runs end-to-end at Stage 3 against a genuine
  monitor URL (GR-026); a representative run is cassetted back.
- `hatch run lint` clean; `filterwarnings = error` clean.

**Dependencies.** GR-CORE.

**Risk / surprises.** `copy_timeout=None` is unbounded-by-design and
unsafe by default (GR-026) — a documentation obligation (GR-DOCS-E2E),
not a code default. End-to-end monitor polling against a real `202` is
integration-only (GR-026).

---

## Step 7 — GR-DOCS-E2E: guides, examples, and e2e wiring

**Scope.** Ship the usage-facing documentation (the provisioning guide
`graph-setup.md` already landed in GR-FOUNDATION) and wire Graph into the
hand-built e2e async streaming chain.

**Files touched.**
- `docs-src/guides/backends/graph.md` (new — usage, config, capability
  notes; must call out `TMPDIR` redirection (GR-019) and the unbounded
  `copy_timeout=None` caveat (GR-026); links across to the Step-1
  `graph-setup.md` for onboarding).
- `docs-src/guides/backends/_nav.yml`, `index.md` (nav entry for the
  usage guide).
- `examples/graph-backend.md` or the module docstring rendered by
  `gen_pages.py`; README backends line + Quick Start snippet (optional).
- `tests/e2e/conftest.py` (Graph credential plumbing reusing the
  GR-FOUNDATION two-layer gate).
- `tests/e2e/test_async_streaming_integrity.py` (conditional Graph hop
  alongside the `if _async_azure_available():` branch; `LAZY_READ`
  chunk-exemption handling if range-fallback fires).

**Spec IDs covered.** Documentation deliverables (RFC § Documentation
deliverables — usage guide / examples); e2e streaming integrity (SHA-256
across hops + lazy-read chunking). No new GR-* behaviour.

**Acceptance criteria.**
- `graph.md` usage guide present, parity-clean against the API
  reference; resolves all on-disk links (AUTHORING Rule 3) and passes the
  docs-framework check. (`graph-setup.md` already shipped + dogfooded in
  GR-FOUNDATION; this step only confirms the cross-link resolves.)
- e2e wiring (named obligation): the Graph hop is gated on the same
  two-layer gate as `graph_live` and **skips cleanly** when creds/Azurite
  are absent; with both present, the integrity and lazy-read-chunking
  assertions cover the Graph hop.
- `FEATURES.md` / README backend lines mention Graph.
- `hatch run lint` clean.

**Dependencies.** GR-READ + GR-WRITE (the streaming behaviour the e2e
chain exercises); GR-CORE (auth/utils for cred plumbing). **GR-MUTATE is
*not* a functional prerequisite** — the streaming-integrity test only
reads and writes across hops, never moves/copies/deletes. The diagram
routes GR-MUTATE in as "all backend ops complete" sequencing, not as an
e2e-test dependency.

**Risk / surprises.** The e2e chain has **no registration seam** — it is
built by hand in the test body, so wiring is non-trivial (cred plumbing
+ conditional hop + `LAZY_READ` exemption), not a plug-in. If Graph's
range-fallback (GR-015) materialises during the run, the lazy-read
chunking assertion (`count > 1`, `max_chunk < file_size`) needs the
documented exemption or it will flap.

---

## Step 8 — GR-DONE: BK-237 DoD umbrella + close-out

**Scope.** Verify every box of the contract-expanding-feature DoD against
the assembled backend, land the Stage-3 authoritative tier, and close
ID-127.

**Files touched.** `tests/backends/fixtures/fixtures.toml` /
`_live_env.py` (confirm the `graph_live` two-layer gate established in
GR-FOUNDATION is complete and exercised across all op steps), any
`@pytest.mark.integration` tests not already landed (GR-007/020/026/
034/054 + 10 MiB round-trip), `CHANGELOG.md`, `sdd/BACKLOG.md` →
`sdd/BACKLOG-DONE.md` (move ID-127 incl. the bundled `ResourceLocked`
sub-task), `sdd/backlogid.json` (`hatch run gen-backlogid`),
`sdd/traces/ID-127-*.yml` (final), **delete this plan file**.

**Spec IDs covered.** Integration-only set (GR-007, GR-020, GR-026,
GR-034, GR-054); GR-051 (combined `close()`); traceability sweep over
every GR-NNN.

**Acceptance criteria (BK-237 contract-expanding-feature DoD — each a
gate).**
- [ ] Spec / RFC up to date; the **conformance + formal** work the
  feature needs was scoped up front (spec 044 / RFC-0010 § Test plan:
  respx unit, Stage-1 replay, Stage-3 live, conformance matrix, Dafny
  oracle), not discovered as follow-ups. **Property-based testing: N/A
  for Graph** — neither spec 044 nor RFC-0010 calls for it; there is no
  value-space invariant beyond what the conformance matrix already
  covers. Recorded here as a deliberate up-front decision, not a
  discovered-late gap (which is exactly what this DoD box guards against).
- [ ] **Combined `close()` (GR-051) verified against a fully-assembled
  backend** — cancels pending monitor pollers (GR-MUTATE half) **and**
  aborts in-flight upload sessions via `DELETE {sessionUrl}` (GR-WRITE
  half), never raising on cleanup. This is the one assertion no single
  op-step owns end-to-end (CORE has the baseline, WRITE the sessions,
  MUTATE the pollers), so GR-DONE pins it.
- [ ] Capability declaration reviewed for **both** over- and
  under-declaration against GR-003.
- [ ] Conformance test + xfail registry landed before the first backend
  impl (GR-CONTRACT) and Graph is fully off the xfail list now.
- [ ] Wrapper forwarding verified — `ProxyStore`, `ext/` wrappers, and
  the sync + oracle adapters all forward the Graph surface
  (`ResourceLocked` propagates through each).
- [ ] Docs ripple swept — every guide, snippet, reference, `FEATURES.md`,
  README the contract appears in.
- [ ] Audit pass run against the unreleased work as a pre-merge gate.
- [ ] Every GR-NNN traceable to ≥1 `@pytest.mark.spec("GR-NNN")` test.
- [ ] `graph_live` Stage-3 fixture skips cleanly without the two-layer
  gate; the four integration-only invariants run there — and, because the
  tenant was live from GR-FOUNDATION, every prior step was already
  reality-checked at Stage 3, not validated for the first time here.
- [ ] `hatch run all` (Stage-1 local gate) clean; strict coverage gate
  is CI-only per CLAUDE.md.
- [ ] ID-127 moved to `BACKLOG-DONE.md` and **this plan file deleted** in
  the same PR.

**Dependencies.** All prior steps.

**Risk / surprises.** The audit pass may surface honest gaps (e.g. an
over-declared capability slice that passes conformance vacuously); per
the audit protocol, report and let the user decide — do not silently
patch. Live-tier validation depends on a real M365 tenant being
available; if not, the integration markers stay skip-clean and the
Stage-3 assertions are deferred to whoever has tenant access (record it).

---

## Alignment notes (read before implementing GR-CONTRACT / GR-CORE)

- **ADR-0024 intention vs. wording (`ResourceLocked` placement).** ADR-0024
  § Bundled implementation says the `ResourceLocked` runtime class + Dafny
  variant "land in the same PR as the Graph sub-package
  (`aio/backends/_graph/`)." This plan lands the bundle one step earlier,
  in **GR-CONTRACT** (step 2). Read **verbatim**, GR-CONTRACT is not the
  sub-package PR; read by **intention**, this is fully aligned, and the
  intention governs. ADR-0024's stated concern is that the Dafny variant
  must not be **orphaned** — "without the runtime class to raise, adding
  the variant alone would create a verified contract for behaviour the
  codebase cannot exhibit" — which is why it "ships together with the
  Graph backend implementation." This plan honours that on every count:
  (1) the bundle stays coupled — class + variant + dispatch ship
  **together** in GR-CONTRACT, never the variant alone; (2) the Graph
  backend that raises it (the only raiser, via GR-CORE's `http.py` 423
  mapper) lands in the immediately following steps of the **same ID-127
  delivery**; (3) the intermediate state is already consistent with the
  repo — ERR-013 exists in spec 005 from RFC acceptance with no raiser, so
  the runtime class joining it before the Graph mapper introduces nothing
  new. The "same PR" phrasing is ADR-0024's wording under a one-PR
  assumption; splitting the bundle across GR-CONTRACT → GR-CORE is the
  same kind of decomposition as splitting the backend itself across
  GR-CORE..GR-MUTATE — neither contradicts the ADR.
- **When this *would* deviate.** The ADR's intention is violated only if
  the Graph backend never lands after GR-CONTRACT — i.e. the bundle is
  shipped and the roadmap then stalls, leaving an orphaned formal contract
  (exactly the standalone-ID-189 scenario ADR-0024 folded away). The
  guardrail for the implementer: **do not merge GR-CONTRACT's
  `ResourceLocked` bundle unless GR-CORE is committed to land in the same
  release cycle.** As long as the backend follows, there is no deviation.
- **Finer decomposition than ADR-0024 contemplated.** ADR-0024 assumed a
  single "Graph backend" PR; this plan splits it (GR-CORE..GR-MUTATE).
  That is a decomposition choice, not a contradiction of any ADR. A
  reviewer who prefers a single Graph PR can collapse
  GR-CONTRACT..GR-MUTATE with no change to *what* lands.

## Spec follow-ups

None. Spec 044, RFC-0010, and ADRs 0021..0024 are internally consistent
and sufficient to implement against, and the plan does not deviate from
any of them. The `ResourceLocked`-in-GR-CONTRACT placement honours
ADR-0024's intention (no orphaned formal contract; the backend lands in
the same delivery) — it reads the ADR by intention rather than verbatim,
which the *Alignment notes* explain in full; it is a decomposition choice,
not a deviation, and edits no spec/ADR file. If implementation surfaces a
genuine spec-content drift, record it here and stop (do not silently amend
the baseline).

## Non-goals for this roadmap

- No item-id addressing (GR-011 deferred), no native-async observe/otel,
  no `ext.integrity` Graph fast-path (GR-049), no cross-drive ops
  (GR-056), no `open_atomic` on the session (GR-040 follow-up). All are
  out of scope per RFC-0010 § Non-goals / Open Questions.
