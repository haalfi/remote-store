# Research: BK-283 — Replay-backed example testing for live backends

**Date:** 2026-06-12
**Backlog items:** BK-283 (Drive the Graph example snippet from replayed cassettes in CI)
**Status:** Design complete — recording requires a live-credential session, so
implementation is deferred to one. This document settles the mechanism so that
session is execution, not exploration.
**Related:** [BK-262](../BACKLOG-DONE.md) (the cassette core this builds on),
[BK-181 Azure PoC](research-bk-181-cassette-replay-poc.md),
[BK-181 S3 infeasibility](research-bk-181-s3-cassette-infeasibility.md),
[spec 048](../specs/048-testing-architecture.md) (TEST-007/008),
[spec 049](../specs/049-live-recording-architecture.md) (REC-001..007).

---

## 1. Problem Statement

`examples/backends/graph_backend.py` runs only under live Graph credentials:
it is excluded from the `tests/scripts/run_examples.py` CI sweep (which covers
only credential-free example dirs), and Graph has no emulator the way S3 has
moto and Azure has Azurite. The example is therefore the one published snippet
with zero CI execution — a doc-drift hazard the repo's example-testing posture
(subprocess smoke tests, [research-example-testing.md](research-example-testing.md))
cannot reach.

BK-262 landed the missing precondition: 118 replay-able Graph cassettes, the
`GRAPH_PROFILE` scrub layer (including the pre-signed-URL placeholder that
makes record and replay agree), and the `graph_replay` fixture that replays
the real `GraphBackend` + `httpx` transport with no network. BK-283 asks for a
second beneficiary: the example itself, replayed in CI without the live
opt-in.

This research answers three questions:

1. Where should the replayed example run — `run_examples.py` (the backlog
   sketch) or the pytest cassette machinery?
2. Can the conformance cassettes be reused, or does the example need its own?
3. How does the example's auth path (interactive MSAL device-code) survive
   replay?

---

## 2. Constraints Established From the Codebase

These facts bound the design space; each was verified against current source.

1. **vcrpy is in-process.** `run_examples.py` executes examples as
   subprocesses (`subprocess.run([sys.executable, script])`,
   `tests/scripts/run_examples.py`). vcrpy patches the HTTP stack of the
   process it runs in; it cannot intercept a child process. Any replayed
   example must execute in the same process as the cassette context.
2. **Conformance cassettes cannot drive the example — because a cassette
   is a session transcript, not an API model.** vcrpy replay does not
   answer "a write request" with "a write response": it serves the verbatim
   response recorded for that request in one concrete session, and recorded
   responses are entangled with their request's specifics — item name,
   size, eTag, the actual content bytes, and the session's state trajectory
   (exists-after-move, overwrite conflicts). Replaying the example's
   `read_bytes("report.csv")` from a conformance read cassette would hand
   the Store that test's payload, and the snippet would print foreign bytes
   under its own prose. The Store genuinely cannot tell live from cassette
   (that is the whole point), but a transcript can only truthfully answer
   the exact session that produced it; transcripts do not compose across
   sessions, however the URIs are rewritten. The visible URI mismatch
   (`remote-store-example` vs `rs-conformance` roots, per-cassette file
   names) is the symptom, not the cause. A recording of the example's own
   session is therefore required; the backlog sketch's "reuse the
   conformance ones if the call shapes line up" branch is dead.
3. **The auth path cannot replay as recorded.** The example constructs
   `GraphAuth` (MSAL device-code on the recorded consumer tier). On replay
   there is no token cache, `initiate_device_flow` is interactive, and the
   recorded token responses are scrubbed to `REDACTED`
   (`graph.body.token-response`, `_cassettes_graph.py`). The solved pattern
   is `graph_replay`'s: a constant stub token provider
   (`token_provider=lambda: "graph-replay-token"`), with the cassette's
   token-exchange interactions simply never re-requested — vcrpy does not
   require every recorded interaction to be played.
