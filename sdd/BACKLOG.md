# Development Backlog
<!-- doc: repo-only -->

Active work items and ideas. Completed items live in
[BACKLOG-DONE.md](BACKLOG-DONE.md).

Items graduate through the SDD pipeline:
**Idea → Backlog → RFC/Spec → Tests → Code**.

<a id="how-this-file-works"></a>
## How this file works

**Status legend:** `[ ]` pending · `[~]` in progress

**Ordering:** within each topic group, higher-priority or blocking items come
first — **except** where a section declares its own ordering, which it must state
in its own preamble. A section whose items form a dependency chain may order by
execution instead; readers who open the file at a heading need that stated where
they land, not only here.

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

## Lint / CI Completeness

- [ ] **BUG-243 — `missing_ok` has no stated obligation when the *container* is absent**
  spec: BE-012, BE-013, BE-021 · effort: M · audience: user.api
  Every clause speaks of "the path" and none of the bucket, container, or table
  holding it. So what a tolerant delete owes against a **missing store** is
  undecided, and each backend answers from whatever its wire protocol happens to
  reveal rather than from a rule.
  Current state, measured (all four flat-NS implementations, so nothing is
  inconsistent *today* — the gap is that the agreement is accidental):
  | Operation | S3 (all three) | Azure non-HNS | SQL |
  | --- | --- | --- | --- |
  | `delete(missing_ok=True)` | returns silently | returns silently | raises |
  | `delete_folder(missing_ok=True)` | raises `NotFound` | raises `NotFound` | raises |
  **The split is protocol accident, not design.** `HeadObject` answers 404 with
  no body, so `NoSuchBucket` never reaches the client and a missing bucket is
  indistinguishable from a missing key; `ListObjectsV2` answers `200
  KeyCount=0`, so the only 404 it can raise is the bucket's, and that one *does*
  carry a code. Azure lands in the same place by a different route. A caller
  writing an idempotent cleanup loop cannot predict which they get.
  **Decide it once, for all flat-namespace backends**, and say so in BE-012 /
  BE-013. Whichever way it goes, note that making S3's `delete` strict costs a
  second `HeadBucket` on every miss, against a spec that budgets exactly one
  probe per miss — so "tolerate the missing container" may be the cheaper rule
  as well as the kinder one.
  Surfaced while fixing BUG-242 (PR #945 round 6).

- [ ] **ID-242 — Four `moto doesn't raise PermissionError` pragmas are coverage holes, not exemptions**
  spec: — · effort: S · audience: contributor
  `_s3_base.py` 510/540/573 and `_s3_pyarrow.py:626` each carry
  `# pragma: no cover -- moto doesn't raise PermissionError`. The mappings are
  correct and the pragmas are accurate statements about the fixture, which is
  exactly the problem: **BUG-242 was a defect living behind the fifth instance
  of this same pragma**, on the one branch that mattered, invisible to a suite
  of 7976 passing tests.
  A true "the fixture cannot reach this" is a coverage hole wearing an
  exemption's clothes. It is indistinguishable from a real exemption at read
  time, so it never gets revisited.
  **Now cheap to close:** `tests/backends/s3/test_denied_probe.py` established a
  `pytest-httpserver` harness that serves real 403s at Stage 1, no Docker and no
  credentials. Each remaining pragma is a few params on that harness.
  Surfaced by the PR #945 round-6 review, which noted the commit's own
  "permanent hole" argument applies verbatim to the four it left behind.

- [ ] **BUG-241 — SQL prefix probes build `LIKE` patterns without escaping `_` and `%`**
  spec: — · effort: S · audience: user.api
  `SQLBlobBackend._reject_folder` builds `LIKE key + "/%"`, and every other
  prefix probe in `_sqlalchemy.py` follows the same convention. In SQL `LIKE`,
  `_` matches any single character and `%` matches any sequence, so a key
  containing either over-matches: probing `a_b` also matches `axb/...`, and a
  key containing `%` matches far more.
  **Consequence:** the wrong-type probe can report a folder that does not
  exist, turning a `NotFound` into an `InvalidPath` for a sibling key whose
  name merely resembles the target. Underscores in object keys are common.
  **Not a blocker for the work that surfaced it** — it predates BK-324 and the
  convention is file-wide, so fixing one site without the rest would be the
  inconsistency this section exists to remove. Fix them together with
  `ESCAPE`, or a dialect-appropriate equivalent.
  **Test shape:** seed sibling keys that differ only in a `LIKE` metacharacter
  position and assert the probe does not confuse them. Surfaced by the PR #945
  round-5 review, which considered and deliberately did not block on it.

- [ ] **BUG-240 — ASYNC-014 and DEPTH-003 state opposite rules, and `GraphBackend` implements the async one**
  spec: ASYNC-014, DEPTH-003 · effort: S/M · audience: user.api
  [ASYNC-014](specs/029-async-store-backend-api.md) says "`max_depth` limits
  traversal depth (when set, `recursive` is ignored)" **while citing DEPTH-003**,
  which states the opposite for the Backend ABC: `max_depth` applies only when
  `recursive=True`. `GraphBackend.list_files` follows ASYNC-014 and pins it at
  `tests/backends/graph/aio/test_list.py:183` — `recursive=False, max_depth=2`
  returns depth-2 files, where a sync backend returns immediate children only.
  **Both readings are asserted by a passing test, on different backends.** That
  is the state Rule 7 calls a live disagreement rather than a defect in one side,
  so which way it resolves is a decision, not a lookup.
  **The split is inside the async lane, not between the lanes.**
  `AsyncMemoryBackend` and `AsyncAzureBackend` implement DEPTH-003's reading;
  `GraphBackend` implements ASYNC-014's. So this is not "sync says one thing,
  async says another" — two async backends already disagree with a third.
  The practical consequence: **the missing async conformance cell cannot be
  added neutrally.** Whichever way it asserts, it turns a currently-green
  backend red, which is why the cell's absence is load-bearing rather than an
  oversight, and why this needs deciding before it can be closed.
  **Three artifacts assert the ASYNC-014 reading, not one.** ASYNC-014 itself,
  `tests/backends/graph/aio/test_list.py:183`, and `GraphBackend.list_files`'s
  own docstring — which BK-331 made *authoritative* for depth strategy in this
  same PR, by replacing spec 037's per-backend table with a pointer to each
  backend's docstring. So closing this means changing a doc BK-331 just
  promoted to source of truth.
  **Why nothing caught it:** there is no async twin of
  `test_list_files_non_recursive_ignores_max_depth`, so conformance never
  cross-checks the two; and both `Store` and `AsyncStore` normalise `max_depth`
  into `recursive` before delegating, so the divergence is invisible to every
  caller above the ABC. Reachable only by a direct backend call.
  **Predates BK-324** — the two clauses already disagreed; BK-324 only made
  DEPTH-003 explicit enough for the contradiction to surface. Surfaced by the
  PR #945 round-3 fix pass.
  **Whichever way it goes, the async conformance cell is part of the fix** —
  without it the next divergence is equally invisible. Expect it to turn a
  backend red on arrival; that is the item working, not a regression.

- [ ] **BK-338 — Decide what a PR review roster should be**
  spec: — · effort: S · audience: contributor.process
  Open question, not a committed design. Evidence from PR #944: the only
  user-facing bug found came from the pass that ran the tool rather than reading
  the diff, and expert-persona reviewers each reported findings inside their own
  lens while the defect sat between lenses.
  **A first attempt was reverted in PR #945.** It replaced the expert roster
  with a single unguided reviewer and pinned a specific model — the pin was
  proposed for one session only and had no business in a shared skill, and the
  roster change was made on one PR's evidence. Reopened as a question:
  `/rvw-pr` and `/orchestrate` should select the experts a change actually
  requires rather than run a fixed numbered list, and whether the author or an
  expert applies a fix is a separate question the reverted attempt conflated
  with it. Do not pin a model in a repo skill.

- [ ] **BK-334 — No ripple-check row covers adding a `hatch` script alias**
  spec: — · effort: S · audience: contributor.process
  The [Pre-work index](CLAUDE-REFERENCE.md#pre-work-index) has no trigger for
  adding an entry to `pyproject.toml`'s `[tool.hatch.envs.default.scripts]`.
  That edit is what decides whether a new `scripts/*.py` is reachable by
  anything — whether it joins `lint` / `preflight` / `docs-gate` / `all`, or is
  deliberately left out — and the table is silent on it.
  **The trigger class, not the instance, is what makes this worth a row.** It
  fires on every new script in `scripts/`, of which the repo has dozens and every
  one carries an alias. Surfaced by the PR #944 review: BK-330 reasoned to the
  right answer only via the adjacent cross-artifact row — which this same PR then
  widened to name drift reports, so it now covers the report case and still says
  nothing about a `gen_*`, a `bench-*`, or any other script.
  Fix shape: one trigger row in **both** presentations of the ripple-check table
  (`check_ripple_parity.py` enforces trigger-parity, so a row added to one and
  not the other fails `lint`), naming the reachability question and the
  `docs-gate`-vs-`lint` choice `check_traces` documents three lines above the
  `report-trace-outcomes` alias.
  **Distinct from BK-333**, which is scoped to three gates that CI *path filters*
  misroute and whose fix is a `docs-gate` entry. This is a missing row in a
  documentation table; different artifact, different fix, different verification.
  BK-333's enumeration of exactly three is load-bearing and should not absorb it.

- [ ] **BK-337 — Widening an authority doc's scope reaches no row that finds its restating copies**
  spec: — · effort: S/M · audience: contributor.process
  The [Pre-work index](CLAUDE-REFERENCE.md#pre-work-index) has a row for a **new**
  authoritative process doc, and one for an authority **direction** amended (which
  side governs). Neither fires on the commonest amendment: an existing authority
  doc's **scope or subject sentence** widening. Nothing then finds the copies that
  restate that scope to route readers in.
  **Measured target set — six live restating copies** of one direction, at the
  time of filing: `CLAUDE.md` § Drift checks, `sdd/CI-OPERATIONS.md`,
  `sdd/CLAUDE-REFERENCE.md` in both ripple presentations,
  `.claude/agents/sdd-expert.md` and `documentation-expert.md`, and
  `.claude/skills/rvw-pr/SKILL.md` and `audit/SKILL.md`.
  **Demonstrated recurrence:** PR #944 widened `DRIFT-RULES.md`'s scope sentence
  and took four review rounds to find them all, being one copy short in three of
  those rounds. `scripts/check_ripple_parity.py` structurally cannot help — it
  enforces parity between the two ripple presentations, not between them and the
  copies scattered through `.claude/**`.
  **Two candidate dispositions, and choosing between them is the first half.**
  Add a trigger row keyed on "an authority doc's scope or subject sentence is
  widened", naming the `.claude/**` step lists and agent FOUNDATION blocks as
  targets — or attack the cause and **delete the restatements**, leaving each
  reader to link to the doc that states its own scope, as `CLAUDE.md` § Drift
  checks already half-does ("that file states its own scope"). The second is
  strictly better if it is achievable: a row keeps N copies synchronised, while
  deletion removes the synchronisation problem. The obstacle is that agent-facing
  files are read cold by a process that may not follow a link, which is the
  reasoning BK-329 recorded when it accepted the copies in the first place.
  **Distinct from BK-334**, which is scoped to `hatch` script aliases — a
  different trigger with a different target set — and from BK-333's CI path
  filters. Surfaced by the PR #944 review, which noted the diagnosis had been
  recorded in that PR's trace and filed nowhere.

- [ ] **BK-335 — `check_links.py` cannot see Markdown links inside Python docstrings**
  spec: — · effort: S/M · audience: contributor.tooling
  [`scripts/docs/check_links.py`](../scripts/docs/check_links.py) walks git-tracked
  `.md` only, and guards on `tgt_path.suffix != ".md"`. So a
  `](../sdd/DRIFT-RULES.md#anchor)` link written inside a `scripts/*.py` docstring
  is validated by nothing: rename the anchor and every reference to it breaks
  silently.
  Measured, not hypothetical: at the time of filing, `scripts/report_trace_outcomes.py`
  and `scripts/_trace_corpus.py` carry several such links between them, pointing at
  anchors minted three PRs earlier in `sdd/DRIFT-RULES.md`. All resolve today —
  this is an unchecked surface, not a live break. `scripts/check_test_placement.py`
  had the pattern first, so BK-330 multiplied it rather than introducing it.
  **Why it was not fixed in BK-330:** the remedy is a new cross-artifact check in
  its own right — it needs a claim space, a stated bound and a decision about what
  counts as a link in Python source, and it will surface pre-existing breakage
  across `scripts/` unrelated to the PR that found it. Adding that inside a review
  round is how a check ships without the design [`DRIFT-RULES.md`](DRIFT-RULES.md#rules)
  requires of it.
  Fix shape: extend the walk to extract links from `.py` docstrings (or a narrower
  "repo-relative Markdown link in any tracked text file" pass), and expect a first
  run that reports existing breakage — decide up front whether that is fixed or
  baselined, since [Rule 6](DRIFT-RULES.md#tolerated) wants tolerated divergence
  registered rather than unnoticed.

- [ ] **ID-239 — Sweep backlog IDs used as provenance anchors out of durable artifacts**
  spec: — · effort: — · audience: contributor.process
  A backlog ID is a short-lived coordinate; the code, config and comments it gets
  stamped into are long-lived. `pyproject.toml` alone carries dozens of
  `# BK-NNN:` / `# ID-NNN:` comment prefixes, and source docstrings across
  `scripts/` open the same way. Once the item is closed the ID explains nothing a
  reader can act on — it points at an archive entry rather than describing the
  thing in front of them.
  Surfaced by the PR #944 review, where the user objected to a
  `# BK-330.`-prefixed `pyproject.toml` comment. That PR's own new and modified
  files were fixed in place; the pre-existing sites were explicitly left out of
  its scope, since the sweep needs its own verification.
  **Preserve the distinction that makes this tractable:** an ID used as a
  *provenance anchor* ("BK-330: rank references by…") is what goes — rewrite the
  sentence to describe the thing on its own terms. An ID that is *data* stays: a
  comment recording that several traces share `id: ID-127`, a test fixture using
  an ID as a literal trace identifier, or a backlog/CHANGELOG cross-reference are
  all load-bearing. Where a fact like that is kept, pin it rather than restating
  it loose.
  **Open, and the reason this is not purely mechanical.** The carve-out lives in
  exactly one place: the ripple-check
  ["Tracker ID in published prose" row](CLAUDE-REFERENCE.md#pre-work-index),
  whose "Out of scope" clause names `sdd/**`, CHANGELOG, DEVELOPMENT_STORY and
  source `#` comments. [`CONTENT-RULES.md`](CONTENT-RULES.md) carries **no**
  tracker-ID carve-out — its scope line says the opposite ("Applies to all
  content: README, guides, docstrings, and inline doc comments"), so there is
  nothing to narrow there and an implementer should not go looking.
  A sharper form of the question than "should the carve-out narrow", because it
  does not need a policy judgement to be a defect: `DRIFT-RULES.md`,
  `CONTENT-RULES.md` and `000-process.md` all carry `<!-- doc: dual dest=... -->`
  and `scripts/gen_pages.py` renders them into the published site — so parts of
  `sdd/**` **are** published prose, and "Out of scope: `sdd/**`" already
  contradicts the dual-dest mechanism today. Settle that first; it bounds
  everything else.
  **Why ID, not BK:** the same reasoning ID-238 states under Cross-Artifact
  Consistency. The
  scope question above is unevaluated and the item's own body says deciding it
  "bounds everything else", so the size of the committed half is unknown — which
  is also why `effort:` is `—` rather than a guess. Contrast BK-334 above, which
  has a stated fix shape, a named enforcement mechanism and a stated
  verification, and is `BK` for exactly those reasons.

- [ ] **ID-235 — Structural lint for BACKLOG files (entry-header integrity)**
  spec: — · effort: S · audience: contributor.tooling
  A string-anchored edit swallowed an entry header in `BACKLOG-DONE.md`
  (PR #932), merging two items — and because `gen_backlogid.py` derives
  IDs from headers, the stale JSON was masked too. Lint the structure:
  every metadata line follows an entry header, headers unique across both
  files, BACKLOG-DONE status `[x]` only. Home: extend
  `scripts/gen_backlogid.py`.
  Stays here rather than under Cross-Artifact Consistency: it checks one
  artifact against a structural rule, not two descriptions against each other.

- [ ] **BK-333 — Three `lint`/`preflight` gates are unreachable for the `sdd/` change that trips them**
  spec: — · effort: S · audience: contributor.tooling
  The remaining instances of the "an `sdd/`-only change reaches no gate" shape,
  after BK-329 closed it for `check_traces` and `gen_backlogid --check`. `CODE_PAT`
  does not match `^sdd/`, so CI's `lint` job (and `preflight` inside it) is skipped;
  `FORMAL_PAT` is `^sdd/(formal|specs)/` **minus `sdd/formal/tla/`**, so the
  second-wiring escape hatch used for `check_spec_marks`, `check_formal_trace`,
  `check_capability_parity` and `check_dafny_twin_parity` does not reach these
  three; and `docs-gate` invokes none of them:
  - `gen_adr_digest.py --check` (in `preflight`) reads `sdd/adrs/`. Adding an ADR,
    accepting a draft or recording a supersession is exactly what bumps the
    **committed generated** `sdd/adrs/DIGEST.md` and can break supersession-graph
    consistency, so staleness ships.
  - `check_tla_no_emdash.py` reads `sdd/formal/tla/**/*.tla` — the one subtree
    `FORMAL_PAT` deliberately excludes, so a TLA-only change skips the check
    written for TLA files.
  - `check_ci_inventory.py` compares `.github/workflows/` against
    `sdd/CI-OPERATIONS.md`. The workflow side is covered (`CODE_PAT` matches
    `^\.github/workflows/`); editing the handbook alone is not.
  Fix shape: add each to `docs-gate` beside the two BK-329 wired, following the
  precedent `check_ripple_parity` documents. Filed rather than fixed in BK-329
  because that PR touched no ADR, no TLA module and not the handbook: its own
  artefacts were the other two, and wiring gates it did not exercise would have
  been scope it could not verify.
  Surfaced by the PR #941 review, which named `gen_adr_digest` as the last
  instance; enumerating `lint` and `preflight` against the path filters found two
  more, so the item is scoped to all three rather than to the one reported.

- [ ] **ID-246 — No gate verifies that a tracker ID cited under `sdd/` resolves**
  spec: — · effort: S · audience: contributor.tooling
  Specs cite backlog coordinates as provenance — the clause says what it binds,
  the ID says which work produced it. `check_no_tracker_refs.py` is built to
  *push* IDs here: it fails a docstring or `docs-src/` page and tells the author
  to "move the coordinate into the corresponding `sdd/specs/` or
  `sdd/BACKLOG-DONE.md` entry", and lists `sdd/**` as out of scope because "the
  trackers are how those documents are addressed". So the citations are correct
  by design. **Nothing checks that they resolve.**
  **Measured** (all 50 specs): 166 citations, 80 distinct IDs, 28 files, **zero
  dangling** — 69 resolve into `BACKLOG-DONE.md`, the rest into `BACKLOG.md`.
  The invariant holds today by discipline, not by construction: no script
  validates sdd-internal tracker citations (`check_no_tracker_refs` looks away
  by design, `check_formal_trace` covers spec IDs not backlog IDs), and
  [`DRIFT-RULES.md`](DRIFT-RULES.md) does not mention the backlog at all.
  **Failure mode:** `BACKLOG-DONE.md` is ~8,000 lines and append-only *by
  convention*. A prune, a bad merge, or a renumber silently rots every spec
  clause pointing into it, and the rot is invisible — a reader meets an ID that
  resolves nowhere and cannot tell whether the evidence was deleted or never
  existed.
  **Fix shape:** extend `check_no_tracker_refs.py` — it already parses the ID
  pattern and already knows both backlog files — with a second, inverted pass:
  every `PREFIX-NNN` under `sdd/` must appear as an item in `BACKLOG.md` or
  `BACKLOG-DONE.md`, failing with the citing file and line
  ([DRIFT-RULES Rule 2](DRIFT-RULES.md#rules): localize, don't merely fail).
  Rule 3 is what makes this cheap and worth doing: the claim space is *derived*
  from the citing documents rather than maintained beside them, and the
  identifiers are already stable. Rule 4 needs a decision the item does not
  presuppose — when a spec cites an ID no backlog file carries, which side is
  wrong. Note the wiring trap BK-333 above documents: a check reading `sdd/`
  must reach a gate an `sdd/`-only change actually runs.
  Surfaced during the ID-241 review by the question "why do specs carry backlog
  IDs at all, aren't they temporary?" The premise turned out to be wrong —
  completed items migrate to `BACKLOG-DONE.md` rather than being deleted, per
  this file's own § Completing work — but the question exposed that nothing
  enforces the migration's promise.

---

## Cross-Artifact Consistency

Work whose purpose is detecting or settling disagreement between two or more
descriptions of the same thing. Design and review rules for anything added here:
[`DRIFT-RULES.md`](DRIFT-RULES.md#rules). The argument, evidence and gap ranking
behind the programme: [research](research/research-inconsistency-detection-multi-artifact.md)
§ 9, whose step numbers each item cites — that document carries the reasoning,
this section carries the work.

**This section orders by execution, not by priority** — the declared exception to
[the file's default](#how-this-file-works), because its items form a dependency
chain. Position therefore says nothing about importance, and dependencies are
stated by ID inside each item so re-sequencing cannot silently invalidate them.
**ID-244 comes first** (ID-241, its sibling, has shipped), then ID-207's steps 3
and 4. This is a
re-sequencing on measured evidence, not the original plan: BK-324 was expected to
clear the way for ID-207 step 2, and instead supplied four instances of the drift
this programme exists to detect — none of which step 2 would have caught. BK-340,
ID-241 (both shipped) and ID-244 are what those four actually exhibited (a rule
gated so no fixture ever runs it), and ID-207 step 3 is the other half (a
citation is not an assertion).
Step 2 keeps its L cost and its ~2.5% reach; it follows rather than leads, and
ID-207 states the evidence. BK-332, ID-236 and ID-237 are follow-ons that get
cheaper once the earlier work lands. BK-327 and ID-238 are independent of the
chain and can be taken at any point; both sit at the section's tail.

**BK-340 shipped and produced ID-244, its own successor in this ordering.**
Registering the `sqlquery` fixture closed the reachability hole for the *gate*
mechanism it named (a family with no fixture) and, in doing so, measured a second
gate underneath it: the conformance suite seeds through `backend.write`, so every
content-bearing contract sits behind `Capability.WRITE` and no read-only backend
can reach any of it. That is ID-244, and it is why `sqlquery` reaches 77 cells
rather than the whole surface. The `ReadOnlyHttpBackend` audit BK-340 also asked
for found the same gate excluding the registry's only read-only LAZY_READ
declarer from SIO-009, plus a vacuous assertion in that cell — shipped alongside
it as [BUG-244](BACKLOG-DONE.md).

**ID-241 shipped and produced ID-245, the same way.** Making the missing-cassette
skip fire per unplayable request rather than per test name moved 52 conformance
cells from skipped to executing — and the act of measuring that moved spec 003's
hand-counted coverage table for the second time, which is ID-245. It sits after
ID-244 rather than at the head: ID-244 changes which cells a read-only backend
can reach, so a generator built first would measure a surface about to move. The
pattern is now three for three: closing a reachability gate
measures the next thing underneath it. Read the measured numbers in
[BACKLOG-DONE.md](BACKLOG-DONE.md) before sizing further work here, because
"skipped" and "unreachable" turned out not to be the same set.

On importance, the research doc's designation, which this section adopts rather
than restates: the two items that build what is actually missing are the authority
model — shipped as BK-329, now
[`000-process.md` Rule 7](000-process.md#intent-attribution) — and **ID-207** (the
canonical claim space). BK-324 was the item they unblock and the evidence that the
gap is real, not itself one of the two.

**That designation now has a measured qualification, recorded here because the
research doc is point-in-time and does not get rewritten.** ID-207 builds a
*canonical claim space* — an omission detector, research § 1 class E. BK-324's
four instances were class A/C/D: one claim restated in several homes and updated
in one. So ID-207 remains the strategic item, and it is **not** the item that
would have caught what this programme has actually caught so far. Detecting those
needs semantic comparison of prose, which § 1 marks as having no general oracle.
The mechanisms that did catch them were an author-side sibling sweep and running
the code rather than reading the diff — neither in the research doc's ranking.
The sweep is now shipped as [BK-336](BACKLOG-DONE.md); the second is still open
as BK-338 under Lint / CI Completeness. Weigh a future step-2 argument against
that.

Shipped so far: step 1 (Dafny twin parity) as BK-328, step 5.1 (the attribution
rule) as BK-329, step 4 (037's per-backend table) as BK-331, and **step 3's
report half** as BK-330; see
[BACKLOG-DONE.md](BACKLOG-DONE.md). Step 3 asked for a report *and* a review
cadence — the cadence is open as ID-238 at the tail of this section, so step 3
is not closed. Four findings from them
apply to what follows: a documented gap statement is not a measured one, pinning
what an exemption covers beats exempting the whole item, an authority rule is
worth exactly the live disagreements it decides — run a proposed one against them
before believing it, because the case that does *not* resolve is the informative
one — and a hand-counted figure about a growing corpus is stale before the commit
that writes it lands, so cite the generator instead.

- [ ] **ID-244 — A read-only backend cannot reach any WRITE-gated contract cell**
  spec: — · effort: M · audience: infra.test
  Sibling of [ID-241](BACKLOG-DONE.md) (shipped), and the same class: a rule
  gated so no fixture ever runs it. Here the gate is not a cassette but the **seeding discipline** —
  conformance cells that need data call `backend.write`, so they sit behind
  `fixture_params(Capability.WRITE)`. Any contract that happens to live in such a
  class is therefore unreachable for a read-only backend, *including contracts
  that have nothing to do with writing*.
  **Measured instance.** SIO-009 (laziness: a LAZY_READ backend must not return a
  BytesIO-backed stream) lives in `TestStreamingConformance`, a WRITE-gated class.
  `ReadOnlyHttpBackend` is the registry's **only read-only LAZY_READ declarer** —
  streaming is the whole justification for its capability set, per
  `tests/backends/http/test_config.py::test_capabilities_are_read_metadata_lazy` —
  and it was structurally excluded from the only cells asserting that contract.
  The two per-backend read tests did not compensate: both assert content and
  chunking, which a pre-loaded `BytesIO` satisfies identically.
  Pinned per-backend by BK-340 in `test_read_is_lazy_not_bytesio`; that is a patch
  over a structural hole, exactly as `tests/backends/sqlquery/test_config.py`'s
  root cells were before BK-340 registered a fixture.
  **The same hole is why BK-340's own `sqlquery` fixture reaches only 77 cells.**
  Its content-bearing surface — read, glob, listing with keys present — is
  WRITE-gated end to end, so registering the fixture bought the
  capability-independent contract and nothing else. That was the right scope for
  BK-340; it is this item's subject.
  **Why ID:** the fix is a seeding indirection (a per-fixture `seed` hook the
  cells call instead of `backend.write`), and *where it binds* is unmade — on the
  fixture, on the helper, or as a capability-neutral rewrite of the affected
  classes. The answer decides how much of the conformance suite changes, and a
  hook whose seeded content cannot round-trip (SQLQueryBackend materialises result
  sets, so `read(k)` never returns the bytes a seeder "wrote") constrains it
  further: the hook must express *presence*, not content, or the cells that use it
  must not assert content.

- [ ] **ID-245 — Spec 003's per-backend cassette-reachability table is hand-counted**
  spec: — · effort: M · audience: infra.test
  [`003-backend-adapter-contract.md`](specs/003-backend-adapter-contract.md)
  BE-029's coverage note tabulates, per backend, which root-path conformance
  cells execute and which are pinned only in a per-backend home. Every figure in
  it was counted by hand, against a corpus that grows — the exact shape BK-330
  warned about and this section's preamble quotes: *"a hand-counted figure about
  a growing corpus is stale before the commit that writes it lands, so cite the
  generator instead."* ID-241 has already rewritten the table once for the same
  reason, which is the second data point.
  **Fix shape:** a script that runs the conformance suite (or its collection plus
  the replay guard's verdict) and emits, per replay fixture, which cells execute
  and which skip for want of a cassette; spec 003 then cites the generator rather
  than a count. The reachability figure is not derivable from collection alone —
  whether a cell needs a cassette depends on whether the backend issues a request,
  which only running it answers (ID-241).
  **Design obligations:** [`DRIFT-RULES.md`](DRIFT-RULES.md#rules) applies in
  full — Rule 3 (the claim space must be *derived*, and its granularity stated),
  Rule 4 (which of spec and generator governs), Rule 5 (gating or advisory, and
  why).
  **Position:** after ID-244, not before it. ID-244 changes which cells a
  read-only backend can reach, so building the generator first would measure a
  surface about to move — the same reason ID-241 filed this rather than building
  it inside its own diff.

- [ ] **ID-207 — Strengthen `check_formal_trace.py` from citation hygiene to clause enforcement**
  spec: — · effort: L · audience: contributor.tooling
  Research § 9 step 2, the programme's strategic half: a canonical claim space,
  extended toward the implementation and below identifier granularity.
  **Re-sequenced after BK-324, on measured evidence — take steps 3 and 4 before
  step 2.** BK-324 was expected to clear the way for step 2; instead it supplied
  four instances of the drift this programme targets, and a design investigation
  found step 2 would have caught none of them (see the step 2 bullet). What the
  four exhibited was **coverage reachability** — a rule can be gated so no
  fixture ever runs it, which is ID-244 in this file (and BK-340 and ID-241,
  both shipped) — and
  **citation ≠ assertion**, which is this item's own **step 3**. Both are cheaper than L and
  both have measured instances behind them; step 2 has an L cost, a ~2.5% reach,
  and no instance. Step 2 is not abandoned: after 3 and 4 land, its unresolved
  scope question ("Dafny-backed only, or corpus-wide?") will have been answered
  by what those two find.
  ID-206 shipped `scripts/check_formal_trace.py`; a PR #663 review
  confirmed it certifies *citation hygiene at spec-ID granularity*, not
  clause-level enforcement (its docstring was narrowed to say so). Four
  independent hardening steps would close the gap:
  1. **Derive D mechanically.** D is built from author-typed `// @spec`
     tags, so deleting a tag silently drops an F1 and a new untagged
     `ensures` never enters D. Parse every contract `ensures` and fail on
     an untagged one — needs an exemption marker for proof-helper lemma
     `ensures` (e.g. `SlashCountZero`, the Safe/Unsafe pairs) that encode
     no spec clause. (Research step 2b.)
  2. **Clause granularity, not ID granularity.** D/T/S key on spec ID, so
     one marker clears F1 for every `ensures` sharing that ID. Run
     `hatch run python scripts/check_formal_trace.py` for the live per-ID
     tag counts — do not restate them here, per BK-330's finding that a
     hand-counted figure about a growing corpus is stale before the commit
     that writes it lands. (This bullet previously claimed "~10 share
     `BE-014`"; BE-014 carries 6 and the maximum is BE-018, so the count
     and the exemplar were both wrong.) Per-clause sub-IDs, or a
     tag→test-name link, would gate each postcondition individually.
     **Read [`DRIFT-RULES.md` Rule 3](DRIFT-RULES.md#rules) before
     choosing between them** — it requires the enumeration be *derived*
     from the authoritative artifact rather than maintained beside it, and
     that decides more of the question than either candidate's own framing.
     **The binding-constraint claim is narrower than it was written.** The
     research doc argued clause granularity is binding "since omission
     detection is identifier-keyed while BK-324's claims are sub-ID
     clauses." That holds for **facet 4 only** — an E-class orphan, spec'd
     and unasserted. It does **not** transfer to the restatement instances
     BK-324 actually kept hitting, and a design investigation measured why:
     **neither candidate would have caught any of the four.** F1 is an
     omission detector; the four were contradictions (research § 1 classes
     A/C/D), one claim restated in several homes and updated in one.
     Finer identifiers make omission detection finer; they do not convert
     it into a contradiction detector. The decisive case is review findings
     1/3/4 — BE-021's F1 was **green for the entire life of the
     divergence**, because the tests existed, cited the right ID, and were
     enabled, while carrying per-fixture skips and capability gates.
     Sub-IDs leave that green.
     **Scope reality:** the Dafny model reaches 26 of 933 declared sections
     and 94 tag sites of a corpus estimated near 3,600 clauses. Step 2 as
     written is a granularity improvement over roughly 2.5% of the claim
     space, and the four motivating instances are not inside it. Corpus-wide
     is the only scope under which any of them becomes reachable, and that
     is a different, larger item.
     **Needs an ADR before implementation, either way**: sub-IDs change the
     spec-ID grammar that [`000-process.md` Rule 5](000-process.md#rules)
     governs and on which ~11,800 citations across 518 files depend; a
     tag→test-name link promotes pytest node IDs to a contract surface and
     takes a Rule 3 exemption.
  3. **Push T past citation.** A marker only cites an ID; it does not
     prove the test asserts the clause, is enabled, or cites the *right*
     ID — a wrong-but-real ID passes F2 and even satisfies F1.
  4. **Bar baseline growth mechanically.** `_BASELINE` shrink-only is a
     review convention; a new violation can be parked by editing the
     frozenset. A committed count/hash pinned by a separate check would
     make it mechanical.
  **Not covered by any of the four:** the `Impl ⊆ S` direction (research step
  2a) — enforced behaviour must have a parent spec section, as a pass over
  raise sites where **the day-one allowlist is the deliverable**, not the gate.
  Two things that scope decides: raise sites in the backend package run to the
  *several hundreds*, so gate-or-report is a real question rather than a
  formality; and facet 4's normative enforcement lives one layer above the
  backend tree, so a backends-only pass reaches it through defensive duplicates
  and records it a layer from where it is enforced.
  Surfaced in the PR #663 review. Steps are independent and may split into
  separate IDs; promote to BK-prefix when one is committed to.

- [ ] **BK-332 — Schedule the custom-backend rehearsal**
  spec: — · effort: S to define, M per run · audience: contributor.process
  Research § 9 step 6. "Build a backend against the guide, from scratch,
  without help" runs today only as a side effect of guide PRs. Its output is a
  list of places the guide, the contract, or the conformance suite failed the
  builder — BK-324 and BK-325 are one run's findings (PR #932), which is the
  argument for scheduling it rather than running it by accident.
  **Cadence:** once per minor release, or after any change to the `Backend` ABC
  or the conformance suite, whichever comes first — the two events that can
  invalidate the guide, per [`DRIFT-RULES.md` Rule 9](DRIFT-RULES.md#period).
  **Evidence level, stated because the ranking flatters it:** n = 1. The claim
  that rehearsal has the best findings-per-unit-noise rests on that single run.
  **After BK-324**, which changes the contract a rehearsal would test against.

- [ ] **ID-236 — Publish the characteristic-accountability record**
  spec: — · effort: S · audience: contributor.tooling
  Research § 9 step 7. `check_formal_trace.py` computes a spec-coverage matrix
  and discards it. Render it at release time — every spec ID, its verification
  evidence (test marker, Dafny tag, TLA+ invariant), its status — so "what was
  verified, and by what" is answerable historically rather than only at HEAD.
  **Why ID:** no committed outcome, and the matrix's shape changes under ID-207,
  so the cost is unknown until that lands.

- [ ] **ID-237 — Derive the cross-artifact checker inventory**
  spec: — · effort: S · audience: contributor.tooling
  Research § 9 step 8. The research doc's own inventory of which artifact pairs
  are checked was assembled by hand, and it says of it: "The table will drift,
  and nothing will notice." Derive it from the `check_*.py` docstrings and
  publish it as a generated surface; it pairs naturally with ID-236, one
  enumerating spec coverage and the other checker coverage.
  Two complications belong in the scope rather than in the implementation
  surprise. A substantial minority of gates are single-artifact rule checks
  whose docstrings state a *rule*, not a pair (assertion presence, mock
  discipline, forbidden RST roles, em dashes in TLA+), so the deliverable needs
  an explicit "rule check, no pair" classification. And the `scripts/check_*.py`
  glob under-reaches: `scripts/docs/check_links.py` is a genuine cross-artifact
  gate outside it.
  **Why ID:** both complications push toward either a docstring convention or a
  curated mapping, and a curated mapping is precisely the
  parallel-artifact-that-drifts problem this item would exist to close. That
  decision is unmade.

- [ ] **BK-339 — Decide what replaces `store.md`'s hand-maintained Backend Behavior Matrix**
  spec: — · effort: M · audience: user.site
  Found by BK-331's sibling sweep and deliberately not swept with it: the same
  defect class as 037/027/020, but on the **user-facing** surface, where
  deletion needs a replacement decision rather than a pointer.
  `docs-src/reference/api/store.md` § Backend Behavior Matrix hand-maintains five
  behavioural rows across ten backends, and carries the line *"Verify against
  actual code before relying on these in production"* — a reference page telling
  readers not to trust it, which is the admission that it drifts.
  **One measured error, not a suspicion.** The `copy()` preserves metadata` row
  says `—` for Memory, but `MemoryBackend.copy` constructs the destination with
  `metadata=src_node.metadata` (`src/remote_store/backends/_memory.py`), so user
  metadata survives a copy. The row is also **ambiguous in a way that hides the
  error**: Local's cell reads "Yes (`copy2`)", which is filesystem metadata,
  while Memory's concerns user metadata — one row conflating two different
  properties, which is why a reader cannot tell a wrong cell from an
  out-of-scope one. Fixing the cell without splitting the row re-hides it.
  **The disposition is the work, and it is not the one BK-331 used.** Rows
  divide three ways: derivable from capability declarations (`Native glob()`
  duplicates the capabilities matrix's GLOB row — the two currently agree, so
  this is duplication rather than contradiction); genuinely useful user
  information available nowhere else (`move()` atomicity, `write_atomic()`
  mechanism); and under-specified (`list_files()` ordering, which the specs do
  not guarantee — publishing per-backend orderings invites reliance on an
  unguaranteed property). Deleting outright would remove real value; deriving
  needs declarations that do not exist for the middle group.
  **Check `capabilities-matrix.md` at the same time** — it is the neighbouring
  ten-backend table and a candidate home for the derivable rows, but whether it
  is generated or hand-maintained was not established by this sweep.

- [ ] **ID-240 — Model "the root always exists" in the Dafny contract**
  spec: BE-029 · effort: S · audience: contributor.process
  Surfaced by BK-324 facet 1, and the only half of it the formal model does not
  already carry. `BackendContract.dfy` declares `const Root: Path := "."` and
  PATH-015 makes `"."` well-formed, so the *aliasing* half was Dafny's position
  before it was Python's. But nothing in `Valid()` asserts `Root in fs`, so
  BE-029's other clause — the root is a folder **even on an empty store**, which
  is where SFTP was actually wrong (`base_path` is created lazily by the first
  write) — has no formal twin.
  **Why ID rather than BK:** the change itself is small, but adding a conjunct
  to `Valid()` obliges every existing lemma and method postcondition to
  re-establish it, and whether that proof cost is worth one clause is exactly
  the judgement `sdd/formal/README.md` asks to be made deliberately rather than
  by reflex. Measure the proof delta before committing.
  **Do not treat the Python fix as the gap.** The conformance suite already
  covers the empty-store case across the fixture registry; this item is about
  the model, and closing it changes no runtime behaviour.

- [ ] **BK-327 — Gate dual-doc nav reachability and index listing**
  spec: — · effort: S · audience: contributor.tooling
  Independent of every other item in this section — take it whenever. A
  `<!-- doc: dual dest=explanation/design/*.md -->` marker publishes a page that
  neither the docs-site nav nor the section index page lists, and nothing catches
  either omission. `mkdocs.yml` sets only `validation: links: not_found: warn`, so
  `nav.omitted_files` stays at its INFO default and `--strict` cannot promote it;
  `scripts/docs/nav.py` builds `SUMMARY.md` *from* `_nav.yml` and never diffs it
  against the pages `gen_pages.py` emitted; the `_index.tmpl` Documents list is
  hand-written and unchecked. So `hatch run docs-gate` goes green on a page that is
  unreachable, unlisted, or both. Each surface had a live instance repaired by hand
  in PR #938: `drift-rules` was absent from both, `ci-operations` was in `_nav.yml`
  and absent from `_index.tmpl`.
  Fix shape: a G-08 in `scripts/check_docs_framework.py` differencing emitted dual
  `dest` paths against both `_nav.yml` and the `_index.tmpl` Documents list;
  raising `nav.omitted_files` to WARNING covers the nav half only.
  Surfaced by the PR #938 review; an unstated bound on `docs-gate` being trusted
  past its range ([`DRIFT-RULES.md` Rule 7](DRIFT-RULES.md#miss-rate)).

- [ ] **ID-238 — Decide whether the trace-outcome report gets a review trigger, and what fires it**
  spec: — · effort: S · audience: contributor.process
  Independent of the chain, like BK-327 above — take it whenever, though it is
  only actionable now that BK-330's report exists.
  Research § 9 step 3 asked for two things: the report, and "review the top of the
  list at the same cadence as the TLA+ status revisit". BK-330 shipped the report;
  its item body dropped the cadence sentence, so the report exists and nothing
  causes anyone to read it. **That gap between what the research asked for and
  what the item scoped is this item's whole justification** — recorded here rather
  than folded into BK-330, which deliberately shipped a tool and left the practice
  question open.
  This item is also the **named owner of BK-330's
  [Rule 6](DRIFT-RULES.md#tolerated) register entry**: the decision it takes is
  what settles whether that advisory check stays tolerated or gets switched off.
  The analogy the research offered is `sdd/formal/README.md`'s TLA+ status revisit
  (every 6 months or every 10 spec amendments, whichever first, each revisit
  tracked as a backlog entry — the ID-150 pattern).
  **The analogy is not the decision.** [`DRIFT-RULES.md` Rule 9](DRIFT-RULES.md#period)
  says set the period from the drift rate and anchor a recurring check to the
  events that can invalidate the artifact, not to a date — so an event trigger
  ("a reference crosses N tags", "at each release", "when a ranked file is next
  edited") is as admissible as a calendar one, and choosing between those shapes
  is most of the work.
  Input to that argument, not the answer: BK-330's
  [BACKLOG-DONE entry](BACKLOG-DONE.md) measured the corpus growing by roughly
  +3 negative tags and +1 tagged trace per merged PR across `79d0382` →
  `d9a2d3d` → `83e22a3`. Re-measure with `hatch run report-trace-outcomes`
  rather than trusting that figure — its going stale is the finding BK-330
  shipped.
  **Why ID, not BK:** the question was filed, not a period committed to. Whether
  a scheduled review is the right mechanism at all is unevaluated, and Rule 9
  makes "no recurring trigger, act on the report when a ranked file is next
  touched" a legitimate outcome.

---

## Docs & Discoverability

- [ ] **BK-325 — Custom-backend guide: registry-integration and remaining contract-topic gaps**
  spec: — · effort: M · audience: user.site
  Guide content the PR #932 walkthrough showed a real backend needed but
  the guide never teaches:
  - Registry integration: credential-named YAML options arrive wrapped in
    `Secret` (constructors need `str | Secret` and `.reveal()`), and a
    `retry:` block injects a `retry=` kwarg. Step 13 says only "names
    must match". Reference shape: `S3Boto3Backend.__init__`.
  - Stream-time error mapping for `LAZY_READ` backends: the cardinal rule
    covers call time only; lazy streams surface native errors during
    `read()` and `test_streaming.py` enforces no-leak there.
  - The file-ancestor lane: `rejects_write_under_file_ancestor`,
    `strict_only` fixtures, and their `_MODULE_FOR` wiring are
    undocumented; skipping them silently drops ~25 conformance cells.
  - Small fixes: error-mapping checklist lacks a base-`RemoteStoreError`
    fallback row; `from exc` guidance omits the deliberate `from None`
    pattern; the `SEEKABLE_READ` note contradicts shipped range-readers.
  Guide content, so it stays here rather than under Cross-Artifact Consistency —
  but it and BK-324 are one rehearsal's findings, which is the argument BK-332
  makes for scheduling the walkthrough rather than running it by accident.

- [ ] **ID-225 — Evaluate migrating the docs stack from Material for MkDocs to Zensical**
  spec: — · effort: L · audience: user.site, library.maintainer, contributor.tooling
  Our docs foundation is entering maintenance mode as its authors converge on a
  successor. [Material for MkDocs is feature-frozen](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
  (critical bug/security fixes for ~12 months, no new features), MkDocs 1.x is
  itself being forked (a `properdocs` MkDocs-1.x continuation now surfaces as a
  transitive docs dep, and a build-time banner warns MkDocs 2.0 will break all
  plugins/themes), and `mkdocs-llmstxt` (adopted in ID-220) is in maintenance
  mode for the same reason. The whole ecosystem is pointing at
  [**Zensical**](https://github.com/zensical/zensical) — a new MIT static site
  generator (Rust core, reads `mkdocs.yml` natively, with a migration path) built
  by the Material team. Crucially, `mkdocstrings`' author is rebuilding
  API-reference-from-docstrings *inside* Zensical — the exact capability our docs
  depend on `mkdocstrings` for.
  **Not prioritized:** Zensical is pre-1.0 and does **not** yet ship the
  API-reference feature we require, so "not yet — revisit when Zensical reaches
  API-reference parity" is a legitimate outcome. Kept visible here as the
  strategic anchor, not queued work.
  **Scope when picked up:** trial `zensical build` against our `mkdocs.yml`;
  confirm parity for the pieces we rely on (gen-files pages, mkdocstrings API
  reference, literate-nav order, BK-171 link rewrites, mike/RTD versioning); and
  fold in native `llms.txt` / `llms-full.txt` generation if Zensical ships it
  (its roadmap already speaks of LLM/agent consumption). This item is the
  **sunset trigger for the interim `mkdocs-llmstxt` adoption (ID-220)**: when the
  migration lands, the HTML→Markdown plugin is a prime candidate for replacement
  by a native feature.
  Background: [research](research/research-llms-full-txt-tooling.md).
  **Why ID, not BK:** unevaluated framework migration against a pre-1.0 upstream,
  no committed outcome.

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

## New Extensions

- [ ] **ID-217 — Async-native extension surface (owner for the deferred async `ext.*`)**
  spec: GR-003 · effort: L · audience: user.api
  `src/remote_store/aio/ext/` ships only `write.py` (`write_with_hash`); there is
  no async equivalent of `ext.glob`, `ext.observe`, `ext.otel`, or `ext.integrity`
  (audit-016 M6). A native `AsyncStore` consumer — the natural audience for an
  async-native backend such as Graph — reaches the full `ext.*` surface only by
  dropping to `AsyncBackendSyncAdapter` (ADR-0025), which forfeits the async
  streaming the backend exists to provide. GR-003 calls this out for `GLOB`
  specifically: async callers compose pattern matching over `list_files`
  themselves "until an async equivalent of `ext.glob` lands as a separate backlog
  item" — this is that item, and it owns the surface as a whole, not just glob.
  **Decision pending:** build per-extension async equivalents (glob first, as the
  smallest and the one a spec promises), or formally decline the ecosystem and
  document the sync-adapter route as the supported path for extension features
  over async backends. The `ext.cache`-over-bridged-backend guard is tracked
  separately as ID-218. Filed (not yet scoped) per audit-016 L10 / BK-268.

- [ ] **ID-218 — `ext.cache`: warn when wrapping a bridged (async-native) backend**
  spec: — · effort: S · audience: user.api
  `CachedStore` with an unset `max_content_size` materialises whatever the wrapped
  backend yields (`ext/cache.py`). Over a sync REST backend that is merely
  inconvenient; over an async-native backend reached through
  `AsyncBackendSyncAdapter` (ADR-0025) — a backend that exists precisely to
  *avoid* materialisation — it silently defeats the streaming the user chose the
  backend for. ADR-0025 § Risks flags this and promises the cache extension
  "should learn to warn when wrapped over a bridged backend (tracked separately)";
  this is that owner. Scope: emit a warning (or require an explicit
  `max_content_size`) when `cache()` wraps a `Store` whose backend is an
  `AsyncBackendSyncAdapter` and `max_content_size` is unset. Sibling of ID-217
  (async-native `ext.*`). Filed per audit-016 L10 / BK-268.

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

- [ ] **ID-229 — Evaluate porting to httpx 1.0 (lift the `<1.0` cap)**
  spec: GR-033 · effort: M · audience: user.api
  BUG-225 capped the `graph` and `httpx` extras at `httpx>=0.24.0,<1.0`
  after the drift guard's `--pre` re-resolution pulled `httpx==1.0.dev3`
  and the async graph backend failed to import. That pre-release turned
  out to be a **wholesale API rewrite**, not the exception-hierarchy
  reorg the BUG-225 diagnosis first assumed: `1.0.dev3` drops
  `httpx.AsyncClient`, `httpx.TransportError`, `httpx.DecodingError`,
  `httpx.HTTPStatusError`, `Timeout`, `Limits` — essentially the entire
  client surface the graph backend (`AsyncClient` in ~30 sites) and the
  `[httpx]` HTTP adapter are built on. Coding around a single missing
  symbol would only convert an honest import failure into a falsely-green
  import that then explodes at runtime on `httpx.AsyncClient(...)`, so the
  cap is the honest interim posture.
  **Upstream context:** the cap matches the maintainers' own guidance.
  httpx 0.28.x is still a pre-1.0 line; the "1.0.dev" / "httpx2" threads
  are about the project's next major API *direction*, not a released
  stable 1.x series. In the late-2024 V1 discussion the maintainers said
  httpx was not yet at a 1.0 SemVer release and recommended **pinning to
  0.28 while reviewing deprecations** — which is exactly what `<1.0` does.
  So `<1.0` is not a defensive over-cap; it tracks the current usable
  branch until a real stable 1.x ships.
  Ref: [encode/httpx#3344](https://github.com/encode/httpx/discussions/3344).
  **When picked up:** real httpx 1.0 stable is out and pins install
  cleanly against it. Diff the actual 1.0 public API against 0.28
  (`AsyncClient`, `Response`, `Timeout`/`Limits`, the transport-error and
  decoding-error bases, `respx` compatibility); decide port-vs-hold; if
  porting, update `_graph/*.py` + the `[httpx]` backend, raise the cap,
  and refresh the `graph` / `httpx` drift baselines. The `graph` drift
  smoke wired in BUG-225 (`scripts/drift_smoke_map.py`) now imports the
  async graph module directly, so a future 1.0 break fails the graph leg
  loudly instead of riding green on the top-level fallback.
  **Why ID, not BK:** unevaluated migration against an upstream whose 1.0
  shape is not yet stable — the same posture as ID-225. Mirrors the
  revisit discipline of ID-150.

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
