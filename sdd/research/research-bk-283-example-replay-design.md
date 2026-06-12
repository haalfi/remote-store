# Research: Replay-backed example testing for live backends (BK-283)

**Date:** 2026-06-12
**Backlog items:** BK-283 (Drive the Graph example snippet from replayed cassettes in CI)
**Status:** Research complete: design settled. Recording requires a
live-credential session, so implementation is deferred to one; this document
settles the mechanism so that session is execution, not exploration.
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
moto and Azure has Azurite. It is therefore the one published snippet with
zero CI execution, a doc-drift hazard the repo's example-testing posture
([research-example-testing.md](research-example-testing.md)) cannot reach.

BK-262 landed the missing precondition: replay-able Graph cassettes (118 at
the time of writing), the `GRAPH_PROFILE` scrub layer, and the `graph_replay`
fixture that replays the real `GraphBackend` + `httpx` transport with no
network. BK-283 asks for a second beneficiary: the example itself, replayed
in CI without the live opt-in.

Decisions this research informs:

1. Where the replayed example runs: `run_examples.py` (the backlog sketch)
   or the pytest cassette machinery.
2. Whether the conformance cassettes can be reused, or the example needs its
   own recording.
3. How the example's auth path (interactive MSAL device-code) survives replay.

### 1.1 Constraints from the codebase

Each verified against current source; together they bound the design space.

1. **vcrpy is in-process.** `run_examples.py` executes examples as
   subprocesses; vcrpy patches the HTTP stack of the process it runs in and
   cannot intercept a child. A replayed example must execute in the same
   process as the cassette context.
2. **A cassette is a session transcript, not an API model.** Replay serves
   the verbatim response recorded for that request in one concrete session,
   and responses are entangled with that session's specifics: item names,
   sizes, eTags, content bytes, state trajectory. Replaying the example's
   `read_bytes("report.csv")` from a conformance cassette would print
   foreign bytes under the snippet's prose. Transcripts do not compose
   across sessions, however the URIs are rewritten; the visible URI mismatch
   (`remote-store-example` vs `rs-conformance` roots) is the symptom, not
   the cause. The example needs a recording of its own session; the backlog
   sketch's "reuse the conformance ones if the call shapes line up" branch
   is dead.
3. **The auth path cannot replay as recorded.** The example constructs
   `GraphAuth` (MSAL device-code); on replay there is no token cache, the
   flow is interactive, and recorded token responses are scrubbed to
   `REDACTED`. The solved pattern is `graph_replay`'s constant stub token
   provider (`token_provider=lambda: "graph-replay-token"`); vcrpy does not
   require every recorded interaction to be played, so the cassette's
   token-exchange interactions simply stay inert.
4. **Drive resolution is symmetric via `GRAPH_DRIVE_ID`.** With the env var
   set, the example skips `GraphUtils.aresolve_drive_id`. Record with the
   real id (the `graph.drive-id` env-redact rewrites it to `FAKE_DRIVE_ID`
   everywhere); replay with `GRAPH_DRIVE_ID=FAKE_DRIVE_ID`. Request URIs
   match without recording the resolution round trip.
5. **The scrub layer needs no new rules.** The example's root
   (`remote-store-example`) is a constant, unlike the per-test
   `rs-conformance-<uuid>` folders. Bearer tokens, pre-signed URLs, identity
   PII, and the drive id are owned by existing `GRAPH_PROFILE` rules, which
   key on shapes, not on which test produced the traffic.
6. **A cassette in `tests/backends/cassettes/graph/` is gate-covered for
   free.** The recorder's scrub-verify step and the creds-free CI PII sweep
   both glob `*.yaml` over the profile's cassette dir. No registration.
7. **The conformance conftest routes by node-name token.** Cassette dir, vcr
   config, shared cassette name, missing-cassette skip, and the root
   conftest's `--record`-mode marking all key on the fixture-alias tokens
   `graph_live` / `graph_replay` appearing in the node name. Any test under
   `tests/backends/conformance/` whose param ids are those tokens inherits
   the entire cassette stack with zero conftest or recorder changes.
8. **`record_cassettes.py` wipes the whole cassette dir on a full record**
   and re-records via `-k graph_live` over `tests/backends/conformance/`.
   A cassette recorded by anything outside that selection is silently
   destroyed by the next `record-graph` run, and skip-on-missing makes the
   loss invisible. The example's record path must be selected by the same
   k-filter and directory, or the recorder must be extended.