4. **Drive resolution is symmetric via `GRAPH_DRIVE_ID`.** With the env var
   set, the example skips `GraphUtils.aresolve_drive_id`. Record with the
   real id (the `graph.drive-id` env-redact rewrites it to `FAKE_DRIVE_ID`
   everywhere); replay with `GRAPH_DRIVE_ID=FAKE_DRIVE_ID`. Request URIs
   match without recording the resolution round trip.
5. **The scrub layer needs no new rules.** The example's root
   (`remote-store-example`) is a constant — unlike the per-test
   `rs-conformance-<uuid>` folders there is nothing to normalise. Bearer
   tokens, pre-signed URLs, identity PII, and the drive id are all owned by
   the existing `GRAPH_PROFILE` rules, which key on shapes, not on which
   test produced the traffic.
6. **A cassette in `tests/backends/cassettes/graph/` is gate-covered for
   free.** Both the recorder's Step-4 scrub-verify
   (`scripts/record_cassettes.py`) and the creds-free CI PII sweep
   (`test_committed_cassettes_carry_no_forbidden_pii`,
   `tests/backends/fixtures/test_cassettes.py`) glob `*.yaml` over the
   profile's cassette dir. No registration needed.
7. **The conformance conftest routes by node-name token, and the tokens
   already exist.** `vcr_cassette_dir`, `vcr_config`,
   `default_cassette_name`, and the missing-cassette skip all key on the
   fixture ids in `GRAPH_PROFILE.fixture_aliases` (`graph_live`,
   `graph_replay`) appearing as a parametrize-bracket component of the node
   name (`tests/backends/conformance/conftest.py`). The root conftest's
   dynamic vcr-marking under `--record` likewise keys on `"graph_live" in
   item.name`. Any test under `tests/backends/conformance/` whose param ids
   are `graph_live` / `graph_replay` inherits the entire cassette stack —
   routing, scrub config, shared cassette name, skip-on-missing, record-mode
   wiring — with zero conftest or recorder changes.
8. **`record_cassettes.py` wipes the whole cassette dir on a full record**
   (Step 1) and re-records via `-k graph_live` over
   `tests/backends/conformance/` (Step 3). An example cassette recorded by
   anything *outside* that selection would be silently destroyed by the next
   `record-graph` run, and the replay test would skip-on-missing — silent
   coverage loss. The example's record path must be selected by the same
   k-filter and directory, or the recorder must be extended.
9. **Streaming replay is proven.** vcrpy 8.1.1 records and replays
   `httpx.AsyncClient.stream()` with no transport shim
   (`test_httpx_streaming_replay.py`, cited by `graph_replay.py`), so the
   example's streaming-read section replays as-is.
10. **Pre-signed replay is order-dependent** (REC-004): all pre-signed
    interactions collapse to one method+URI and disambiguate by recorded
    order. The example is strictly sequential, so this is safe — but it is a
    standing constraint on what the example may ever do concurrently.

### What a replayed example does and does not cover

Every layer the example traverses is already contract-covered, and by
design no existing test chains them end-to-end:

- `AsyncStore → backend` is backend-generic, tested over
  `AsyncMemoryBackend` / adapted `MemoryBackend` (`tests/aio/conftest.py`).
- `GraphBackend → Graph API` is owned by the conformance suite, which
  drives `async_backend` **directly** — no Store in the loop — against the
  replayed cassettes; the graph unit tests stub the same boundary with
  respx, offline.

Shape containment was verified op by op against the committed corpus:
every backend operation the example's Store calls fan out to has recorded
cassettes — write and overwrite (`TestWriteReadRoundTrip`,
`TestOperationalConsistency`), `read_bytes` and streaming read
(`TestAsyncReadStream`), `get_file_info`, recursive `list_files`, `copy`,
`move`, `exists`, `delete`. The single API call the example can make that
is absent from the corpus is `GraphUtils.aresolve_drive_id("me")`, which
is respx-unit-tested (GR-057, `tests/backends/graph/aio/test_utils.py`)
and skipped symmetrically in both record and replay via `GRAPH_DRIVE_ID`
(constraint 4) — so its absence is a non-event, not a coverage gap.

