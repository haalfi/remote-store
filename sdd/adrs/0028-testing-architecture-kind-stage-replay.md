# ADR-0028: Testing Architecture with Kind and Stage Axes and HTTP Replay Demotion

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

The repository has not had a dedicated testing-architecture decision
record. The de facto state lives in [`sdd/TESTING.md`](../TESTING.md)
(quality rules and a placement table) and in `tests/backends/conftest.py`
(the parametrize that wires backends into conformance). That is enough
when every backend can be exercised by a local fixture or a Docker
emulator, but the recent extension of test coverage to a real cloud
account exposed structural problems the implicit design cannot resolve.

Three forces are in play.

The first is fidelity. Local emulators silently accept inputs the real
service rejects. A conformance suite parametrised over an emulator
gives no signal on the code paths the real account would exercise. For
some backends, only a live account can validate the contract.

The second is duplication. When real-cloud tests are added next to
emulator-backed conformance, the live file recreates contracts the
conformance suite already enforces, only against a different account.
Each new contract added to conformance has to be re-added in the live
file, or its real-cloud coverage stays at zero. The cost grows with
every contract.

The third is asymmetry. A test that needed a live account to discover a
behaviour has no way to re-run cheaply. Either the cost-controlled tier
is paid forever or the cheap tier cannot enforce what the costly tier
taught. There is currently no demotion path between the tiers.

[BK-175](../BACKLOG-DONE.md) named the architectural debt and asked for
an RFC covering parametrised conformance plus a record/replay layer.
Two clarifications during the design phase shaped the scope. The shape
applies to every backend, not only the one that surfaced it. And the
replay mechanism is honest only for HTTP-transport backends; protocols
that ride on SSH or DB wire formats are not reachable by HTTP capture
tools without a custom transport adapter.

## Decision

<!-- adr:decision -->
The testing architecture rests on five coupled commitments:

1. **Two orthogonal axes** — separate *kind* (pure, mocked, real-local, real-live) from *stage* (1/2/3 by cost); a fixture declares one of each.
2. **Conformance as the cross-backend spine** — one parametrised suite over the public `Store` / `Backend` API that every backend runs; backend-specific behaviour is isolated per backend.
3. **HTTP cassette + replay as a Stage 1 fixture** — a `<backend>_replay` fixture runs the real SDK path against a recorded cassette (Stage 3 records, Stage 1 replays); scoped to HTTP-transport backends only.
4. **Capability gating via native pytest** — parametrize id-filtering plus `pytest.mark.skipif`, no custom `@requires` marker layer.
5. **Explicit cassette refresh** — cassettes regenerate only when a developer runs `pytest --stage=3 --record` and commits the diff; CI never silently re-records.
<!-- /adr:decision -->

They share rationale: the demotion mechanism only works because the axes are
separated, the gate works only because gating is native, and the scope works
only because the spec calls out where it does not apply. One ADR captures the
bundle; any commitment that later evolves can be superseded individually.

### Two orthogonal axes: kind and stage

A linear list of "stages" running unit, emulator, live collapses two
distinct concerns. *What the test wires up* is one axis (kind: pure,
mocked, real-local, real-live). *How expensive it is to run* is
another (stage: 1, 2, 3, ordered by cost and required infrastructure).
The architecture separates them. A fixture declares one of each. Spec
contracts in [spec 048](../specs/048-testing-architecture.md) TEST-001.

A linear collapse hides real options. Replay is a real-SDK code path
that runs at Stage 1 cost; a single-axis ordering cannot express that
combination.

### Conformance as the cross-backend spine; backend-specific tests isolated per backend

Conformance is one parametrised test set referencing only the public
`Store` and `Backend` API. Every backend that exposes the API runs
the full suite. Behaviour that only one backend exhibits, whether
protocol quirks, storage-model semantics, or vendor configuration, is
isolated to that backend's own home, separate from the spine.

Two consequences follow at once. "Add a backend, get conformance for
free" becomes the literal mechanism. And backend-specific tests gain
a home that is not interleaved with the cross-backend suite. Spec
contracts in TEST-002 and TEST-003. Layout in TEST-010.

### HTTP cassette and replay as a Stage 1 fixture, scoped to HTTP backends

