# ADR-0043: Tiered per-PR CI gate, interpreter set by derivation

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | ADR-0032 |
| Superseded by | —        |
| Amends        | —        |

Builds on the Stage model of
[ADR-0028](0028-testing-architecture-kind-stage-replay.md), exactly as
ADR-0032 did. See spec [048 § TEST-006](../specs/048-testing-architecture.md)
for the CI mapping and `sdd/CI-OPERATIONS.md` for the runbook.

## Context

[ADR-0032](0032-tiered-ci-gate-with-full-matrix-backstop.md) split the per-PR
gate by test tier and moved the full per-interpreter live suite to a
`ci-full.yml` backstop. Its measurements are the evidence for this decision too
and are not repeated here: the 20-concurrent-job cap, xdist oversubscription
buying nothing, sharding re-paying live-backend setup, and call-time durations
mis-balancing shards.

Its Decision also **named the interpreters**, both as the full set and as the
non-primary list. The decision never depended on which versions those were. So
the record went stale at the first change to the supported set, and an Accepted
ADR cannot be edited ([`000-process.md` Rule 4](../000-process.md#rules)).
Dropping Python 3.10 (BK-380) was that change. This record restates the same
decision with the set named by where it is derived, so the next change to the
roster owes no new ADR.

## Decision

The per-PR gate is split by **test tier**, and the full per-interpreter live
guarantee runs as a scheduled/on-master backstop. Interpreters are named by role,
never by version. The **primary** interpreter is `.python-version`. The
**supported set** is `ci.yml`'s `ALL_PYTHONS`, held equal to `ci-full.yml`'s
matrix by `check_ci_full_matrix.py`, and its roster is governed by the
`pyproject.toml` classifiers ([ADR-0039](0039-support-tracks-upstream-security-fixes.md)).

- **Primary interpreter: full fidelity per PR.** `test-primary` runs the
  live-backend Stage-2 pass-1, `pytest-split`-sharded (`least_duration`) over a
  setup-inclusive `.test_durations_pass1` (`scripts/gen_split_durations.py`).
  `test-primary-sftp` runs the serial `sftp_docker` conformance, and
  `coverage-gate` combines the shard partials and asserts the **95 % floor**.
  The interpreter-independent `TestCommittedCassettePIISweep` scans run once, in
  `test-cassette-pii`.
- **Every other supported interpreter: Stage 1 per PR.** The `test` matrix
  (`ALL_PYTHONS` minus the primary) runs the repo-only tier, sharded, so
  interpreter-specific breakage still blocks the PR.
- **`ci-full.yml`: full-matrix backstop.** The complete two-pass live-backend
  suite runs on **every** supported interpreter, nightly and on every push to
  master.

**The guarantee tradeoff (owner-approved, unchanged from ADR-0032):** a
regression that appears *only* on a non-primary interpreter *against a live
backend* is caught by `ci-full` after merge, not on the PR. Every other
guarantee still gates each PR.

*Reverse if* that tradeoff lets such a regression reach a release, or the
account gains merge-queue or larger-runner capacity.

## Consequences

- **What changes from ADR-0032 is the wording, not the gate.** Workflows,
  shards, the coverage floor and the backstop are as before. Changing the
  supported set now touches the spellings the ripple-check's **Supported
  interpreter set** row enumerates, and no ADR.
- **Unchanged duties:** `.test_durations_pass1` needs periodic refresh, and a
  release manager confirms the `ci-full.yml` run as well as `ci.yml`.
- ADR-0032's per-PR wall-clock and coverage figures were measured on the
  five-interpreter matrix it named. They are its evidence, not a claim about
  today's matrix, and none is restated here.