So the conformance cassettes already encode every backend↔API expectation
the example's traffic exercises; a replayed example adds **zero new
contract coverage**. Its entire value is guarding the published snippet
itself: the imports resolve, the env gate works, the demonstrated API usage
still type-matches and sequences correctly, the printed output is what the
docs show. That is an executable-documentation guard, and the dedicated
cassette in § 2 constraint 2 is a mechanical consequence of replaying a
transcript — not a coverage instrument. Containment also yields a design
assurance: since every interaction shape the example produces is one the
corpus already records and the profile already scrubs, recording the
example's session is risk-free — no new scrub rules, no new PII surface,
no named-rule changes. Corollaries:

- The example test will be the **only** place the full
  `Store → GraphBackend → API` chain executes. That chain's absence from
  unit tests is correct layering, not a gap; the example test must never be
  positioned (in docstrings, traces, or reviews) as the integration test
  for it.
- Assertions belong on the script's observable behaviour (exit, stdout),
  never on backend semantics — those assertions live in conformance.

---

## 3. Options

### 3.1 Option A — Replay driver wired into `run_examples.py`

**Pattern:** A driver script (`tests/scripts/replay_example.py <script>`)
that, inside the subprocess, builds `build_profile_vcr_config(GRAPH_PROFILE,
None)`, enters `vcr.use_cassette(...)`, stubs env + `GraphAuth`, and
`runpy.run_path`s the example. `run_examples.py` gains a "replayed scripts"
table; the CI examples job runs it.

**Trade-offs:**

- Pro: Lands exactly where the backlog sketch pointed; the examples CI job
  stays the single place examples run.
- Con: Re-implements outside pytest what the cassette machinery already owns:
  record-mode wiring, missing-cassette skip, scrub-manifest dump, live
  gating. That is a second copy of spec-049 behaviour (violates SSOT,
  CLAUDE.md principle 4).
- Con: Recording has no home. The driver would need its own `--record` mode
  plus Step-4/Step-5 equivalents, or `record_cassettes.py` grows a
  non-pytest step. Either way constraint 8 (full-record wipe) requires
  bespoke recorder surgery.
- Con: The examples CI job installs `.[dev,arrow]`; it would additionally
  need the graph extra and the cassette tree, coupling two CI jobs to the
  cassette corpus instead of one.

### 3.2 Option B — Example test inside the conformance suite (recommended)

**Pattern:** A new `tests/backends/conformance/test_examples.py` with one
test, parametrized over two ids chosen to match the existing fixture-alias
tokens:

```python
EXAMPLE = Path(__file__).parents[3] / "examples" / "backends" / "graph_backend.py"

@pytest.mark.parametrize(
    "mode",
    [
        pytest.param("live", id="graph_live", marks=pytest.mark.live),
        pytest.param("replay", id="graph_replay", marks=pytest.mark.vcr(record_mode="none")),
    ],
)
def test_graph_backend_example(mode, monkeypatch, capsys):
    if mode == "live":
        if os.environ.get("RS_TEST_LIVE_GRAPH") != "1":
            pytest.skip("graph_live opt-in via RS_TEST_LIVE_GRAPH=1")
        require_graph_live_credentials()  # real env vars stay in place
    else:
        monkeypatch.setenv("GRAPH_TENANT_ID", "consumers")
        monkeypatch.setenv("GRAPH_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
        monkeypatch.setenv("GRAPH_DRIVE_ID", FAKE_DRIVE_ID)
        monkeypatch.setattr("remote_store.aio.GraphAuth", _StubGraphAuth)

    runpy.run_path(str(EXAMPLE), run_name="__main__")

    out = capsys.readouterr().out
    assert "Wrote 2 files." in out
    assert "Cleaned up all example files." in out
    assert "Done!" in out
```

