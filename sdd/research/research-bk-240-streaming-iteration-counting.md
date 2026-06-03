# Research: BK-240 — Streaming-iteration counting wrapper for write paths

**Item ID:** BK-240
**Date:** 2026-06-03
**Spec:** SIO-003 (Writable Content), ASYNC-021 (Async Writable Content)
**Audience:** infra.test
**Effort:** S
**Status:** Plan — not yet implemented.

---

## 1. Problem

Three closed bugs are the same defect wearing different hats:

- **BUG-165** — `AsyncAzureBackend.write` (non-HNS) collected an
  `AsyncIterator[bytes]` into a single `bytes` before `upload_blob`, defeating
  the bounded-memory streaming promise.
- **BUG-181** — HNS size counting on the same async write path.
- **BUG-194 / gotcha `async_materialize_antipattern`** — the *initial* HNS fix
  buffered the `AsyncIterator` to `bytes` so `upload_data` got a known length;
  reverted in review as a re-introduction of the same anti-pattern.

The common shape: an `AsyncIterator[bytes]` (async, ASYNC-021) or `BinaryIO`
(sync, SIO-003) is materialized into one `bytes` before the SDK call. **The
type signature tolerates it** — `bc.upload_blob(b"".join([c async for c in
src]))` type-checks exactly like `bc.upload_blob(src)`. So the bug recurs, and
each recurrence is caught only by a *backend-specific* assertion:

- `tests/backends/azure/aio/test_config.py:479` —
  `forwarded = bc.upload_blob.await_args.args[0]; assert hasattr(forwarded, "__aiter__")`.
- `tests/backends/azure/aio/test_config.py:1512` — HNS: `upload_data` must NOT
  be called for `AsyncIterator` input (drives `append_data` per chunk instead).

These guards mock the Azure SDK and inspect the forwarded argument. They do not
generalize: the next streaming backend (S3 multipart, a future Graph backend)
inherits no protection. BK-240 asks for a **conformance-level** guard that
travels with the contract, not the backend.

## 2. The core design problem: what is observable?

The backlog phrases the test as "wrap the iterable in a counting iterator and
assert the SDK call observes >1 chunk." Taken literally, a pure pull-counting
wrapper **cannot** detect materialization, and this is the crux of the item:

> In the anti-pattern, the backend still iterates the input chunk-by-chunk —
> `b"".join([c async for c in src])` pulls every chunk via `__anext__`. A
> stream-through backend that forwards the same iterator to the SDK *also*
> pulls every chunk. **Both paths exhaust the wrapper in N pulls.** Counting
> input pulls gives the same number either way.

The distinguishing signal is *not how many chunks are pulled* but *whether the
consumer holds them all at once*. Two observation strategies exist:

| Strategy | Observes | Generic? | Robustness |
|----------|----------|----------|------------|
| **(A) SDK-argument spy** | the object handed to the SDK is an iterator, not `bytes` | No — needs a mock SDK per backend | High, but is just the existing per-backend guard generalized into a helper |
| **(B) Peak-memory bound** | total Python allocation during the write stays well under the payload size | Yes — black-box, runs against the real backend | High with a generous margin; the join buffer is a pure-Python `bytes`, always visible to `tracemalloc` |
| **(C) Chunk-liveness weakrefs** | earlier chunks are GC'd before later ones are pulled | Yes | Brittle — SDK `max_concurrency` legitimately holds several chunks live; GC timing dependent |

**Recommendation: (B), with a pull-counting wrapper as a complementary sanity
assertion.** (A) is the right per-backend regression guard and already exists;
promoting it to a shared helper is cheap and worth doing, but it is not the
generic conformance test the item is asking for. (C) is too brittle to ship.
(B) is the only strategy that is both generic *and* runs against the production
write path without mocking — exactly what "conformance test" means here.

### Why (B) is robust, not flaky

