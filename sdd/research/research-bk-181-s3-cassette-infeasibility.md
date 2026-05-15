# Research: BK-181 PR 2 — S3 cassette/replay infeasibility

**Date:** 2026-05-15
**Status:** Spike complete. Verdict: **NO-GO for the planned PR 2 scope.**
S3 replay cannot be implemented today via vcrpy/pytest-recording without
upstream changes. Recommended close-out: BK-181 ships at the Azure slice
(PR 1a/1b, already merged); revisit S3 when vcrpy supports the
`aiobotocore` transport stack.
**Scope:** Validate whether the [BK-181 Azure verdict](research-bk-181-cassette-replay-poc.md)
extends to `S3Backend`'s code path. The Azure PoC settled the mechanism
question for `azure.core` and warned that S3 needed separate validation
because `s3fs` rides `aiobotocore` and `aiohttp` rather than `azure.core`.
This spike answers that question.
**Related:** [BK-181](../BACKLOG.md), [BK-181 Azure PoC](research-bk-181-cassette-replay-poc.md),
[spec 048](../specs/048-testing-architecture.md) (TEST-007/008/009),
the spike folder [`bk-181-s3-spike/`](bk-181-s3-spike/).

## Verdict

S3 cannot be brought under the cassette/replay layer in PR 2. The
underlying issue is well outside this repo: vcrpy 8.1.1's `aiohttp_stubs.py`
cannot transparently intercept the `aiobotocore` request/response cycle
that `s3fs` relies on. The failure is not a quirk of streaming-only
paths (the Azure caveat) but applies to every `s3fs` write and read,
because every such call is dispatched through `aiobotocore` even from
sync entry points (`_fs.pipe_file`, `_fs.cat_file`, `_fs.call_s3`).

