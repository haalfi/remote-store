# Audit 016 — Microsoft Graph Backend (ID-127) Review

**Backlog item:** — (ad-hoc multi-expert review of ID-127, post-merge; follow-ups proposed at the end)
**Date:** 2026-06-09
**Scope:** The complete Microsoft Graph / OneDrive / SharePoint backend delivered by
ID-127 (PRs #750–#769): `src/remote_store/aio/backends/_graph/` (~2,800 LOC across
`backend.py`, `http.py`, `transfer.py`, `monitor.py`, `items.py`, `auth.py`,
`utils.py`), its tests (~4,400 LOC under `tests/backends/graph/`), spec
`044-graph-backend.md`, `rfc-0010`, ADRs 0021–0024, the 13 ID-127 traces, the
user-facing guides/example, and the extension-ecosystem interactions.
**Method:** Five domain experts (Store/Backend, Testing, SDD, Documentation,
Extension) reviewed independently, each from a consumer-advocate stance, against
the spec as contract. Claims were cross-checked across experts and verified
against source. The live consumer-OneDrive API was exercised: the full live
conformance suite passes **109 passed / 0 failed / 9 skipped**. This is a
**report-only** audit — nothing was modified. Findings carry file:line and
spec-ID evidence; dispositions in the proposals section are advisory (the user
decides what becomes work).

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low / Nit.
Each finding tag (H1, M3, L7…) is referenced by the proposals table at the end.

---

## Summary

The backend is well-built where it counts: an honest capability declaration with
no over- or under-declaration, error classification that keys only on HTTP status
plus `error.code` (never message strings), a disciplined retry/resume design, and
a test tree with zero `MagicMock` (every boundary is `respx` or a hand-written
fake). The two material risks are orthogonal to that quality:

1. a **credential leak** — the pre-signed upload-session URL (carrying its own
   query credential) is embedded verbatim in a `ResourceLocked` exception
   message, enshrined by a passing test, while the sibling monitor path redacts
   the identical credential class. The root cause is a spec-internal
   contradiction (GR-045 vs GR-035/GR-026); and
2. **near-total absence of automated behavioural coverage in CI** — the
   cross-backend conformance matrix is 100% skipped for Graph (no committed
   cassettes) and the integration tier never runs in any CI lane, so the only
   automated guard is the respx unit suite, whose mocks (by ID-127's own
   experience) encoded shapes the real service contradicts.

The remaining findings are spec-lags-code accuracy gaps, documentation defects
(including a headline example that throws on copy-paste), and small correctness
edges.

---

## 🔴 High

### H1 — Pre-signed upload-session URL (credential) leaked into the `ResourceLocked` message

**Files:** `src/remote_store/aio/backends/_graph/transfer.py:487-501`
(`_resource_locked_mid_session`), reached from `transfer.py:426`;
test `tests/backends/graph/aio/test_write.py:520-537`.

On a `423` during an upload-session chunk PUT, the backend raises:

```python
return ResourceLocked(
    f"Resource locked during upload session (423): {path}. The session URL stays valid for "
    f"caller-driven resume — sessionUrl={session_url} nextExpectedRanges=[{ranges_text}].",
    ...)
```

`session_url` is the Graph `uploadUrl`. Per **GR-038** it "is pre-signed … and
carries its own credential in the query string"; the suite's own
`test_chunk_puts_are_unauthenticated_against_presigned_session`
(`test_write.py:416`) proves the URL itself authorises (chunk PUTs deliberately
omit `Authorization`). The test for this path **asserts the credential is
present**, with fixture `_UPLOAD_URL = "https://up.example.com/session/abc?tempauth=secret"`
(`test_write.py:43`):

```python
assert _UPLOAD_URL in str(exc.value)   # requires "?tempauth=secret" in the message
```

