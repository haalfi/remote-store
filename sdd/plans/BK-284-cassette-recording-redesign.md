<!-- doc: repo-only -->
# BK-284 Plan — Cassette Recording Layer Redesign

> **Temporary artefact. Delete when BK-284 closes.** This plan is a
> point-in-time decomposition of the implementation, not a living
> contract. The authoritative baseline is the BK-284 backlog entry
> (its five filing decisions), [spec 048 § TEST-007](../specs/048-testing-architecture.md#test-007-http-cassette-and-replay-layer),
> and — once PR 2 lands — `sdd/specs/049-live-recording-architecture.md`
> plus `sdd/adrs/0029-cassette-recording-architecture.md`. When those
> and this plan disagree, they win and this file is wrong (principle 5).
> On BK-284 close, this file is removed in the same PR that moves
> BK-284 to `BACKLOG-DONE.md` (the ID-127 plan precedent).

## Purpose

Decompose BK-284 into the two PRs its filing decision 5 mandates, at
file-and-function granularity, against the **post-PR-#787 codebase**
(the BK-262 Graph-cassette branch — see Baseline below). Each PR is
independently reviewable and reversible; PR 1 proves the
filter-equivalence claim on low-risk ground before PR 2 touches
cassette-matching correctness.

The redesign turns `tests/backends/fixtures/_cassettes.py` from two
parallel hand-rolled scrub stacks (Azure, Graph) into a
backend-agnostic core driven by declarative per-backend profiles, and
gives the recording transport its own spec (049, REC-NNN clauses) so
the invariants BK-262 surfaced stop living only in code comments.

## Baseline and merge order (load-bearing)

Everything below describes the tree **after PR #787
(`bk-262-graph-cassettes`) merged** (master `831f34f`). That PR
created `_GRAPH_PII_BODY_SCRUB` (the fourth scrub list), the Step-4
`forbidden_patterns` gate in `scripts/record_cassettes.py`, the
`graph_live` / `graph_replay` fixtures, and the 118-cassette Graph
corpus this refactor must keep replaying.

Review-adapted scrub logic that landed with the merge (deltas vs the
PR draft this plan was first written against — all must survive PR 2's
rewrite as profile declarations):

- `GRAPH_FORBIDDEN_CASSETTE_PATTERNS` moved into `_cassettes.py` as
  the **single source for two gates**: the recorder's Step-4
  scrub-verify *and* a creds-free CI sweep over the committed tree
  (`test_cassettes.py::TestGraphCommittedCassettePIISweep`). It also
  grew markers: bare JWT (`eyJ…`), tenant SharePoint host, unredacted
  credential forms, unredacted identity keys, bare email address.
- The token-response body scrub covers `id_token` / `client_info`
  (base64-encoded account identity), not just
  `access_token` / `refresh_token`.
- The pre-signed request branch additionally rewrites the `Host`
  header to the placeholder host and runs the credential-form body
  scrub before its early return (token exchange against a non-API
  auth host such as `login.live.com`).
- `_GRAPH_SCRUB_RESPONSE_HEADERS` grew the ESTS / SharePoint / CDN
  correlation ids (`x-ms-request-id`, `x-ms-ests-server`,
  `sprequestguid`, `splogid`, `ms-cv`, `x-msedge-ref`).

Independent of BK-283 (example-test replay extension).

## Sequencing at a glance

```
PR #787 (BK-262, open) ──► PR 1 — native filters ──► PR 2 — profile core + spec 049 + ADR-0029
                              (warm-up, S)               (the rewrite, L)
```

Commit messages for both PRs start with `BK-284:` (CLAUDE.md §
Backlog). The trace
`sdd/traces/bk-284-cassette-recording-redesign.yml` is authored when
PR 1 work begins and ships, updated, with **each** PR (CLAUDE.md §
Trace authoring). CHANGELOG: N/A for both PRs (audience `infra.test`,
not user-facing). BACKLOG transitions: PR 1 marks BK-284 `[~]` with a
"PR 1 of 2 landed" note; PR 2 moves it to `BACKLOG-DONE.md`, runs
`hatch run gen-backlogid`, and deletes this plan file.

## Cross-cutting decisions

Decisions 1–5 of the backlog entry (spec home, profile-on-fixture
registration, async notes in the same spec, hybrid forbidden-pattern
ownership, two-PR migration) are taken as given and not re-litigated.
The following are **new, plan-level** decisions inside the latitude
those left open. They are advisory (an audit-style prescription):
re-evaluate at implementation time and diverge with a trace note if a
different path fits better.

1. **`EnvRedact` takes a resolver, not a raw env-var name.** The
   sketch's `EnvRedact(env_var, fake)` fits Graph (`GRAPH_DRIVE_ID` is
   the value verbatim) but not Azure: the account name is parsed out
   of `AZURE_STORAGE_CONNECTION_STRING`, it is not an env var's whole
   value. Shape: `EnvRedact(name, resolve, fake, case_insensitive=False)`
   where `resolve: Callable[[], str | None]` returns the live value in
   record mode and `None` in replay mode (collapsing today's
   `_real_azure_account` / `_real_graph_drive_id` conftest functions
   into the profile). The "env" framing survives in the spec prose;
   the code generalises to "live-value redaction".

