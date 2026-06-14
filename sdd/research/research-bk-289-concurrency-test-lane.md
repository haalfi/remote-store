# Research: Cross-Backend Concurrency Test Lane (BK-289)

**Date:** 2026-06-14
**Context:** BK-289 was filed as a *Graph-only* concurrency test lane out of the
expectation-driven Graph review (see
[research-expectation-driven-review.md](research-expectation-driven-review.md)).
The premise of this document is broader: thread-safety and concurrency are
asserted about `Store`, `AsyncStore`, and several backends across `src/` and
`docs/`, yet **no test exercises concurrent operations on a single instance for
any backend except in-process Memory**. The audit-001 finding **M-14** ("zero
concurrency tests despite thread-safety spec claims") is still *Open* in
[research-testing-best-practices.md](research-testing-best-practices.md). This
document analyses the claim surface, rejects the naive "every backend must pass a
concurrency test" framing, and designs a **posture-gated concurrency conformance
lane** that fits the existing capability/registry machinery.

---

## 1. The claim surface

Thread-safety / concurrency is asserted in specs and docs, but it is **not a
single uniform property**. It splits across two layers (Store vs. Backend) and
two axes (sync threads vs. async coroutines).

| Layer / backend | Declared posture | Source | Tested today? |
|---|---|---|---|
| `Store` | Immutable, safe to share across threads | STORE-007 (spec 001), ADR-0001 | Memory only — `test_store.py::TestStoreThreadSafety` |
| `Store.child` | Inherits STORE-007 | CHILD-010 (spec 015) | Memory only — `test_store_child.py::TestChildThreadSafety` |
| `AsyncStore` | Safe for concurrent coroutines on **one** loop; never across loops | ASYNC-055 (spec 029) | Memory + sync-adapter bridge only |
| Memory | Fully thread-safe (single coarse lock) | MEM-025 (spec 013) | Yes |
| Local | Effectively thread-safe (stateless; delegates to `os`/`shutil`) | — (undocumented) | — |
| S3 / S3-PyArrow | Safe via thread-safe `boto3`/`s3fs` connection pools | custom-backend-guide | — |
| Azure | Safe via thread-safe SDK HTTP client | — | — |
| Graph | Safe for concurrent coroutines on one loop; `overwrite=False` is a **server-side atomic create-if-absent** | live-confirmed (review); spec gap — proposed GR-059 | **none** |
| SQLBlob | Thread-safe (SQL transaction) | concurrency.md | — |
| **SFTP** | **NOT thread-safe** — single paramiko socket; one instance per thread | SFTP-guide, `_sftp.py` docstring, async.md | Carve-out asserted in `test_sync_adapter_conformance.py` |
| **HTTP** | **NOT thread-safe** — shared redirect-counter on the opener | `_http.py` docstring | — |

Two facts dominate the design:

1. **The posture is per-backend and non-uniform.** Memory/Local/cloud/SQLBlob are
   thread-safe; SFTP and HTTP are explicitly *not*.
2. **Most claims are untested.** Everything green above is Memory or the bridge;
   every cloud and filesystem backend is unverified for concurrent single-instance
   use.

---

## 2. Why "every backend must pass a concurrency test" is the wrong frame

The reframing that triggered this work — *"any store backend must be tested for
concurrency"* — is right in spirit but wrong if read as *"every backend must pass
the same concurrent-stress assertion."* A blanket thread-stress over
`fixture_params()` would assert a property that **SFTP and HTTP deliberately do
not have**, and would either fail (correctly, but uselessly) or hang (paramiko
races on its shared socket — already observed; see
`live_adapted_backend_concurrent` excluding SFTP for exactly this reason).

The correct model is the one the codebase already uses everywhere else:
**declare a posture, then test each backend against its own declared posture.**
This is structurally identical to the `Capability` system —
`fixture_params(Capability.X)` runs a test only on backends that declare `X`, and
negative-direction guards assert the *carve-out* on backends that don't (e.g.
`test_file_info_metadata_none_when_capability_absent`). Concurrency is just
another such gated property.

---

## 3. Existing coverage and the gap

**What exists:**

- `test_store.py::TestStoreThreadSafety` (STORE-007) — concurrent reads on a
  shared Store, **Memory only**.
- `test_store_child.py::TestChildThreadSafety` (CHILD-010) — concurrent
  `child()`, **Memory only**.
- `tests/backends/memory/aio/test_basics.py::TestAsyncMemoryConcurrency`
  (ASYNC-055) — `asyncio.gather` writes/reads, **Memory only**.