The copy/move **monitor** path treats the identical credential class as a secret
and strips it — `monitor.py:121-133` (`_redact_url`) query-strips, and
`test_monitor.py:232` asserts `"tempauth" not in msg`. The two pre-signed-URL
sites apply the masking rule inconsistently to the same threat.

**Consumer impact:** any caller that logs a caught `ResourceLocked` (the norm for
exception handlers, Sentry, crash reporters) exposes a live write/DELETE
credential valid for the session lifetime (hours, per GR-024). This defeats
**GR-035** ("token values never appear in exception messages … at any level").

**Root cause — a spec contradiction (escalated, see SDD findings):** **GR-045**
*mandates* embedding the session URL so callers can "resume without re-deriving";
**GR-035** + **GR-026** *forbid* tokens in messages. For the upload session the
credential **is** the resume handle, so the two cannot both hold: query-stripping
(GR-026's remedy) removes exactly the part that makes resume possible. Confirmed
independently by the Store/Backend, Testing, and SDD experts plus direct
re-verification of the test.

### H2 — Graph behavioural coverage is effectively absent in automated CI

**Evidence (run output and source):**

- `tests/backends/cassettes/graph/` contains **zero** committed cassettes (only
  `azure/` and a `.gitkeep` exist). Consequently `pytest tests/backends/conformance -k graph`
  (Stage-1, no live) reports **118 skipped, 0 passed** — every conformance slice
  skips with "replay cassette missing". This includes the two capability-honesty
  guards (`test_populated_field_implies_declared_capability[graph-*]`,
  `test_file_info_metadata_none_when_capability_absent[graph]`), which are
  therefore also inert.
- `scripts/record_cassettes.py:148` sets graph `"min_cassettes": 0`, and the
  guard at `:322` reads `min_expected = cfg.get("min_cassettes", 0)` — so a
  recording run that writes **zero** graph cassettes does not *fail* the gate. It
  does *warn*: `:329-337` prints a loud zero-cassette WARNING, but it is
  non-fatal, so an empty corpus still passes CI. The fix should promote that
  warning to a hard failure rather than add a redundant tripwire.
- The integration tier (`tests/backends/graph/aio/test_integration.py`,
  covering GR-007/019/020/026/034/054 + a 10 MiB round-trip) carries module-level
  `pytest.mark.live`. `pyproject.toml:355` sets `addopts = "… -m 'not live'"`, so
  it is deselected in every lane, and no scheduled/nightly live lane exists
  (`.github/` has no `-m live` / `--stage` / `RS_TEST_LIVE_GRAPH` invocation).

**Net:** the **only** automated coverage of the Graph backend is the ~300 respx
unit tests. By ID-127's own experience this is the risky kind of coverage: the
first live conformance run (recorded during GR-DONE) failed **23/118** because
the respx mocks asserted `409 + folder-facet` while live Graph returns `501`
(write-to-folder), `404` (write under a file ancestor), and `400 invalidRequest`
(move/copy under a file ancestor) — real mapping bugs the green mock suite hid.
The same class of blind spot remains for any service behaviour the mocks guess.

The cassette-replay gap itself is partly tracked (BK-262), but two
sub-issues are not: the `min_cassettes: 0` gate-blindness, and the fact that the
spec presents the suite as covering "every ID" without disclosing that the matrix
is skip-only and the integration tier never runs automatically (see C-series
below). The `@pytest.mark.spec` gate (`scripts/check_spec_marks.py` →
`violations: 0`) is **structural**: it proves a mark exists at collection time,
not that the test executes — so spec-mark-green does not imply behaviour-verified.

---

## 🟠 Medium

### M1 — `WriteResult.size` source diverges from GR-018 / GR-019 (code is better; amend the spec)

`items.py:106` populates `WriteResult.size` from the caller-supplied byte count
(`backend.py:812` passes `total`; `:857` passes `len(data)`), and the docstring
says so explicitly: "*size* is the byte count the backend wrote (authoritative
even when the response omits or under-reports `size`), not re-derived from the
body." But **GR-018** (spec 442-444) and **GR-019** (546-549) both state `size`
is "populated from the `driveItem` body Graph returns". `etag`/`last_modified`/
`version_id` *do* come from the body; only `size` diverges. Because
`get_file_info().size` reads `driveItem.size` (`items.py:78`), the two can
disagree if Graph omits or lags the field. The code's choice is the more
trustworthy one — per principle 5 the **spec** is the less-authoritative side and
should be amended, not the code.

