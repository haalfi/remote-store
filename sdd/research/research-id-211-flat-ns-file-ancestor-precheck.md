# Research: ID-211 — HEAD pre-check for flat-namespace backends

**Item ID:** ID-211
**Date:** 2026-05-26
**Predecessor:** ID-209 (PR #680, merged)
**Status:** Implemented per disposition (b) — opt-in `reject_write_under_file_ancestor` kwarg on flat-NS backends.

---

## 1. Question

ID-209 landed a cross-backend conformance gate that
`write` / `write_atomic` / `open_atomic` / `move` / `copy` MUST raise
`InvalidPath` when a slash-aligned ancestor of the destination path is
a regular file (BE-008 / BE-018 / BE-019). Hierarchical backends
(Local, SFTP, Memory) enforce this via their native
`parent.mkdir(parents=True)` / `sftp.mkdir` / `EnsureParents` walks.
Flat-namespace backends (S3, Azure non-HNS, SQLBlob, HTTP) cannot
detect the case in O(1) — they need an extra round trip per
slash-aligned ancestor to HEAD whether the ancestor exists as a file.
ID-209 carved them out via `_skip_flat_namespace` on the new
conformance tests; ID-211 follows up to decide whether the optional
HEAD pre-check is worth shipping.

The user's nominated optimisation: a path with no slash has no
ancestor to check, so skipping the gate on no-slash paths collapses
the cost to nested-path writes only. Most writes against a backend
target the store root (no slash), so the worst-case cost is paid only
when the caller deliberately writes into a nested subtree.

Three dispositions to evaluate:

* **(a) Ship unconditional.** Tighten the contract for every flat-NS
  backend. Every nested-path write pays the HEAD walk; no-slash writes
  are free.
* **(b) Ship as an opt-in client kwarg** (e.g.
  `reject_write_under_file_ancestor: bool = False` on each flat-NS
  backend constructor). Default off; users who care pay for the
  contract.
* **(c) Carve-out stays.** Close ID-211 with the measurement, update
  spec 003 BE-008 prose to cite this note in place of "tracked under
  ID-211", and leave the conformance gate skipping on flat-NS
  fixtures.

## 2. Method

Harness: `sdd/research/research-id-211-flat-ns-file-ancestor-precheck.py`.
For each backend in scope and each path depth in `{0, 1, 3, 6}`, time
100 `write(path, 1024 bytes)` calls (after 10 discarded warmups)
under two variants:

* **`baseline`** — existing production `write()` only.
* **`precheck`** — the proposed `_check_no_file_ancestor` walk
  (one `HEAD` per slash-aligned ancestor, with the no-slash early
  exit) followed by the existing `write()`.

In the harness every ancestor is absent, so the walk runs to
completion on every nested-path write. That is the worst case — a real
`InvalidPath` hit would short circuit on the first file ancestor —
and the published numbers are an upper bound on the per-call cost.

The fixture wraps the same production code paths the conformance
suite drives (`S3Backend(endpoint_url=moto)`, `SQLBlobBackend(url=
"sqlite:///:memory:")`). Azurite would have rounded out the Stage-1
matrix; this environment has no Docker daemon, so it self-skipped.
Real-cloud (S3 live + Azure ADLS live) is out of scope for the
Stage-1 measurement — its per-HEAD latency is bounded by network
RTT, and the same depth-vs-cost shape from the in-process numbers
extrapolates linearly to whatever the user's account RTT looks like.

## 3. Measurement results

Each row: 100 writes of a 1 KiB payload after 10 discarded warmups.
"Backend" is the production write path wrapped in the harness.

In `precheck`, no ancestor exists, so every slash-aligned ancestor
HEAD runs to completion. A real `InvalidPath` hit short circuits on
the first file ancestor, so these numbers are the upper bound on the
gate's per-call cost.

### s3_moto (in-process moto HTTP server, no network RTT)

| depth | variant  | P50 (ms) | P95 (ms) | P99 (ms) | mean (ms) | overhead vs baseline (mean) |
| ----- | -------- | -------- | -------- | -------- | --------- | --------------------------- |
|     0 | baseline |   17.382 |   27.718 |   29.421 |    18.737 | —                           |
|     0 | precheck |   17.306 |   18.991 |   28.655 |    17.763 | -0.974 ms (-5.2%)           |
|     1 | baseline |   17.396 |   27.362 |   60.191 |    18.522 | —                           |
|     1 | precheck |   21.558 |   30.736 |   32.946 |    22.127 | +3.605 ms (+19.5%)          |
|     3 | baseline |   17.598 |   27.833 |   28.911 |    18.590 | —                           |
|     3 | precheck |   29.776 |   40.107 |   41.642 |    30.893 | +12.303 ms (+66.2%)         |
|     6 | baseline |   18.346 |   28.484 |   29.249 |    19.550 | —                           |
|     6 | precheck |   41.718 |   52.136 |   95.700 |    43.523 | +23.973 ms (+122.6%)        |

### sqlblob_sqlite (in-memory SQLite, no network RTT)

| depth | variant  | P50 (ms) | P95 (ms) | P99 (ms) | mean (ms) | overhead vs baseline (mean) |
| ----- | -------- | -------- | -------- | -------- | --------- | --------------------------- |
|     0 | baseline |    0.300 |    0.448 |    0.537 |     0.315 | —                           |
|     0 | precheck |    0.296 |    0.397 |    0.827 |     0.311 | -0.005 ms (-1.5%)           |
|     1 | baseline |    0.291 |    0.341 |    0.380 |     0.295 | —                           |
|     1 | precheck |    0.458 |    0.574 |    0.617 |     0.469 | +0.175 ms (+59.4%)          |
|     3 | baseline |    0.326 |    0.443 |    0.504 |     0.337 | —                           |
|     3 | precheck |    0.722 |    0.930 |    1.032 |     0.746 | +0.408 ms (+121.0%)         |
|     6 | baseline |    0.298 |    0.390 |    0.406 |     0.306 | —                           |
|     6 | precheck |    1.057 |    1.188 |    1.320 |     1.069 | +0.763 ms (+249.0%)         |

### azurite (Azure non-HNS via Docker emulator)

Not measured: this environment has no Docker daemon, so the
`azurite` factory self-skipped on the unreachable `127.0.0.1:10000`
probe. The shape will mirror `s3_moto` (one HEAD per ancestor against
a local HTTP server); the absolute numbers depend on Azurite's
per-request overhead, which is in the same order of magnitude as
moto's. Re-run the harness with `--include azurite` once Docker is
up if the disposition turns on Azurite-specific numbers.

## 4. Interpretation

Two things stand out:

### 4.1 The no-slash early exit is essentially free

`depth=0` precheck overhead is within noise on both backends:
`-0.974 ms (-5.2%)` on `s3_moto` and `-0.005 ms (-1.5%)` on
`sqlblob_sqlite`. The negative signs are jitter, not a speedup. The
user's "skip the check when there are no slash segments" optimisation
collapses the gate cost to **zero** on store-root writes, regardless
of backend. Any disposition that includes it pays nothing for the
most common write shape.

### 4.2 On nested-path writes, the cost is linear in depth and meaningful

On `s3_moto`, where the HEAD round trip is purely local-process HTTP
and so the floor on per-HEAD cost, the precheck adds:

* depth 1: +3.6 ms mean (+19.5%) — roughly one extra HEAD on a 17 ms
  baseline.
* depth 3: +12.3 ms mean (+66.2%) — three extra HEADs.
* depth 6: +24.0 ms mean (+122.6%) — six extra HEADs; **more than
  doubles** the write wall time.

The per-HEAD increment is ~4 ms on moto. Real S3 typically runs at
5–50 ms per HEAD against a regional endpoint; depth-6 nested writes
against live S3 would land in the +30–300 ms band per write. The
proportional cost on real S3 stays similar because the baseline write
RTT scales with per-call latency in lockstep with the per-HEAD RTT.

`sqlblob_sqlite` shows the same depth-linear shape with sub-millisecond
absolute numbers (+0.76 ms at depth 6). On a real SQL backend served
over a network the per-`SELECT` RTT lifts the absolute cost into the
same range as S3.

### 4.3 The pre-check has a behavioural side effect worth flagging

The HEAD walk introduces N extra control-plane calls per write that
the user did not request. Each one is a request the user pays for
under per-request cloud pricing (S3 `HEAD Object` ≈ $0.0004/1k), and
each one can fail in ways the user has to reason about: rate-limit
throttling on the parent prefix, a non-`NotFound` `4xx` from the
provider, transient connectivity. Today the only way `write()` fails
on flat-NS backends is the write itself; under disposition (a), every
write inherits the failure modes of N HEADs.

## 5. Discussion

### 5.1 Why (a) is hard to recommend

The contract value at the boundary is real: a caller that writes
`a/b/c.txt` after `write("a/b", b"file")` lands a key whose ancestor
is a file and breaks the well-formedness invariant we care about
enough to encode in the Dafny `Valid()` predicate. Hierarchical
backends close this loophole automatically; flat-NS backends today
let it through. Disposition (a) shrinks the cross-backend contract
divergence, which is its appeal.

The cost case against it is the table above. A 2× wall-time tax on
deep-nested writes is meaningful on hot paths. Worse, it is paid by
every caller regardless of whether they are actually at risk of the
ancestor-as-file shape — most callers never write to a path whose
ancestor they have separately written as a file, and the gate is pure
overhead for them. The behavioural side effect (5.4 below) further
shifts the cost-benefit against (a).

The well-formedness invariant the gate enforces is *latent*: a
caller who writes `a/b` as a file and then `a/b/c.txt` ends up with
listings that already self-protect via the ID-184
`!AllAncestorsTraversable ==> []` clause. The fs corruption is real
but bounded — listings hide the orphaned key, reads return `NotFound`,
and the offending path is unreachable through normal traversal. The
gate's defence is against a caller who is willing to lose data this
way being told `InvalidPath` instead. Useful, but the wall-time tax
on every other caller does not feel worth it.

### 5.2 (b) opt-in: a path through the cost-benefit

`AzureBackend(..., reject_write_under_file_ancestor=True)` (and
analogous on S3 / SQLBlob) opens the contract to callers who want it
without taxing those who don't. The trade is added public API surface
on three backends, a new fixture variant per backend to exercise the
opt-in path, and a small carve-out in spec 003 BE-008 prose noting
the kwarg.

The audience for the opt-in is narrow: a user who genuinely cares
about cross-backend `InvalidPath` consistency on flat-NS backends.
Realistically that audience is "the project maintainers using
remote-store as a substrate for a layered system that depends on the
contract" — i.e. a thin slice. Most users get no value from the
kwarg; flagging it as a flat-NS-only foot-gun in the API reference
also costs them attention budget.

The opt-in shape also raises a per-backend coupling question: if a
user opts in on S3 but not Azure within the same application, the
contract becomes per-instance rather than per-call. That is workable
but new in the public API.

### 5.3 (c) keep the carve-out: matches the measured cost-benefit

The status quo is honest: the spec calls out the exemption explicitly,
the conformance gate skips per-fixture, and ID-184's listings layer
already hides the orphaned-key state from any traversal. Closing
ID-211 with the measurement, the research note, and a small spec
prose update (drop the "ID-211 tracks the optional HEAD pre-check
follow-up" placeholder; cite the research note as the resolved
disposition) leaves the contract divergence as documented behaviour
rather than an open follow-up.

This loses the cross-backend contract tightening on flat-NS
backends, which is a real loss. It is hard to argue the gain is
worth the wall-time tax measured above, and the gain is reachable
via (b) later if a user reports the divergence.

### 5.4 Architectural alternatives the measurement informs

* **Move the gate into the user-facing `Store` rather than each
  `Backend`.** `Store.write` could opt-in to the gate via a Store
  config flag and call `backend.exists(ancestor)` itself, mirroring
  the pattern in 5.2 without forcing each backend to carry the
  kwarg. Same cost profile, smaller public-API surface.
* **Use `head_object` directly rather than `_fs.exists`.** s3fs's
  `exists()` does `HEAD + LIST` to disambiguate "object" from
  "prefix"; for the file-ancestor check we only care about the HEAD
  branch. A `head_object`-only walk would halve the per-ancestor cost
  on S3. The harness already calls `head_object` directly, so the
  numbers above are the optimal-walk floor.
* **Batch the check on SQL backends.** `WHERE key IN (ancestors)` is
  one round trip regardless of depth. Worth doing if disposition (a)
  or (b) lands on SQL. Out of scope for S3/Azure (no batch HEAD).

## 6. Disposition that landed

After the measurement was in hand, the user chose **disposition (b)**:
ship the pre-check as an opt-in client kwarg on each flat-NS backend.
The reasoning: the cost is meaningful at depth and most callers will
not opt in, but the contract value at the boundary is real for the
callers who care, and the no-slash early exit makes default-off a
near-zero ongoing cost. (c) was the closest runner-up; the deciding
factor is that (b) makes the contract reachable without forcing the
tax on everyone, and the opt-in surface is small enough to absorb.

What landed:

1. New shared helper `src/remote_store/backends/_flat_ns.py` exports
   `_check_no_file_ancestor` (sync) and `_acheck_no_file_ancestor`
   (async). Both walk the slash-aligned ancestor chain via a
   caller-supplied `head_one` callable; both short-circuit on no-slash
   paths.
2. `S3Backend`, `S3PyArrowBackend`, `AzureBackend`, `SQLBlobBackend`,
   and `AsyncAzureBackend` gained a
   `reject_write_under_file_ancestor: bool = False` constructor kwarg;
   each constructs a backend-specific `head_one` (`head_object` for S3,
   `get_blob_properties` for Azure non-HNS, `SELECT 1` for SQLBlob)
   and threads it through `write` / `write_atomic` / `open_atomic` /
   `move` / `copy`. Azure HNS short-circuits the opt-in walk because
   `hdi_isfolder` already enforces the contract.
3. New `*_strict` fixtures (`s3_moto_strict`, `s3_pyarrow_moto_strict`,
   `sqlblob_strict`, `azurite_strict`) wire the kwarg on. The existing
   default-off fixtures keep their behaviour.
4. `BackendFixture.rejects_write_under_file_ancestor` is the new
   per-fixture flag, defaulting to `not flat_namespace` so hierarchical
   backends keep their native enforcement. The conformance test
   `test_write_under_file_ancestor_raises_invalid_path` (and its
   move/copy sibling, plus the async equivalents) now skip via
   `_skip_unless_rejects_file_ancestor` instead of
   `_skip_flat_namespace` — strict fixtures run the gate.
5. Spec 003 § BE-008 / BE-018 / BE-019 and spec 029 § ASYNC-008 /
   ASYNC-010 / ASYNC-018 / ASYNC-019 carry the new prose.
6. `CHANGELOG.md` lists the kwarg under `Added`.

The Trace `audience` reflects the user-facing addition: `user.api`
(the kwarg is part of every flat-NS backend's public constructor),
`library.maintainer` (the spec/test plumbing), and
`contributor.process` (BACKLOG hygiene).

## 7. Reproducibility

* Harness: `sdd/research/research-id-211-flat-ns-file-ancestor-precheck.py`.
* Run: `hatch run python sdd/research/research-id-211-flat-ns-file-ancestor-precheck.py`.
* Output table: `sdd/research/research-id-211-results.md` (regenerated
  on every run).
* Stage-1 bootstrap: in-process `ThreadedMotoServer` for S3, in-memory
  SQLite for SQLBlob. Azurite self-skips when 127.0.0.1:10000 is
  unreachable. No live cloud creds required.

If the disposition is revisited later under real-cloud RTT
constraints, rerun with `--include azurite` after starting Docker
(`docker compose -f infra/docker-compose.yml up -d azurite`) and
extend the harness with a live-S3 / live-Azure factory keyed on
`RS_TEST_LIVE_*`.