2. **Named-pattern audit counts via a recording-run manifest.** Step 4
   runs in a separate process after the pytest recording subprocesses
   exit, so per-rule fire counts cannot live in module globals. The
   scrub core, when `record_cassettes.py` exports a manifest path
   (e.g. `_RS_SCRUB_MANIFEST=./tmp/scrub-manifest-<backend>.json`),
   counts each `RedactPattern` application and dumps
   `{rule_name: count}` at session end; Step 4 reads it and fails any
   `required-to-fire` rule at zero. The manifest is ephemeral
   (`./tmp/`, gitignored), never committed — counts are
   workload-dependent and only the zero/non-zero signal gates.
   *Rejected alternative:* inferring counts post-hoc by scanning
   cassettes for replacement markers — generic `REDACTED` replacements
   are not attributable to a rule. Keep the env-independent
   byte-scan (`FORBIDDEN_ENVELOPE` + per-profile additions) exactly
   because it needs no manifest and works in `--verify-only` mode,
   where no recording ran and the named-count audit is skipped.

3. **Profile lookup stays on the node-name helper.** Of the two
   options decision 2 left open, extend the existing
   bracket-token matcher (`_cassette_dir_for_node_name`) over a map
   built at conftest import from the fixture registry
   (`fixture_id → profile`), rather than `request.node.callspec`
   introspection: the missing-cassette skip hook runs in
   `pytest_collection_modifyitems`, where there is no
   `FixtureRequest`, so the node-name path is needed regardless —
   one mechanism for all four consumers beats two.

4. **One `CassetteProfile` instance per backend family, shared by
   reference.** `azure_live`, `azure_live_async`, `azure_replay`,
   `azure_replay_async` all carry the same frozen profile object;
   likewise `graph_live` / `graph_replay`. The profile also declares
   each fixture id's canonical cassette alias (replacing
   `_CASSETTE_ID_ALIASES`), so registering a fixture with a profile is
   the *single* registration act — no second table to forget
   (the per-backend extension contract, REC-007 below).

5. **PR 2 never re-records.** The existing committed corpus
   (≈200 Azure + 118 Graph cassettes) is the oracle proving the
   refactor preserved behaviour. If any PR-2 change appears to require
   re-recording to stay green, that is a defect in the refactor, not a
   refresh chore — stop and diagnose.

---

## PR 1 — vcrpy-native filter migration (warm-up, effort S) — IMPLEMENTED

**Status: implemented** (this branch). The header half migrated; the
OAuth POST-body half was **evaluated and rejected** on empirical
grounds — see below. Divergence recorded here, in the backlog entry,
and in the trace, per the cross-cutting decisions preamble.

**Scope.** Move the scrubs vcrpy ships native filters for out of the
hand-rolled `before_record_*` callbacks, in both `build_vcr_config`
and `build_graph_vcr_config`. Pure behaviour-preserving refactor of
`_cassettes.py` + its unit tests; no cassette file changes, no
conftest changes, no new concepts.

**The migration map (as implemented).**

