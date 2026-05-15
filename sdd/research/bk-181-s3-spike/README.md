# BK-181 S3 cassette/replay spike

<!-- doc: repo-only -->

Decision gate for PR 2 of BK-181 (HTTP cassette/replay layer). The Azure
PoC (`sdd/research/bk-181-poc/`) settled the mechanism for the Azure SDK
(`azure.core` pipeline + `AsyncioRequestsTransport` shim for the aiohttp
streaming bug). The same vcrpy version (8.1.1) must now be validated
against `s3fs` traffic, which rides `aiobotocore → aiohttp` even from
sync code (via `_fs.call_s3` and `_fs.open`).

The Azure PoC found vcrpy's `aiohttp_stubs.py` drops the response body
on record and deadlocks `AioHttpTransport.__anext__` on replay. For
Azure async, the workaround was to inject `AsyncioRequestsTransport`
via `client_options`. **No equivalent injection point exists for
`s3fs.S3FileSystem`** — its `aiobotocore` transport is hardcoded to
aiohttp. So if the bug bites here too, the only path forward is to
drop s3fs from the replay code path (a non-starter — it would mean
testing a fake backend instead of production code), or wait for vcrpy
to fix `aiohttp_stubs.py`.

## Tests

* `test_spike_s3_write_read_small` — 5-byte round trip. Catches a
  catastrophic body-drop bug for non-streaming paths.
* `test_spike_s3_read_streaming` — 1 MiB write + `read()`-stream-chunk
  iteration. The streaming-body path most analogous to what Azure
  `AioHttpTransport.__anext__` deadlocks on.

## Decision

* **Pass** (both tests record + replay cleanly, bytes match): proceed
  to full PR 2 wiring as planned.
* **Fail** (record drops body, replay deadlocks, or bytes mismatch):
  land an infeasibility doc, open a new BK item, close BK-181 with
  the caveat that S3 replay is blocked on a vcrpy upstream fix.

## Run

```sh
# Record (requires real AWS creds in .env)
RS_TEST_LIVE_S3=1 hatch run pytest sdd/research/bk-181-s3-spike/ --record-mode=rewrite

# Replay (default — no network)
hatch run pytest sdd/research/bk-181-s3-spike/ --block-network \
    --allowed-hosts=127.0.0.1,::1,localhost
```

The spike folder lives outside `testpaths = ["tests"]`, so a normal
`hatch run test` ignores it.

## Frozen

Per the PoC convention, this folder is frozen once the spike settles.
The findings drive the production wiring in PR 2; do not extend the
spike — extend the production fixtures instead.