`_StubGraphAuth` accepts the example's constructor arguments and returns a
constant token when called, mirroring `graph_replay`'s
`lambda: "graph-replay-token"`. `runpy.run_path(..., run_name="__main__")`
executes the script exactly as a user does — module-level env gate,
`asyncio.run(main())`, `sys.exit` paths included — which a plain
`import` + `await main()` would not.

By constraint 7, the param ids buy the whole stack:

- `vcr_cassette_dir` routes to `tests/backends/cassettes/graph/`;
  `default_cassette_name` collapses both ids to one shared cassette
  (`test_graph_backend_example[graph].yaml`).
- `vcr_config` builds the `GRAPH_PROFILE` scrub in record mode and the
  deterministic replay config otherwise.
- The missing-cassette skip keeps the replay param inert until the cassette
  is recorded (the same way `graph_replay` shipped before its cassettes —
  with the difference that here the cassette lands in the very next live
  session, not a later milestone).
- Under `--record`, the root conftest adds `pytest.mark.vcr` to the live
  param (it matches `"graph_live" in item.name`).
- By constraint 8's own mechanism, `record_cassettes.py` needs **zero
  changes**: Step 3 (`-k graph_live` over the conformance dir) records the
  example cassette in the same sweep that records the conformance corpus,
  Step 4 sweeps it, Step 5 (`-k graph_replay`) replays it. A full
  `record-graph` regenerates it instead of orphaning it. `min_cassettes=100`
  keeps headroom (corpus goes 118 → 119).

**Trade-offs:**

- Pro: Single source of truth for record/replay/scrub/skip; the example
  becomes one more cassette consumer, which is exactly the BK-283 framing
  ("same `graph_replay` vcr config, second beneficiary").
- Pro: Replay runs in the normal Stage-1 test sweep (`hatch run all`, CI
  test jobs), so the snippet is exercised on every push, not only in the
  examples job.
- Pro: stdout assertions upgrade the example from "no crash" to
  output-verified — the Go-`Example` posture
  [research-example-testing.md](research-example-testing.md) recommended.
- Con: Diverges from the backlog sketch's `run_examples.py` wiring. Per the
  audit-disposition rule (CLAUDE.md), the sketch is advisory; the diagnosed
  pain is "the snippet has no CI coverage", which this resolves with less
  machinery. `run_examples.py` keeps its credential-free scope; its
  docstring gains one line pointing at the conformance example test.
- Con: A test about an example living under `tests/backends/conformance/`
  stretches the dir's name. Accepted: the placement is what makes the
  machinery reuse free, and the module docstring states the rationale.

### 3.3 Option C — Make the example replay-aware itself

**Pattern:** Teach the example a replay mode (env switch selecting a stub
token provider), so it can run under a thin vcr wrapper anywhere.

**Trade-offs:**

- Pro: No auth monkeypatching.
- Con: Test scaffolding leaks into published documentation — the example is
  rendered verbatim into the docs site. Readers would see replay plumbing in
  a snippet whose entire job is to show the real auth flow. Rejected.

### 3.4 Option D — respx fake API instead of a cassette

**Pattern:** Since the example test is an executable-documentation guard
(§ 2), not backend coverage, replay fidelity is arguably negotiable: run the
script under a respx route table faking the Graph API — the same boundary
the graph unit tests stub — with the env/auth stubbing of Option B. Real
`GraphBackend` + real `httpx`, no cassette, no live session ever needed.

**Trade-offs:**

- Pro: Zero recording dependency — implementable and verifiable entirely in
  a creds-free session; immune to the full-record wipe (constraint 8) and
  the pre-signed order-dependence (constraint 10).
- Con: The example's op sequence (write ×2, read, metadata, recursive list,
  server-side copy, move, exists ×2, streaming read, delete sweep) needs a
  stateful hand-written fake of a dozen Graph endpoints, including the
  pre-signed download redirect. That is a second, drifting model of the
  Graph API maintained by hand — precisely what BK-262 built the recording
  pipeline to avoid. A cassette gets real-service fidelity for the cost of
  one recorded test in a sweep that already runs.