9. **Streaming replay is proven.** vcrpy 8.1.1 replays
   `httpx.AsyncClient.stream()` with no transport shim
   (`test_httpx_streaming_replay.py`), so the example's streaming-read
   section replays as-is.
10. **Pre-signed replay is order-dependent** (REC-004): pre-signed
    interactions disambiguate by recorded order. Safe for the strictly
    sequential example, and a standing constraint on what it may ever do
    concurrently.

### 1.2 What the test guards

Every layer the example traverses is already contract-covered, and by design
no existing test chains them end-to-end: Store → backend is tested over the
memory backends (`tests/aio/conftest.py`); GraphBackend → API is owned by the
conformance suite, which drives the backend directly against the replayed
cassettes. Shape containment was verified op by op against the committed
corpus: every backend operation the example's Store calls fan out to has
recorded conformance cassettes. The single absent API call,
`GraphUtils.aresolve_drive_id("me")`, is respx-unit-tested (GR-057) and
skipped symmetrically in record and replay via constraint 4: a non-event,
not a coverage gap.

A replayed example therefore adds **zero new contract coverage**. Its value
is guarding the published snippet itself: imports resolve, the env gate
works, the demonstrated API usage still type-matches and sequences, the
printed output is what the docs show. That is an executable-documentation
guard; the dedicated cassette (constraint 2) is a mechanical consequence of
replaying a transcript, not a coverage instrument. Containment also makes
recording risk-free: every interaction shape the example produces is one the
profile already scrubs, so no new scrub rules and no new PII surface.
Corollaries:

- The example test will be the **only** place the full
  `Store → GraphBackend → API` chain executes. That chain's absence from
  unit tests is correct layering, not a gap; never position the test (in
  docstrings, traces, or reviews) as the integration test for it.
- Assertions belong on the script's observable behaviour (exit, stdout),
  never on backend semantics; those live in conformance.

---

## 2. Survey: Options

### 2.1 Option A: Replay driver wired into `run_examples.py`

**Pattern:** A driver script that, inside the subprocess, builds the
`GRAPH_PROFILE` vcr config, enters `vcr.use_cassette(...)`, stubs env +
`GraphAuth`, and `runpy.run_path`s the example; `run_examples.py` gains a
"replayed scripts" table.

**Trade-offs:**

- Pro: Lands where the backlog sketch pointed; the examples CI job stays the
  single place examples run.
- Con: Re-implements outside pytest what the cassette machinery owns:
  record-mode wiring, missing-cassette skip, scrub-manifest dump, live
  gating. A second copy of spec-049 behaviour (violates SSOT, CLAUDE.md
  principle 4).
- Con: Recording has no home: the driver needs its own `--record` mode plus
  scrub-verify/replay-check equivalents, and constraint 8 (full-record wipe)
  requires bespoke recorder surgery either way.
- Con: Couples the examples CI job (currently `.[dev,arrow]`, no cassettes)
  to the graph extra and the cassette tree, putting two CI jobs on the
  corpus instead of one.

### 2.2 Option B: Example test inside the conformance suite (recommended)

**Pattern:** A new `tests/backends/conformance/test_examples.py` with one
test, parametrized over two ids chosen to match the fixture-alias tokens:

```python
pytest.importorskip("httpx", reason="httpx not installed (graph extra)")
pytest.importorskip("msal", reason="msal not installed (graph extra)")

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
    assert "revenue,profit" in out  # demonstrated content, not just banners
    assert "Cleaned up all example files." in out
    assert "Done!" in out
```

`_StubGraphAuth` accepts the example's constructor arguments and returns a
constant token, mirroring `graph_replay`. `runpy.run_path(...,
run_name="__main__")` executes the script exactly as a user does
(module-level env gate, `asyncio.run(main())`, `sys.exit` paths included),
which a plain `import` + `await main()` would not.

Two details exist for review-identified reasons. The module-level
`importorskip`s mirror the fixture factories' ImportError-to-skip conversion
(`graph_replay._factory`, `graph_live._factory`): without the graph extra,
`remote_store.aio` has no `GraphAuth` attribute to monkeypatch and the
example's import raises, so both params would hard-fail in an environment
the conformance suite deliberately passes in. The `revenue,profit`
assertion pins one line of demonstrated content: the banner lines alone
would pass even if `read_bytes` handed back foreign bytes, which is the
failure mode constraint 2 describes and the § 1.2 guard exists to catch.