A `<backend>_replay` Stage 1 fixture exercises the real SDK code path
with the HTTP transport stubbed by a recorded cassette. Stage 3 runs
record. Stage 1 runs replay. A Stage-3-discovered behaviour, once
recorded, runs at zero cost in every default CI run. That is the
demotion mechanism the third force in the Context describes.

The mechanism applies to HTTP-transport backends only. Backends that
speak SSH binary or a DB wire protocol are not reachable by available
capture tools without a custom transport adapter, and that work is not
in scope here. For excluded backends, Stage 2 (Docker) is the cheapest
source of truth, with no Stage 3 to Stage 1 demotion path until and
unless dedicated work delivers one. Spec contracts in TEST-007 and
TEST-008.

### Capability gating uses native pytest mechanisms

Conformance tests gate on cross-backend `Capability` values via
parametrize id-filtering and `pytest.mark.skipif`. No `@requires(...)`
custom marker layer is introduced. A reader can trace from the
parametrize call to the fixture registry without indirection or a
plugin hook.

The cost paid is verbosity in a few helper functions. The cost avoided
is a parallel marker system that needs its own conftest hook,
documentation, and IDE-tooling integration. Spec contracts in
TEST-005.

### Cassette refresh is explicit

Cassettes regenerate when a developer runs `pytest --stage=3 --record`
and commits the diff. CI does not silently re-record. The refresh is
auditable as a normal PR. Drift between cassettes and real-service
responses is detected by the next manual refresh. A scheduled refresh
job is schedulable later if drift becomes painful. The reverse default,
scheduling from day one, couples the cost-controlled tier to a recurring
job before any empirical drift data exists. Spec contracts in TEST-009.

## Consequences

Adding a backend that satisfies the `Backend` or `AsyncBackend` ABC
and registers a fixture extends conformance coverage without
rewriting any test.

Bug fixes for behaviour that is only observable on a real account
land in the affected backend's own home, against the live fixture
(authoritative) and the replay fixture (regression guard). The
hand-written live file shrinks to behaviour that conformance cannot
express. The duplicated cases are deleted.

Stage 1 CI exercises real SDK pipelines for HTTP backends at zero cost
and zero credentials, via cassettes. Contributors without cloud
accounts can run the full default suite.

Stage 3 runs require deliberate opt-in. Cost stays under developer
control. CI cost stays at zero unless a scheduled job is added later.

The HTTP-only replay scope is a real limitation. Contracts validated
only at Stage 2 for SSH or non-SQLite SQL backends cannot be re-run
more cheaply. The limitation is documented up front rather than
discovered at implementation time.

Sync and async fixtures share the conformance tree. Per-backend `aio/`
carve-outs exist only where sync and async semantics genuinely diverge,
not as a default mirror.

The fixture registry centralises stage, kind, capability, and factory
metadata. Per-test stage and capability questions become registry
queries rather than ad-hoc imports.

## Alternatives considered

**Single linear stage list.** Rejected. Collapses kind and stage into
one axis. Replay (real-SDK code path at Stage 1 cost) cannot be
expressed without violating a single-axis ordering.

**Custom `@requires(Capability.X)` marker layer.** Rejected. Requires
a conftest hook, parallel skip mechanism, and per-CI documentation for
the marker. Native `pytest.mark.skipif` plus parametrize-filter deliver
the same gating with no plugin surface.

**Universal replay (record SSH and DB wire protocols).** Rejected for
this iteration. Feasible only via custom transport adapters per
protocol. Cost per backend exceeds the value at this stage. Revisit if
a specific backend's Stage 3 cost or unavailability justifies the
investment.

**Scheduled cassette refresh in CI.** Rejected as the default. Couples
the cost-controlled tier to a recurring job before empirical drift data
exists. Schedulable later as an additive change.

**Capability declared on tests rather than fixtures.** Rejected. Pushes
backend awareness into every test. Declaring on fixtures keeps tests
backend-agnostic and lets a new fixture inherit the correct test
inclusion automatically.

**Bundle all backend tests in one tree without a dedicated
cross-backend conformance subtree.** Rejected. Keeps the duplication
problem. Without a separate enforced home for cross-backend
conformance, the rule that conformance is parametrised across
backends has no anchor, and re-derivation under deadline pressure is
the path of least resistance.
