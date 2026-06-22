# Testing Runbook
<!-- doc: repo-only -->

Operational companion to [`sdd/TESTING.md`](TESTING.md). TESTING.md owns test
**quality** standards and file placement; this runbook owns the **commands**:
how to select a stage, how to invoke live-cloud tests, and how to record and
refresh HTTP cassettes.

This is a recipe sheet, not a rulebook. For the *why* behind the kind × stage ×
replay model it links the specs and never restates them; when this page and a
spec disagree, the spec wins.

| Authority | Owns |
|---|---|
| [spec 048](specs/048-testing-architecture.md) | Stage selection, kind/stage/replay, cassette-refresh-is-explicit (TEST-006, TEST-007, TEST-009) |
| [spec 049](specs/049-live-recording-architecture.md) | Redaction, scrub audit, async capture (REC-001..008) |
| [ADR-0028](adrs/0028-testing-architecture-kind-stage-replay.md) | Why kind × stage × replay is the decision |
| [`sdd/TESTING.md`](TESTING.md) | Test quality rules, file placement |

## Stages at a glance

Three stages, gated by `--stage`. With no flag the stage auto-detects: Stage 2
when a Docker daemon is reachable, else Stage 1. Override with `--stage=N`, or
set `RS_TEST_STAGE=N` to fix the stage and skip the up-to-5s `docker info`
probe. Higher stages are supersets: Stage 3 still runs Stage 1 and 2 unless you
narrow with `-k` / a node id.

| Stage | Needs | What runs | Invocation |
|---|---|---|---|
| **1** | nothing (no Docker, no network) | in-process backends (`memory`, `local`) + all unit/PBT/contract tests | `hatch run test-cov-s1`, or any run with `--stage=1` |
| **2** | Docker (Azurite, moto, MinIO, sftp) | Stage 1 **plus** emulator-backed conformance | `hatch run test` (probes for Docker), or `--stage=2` |
| **3** | a real cloud account + opt-in env var | Stage 2 **plus** `live`-marked tests against the real service | `--stage=3 -m live` + the backend's `RS_TEST_LIVE_*` flag (recipes below) |

