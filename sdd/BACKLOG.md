# Development Backlog
<!-- doc: repo-only -->

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Ordering:** within each topic group, higher-priority or blocking items come first.

**Item scope:** idea + decision-relevant constraints + open questions.
Do not repeat process steps (those live in `sdd/000-process.md` and the ripple-check table).
Existing items may be more verbose — trim on next touch.

**Item attributes:** each item carries a compact `spec: · effort: · audience:` line for quick scanning.
Effort: S = <1 day · M = 1–3 days · L = >3 days. `—` = not applicable.

**Completing work:**

- Fully done → delete from here, add to `BACKLOG-DONE.md` as `[x]`
  (same commit as the code change).
- Partially done → split: ship the done part to `BACKLOG-DONE.md` as `[x]`
  under its original ID, create a new ID here for the remaining work, and
  link both.

**ID prefixes:**

| Prefix | Meaning |
|--------|---------|
| `BL-NNN` | Release blocker — must resolve before next PyPI publish. Monotonic, not reset per release. |
| `BK-NNN` | Committed backlog work, queued behind blockers. |
| `BUG-NNN` | Confirmed defect with reproduction steps. |
| `ID-NNN` | Idea — not evaluated, not committed to. |
| `AF-NNN` | Audit finding (retired — use `BUG` or `BK` for new items). |

**Assigning a new ID:** check `sdd/backlogid.json` (max per prefix from BACKLOG-DONE.md)
and the highest ID already in this file, then take the next integer. Run
`hatch run gen-backlogid` after moving items to BACKLOG-DONE.md to keep the JSON current.
`hatch run lint` flags drift and collisions.

---

## Release Blockers

*(none)*

---

## SFTP

- [ ] **ID-181 — Per-backend `ssh-rsa` opt-in via `paramiko.Transport` subclass**
  spec: SFTP-007 · effort: M · audience: user.api
  `SFTPUtils.enable_ssh_rsa_compat()` mutates paramiko's class attributes
  so every `Transport` instance in the process accepts SHA-1 host keys
  thereafter. For single-server use cases this is fine and documented as
  a security tradeoff. For processes that talk to a mix of modern and
  legacy SFTP backends (e.g. a Dagster job, a multi-tenant pipeline),
  the shim leaks SHA-1 acceptance into every other transport. A
  per-backend escape hatch would scope the tradeoff to one backend.
  Sketch: `BackendConfig(type="sftp", options={..., "allow_legacy_ssh_rsa": True})`
  constructs a `Transport` subclass whose instance-level `_preferred_keys`
  / `_preferred_pubkeys` include `ssh-rsa`, leaving `paramiko.Transport`
  class attrs untouched. `Transport._key_info` and `RSAKey.HASHES` are
  read at class scope so they still need a module-level patch — but
  those are algorithm-name → impl lookup tables, not security policy.
  Surfaced during BK-198 (PR 613) review.

---

## Azure

- [ ] **ID-198 — Medallion Dagster + Azure HNS live showcase validation run**
  spec: — · effort: S · audience: library.maintainer, user.api
  The `examples/medallion_dagster/` showcase demonstrates a realistic user journey
  combining Dagster orchestration with an Azure HNS backend, but has never executed
  against a live ADLS Gen2 account. Run the full example end-to-end against real cloud
  infrastructure to surface testing gaps, implementation TODOs, or edge cases that
  conformance and unit tests miss. Async patterns are settled (ID-193 landed,
  see BACKLOG-DONE.md). Findings inform the next release scope; no code changes
  are produced by this item itself.

---

## Graph

ID-127 (Microsoft Graph / OneDrive / SharePoint) follow-ups, in execution order;
full findings in [audit-016](audits/audit-016-graph-backend-review.md).
**Order:** load-bearing CI coverage (BK-262) → cheap spec/doc fixes (BK-264/265) →
correctness + tests (BK-266/267) → blocked or hygiene tail (BK-259/261/268). Each
item's own rationale lives in its body. (Security item BK-263 — the upload-session
credential leak — shipped first; see BACKLOG-DONE.md.)