### M2 — `base_path` (GR-058) is absent from the spec's authoritative signature and validation

GR-058 was added late (during GR-DONE). The code has `base_path: str = ""` in
`__init__` (`backend.py:175`) and validates it must be a `str`
(`backend.py:182-183`). But **GR-001**'s signature block (spec 32-45) — the one
place that enumerates the constructor contract — does not list `base_path`, and
**GR-005**'s validation list (spec 130-140) omits the `base_path` check. The RFC
never mentions it either. The spec lags shipped reality (principle 3).

### M3 — Live-tier credential env vars are wrong in the spec and RFC

The spec's Integration-only section (spec 1211-1213) and **rfc-0010** Stage 3
(407-410) both require "the four credential env vars `GRAPH_TENANT_ID`,
`GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_DRIVE_ID`" — a client-credentials
tier. The shipped tier is device-code / consumer (`_live_env.py:135-143`,
`graph_live.py:7-12`, `test_integration.py:28-30`): three vars, **no**
`GRAPH_CLIENT_SECRET`. The spec/RFC describe a live tier that does not exist.

### M4 — `graph-setup.md` is written as if the backend has not shipped

`docs-src/guides/backends/graph-setup.md` describes the backend in the future
tense throughout: "the **forthcoming** Graph backend **will take** one opaque
`drive_id`" (L155); "`GraphUtils.resolve_drive_id(...)` (**shipping with** the
backend) **will accept** three target shapes" (L156); "the libraries the built-in
`GraphAuth` helper **will wrap**" (L173-174); "the built-in `GraphAuth` helper,
**when it ships**, **will persist** its MSAL cache" (L253-254). The backend
shipped at `77acaa58b`. A reader concludes it is unavailable and hand-rolls an
`msal`/`httpx` device-code snippet (L177-214) instead of `pip install
"remote-store[graph]"` + `GraphUtils.resolve_drive_id("me", …)` — the exact
ergonomic on-ramp ID-127 delivered. Principle-3 violation.

### M5 — The main guide's headline Usage snippet throws on copy-paste

`docs-src/guides/backends/graph.md:26-41` mixes the **sync** resolver into an
async context:

```python
drive_id = GraphUtils.resolve_drive_id("me", token_provider=auth)   # L34 — runs asyncio.run() internally
async with AsyncStore(backend, root_path="Documents") as store:     # L38 — requires async def
```

A reader wrapping the block in `async def main(): … asyncio.run(main())` hits
`RuntimeError: asyncio.run() cannot be called from a running event loop`, because
`resolve_drive_id` calls `asyncio.run()` internally (`utils.py:58`). The runnable
example does it correctly with `await GraphUtils.aresolve_drive_id("me", …)`
(`examples/backends/graph_backend.py:71`) — the guide and the example disagree.

### M6 — The async-native Graph consumer gets no extension ecosystem (undocumented cliff)

`src/remote_store/aio/ext/` ships exactly one module — `write.py`
(`write_with_hash`). There is no async `observe`, `otel`, `glob`, `cache`,
`integrity`, `arrow`, `parquet`, or `dagster`. The spec's claim (GR-003, GR-015,
GR-026) that these are sync-only and reach Graph only via
`AsyncBackendSyncAdapter` is therefore accurate. The consequence is a real
user-experience cliff: a native `AsyncStore` Graph consumer — the natural
audience for an async-native backend — has the full `ext.*` surface available
only by switching to the sync adapter, which forfeits the async streaming the
backend exists to provide. This asymmetry is documented piecemeal in ADR-0025
and scattered spec notes, but nowhere a consumer would see it (no guide section,
no async-vs-sync extension matrix).