- `test_sync_adapter_conformance.py` (ASYNC-031/055) — bridge concurrency with an
  explicit **SFTP-not-thread-safe carve-out** (`live_adapted_backend_concurrent`
  excludes SFTP). This is the one place a posture carve-out is already encoded —
  and the precedent this design generalises.

**The gap (per backend, single instance):**

- No concurrent-read / concurrent-distinct-key-write / read-after-write stress on
  Local, S3, Azure, SQLBlob, or Graph.
- No create-once-race contract test (does concurrent `overwrite=False` produce
  exactly one winner where the backend claims server-side atomicity, e.g. Graph?).
- No stream-vs-mutate, N-parallel-large-upload, or token-call-count probes
  (Graph-specific, from the review).
- No black-box `Store`-surface DX validation in the downstream expectations repo.

---

## 4. Design: posture-gated concurrency conformance lane

### 4.1 Posture as registry data

Add a concurrency posture to the fixture registry exactly as `transport`,
`flat_namespace`, and `large_write_distinct` are carried today — sourced
per-family from `backends.toml`, surfaced on `BackendFixture`:

```python
# BackendFixture, sourced from [backend.<x>] in backends.toml
concurrency: Literal["thread_safe", "single_connection"] = "thread_safe"
```

- `thread_safe` — concurrent threads on one instance are safe (Memory, Local,
  S3, S3-PyArrow, Azure, SQLBlob).
- `single_connection` — one instance per thread; concurrent ops on one instance
  race (SFTP, HTTP).

The **async axis** is universal: every `AsyncBackend` is `coroutine_safe` on a
single loop and unsafe across loops (ASYNC-055), so it needs no per-fixture flag —
it is asserted uniformly over the async fixture set, with the single
"never across loops" negative guard.

Add a selector mirroring `fixture_params`:
`fixture_params_concurrent()` returns only `thread_safe` fixtures for the positive
thread-stress; the `single_connection` set is enumerated separately for the
carve-out guards.

**Dependency:** the posture must be *declared in a spec* before it can be
conformance-tested. That declaration is precisely **BK-287**'s
"cross-backend concurrent-use-posture clause to specs 003/029." See §5.

### 4.2 Lane structure

New files: `tests/backends/conformance/test_concurrency.py` (sync) and an
`aio/` async sibling, organised in three tiers. **Every assertion is an
invariant** — no error, correct final state, no lost writes on distinct keys,
create-once → exactly one winner — *never* a timing or interleaving assertion.

**Tier 1 — deterministic contract guards (Stage 1, CI):**
- In-process substrates (Memory, Local tmpdir) over the `thread_safe` set:
  concurrent reads return consistent content; N concurrent writes to *distinct*
  keys all land; read-after-write is consistent under a `ThreadPoolExecutor`.
- Mock-level create-once-race over respx (Graph) / moto (S3): concurrent
  `overwrite=False` on one key yields **exactly one** success and the rest
  `AlreadyExists`, where the backend declares server-side atomicity. Cassette
  replay is **not** concurrency-safe (vcrpy matches sequentially), so these guards
  use respx/moto, **not** cassettes — as BK-289 already specifies for Graph.
- Bridge deadlock-freedom and the BUG-219 `aclose` no-raise/no-warning property
  (Graph), folded in from the review.

**Tier 2 — carve-out guards (Stage 1, CI):**
- Over the `single_connection` set (SFTP, HTTP): assert the documented posture —
  the *one-instance-per-thread* pattern works concurrently, and the lane does
  **not** subject a shared single instance to the thread-stress. This is the
  negative-direction guard that keeps the posture honest (a backend that silently
  became thread-safe, or unsafe, would diverge from its declaration).

**Tier 3 — live race probes (Stage 3, gated):**
- Behind `RS_TEST_LIVE_*` (e.g. `RS_TEST_LIVE_GRAPH`): real concurrent
  create / overwrite / move / copy, N-parallel large uploads, and Graph
  token-call counting. The review already built a re-runnable harness for these.

### 4.3 Determinism and flakiness guardrails

Concurrency tests are the historical #1 source of flaky CI, and this repo has
already paid for that lesson (CLAUDE.md *Parallel tests*: the team rejected
`--dist loadgroup`, MaxStartups tuning, and banner retries for the *simplest*
xdist carve-out). The lane must be deterministic **by construction**:

- Assert invariants only; never assert a particular interleaving, ordering, or
  timing. No `sleep`-based synchronisation.
- Fixed, modest thread/coroutine count (8–16) so that under `pytest -n auto`,
  `workers × threads` does not saturate the host. (`scripts/run_tests.py` already
  caps xdist workers.)
