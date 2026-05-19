# Research: Backend Setup & Configuration Guides Expansion

**Item ID:** ID-199
**Date:** 2026-05-19
**Status:** Proposal — awaiting prioritization and per-guide commitment

---

## 1. Context

Two existing guides — [`azure-hns-setup.md`](../../docs-src/guides/backends/azure-hns-setup.md)
and [`sftp.md`](../../docs-src/guides/backends/sftp.md) — came out of real
setup pain hit during library development. Both proved valuable as
user-facing documentation, not only as internal engineering notes.

The question this research answers: **what other setup / configuration
pain hits remote-store users that they cannot resolve from the
per-backend reference pages or README alone, and what guides would retire
it?**

The approach was deliberately pain-first rather than backend-first:
enumerate dimensions of user challenge across the four backend families
(S3, Azure Blob + HNS, SFTP, SQL Blob), then let guides fall out of the
matrix where evidence is strong.

## 2. Approach

### 2.1 Evidence base

Two independent sources of signal:

**In-repo (mined via agent sweep).** The two existing guides plus their
commit history, every file under [`sdd/traces/`](../traces/),
[`sdd/BACKLOG.md`](../BACKLOG.md) and [`BACKLOG-DONE.md`](../BACKLOG-DONE.md),
[`CHANGELOG.md`](../../CHANGELOG.md), GitHub issues (sparse — one closed
unrelated issue), and recent merged PRs.

**External (mined out-of-session).** GitHub issues across `boto3`,
`aiobotocore`, `s3fs`, `azure-storage-blob`, `azure-identity`, `paramiko`,
`asyncssh`, `fsspec`, `rclone`; Stack Overflow questions with recent
activity; Reddit (r/aws, r/AZURE, r/devops, r/selfhosted); vendor support
forums; engineering postmortems. Filtered through eight category axes
(provisioning, self-hosting, auth, network, performance, quirks,
operations, migration).

The two sources cross-validate. External adds four high-signal categories
the repo did not surface (large-object tuning, Azure keyless auth, SFTP
reliability, SQLite operational); in-repo confirms one candidate
(local-dev emulators) that the external sweep underweighted.

### 2.2 Authoring contract (dogfood-first)

Every guide that ships under this initiative MUST satisfy the following.
This is a hard contract, not a suggestion — a candidate that cannot meet
it is deferred, scope-reduced, or dropped, never weakened to fit.

1. **Self-validated.** Every command, snippet, and configuration in the
   guide has been executed end-to-end by a maintainer against a real
   target (live cloud, real emulator, real legacy server). Untested
   recipes do not ship.