- Materialization allocates the full payload as one pure-Python `bytes`
  (the `b"".join(...)` buffer). With a payload of 8 MiB delivered in 64 KiB
  chunks and a peak-allocation threshold of ~1 MiB, the materialize case
  (~8 MiB) and the stream case (~`chunk_size × max_concurrency`, well under
  1 MiB) are separated by ~8×. No knife-edge.
- `tracemalloc` is per-process; `pytest -n auto` (xdist) runs workers in
  separate processes, so peak measurement is not cross-contaminated.
- The SDK's own C-level/socket buffers are invisible to `tracemalloc`, which is
  *good*: we only want to catch the backend-level Python materialization, which
  is exactly what shows up.

## 3. Gating: which backends are in scope?

Materializing is **correct** for in-memory, local, and SQL-blob backends —
there is no remote stream to feed, so holding the payload is the natural
implementation and SIO-003 does not forbid it. The guard must apply only to
backends whose contract is bounded-memory streaming to a remote SDK.

There is **no capability** for "streaming write" today (`_capabilities.py` has
`WRITE`, `ATOMIC_WRITE`, `LAZY_READ`, `WRITE_RESULT_NATIVE`, `SEEKABLE_READ` —
the write-side counterpart of `LAZY_READ` does not exist).

| Gating option | Ripple | Verdict |
|---------------|--------|---------|
| **New fixture-record flag** `streaming_write: bool = False` on `BackendFixture`, sourced from `fixtures.toml`/`backends.toml` like `flat_namespace` | tests-only: `registry.py`, the toml loader, the two new test classes, the fixtures that opt in | **Recommended.** Keeps BK-240 at effort S and `infra.test` scope. Mirrors the established `flat_namespace` / `rejects_write_under_file_ancestor` pattern. |
| **New capability** `STREAMING_WRITE` (symmetric with `LAZY_READ`) | spec clause (new SIO-0xx), `_capabilities.py`, every backend's declared set, Dafny `Capability` parity (triggers BK-245), `FEATURES.md`, full ripple-check | Heavier; promotes S→M and pulls in spec + formal work. Defer unless a *runtime* caller needs to branch on the promise. |