- A dedicated marker (e.g. `@pytest.mark.concurrency`) so the lane is selectable
  and excludable in isolation.
- SFTP probes stay in the existing **serial** lane — `sftp_docker` is already
  dropped from parametrize under xdist, and SFTP is `single_connection` anyway,
  so its only probe is the one-instance-per-thread carve-out.
- Live probes are Stage-3 / `RS_TEST_LIVE_*`-gated — real money, real creds,
  inherently slower — never in the default CI lane.

### 4.4 Consolidation map (reuse, don't duplicate)

The lane is the new single home for concurrency conformance; the scattered tests
are folded in or cross-referenced, not duplicated:

| Existing test | Disposition |
|---|---|
| `test_store.py::TestStoreThreadSafety` (STORE-007) | Generalise share-across-threads over the `thread_safe` fixture set; keep Store-layer immutability note |
| `test_store_child.py::TestChildThreadSafety` (CHILD-010) | Cross-reference; CHILD-010 inherits STORE-007 |
| `memory/aio/.../TestAsyncMemoryConcurrency` (ASYNC-055) | Generalise into the async lane over the async fixture set |
| `test_sync_adapter_conformance.py` SFTP carve-out | The precedent; its `single_connection` exclusion becomes registry-driven |

### 4.5 Expectations mirror (separate repo)

The public-`Store`-surface subset (create-once race, read-after-write,
`ThreadPoolExecutor` + `ext.batch`) is mirrored into
`../remote-store-expectations` as black-box DX validation. **Note:** that repo is
*not* present in this container — it is a separate-repo follow-up, tracked as a
sub-task of BK-289, not part of the in-repo lane.

---

## 5. Dependencies and sequencing

```text
BK-287 (declare posture in specs 003/029 + GR-059)  --->  BK-289 (test the posture)
```

- **BK-287 must precede or co-ship with BK-289.** You cannot conformance-test a
  posture that no spec declares; the registry `concurrency` field is the
  machine-readable shadow of BK-287's prose clause, and the carve-out guards
  assert *that* declaration. If BK-287 slips, BK-289's Tier 2/Tier 1 atomicity
  guards have nothing authoritative to bind to.
- **BK-288** (concurrency docs) is independent but naturally co-reviewed — the
  `concurrency.md` table gains a Graph row and a posture column the lane mirrors.
- **BUG-219** (Graph `aclose`) and **BK-290/292** (I/O robustness, token
  single-flight) are *exercised* by Tier 3 live probes but fixed elsewhere.

---

## 6. Risks and open questions

1. **Posture spec ownership.** The `thread_safe` vs `single_connection` taxonomy
   is proposed here; BK-287 owns the authoritative wording. If BK-287 lands a
   finer taxonomy (e.g. distinguishing "process-safe" cloud backends from
   "in-process-lock" Memory), the registry enum must follow. Recommend the
   two-value enum unless BK-287 finds a third posture that an actual backend
   exhibits.
2. **Local backend posture is undocumented.** The table marks Local
   `thread_safe` by inference (stateless, OS-level). BK-287 should state it
   explicitly, or the carve-out guard should treat "undeclared" as a failure.
3. **moto/respx fidelity for the create-once race.** In-process mocks may not
   reproduce true server-side atomic create semantics; the *authoritative*
   create-once-race evidence is the Tier-3 live probe. Tier-1 mock guards protect
   the **mapping** (409 → `AlreadyExists`), not the server's atomicity — keep that
   distinction explicit in the test docstrings (cf. the "exercised, not
   mechanism-asserted" discipline in `test_atomic.py`).
4. **Cross-loop async negative guard.** ASYNC-055's "never across loops" clause
   needs a deliberate negative test (one `AsyncBackend` driven from two loops must
   be a documented misuse, not silent corruption). This is the async analogue of
   the `single_connection` carve-out.

---

## 7. Recommendation

1. **Broaden BK-289 in place** from "Graph concurrency test lane" to a
   cross-backend, **posture-gated** concurrency conformance lane, with Graph as
   the Tier-3 live exemplar. (Done in this PR — see `sdd/BACKLOG.md`.)
2. **Co-sequence with BK-287**: land the spec posture clause + the registry
   `concurrency` field first (small), then the conformance lane (the bulk).
3. **Build Tier 1 + Tier 2 for CI first** (deterministic, Stage-1, in-process +
   respx/moto), wire Tier 3 live probes behind `RS_TEST_LIVE_*` second, and file
   the expectations-repo mirror as a separate-repo sub-task.
4. **Close M-14** (audit-001) when Tier 1 lands — it is the long-open
   "zero concurrency tests" finding this lane finally discharges.
