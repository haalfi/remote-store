# Test tree — orientation
<!-- doc: repo-only -->

You are in the pytest suite. This page is a signpost, not a rulebook: it points
at the authority for each kind of test question.

| I need to… | Go to |
|---|---|
| Run a stage, a live-cloud test, or record/refresh cassettes | [`sdd/TESTING-RUNBOOK.md`](../sdd/TESTING-RUNBOOK.md) — the operational commands |
| Know the test **quality** rules and where a test file belongs | [`sdd/TESTING.md`](../sdd/TESTING.md) |
| Understand the test **architecture** (kind × stage × replay, fixture registry) | [spec 048](../sdd/specs/048-testing-architecture.md) |
| Understand cassette **recording/redaction** internals | [spec 049](../sdd/specs/049-live-recording-architecture.md) |
| Work on the **async** test tree | [`tests/aio/README.md`](aio/README.md) |

Quick start: `hatch run test-cov-s1` runs the no-Docker Stage 1 suite. `hatch
run all` is the pre-commit gate. See the runbook for stages 2 and 3.