2. **Practicable.** Steps are copy-pasteable. Prerequisites are explicit
   and minimal. Failure modes the maintainer hit while dogfooding are
   documented inline (per the `azure-hns-setup.md` precedent —
   AADSTS50076, multi-line `\` HNS quirk, etc.).
3. **Proven (dogfood evidence trail).** The PR that lands each guide
   either contains a short trace (`sdd/traces/`) of the dogfood walk,
   or links to the artifacts (workflow run, account ID redacted,
   recorded session) that prove the recipe works.
4. **Down to the point.** No background prose, no rationale paragraphs,
   no "why this matters" framing. Each section is recipe + observed
   outcome + caveat. Prose density follows `azure-hns-setup.md` —
   short paragraphs, runnable blocks, no marketing.
5. **Reliable external references only.** Cite vendor official docs
   (AWS, Azure, Microsoft Learn, Cloudflare), RFCs, language/library
   official documentation (paramiko, boto3), and the relevant project
   tracker only when the cite is the authoritative source. Do NOT
   cite Stack Overflow, Reddit, Medium / personal blogs, AI-generated
   SEO pages, or GitHub-issue threads in user-facing prose. Internal
   evidence (CHANGELOG entries, BUG IDs, trace IDs) belongs in
   commit/PR descriptions, not in the guide body.
6. **Scope-honest.** If the maintainer can dogfood three of four
   providers, the guide names the tested three and explicitly says the
   fourth is "documented from external pattern, not verified here."
   No silent over-claiming.

The two existing guides (`azure-hns-setup.md`, `sftp.md`) already meet
this contract; they are the reference shape. New guides that cannot
match it stay in this research doc as proposals, not as drafts.

## 3. Proposed guides

Seven candidates. Tier-1 has converging evidence from both sources or
strong evidence from one. Tier-2 are short sidebar additions to existing
pages, not standalone documents. Tier-3 is explicitly out of scope.

### Tier-1: standalone guides

| # | Guide | Target path | Effort | Scope |
|---|---|---|---|---|
| 1 | S3-compatible providers cookbook | `docs-src/guides/backends/s3-compatible.md` | M | Cross (S3 family) |
| 2 | Large-object & streaming tuning | `docs-src/guides/large-object-tuning.md` | M | Cross |
| 3 | Local-dev emulators | `docs-src/guides/local-dev-emulators.md` | M | Cross |
| 4 | SFTP reliability | `docs-src/guides/backends/sftp-reliability.md` | S–M | Backend |
| 5 | Azure keyless auth & private endpoints | `docs-src/guides/backends/azure-keyless-auth.md` | M | Backend |
| 6 | Credential & secret rotation | `docs-src/guides/credential-rotation.md` | M | Cross |
| 7 | SQLite operational notes | sidebar in `sql-blob.md` (or new guide) | S | Backend |

### 3.1 S3-compatible providers cookbook

**Pain it retires.** MinIO, Cloudflare R2, Backblaze B2, Wasabi, Ceph,
Garage, and SeaweedFS users hit endpoint-URL setup, addressing-style
choice (path vs virtual-hosted), signature version, region quirks, and
capability gaps. Highest-volume category in the external survey; affects
four-plus provider families. In-repo BUG-185 reproduced the same shape
internally (s3fs path-style against MinIO required
`s3.addressing_style="path"` plus explicit proxy disable).

**Evidence pointers.**

- In-repo: CHANGELOG v0.24.1 BUG-185; CHANGELOG v0.24.0 BUG-178;
  BACKLOG-DONE BK-149 (TLS-005); [`examples/snippets/s3_botocore_tuning.py`](../../examples/snippets/s3_botocore_tuning.py);
  [`s3.md`](../../docs-src/guides/backends/s3.md) § "Botocore Client Tuning".
- External Tier-1 items #1 (boto3 / aiobotocore / s3fs pinning), #3 (s3fs
  listings cache), #4 (S3-compatible partial-API coverage); Tier-2.A
  (minimum IAM policy).

**Scope.** Endpoint URL + addressing-style + signature version per
provider; capability-matrix expectations ("MinIO does not support X" as a
design feature, not a bug); corporate-proxy snippets folded in; pin
matrix for the `boto3` / `aiobotocore` / `s3fs` triangle; minimum IAM
policy snippet for AWS S3 specifically.

**Dogfood plan.** MinIO via the existing `benchmarks/infra/` compose
file (already in CI). Cloudflare R2 and Backblaze B2 via fresh free-tier
accounts; one bucket each, smoke-tested for read / write / list /
multipart / delete. Wasabi, Ceph, Garage, SeaweedFS are NOT in scope as
verified — the guide says "documented from pattern, not tested here"
inline. Pin matrix verified by `uv pip install` runs against pinned
versions.

**Verdict.** Greenlit. Scope: AWS S3, MinIO, R2, B2 as tested;
others as pattern.

**Out of scope.** Self-hosting MinIO at operator scale; cross-provider
migration; provider-specific billing.

**Cross-links.** From `s3.md` and `s3-pyarrow.md`. To `troubleshooting.md`.

### 3.2 Large-object & streaming tuning

**Pain it retires.** `s3fs` multipart-upload restart bug at the ~5 GB
boundary, with counter-intuitive workarounds (`nomixupload`,
`max_dirty_data` tuning); paramiko slow reads (~25 MB/s on gigabit per
paramiko #1080, #2235, #2418) caused by default prefetch logic;
"when to pick `s3-pyarrow` over `s3`" decision.

**Evidence pointers.**

- In-repo: CHANGELOG v0.23.0 BUG-161 (Azure chunked upload), BUG-162
  (256 KiB copy buffer); CHANGELOG v0.17.0 ID-076
  (`AzureBackend(max_concurrency=)`); `azure.md` § "Upload tuning"
  already has a table.
- External Tier-1 #2 (S3 5 GB cliff, s3fs-fuse #1936); Tier-1 #9
  (paramiko `max_request_size` and read-window knobs); cross-cutting #2.

**Scope.** Decision tree: when defaults are enough vs when to tune. S3
multipart boundary and `s3-pyarrow` recommendation. SFTP prefetch
tunables. Azure multipart already in `azure.md`; link in.

**Dogfood plan.** Two halves:
- **SFTP prefetch tuning** — measured against `atmoz/sftp` and `SFTPGo`
  containers with synthetic 100 MB and 1 GB files; before/after numbers
  recorded. Doable on any laptop.
- **S3 5 GB multipart cliff** — requires a real AWS S3 bucket and
  ~10 GB of write traffic against `s3fs` with and without `nomixupload`.
  Costs AWS budget; cannot be reproduced on MinIO (the bug is in `s3fs`
  control flow against AWS-specific responses).

**Verdict.** **Split-ship.** SFTP half greenlit (Phase 2); S3 5 GB
sub-section deferred until AWS dogfood budget is approved. Do not ship
the S3 cliff prose without the dogfood run — it is the central pain
this guide retires.

**Out of scope.** Generic Python streaming patterns; benchmark
methodology (lives in `docs-src/explanation/performance.md`).

**Cross-links.** From per-backend pages. To `retry.md`, `ext.transfer`
guide, `s3-pyarrow.md`.

### 3.3 Local-dev emulators

**Pain it retires.** Azurite, MinIO, moto, SFTPGo, and atmoz/sftp each
have known divergences from production. Today these notes are scattered:
Azurite-no-HNS in `azure.md`; SFTPGo compat note in README + `sftp.md`;
MinIO snippets in `s3.md`; moto + PyArrow ≥24 multipart-mismatch only in
trace `bk-172-s3-pyarrow-minio.yml`.

**Evidence pointers.**

- In-repo: traces [`bk-172-s3-pyarrow-minio.yml`](../traces/bk-172-s3-pyarrow-minio.yml),
  [`bk-180-live-azure-conformance-fixtures.yml`](../traces/bk-180-live-azure-conformance-fixtures.yml),
  [`id-195-speed-up-hatch.yml`](../traces/id-195-speed-up-hatch.yml);
  CHANGELOG v0.20.0 SFTPGo note; CHANGELOG v0.5.0 Azurite CI integration.
- External: scattered but consistent. Users hit emulator pain in
  development; severe pain shows up in production where emulators are
  irrelevant — explains the lower external signal.

**Scope.** Recipe per emulator: docker-compose snippet, env wiring,
divergences-from-prod table. The divergences table is the value-add —
what fails on Azurite but works on real HNS, what moto accepts that real
S3 rejects, the SFTPGo vs OpenSSH semantic differences we test against.

**Dogfood plan.** Already dogfooded — every emulator runs in CI for
every PR. Extract compose snippets verbatim from `benchmarks/infra/`
and `.github/workflows/`; populate the divergences table from observed
quirks already recorded in CHANGELOG entries and traces. No new setup.

**Verdict.** Greenlit. Lowest-friction guide of the seven.

**Out of scope.** Recommending one emulator over another; CI orchestration
patterns (separate concern).

**Cross-links.** From every backend page and from `CONTRIBUTING.md`.

### 3.4 SFTP reliability

**Pain it retires.** Connection staleness on client IP change / NAT
rebind (rclone #1541, #3656); opaque dropped connections that hang rather
than surface a failure; keepalive + timeout settings; composition with
the existing `retry.md`.

**Evidence pointers.**

- In-repo: `sftp.md` § "Single-connection thread-safety caveat";
  BUG-209 / BUG-211 (Windows tempfile leak); BACKLOG ID-181
  (per-backend `ssh-rsa` opt-in, still open).
- External Tier-1 #10 (connection staleness), #9 (prefetch — partially
  covered in §3.2); cross-cutting #4 (SFTP reliability).

**Scope.** Keepalive settings, timeout composition, retry strategy for
transient drops, cross-link to prefetch tuning in §3.2.

**Dogfood plan.** Local `SFTPGo` container, drop the connection
mid-transfer via `iptables -j DROP` (Linux), `pfctl` (macOS) or
`Set-NetFirewallRule` (Windows), observe the failure shape with and
without keepalive configured. NAT-rebind documented as "simulated link
drop" — we cannot promise a real DSL-reconnect reproduction, and the
guide says so explicitly.

**Verdict.** Greenlit with honest scope. Phase 1.

**Out of scope.** Auth and host-key topics — those live in `sftp.md`
(already comprehensive) and its legacy-server section.

**Cross-links.** From `sftp.md` and `retry.md`.

### 3.5 Azure keyless auth & private endpoints

**Pain it retires.** Disabling shared-key auth and public access on a
storage account, then wiring `DefaultAzureCredential` plus Storage Blob
Data Contributor RBAC plus firewall rules for CI runners. Trips up users
on Microsoft Q&A 5769536 and similar threads. Adjacent to our iceboxed
ID-118b (Azure TLS CA bundle, Phase 2 — Azure Stack Hub / on-prem).

**Evidence pointers.**

- In-repo: BACKLOG ID-118b (iceboxed) for the on-prem variant;
  `azure-hns-setup.md` covers account-key auth only.
- External Tier-1 #6 (OIDC + RBAC + firewall for CI runners), #5 (SAS
  token expiry that fails silently on stream-style writes); Tier-2.C
  (GitHub-runner egress allowlist).

**Scope.** Sibling guide to `azure-hns-setup.md`: keyless setup, OIDC
federation for GitHub Actions and Azure DevOps, private-endpoint wiring,
egress allowlist, SAS-expiry diagnosis pattern.

**Dogfood plan.** Requires a real Azure subscription with elevated RBAC
(`User Access Administrator` or `Owner` on the resource group, plus
permission to create vNets / private endpoints / private DNS zones).
OIDC federation tested via a sacrificial workflow on a private GitHub
repo. SAS-expiry diagnosis reproduced by manufacturing a near-expired
SAS and writing through it. Significant prep cost.

**Verdict.** **Conditional.** Greenlit only when subscription access
with the required RBAC is confirmed available. Otherwise defer the
entire guide — partial coverage (keyless without private endpoints, or
vice versa) would mis-set user expectations.

**Out of scope.** Microsoft Entra ID administration (link to Microsoft
docs); Azure Stack Hub specifics (fold into ID-118b if it reactivates).

**Cross-links.** From `azure.md` and `azure-hns-setup.md`. To `retry.md`
and `troubleshooting.md`.

### 3.6 Credential & secret rotation

**Pain it retires.** S3 STS and static keys, Azure SAS and OIDC
federated identity, SFTP keypairs and host keys, SQL DSNs — all have
rotation patterns and visible failure shapes (typically `PermissionDenied`
or `BackendUnavailable`) that today are only documented for Azure
account-key rotation in `azure-hns-setup.md`.

**Evidence pointers.**

- In-repo: `Secret` wrapper (v0.13 ID-039), `__repr__` masking (v0.7
  AF-008), cross-backend masking tests in BACKLOG-DONE; only Azure has
  a documented rotation recipe.
- External: cross-cutting #1 ("ties into our `Secret` masking and typed
  error model"); Tier-1 #11 (SSH key rotation).

**Note on a source disagreement.** In-repo evidence for this category
was thin; external survey called it Tier-1 cross-cutting. The reframe:
in-repo evidence is thin precisely *because* rotation pain lands at
users' production environments, not in our test traces or bug reports.
External wins on breadth here.

**Scope.** One short recipe per backend: how to rotate, how to surface
rotation failures, how `Secret` masks the rotated value. Cross-link to
typed-error model.

**Dogfood plan.** Per backend, perform a real rotation against the same
target used elsewhere in this initiative (the dogfooded MinIO / R2 / B2
buckets from §3.1; the SFTPGo container from §3.4; the SQLite store
from §3.7; Azure rotation reuses the §3.5 subscription if §3.5 is
greenlit, otherwise the Azure half of this guide defers). Each rotation
recipe ends with the observed error shape when an in-flight stream hits
expired credentials.

**Verdict.** Greenlit per-backend. Phase 1 for S3 + SFTP + SQLite halves;
Azure half conditional on §3.5's subscription access.

**Out of scope.** Vendor-side rotation policies (link to AWS, Azure,
OpenSSH docs).

**Cross-links.** From every backend page.

### 3.7 SQLite operational notes

**Pain it retires.** SQLite live-file concurrent-write fragility —
syncing or copying a SQLite blob store while another process holds write
locks risks corruption (rclone #4377). `SQLBlobBackend` already enables
WAL plus `PRAGMA synchronous=NORMAL`, but the operational story ("do not
sync a live file", recommended backup mechanisms) is undocumented.

**Evidence pointers.**

- In-repo: `SQLBlobBackend` shipped v0.20.0 with WAL; no follow-up bug
  evidence.
- External Tier-1 #12 (rclone #4377).

**Open question.** Standalone guide or sidebar in `sql-blob.md`.
**Recommendation: sidebar** — single backend, ~200 words of content,
no cross-backend ripple.

**Dogfood plan.** Two concurrent Python processes writing to the same
SQLite blob store; observe WAL behavior and the lock-conflict failure
shape remote-store surfaces. Copy the file mid-write with `cp` and read
the copy back to demonstrate the inconsistent-snapshot risk. ~30
minutes of work on any laptop.

**Verdict.** Greenlit. Sidebar in `sql-blob.md`. Phase 1.

**Cross-links.** From `sql-blob.md`.

## 4. Tier-2 sidebar additions

Not full guides. Short additions to existing pages that retire support
load without justifying a new file.

| Addition | Target page |
|---|---|
| Minimum IAM policy snippet for AWS S3 | `s3.md` |
| Minimum `sshd_config` plus "we test atmoz/sftp on OpenSSH" | `sftp.md` |
| Azure egress allowlist one-liner | `azure.md` |
| HNS-vs-flat semantics table expansion (`is_folder`, `list_folders`, `delete_folder`) | `azure-hns-setup.md` |
| "We do NOT use adlfs/fsspec for Azure" disclaimer | `azure.md` |
| SAS-token-expiry failure-mode note | `azure.md` |

Several of these can be absorbed into Tier-1 guides above where the scope
overlaps (e.g. IAM-minimum may live in §3.1 if standalone fits poorly;
the HNS-vs-flat expansion belongs in `azure-hns-setup.md` regardless of
§3.5 progress).

## 5. Out of scope (Tier-3)

Explicitly NOT to be written. If a future contribution starts drafting
any of these, redirect to vendor docs instead.

- AWS account ownership and root-email governance
- MinIO operator console UX
- `s3fs-fuse` 64 PB quota reporting (FUSE-only, irrelevant to our Python
  `s3fs` usage)
- S3 Inventory not listing incomplete multipart uploads
- Generic DB driver / connection-pool tuning
- Self-hosted Azure-Blob-like servers (no real evidence)

## 6. Code-side questions for maintainers (NOT guides)

The external survey flagged three design or implementation matters, not
documentation gaps. All three have now been carved into the
`S3 Client-Implementation Strategy` section of
[BACKLOG.md](../BACKLOG.md): execute in order, ID-200 informs whether
ID-202 needs to also cover error-mapping wins.

1. **`s3fs` typed-error mapping fidelity** → **ID-200**. Does
   `_S3Base`'s error mapping preserve 403-vs-404 distinctions,
   SAS-expiry signals, and partial-upload failure shapes? A short audit
   driving five concrete scenarios (missing key, forbidden key, expired
   token, mid-stream multipart abort, directory-marker ambiguity)
   against a moto-backed `S3Backend`, recording target vs observed
   typed error per row. If any row diverges, opens a BUG-NNN.

2. **`S3Backend` default for `use_listings_cache`** → **ID-201**.
   Inheriting the `s3fs` default surprises `Store`-style readers with
   stale listings (fsspec/filesystem_spec #324, #1423). Spike measuring
   `list_files` / `iter_children` latency with cache on vs off at
   100 / 1 000 / 10 000 keys per prefix, plus staleness frequency in a
   write-then-list loop. Three exit dispositions: flip default, keep
   default with docs, or expose a first-class `Store.refresh()` API.

3. **Third S3 lane (`s3-boto3` direct)** → **ID-202**. Three of the
   Tier-1 S3 pains (boto3 / aiobotocore / s3fs pinning, 5 GB multipart
   restart, listings-cache staleness) are *s3fs-specific* and would not
   exist on a boto3-direct backend. PoC `S3Boto3Backend` sharing
   `_S3Base` where sensible, conformance-tested under moto, decided on
   three axes (user value, maintenance cost, interop loss) with
   ship / park / reject exit dispositions.

These three IDs run independently of the guide-authoring work in §§ 3–5;
their findings may inform the §3.1 and §3.2 guide content if landed
before those guides ship.

## 7. Sequencing recommendation

Phases are ordered by dogfood cost, not by user-pain ranking. The
authoring contract (§ 2.2) makes dogfood-feasibility the binding
constraint — a higher-pain guide we cannot validate yet is later in the
queue than a lower-pain guide we can ship now.

| Phase | Guides | Dogfood cost | Rationale |
|---|---|---|---|
| Phase 1 — zero / minimal new setup | §3.3 (local-dev emulators), §3.7 (SQLite sidebar), §3.4 (SFTP reliability) | Already in CI; laptop-only | Can start immediately; proves the authoring contract end-to-end on low-risk targets |
| Phase 2 — free-tier accounts | §3.1 (S3-compatible: MinIO + R2 + B2 scope), §3.6 (credential rotation, non-Azure halves), §3.2-SFTP-half (prefetch tuning) | Account signup; no budget | Sign up R2 + B2 free-tier accounts; reuse §3.1 buckets for §3.6 rotation tests |
| Phase 3 — budgeted dogfood | §3.2-S3-half (5 GB cliff — AWS budget), §3.5 (Azure keyless — subscription + RBAC), §3.6-Azure-half | Real AWS / Azure spend | Defer until access is confirmed; do not start writing without it |
| Tier-2 sidebars | `s3.md`, `sftp.md`, `azure.md`, `azure-hns-setup.md` additions | Negligible | Fold into adjacent Tier-1 PRs wherever the relevant page is already being edited |

Phase 1 candidates can ship in parallel and are mutually independent.
Phase 2 candidates depend on the free-tier accounts being provisioned
once; after that they are independent. Phase 3 is gated on §8 Q5.

## 8. Open questions

1. **One PR or many?** Each guide is a self-contained addition; per-guide
   PRs are easier to review but lose the consistency a single sweep
   would give. Recommendation: **per-Tier-1-guide PR**, with sidebar
   mop-up rolled into whichever PR touches the relevant backend page.

2. **Guide template.** The two existing guides (`azure-hns-setup.md`,
   `sftp.md`) have slightly different shapes. Extract a shared template
   (Prerequisites → Setup → Verification → Troubleshooting → Out of
   scope) before authoring the next one? Recommendation: **yes, but
   cheap** — derive from the structure both existing guides already
   converge on; do not over-engineer.

3. **Per-guide ownership.** Each guide needs a backlog item of its own
   when picked up. ID-199 (this proposal) is the parent; per-guide IDs
   split off as work begins. Recommendation: defer per-guide IDs until
   each guide is committed to.

4. **Code-side flags (§6).** Should the third-S3-lane question be folded
   into ID-114 (iceboxed PyArrow bucket-path research) or get its own
   ID? Recommendation: **own ID** — different design question, different
   evidence base.

5. **Dogfood budget and access (gates Phase 3).** §3.5 (Azure keyless)
   requires a real Azure subscription with elevated RBAC plus vNet /
   private-endpoint provisioning rights. §3.2's S3 5 GB sub-section
   requires an AWS bucket and ~10 GB of write traffic. Two paths: (a)
   authorize the spend / access up front and queue Phase 3 immediately
   after Phase 2; (b) ship Phase 1 + Phase 2 only and re-evaluate Phase
   3 once user pain on those sections is confirmed or fades.
   Recommendation: **(b) — ship what we can dogfood now**, treat
   Phase 3 as an explicit follow-on decision rather than an assumption.

---

This research is advisory per
[`CLAUDE.md` § Audits Rule 3](../../CLAUDE.md#audits) ("an audit's
authority is its diagnosis; its prescription is advisory"). The
diagnosis — seven pain themes with cross-validated evidence — is what to
trust. The proposed guide structure, scope boundaries, and sequencing
are starting points to challenge during pick-up.
