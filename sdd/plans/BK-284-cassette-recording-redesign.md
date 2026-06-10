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
(`bk-262-graph-cassettes`) merges**. That PR creates
`_GRAPH_PII_BODY_SCRUB` (the fourth scrub list), the Step-4
`forbidden_patterns` gate in `scripts/record_cassettes.py`, the
`graph_live` / `graph_replay` fixtures, and the 118-cassette Graph
corpus this refactor must keep replaying. As of this plan's authoring,
PR #787 is **open**: neither BK-284 PR can branch from or merge to
master before it lands. Re-verify file/line references against the
merged tree before starting; if #787 changed in review, the references
here are stale, not the design.

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

## PR 1 — vcrpy-native filter migration (warm-up, effort S)

**Scope.** Move the scrubs vcrpy ships native filters for out of the
hand-rolled `before_record_*` callbacks, in both `build_vcr_config`
and `build_graph_vcr_config`. Pure behaviour-preserving refactor of
`_cassettes.py` + its unit tests; no cassette file changes, no
conftest changes, no new concepts.

**The migration map.**

| Today (hand-rolled) | After PR 1 (vcr-native) |
|---|---|
| `_SCRUB_REQUEST_HEADERS` delete loop (azure) | `filter_headers=["authorization", "x-ms-date", "x-ms-client-request-id", "cookie"]` |
| `_GRAPH_SCRUB_REQUEST_HEADERS` delete loop | `filter_headers=["authorization", "cookie", "client-request-id"]` |
| `user-agent` rewrite branch (both) | tuple form appended: `("user-agent", "azsdk-python-replay")` |
| `_GRAPH_REQUEST_BODY_SCRUB` regex list | `filter_post_data_parameters=[("client_secret", "REDACTED"), ("client_assertion", "REDACTED"), ("assertion", "REDACTED"), ("refresh_token", "REDACTED")]` |

Tuple form is load-bearing on both rows (backlog decision 5): list
form would *delete* the header value pair / POST parameter, where
today's behaviour keeps the key and replaces the value
(`client_secret=REDACTED`), and deletion would break the
byte-identity claim on the first re-record diff.

**What stays custom, on purpose** (vcrpy has no native equivalent):

- Azure: `x-ms-rename-source` / `x-ms-copy-source` request-header
  *rewrites* (account + filesystem + tmp-uuid normalisation), the URI
  rewrites, all of `before_record_response` (response-header deletes
  and rewrites, body scrubs — vcrpy has no response-side filters).
- Graph: the pre-signed-host URI collapse, drive-id / conformance-root
  rewrites, the request-body **drive-id** rewrite (the OAuth-param
  half leaves; the JSON `parentReference` rewrite stays), and all of
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

- `tests/backends/fixtures/_cassettes.py` — both config builders;
  delete `_GRAPH_REQUEST_BODY_SCRUB`; module docstring updated to name
  the native/custom split.