- Con: A fake this large invites assertions against its own behaviour; the
  unit tests keep respx honest by scoping each route table to one narrow
  contract, which a whole-script fake cannot.

The same verdict covers the variant of synthesizing the example's cassette
offline from recorded conformance interactions used as templates (rewrite
names, sizes, content bytes): that is hand-editing transcripts whose
response fields are internally entangled (size, eTag, hash, pre-signed
ordering) — a hand-maintained fake in cassette format — and it would break
the BK-262 invariant that every committed cassette is a scrub-verified
recording of real traffic, which is what the PII gates assume.

Rejected for the example guard, but it is the fallback if the live tier
ever becomes unavailable: the guard degrades gracefully to a fake, because
nothing in it asserts backend semantics.

---

## 4. Evaluation

| Criterion | A: run_examples driver | B: conformance test | C: replay-aware example | D: respx fake API |
|-----------|------------------------|---------------------|--------------------------|-------------------|
| Reuses spec-049 machinery | partial (config only) | full | partial | — |
| Recorder integration | bespoke | zero changes | bespoke | — (no cassette) |
| PII gates cover new cassette | yes (dir glob) | yes (dir glob) | yes (dir glob) | — (no cassette) |
| Survives full `record-graph` wipe | needs recorder surgery | automatic | needs recorder surgery | immune |
| Needs a live session once | yes | yes | yes | no |
| API fidelity | recorded | recorded | recorded | hand-maintained fake |
| Example file untouched | yes | yes | no | yes |
| Executes script as `__main__` | yes | yes (runpy) | yes | yes |
| Output verified | exit code only | stdout assertions | exit code only | stdout assertions |
| New process/code surface | driver + runner table | one test module | example churn | test module + fake API model |

Option B dominates A and C on every criterion except fidelity to the
original sketch. Against D the trade is one live recording session versus a
permanently hand-maintained fake of a dozen stateful Graph endpoints; B wins
on maintenance, D remains the documented fallback (§ 3.4).

---

## 5. Recommended Design (Option B) — Implementation Plan

For the live-capable session that implements BK-283:

1. **Add `tests/backends/conformance/test_examples.py`** as sketched in
   § 3.2: the parametrized test, `_StubGraphAuth`, stdout assertions, and a
   module docstring explaining the param-id routing trick, the
   `run_examples.py` division of labour, and the coverage framing from § 2:
   this is an executable-documentation guard — backend↔API expectations
   live in conformance, Store↔backend in `tests/aio/`; assert on the
   script's output, never on backend semantics.
