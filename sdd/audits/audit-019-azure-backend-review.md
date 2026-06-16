# Audit 019 — Azure backend (ID-219) expectation-driven review

**Backlog item:** ID-219 (apply the expectation-driven / DX review to the Azure
backend; follow-ups proposed at the end).
**Date:** 2026-06-16
**Scope:** The Azure backend — sync `AzureBackend`
(`src/remote_store/backends/_azure.py`), async `AsyncAzureBackend`
(`src/remote_store/aio/backends/_azure.py`), the shared
`src/remote_store/backends/_azure_common.py`, the `AsyncBackendSyncAdapter`
bridge (`src/remote_store/_async_to_sync_adapter.py`), spec
`sdd/specs/012-azure-backend.md` plus the cross-backend posture clauses (BE-028
spec 003, ASYNC-094 spec 029), the user guides `docs-src/guides/backends/azure.md`
and `azure-hns-setup.md`, and the test tiers (conformance + azurite Stage 2 +
`azure_live` Stage 3 + the 303 committed cassettes + `tests/backends/azure/test_live_hns.py`).
**Method:** the expectation-driven methodology
([research-expectation-driven-review.md](../research/research-expectation-driven-review.md)),
run as a **lens-organized panel** (the eight catalog lenses across five parallel
agents, each seeded with the matching [audit-016](audit-016-graph-backend-review.md)
finding-class so the sweep re-points rather than rediscovers), followed by a
**bounded live battery** against a real ADLS Gen2 (HNS) account (one fresh
filesystem, KB payloads, ~25 ops, immediate teardown — cost discipline per the
methodology §5). Every claim is verified against **source**, not against
mocks/cassettes (a cassette encodes our assumed shape, not the service's). This is
a **report-only** audit — nothing was modified. Dispositions in the proposals
section are advisory; the user decides what becomes work.

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low / Nit.
Each finding tag (H1, M3, L7…) is referenced by the proposals table at the end.

---

## Summary

The Azure backend is in materially better shape than Graph was at audit-016 on the
two dimensions that dominated that review. Behavioural coverage is **not** absent:
`tests/backends/cassettes/azure/` holds **303** committed cassettes (sync + async),
and a dedicated live HNS suite (`test_live_hns.py`) exercises the `hdi_isfolder`
directory guards, `write_atomic` etag normalisation, and root `get_folder_info`
against a real account — so Graph's headline H2 does not recur. The guides are
present-tense and their snippets run as written (Graph's M4/M5 do not recur). The
sync and async twins are remarkably disciplined: identical capability sets, a
single shared structured error classifier with **no** stdlib-exception leak (Graph
M7 does not recur), byte-identical HNS file-ancestor machinery, and a
`WriteResult.size` source that matches the spec (no Graph M1 divergence).

The material risks are different and orthogonal to that quality:

1. **`close()`/`aclose()` close a caller-supplied credential** (no ownership flag),
   so a shared `DefaultAzureCredential` is torn down out from under the rest of the
   user's application — a genuine, statically-certain defect (**H1**).
2. **The error classifier silently drops throttling and server errors.**
   `classify_azure_error` types only 404/403/409; **429, 5xx, 412, 401** fall
   through to a bare `RemoteStoreError`, so a caller backing off on
   `BackendUnavailable` never catches a throttle — and Graph types exactly these as
   `BackendUnavailable` (**H2**, cross-backend-inconsistent).
3. **The use-after-close contract diverges from Graph by deliberate design.**
   `AsyncAzureBackend` has no `_closed` guard and AZ-029 *blesses* "re-initialise on
   demand" — the exact postcondition that *was* Graph's BUG-219 (live-confirmed
   here: `exists()` succeeded after `close()`). This is the cross-backend
   concurrency-contract divergence the BUG-219 trace explicitly flagged for ID-219
   (**M1**), and it now needs a posture decision.

The remainder are spec-lags-code accuracy gaps, doc gaps (notably a guide that
steers analytics users into an in-RAM anti-pattern), and small correctness edges.

---

## 🔴 High

### H1 — `close()`/`aclose()` close a caller-supplied credential (ownership defect)

**Files:** `src/remote_store/backends/_azure_common.py:181-199` (`resolve_credential`);
`src/remote_store/backends/_azure.py:1126-1132` (sync `close()`);
`src/remote_store/aio/backends/_azure.py:1214-1220` (async `aclose()`).

`resolve_credential` returns an explicitly-passed `credential=` object **unchanged**
(`cred = credential` at `_azure_common.py:181`; the `is None` branches only fire
when the caller supplied nothing). `_get_credential` caches it into
`self._resolved_credential`. Then `close()` does:

```python
# Close credential (e.g. DefaultAzureCredential holds transport sessions).
if self._resolved_credential is not None:
    close = getattr(self._resolved_credential, "close", None)
    if close is not None:
        with contextlib.suppress(Exception):
            close()
```

There is **no `created_credential` flag** distinguishing a backend-auto-created
`DefaultAzureCredential` from a caller-owned one. The comment says "auto-created"
(`aio/_azure.py:1214`) but the code closes *whatever* is in `_resolved_credential`.

**Consumer impact:** the realistic pattern is a single shared
`DefaultAzureCredential()` (or any `TokenCredential`) passed via `credential=` to
several clients/backends. The first `close()` (or context-manager exit, or
`__del__`) closes the user's credential — its transport sessions go away and every
*other* client still holding it starts failing; a second backend sharing it
double-closes. The backend should close only credentials it created. (Scope: the
`credential=` object path. `account_key`/`sas_token` resolve to strings — `getattr(str, "close")`
is `None`, harmless — and the `connection_string` path does not populate
`_resolved_credential` at all, so those callers are unaffected.) Statically
certain; the `credential=` branch in `_blob_service` is even `# pragma: no cover`
(`aio/_azure.py`), i.e. untested.

### H2 — Error classifier drops throttling / server / precondition errors to a bare `RemoteStoreError`

**File:** `src/remote_store/backends/_azure_common.py:104-113` (`classify_azure_error`).

The classifier branches on `ResourceNotFoundError`/`ResourceExistsError`/
`ClientAuthenticationError`/`ServiceRequestError`/`ServiceResponseError`, and for
`HttpResponseError` only on status **404/403/409**. Every other status —
**429 (throttle), 500/503 (server), 412 (precondition), 401 (HTTP-shaped auth)** —
hits the fall-through:

```python
return RemoteStoreError(str(exc), path=path, backend=backend_name)  # pragma: no cover
```

**Consumer impact:** a FastAPI app or data pipeline that catches
`BackendUnavailable` to retry/back off under throttling **will not catch it** — a
sustained 429 (after SDK retry exhaustion) arrives as `HttpResponseError(status=429)`,
not `ServiceResponseError`, so it surfaces as the generic base error. Graph types
"throttling, 5xx, or transport failure" consistently as `BackendUnavailable`
(`aio/backends/_graph/backend.py`), so the same workload behaves differently across
two backends — a cross-backend-inconsistency. AZ-025's mapping table
(`sdd/specs/012-azure-backend.md`) has **no row for 429/5xx**, so the spec is silent
here too. The `# pragma: no cover` on both fall-through lines confirms no test ever
exercises a real 429/5xx/412 shape — exactly the audit-016 "mocks ≠ service" hazard.
The mapping gap is certain statically; *quantifying* how often each status arrives
as `HttpResponseError` vs `ServiceResponseError` under real throttling needs a live
load test (deliberately **not** run here — forcing throttling is high-volume, against
the pay-per-use cost discipline).

---

## 🟠 Medium

### M1 — Use-after-close silently re-initialises; AZ-029 blesses the exact postcondition that was Graph's BUG-219

**Files:** `aio/backends/_azure.py:1202-1220` (`aclose()`, no `_closed` guard) and the
lazy properties `_blob_service`/`_cc`/`_datalake_service` (re-create on `is None`);
sync `_azure.py:1115-1132` shares the gap; `sdd/specs/012-azure-backend.md:249-252`
(AZ-029).

Neither twin sets or checks a `_closed` flag. `aclose()` zeroes the cached client
instances and `_resolved_credential`; the next operation hits a lazy property that
**re-creates** the client (and `_get_credential` re-resolves a fresh credential), so
the op silently succeeds against brand-new resources the caller has no handle to
close. **Live-confirmed:** after `close()`, `exists("uac/x.txt")` returned `True`.
AZ-029 explicitly sanctions this: "because lazy properties re-initialize on next
use, the backend is technically reusable after `close()`. This is consistent with
S3Backend's behavior." That is verbatim the "re-initialise on demand" postcondition
that *was* the Graph bug — Graph's GR-051 was amended (BUG-219) to make the backend
**terminal** (typed `BackendUnavailable` on use-after-close). The BUG-219 trace
(`sdd/traces/bug-219-graph-aclose-guard.yml`) records this divergence as
"deliberately flagged for the cross-backend concurrency-contract work
(BK-287 / ID-219)". This audit is that surfacing.

**Consumer impact:** a user who closes a backend to release resources, then
accidentally reuses it, gets a silent resource reopen (new aiohttp sessions / a new
`DefaultAzureCredential`) instead of a clear error — a leak masquerading as success.
This is a **posture decision**, not an obvious bug: align Azure (and S3) with
Graph's terminal close, or bless the divergence and document it as the intended
cross-backend contract. Classification: cross-backend-inconsistency / spec-gap.

### M2 — `error_code` is mandated by AZ-025 but never read by the classifier

**Files:** `_azure_common.py:104-112`; `sdd/specs/012-azure-backend.md` (AZ-025 table,
which enumerates `BlobNotFound`/`AuthorizationFailure`/`DirectoryIsNotEmpty`/…).

`classify_azure_error` keys solely on exception type and `status_code`; the only
`error_code` ever consulted in the backend is the inline `DirectoryIsNotEmpty` check
in `delete()` (`aio/_azure.py`). The error codes the AZ-025 table enumerates are
never used by the shared classifier. Per principle 5 either the code under-reads
(should consult `error_code`) or the spec over-promises; the two disagree.

### M3 — The guide steers analytics users into an in-RAM anti-pattern, and the async/bridged path forfeits Azure's native range reader

**Files:** `docs-src/guides/backends/azure.md:135-144` (Streaming); sync
`read_seekable` + `_AzureRangeReader` (`_azure.py:435-448, 109-171`); `AsyncStore`
omits `read_seekable` (`aio/_async_store.py:16`); `AsyncBackendSyncAdapter` masks
`SEEKABLE_READ` (`_async_to_sync_adapter.py`); `src/remote_store/aio/ext/` ships only
`write.py`.

For seekability the guide tells readers to `read_bytes()` then wrap in `io.BytesIO`
— i.e. materialise the **entire** blob into memory — and never mentions
`Store.read_seekable()`, the API Azure *optimised* with a true HTTP-Range reader
(`_AzureRangeReader`, no spill). So a citizen dev following the guide loads a
multi-GB blob into RAM rather than range-seeking the footer. Worse on the async
side: an async-native Azure consumer has **no** `read_seekable` and no async
`ext.arrow`/`parquet`, so to use them they must bridge to sync — and the bridge masks
`SEEKABLE_READ`, falling back to spooling the whole file to `TMPDIR` before PyArrow
can seek. This is the audit-016 L9/M6 phenomenon, but sharper for Azure (which
forgoes an *existing* native optimisation). The sync-native path is a verified
strength; the doc and the async/bridged paths are the gap. Classification: doc-gap
(+ a candidate cross-backend shared item with Graph's L9/M6).

### M4 — HNS `write_atomic` drops `digest` while sibling `write` keeps it; guide's digest claim is half-true

**Files:** HNS post-rename `props_dict` carries only `etag`/`last_modified`
(`_azure.py:612-626`; `aio/_azure.py:673-686`), fed to
`_build_azure_write_result` which reads `content_md5`/`version_id` from that dict
(`_azure_common.py:212-214`); `docs-src/guides/backends/azure.md` (digest claim).

**Live-confirmed on real HNS:** `write_atomic` → `digest=None`; the sibling `write`
on the same account → `digest=ContentDigest('md5', …)`. (`version_id` was `None` for
both — versioning not enabled on the account — so the divergence is specifically
`digest`.) The guide states `WriteResult.digest` is populated "when Azure echoes
back Content-MD5 in the upload response" without noting that HNS `write_atomic` never
echoes it (the committing rename's post-read does not re-expose Content-MD5). A user
inspecting `WriteResult.digest` after `write_atomic` on HNS silently gets `None` even
though the same payload via `write` yields a digest. Classification: doc-gap
(behavior is by-design); a per-method inconsistency worth disclosing or closing.

### M5 — Sticky silent HNS misdetection degrades semantics for the instance lifetime

**Files:** `_azure.py:1293-1305` (sync `_hns`); `aio/_azure.py:243-259`
(`_ensure_hns`).

The HNS probe (`get_account_information()`) is wrapped in `except Exception`, logs a
warning, and caches `_hns_enabled = False` for the backend's lifetime. A *transient*
failure on the first probe permanently routes an HNS account through flat-blob
emulation — no atomic rename, no `hdi_isfolder` directory rejection — until `close()`,
with no error surfaced. AZ-006 discloses the fail-open fallback but not the
lifetime-stickiness. Classification: bug / unspecced behavior. (Forcing the transient
blip needs live fault injection; the caching logic is statically certain.)

### M6 — Sync/async docstring and guide-table omissions

**Files:** sync constructor docstring (`_azure.py:187-213`) omits `retry` (the param
exists at `:229`); the async twin documents it (`aio/_azure.py:73`).
`docs-src/guides/backends/azure.md:71-82` Options table omits both `retry` and
`reject_write_under_file_ancestor`. Sync `check_health` (`_azure.py:305`) has no
docstring while the async one documents its `Raises:` (`aio/_azure.py:265-272`); with
`show_if_no_docstring: false`, the sync contract renders as nothing.

A real, public kwarg is undocumented on the side a reader checks first, and the
user-facing Options table reads as authoritative while missing two real options.
Classification: doc-gap + cross-twin inconsistency.

---

## 🟡 Low / Nits

- **L1 — Self-op short-circuit uses raw `src == dst`, but `azure_path` normalises.**
  `_azure.py:994` / `:1060` compare raw strings; `azure_path` collapses `/+` and
  lstrips `/` (`_azure_common.py:74`). A direct-backend `move("a//b","a/b", overwrite=True)`
  on a flat account is not seen as a self-op → copy-to-self then delete-source = the
  file is gone. Unreachable via `Store` (`RemotePath` canonicalises and the Store
  short-circuits first), so it bites only direct-backend callers and is invisible to
  conformance. Graph L3 analog. Classification: bug (latent). Hit-likelihood: low.

- **L2 — `glob` classifies pattern-translation errors on async only.** Async wraps
  the whole body (incl. `pattern_to_regex`) in `classify_azure_error`
  (`aio/_azure.py:944-954`); sync does not (`_azure.py:901-909`). A malformed-pattern
  `re.error` leaks raw from sync but is re-wrapped as a generic `RemoteStoreError` by
  async. Same op, two error types (sync's is arguably the more correct). 

- **L3 — Async `ext.*` cliff is undocumented.** A native `AsyncStore` Azure consumer
  has no async `observe`/`otel`/`glob`/`cache`/`integrity`/`arrow`/`parquet`/`dagster`
  (only `aio/ext/write.py` ships); reachable only by bridging to sync, forfeiting async
  streaming. Audit-016 M6 analog; absent from `azure.md`.

- **L4 — ASYNC-094 cross-loop rule and the `_ensure_hns` thundering-herd are not
  surfaced to consumers.** The "one `AsyncStore` per event loop, never share across
  loops" constraint (load-bearing for the FastAPI persona) lives only in the spec.
  Two coroutines on one loop can both pass the `_hns_enabled is None` check and both
  fire the account-info probe (`aio/_azure.py:243-259`) — idempotent (no correctness
  bug), but a redundant round-trip the AZ-037/ASYNC-094 "race-free between awaits"
  framing does not cover (the mutation straddles an await).

- **L5 — No connector-pool tuning guidance.** A shared single-store FastAPI
  deployment funnels all coroutines through one aiohttp connector; the guide gives no
  guidance on tuning the pool via `client_options` for high concurrency. By-design;
  benefits from a live high-concurrency characterisation.

- **L6 — `backend="azure"` vs `"async-azure"` drift.** AZ-026 states mapped errors
  carry `backend="azure"`, but the async classifier is invoked with
  `backend_name="async-azure"`. Spec/code doc drift.

- **L7 — `write_atomic` streaming chunk-size bound differs across twins.** Sync caps
  every DFS `append_data` at `_AZURE_BLOCK_SIZE` (`_azure.py:591`); async appends one
  call per producer chunk, unbounded (`aio/_azure.py:653`). Documented intentional, but
  a real behavioral divergence for large async streaming uploads.

- **L8 — Streaming upload is not spooled.** `write()` passes the async generator
  straight to `upload_blob` (no spool-to-temp like Graph); whole-upload retry safety
  for `AsyncIterable` content rests entirely on SDK block-level buffering. By-design /
  cross-backend difference; relevant only under an injected mid-upload transport failure
  (live-only to characterise).

---

## Verified strengths (checked, not rubber-stamped)

- **Twin parity is high.** Identical capability sets (`{all} − {SEEKABLE_READ, ATOMIC_MOVE}`,
  `_azure.py:51` ≡ `aio/_azure.py:49`); identical move/copy precondition ordering and
  `hdi_isfolder` dst-probe logic; byte-identical HNS file-ancestor machinery
  (`_azure.py:1334-1386` ≡ `aio/_azure.py:1317-1360`); identical delete error mapping.
- **One structured classifier, no stdlib leak.** Every SDK exception routes through
  `classify_azure_error` (`_azure_common.py:77`), keyed on type + status, never on
  message strings; the missing-`azure-identity` case raises `BackendUnavailable`, not a
  stdlib error. Graph M7 (stdlib `PermissionError` leak) does not recur.
- **`WriteResult.size` matches spec.** `len()` for bytes, a byte-counting passthrough
  for streams, `source="native"` via the single `_build_azure_write_result`. No Graph
  M1-style divergence.
- **No M4/M5 doc recurrence.** Both guides are present-tense; every runnable block is
  sync and API-accurate, and the guide agrees with `examples/backends/azure_backend.py`.
  No throw-on-copy-paste.
- **HNS-only behaviour is genuinely live-covered.** `test_live_hns.py` exercises
  `hdi_isfolder` directory guards, `write_atomic` etag normalisation, `is_folder`/`is_file`,
  root `get_folder_info`, and streaming `write_atomic` against a real account.
  **This audit's live battery additionally confirmed:** HNS `move(overwrite=True)` is a
  real atomic rename (src removed, dst holds src bytes); `overwrite=False` raises
  `AlreadyExists` on an existing key; `write_atomic` size/etag/source are correct.
- **Bounded memory at volume.** Listings (`list_files`/`list_folders`/`iter_children`)
  and folder aggregation stream via SDK pagination; uploads stage in bounded ~1 MiB
  blocks; async byte uploads avoid the materialize anti-pattern.
- **The bridge genuinely manufactures thread-safety.** `AsyncBackendSyncAdapter`
  serialises every sync caller onto one private daemon-thread loop, loop-confining the
  async Azure client and satisfying ASYNC-094; no surprise under bridged concurrent load.
- **Sync `read_seekable` is efficient and reachable.** The Store dispatches the
  `_AzureRangeReader` override directly (independent of the masked `SEEKABLE_READ`),
  so sync `ext.arrow`/`parquet` over Azure range-seek rather than spill.

---

## Proposed backlog items

Advisory groupings for the user to accept, split, or decline (per the Audits rule,
this audit proposes; nothing is filed without sign-off). Routing follows the
methodology §4 table.

### New items (proposed)

| Group | Findings | Scope / files | Route + suggested disposition |
|-------|----------|---------------|-------------------------------|
| **G1 — Credential ownership + close posture** | **H1, M1** | `_azure_common.py` (`resolve_credential` → track ownership), both `close()`/`aclose()`; AZ-029; conformance spine | **H1 is a clear bug (High):** add a `created_credential` flag so the backend closes only credentials it created; flip the `# pragma: no cover` credential path into a real test. **M1 is a posture decision (Medium):** align Azure+S3 with Graph's terminal close (typed `BackendUnavailable`, an aclose-terminal **conformance** lane next to `test_concurrency.py`) **or** bless the divergence and state it as the intended cross-backend contract in AZ-029 / the BK-287 posture family. This is the cross-backend item the BUG-219 trace flagged for ID-219 — decide it here. |
| **G2 — Error-mapping completeness** | **H2, M2** | `classify_azure_error` (`_azure_common.py:104-113`); AZ-025 table | Extend the classifier to type **429/5xx → `BackendUnavailable`** (matching Graph) and decide **412/401** dispositions; reconcile AZ-025 (add the missing rows and/or read `error_code`). Add a deterministic test for each mapped status (the fall-through is currently `# pragma: no cover`). A live throttle characterisation (which statuses arrive as `HttpResponseError` vs `ServiceResponseError`) is a **live-tier** follow-up, milestone-gated — not a per-PR gate. |
| **G3 — Seekable-read DX + async ext cliff** | **M3, L3, L5** | `docs-src/guides/backends/azure.md`; possibly a cross-backend explanation page shared with Graph L9/M6 | Replace the `read_bytes()`+`BytesIO` "seekability" advice with `Store.read_seekable()`; document the async-native `ext.*` cliff and the bridged-read `TMPDIR` spool; add connector-tuning guidance. Consider folding with the Graph L9/M6 item into one cross-backend doc note. **Also the strongest candidate for the companion cloud DX pilot** (the "does the documented story hold" narrative — see routing note below). |
| **G4 — WriteResult digest accuracy on HNS** | **M4** | `docs-src/guides/backends/azure.md`; optionally the HNS `write_atomic` path | Document that HNS `write_atomic` returns `digest=None` (the sibling `write` populates it); or close the gap by populating `digest` from the post-rename properties when available. Low-risk; docs-first. |
| **G5 — HNS-detection robustness** | **M5** | `_azure.py:1293-1305`; `aio/_azure.py:243-259`; AZ-006 | Do not cache a `False` HNS result that came from a *transient* probe failure (distinguish "probed flat" from "probe errored"); spec the stickiness. Small, independent. |
| **G6 — Doc/docstring parity + correctness edges** | **M6, L1, L2, L4, L6, L7** | both `_azure.py` docstrings; `azure.md` Options table; `_azure.py:994/:1060`; `glob`; AZ-026 | Add `retry` to the sync docstring and the guide Options table (+ `reject_write_under_file_ancestor`); give sync `check_health` a docstring; normalise paths before the self-op `src == dst` short-circuit (or document the direct-backend assumption); align sync/async `glob` error handling; surface the ASYNC-094 cross-loop rule in the guide; fix the `backend="azure"`/`"async-azure"` drift. Each is small and independent; split freely. |

**Priority ordering:** G1-H1 (credential bug, security/reliability) → G2 (error
mapping, high blast-radius under load) → G1-M1 (the cross-backend posture decision)
→ G3 (consumer-facing DX, cheap) → G4/G5/G6 (docs + correctness edges).

### Routing note — companion cloud DX pilot

Per the ID-219 charter, the citizen-dev "does the documented story hold" narratives
route to the **companion black-box DX suite's cloud DX tier** — the Azure successor
to the completed Graph pilot (companion B-012 Iteration 3B), tracked in the companion
repo, **not** here. The cleanest candidates are **M3** (the in-RAM anti-pattern a
guide-following user actually hits) and **M4** (the `digest=None` surprise), both
observable black-box through the public API with a consumer's own creds.
