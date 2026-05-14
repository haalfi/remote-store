# BK-181 PoC — HTTP cassette/replay layer

<!-- doc: repo-only -->

A throwaway spike that answers one question for **BK-181** (Spec 048
Phase 3, TEST-007/008/009): can `pytest-recording`/vcrpy record the real
Azure SDK HTTP traffic and replay it at zero cost, for both the sync and
async backends, with credentials scrubbed?

The verdict and its reasoning live in
[`../research-bk-181-cassette-replay-poc.md`](../research-bk-181-cassette-replay-poc.md).
This folder is the evidence behind that doc. Per the repo's PoC convention
it **freezes** once the finding lands — BK-181 proper reimplements at the
real tree paths (`tests/backends/fixtures/azure_replay.py`,
`tests/backends/cassettes/azure/`), it does not extend this folder.

## Layout

| File | Role |
|---|---|
| `conftest.py` | vcrpy wiring: scrubbing layer, record/replay connection-string switch, backend fixtures, missing-cassette → skip |
| `test_replay_sync.py` | `AzureBackend`: happy-path round-trip + the BUG-197 unhappy case |
| `test_replay_async.py` | `AsyncAzureBackend` via the `AsyncioRequestsTransport` shim — vcrpy's `AioHttpTransport` stub can't stream a body, so the shim is the make-or-break finding (see the finding doc) |
| `cassettes/` | Recorded, scrubbed YAML cassettes (committed) |

This folder is outside `testpaths` in `pyproject.toml`, so a normal
`hatch run test` never collects it. Every command below names the path
explicitly.

## Prerequisite

`pytest-recording` is **not** in `pyproject.toml` (this is a throwaway
spike). Install it ad-hoc into the hatch env:

```
uv pip install --python .venv pytest-recording
```

## Replay — the default, zero credentials

```
hatch run pytest sdd/research/bk-181-poc/ --block-network --allowed-hosts=127.0.0.1,::1,localhost
```

`record_mode` defaults to `none`: the backend is built from a fixed *fake*
connection string and vcrpy serves every response from `cassettes/`.
`--block-network` makes any real network call a hard error, so a green run
proves zero network. The `--allowed-hosts` loopback allowance is needed
only on Windows — pytest-recording's guard otherwise blocks the
`ProactorEventLoop` self-pipe and the async tests error at loop creation;
real Azure hosts stay blocked. A test whose cassette is missing **skips**
(TEST-007), it does not fail.

## Record — needs a real ADLS Gen2 account

```
RS_TEST_LIVE_HNS=1   # plus AZURE_STORAGE_CONNECTION_STRING in .env
hatch run pytest sdd/research/bk-181-poc/ --record-mode=rewrite
```

`--record-mode=rewrite` deletes the old cassette and re-records against the
real account named by `AZURE_STORAGE_CONNECTION_STRING`. Missing or
Azurite-pointing credentials fail loud (repo convention — a silent skip
while recording would mean "I thought I captured it" but didn't). The
scrubbing layer in `conftest.py` rewrites the real account name to
`bk181poc` and drops `Authorization` / `x-ms-date` / request-id headers
before anything is written to disk.

Recording reuses a persistent `bk181poc` filesystem on the account
(deterministic name — a per-run uuid would break cassette matching).
Delete that filesystem by hand for a fully clean capture.

## Verifying a recording

```
# no real account name anywhere in the committed cassettes:
grep -ril "<your-real-account>" sdd/research/bk-181-poc/cassettes/
# no credential headers:
grep -ril "authorization" sdd/research/bk-181-poc/cassettes/
```