2. **Live-param hygiene:** before and after the live run, best-effort delete
   the drive's `remote-store-example` folder via an unrooted helper backend
   (mirror `graph_live._aclose`'s teardown pattern). The example cleans its
   files but leaves empty folders; pre-cleaning keeps re-records
   deterministic and protects a user's real OneDrive folder from stale
   state.
3. **Record:** either a single-cassette run,
   `python scripts/record_cassettes.py --backend graph --node
   "tests/backends/conformance/test_examples.py::test_graph_backend_example[graph_live]"`,
   or a full `hatch run record-graph` (which now includes the example).
   Steps 4–5 (scrub-verify + Stage-1 replay) run unchanged in both modes.
4. **Verify replay** (principle 6): `pytest tests/backends/conformance/
   -k graph_replay --stage=1` green including the new test; then the full
   `hatch run all` gate.
5. **Ripples** (pre-checked against `sdd/CLAUDE-REFERENCE.md` concerns:
   no backend, error, capability, version, or dependency surface changes):
   - `tests/scripts/run_examples.py` docstring: note that
     `examples/backends/graph_backend.py` is covered by the conformance
     replay test, not this sweep.
   - `sdd/BACKLOG.md`: close BK-283 into BACKLOG-DONE per the completing-work
     procedure; audience `infra.test`, so no CHANGELOG (BK-262 precedent).
   - Trace `sdd/traces/bk-283-example-replay.yml` authored during the
     implementation, same PR.
   - Spec 049 needs no change: the example test consumes existing REC
     surfaces. If review disagrees, the natural anchor is a one-line
     "consumers" note under REC-007.

### Open verification points for the implementing session

Cheap to confirm, listed so they are checked rather than assumed:

- The `--stage` option does not deselect the new test (stage gating is
  registry-fixture-driven; this test is not registry-backed, so it should
  run at every stage, with the live param fenced by the `live` marker and
  the in-test `RS_TEST_LIVE_GRAPH` skip — confirm by collection at
  `--stage=1`).
- The recorded cassette's MSAL token-exchange interactions stay inert under
  `record_mode="none"` with the stub auth (vcrpy does not fail on unplayed
  interactions; confirm on the first replay).
- `monkeypatch.setattr("remote_store.aio.GraphAuth", ...)` lands before
  `runpy` executes the example's `from remote_store.aio import ...` (it
  does — the example binds the name at exec time — but assert the stub was
  actually called, e.g. via a call counter, so a silent fall-through to real
  MSAL fails loudly).
- `examples/_categories.yml` / docs rendering are unaffected (the example
  file itself is untouched; gen_pages parses it via `ast.parse`).

---

## 6. Generalization: Which Live Backends Can This Pattern Reach?

"Replay-backed example testing" is bounded by
[TEST-008](../specs/048-testing-architecture.md#test-008-replay-scope-is-http-transport-only):
replay scope is HTTP transport only, and within that, only stacks vcrpy can
intercept.

| Backend example | Transport | Replay-example feasible? | Worth it? |
|---|---|---|---|
| `graph_backend.py` | httpx (vcrpy-proven) | yes — this design | yes: no emulator exists; only creds-free path |
| `azure_backend.py` | azure.core/requests (BK-181 PoC) | yes — same pattern over `AZURE_PROFILE` | low: the example already documents an Azurite invocation; an emulator-driven CI run is simpler than a cassette |
| `s3_backend.py`, `s3_*.py` | aiobotocore via s3fs | no — vcrpy cannot intercept ([BK-181 spike](research-bk-181-s3-cassette-infeasibility.md)) | moto/MinIO are the right tools |
| `sftp_backend.py` | SSH (paramiko) | no — not HTTP | Docker sftp fixture territory |
| `sql_blob_backend.py` | DB driver | no — not HTTP | SQLite/local DB runs without creds |
| `http_backend.py` | httpx | technically yes | unnecessary: any local HTTP server suffices |

So the honest generalisation is narrow: the pattern earns its keep exactly
where a live HTTP service has no emulator — today, Graph alone, with Azure as
a possible-but-low-value second. The test module should therefore stay a
plain parametrized test, not grow a registration framework; if a second
example ever joins, factor the env-stub/auth-stub pairs into a table inside
the module then, not before (CLAUDE.md content-longevity: build for the
second consumer when it exists).

---

## 7. Recommendation

Implement Option B in a live-credential session: one new test module under
`tests/backends/conformance/`, one recorded cassette, zero changes to
`record_cassettes.py` or the conformance conftest, doc ripples per § 5.
Effort matches the backlog's S estimate. The BK-283 body's `run_examples.py`
wiring is superseded by this design (sketches are advisory; the diagnosed
pain — no CI coverage for the snippet — is fully resolved by the Stage-1
replay test).

Frame it honestly when closing the item: the test guards the published
snippet, it does not extend backend coverage — every backend↔API
expectation in its traffic is already owned by the conformance cassettes
(§ 2). If the live tier ever becomes unrecordable, degrade to the respx
fallback (§ 3.4) rather than letting the guard rot behind a permanent
missing-cassette skip.
