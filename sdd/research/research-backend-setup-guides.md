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

## 2. Evidence base

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
documentation gaps. Surfacing here so they can be triaged separately. If
any reaches commit-worthy priority, open a dedicated backlog item; do
not let them block guide work.

1. **`s3fs` typed-error mapping fidelity.** Does `_S3Base`'s error
   mapping preserve 403-vs-404 distinctions, SAS-expiry signals, and
   partial-upload failure shapes? Specifically: does `s3fs` swallow
   `botocore.ClientError` before it reaches `_ErrorMappingStream`? A
   short audit would tell us whether §3.4 and §3.6 have the typed errors
   they need.

2. **`S3Backend` default for `use_listings_cache`.** Inheriting the
   `s3fs` default surprises `Store`-style readers with stale listings
   (fsspec/filesystem_spec #324, #1423). Worth considering
   `use_listings_cache=False` as our default with documented perf
   trade-off, instead of doc-only mitigation in §3.1.

3. **Third S3 lane (`s3-boto3` direct).** Three of the Tier-1 S3 pains
   (boto3 / aiobotocore / s3fs pinning, 5 GB multipart restart,
   listings-cache staleness) are *s3fs-specific* and would not exist on
   a boto3-direct backend. A short RFC weighing the third-lane
   maintenance cost against the cumulative s3fs pain footprint may be
   worth its own ID.

## 7. Sequencing recommendation

If picked up as one body of work, suggested order:

| Phase | Guides | Rationale |
|---|---|---|
| Phase 1 — highest pain | §3.1 (S3-compatible), §3.4 (SFTP reliability) | Converging in-repo + external evidence; clear scope |
| Phase 2 — cross-cutting | §3.2 (large-object tuning), §3.6 (credential rotation) | Each retires pain across multiple backends; existing snippets to lean on |
| Phase 3 — broader pulls | §3.5 (Azure keyless), §3.3 (local-dev emulators) | Azure keyless has strong external pull; local-dev consolidates scattered notes |
| Phase 4 — sidebars | Tier-2 table; §3.7 (SQLite as sidebar) | Mop-up alongside Phase 1 or 2 wherever a backend page is already being edited |

Phases are sequenceable but not strictly serial: §3.1 and §3.4 can ship
in parallel; sidebars are filler work folded into adjacent PRs.

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

---

This research is advisory per
[`CLAUDE.md` § Audits Rule 3](../../CLAUDE.md#audits) ("an audit's
authority is its diagnosis; its prescription is advisory"). The
diagnosis — seven pain themes with cross-validated evidence — is what to
trust. The proposed guide structure, scope boundaries, and sequencing
are starting points to challenge during pick-up.
