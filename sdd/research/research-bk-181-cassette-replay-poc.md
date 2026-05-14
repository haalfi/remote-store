# Research: HTTP cassette/replay layer — mechanism PoC (BK-181)

**Date:** 2026-05-14
**Status:** PoC complete. Verdict: **GO with `pytest-recording`** plus an
async transport shim. Feeds the BK-181 implementation.
**Scope:** A deliberately minimal spike answering the one open question in
[BK-181](../BACKLOG.md): can `pytest-recording`/vcrpy record the real Azure
SDK HTTP traffic and replay it at zero cost — sync *and* async — with
credentials scrubbed? The alternative the backlog names is a custom
`azure.core` transport adapter.
**Related:** [BK-181](../BACKLOG.md), [spec 048](../specs/048-testing-architecture.md)
(TEST-007/008/009), [ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md),
[BUG-197](../BACKLOG.md), the spike folder [`bk-181-poc/`](bk-181-poc/).

**Context.** BK-181 demotes live-only Azure HNS contracts to a zero-cost
Stage 1 `<backend>_replay` fixture: Stage 3 records a cassette, every
default CI run replays it. It is the foundation for turning the open HNS
defects (the BUG-195..203 family, each "surfaced only by the Stage 3
`azure_live` run") into always-on regression guards. The backlog left the
recording mechanism unchosen and flagged async-pipeline coverage and
scrubbing complexity as the axes to benchmark. This PoC settles it before
the L-effort build starts. Per the repo's PoC convention the spike folder
freezes once this doc lands; BK-181 reimplements at the real tree paths.

---

## Verdict

**Use `pytest-recording` (vcrpy).** It works for sync and async Azure,
needs **zero production-code change**, and reuses a maintained library for
`--record-mode`, cassette management, and network blocking. The custom
`azure.core` transport adapter — the "build" alternative — is not needed.

One real wrinkle, fully worked around in the PoC: **vcrpy 8.1.1's aiohttp
stub cannot stream a response body.** The fix is a one-line shim — inject
`AsyncioRequestsTransport` into the async backend via the existing
`client_options` kwarg — so async traffic rides vcrpy's proven
requests/urllib3 stub instead. Details below.

All six PoC success criteria pass. The spike has 4 tests (sync + async ×
happy-path + the BUG-197 unhappy case); all 4 record against a real ADLS
Gen2 account and replay green from committed, scrubbed cassettes with
`--block-network` in 0.6 s.

---

## Build vs reuse

**Reuse wins decisively.** `pytest-recording` + `vcrpy` installed clean
(2 packages, no dependency conflicts with the existing dev set) and
deliver, off the shelf:

- the `--record-mode` CLI surface (`once`/`rewrite`/`none`/...),
- per-test cassette files with a stable path convention,
- `--block-network` enforcement (the zero-network proof),
- the YAML cassette format with request/response filtering hooks.

The only "build" is ~150 lines of conftest glue — scrubbing, the
fixed-name trick, the missing-cassette skip hook. A custom transport
adapter would need *all of that anyway*, **plus** the adapter itself, in
sync and async variants, **plus** a second mechanism for S3 (which has no
`azure.core` pipeline). Reuse is less code and less surface to maintain.

---

## What was tested

Spike folder: [`sdd/research/bk-181-poc/`](bk-181-poc/) — outside
`testpaths`, run by pointing pytest at it explicitly.

| File | Role |
|---|---|
| `conftest.py` | vcrpy wiring: scrubbing, record/replay connection-string switch, backend fixtures, missing-cassette → skip |
| `test_replay_sync.py` | `AzureBackend`: happy-path round-trip + BUG-197 unhappy case |
| `test_replay_async.py` | `AsyncAzureBackend`: same two cases |
| `cassettes/` | 4 recorded, scrubbed cassettes (committed) |

Each test runs the *real* Azure SDK code path. The only thing that
changes between record and replay is the transport: recording hits a real
ADLS Gen2 account (`<real-account>`), replay serves the committed cassette
from a fake connection string with no network.

---

## Success criteria — results

### 1. Interception — partial for async, fully solved

| Path | SDK transport | vcrpy stub | Result |
|---|---|---|---|
| Sync | `RequestsTransport` (urllib3) | requests/urllib3 | **Works flawlessly** — record and replay |
| Async | `AioHttpTransport` (aiohttp) | aiohttp | **Broken** — see below |

vcrpy 8.1.1's aiohttp stub cannot carry a streamed response body:

- **On record**, the cassette captures the body correctly, but the live
  caller receives `b""` — the body never reaches the SDK. The async
  download path (`azure.core...._aiohttp.py` async-iterating the response
  content) is left empty.
- **On replay**, the same path **deadlocks**. Faulthandler caught it
  blocked in `AioHttpTransport.__anext__` → `asyncio.streams.read`,
  awaiting a stream vcrpy's mock response never feeds and never closes.
  Responses *without* a body (the BUG-197 directory read, error
  responses) replay fine — the deadlock is body-stream-specific.

**Workaround (applied in the PoC):** inject `AsyncioRequestsTransport` —
an `azure.core` async transport that rides `requests` in a thread pool —
into the async backend via `client_options={"transport": ...}`. Async
traffic then flows through vcrpy's working urllib3 stub. The backend's own
async code path (`aio/backends/_azure.py`) is unchanged; only the leaf
transport differs, and injection uses an existing public kwarg, so
production code is untouched.

*Fidelity caveat:* the async replay fixture exercises every async backend
code path and every `azure.core` pipeline policy, but its leaf transport
is `AsyncioRequestsTransport`, not the production-default
`AioHttpTransport`. A defect living *purely* in aiohttp-transport
behaviour would not be caught by replay. This is acceptable: the live
Stage 3 `azure_live_async` fixture keeps the real `AioHttpTransport` and
remains the source of truth (the spec's design intent), and conformance
exercises the backend, not the transport leaf. If transport-layer
fidelity ever matters, the options are an upstream vcrpy aiohttp fix or a
custom `AsyncHttpTransport` adapter — neither blocks BK-181.

### 2. Zero-credential replay — pass

Replay builds the backend from a fixed fake connection string
(`AccountName=bk181poc`, Azurite's public well-known key — valid base64,
not a secret). `hatch run pytest sdd/research/bk-181-poc/ --block-network
--allowed-hosts=127.0.0.1,::1,localhost` passes all 4 tests in 0.63 s with
no network. (The loopback allowance is required only for the Windows
`ProactorEventLoop` self-pipe — see Other findings.)

### 3. HNS-specific behaviour captured — pass

Both BUG-197 cases (sync and async) replay green, asserting the current
buggy `read_bytes(hns_dir) == b""`. The cassettes carry the
`x-ms-is-hns-enabled: 'true'` account probe and the real HNS
directory-marker traffic — exactly the behaviour Azurite cannot emulate
and the whole BUG-195..203 family depends on. Recording this *confirmed
BUG-197 reproduces on the async backend too*, against the real account.

### 4. Scrubbing — works at header level; one body-level gap

Verified: grepping all 4 committed cassettes for the real account name,
`authorization`, `x-ms-date`, `x-ms-client-request-id`,
`x-ms-request-id`, `AccountKey`, `sig=` returns **nothing**. The
`before_record_request` host rewrite turns `<real-account>` into
`bk181poc` everywhere — URLs, headers, and response bodies.

**Gap for BK-181 proper:** per-run identifiers embedded in *error-response
XML bodies* survive — e.g. `<Message>...RequestId:8fa924c6-...
Time:2026-05-14T...` in a `ContainerAlreadyExists` body. Header scrubbing
does not reach them. BK-181 needs a body-level regex scrub for
`RequestId:` / `Time:` fragments. Cosmetic, not a credential leak, but it
makes cassette diffs noisy. (Also cosmetic: `User-Agent` records the
recording machine's OS/Python version — worth normalising.)

### 5. Per-run identifier problem — solved

The live registry fixtures mint a per-call `conformance-<uuid>`
filesystem (`azure_live.py:77`); that uuid would land in every request
URL and break cassette matching. The PoC uses a **fixed** container name
(`bk181poc`) plus the `before_record_request` host rewrite. vcrpy's
default `match_on` (method/scheme/host/port/path/query) then matches
cleanly: SharedKey auth keeps its signature in the `Authorization` header
(scrubbed, unmatched), not the query, and `x-ms-client-request-id` is a
header too. No custom matcher was needed.

### 6. Missing cassette → skip — solved

vcrpy's native behaviour on a missing cassette in `record_mode=none` is to
*raise*. TEST-007 wants a *skip*. A `pytest_collection_modifyitems` hook
in the conftest checks each `vcr`-marked test's cassette path at
collection time and adds `pytest.mark.skip` when it is absent. Verified:
with one cassette removed, that test skips with a clear reason and the
other three pass.

---

## Other findings

- **Install is clean.** `uv pip install pytest-recording` pulled
  `pytest-recording==0.13.4` + `vcrpy==8.1.1`, no conflicts.
- **`--block-network` vs Windows asyncio.** pytest-recording's network
  guard blocks `socket.socketpair()`, which the Windows `ProactorEventLoop`
  needs for its self-pipe — async tests error at loop creation. Fix:
  `--allowed-hosts=127.0.0.1,::1,localhost`. Real Azure hosts stay
  blocked. BK-181's `--stage` runner should bake this allowance in.
- **`filterwarnings = error` is unforgiving here.** A half-created event
  loop (from the `--block-network` issue above) leaks a `ResourceWarning`
  that the global `error` filter escalates and that then poisons
  *subsequent* tests via `PytestUnraisableExceptionWarning`. BK-181 must
  keep async fixture teardown airtight.
- **Idempotent setup records cleanly.** Filesystem- and directory-create
  calls are wrapped in `except ResourceExistsError: pass`; the request is
  identical whether the resource pre-exists (`409`) or not (`201`), so
  re-records work against a dirty or clean account alike.
- **Speed.** Full 4-test replay: ~0.6 s. Recording: ~4.5 s (real account).

---

## Recommendations for BK-181 proper

1. **Mechanism:** `pytest-recording` + `vcrpy`. Add both to the `dev`
   extra in `pyproject.toml`.
2. **Async:** inject `AsyncioRequestsTransport` in the `azure_replay_async`
   fixture's factory via `client_options`. Document the fidelity caveat
   next to it. Do **not** wait on an upstream vcrpy aiohttp fix.
3. **Real-tree wiring:** `tests/backends/fixtures/azure_replay.py` +
   `azure_replay_async.py`; `[fixture.azure_replay]` /
   `[fixture.azure_replay_async]` in `fixtures.toml` with
   `kind = "replay"`, `stage = 1`, `container = "none"`; register via
   `registry.register`. Cassettes at the spec location
   `tests/backends/cassettes/azure/`. Model the recording-side factory on
   `azure_live.py`, but with a **deterministic** filesystem name.
4. **`--record` wiring:** map the spec's `pytest --stage=3 --record` onto
   vcrpy's `--record-mode=rewrite` in `tests/conftest.py::pytest_addoption`,
   and fold the `--allowed-hosts` loopback allowance into the runner.
5. **Scrubbing:** port the PoC's `vcr_config` and *add* a body-level regex
   scrub for `RequestId:` / `Time:` fragments and `User-Agent`
   normalisation.
6. **Missing-cassette skip + plugin guard:** port the
   `pytest_collection_modifyitems` hook (the cassette-path logic mirrors
   `pytest_recording.plugin`) and the `pytest_configure` plugin-availability
   guard — the registry fixtures depend on `pytest-recording`'s
   `record_mode` fixture, so a missing plugin should fail fast with a clear
   message, not an opaque `fixture not found`.
7. **S3 ("follows"):** a separate validation — `s3fs` rides
   `aiobotocore`/`botocore`, not `azure.core`. vcrpy supports botocore,
   but the streaming-body behaviour must be re-checked the same way this
   PoC checked aiohttp. Do not assume the Azure result transfers.
8. **Ship the trace** (`sdd/traces/bk-181-*.yml`) and the
   `TESTING.md` / spec-048 migration-note updates with the work.

**Effort:** stays **L**. The PoC removes the mechanism risk, but the
real-tree fixture wiring, the `--stage`/`--record` plumbing, scrubbing
completeness, the S3 second mechanism, and the docs/trace ripple are still
the bulk of the work.

---

## Reproduce

See [`bk-181-poc/README.md`](bk-181-poc/README.md). In short:

```
uv pip install --python .venv pytest-recording          # one-time
hatch run pytest sdd/research/bk-181-poc/ --block-network --allowed-hosts=127.0.0.1,::1,localhost
```

The second command replays the committed cassettes with no network and no
credentials. Recording (needs a real ADLS Gen2 account in `.env` plus
`RS_TEST_LIVE_HNS=1`) is `--record-mode=rewrite`.