- `tests/backends/fixtures/test_cassettes.py` — **the load-bearing
  test rework.** Today's security-gate tests call
  `cfg["before_record_request"]` directly; after PR 1 that callable no
  longer drops `Authorization`, so the tests would fail (or worse,
  be weakened to pass). Rework them to exercise the *composed*
  pipeline the way vcrpy does — build `vcr.VCR(**cfg)` and obtain the
  composed filter via `_build_before_record_request()` — so the gate
  asserts what a real recording run does. Add: a mixed-case
  `AUTHORIZATION` deletion test (confirms vcrpy's filter is
  case-insensitive like today's `.lower()` loop); a bytes-body and a
  str-body OAuth POST test through the composed chain (confirms
  `filter_post_data_parameters` handles both body types MSAL can
  send); a native-before-custom ordering smoke test.

**Acceptance criteria.**

- All existing scrub assertions pass through the composed pipeline —
  same secrets in, same redactions out, for every test in
  `TestGraphCassetteScrub` and the azure scrub tests.
- `hatch run all` green; `graph_replay` and `azure_replay*` Stage-1
  conformance slices pass against the **unchanged** committed corpus.
- `python scripts/record_cassettes.py --backend graph --verify-only`
  and `--backend azure --verify-only` pass (steps 4–5 on the existing
  corpus).
- Optional, requires live creds: one `--node` single-cassette
  re-record per backend; diff shows byte-identical output modulo
  nothing (the filter-source change must not alter recorded bytes).
  If no live access, state so in the PR per the dogfood-honesty rule.

**Risks.**

- `filter_post_data_parameters` choking on a bytes form body
  (vcrpy parses form bodies; MSAL may send `str` or `bytes`). The new
  unit tests catch this before any recording does; fallback is keeping
  the bytes-domain regex for the body and migrating only headers —
  record the divergence in the trace and the backlog entry.
- Tests reaching into `VCR._build_before_record_request` (private
  API). Accepted: equivalence with vcrpy's real composition is
  exactly the property under test; a vcrpy bump that breaks it should
  break loudly here. Pin with a comment.

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
    Request-header and POST-param scrubs run through vcrpy's
    `filter_headers` / `filter_post_data_parameters`, never touch a
    `RedactPattern`, and are therefore invisible to the named audit;
    their defence is the forbidden-pattern envelope plus per-PR diff
    review. Named explicitly so neither half is assumed to cover the
    other (backlog sketch point 3, second constraint).
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
  (PR 1 already removed `_GRAPH_REQUEST_BODY_SCRUB`). Bytes-domain;
  the core owns the encode/decode dispatch for str bodies (today
  duplicated in both builders).
- `EnvRedact(name, resolve, fake, case_insensitive=False)` — per
  cross-cutting decision 1. Azure: account name via
  `parse_account_name(live_connection_string())`. Graph:
  `GRAPH_DRIVE_ID`, case-insensitive. The core applies it across URI,
  rewrite-listed header values, request body, response body, bytes +
  str — replacing today's hand-woven `real_account` /
  `_drive_id_re_*` threading.
- `CassetteProfile` — per backend family. Field inventory (everything
  the two builders + conftest tables currently encode):
  `backend` name; `cassette_dir`; `fixture_aliases`
  (`{"azure_live": "azure", "azure_replay": "azure", ...}` — replaces
  `_CASSETTE_ID_ALIASES` *and* `_FIXTURE_CASSETTE_DIRS`);
  `filter_headers` / `filter_post_data_parameters` /
  `filter_query_parameters` (the native half, from PR 1);
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
- `FORBIDDEN_ENVELOPE` — module-level: bare non-redacted `Bearer`,
  generic `email@host` form, common token shapes. Graph's profile adds
  the `docID` site-GUID host form and the long `b!…` id (today in
  `record_cassettes.py`'s `_BACKENDS["graph"]["forbidden_patterns"]`,
  which moves here).

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

### E. Step-4 named-pattern audit (`scripts/record_cassettes.py`)

- Steps 2–3 export `_RS_SCRUB_MANIFEST` (cross-cutting decision 2);
  the core appends per-rule fire counts; Step 4 loads the manifest,
  prints `rule_name: N occurrences` per rule, fails any
  `required-to-fire` rule at zero. In `--verify-only` / `--node` mode
  the manifest half is skipped (printed as such), the byte-scan half
  runs always.
- The byte-scan half iterates `FORBIDDEN_ENVELOPE` + the profile's
  `forbidden_patterns` (now sourced from the profile, deleting the
  hand-maintained tuple in `_BACKENDS["graph"]`).
- `_BACKENDS` keeps only CLI/workflow facts (k-filters, opt-in env,
  setup doc, `min_cassettes`); cassette dir + scrub knowledge come
  from the profile registry (the script already sys.path-inserts the
  repo root and imports from the fixtures package).
- Expectation calibration from BK-262's known corpus: the OAuth
  POST-param scrubs and the error-XML `RequestId:`/`Time:` scrubs are
  `opportunistic` (documented zero-hit cases); the bearer body scrub,
  downloadUrl/uploadUrl placeholders, drive-id and account/filesystem
  env-redacts are `required-to-fire` on a full-slice recording.
  Note: OAuth params are native-filter territory after PR 1 and never
  reach the named registry at all (REC-005).
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
| `record_cassettes.py --verify-only` (azure + graph) | ✓ | ✓ |
| Composed-pipeline scrub unit tests | ✓ (introduced) | ✓ (carried) |
| `check_spec_marks.py` REC coverage | — | ✓ |
| `hatch run docs-gate` + `gen-graph` | — | ✓ |
| Single-node live re-record byte-diff | optional (creds) | — |
| Trace shipped in-PR | ✓ | ✓ |

## Ripple-check obligations (read before each PR)

Per principle 2, consult `sdd/CLAUDE-REFERENCE.md` Pre-work index
before starting and the Detailed checklist before committing. Rows
known to fire here: **Spec section** (REC-NNN ↔
`@pytest.mark.spec` ↔ BACKLOG), **Backlog item touched** (live
trace mandatory), **New test file** (none expected to be
OS-sensitive). `FEATURES.md` is untouched (no capability change);
CHANGELOG N/A both PRs.