Recommend the **fixture flag**. It is a test-infrastructure fact ("this fixture
is expected to stream"), not a public API promise, so it belongs in the fixture
registry, not the capability enum. If a real caller ever needs to query the
promise at runtime, promote to a capability then (and that is its own item).

**In-scope fixtures (set `streaming_write=True`):** the Azure async fixtures
(non-HNS `upload_blob` and HNS `append_data` paths — the actual bug sites).
S3 is a candidate *only if* its write path forwards a stream to the SDK rather
than buffering; verify before flagging (see §6, open question). Everything else
stays `False` and is simply absent from the parametrization.

## 4. Sync vs async

SIO-003 sync input is `BinaryIO` (not `Iterable[bytes]`); ASYNC-021 async input
is `bytes | AsyncIterator[bytes]`. The two paths need different wrappers:

- **Async** — wrap an `AsyncIterator[bytes]` producer that yields K chunks of
  `chunk_size`. Pass it to `async_backend.write(path, wrapper)`. Assert (B)
  peak allocation bound, plus (sanity) the wrapper was pulled `>1` time.
- **Sync** — wrap a `BinaryIO` whose `read(size)` calls are counted and whose
  largest single requested size is recorded. A streaming backend issues bounded
  `read(chunk_size)` calls; a materializing one issues a single unbounded
  `read()` (returns the whole file). Assert (B) peak bound, plus (sanity) the
  reader was driven in bounded chunks (`>1` sized read, no single unbounded
  slurp). Note: the sync streaming set may be small or empty today — that is
  fine; the test still encodes the contract and activates when a streaming sync
  backend lands.

## 5. Where the code lands

- **Test infra** — a shared wrapper module, e.g.
  `tests/backends/conformance/_streaming_probe.py`:
  - `CountingAsyncChunks(chunk_size, n_chunks)` — async generator + pull counter.
  - `CountingBinaryIO(payload, chunk_size)` — `BinaryIO` recording read calls and
    max requested size.
  - `assert_bounded_write(...)` — `tracemalloc`-based peak-allocation assertion
    helper shared by both.
- **Async conformance** — new class in
  `tests/backends/conformance/test_async_extended.py`, parametrized via
  `fixture_params(Capability.WRITE, is_async=True)` and gated on the new
  `streaming_write` fixture flag (skip via a `_require`-style helper reading
  `_fixture_record(backend).streaming_write`). `@pytest.mark.spec("ASYNC-021", "SIO-003")`.
- **Sync conformance** — new test(s) in
  `tests/backends/conformance/test_streaming.py` alongside the existing
  SIO-003 `test_write_from_binaryio_streams_content` (lines 120-133), gated the
  same way. `@pytest.mark.spec("SIO-003")`.
- **Fixture flag** — add `streaming_write: bool = False` to `BackendFixture`
  (`tests/backends/fixtures/registry.py`), wire it through the toml loader, and
  set it on the Azure async fixtures in `fixtures.toml`.

## 6. Open questions for the implementer

1. **Does the S3 sync/async write path stream or buffer?** If it forwards a
   stream to boto3/s3fs it should be flagged `streaming_write=True` and gains
   coverage; if it buffers (legitimately, for single-PUT sizing) it stays
   `False`. Verify against `_s3.py` / `aio/backends/_s3.py` before flagging —
   do not assume.
2. **Payload/chunk/threshold constants.** Propose 8 MiB payload, 64 KiB chunks
   (matches ASYNC-020's documented default), ~1 MiB peak-allocation threshold.
   Confirm 8 MiB does not slow the Azurite/S3-moto conformance pass
   unacceptably under `-n auto`; shrink to 4 MiB / 0.5 MiB if needed (margin
   stays ≥8×).
3. **Azure HNS path.** The HNS branch uses `append_data` per chunk, not
   `upload_blob`. The peak-memory probe covers it the same way (a materializing
   HNS fix would still allocate the join buffer), so one async test class can
   cover both Azure shapes via the two Azure async fixtures — confirm both
   fixtures carry `streaming_write=True`.

## 7. Ship-complete checklist (per CLAUDE.md principle 1)

Implementation must land, in one PR:

- [ ] `_streaming_probe.py` helper + async test class + sync test(s).
- [ ] `streaming_write` flag on `BackendFixture` + toml wiring + Azure async
      fixtures opted in.
- [ ] `@pytest.mark.spec` tags so `check_formal_trace.py` / spec-trace tooling
      sees the new SIO-003 / ASYNC-021 coverage.
- [ ] Trace `sdd/traces/bk-240-streaming-iteration-counting.yml` authored
      *as implementation begins* (mandatory once work starts, not after).
- [ ] `CHANGELOG.md` entry (audience `infra.test`).
- [ ] `sdd/BACKLOG.md`: move BK-240 to `BACKLOG-DONE.md` with the PR link.
- [ ] Ripple-check: this plan deliberately avoids the capability/spec/Dafny
      ripple by gating via a fixture flag. If the implementer chooses the
      capability route instead (§3), the full ripple-check
      (`sdd/CLAUDE-REFERENCE.md`) for a capability change applies, and BK-245
      (Python↔Dafny capability parity) becomes a co-shipped concern.

## 8. Recommendation summary

Mechanism **(B) peak-memory bound** + a complementary pull-count sanity check,
gated by a new **`streaming_write` fixture-record flag**, with new conformance
classes in `test_async_extended.py` (ASYNC-021) and `test_streaming.py`
(SIO-003). This keeps BK-240 at its declared effort S and `infra.test` scope,
adds zero public-API surface, and turns three backend-specific regression
guards into one contract-level guard that future streaming backends inherit
automatically.