### M7 — `GraphAuth.get_token` raises stdlib `PermissionError`, not a `RemoteStoreError`

`auth.py:184` raises the builtin `PermissionError` on a token-acquisition
failure. It is invoked via `acquire_token` inside `graph_send`, so a failure
during any `store.read()` / `store.write()` propagates a stdlib exception to the
caller. It is not a `RemoteStoreError` subclass, so `except RemoteStoreError`
will not catch it — at odds with FEATURES' promise that "callers always receive a
typed error, never a backend-native exception" and the BE-021 spirit. The
docstring documents it honestly; the question is whether the built-in helper
should map it. (User-supplied token providers may raise anything; this finding is
scoped to the bundled `GraphAuth`.)

---

## 🟡 Low / Nits

### L1 — `resourceNotFound` mapped to `BackendUnavailable` regardless of scope

`http.py:124`: `if scope == "drive" or code == "resourceNotFound"` maps to
`BackendUnavailable`. `_get_item` always passes `scope="item"`
(`backend.py:362`), and `exists`/`is_file`/`is_folder` catch only `NotFound`
(`backend.py:542-569`). **GR-031** ties `resourceNotFound` to *drive* scope, but
the code applies it at any scope. If Graph ever returns `404 resourceNotFound` for
a missing *item*, `exists()` would raise `BackendUnavailable` rather than return
`False`, violating BE-004/BE-005. Latent today (Graph uses `itemNotFound` for
items), but the mapping is broader than the spec authorises.

### L2 — `_range_fallback_paths` stale-flag / scope-bleed (extends BK-259)

`backend.py:206` holds a per-instance `set[str]` that grows for the backend's
lifetime; `_mark_range_fallback` (`:448`) adds the raw `path`, and
`get_file_info` (`:586-589`) stamps `extra["graph.read.range_fallback"]=True` on
**every** future `FileInfo` for that path. Beyond BK-259's unbounded-growth
concern: the flag is set by a *read* but reported by an unrelated later
`get_file_info`, with no operation-context scoping despite GR-015 saying "within
the operation context"; it never clears, so a re-created item or changed tenant
config still reports a stale fallback; and the key is the raw caller string, so
`"/x"` and `"x"` track as distinct entries.

### L3 — Self-op short-circuit uses raw string equality, not normalised paths

`_short_circuit_self_op` (`backend.py:1043-1055`) returns `src == dst` by raw
string. But `native_path` treats `"/a.txt"` and `"a.txt"` as the same item
(`:253` drops empty segments). So a direct-backend `copy("/a.txt", "a.txt")` does
**not** short-circuit (GR-044): it issues a real `POST …/copy`, Graph `409`s, and
the caller gets `AlreadyExists` instead of the no-op. Masked through
`AsyncStore`/`Store`, which normalise and short-circuit before the backend — but
GR-044 is a backend contract ("exercised … when the backend is invoked
directly").

### L4 — GR-034 "Retry-After propagated via the error's context" describes a surface that does not exist

**GR-034** (spec 929-931) says the `Retry-After` value is "propagated via the
error's context". There is no `RemoteStoreError.context` surface (GR-026,
GR-045, and ADR-0024 all say so), and the code honours `Retry-After` inline in
the retry loop (`http.py:411-423`), not on any error object. The mechanism
wording is inaccurate on two counts; GR-048 already states the in-loop behaviour
correctly.

### L5 — `Raises:` clauses omit `PermissionDenied`, list `BackendUnavailable` inconsistently