By constraint 7, the param ids buy the whole stack: cassette-dir routing,
the shared cassette name (`test_graph_backend_example[graph].yaml`), the
`GRAPH_PROFILE` record/replay configs, the missing-cassette skip (which
keeps the replay param inert until the cassette lands, here in the very
next live session), and `--record`-mode marking of the live param. By
constraint 8's own mechanism, `record_cassettes.py` needs **zero changes**:
the `-k graph_live` sweep records the example cassette alongside the
conformance corpus, scrub-verifies it, and replays it; a full `record-graph`
regenerates it instead of orphaning it (`min_cassettes=100` keeps headroom).

**Trade-offs:**

- Pro: Single source of truth for record/replay/scrub/skip; the example
  becomes one more cassette consumer, exactly the BK-283 framing.
- Pro: Replay runs in the normal Stage-1 sweep (`hatch run all`, CI test
  jobs), so the snippet is exercised on every push, not only in the
  examples job.
- Pro: stdout assertions upgrade the example from "no crash" to
  output-verified, the Go-`Example` posture
  [research-example-testing.md](research-example-testing.md) recommended.
- Con: Diverges from the backlog sketch's `run_examples.py` wiring. The
  sketch is advisory (CLAUDE.md audit-disposition rule); the diagnosed pain
  — no CI coverage for the snippet — is resolved with less machinery.
  `run_examples.py` keeps its credential-free scope; its docstring gains one
  pointer line.
- Con: A test about an example under `tests/backends/conformance/` stretches
  the dir's name. Accepted: the placement is what makes the machinery reuse
  free; the module docstring states the rationale.

### 2.3 Option C: Make the example replay-aware itself

**Pattern:** Teach the example a replay mode (env switch selecting a stub
token provider) so it runs under a thin vcr wrapper anywhere.

**Trade-offs:**

- Pro: No auth monkeypatching.
- Con: Test scaffolding leaks into published documentation: the example is
  rendered verbatim into the docs site, and its entire job is to show the
  real auth flow. Rejected.

### 2.4 Option D: respx fake API instead of a cassette

**Pattern:** Since the test is an executable-documentation guard (§ 1.2),
replay fidelity is arguably negotiable: run the script under a respx route
table faking the Graph API (the boundary the graph unit tests stub), with
Option B's env/auth stubbing. No cassette, no live session ever needed.

**Trade-offs:**

- Pro: Zero recording dependency, implementable in a creds-free session;
  immune to the full-record wipe (constraint 8) and pre-signed
  order-dependence (constraint 10).
- Con: The example's op sequence (write ×2, read, metadata, recursive list,
  copy, move, exists ×2, streaming read, delete sweep) needs a stateful
  hand-written fake of a dozen Graph endpoints including the pre-signed
  download redirect: a second, drifting model of the Graph API, precisely
  what BK-262 built the recording pipeline to avoid. The unit tests keep
  respx honest by scoping each route table to one narrow contract; a
  whole-script fake cannot.

The same verdict covers synthesizing the example's cassette offline from
conformance interactions used as templates: response fields are internally
entangled (size, eTag, hash, pre-signed ordering), so that is a
hand-maintained fake in cassette format, and it breaks the BK-262 invariant
that every committed cassette is a scrub-verified recording of real traffic,
which the PII gates assume.

Rejected for the guard, but it is the fallback if the live tier ever becomes
unrecordable: the guard degrades gracefully to a fake because nothing in it
asserts backend semantics.

---

## 3. Evaluation

| Criterion | A: run_examples driver | B: conformance test | C: replay-aware example | D: respx fake API |
|-----------|------------------------|---------------------|--------------------------|-------------------|
| Reuses spec-049 machinery | partial (config only) | full | partial | — |
| Recorder integration | bespoke | zero changes | bespoke | — (no cassette) |
| Survives full `record-graph` wipe | needs recorder surgery | automatic | needs recorder surgery | immune |
| Needs a live session once | yes | yes | yes | no |
| API fidelity | recorded | recorded | recorded | hand-maintained fake |
| Example file untouched | yes | yes | no | yes |
| Output verified | exit code only | stdout assertions | exit code only | stdout assertions |
| New code surface | driver + runner table | one test module | example churn | test module + fake API model |