`hatch run all` uses `test-cov-s1` deliberately: the pre-commit gate never
requires Docker. The 95% coverage floor (`test-cov-strict`) lives in CI and the
publish workflow, where Azurite is up; do not substitute it locally (see
[CLAUDE.md § Coverage gate](../CLAUDE.md#coverage-gate)).

The gate runs against the editable install, so do not mutate the working tree
while one is in flight (a background `hatch run all`, a watch loop). Concurrent
edits or a `git stash` feed the running gate a tree it never saw whole, producing
failures that vanish on a clean re-run. To check whether a fix is load-bearing,
prove the failure in isolation (revert the fix, run, observe), not by editing
alongside a live gate.

Stage selection is the authority of
[TEST-006](specs/048-testing-architecture.md#test-006-stage-selection): live
tests run only at `--stage=3` with the matching opt-in env var; CI never runs
them.

## Live cloud: exact invocation

A live run needs three things set at once, and each has a trap if you miss it
(see the trap table below):

1. The backend's opt-in flag exported **in the shell**, deliberately *not* in
   `.env`, so a default `hatch run test` never touches a real account.
2. `--stage=3` so the live fixtures are collected at all.
3. `-m live` on the command line to override the default `addopts` `-m 'not
   live'`, which otherwise silently deselects every `live`-marked test.

Credentials (connection strings, AWS keys, Graph client ids) live in `.env`;
`pytest_configure` loads `.env` when a `live` mark inclusion is detected, so the
collection-time `skipif` gates see the values. The opt-in *flag* is the one var
you keep out of `.env`.

### Per-backend recipes

The opt-in flag, the required credential vars, and the conformance fixture ids
are declared in [`tests/backends/fixtures/_live_env.py`](../tests/backends/fixtures/_live_env.py)
(the fail-loud validators) and the per-backend `*_live.py` fixture modules.

**Azure ADLS Gen2 (HNS), conformance:**

```bash
RS_TEST_LIVE_HNS=1 hatch run python -m pytest \
  "tests/backends/conformance/test_errors.py::TestX::test_y[azure_live]" \
  --stage=3 -m live -n0 -v --tb=short
```

Needs `AZURE_STORAGE_CONNECTION_STRING` (a real account; an Azurite signature
fails loud). The per-backend HNS deviation suite under `tests/backends/azure/`
additionally needs `RS_TEST_LIVE_HNS_CONTAINER` (the persistent ADLS Gen2
filesystem name). It exercises HNS-only behaviour the conformance suite cannot
express (`hdi_isfolder` directory markers, the `exists` DataLake fallback, root
`get_folder_info("")`, `AzureUtils.detect_hns`).

**AWS S3, conformance:**

```bash
RS_TEST_LIVE_S3=1 hatch run python -m pytest \
  "tests/backends/conformance/test_errors.py::TestX::test_y[s3_live]" \
  --stage=3 -m live -n0 -v --tb=short
```

Needs `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`. If
`AWS_ENDPOINT_URL` / `AWS_S3_ENDPOINT_URL` is set it must not point at an
emulator (moto/MinIO/LocalStack signatures fail loud). The live IAM user is
scoped to a bucket prefix; see the "Required IAM permissions" comment in
[`tests/backends/fixtures/s3_live.py`](../tests/backends/fixtures/s3_live.py).

**Microsoft Graph (OneDrive), live e2e:**

```bash
RS_TEST_LIVE_GRAPH=1 hatch run pytest \
  tests/e2e/ -o addopts= -p no:randomly -n0 -k graph -v
```

`GraphBackend` is async-only (construct it with `AsyncStore`); the medallion e2e
bridges it to a sync `Store` via the `graph_lake` fixture, which skips unless the
`RS_TEST_LIVE_GRAPH` gate is satisfied (Graph has no emulator). The `-k graph`
filter targets the Graph-specific cases — `test_graph` in
`tests/e2e/test_data_lake.py` and the `test_memory_to_graph` /
`test_graph_to_memory` transfers in `tests/e2e/test_transfer.py` — and skips the
Docker medallion variants (`test_azurite`, `test_s3_pyarrow_minio`) that the bare
file path would otherwise collect. The async streaming-integrity hop lives in
`tests/e2e/test_async_streaming_integrity.py` (gated by `_graph_live_available()`).

Credentials are device-code (delegated) against a personal Microsoft account:
`GRAPH_CLIENT_ID` / `GRAPH_TENANT_ID` (`consumers`) / `GRAPH_DRIVE_ID`. The MSAL
refresh token comes from the cache the first interactive sign-in writes; there is
no client secret. e2e tests are excluded from the default `addopts`
(`--ignore=tests/e2e`), so the recipe clears `addopts` entirely with `-o addopts=`
(which lifts both the ignore and `-m 'not live'`). Run the whole e2e suite with
`hatch run e2e`.

### Partitioning by backend

In `tests/backends/conformance/`, the fixture id appears only inside the
`[...]` parametrize segment of the node id (class and method names use abstract
terms), so `-k <fixture-stem>` cleanly selects one backend without colliding
with test names:

```bash
hatch run python -m pytest tests/backends/conformance/ -k "local"          # local + local_async_adapted
hatch run python -m pytest tests/backends/conformance/ -k "s3 or sftp"     # cloud-stack fixtures
```

Authoritative fixture ids live in `tests/backends/fixtures/`.

### Trap table

Each row is a way a live or e2e run silently does the wrong thing.

| Trap | Symptom | Fix |
|---|---|---|
| Missing `-m live` | live fixtures collected then **silently deselected** (default `addopts` carries `-m 'not live'`) | always pass `-m live`; the CLI `-m` wins over `addopts` |
| Missing `--stage=3` | live fixtures never collected | live needs `--stage=3` **and** `-m live` together; neither alone is enough |
| `-p no:xdist` for a single node | `INTERNALERROR ... unknown hook 'pytest_configure_node'` (the mutation plugin aborts) | use `-n0`, which keeps xdist loaded and runs serially in-process |
| Running e2e under default `addopts` | e2e ignored (`--ignore=tests/e2e`) and live deselected | clear it with `-o addopts=` (lifts both), or use `hatch run e2e` |
| Opt-in flag in `.env` | a default `hatch run test` would hit a real account | keep `RS_TEST_LIVE_*` out of `.env`; export it per-shell. Credentials may live in `.env` |
| Azurite stands in for ADLS Gen2 | emulator accepts quirks real ADLS rejects (no Hierarchical Namespace) | HNS behaviour must be verified at Stage 3 against a real account, never inferred from a green Azurite run |

`--runxfail` lifts an `xfail` mask so a live run reports the real pass/fail
instead of `XFAIL`/`XPASS`. Use it to check whether an `xfail` is still
warranted against the live endpoint (e.g. confirming a divergence is
emulator-only). The xfail roster lives at the top of
[`tests/backends/conformance/conftest.py`](../tests/backends/conformance/conftest.py).

## Cassette record & refresh (HTTP-transport backends)

Cassettes under `tests/backends/cassettes/<backend>/` are committed snapshots of
real HTTP traffic. Refresh them when the backend SDK, the scrubbing layer, or
the real service responses change. Per
[TEST-009](specs/048-testing-architecture.md#test-009-cassette-refresh-is-explicit),
CI does not auto-record; a refresh is a normal PR diff. The redaction
architecture is [spec 049](specs/049-live-recording-architecture.md).

**Prerequisite (Azure):** see
[Azure HNS account setup](../docs-src/guides/backends/azure-hns-setup.md) for
credential and `.env` configuration. The recording needs the live opt-in flag
set in the invoking shell.

### Full re-record (all-or-nothing)

```bash
RS_TEST_LIVE_HNS=1 hatch run record-azure
```

`scripts/record_cassettes.py --backend azure` deletes existing cassettes,
re-records sync and async fixtures against a live ADLS Gen2 account, verifies no
credentials survived scrubbing, and runs a Stage 1 replay smoke test. Pass
`--verify-only` to skip recording and re-run only the verification steps. The
Graph equivalent is `hatch run record-graph` (device-code sign-in on first run).

The azure record run covers **two** trees: the conformance suite (`azure_live` →
`azure_replay`) and the HNS deviation suite (`azure_live_hns` →
`azure_replay_hns`). The latter needs `RS_TEST_LIVE_HNS_CONTAINER` set alongside
`RS_TEST_LIVE_HNS=1`. Both trees share `tests/backends/cassettes/azure/`; the HNS
cassettes use the `[azure_hns]` / `[azure_hns_async]` alias.

The full run deletes the cassette tree at Step 1 *before* re-recording, so an
aborted run (lost credentials, network drop) can leave the tree partially wiped.
Recover the committed cassettes with `git checkout -- tests/backends/cassettes/azure/`,
then re-run. The single-cassette path below avoids the delete entirely.

Because the delete comes first, prove every test in scope passes live *before*
the destructive run, with a plain no-`--record` live pass:

```bash
RS_TEST_LIVE_HNS=1 hatch run python -m pytest tests/backends/conformance/ \
  --stage=3 -m live -k "azure_live and not async" -n0
```

This hits real HTTP: the conformance conftest only adds `pytest.mark.vcr` under
`--record`, so without it there is no record/replay interception. A green sync
run (plus a second pass with `-k azure_live_async`) means the subsequent
`record-azure` will not abort partway and leave the tree half-wiped.
`--verify-only` cannot substitute, it only replays existing cassettes.

### Single-cassette refresh (no tree-wipe)

To record or refresh **one** cassette without the all-or-nothing delete, pass
`--node` with the live-variant node id. Invoke the script through `hatch run
python`, **not** the `record-azure` alias:

```bash
RS_TEST_LIVE_HNS=1 hatch run python scripts/record_cassettes.py --backend azure \
  --node "tests/backends/conformance/test_errors.py::TestX::test_y[azure_live]"
```

This skips the Step-1 delete and the min-cassette guard, records only the named
test, then runs the same scrub-verify + Stage 1 replay over the whole corpus.
Use it for a focused PR diff: every other cassette's volatile headers stay put.
The Graph equivalent swaps `--backend graph` (and `RS_TEST_LIVE_GRAPH=1`).

> [!WARNING]
> Do **not** write `hatch run record-azure --node "..."`. The `record-azure` /
> `record-graph` script aliases do not forward trailing flags, so hatch drops
> `--node`, the script falls back to full-tree-wipe mode, and (with the live
> flag set) it deletes and re-records the entire cassette tree. Always go
> through `hatch run python scripts/record_cassettes.py --backend <b> --node …`,
> which passes argv straight to the script.

The `--node` selector can also be a **directory**, not just a single node id:
`--node "tests/backends/azure/"` records every live test under that path (the
whole HNS deviation suite, sync and async) in one no-tree-wipe run. In single
mode the script hands the selector to pytest as a positional with `-m live`, so
a directory collects all live tests beneath it.

For a **subset of N cassettes** (more than one, fewer than a whole directory),
`--node` does not fit, it takes a single selector. Use a raw two-command form: a
`pytest --record` run filtered with `-k`, then a `--verify-only` pass for the
whole-dir scrub-verify and replay smoke.

```bash
RS_TEST_LIVE_HNS=1 hatch run python -m pytest tests/backends/azure \
  --stage=3 --record -m live -k "name1 or name2" -n0 -p no:unraisableexception
RS_TEST_LIVE_HNS=1 hatch run python scripts/record_cassettes.py \
  --backend azure --verify-only
```

The raw `pytest --record` run needs `-p no:unraisableexception` by hand: vcrpy's
record-mode transport orphans the live SSL sockets it wraps, and their GC
`ResourceWarning` would otherwise abort the run under the suite's
`filterwarnings = error`. The `record_cassettes.py` wrapper adds the flag to its
own subprocesses automatically; a bare `pytest --record` does not.

### Large-payload exclusion

Conformance tests that upload an 8 MiB payload carry
`@pytest.mark.large_payload`. The conformance collection hook skips any
`large_payload` test that lands on a `live` fixture, so neither `record-azure` /
`record-graph` nor an ad-hoc `--stage=3 -m live` run hits a pay-per-use account
with them (a full recording would otherwise produce ~100×-norm, multi-MB
cassettes). They keep their staged/multipart coverage for free at Stage 2.

### Recording traps

| Trap | Why it bites | Fix |
|---|---|---|
| PII survives in **headers** | the scrub layer applies body regexes to the response body and a separate allowlist drop to headers; a secret can survive verbatim in an un-listed header in a different format | scrub headers **and** bodies; verify by grepping the **raw secret value** (the GUID/email/id itself, case-insensitive) across the cassette bytes, not just the `"key":"value"` JSON form. Base64-embedded secrets (`id_token`, `client_info`) need a JWT-shape marker |
| Shared-state residue when promoting live → replay | a test that reads shared mutable account state (a container/bucket root listing) bakes whatever happened to be there at record time; a re-record then churns the file with unrelated entries and may capture un-anticipated PII | isolate the test on a dedicated **empty** namespace (fresh filesystem/container, name scrubbed to the placeholder so replay matches), then assert exact aggregates (`file_count == 0`) |
| Cassette proves the test never hits its named path | assertion-on-outcome ≠ the documented branch being taken; a short-circuit can make a "fallback" path dead | **read the recorded request sequence**; pin the real distinguishing behaviour and correct the docstring if the cassette contradicts it |
| `.env` masks a CI cred-absence failure | unit tests that drive `record_cassettes.main()` run Step-4 scrub-verify, which calls the backend's `account_fn` resolver; it reads creds from `.env` locally but finds nothing in CI | inject the value via `monkeypatch.setenv` (a syntactically valid, non-emulator value); verify CI-faithfully by running with a hostile ambient value to prove the monkeypatch overrides `.env` |

## Cassette-first bug investigation

When investigating a bug in an HTTP-transport backend whose live behaviour is
recorded as a cassette, default to **replay-first**: work on the committed
cassette until root cause is clear, escalate to a fresh recording only if the
cassette cannot carry the diagnosis. Final sign-off always runs against the live
service. The architecture under this workflow is
[ADR-0028](adrs/0028-testing-architecture-kind-stage-replay.md).

**Step 1: Reproduce on the cassette.** Run the failing conformance test against
the `<backend>_replay` (and `_replay_async`) fixture. No credentials, no
network, no Docker.

```bash
hatch run python -m pytest "<nodeid>[azure_replay]" -v --tb=short
```

If the test is marked `xfail(strict=False)` against real-cloud fixture ids
(confirmed defects parked to keep CI green), pytest reports `XFAIL` and hides
the assertion. Force the underlying failure with `--runxfail`. Removing a test
function name from the roster in
[`tests/backends/conformance/conftest.py`](../tests/backends/conformance/conftest.py)
un-xfails it for all real-cloud fixture ids in one place.

**Step 2: Classify cassette sufficiency.** Read the backend code the failing
test exercises and ask: does the fix require any HTTP call the cassette does not
already contain?

| Fix shape | Cassette sufficiency | Action |
|---|---|---|
| In-process filter / mapping over data the SDK already returns | Sufficient | Proceed to step 3 |
| Adds, removes, or reorders SDK calls | Insufficient | Refresh the cassette (needs Stage 3 live access), then resume on the new one (`--node` for a single test to avoid churning the corpus) |

The decision is mechanical: list the SDK calls the fix introduces, grep the
cassette `interactions:` list for matching `method` + `uri` patterns, and
proceed only when every needed call is already recorded.

**Step 3: Fix.** Implement the change in the backend module(s).

**Step 4: Verify on replay.** Remove the test function name from the xfail
roster (Step 1) and re-run the same nodeid without `--runxfail`. Green = the fix
is consistent with the recorded wire behaviour.

**Step 5: Final verification on live.** Run against the `<backend>_live` /
`_live_async` fixture before merge (the live recipes above). Live is the source
of truth; the cassette is only a faithful recording of a single trajectory.
Account-config variance, eventual consistency, and timing-dependent SDK paths
can hide behind a green replay.