`classify_graph_error` maps `401`/`403` → `PermissionDenied` on every
authenticated request (`http.py:117-122`), yet no public-method docstring lists
it (`read` :467, `get_file_info` :578, `delete` :887, `copy` :976, `move` :1016,
`write` :779). `BackendUnavailable` (429/5xx/transport, also universal) is listed
on `read`/`write`/`copy`/`move` but absent on `get_file_info`/`delete`/
`list_files`. No docstring promises an exception the code does not raise — this is
a completeness/consistency gap.

### L6 — No "SharePoint/business is less-tested ground" caveat; consumer-only verification is scattered

The whole backend was live-verified only against consumer OneDrive (device-code).
The candid SharePoint-unverified notes exist but are scattered across GR-018
(BK-261), GR-025 (`parentReference` path-form), GR-027 (`conflictBehavior` on
PATCH), and GR-049 (`file.hashes` omission), and all correctly cross-reference
each other. What is missing: (a) the spec's Integration-only section never states
the live tier is consumer-only with zero SharePoint/business coverage; and (b)
`graph.md` leads with "OneDrive, SharePoint, and Teams" and presents SharePoint
as fully supported, with no signal that a SharePoint user is on less-exercised
paths.

### L7 — Test gaps within the (sole) respx tier

- `read()` is an async generator, so its `_get_item` + folder check defer to
  first iteration. `test_read.py:207` (`test_folder_raises_before_yield`) wraps
  the whole `async for` in `pytest.raises` and does not assert *no bytes yielded
  before the raise* — it would pass whether the error fires on first `__anext__`
  or after partial yields. The timing it is named for is not pinned.
- `write_atomic` has no direct failure-path test (`test_write.py:317-324` asserts
  only delegation); its failure modes are covered transitively via `write`. Per
  TESTING.md Rule 1 it is a public method without its own `pytest.raises`.
- No per-method `403`→`PermissionDenied` test on any data-plane method;
  PermissionDenied is exercised only centrally at the `graph_send` layer.

### L8 — `ext.cache` shared-`cache_backend` cross-store collision (extends ID-123)

Cache keys are plain `(op, path)` tuples with no backend identity
(`ext/cache.py:365,392,409`); GR-050 acknowledges this. The default
`cache(store)` builds a fresh cache per store, so single-store use is safe. The
unguarded case is an explicitly **shared** `cache_backend=` across two top-level
stores at different drives: `cache(GraphStore("A"), cache_backend=shared)` and
`cache(GraphStore("B"), cache_backend=shared)` collide on `("read_bytes",
"report.csv")` → drive B serves drive A's bytes. Not Graph-specific (same for two
Local roots or S3 buckets) and opt-in, but ID-123's framing ("single-backend
cache keys are already correct") understates the multi-store case, which is
exactly where collisions occur.

### L9 — Large arrow/parquet reads over Graph spool to `TMPDIR` (undocumented, read-side)

`SEEKABLE_READ` is masked off, so `ext.arrow`/`ext.parquet` route large reads
through `read_seekable` (`ext/arrow.py:331`), which the Store layer synthesises
via `SpooledTemporaryFile`. Reading a large Parquet file over Graph therefore
spools the whole file to the temp volume before PyArrow can seek the footer — the
same `TMPDIR`-sizing concern GR-019 flags for uploads, but on the read side and
not currently documented in the guide.

### L10 — Promised follow-ups are untracked

GR-003 says async callers compose pattern matching themselves "until an async
equivalent of `ext.glob` lands as a separate backlog item" — no such item exists
in BACKLOG. ADR-0025 § Risks says "the cache extension should learn to warn when
wrapped over a bridged backend (tracked separately)" — that follow-up is not
filed either. The deferred async-ext surface (glob, observe, otel, cache,
integrity) is largely without a tracked owner.

---

## Verified strengths (checked, not rubber-stamped)

These were actively probed and came back clean:

- **Capability honesty (GR-003):** all 10 declared capabilities back a real,
  non-vacuous method; all 4 withheld (`GLOB`/`SEEKABLE_READ`/`ATOMIC_MOVE`/
  `USER_METADATA`) have sound rationale. No over- or under-declaration; the
  declared set is byte-identical to the GR-003 prose. `USER_METADATA` carries a
  defense-in-depth backend gate (`_reject_user_metadata`).
- **Error mapping is structured-only:** `classify_graph_error` keys on HTTP
  status + `error.code`; there is no string-matching on error messages anywhere
  (GR-028 satisfied). The monitor reuses the same table via a code→status reverse
  map.
- **Test-double discipline is exemplary:** zero `MagicMock`/`Mock(` in the entire
  graph test tree — every boundary is `respx` (real `httpx` transport) or a
  hand-written fake (TESTING.md Rules 4 & 6).
- **Retry/backoff is asserted at the computation level:** `test_http.py` pins
  Retry-After (delta and HTTP-date), precedence over computed backoff, and budget
  short-circuit — not just eventual success. Monitor cadence likewise.
- **Upload-session resume is hardened:** the liveness guard (non-advancing
  `nextExpectedRanges` → `BackendUnavailable`), malformed/missing ranges, and the
  strictly-increasing-offset termination guarantee are all tested.
- **Retry-safety of writes:** `spool_content` always materialises an
  `AsyncIterator` to a seekable spool before any send; no streaming body ever
  reaches a retrying `graph_send`.
- **Combined `close()` (GR-051) is genuinely pinned:** one test asserts both
  poller-cancel and session-abort fire on a fully-assembled backend and that
  `close()` never raises.
- **Extension safety is structural, not assumed:** ID-127 changes no `ext/`
  file and breaks none. `ProxyStore` forwards exceptions by default; `observe`/
  `otel` catch-record-`raise`; `ResourceLocked` reaches the caller verbatim
  through every layer. `ext.integrity` over Graph recomputes from the stream
  (no crash, no silent no-op). Lazy-import discipline is intact — no `ext`
  module imports graph/httpx/msal.
- **Trace quality is high:** the 13 ID-127 traces conform to the schema; the
  gr-done "vacuous conformance" finding matches reality; no trace claims a
  behaviour the code/tests do not support; the GR-* spec IDs are contiguous
  (GR-001..GR-058 + GR-036a) with no duplicates or dangling references.

---

## Proposed backlog items

Advisory groupings for the user to accept, split, or decline. Findings are
grouped by theme, owning files, and disposition. Existing items to **amend** are
called out first.

### Amend existing items

