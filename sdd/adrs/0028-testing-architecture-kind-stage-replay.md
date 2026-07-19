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

The testing architecture rests on five coupled commitments. They share one
rationale: the demotion mechanism works only because the axes are separated, the
gate works only because gating is native, and the scope holds only because the
spec calls out where it does not apply. One ADR captures the bundle; any
commitment that later evolves can be superseded individually. Spec contracts live
in [spec 048](../specs/048-testing-architecture.md).

- **Two orthogonal axes: kind and stage.** Separate *what a test wires up* (kind:
  pure, mocked, real-local, real-live) from *how expensive it is to run* (stage:
  1/2/3 by cost); a fixture declares one of each. A single linear stage list
  collapses the two and hides real options, notably replay: a real-SDK code path
  that runs at Stage 1 cost, which no single-axis ordering can express (TEST-001).
  *Reverse if* a single axis ever expresses every kind/cost combination in use.
- **Conformance as the cross-backend spine.** One parametrised suite over the
  public `Store` / `Backend` API that every backend runs, so "add a backend, get
  conformance for free" is the literal mechanism; backend-specific behaviour is
  isolated to that backend's own home, not interleaved with the spine (TEST-002,
  TEST-003, TEST-010). *Reverse if* the public API stops being a sufficient
  cross-backend contract.
- **HTTP cassette and replay as a Stage 1 fixture.** A `<backend>_replay` fixture
  runs the real SDK path against a recorded cassette (Stage 3 records, Stage 1
  replays), demoting a Stage-3-discovered behaviour to zero-cost CI. Scoped to
  HTTP-transport backends only: SSH-binary and DB-wire protocols are not reachable
  by available capture tools without a custom transport adapter, so their cheapest
  source of truth stays Stage 2 with no demotion path (TEST-007, TEST-008).
  *Reverse if* a capture mechanism for non-HTTP transports becomes worth its cost.
- **Capability gating via native pytest.** Parametrize id-filtering plus
  `pytest.mark.skipif`, with no custom `@requires` marker layer, so a reader
  traces from the parametrize call to the fixture registry without a plugin hook.
  The cost is verbosity in a few helpers; the cost avoided is a parallel marker
  system with its own conftest hook, docs, and IDE integration (TEST-005).
  *Reverse if* native gating can no longer express the capability matrix.
- **Explicit cassette refresh.** Cassettes regenerate only when a developer runs
  `pytest --stage=3 --record` and commits the diff; CI never silently re-records.
  Scheduling a refresh from day one would couple the cost-controlled tier to a
  recurring job before any empirical drift data exists; a scheduled job is
  additive later if drift becomes painful (TEST-009). *Reverse if* observed drift
  makes manual refresh unreliable.

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
