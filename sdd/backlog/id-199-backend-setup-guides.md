# ID-199 — Backend setup & configuration guides expansion
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Expand the backend-related guide set in `docs-src/guides/` based on user
pain mined from two sources: in-repo signal (traces, BACKLOG, CHANGELOG,
PRs) and an external survey of GitHub issues across `boto3`/`s3fs`/
`azure-storage-blob`/`paramiko`/`fsspec`, Stack Overflow, Reddit, and
vendor forums. Seven candidate guides identified; full pain mapping,
scope boundaries, sequencing, and code-side flags are in
[research](../research/research-backend-setup-guides.md). The two existing
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
see [BACKLOG-DONE.md](../BACKLOG-DONE.md) (ID-201's disposition shipped
as BK-257).

**Sequencing (dogfood-cost ordered, see research § 7):**
Phase 1 (zero new setup) = §3.3 + §3.7 + §3.4;
Phase 2 (free-tier accounts) = §3.1 + §3.6 non-Azure halves + §3.2 SFTP half;
Phase 3 (budgeted dogfood — gated on the access decision in research § 8 Q5) = §3.2 S3 half + §3.5 + §3.6 Azure half;
Tier-2 sidebars mop up alongside Phase 1/2.

Effort `L` reflects the parent scope; each individual guide is M-sized.