- [ ] **BK-262 — Graph conformance cassettes: replay-able pre-signed URLs**
  spec: GR-015, GR-019 · effort: M · audience: infra.test
  ID-127 GR-DONE recorded the Graph conformance suite live (green, 109/0/9) but
  the cassettes are **not committed**, and `record_cassettes.py` keeps
  `min_cassettes=0` for graph (no committed cassette under
  `tests/backends/cassettes/graph/`). Replaying reads/writes fails because the
  GR-035 scrub redacts `@microsoft.graph.downloadUrl` (read) and the upload-session
  `uploadUrl` (write) to the bare string `"REDACTED"`, which is not a URL the
  backend can `GET`/`PUT` on replay (it issues `GET :///REDACTED` → no cassette
  match; the read conformance slices write-then-read, so they hit it too). The
  token also rides the request *query* on those pre-signed hosts, so a naive
  host+path+query match would either leak the token (if kept) or fail to match (if
  filtered asymmetrically between record and replay). The GR-FOUNDATION streaming
  proof never exercised this because it recorded and replayed the **same** URL.

  **Solution sketch (decide when picked up):** redact pre-signed URLs (downloadUrl
  / uploadUrl / `Location`) to a **valid placeholder URL** (e.g.
  `https://graph-download.invalid/REDACTED`) — or, equivalently, wipe the *query
  only* (preserve host+path, mirroring the existing `Location`-header scrub) via a
  `before_record_request` that normalises the query to empty on the
  non-`graph.microsoft.com` pre-signed hosts (so record and replay agree) and/or a
  custom `match_on` that ignores the query for those hosts — consistently in
  response bodies, the `Location` header, and the recorded pre-signed-host
  **request** URIs, so `graph_replay` matches the recorded (rewritten) request:
  the same full redaction, just replay-able. Then re-record, validate Stage-1
  replay, raise `scripts/record_cassettes.py` graph `min_cassettes` off `0` (see
  the Audit-016 note below), move the slices off the missing-cassette skip, and
  commit the cassettes so the cross-backend conformance spine runs for Graph in CI
  (today it skips-clean). Watch for vcr replay-ordering on multiple same-placeholder
  `GET`s within one cassette. Prerequisite scrub infra (vcr-mark hook extended to
  `graph_live`, request-body `drive_id` scrub, per-test `base_path` uuid scrub,
  `graph_replay` `base_path`) already landed in the ID-127 GR-DONE PR. Until then
  the live device-code probe (`tmp/validate_graph_*_live.py`) is the Stage-3
  reality-check (the GR-TRANSFER precedent). Touches
  `tests/backends/fixtures/_cassettes.py`,
  `tests/backends/conformance/conftest.py`, `scripts/record_cassettes.py`, and the
  recorded cassette tree. Discovered in ID-127 GR-WRITE; re-confirmed in GR-DONE.
  (Consolidates the former BK-260, retired into this item per PR #770 review.)

  **Extension (example tests, ID-127 GR-DOCS-E2E review, PR #764):** the same
  recorded cassettes could drive the env-gated `examples/backends/graph_backend.py`
  snippet, which today only runs under live credentials (and is excluded from the
  `run_examples.py` CI sweep entirely). Once the pre-signed-URL replay above is
  solved, a replayed variant could exercise the example in CI without creds —
  same blocker, second beneficiary. Gated on the solution sketch landing first.

  **Audit-016 (H2):** until cassettes land, the Graph conformance matrix is 100%
  skip in CI *and* the integration/live tier (GR-007/020/026/034/054 + the 10 MiB
  round-trip) runs in no lane — so the only *automated* coverage is the ~300 respx
  unit tests (the code was live-validated per-PR during implementation, but
  manually — no CI gate captures it; the first live run of the conformance
  *matrix* at GR-DONE proved those mocks wrong in 23/118 cases). Raising
  the `min_cassettes` floor off `0` is part of this work for a second reason: at
  `0` the record gate *warns* but does not *fail* on an empty corpus
  (`record_cassettes.py:329-337` prints a loud zero-cassette WARNING, but it is
  non-fatal), so the fix should promote that existing warning to a hard failure
  rather than add a redundant one. The spec-honesty disclosure of this gap is
  tracked in BK-264.

- [ ] **BK-264 — Graph spec / RFC reality-sync**
  spec: GR-001, GR-005, GR-018, GR-019, GR-034 · effort: S · audience: library.maintainer
  Sweep `sdd/specs/044-graph-backend.md` + `sdd/rfcs/rfc-0010-graph-backend.md`
  where the spec lags shipped code (all `sdd/`-only):
  - GR-018 / GR-019 say `WriteResult.size` comes from the driveItem body, but the
    code uses the written byte count (the better choice — amend the spec, not the
    code; principle 5).
  - `base_path` (GR-058) is missing from the GR-001 signature block and the GR-005
    validation list, and unmentioned in the RFC.
  - The Integration-only env-var list and RFC Stage 3 describe a client-credentials
    tier (4 vars incl. `GRAPH_CLIENT_SECRET`); the shipped tier is
    device-code / consumer (3 vars, no secret).
  - GR-034's "Retry-After propagated via the error's context" describes a surface
    that does not exist — reword to the in-loop honouring that GR-048 already
    states correctly.
  - Disclose in the Integration-only section that the conformance matrix is
    skip-only and the integration tier never runs in automated CI, and that the
    live tier is consumer-OneDrive-only (no SharePoint/business coverage).
  Audit-016 M1 / M2 / M3 / L4 / L6 / H2.

- [ ] **BK-265 — Graph guide & docstring accuracy**
  spec: GR-058, GR-001 · effort: S · audience: user.api, user.site
  User-facing doc fixes (M4 / M5 are the cheapest, highest-value):
  - `graph-setup.md` is written in the future tense ("the forthcoming Graph backend
    will…") and steers readers to hand-roll `msal` instead of the shipped
    `pip install "remote-store[graph]"` + `GraphUtils.resolve_drive_id` — rewrite to
    present tense, reframe the hand-rolled snippet as an alternative.
  - The `graph.md` headline Usage snippet calls the sync `resolve_drive_id` (which
    runs `asyncio.run`) inside an `async with`, so it throws `RuntimeError` on
    copy-paste — fix to `await aresolve_drive_id` or resolve outside the async scope
    (the runnable example already does it right).
  - Add an async-vs-sync extension note/matrix: a native-async Graph consumer has no
    `ext.*` surface (only `aio.ext.write`).
  - Complete the `Raises:` clauses (`PermissionDenied`, consistent
    `BackendUnavailable`) across public methods.
  - Add a "verified against consumer OneDrive; SharePoint/business less exercised"
    caveat, and note read-side `TMPDIR` spooling for large arrow/parquet reads.
  Audit-016 M4 / M5 / M6 / L5 / L6 / L9.

- [ ] **BK-266 — Graph backend correctness edges**
  spec: GR-031, GR-044 · effort: S · audience: user.api, library.maintainer
  Three small, independent fixes (split if preferred):
  - Scope the `resourceNotFound`→`BackendUnavailable` mapping to drive scope so it
    cannot escape `exists()` / `is_file()` / `is_folder()` when seen at item scope
    (`http.py:124`, GR-031).
  - Normalise paths before the self-op `src == dst` short-circuit, or document that
    GR-044 assumes Store-normalised input — direct-to-backend `copy("/a.txt",
    "a.txt")` skips the no-op today (`backend.py:_short_circuit_self_op`).
  - Decide whether the bundled `GraphAuth.get_token` should raise a
    `RemoteStoreError` subtype instead of stdlib `PermissionError` (`auth.py:184`),
    which currently propagates through `read` / `write` uncatchable by
    `except RemoteStoreError`.
  Audit-016 L1 / L3 / M7.

- [ ] **BK-267 — Graph test hardening**
  spec: GR-012, GR-040 · effort: S · audience: infra.test
  Close respx-tier gaps in the sole-coverage suite:
  - Pin `read()` first-iteration failure timing — assert no bytes are yielded
    before the `NotFound` / `InvalidPath` raise (the async-generator body defers;
    `test_read.py:207` does not catch this).
  - Add a direct `write_atomic` failure-path test (today only delegation is
    asserted).
  - Add at least one per-method `403`→`PermissionDenied` test, or document the
    centralised-mapping rationale.
  Audit-016 L7.

- [ ] **BK-259 — Graph `_range_fallback_paths` flag: scope to operation, not backend lifetime**
  spec: GR-015 · effort: S · audience: user.api, library.maintainer
  `GraphBackend._range_fallback_paths` is a per-instance `set[str]`: a range
  read that falls back (a SharePoint drive ignored/rejected `Range`) records the
  path, and `get_file_info` then flags `extra["graph.read.range_fallback"] = True`
  on any `FileInfo` it returns for that path. The set only grows; nothing clears
  it. Two problems, surfaced in PR #760 review:
  - **Unbounded memory.** A long-lived backend that range-reads many distinct
    range-incapable paths holds one key per path for the instance lifetime.
    Bounded in practice by *distinct range-failing paths* (fallback is the rare
    misconfigured-SharePoint case), not by total reads — but unbounded in
    principle.
  - **Semantics vs spec.** GR-015 scopes the flag to "any `FileInfo` returned
    for the same item **within the operation context**." A per-backend set marks
    the path *permanently*: a later non-range `get_file_info`, or a read that did
    not fall back, still reports the stale flag. If range behaviour is
    per-request / tenant-config rather than a permanent drive property, this
    misleads.

  **Why it exists this way:** `read` / `_read_bytes` return bytes, and the
  backend has no `StoreEvent` / operation handle (the OBS-layering constraint
  GR-015 itself calls out — the proxy builds `StoreEvent` before the inner call,
  so the backend cannot inject into it). A per-backend set is the only channel
  that survives from a range read to a later `get_file_info`. The WARNING log
  (`graph.read.range_fallback` marker) is the always-reachable signal;
  `FileInfo.extra` is the spec-mandated but architecturally-awkward second one.

  **Solution space (decide when picked up):**
  1. **Self-healing flag (lean).** Clear the path from the set when a later
     ranged read on it succeeds (`206`), so the flag tracks the most-recent
     outcome instead of "ever failed." Small change; risk: flapping if a drive
     answers ranges inconsistently. Needs `stream_range` to signal range-success
     back (a second callback / return flag, mirroring `on_fallback`).
  2. **Bound the set.** A `TTLCache` / LRU caps memory and ages out stale marks,
     accepting staleness within the window. Fixes memory; only partly fixes the
     stale-semantics point.
  3. **Soften the spec.** If the marker is genuinely a backend-lifetime *hint*
     and not operation-scoped, amend GR-015's "within the operation context"
     wording to match reality and document the limitation. Pairs with (1).
  4. **Native-async observability.** Deliver the signal through the proper event
     channel once an async observe/otel surface exists — GR-015 already defers
     native-async observability as "a separate, unscheduled item"; the flag would
     then ride `StoreEvent.metadata` with true operation scope.

  Leaning **(1) + (3)**: self-heal on a successful ranged read and align the
  spec wording, with **(4)** as the eventual proper home. Touches
  `src/remote_store/aio/backends/_graph/{backend,transfer}.py`,
  `tests/backends/graph/aio/test_transfer.py`, and
  `sdd/specs/044-graph-backend.md` (GR-015). Discovered in PR #760 (ID-127
  GR-TRANSFER) review.

- [ ] **BK-261 — Graph small-write `overwrite=True`: replace-returns-409-for-files quirk**
  spec: GR-018 · effort: S · audience: user.api, library.maintainer
  On the small-file `PUT /content` path, `@microsoft.graph.conflictBehavior=replace`
  is expected to overwrite an existing file and return `200`. Graph issue reports
  describe some backing stores (SharePoint-backed drives) instead returning
  `409 nameAlreadyExists` for a *file* even with `replace`. The 409 discrimination
  in GR-018 would map that to `AlreadyExists` — a spurious failure for an intended
  overwrite. **Not reproduced**: the consumer OneDrive drive used for Stage-3 live
  verification honours `replace`, and our live path is consumer-only / device-code,
  so the SharePoint-backed edge cannot be live-verified today. No guard is taken in
  v1 because a speculative one (treating a `file`-faceted 409 on the `replace` path
  as success-equivalent) risks masking a genuine conflict and would guess at the
  body shape blind.
  **When picked up:** reproduce against a SharePoint-backed drive (needs app-only /
  SharePoint live testing, currently blocked — see the live-testing note), confirm
  the exact 409 body, then decide between a targeted guard on the `replace` path or
  documenting it as a hard backend limitation. Touches
  `src/remote_store/aio/backends/_graph/backend.py` (`_write_small`) and
  `sdd/specs/044-graph-backend.md` (GR-018). Discovered in ID-127 GR-WRITE review.

- [ ] **BK-268 — File the deferred Graph async-ext follow-ups (backlog hygiene)**
  spec: GR-003 · effort: S · audience: library.maintainer
  Two promised follow-ups have no tracked owner: GR-003 says async callers compose
  pattern matching themselves "until an async equivalent of `ext.glob` lands as a
  separate backlog item" (no such item exists), and ADR-0025 § Risks says the cache
  extension "should learn to warn when wrapped over a bridged backend (tracked
  separately)" (not filed). File or explicitly decline each so the deferred
  async-ext surface (glob / observe / otel / cache / integrity) has owners.
  Audit-016 L10.

---

## CI Operations

Scheduled-guard observability follow-ups from
[audit-018](audits/audit-018-ci-operations.md), prompted by the weekend mutation
failure (#763) reaching the maintainer by email only. `drift-guard` is the proven
pattern (scheduled finding → rolling GitHub issue → triage skill); these items
generalise it to the guards that lack it.
**Order:** handbook + principle (BK-275, the SSoT the others point at) → mutation
issue surface (BK-273, closes the #763 class) → dependabot approval safety
(BK-274). The adversarial section of audit-018 challenges each — read it before
picking one up; in particular the disposition below may narrow.

- [ ] **BK-275 — CI-operations handbook + the scheduled-guard consistency principle**
  spec: — · effort: S · audience: library.maintainer
  No document inventories the scheduled/automated workflows: what runs when, what
  finding each produces, where that finding shows up (issue / PR / Security tab /
  email), and which skill actions it. The knowledge exists only for one guard
  (`/drift` + `drift-guard.yml` header + `CONTRIBUTING § Dependency drift guard`).
  Author one authority doc (e.g. `sdd/CI-OPERATIONS.md` or a `CONTRIBUTING`
  section) holding that inventory table and stating the house principle: *every
  scheduled-maintenance guard emits a durable GitHub Issue as its TODO and has a
  triage entry point; email / red-X / green-check are insufficient alone.* Record
  codeql's weekly sweep (`codeql.yml:21-22`) reporting to the Security tab as a
  deliberate exception. The per-task skills/checklists (`/drift`, and any from
  BK-273/274) become thin pointers to this doc per the skill-overlay convention.
  **Decide first (audit-018 A1):** prefer a *generated* inventory
  (`scripts/check_ci_inventory.py` parsing `.github/workflows/*.yml` for
  `on.schedule`/`on.pull_request_review` and failing on an undocumented guard) over
  hand-maintained prose, which goes stale — matching the repo's automate-don't-hand-maintain
  doctrine (FEATURES.md, graph data). If shipped as static prose, attach an explicit
  "review when a workflow is added" obligation (the ID-150 revisit-ticket pattern).
  Audit-018 M2 / L1.

- [ ] **BK-273 — `mutation` testing produces no durable TODO; failures reach the maintainer by email only**
  spec: — · effort: M · audience: library.maintainer, infra.test
  `mutation.yml` lets its job fail, so the only signals are a red X in the Actions
  tab and GitHub's default actor email — that is how the weekend run (#763, an
  *implementation* failure, not even a surviving mutant) surfaced. No issue, no
  dedup, no triage skill. Contrast `drift-guard`: it never fails the job, writes
  structured JSON, and a `report` job (`drift_report.py`) reconciles a single
  rolling issue. Give mutation the same surface: redirect the `summary` job
  (`mutation.yml:188-218`, which already aggregates per-scope outcomes) into a
  `scripts/mutation_report.py` modeled on `drift_report.py` that reconciles a
  rolling `[mutation]` issue, and add a `.claude/skills/mutation/SKILL.md`
  mirroring `/drift`.
  **The body must distinguish two outcomes** (drift has one axis; mutation has
  two): a **surviving mutant** (test-coverage gap, advisory) vs a
  **harness/implementation failure** (the run itself broke — #763). Note the
  `summary` job today aggregates only `job.status` (success/failure/skipped), which
  cannot tell those two apart, so the reconciler must derive the distinction from
  the per-scope reports / exit semantics — this is closer to A5's "more code than
  it looks" than to a pure redirect.
  **Decide first (audit-018 C-DECISION / A3):** `drift-guard` chose
  never-red-issue-only; mutation should likely diverge — *surviving mutant → issue
  only, run stays green*; *harness/impl failure → issue AND red run*. The choice
  shapes whether the `mutate` job swallows or propagates its exit code. A3 raises
  a prior question: if surviving mutants are rarely actioned in practice, drop the
  issue for them entirely (report artifact only) and keep just the loud-fail on
  harness breaks — check the base rate across recent Saturday runs before building
  the full reconciler. The harness/impl-failure half is worth it unconditionally.
  If `mutation_report.py` is built, lift `drift-guard`'s single-writer concurrency
  guard (`drift-guard.yml:37-44`) deliberately, not approximately (audit-018 A5).
  Audit-018 H1 / L2.

- [ ] **BK-274 — Dependabot approval is the only gate before auto-merge to `master`, with no codified criteria**
  spec: — · effort: S · audience: library.maintainer
  `dependabot-auto-merge.yml` fires on a maintainer `approved` review and runs
  `gh pr merge --auto --squash` (`:33-41`) — by design, the human review is the
  gate. So the approval click is the load-bearing safety control, yet nothing
  documents what to verify per ecosystem before clicking: `Chore(deps)`
  (github-actions) goes green because the bump exercises nothing testable (#766 was
  approved on the green check); `Chore(deps-dev)` (pip) can go red on an
  upper-pin (#767) with no "real-ceiling-vs-transient" runbook.
  **Decide first (audit-018 A2 — the real risk may be the control, not the
  runbook):** the strongest option is to **drop auto-merge for the `github-actions`
  ecosystem** (low volume; a manual `gh pr merge` costs seconds and removes the
  rubber-stamp path), optionally gating any remaining auto-merge behind an explicit
  label so the irreversible step is deliberate. If a control is adopted, this item
  shrinks to a small "triage a red pip dev-dep" checklist; whether it needs a
  `/deps` skill or just a handbook checklist (BK-275) is itself deferred until the
  triage proves multi-step (audit-018 A4). Codify the surviving checklist in the
  BK-275 handbook rather than a standalone doc.
  Audit-018 M1.

---

## Lint / CI Completeness

audit-017 gate-topology follow-ups (BK-269–BK-272), in execution order; full
findings in [audit-017](audits/audit-017-dev-process-gate-topology.md).
**Order:** single-source the lint definition (BK-269, done) → route `sdd/specs`-only
and docs-only changes through their gates (BK-270) → point the `/pr` and
`/fix-pr` skills at that single gate (BK-271) → drop the dead mypy pre-push hook
(BK-272). BK-269 then BK-271 are the load-bearing consolidation wins; BK-270
closes the real coverage gaps and is cheaper once BK-269 makes the gate
one-place; BK-272 is trivial and order-independent. Each item's rationale lives
in its body. The `ID-*` items below are older, unprioritised ideas in the same
area.

- [ ] **BK-270 — Route `sdd/specs`-only and docs-only changes through their gates**
  spec: — · effort: S · audience: library.maintainer, infra.test
  The CI `setup` path filter (`ci.yml:40`, `CODE_PAT`) does not match `sdd/`, so a
  spec-only PR **skips the entire `lint` job** — `check_spec_marks` and
  `check_formal_trace` (the spec ↔ test / spec ↔ Dafny drift gates) never run, in
  CI or at commit (`verify-formal` runs only `dafny verify` +
  `check_capability_parity`, `ci.yml:364-374`). Separately, a docs-only PR
  (`docs-src/guides/*.md`) runs only `check_docs_framework` + `mkdocs build
  --strict` in the `docs` job, skipping `check_no_tracker_refs` (the gate built for
  guide prose), `check_links`, and `drift_check render-docs --check` (the last runs
  in no PR CI lane at all). Both fixes route *existing* gates to the change types
  they validate; neither adds a new gate:
  - Widen `CODE_PAT` to include `^sdd/specs/` (leanest), or add `check_spec_marks`
    + `check_formal_trace` to `verify-formal` — pick one place, not both.
  - Add `check_no_tracker_refs`, `check_links`, and `drift_check render-docs
    --check` to the `docs` job (or, once BK-269 lands, point the `docs` job at the
    relevant `hatch` targets).
  Audit-017 H2 / M3 / M5.

- [ ] **BK-271 — `/pr` and `/fix-pr` delegate to `hatch run all` instead of re-encoding gate logic**
  spec: — · effort: M · audience: library.maintainer, contributor.process
  `/pr` never runs `hatch run lint` or `hatch run all` — CONTRIBUTING's prescribed
  pre-PR command (`CONTRIBUTING.md:358`) — and instead reconstructs a partial
  subset (manual TESTING/CONTENT reads, a coverage run keyed on
  `src|tests|examples`, a trace-existence check, a local-machine grep), so it can
  open a PR that fails any of the 13+ lint checks it does not run. Both skills also
  prescribe `hatch run test` for "docs/config-only" diffs (`pr/SKILL.md:36-38`,
  `fix-pr/SKILL.md:109-111`) — the suite least relevant to a doc/spec change — and
  never prescribe `hatch run lint`, the gate that validates those changes. Define
  "what validates a change" **once** as `hatch run all` and have both skills run
  it, dropping the per-type coverage branch and the manual sub-gates (those rules
  already live inside `check_*` / `docs-check`). If a lighter fast-iteration gate
  is wanted, document one thin target and have both skills call it — but only one.
  Best sequenced after BK-269 + BK-270 so `hatch run all` is the true, complete
  superset. Audit-017 M1 / M2 / L2.

- [ ] **BK-272 — Resolve the dead mypy pre-push hook**
  spec: — · effort: S · audience: library.maintainer, contributor.process
  `.pre-commit-config.yaml:8-15` declares mypy with `stages: [pre-push]`, but the
  documented install (`hatch run pre-commit-install` = `pre-commit install`,
  `pyproject.toml:256`) installs only the pre-commit stage — there is no
  `default_install_hook_types` in the config and no doc mentions
  `--hook-type pre-push` — so the hook never fires on `git push`. Type-checking
  still runs via `hatch run typecheck`/`all` and CI, so this is dead config, not a
  correctness hole. Either set `default_install_hook_types: [pre-commit,
  pre-push]` so `pre-commit install` wires both stages, or drop the pre-push mypy
  hook and rely on `hatch run`/CI. Don't leave a declared gate that never fires.
  Trivial and order-independent. Audit-017 M4.

- [ ] **ID-179 — Trace schema validator: wire `audience` field check into `hatch run lint`**
  spec: — · effort: S · audience: library.maintainer
  `sdd/traces/_schema.yml` declares `audience` as `required`, but BK-193
  deliberately left that field as an authoring convention — enforced "on the
  next aggregator run," not at commit time — rather than wiring a gate (no
  aggregator exists yet, so nothing validates it today). Add
  `scripts/check_traces.py` that jsonschema-validates every
  `sdd/traces/[!_]*.yml` against the schema. Wire into the existing
  `hatch run lint` script list and into the lint CI job. Per
  `feedback_check_scripts_dual_wire`. Promotes BK-193's convention to
  mechanical enforcement. No priority while trace authoring is still
  ad-hoc; promote to BK-prefix when trace volume justifies enforcement.

- [ ] **ID-207 — Strengthen `check_formal_trace.py` from citation hygiene to clause enforcement**
  spec: — · effort: L · audience: platform.tooling
  ID-206 shipped `scripts/check_formal_trace.py`; a PR #663 review
  confirmed it certifies *citation hygiene at spec-ID granularity*, not
  clause-level enforcement (its docstring was narrowed to say so). Four
  independent hardening steps would close the gap:
  1. **Derive D mechanically.** D is built from author-typed `// @spec`
     tags, so deleting a tag silently drops an F1 and a new untagged
     `ensures` never enters D. Parse every contract `ensures` and fail on
     an untagged one — needs an exemption marker for proof-helper lemma
     `ensures` (e.g. `SlashCountZero`, the Safe/Unsafe pairs) that encode
     no spec clause.
  2. **Clause granularity, not ID granularity.** D/T/S key on spec ID, so
     one marker clears F1 for every `ensures` sharing that ID (~10 share
     `BE-014`). Per-clause sub-IDs, or a tag→test-name link, would gate
     each postcondition individually.
  3. **Push T past citation.** A marker only cites an ID; it does not
     prove the test asserts the clause, is enabled, or cites the *right*
     ID — a wrong-but-real ID passes F2 and even satisfies F1.
  4. **Bar baseline growth mechanically.** `_BASELINE` shrink-only is a
     review convention; a new violation can be parked by editing the
     frozenset. A committed count/hash pinned by a separate check would
     make it mechanical.
  Surfaced in the PR #663 review. Steps are independent and may split
  into separate IDs. No priority until the gate is shown to miss a real
  regression; promote to BK-prefix at that point.

---

## Docs & Discoverability

- [ ] **ID-161 — Publish `llms.txt` to the docs site**
  spec: — · effort: S · audience: user.api, library.maintainer
  Add a machine-readable discovery file at `docs-src/llms.txt` (served as
  `https://docs.remotestore.dev/llms.txt`) per the
  [llmstxt.org](https://llmstxt.org/) open standard. The file gives LLM
  tools a single, stable entry point — a curated H1 title, a one-paragraph
  summary, and a short link list — without relying on any specific platform.

  **Format** (llmstxt.org §2):
  ```
  # remote-store

  > Unified file-storage API for Python — one `Store` interface across
  > Local, S3, SFTP, Azure, SQL, and more.

  ## Docs
  - [Getting started](https://docs.remotestore.dev/getting-started/)
  - [Backends & capabilities](https://docs.remotestore.dev/reference/capabilities-matrix/)
  - [API reference](https://docs.remotestore.dev/api/)
  - [Migration guide](https://docs.remotestore.dev/reference/migration/)
  - [FEATURES (authoritative)](https://github.com/haalfi/remote-store/blob/master/FEATURES.md)

  ## Source
  - [GitHub](https://github.com/haalfi/remote-store)
  - [PyPI](https://pypi.org/project/remote-store/)
  ```

  **Why this adds value over `context7.json`:** `context7.json`
  targets one proprietary index; `llms.txt` is an open, client-agnostic
  standard. Tools that resolve `/llms.txt` at a domain root (e.g. Cursor,
  OpenAI's URL tools, or any future LLM IDE plugin) will discover the file
  without prior registration.

  **MkDocs note:** `docs_dir: docs-src` is set in `mkdocs.yml`. MkDocs
  copies non-Markdown files verbatim, so `docs-src/llms.txt` will appear
  at the site root automatically. No plugin or hook needed.

  **Maintenance:** the link list should be reviewed when major new guides
  land, not on every release. The file has no version number — it describes
  the current stable docs, not a specific release.

  **Optional follow-on (not in scope here):** `llms-full.txt` —
  concatenated full prose of all guides, for tools that prefer a single
  large context file. Worth a separate ID if demand appears. **Tooling
  decision:** if pursued, generate it from the **built** site with a
  MkDocs-native plugin (`mkdocs-llmstxt`, by the `mkdocstrings` author —
  `full_output:` emits `llms-full.txt`), not an external source bundler. A
  raw-source bundler would miss the `gen-files`-generated API pages and the
  BK-171 URL rewrites, and ignore `literate-nav` order. See
  [`research/research-lx-llms-context-tooling.md`](research/research-lx-llms-context-tooling.md).
  The orthogonal "bundle repo source for a coding agent" use-case is ID-216,
  not this file.

  **Content checklist when starting:** streaming reads (`with store.read(path) as f:`),
  `MemoryBackend` for unit testing, `store.child()` scoping, and
  `ext.integrity`/`ext.partition`/`ext.transfer` use-case examples are the
  known gaps in how external tools currently discover remote-store.

  **Sequence — prerequisites met (all landed, see BACKLOG-DONE.md):**
  ID-174 (docs reorg, stable source URLs), ID-172 + ID-173 (aio verifiers:
  `aio.md` and `index.md` now reflect the async API), ID-192 (aio.md rework),
  and ID-193 (async conformance) have all shipped. Nothing gates this item;
  the link list can be written against the current stable docs.

  **Exit criteria:** `docs-src/llms.txt` committed; `GET
  https://docs.remotestore.dev/llms.txt` returns the file after next deploy.

- [ ] **ID-216 — Evaluate `lx` as an ad-hoc repo-context bundler for coding agents**
  spec: — · effort: S · audience: library.maintainer
  [`rasros/lx`](https://github.com/rasros/lx) (Go, MIT) bundles a directory
  tree into one LLM-ready blob (XML/Claude format, token estimation,
  `.gitignore`-aware, tree/skeleton views). This is a **developer-convenience**
  tool for handing a coding agent whole-codebase or whole-subtree **source**
  context on demand — distinct from the docs-site `llms.txt`/`llms-full.txt`
  lineage (ID-161), which targets *published docs prose*, not source. Nothing
  here is committed or deployed, so the pipeline and supply-chain-in-CI concerns
  that rule `lx` out for `llms-full.txt` do not apply.
  **Scope:** timeboxed local trial — does `lx` beat a plain `git archive` /
  bespoke script for our layout? Settle on an invocation (likely an `.lxignore`
  plus a documented one-liner), and decide whether it earns a mention in
  CONTRIBUTING / dev docs. Do **not** wire it into CI or the docs build.
  **Why ID, not BK:** unevaluated DX convenience, no committed outcome.
  Background and the full lx-vs-MkDocs-plugin analysis:
  [`research/research-lx-llms-context-tooling.md`](research/research-lx-llms-context-tooling.md).
  **Exit criteria:** trial run recorded; keep/drop decision noted on this item;
  if kept, a documented invocation lands in dev docs.

- [ ] **ID-197 — Review context7.com docs page for framing and content gaps**
  spec: — · effort: S · audience: library.maintainer
  The context7 docs proxy surfaces how external tools and readers discover the
  project; framing found there (e.g. "one consistent interface across environments")
  may sharpen our own Getting Started, README, or guides. Walk the page, compare
  framing and structure against `docs-src/`, note strong angles and coverage gaps,
  then assess whether our source docs already cover them or could adopt the same
  framing. Findings feed the next docs-improvement session or ID-161 content checklist.

- [ ] **ID-199 — Backend setup & configuration guides expansion**
  spec: — · effort: L · audience: user.site, library.maintainer
  Expand the backend-related guide set in `docs-src/guides/` based on user
  pain mined from two sources: in-repo signal (traces, BACKLOG, CHANGELOG,
  PRs) and an external survey of GitHub issues across `boto3`/`s3fs`/
  `azure-storage-blob`/`paramiko`/`fsspec`, Stack Overflow, Reddit, and
  vendor forums. Seven candidate guides identified; full pain mapping,
  scope boundaries, sequencing, and code-side flags are in
  [research](research/research-backend-setup-guides.md). The two existing
  guides (`azure-hns-setup.md`, `sftp.md`) are the proof-of-value pattern.

  **Authoring contract (binding — see research § 2.2):** every guide
  under this initiative must be self-validated (maintainer-walked
  end-to-end against a real target), practicable (copy-pasteable steps),
  proven (dogfood trace or artifact in the PR), down to the point
  (recipe + outcome + caveat, no marketing), and link only reliable
  external references (vendor docs, RFCs, library docs — not Stack
  Overflow, Reddit, blogs, or GitHub-issue threads). Candidates that
  cannot meet the contract are deferred or scope-reduced, never
  weakened to fit.

  **Tier-1 standalone guides (per-guide PR + dedicated backlog ID when
  each is picked up):**
  1. S3-compatible providers cookbook — greenlit; AWS S3 + MinIO + R2 + B2 tested scope
  2. Large-object & streaming tuning — **split-ship**: SFTP half greenlit; S3 5 GB cliff deferred until AWS dogfood budget
  3. Local-dev emulators — greenlit; already dogfooded via CI
  4. SFTP reliability — greenlit
  5. Azure keyless auth & private endpoints — **conditional** on Azure subscription with elevated RBAC + vNet rights
  6. Credential & secret rotation — greenlit per-backend; Azure half tied to #5
  7. SQLite operational notes — greenlit; sidebar in `sql-blob.md`

  **Tier-2 sidebars** for `s3.md`, `sftp.md`, `azure.md`,
  `azure-hns-setup.md` — see research doc § 4. Fold into adjacent
  Tier-1 PRs where scope overlaps.

  **Out of scope (Tier-3):** AWS root-email governance, MinIO operator
  UX, `s3fs-fuse` FUSE-only concerns, generic DB pool tuning,
  hypothetical Azure-Blob-like self-hosts. Redirect to vendor docs.

  **Three code-side flags surfaced** (NOT guide work) — see research doc
  § 6: `s3fs` typed-error mapping fidelity; `S3Backend`
  `use_listings_cache` default; third S3 lane (`s3-boto3` direct)
  viability. Tracked as **ID-200 / ID-201 / ID-202** — all complete;
  see [BACKLOG-DONE.md](BACKLOG-DONE.md) (ID-201's disposition shipped
  as BK-257).

  **Sequencing (dogfood-cost ordered, see research § 7):**
  Phase 1 (zero new setup) = §3.3 + §3.7 + §3.4;
  Phase 2 (free-tier accounts) = §3.1 + §3.6 non-Azure halves + §3.2 SFTP half;
  Phase 3 (budgeted dogfood — gated on the access decision in research § 8 Q5) = §3.2 S3 half + §3.5 + §3.6 Azure half;
  Tier-2 sidebars mop up alongside Phase 1/2.

  Effort `L` reflects the parent scope; each individual guide is M-sized.

- [ ] **ID-205 — Migrate complex ASCII diagrams to Mermaid**
  spec: — · effort: M · audience: library.maintainer
  ASCII art diagrams in `sdd/`, `guides/`, and `docs-src/` are hard to
  maintain and render poorly. Mermaid renders natively on GitHub and in
  MkDocs via `pymdownx.superfences` (already used in `docs-src/index.md`
  and several `sdd/` research docs). Convert all non-trivial ASCII diagrams; leave simple
  inline flows (single arrows, short sequences) as text.

---

## API Ergonomics

- [ ] **ID-123 — Cache key derivation from `ResolutionPlan` (Phase 2)**
  spec: RES-100 · effort: M · audience: user.api
  `ext.cache` derives cache keys from `ResolutionPlan` fields instead of
  ad-hoc `(operation, path)` tuples. Only valuable once `CompositeStore`
  (ID-121) exists — single-backend cache keys are already correct *for the
  default per-store cache*. The exception (audit-016 L8): a **shared**
  `cache_backend=` across two top-level stores at different backends/drives
  collides on `(op, path)` and serves one store's bytes for another's — not
  Graph-specific (same for two Local roots or S3 buckets), opt-in, but exactly
  the case identity-derived keys would close.
  - Spec: RES-100 (proposed in [043](specs/043-resolution-plan.md))
  - Depends on: ID-121 (CompositeStore)

---

## New Backends

- [ ] **ID-121 — CompositeStore (research complete)**
  spec: — · effort: L · audience: user.api
  `CompositeStore(Store)` — core Store subclass (not extension) that composes
  multiple stores into one. Deterministic fallthrough resolution for reads, union
  LIST (deduplicated), writes to primary tier only.
  - [Research](research/research-sqlalchemy-backend.md#52-compositestore-id-120)
    (anchor uses historical ID-120 from research doc; now ID-121 after swap)
  - Depends on: unified `resolve()` → `ResolutionPlan` (ID-120) — **satisfied**:
    `Store.resolve()` ships and returns a `ResolutionPlan` (see BACKLOG-DONE.md).
    Remaining: at least two working backends to be useful; pairs well with
    ID-119 (landed) — so both conditions are already met.
  - Next: design as separate spec — backend-agnostic, useful independently

- [ ] **ID-140 — SQLBlob lazy reads for SQLite & PostgreSQL**
  spec: SQL-BLOB-003, SQL-BLOB-020 · effort: L · audience: user.api
  The current blanket claim that `SQLBlobBackend` cannot do lazy reads is too
  strong (see spec 040 SQL-BLOB-020, `_sqlalchemy.py:47` excluding
  `Capability.LAZY_READ`). Both primary dialects have a path to honest
  `LAZY_READ`; MySQL does not. This item captures the direction — **no
  implementation yet**.

  **SQLite (Py 3.11+):** `sqlite3.Connection.blobopen(table, col, rowid)`
  returns a seekable, chunked `Blob` handle. Reachable through SQLAlchemy via
  `sa_conn.connection.driver_connection`. Requires a `SELECT rowid FROM t
  WHERE key = :key` lookup first, and only works when the user-supplied table
  has an implicit rowid (i.e. not `WITHOUT ROWID`). Genuine streaming.

  **PostgreSQL (`bytea`, our current schema):** no native blob handle API.
  Pseudo-stream via repeated `SELECT substring(data FROM :off FOR :len) FROM
  t WHERE key = :k`. Client memory stays bounded (satisfies LAZY_READ
  semantics per spec 006 line 70-73), but each chunk is a round trip, and on
  compressed TOAST (`EXTENDED`, the default) the server must decompress per
  call. `ALTER COLUMN data SET STORAGE EXTERNAL` makes substring cheap at
  the cost of disk space — caller-controlled tradeoff.

  **PostgreSQL Large Objects (`lo_*`):** genuine streaming via
  `psycopg.connection.lobject()`, but requires an `oid` column and manual
  lifecycle (`lo_unlink` on delete/overwrite/move, otherwise we leak).
  Different storage model — belongs in a separate backend variant
  (e.g. `sql-largeobject`), not a retrofit to `SQLBlobBackend`.

  **MySQL:** no streaming story. Same `SUBSTRING()` pseudo-stream is
  possible but out of scope here (not a primary target).

  **Constraints & gotchas:**
  - `requires-python = ">=3.10"` (`pyproject.toml:11`) stays. SQLite
    `blobopen` is 3.11+ → runtime check, fall back to current eager path on
    3.10.
  - Capability becomes **per-instance, dialect-conditional** — new pattern
    in this codebase; no other backend varies capabilities at runtime.
    Consider whether `Capability` set should be computed in `__init__` and
    cached, and how `store.supports()` interacts with it.
  - Connection lifetime: streaming handle must keep the DBAPI connection
    checked out until the returned `BinaryIO.close()`. Needs a wrapper that
    owns both.
  - Custom tables (`create_table=False`): rowid may not exist; substring
    path is schema-agnostic and works as a universal fallback.

  **Ripple checks when picked up** (per `sdd/CLAUDE-REFERENCE.md`):
  - Spec 040 SQL-BLOB-003 (capabilities list) and SQL-BLOB-020 (`read()`).
  - Spec 006 streaming-io — capability semantics already fit.
  - `FEATURES.md` capability matrix.
  - `tests/backends/sqlblob/test_config.py:148` asserts LAZY_READ is NOT
    declared — must split into dialect-conditional assertions.
  - Behavioral test: large blob (e.g. 50 MiB) read in 4 KiB chunks with
    bounded RSS.
  - CHANGELOG, this file.

  **Open decisions for whoever picks this up:**
  1. SQLite-only first, or SQLite + PG `bytea` substring together?
  2. Declare `LAZY_READ` for PG substring path given the per-chunk
     round-trip cost, or reserve LAZY_READ for "true" lazy and add a
     separate `CHUNKED_READ` quality flag?
  3. PG Large Objects as a follow-up backend — separate idea, own ID.

  Related: ID-136 (non-lazy **write** is by-design; this item is about
  **reads** only — writes remain eager).

---

## Formal Verification

Dafny-section work earns its slot one of three ways: **(C)** prove a
spec clause is internally consistent and satisfiable, **(T)** certify
that a conformance test demands nothing the verified contract does not
(via the compiled `MemoryBackend` oracle), or **(O)** supply an
oracle-computed expected value for a property-based test. Runtime
backend gaps downstream of a Dafny-backed clause — a backend not
honouring a verified postcondition — are spec-conformance work, not
Dafny-section work; file those under the relevant backend section
(SFTP, Azure, S3, etc.).

Full doctrine and intake rules: [`sdd/formal/README.md`](formal/README.md)
§ "Three shapes of Dafny-section work: (C), (T), (O)".

*(none)*

---

## Maintenance / Long-horizon

- [ ] **ID-150 — Revisit informational `verify-tla` CI status (2026-10-19)**
  spec: — · effort: S · audience: library.maintainer
  First revisit ticket for the informational `verify-tla` job landed under
  ID-147 on 2026-04-19. Per [`sdd/formal/README.md` § Authoring rules](formal/README.md#authoring-rules) (3),
  the status is revisited every 6 months or every 10 spec amendments touching
  TLA-backed sections (whichever first). At the revisit, record one of:
  **promote** (check caught a real regression — add to the gate's `needs`),
  **remove** (no catches, no active modules — drop the job), or **re-defer**
  (still useful but no catch yet — open the next revisit ticket). A calendar
  without a ticket is the same as no calendar, which is why this item exists.

  **Exit criteria:** decision logged in the ticket's close note; if re-deferred,
  the successor ticket is linked here; if promoted, `verify-tla` joins the
  `gate.needs` list in `.github/workflows/ci.yml` and the caveat in
  `sdd/formal/README.md` is updated.

- [ ] **BK-242 — Flat-NS file-ancestor pre-check perf (SQLBlob IN-list, memoisation)**
  spec: — · effort: S · audience: infra.test, library.maintainer
  ID-211 review surfaced two perf optimisations the disposition (b)
  opt-in didn't ship. Bundle here so they don't get lost:
  - **SQLBlob `WHERE key IN (ancestors)`**: today `_head_one` issues one
    `SELECT 1` per ancestor — N round trips for a depth-N path. The
    research note (`sdd/research/research-id-211-flat-ns-file-ancestor-precheck.md`
    § 5.4) already flagged this; a single `SELECT key FROM table WHERE
    key IN (:ancestors)` collapses the walk to one RTT. On in-memory
    SQLite the win is sub-ms; on PostgreSQL/MySQL over the network at
    depth 6 it is 6 RTTs → 1 RTT (~10-50 ms each).
  - **`head_one` memoisation**: bulk-write workloads (`a/b/c/file-{i}.bin`
    for i in 1..N) re-HEAD the same `a`, `a/b`, `a/b/c` ancestors N
    times. A bounded per-instance `TTLCache(maxsize=…, ttl=…)` on the
    closure collapses O(N×D) HEADs to ~O(D) per distinct prefix without
    changing the contract (the TTL accepts staleness within its window).
    Applies to S3, S3PyArrow, Azure non-HNS, and SQLBlob.
  Both are perf optimisations that don't change the gate's contract —
  ship behind the existing `reject_write_under_file_ancestor=True`
  opt-in only. Includes refreshing `§ 4` / `§ 5.4` in the research note
  with measured before/after numbers. Touches
  `src/remote_store/backends/_flat_ns.py`,
  `src/remote_store/backends/_sqlalchemy.py`,
  `src/remote_store/backends/_s3.py`,
  `src/remote_store/backends/_s3_pyarrow.py`,
  `src/remote_store/backends/_azure.py`,
  `src/remote_store/aio/backends/_azure.py`. Discovered in PR #686 review.

- [~] **ID-018 — conda-forge publishing**
  spec: — · effort: — · audience: library.maintainer
  Recipe, CI validation, release checklist steps all done.
  - Done: [recipe](../packaging/conda-forge/recipe.yaml),
    [conda-recipe workflow](../.github/workflows/conda-recipe.yml),
    staged-recipes PR `conda-forge/staged-recipes#32401` (CI green).
  - Blocked: waiting for conda-forge reviewer approval. When merged: add
    `conda install -c conda-forge remote-store` to README.

---

## Icebox

Deferred indefinitely — revisit only if demand or circumstances change.

- [ ] **ID-215 — `RemotePath` deferred pathlib-parity members**
  spec: PATH-016, PATH-017 · effort: S · audience: user.api
  Follow-up from ID-196. That item shipped `as_posix()` (PATH-016) and pinned
  the deliberate non-goal that `RemotePath` is **not** `os.PathLike`
  (PATH-017). The accompanying parity audit catalogued the `pathlib.PurePath`
  members still absent from `RemotePath`:
  - **Cheap, safe read accessors** complementing the existing `name` / `suffix`:
    `stem` (name without final suffix) and `suffixes` (list of all suffixes).
  - **Copy-with mutators:** `with_name`, `with_suffix`, `with_stem`. Each must
    re-run normalisation/validation and reject empty results per PATH-008.
  - **Other:** `joinpath` (n-ary `/`), `parents` (ancestor sequence),
    `match` (glob), `relative_to` / `is_relative_to`, `is_absolute`.
  Out of scope (meaningless for a rootless remote key): `drive`, `root`,
  `anchor`, `as_uri`. No demand for any of these yet — `as_posix()` covered the
  one concrete need. Reactivate per-member if a user hits a specific gap; each
  would need a `PATH-NNN` clause + spec-tagged test.
  Surfaced during the ID-196 parity audit.

- [ ] **BK-139d — Implement remaining bug prevention measures from research**
  spec: — · effort: M · audience: library.maintainer
  Items 1–3 shipped as BK-139a; items 4, 5, 7 shipped as BK-139b (see
  BACKLOG-DONE.md). Only item 6 remains: `scripts/check_error_handling.py`
  (~80 lines) — an AST script flagging broad exception handlers that silently
  return without checking `errno`. Deferred because BLE rules (item 4) and the
  extended conformance error-fidelity category (item 5) cover the same
  error-swallowing bug class with less maintenance overhead. Reactivate if a
  new error-swallowing bug escapes those nets.
  Related: [research](research/research-bug-prevention-beyond-testing.md).

- [ ] **ID-114 — PyArrow-style bucket path support (research)**
  spec: — · effort: S · audience: user.api
  PyArrow convention: `"bucket/prefix"` embeds bucket in path. Current
  `S3Backend` requires split (`bucket=...`, `path=...`). Research feasibility
  of factory method or native convention for easier PyArrow→remote-store
  migration.
  - Deliverable: RFC only — low commitment, no code change guaranteed

- [ ] **ID-118b — TLS CA bundle for Azure (Phase 2)**
  spec: — · effort: M · audience: user.api
  Extend `tls_ca_bundle` to `AzureBackend` if demand materializes.
  Primarily benefits Azure Stack Hub / on-premises deployments.
  Wrap `ClientOptions(ca_cert=...)`, check `AZURE_CA_CERTIFICATE_PATH`.
  S3 Phase 1 shipped — see BACKLOG-DONE.md.

- [ ] **ID-105 — AzurePyArrowBackend (C++ Tier 1)**
  spec: — · effort: L · audience: user.api
  Optional upgrade from the Tier 3 range reader shipped in
  [ID-102](BACKLOG-DONE.md#streaming--io). Only worth pursuing if real-Azure
  benchmarks show GIL overhead or missing I/O coalescing matters for target
  workloads. Approach: `pyarrow.fs.AzureFileSystem` (C++, ships with PyArrow)
  following the `S3PyArrowBackend` dual-library pattern.
  [Research § 6](research/research-azure-pyarrow-optimization.md#6-full-tier-1-path-if-needed).
  - Spike: validate auth methods, HNS/non-HNS, `ReadRangeCache` activation.
  - If viable: `AzurePyArrowBackend` — spec, tests, docs.

- [ ] **ID-125 — Update medallion showcase to Dagster v2 resource pattern**
  spec: — · effort: S · audience: user.api
  Replace `dagster_io_manager(store)` calls in `examples/medallion_dagster/`
  with `RemoteStoreIOManager`. Demonstrates the config-driven pattern.

- [ ] **ID-066 — PR preview deployments**
  spec: — · effort: L · audience: library.maintainer
  Deploy PR previews to Cloudflare Pages, Netlify, or GitHub Pages artifacts.
  Inspired by FastAPI's Cloudflare Pages pattern. Infrastructure decision needed.
  [Research](research/research-fastapi-docs.md) P6.

- [ ] **ID-067 — griffe-typingdoc for `Annotated[T, Doc("...")]` docstrings**
  spec: — · effort: S · audience: library.maintainer
  Only relevant if migrating from Google-style docstrings to PEP 727
  `Annotated[T, Doc("...")]`. Not recommended near-term.
  [Research](research/research-fastapi-docs.md) P5.