The user-facing impact is small. `s3_moto` already provides a
high-fidelity Stage-1 in-process S3 fixture
(`tests/backends/fixtures/s3_moto.py`), so the conformance suite covers
S3 without network or Docker today. The original BK-181 motivation
("turn Azure HNS bugs into always-on regression guards") never applied
to S3 — Azure needed cassettes because Azurite cannot emulate the
hierarchical namespace, while moto emulates S3 with enough fidelity for
the conformance contract. Spec [TEST-008](../specs/048-testing-architecture.md#test-008-replay-scope-is-http-transport-only)
gains a "Noted exception — S3" paragraph that narrows
[TEST-007](../specs/048-testing-architecture.md#test-007-http-cassette-and-replay-layer)'s
otherwise-universal "HTTP backends support replay" invariant; the
paragraph points at this finding for the diagnosis.

## What was tested

Spike folder: [`sdd/research/bk-181-s3-spike/`](bk-181-s3-spike/), outside
`testpaths`, run by pointing pytest at it explicitly. Two probes were
exercised against a real AWS account (the same `s3_live` env that
`tests/backends/fixtures/s3_live.py` validates).

| File | Role |
|---|---|
| `conftest.py` | Minimal vcrpy wiring: scrub headers, query params, AWS auth signature |
| `test_spike.py` | `S3Backend.write` / `read_bytes` round-trip + 1 MiB streaming read |
| `isolation_check.py` | The same two operations driven through `vcr.use_cassette` directly, bypassing pytest-recording entirely |

The IAM policy on the `s3_live` account restricts `s3:CreateBucket` /
`s3:PutObject` to `arn:aws:s3:::rs-conformance-*`, so the spike uses
`rs-conformance-bk181spike` as a stable bucket name (no per-run UUID
rewriting needed at this stage).

## Failure mode

Both the pytest-driven spike and the standalone `isolation_check.py`
fail in the same way during recording, with a `--record-mode=all`
(equivalently `rewrite`) session pointed at a real AWS endpoint:

```
File "site-packages/s3fs/core.py", line 211, in _error_wrapper
    await tb.tb_frame.f_locals["response"]
          ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
KeyError: "local variable ''response'' is not defined"
<sys>:0: RuntimeWarning: coroutine 'AioAwsChunkedWrapper.read' was never awaited
```

What this is saying:

1. vcrpy hooks the underlying aiohttp connection used by `aiobotocore`.
2. The hooked code path attempts to consume the request body
   (`AioAwsChunkedWrapper.read`) but vcrpy's stub does not properly
   drive the async-iteration protocol the wrapper expects.
3. The coroutine is left un-awaited and the request fails partway.
4. `s3fs.core._error_wrapper` (`s3fs/core.py:211`) tries to introspect
   the failed call's traceback for a `response` local. Because the
   failure occurred before any HTTP response could be constructed,
   `response` is never bound — `s3fs` then raises `KeyError`.
5. No cassette is written (`isolation.yaml` is never created).

This is the same family as the Azure PoC's "aiohttp streaming-body bug"
([research-bk-181-cassette-replay-poc.md § Success criteria — results](research-bk-181-cassette-replay-poc.md)),
but worse: for Azure the bug applies only to *response* bodies and
only on the async path; for `s3fs` it applies to every `aiobotocore`
call because the request bodies themselves are wrapped in an async
chunked reader the vcrpy stub cannot drive. Sync entry points
(`_fs.pipe_file` etc.) trip the same path because `s3fs` invokes
`aiobotocore` through a private event loop regardless of caller mode.

## Workarounds considered

1. **Inject a non-aiohttp transport into `s3fs`** (the Azure trick).
   *Verdict: not available.* `azure.core` exposes a pluggable
   `transport=` parameter so we can swap `AioHttpTransport` for
   `AsyncioRequestsTransport`. `aiobotocore` has no such hook —
   `aiohttp` is hardwired in `aiobotocore.endpoint.AioEndpoint` and
   `s3fs` exposes no toggle to replace it.
2. **Drop `s3fs` from the replay path; use plain `boto3` (sync)**.
   *Verdict: defeats the purpose.* Cassette tests exist to exercise the
   real production-code SDK pipeline. `S3Backend` *is* `s3fs`; if a
   replay fixture uses raw `boto3` it stops testing the code that
   ships to users. The cassettes would catch nothing the existing
   `s3_moto` fixture does not already catch.
3. **Wait for a vcrpy upstream fix.** *Verdict: not under our
   control.* vcrpy's `aiohttp_stubs.py` is a long-standing rough edge
   ([kevin1024/vcrpy](https://github.com/kevin1024/vcrpy)). No fix is
   scheduled. This finding and the preserved spike folder are the
   retest entry points if a future contributor wants to re-evaluate
   against a new vcrpy release.
4. **Write a custom `aiobotocore` recorder.** *Verdict: out of scope.*
   A bespoke recorder would be a sizeable internal tool, and the
   value is low: `s3_moto` already covers the Stage-1 conformance
   surface for S3. The original Azure justification (no Stage-1
   emulator covers HNS) does not apply.

## Why moto is sufficient

For Azure, `s3_moto`'s analogue does not exist: Azurite does not
emulate the Hierarchical Namespace, so contracts like
`hdi_isfolder` directory probes and the BUG-195..203 family can only
be observed against real ADLS Gen2. The replay layer turns those
contracts into always-on tests by recording them once.

For S3, every conformance contract the suite cares about — the
existing parametrised tests — already runs against `s3_moto` at
Stage 1 today
(`tests/backends/fixtures/s3_moto.py`,
`tests/backends/fixtures/fixtures.toml`). `s3_moto` exercises the
same `S3Backend → s3fs → aiobotocore → aiohttp → moto server` chain
end-to-end with no network, no Docker, and no live cloud account.
The few S3-specific defects that *would* be S3 analogues of the HNS
BUG-* family (multipart-upload edge cases, presigned-URL handling,
versioning quirks) are not on BK-181's roadmap and have no committed
backlog item demanding cassette coverage.

The remaining gap — a real-AWS contract that moto's emulation does
not match — is covered by `s3_live` at Stage 3 (manual or scheduled
CI cadence). The `live` mark keeps it out of default runs.

## Recommendation

Close BK-181 at PR 2 with the S3 slice deferred:

1. Move BK-181 from BACKLOG.md to BACKLOG-DONE.md (status flips
   `[~]` → `[x]`) with the Azure-shipped, S3-deferred outcome
   documented in the close-out entry.
2. Amend [spec 048 TEST-008](../specs/048-testing-architecture.md#test-008-replay-scope-is-http-transport-only)
   with a "Noted exception — S3" paragraph that narrows
   [TEST-007](../specs/048-testing-architecture.md#test-007-http-cassette-and-replay-layer)'s
   "HTTP backends support replay" invariant, pointing here for the
   diagnosis.

No follow-up backlog item is filed: `s3_moto` already covers Stage 1,
no S3-specific contract today demands cassette-level fidelity, and the
fix path runs through upstream vcrpy rather than this repo. If a
future need surfaces, this doc and the spike folder are the entry
points to re-evaluate the decision.

The trace `sdd/traces/BK-181-cassette-replay-impl.yml` is extended with
an `s3-spike-finding` phase pointing here.

## Spike folder fate

Per the repo's PoC convention, the spike folder is frozen once the
finding is recorded. `bk-181-s3-spike/` stays as evidence:
`isolation_check.py` is the smallest reproducer if a future contributor
wants to retest against a new vcrpy or s3fs release. `test_spike.py`
and `conftest.py` document the pytest-recording wiring path that did
not work and serve as a starting point for any future revisit.