| Today (hand-rolled) | After PR 1 |
|---|---|
| `_SCRUB_REQUEST_HEADERS` delete loop (azure) | `filter_headers=["authorization", "x-ms-date", "x-ms-client-request-id", "cookie", ...]` |
| `_GRAPH_SCRUB_REQUEST_HEADERS` delete loop | `filter_headers=["authorization", "cookie", "client-request-id", ...]` |
| `User-Agent` rewrite branch (both) | tuple form appended: `("User-Agent", "azsdk-python-replay")` |
| `_GRAPH_REQUEST_BODY_SCRUB` regex list | **kept as regex** — native filter rejected, see below |

Tuple form is load-bearing on the User-Agent row (backlog decision
5): list form would *delete* the header, where today's behaviour
keeps the key and replaces the value. The tuple key is capitalised
`User-Agent` because vcrpy re-inserts under the given key's case
after its case-insensitive pop, and every committed cassette records
the capitalised form — the lowercase key the filing sketch used would
case-flip the header on every re-record.

**Why `filter_post_data_parameters` was rejected** (the empirical
finding that re-decided the filing sketch's fourth row): in vcrpy
8.1.1 (`vcr/filters.py:replace_post_data_parameters`) the filter is
POST-only and re-serialises every body whose `Content-Type` is
`application/json` through `json.loads`/`json.dumps` **even when no
parameter matches** — whitespace-churning every Graph JSON POST
(copy, createFolder, createUploadSession) on the next re-record and
polluting the security-review diff the forbidden-pattern defence
model relies on (REC-005). The targeted bytes regexes are
byte-preserving and method-agnostic, so they stay. Revisit only if
vcrpy gains a non-rewriting filter. (The originally-named fallback
trigger — bytes bodies choking the filter — turned out fine; the
JSON-rewrite collateral is what disqualified it.)

**What stays custom, on purpose** (vcrpy has no native equivalent):

- Azure: `x-ms-rename-source` / `x-ms-copy-source` request-header
  *rewrites* (account + filesystem + tmp-uuid normalisation), the URI
  rewrites, all of `before_record_response` (response-header deletes
  and rewrites, body scrubs — vcrpy has no response-side filters).
- Graph: the pre-signed-host URI collapse + `Host`-header rewrite,
  drive-id / conformance-root rewrites, the whole
  `_GRAPH_REQUEST_BODY_SCRUB` body scrub (both branches), and all of
  `before_record_response`.

After the move, `build_graph_vcr_config`'s `_scrub_request_headers`
helper disappears entirely; the azure request-header loop shrinks to
the two `x-ms-*-source` rewrite keys.

**Ordering fact to encode in a test:** vcrpy composes the native
filters *before* the custom `before_record_request`
(`vcr.config.VCR._build_before_record_request`), so the custom hook
sees an already-filtered request. Nothing in the remaining custom code
reads the headers the filters remove, so this is safe — assert it
anyway (see tests).

**Files touched.**

- `tests/backends/fixtures/_cassettes.py` — both config builders gain
  `filter_headers`; `_GRAPH_REQUEST_BODY_SCRUB` stays (rejection
  rationale documented at its definition); docstrings name the
  native/custom split.
- `tests/backends/fixtures/test_cassettes.py` — **the load-bearing
  test rework.** The security-gate tests called
  `cfg["before_record_request"]` directly; after PR 1 that callable no
  longer drops `Authorization`, so the tests would fail (or worse,
  be weakened to pass). Reworked to exercise the *composed*
  pipeline the way vcrpy does — `vcr.VCR(**cfg)` + its
  `_build_before_record_request({})` — with real `vcr.request.Request`
  objects, so the gate asserts what a real recording run does. Added:
  a mixed-case `AUTHORIZATION` deletion test (vcrpy's `HeadersDict`
  is case-insensitive like today's `.lower()` loop); a
  native-before-custom ordering test; a first-ever
  `TestAzureCassetteScrub` unit class (the azure scrub previously had
  only the replay conformance suite as proof). One direct-hook
  `SimpleNamespace` test remains for the custom hook's `str`-body
  dispatch (real vcrpy requests byte-encode `str` bodies on
  assignment, so the branch is unreachable through the composed
  chain).

**Acceptance criteria** (status at implementation):

- All existing scrub assertions pass through the composed pipeline —
  same secrets in, same redactions out. ✓ (35 passed)
- `graph_replay` and `azure_replay*` Stage-1 conformance slices pass
  against the **unchanged** committed corpus. ✓ (109 + 296 passed,
  zero cassette files modified)
- `hatch run all` green. ✓
- `record_cassettes.py --verify-only` for both backends — **✓ run
  live** (session teleported to a machine with `.env` creds): graph
  Step 4 clean over 118 cassettes (live drive-id + all 10 forbidden
  markers absent), azure Step 4 clean over 303 cassettes (live
  account name absent), and Step 5 replay smoke green for both
  (109 / 296). This is the load-bearing creds-gated gate: it resolves
  the **real** account name / drive-id from `.env` and confirms
  neither survives into any committed cassette under the new
  native-filter code path.
- Byte-identity dogfood — **✓ run live** (opt-in flags exported, one
  `--node` re-record per backend, both reverted, nothing committed):
  - **Azure** byte-equivalent — only `ETag` / `Last-Modified`
    (per-run volatile) changed; every migrated header stably
    absent/normalised. No filter-attributable byte change.
  - **Graph** byte-equivalent on the interactions both recordings
    share (volatile churn only); the re-record additionally captured
    a cold-cache MSAL `refresh_token` POST absent from the corpus,
    which directly proves the migration: `User-Agent` normalised via
    the native filter, `refresh_token=` redacted by the kept bytes
    regex, all four token-response fields redacted.
  - **Finding folded into PR 2:** that same refresh POST exposed a
    pre-existing scrub gap — `X-AnchorMailbox` embeds the cid in
    hyphen-split oid form, missed by the contiguous drive-id rewrite
    and every Step-4 marker. The committed corpus is clean (warm
    cache → no real token POST ever recorded), so nothing is broken
    today; PR 2's `EnvRedact` + `FORBIDDEN_ENVELOPE` work (workstream
    B above) closes it before any future cold-cache re-record can
    commit the cid.

**Risks (resolved at implementation).**

- ~~`filter_post_data_parameters` choking on a bytes form body~~ —
  superseded: the filter was rejected outright for its JSON-rewrite
  collateral (see above). The named fallback path was taken.
- Tests reaching into `VCR._build_before_record_request` (private
  API). Accepted: equivalence with vcrpy's real composition is
  exactly the property under test; a vcrpy bump that breaks it should
  break loudly here. Pinned with a comment in the test helper.

---

## PR 2 — profile core, spec 049, ADR-0029, named audit (effort L)

Five workstreams, one PR (backlog decision 5). Suggested commit order
within the PR: A (spec skeleton) → B → C → D → E → A (spec
finalised against what shipped), so the spec is authored against real
shapes, not aspiration.

### A. Spec 049 + ADR-0029 + 048 cross-link

- `sdd/specs/049-live-recording-architecture.md` (new; directory
  default makes it dual, no marker needed). Proposed clause map — the
  implementer owns final wording and numbering:
  - **REC-001 Backend-agnostic recording core.** One orchestrator
    consumes per-backend `CassetteProfile`s; no per-backend
    `build_X_vcr_config` functions. The shared module contains no
    backend-specific constants or helpers.
  - **REC-002 Named redaction rules.** Every body/URI/header scrub is
    a named `RedactPattern` with an audit identity
    (`graph.pii.email_displayname` style) and a declared expectation:
    `required-to-fire` or `opportunistic`.
  - **REC-003 Live-value coverage.** A declared live value
    (`EnvRedact`) must be redacted in request URI, header values,
    request body, response body — bytes and str, case-insensitively
    when declared (the Graph cid lower/upper story).
  - **REC-004 Pre-signed round-trip consistency.** URI, `Location` /
    `Content-Location`, and body rewrite to the *same, valid-URL*
    placeholder; `before_record_request` runs in both modes; the
    BK-262 root cause (`"REDACTED"` is not a URL) is the
    counter-example the clause forbids.
  - **REC-005 Native-filter half and its defence boundary.**
    Request-header deletes and the User-Agent rewrite run through
    vcrpy's `filter_headers`, never touch a `RedactPattern`, and are
    therefore invisible to the named audit; their defence is the
    forbidden-pattern envelope plus per-PR diff review. Named
    explicitly so neither half is assumed to cover the other (backlog
    sketch point 3, second constraint). The clause must also record
    the PR-1 finding that `filter_post_data_parameters` is excluded
    from the native half (vcrpy 8.1.1 re-serialises `application/json`
    POST bodies even on no match): the OAuth POST-param scrub stays in
    the declarative half as named `RedactPattern`s — which means it
    *is* audit-visible, unlike the filing sketch assumed.
  - **REC-006 Scrub audit gate.** Step 4 asserts by rule name;
    `required-to-fire` rules fail at zero, `opportunistic` rules
    don't; exact counts never gate (workload-dependent). The
    env-independent forbidden-pattern byte-scan is hybrid:
    a module-level `FORBIDDEN_ENVELOPE` every profile inherits plus
    per-profile additions (backlog decision 4).
  - **REC-007 Per-backend extension contract.** What a third HTTP
    backend registers (one `CassetteProfile` on its fixtures: filters,
    redactions, presigned predicate, cassette dir, id-aliases,
    `match_on`) and what the core promises in return (directory
    routing, name normalisation, missing-cassette skip, fail-loud
    guard, audit inclusion) — with **no second registration point**.
  - **REC-008 Async-transport capture.** The
    `AsyncioRequestsTransport` shim azure async fixtures inject (vcrpy
    8.1.1's aiohttp stub drops/deadlocks streamed bodies), the no-shim
    story for httpx (vcrpy patches httpx directly; proven by
    `test_httpx_streaming_replay.py`), and the
    `_RS_CASSETTE_RECORDING=1` wiring (backlog decision 3: same spec).
- Spec-marks gate: `scripts/check_spec_marks.py` discovers `REC-\d+`
  automatically (no prefix list to extend) and will require a
  `@pytest.mark.spec("REC-NNN")` test per clause. REC-001/002/003/004
  /005/006/007 map onto the reworked `test_cassettes.py` +
  `tests/scripts/test_record_cassettes.py` tests; REC-008 maps onto
  `test_httpx_streaming_replay.py` and the azure async replay tests —
  or, if a clause ends up purely descriptive, add it to
  `_ALLOWLIST_DESIGN` with rationale. Decide per clause; don't
  blanket-allowlist.
- `sdd/specs/048-testing-architecture.md` — TEST-007's
  "Implementation choice" paragraph gains "See spec 049" (the
  deferral's landing site).
- `sdd/adrs/0029-cassette-recording-architecture.md` (new, after
  ADR-0028): the decision record for declarative profiles over
  per-backend config functions; consequences include the
  REC-005 defence split and the no-re-record migration constraint.
- Docs plumbing: `hatch run gen-graph` (graph.json picks up new
  docs nodes), `hatch run docs-gate` for links/bridge. Existing
  `sdd/specs/` + `sdd/adrs/` directory defaults handle classification.

### B. The declarative core (`_cassettes.py` rewrite)

New shapes (frozen dataclasses, names indicative):

- `RedactPattern(name, pattern: re.Pattern[bytes], replacement: bytes,
  expectation: Literal["required-to-fire", "opportunistic"])` —
  replaces `_BODY_SCRUB`, `_GRAPH_BODY_SCRUB`, `_GRAPH_PII_BODY_SCRUB`
  *and* `_GRAPH_REQUEST_BODY_SCRUB` (the OAuth POST-param scrub stays
  declarative; PR 1 rejected its native-filter migration — see PR 1).
  Bytes-domain; the core owns the encode/decode dispatch for str
  bodies (today duplicated in both builders).
- `EnvRedact(name, resolve, fake, case_insensitive=False)` — per
  cross-cutting decision 1. Azure: account name via
  `parse_account_name(live_connection_string())`. Graph:
  `GRAPH_DRIVE_ID`, case-insensitive. The core applies it across URI,
  rewrite-listed header values, request body, response body, bytes +
  str — replacing today's hand-woven `real_account` /
  `_drive_id_re_*` threading. **Must also match the hyphen-split
  GUID/oid form of the Graph cid** (PR-1 dogfood finding, see PR 1
  verification): the contiguous `re.escape(drive_id)` rewrite misses
  the cid when it rides the oid low-64-bits inside the
  `X-AnchorMailbox: Oid:…-XXXX-XXXXXXXXXXXX@…` *request header* on the
  MSAL `grant_type=refresh_token` POST. The EnvRedact must additionally
  scrub the **request-header values** of the Graph profile (today only
  the Azure `x-ms-*-source` rewrites touch request headers), and the
  Graph profile should just **delete `X-AnchorMailbox`** outright (the
  backend never reads it on replay) — belt and braces.
- `CassetteProfile` — per backend family. Field inventory (everything
  the two builders + conftest tables currently encode):
  `backend` name; `cassette_dir`; `fixture_aliases`
  (`{"azure_live": "azure", "azure_replay": "azure", ...}` — replaces
  `_CASSETTE_ID_ALIASES` *and* `_FIXTURE_CASSETTE_DIRS`);
  `filter_headers` / `filter_query_parameters` (the native half,
  from PR 1; no `filter_post_data_parameters` — rejected in PR 1);
  `response_header_deletes`; `response_header_rewrites` (the
  `x-ms-copy-source` / `Location` handling, host-aware);
  `presigned_host_predicate` + `presigned_placeholder` (None for
  Azure); `uri_rewrites` (filesystem-uuid, tmp-uuid,
  conformance-root patterns as named `RedactPattern`s in the str
  domain); `request_body_redactions` / `response_body_redactions`
  (lists of `RedactPattern`); `env_redacts`; `forbidden_patterns`
  (per-profile additions to `FORBIDDEN_ENVELOPE`); `match_on`
  (default None = vcrpy default; BK-262's flirtation with a custom
  matcher gets a declared home).
- `build_profile_vcr_config(profile, record_mode) -> dict` — the one
  generic factory. Its `before_record_request` /
  `before_record_response` implement, once: bytes/str dispatch,
  list-vs-scalar header values, presigned-host collapse, and the
  REC-004 cross-field invariant (URI ↔ `Location` ↔ body to the same
  placeholder, request hook active in both modes).
- `FORBIDDEN_ENVELOPE` — module-level: the universal markers of
  today's `GRAPH_FORBIDDEN_CASSETTE_PATTERNS` (bare non-redacted
  `Bearer`, bare JWT `eyJ…`, bare email, unredacted credential forms);
  Graph's profile keeps its specifics (`docID` site-GUID host form,
  long `b!…` id, tenant SharePoint host, identity keys). #787's merge
  already centralised the combined tuple in `_cassettes.py` as the
  single source for the recorder's Step-4 gate AND the creds-free CI
  sweep (`TestGraphCommittedCassettePIISweep`) — the split into
  envelope + profile additions must keep feeding **both** consumers,
  and the CI sweep generalises to iterate every registered profile
  with a non-empty cassette dir, not just Graph. Likewise the
  `id_token` / `client_info` token-response redaction and the
  pre-signed `Host`-header rewrite are review-hardened guarantees the
  profile declarations must reproduce, not regress. **Add an
  oid-anchor forbidden marker** (`Oid:[0-9a-f-]{36}` or tighter) so a
  cold-cache re-record that captures the MSAL refresh POST cannot
  silently commit the cid via `X-AnchorMailbox` — the gap the PR-1
  dogfood found, which today's contiguous-cid markers miss.

The behaviour bar: every redaction the two builders perform today is
reproduced exactly — the reworked PR-1 unit tests (which assert
through the composed pipeline) carry over and **must not lose a single
assertion**. Diff the old builders against the profile declarations
side by side in review.

### C. Registration + conftest delegation

- `tests/backends/fixtures/registry.py` — add
  `cassette_profile: CassetteProfile | None = None` to
  `BackendFixture` (like `capabilities` / `marks`; non-HTTP fixtures
  leave it None). Docstring points at REC-007.
- `tests/backends/fixtures/{azure_live,azure_live_async,azure_replay,azure_replay_async}.py`
  and `{graph_live,graph_replay}.py` — pass their family's profile
  object (defined in `_cassettes_azure.py` / alongside the graph
  scrub declarations) at `register(...)` time.
- `tests/backends/conformance/conftest.py` — delete
  `_CASSETTE_ID_ALIASES` and `_FIXTURE_CASSETTE_DIRS`; build one
  `fixture_id → (profile, canonical_alias)` map from
  `all_fixtures()` at import. **All four consumers** route through it
  (the backlog's explicit completeness requirement): `vcr_cassette_dir`
  (sync + async), `default_cassette_name` /
  `_normalise_cassette_name`, the missing-cassette skip hook
  (`_cassette_path_for_item` / `_cassette_dir_for_node_name`), and the
  fail-loud "vcr-marked but unregistered" guards in both
  `vcr_cassette_dir` and `vcr_config`. `vcr_config` itself collapses
  to: look up profile, `return build_profile_vcr_config(profile,
  record_mode)`; `_real_azure_account` / `_real_graph_drive_id` move
  into the profiles' `EnvRedact.resolve` callables.
  (`_AZURE_REAL_FIXTURE_IDS` / the HNS-xfail roster is adjacent
  machinery, not cassette routing — leave it.)
- Registry import-order note: conftest currently imports `_cassettes`
  constants directly; after the change it must not import profiles
  before the per-backend fixture modules have registered (the
  `tests.backends` conftest already imports each module for
  side-effectful registration — verify the conformance conftest builds
  its map lazily or after those imports).

### D. Azure helper relocation

`live_connection_string`, `parse_account_name`, `FAKE_CONN_STR`,
`FAKE_ACCOUNT`, `FAKE_FILESYSTEM`, `_FAKE_KEY`, `_AZURITE_FRAGMENTS`
move to `tests/backends/fixtures/_cassettes_azure.py` (new), leaving
`_cassettes.py` backend-agnostic (Graph declarations move next to the
graph profile in the same file or a `_cassettes_graph.py` twin —
implementer's call, symmetric either way). Update all importers:

- `tests/backends/fixtures/azure_replay*.py` (`FAKE_CONN_STR`)
- `tests/backends/conformance/conftest.py` (resolver relocation, § C)
- `scripts/record_cassettes.py` (`_AZURITE_FRAGMENTS`,
  `parse_account_name` in `_resolve_azure_account`)
- `tests/backends/fixtures/test_cassettes.py` import paths

Grep for `from tests.backends.fixtures._cassettes import` and
`_cassettes.` across the tree before claiming done (principle 2).

PR #791 review round 2 (user decision: handle here, not PR 1) adds two
obligations to this workstream:

- **Azure-first naming.** Relocation is the primary answer: once
  `FAKE_ACCOUNT` / `FAKE_FILESYSTEM` live in `_cassettes_azure.py`,
  Azure-flavored placeholder values are domain vocabulary, not history.
  Decide there whether the *values* also rename (`azreplay` →
  `rsreplay`; account names allow lowercase alphanumerics only, so
  `rs_replay` / `stage3_replay` are invalid shapes). A value rename
  rewrites all 303 committed Azure cassettes — if taken, it must be one
  isolated, purely-textual commit so cross-cutting decision 5 ("the
  corpus is the oracle") stays reviewable, and the "zero cassette files
  modified" acceptance criterion gains that single explicit exception.
- **Remaining comment bulk.** The round flagged the file's
  over-documentation generally (CONTENT-RULES); PR 1 fixed the four
  flagged sites. The rewrite must land the surviving long rationales
  (response-header roster, `GRAPH_PRESIGNED_PLACEHOLDER`, forbidden
  markers) in spec 049 / ADR-0029 clauses, leaving code comments to
  state constraints only.

### E. Step-4 named-pattern audit (`scripts/record_cassettes.py`)

- Steps 2–3 export `_RS_SCRUB_MANIFEST` (cross-cutting decision 2);
  the core appends per-rule fire counts; Step 4 loads the manifest,
  prints `rule_name: N occurrences` per rule, fails any
  `required-to-fire` rule at zero. In `--verify-only` / `--node` mode
  the manifest half is skipped (printed as such), the byte-scan half
  runs always.
- The byte-scan half iterates `FORBIDDEN_ENVELOPE` + the profile's
  `forbidden_patterns` (the `GRAPH_FORBIDDEN_CASSETTE_PATTERNS` tuple
  the script already imports from `_cassettes.py` splits along that
  line; the creds-free CI sweep keeps consuming the same combined
  view, generalised over profiles).
- `_BACKENDS` keeps only CLI/workflow facts (k-filters, opt-in env,
  setup doc, `min_cassettes`); cassette dir + scrub knowledge come
  from the profile registry (the script already sys.path-inserts the
  repo root and imports from the fixtures package).
- Expectation calibration from BK-262's known corpus: the OAuth
  POST-param scrubs (named `RedactPattern`s after PR 1's
  native-filter rejection) and the error-XML `RequestId:`/`Time:`
  scrubs are `opportunistic` (documented zero-hit cases); the bearer
  body scrub, downloadUrl/uploadUrl placeholders, the
  `id_token`/`client_info` token-response scrub, drive-id and
  account/filesystem env-redacts are `required-to-fire` on a
  full-slice recording (token-response: required only if a token POST
  was recorded — calibrate against the corpus before wiring).
- `tests/scripts/test_record_cassettes.py` — extend: manifest
  read/gate logic, required-vs-opportunistic behaviour, verify-only
  skip path, envelope + profile-additions merge.

### PR 2 acceptance criteria

- **The corpus is the oracle:** full Stage-1 `azure_replay*` +
  `graph_replay` conformance green against unchanged committed
  cassettes; `record_cassettes.py --verify-only` green for both
  backends; zero cassette files modified in the PR diff
  (cross-cutting decision 5).
- Old assertions preserved: every pre-existing scrub test passes
  against the profile-built configs; the fail-loud unregistered-vcr
  guard still raises (unit test it via a fake vcr-marked node name).
- New surface tested: profile registry lookup (incl. a fixture with
  `cassette_profile=None` is invisible to routing), `RedactPattern`
  expectation semantics, `EnvRedact` URI/header/body/bytes/str/
  case-insensitive coverage matrix (REC-003 as a parametrised test),
  REC-004 round-trip test (port
  `test_downloadurl_body_value_replays_against_recorded_request` to
  the generic core).
- `scripts/check_spec_marks.py` (via `hatch run lint`) green with
  every REC-NNN either marked or rationale-allowlisted; docs-gate
  green; `hatch run all` green.
- Spec 048 cross-link in place; ADR-0029 status Accepted; trace
  updated (gates read, surprising ripples, co-shipped items);
  BK-284 → `BACKLOG-DONE.md` + `gen-backlogid`; **this plan file
  deleted**.

### PR 2 risks / surprises to budget

- **Cassette-matching regressions are the headline risk.** Any drift
  in URI normalisation order (e.g. tmp-uuid rewrite before vs after
  env-redact) changes the request key and breaks replay. Mitigation:
  the generic core applies rewrites in a documented, profile-declared
  order; the unchanged-corpus acceptance bar catches every miss.
- **pytest-recording internals.** `vcr_cassette_dir` /
  `default_cassette_name` override names are plugin contract; the
  rewrite keeps those fixture names and only changes what feeds them.
  Pin the pytest-recording version assumption in the trace if it
  bumps mid-work.
- **Manifest plumbing across subprocesses** (decision 2): xdist
  workers each write counts — aggregate per-worker files
  (`manifest-<worker>.json`) or run recording non-parallel (recording
  already runs `-m live` serially today; confirm and document).
- **Scope creep into BK-283.** Example-test replay extension is
  explicitly out (independent item); the extension contract (REC-007)
  must be written so BK-283 can consume it without amendment, but no
  BK-283 code lands here.

---

## Verification matrix

| Gate | PR 1 | PR 2 |
|---|---|---|
| `hatch run all` (pre-commit gate) | ✓ | ✓ |
| Stage-1 replay slices vs unchanged corpus | ✓ | ✓ |
| `record_cassettes.py --verify-only` (azure + graph) | ✓ live | creds-gated |
| Creds-free CI PII sweep over committed cassettes | ✓ | ✓ (per profile) |
| Composed-pipeline scrub unit tests | ✓ (introduced) | ✓ (carried) |
| `check_spec_marks.py` REC coverage | — | ✓ |
| `hatch run docs-gate` + `gen-graph` | — | ✓ |
| Single-node live re-record byte-diff | ✓ live (both backends) | — |
| Trace shipped in-PR | ✓ | ✓ |

## Ripple-check obligations (read before each PR)

Per principle 2, consult `sdd/CLAUDE-REFERENCE.md` Pre-work index
before starting and the Detailed checklist before committing. Rows
known to fire here: **Spec section** (REC-NNN ↔
`@pytest.mark.spec` ↔ BACKLOG), **Backlog item touched** (live
trace mandatory), **New test file** (none expected to be
OS-sensitive). `FEATURES.md` is untouched (no capability change);
CHANGELOG N/A both PRs.