Option B dominates A and C on every criterion except fidelity to the
original sketch. Against D the trade is one live recording session versus a
permanently hand-maintained fake of a dozen stateful endpoints; B wins on
maintenance, D remains the documented fallback (§ 2.4).

### 3.1 Generalisation: which live backends can the pattern reach?

Bounded by
[TEST-008](../specs/048-testing-architecture.md#test-008-replay-scope-is-http-transport-only):
replay scope is HTTP transport only, and within that, only stacks vcrpy can
intercept.

| Backend example | Transport | Replay-example feasible? | Worth it? |
|---|---|---|---|
| `graph_backend.py` | httpx (vcrpy-proven) | yes: this design | yes: no emulator; only creds-free path |
| `azure_backend.py` | azure.core/requests (BK-181 PoC) | yes: same pattern over `AZURE_PROFILE` | low: Azurite-driven CI is simpler than a cassette |
| `s3_backend.py`, `s3_*.py` | aiobotocore via s3fs | no: vcrpy cannot intercept ([BK-181 spike](research-bk-181-s3-cassette-infeasibility.md)) | moto/MinIO are the right tools |
| `sftp_backend.py` | SSH (paramiko) | no: not HTTP | Docker sftp fixture territory |
| `sql_blob_backend.py` | DB driver | no: not HTTP | SQLite/local DB runs without creds |
| `http_backend.py` | httpx | technically yes | unnecessary: any local HTTP server suffices |

The honest generalisation is narrow: the pattern earns its keep exactly
where a live HTTP service has no emulator. Today that is Graph alone. The
test module stays a plain parametrized test, not a registration framework;
if a second example ever joins, factor the stub pairs into a table then,
not before.

---

## 4. Recommendation

Implement Option B in a live-credential session: one new test module under
`tests/backends/conformance/`, one recorded cassette, zero changes to
`record_cassettes.py` or the conformance conftest. Effort matches the
backlog's S estimate. The BK-283 body's `run_examples.py` wiring is
superseded (sketches are advisory, and the Stage-1 replay test fully
resolves the diagnosed pain of no CI coverage for the snippet). Frame it
honestly when closing the item: the test guards the published snippet, it
does not extend backend coverage (§ 1.2). If the live tier ever becomes
unrecordable, degrade to the respx fallback (§ 2.4) rather than letting the
guard rot behind a permanent missing-cassette skip.

Plan for the implementing session:

1. **Add `tests/backends/conformance/test_examples.py`** as sketched in
   § 2.2, with a module docstring covering the param-id routing trick, the
   `run_examples.py` division of labour, and the § 1.2 framing.
2. **Live-param hygiene:** before and after the live run, best-effort delete
   the drive's `remote-store-example` folder via an unrooted helper backend
   (mirror `graph_live._aclose`'s teardown). The example cleans its files
   but leaves empty folders; pre-cleaning keeps re-records deterministic.
3. **Record:** a single-cassette `record_cassettes.py --backend graph
   --node ...[graph_live]` run, or a full `hatch run record-graph` (which
   now includes the example). Scrub-verify + Stage-1 replay run unchanged.
4. **Verify replay** (principle 6): `pytest tests/backends/conformance/
   -k graph_replay --stage=1` green including the new test; then the full
   `hatch run all` gate.
5. **Ripples** (pre-checked against `sdd/CLAUDE-REFERENCE.md`; no backend,
   error, capability, version, or dependency surface changes):
   `run_examples.py` docstring pointer; close BK-283 per the completing-work
   procedure (audience `infra.test`, so no CHANGELOG, per BK-262 precedent);
   trace `sdd/traces/bk-283-example-replay.yml` in the same PR. Spec 049
   needs no change (the test consumes existing REC surfaces); if review
   disagrees, the anchor is a one-line "consumers" note under REC-007.

Open verification points, cheap to confirm and listed so they are checked
rather than assumed:

- `--stage` does not deselect the new test (stage gating is
  registry-fixture-driven; this test is not registry-backed; confirm by
  collection at `--stage=1`).
- The cassette's MSAL token-exchange interactions stay inert under
  `record_mode="none"` with the stub auth (confirm on first replay).
- The `GraphAuth` monkeypatch lands before `runpy` executes the example's
  import (it does: the example binds the name at exec time), but assert
  the stub was actually called, e.g. via a call counter, so a silent
  fall-through to real MSAL fails loudly.
- `examples/_categories.yml` / docs rendering are unaffected (the example
  file is untouched; gen_pages parses it via `ast.parse`).