| Item | Folds in | What to add |
|------|----------|-------------|
| **BK-262** (Graph conformance cassettes / replay-able pre-signed URLs; the near-duplicate **BK-260** was consolidated into it per this PR's review) | **H2** | Already owns the cassette-replay gap. Extend its Definition-of-Done with two currently-unowned sub-issues: (1) once cassettes land, raise `record_cassettes.py` graph `min_cassettes` off `0` so an empty corpus *fails* the record gate — today the `recorded == 0` branch (`record_cassettes.py:329-337`) only *warns*, non-fatally, so promote that warning rather than add a redundant one; (2) note that until cassettes exist the Graph conformance matrix is skip-only — the suite must not read as "covered". Keep the pre-signed-URL redaction-vs-replay work as the load-bearing blocker. |
| **BK-259** (range-fallback flag: scope to operation, not backend lifetime) | **L2** | Already targets the flag's lifetime. Add the staleness/scope-bleed observations: the flag is set by a read but read back by a later unrelated `get_file_info`; it never clears (stale after item re-creation / tenant change); and it keys on the raw caller string (`"/x"` vs `"x"` diverge). The fix that scopes to operation context should also address these. |
| **ID-123** (cache keys derived from backend identity) | **L8** | Correct the framing: "single-backend cache keys are already correct" holds for the default per-store cache but **not** for a shared `cache_backend=` across multiple top-level stores, which is precisely where cross-drive collisions occur. Note this case in the item's scope. |

### New items (proposed)

| Group | Findings | Scope / files | Suggested disposition |
|-------|----------|---------------|-----------------------|
| **G1 — Resolve the credential-leak spec contradiction (security)** | **H1** | spec GR-045 / GR-035 / GR-026, possibly ADR-0024; `transfer.py:_resource_locked_mid_session`; `test_write.py` (flip to assert *absence* of the credential); add a masking regression test | **High / security.** Needs a design decision first (the two options are: redact the query like the monitor path and amend GR-045 to drop the resume-from-message promise; or introduce a structured `RemoteStoreError.context` carrier — spec-005 work ID-127 declared out of scope — and keep both the no-leak guarantee and resume). Escalate as a spec contradiction per CLAUDE.md before any code change. |
| **G2 — Spec / RFC reality-sync for ID-127** | **M1, M2, M3, L4, L6 (spec half), H2 (honesty note)** | `sdd/specs/044-graph-backend.md`, `rfc-0010`; `sdd/`-only | Amend GR-018/GR-019 so `size` is the written byte count (code is authoritative; M1); add `base_path` to the GR-001 signature block and GR-005 validation list and mention it in the RFC (M2); fix the Integration-only env-var list and RFC Stage 3 to the device-code three-var tier (M3); reword GR-034 to describe in-loop Retry-After honouring (L4); disclose in the Integration-only section that the conformance matrix is skip-only and the integration tier never runs in automated CI, and that the live tier is consumer-OneDrive-only with no SharePoint/business coverage (H2, L6). |
| **G3 — Graph guide & docstring accuracy** | **M4, M5, M6, L5, L6 (guide half), L9** | `docs-src/guides/backends/graph-setup.md`, `graph.md`; docstrings in `backend.py`; FEATURES.md | Rewrite the setup guide to present tense and reframe the hand-rolled snippet as an alternative (M4); fix the Usage snippet to resolve the drive id outside the async scope or use `await aresolve_drive_id` (M5); add an async-vs-sync extension matrix / note that native-async consumers have no `ext.*` surface (M6); complete the `Raises:` clauses (`PermissionDenied`, consistent `BackendUnavailable`) (L5); add a "verified against consumer OneDrive; SharePoint/business less exercised" caveat (L6); note read-side `TMPDIR` spooling for large arrow/parquet reads (L9). Low-risk, docs-only — M4/M5 are the cheapest, highest-value wins. |
| **G4 — Graph backend correctness edges** | **L1, L3, M7** | `src/remote_store/aio/backends/_graph/{http.py, backend.py, auth.py}` | Scope the `resourceNotFound`→`BackendUnavailable` mapping to drive scope so it cannot escape `exists()`/`is_file()`/`is_folder()` (L1); normalise paths before the self-op `src == dst` short-circuit, or document that the contract assumes Store-normalised input (L3); decide whether the bundled `GraphAuth` should raise a `RemoteStoreError` subtype instead of stdlib `PermissionError` (M7). Each is small and independent; split if preferred. |
| **G5 — Graph test hardening** | **L7** (+ the masking regression test from G1) | `tests/backends/graph/aio/` | Pin `read()` first-iteration failure timing (assert no bytes yielded before the raise); add a direct `write_atomic` failure-path test; add at least one per-method `403`→`PermissionDenied` test or document the centralised-mapping rationale. |
| **G6 — File the deferred async-ext follow-ups (backlog hygiene)** | **L10** | `sdd/BACKLOG.md` | File (or decline) the "async `ext.glob`" item GR-003 promises and the "cache warns when wrapping a bridged backend" item ADR-0025 promises, so the deferred async-ext surface has tracked owners. |

**Priority ordering:** G1 (security, needs a decision) → BK-262 amendment +
G2 honesty note (close the coverage/honesty gap) → G3 (consumer-facing docs,
cheap) → G4/G5 (correctness + tests) → BK-259/ID-123 amendments, G6 (hygiene).
