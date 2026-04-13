# Research: v1.0 Communication & Announcement Plan

**Date:** 2026-04-13
**Status:** Research complete — ready for review and refinement
**Backlog items:** ID-018 (conda-forge publishing) is the last gating release task; v1.0 announcement uses this plan

---

## 1. What Is remote-store and Who Is It For

### One-liner

> Write file storage code once. Run it against local files, S3, SFTP, or Azure.

### What it actually is

A Python library that gives every storage backend the same front door:
`store.read()`, `store.write()`, `store.list_files()`. Same call whether
files sit on a local disk, S3, SFTP, Azure Blob, HTTP, or a SQL table.
Streaming by default, atomic writes where the backend supports it, zero
runtime dependencies in the core package, native async for backends that
support it.

Authoritative inventory of backends, capabilities, extensions, and extras
lives in [`FEATURES.md`](../../FEATURES.md). Avoid copying that list into
announcement copy — link to it.

### What it is _not_

- Not a query engine (no SQL planning, no predicate pushdown over files)
- Not a table format (no Delta log, no Iceberg manifests)
- Not a filesystem reimplementation — delegates to `boto3`/`s3fs`,
  `paramiko`, `azure-storage-file-datalake`, `pyarrow`, `SQLAlchemy`
- Not an `fsspec` competitor on the same axis (see § 2)

### Audiences

1. **Citizen developers** — analysts, scientists, domain experts who write
   Python but shouldn't need to learn cloud SDKs to read and write files.
2. **Platform / tooling teams** — engineers who hand colleagues a safe,
   immutable-config API that can't be misused.
3. **Data engineering teams** — Bronze/Silver/Gold lakes via
   `Store.child()` + the PyArrow / Parquet extensions, without Spark.

---

## 2. The Landscape

remote-store's positioning is honest about where it overlaps with — and
defers to — other tools.

### Closest neighbours

- **fsspec** — the de facto Python filesystem abstraction. Big surface,
  big ecosystem, stateful caching. remote-store is the smaller, narrower
  alternative for teams that want `read/write/list/delete` with immutable
  config and no surprises.
- **obstore / obspec** — Rust-backed object store client. Faster on
  concurrent small reads against object stores. No SFTP, no streaming
  file-like interface. Different goals, partially overlapping audience.
- **smart_open** — drop-in `open()` replacement. No `list`, `delete`,
  `move`, `metadata`. Teams that outgrow `smart_open(...).read()` because
  they need management operations are remote-store's exact audience.
- **cloudpathlib** — `pathlib`-style classes for cloud stores. No SFTP,
  no streaming, implicit caching. remote-store rejects the pathlib
  metaphor for object stores: `Store` is the abstraction, not the path.
- **universal_pathlib (UPath)** — pathlib over fsspec. Inherits fsspec's
  surface and statefulness.
- **Raw SDKs (boto3, paramiko, azure-storage-\*)** — remote-store wraps
  these and exposes `unwrap()` as the escape hatch.

### Comparison table

| Dimension                | fsspec          | smart_open      | cloudpathlib    | obstore          | remote-store           |
|--------------------------|-----------------|-----------------|-----------------|------------------|------------------------|
| API surface              | broad           | `open()` only   | pathlib-style   | narrow           | narrow, capability-gated |
| Backend coverage         | 30+             | S3/GCS/Az/SFTP  | S3/GCS/Az       | S3/GCS/Az        | see [`FEATURES.md`](../../FEATURES.md) |
| SFTP support             | via sshfs       | Yes             | --              | --               | Yes                    |
| Local + in-memory        | Yes             | local fallback  | local mock      | local            | Yes (test-grade)       |
| List / glob / delete     | Yes             | --              | Yes             | Yes              | Yes                    |
| Atomic writes            | --              | --              | --              | --               | Yes (capability-gated) |
| Core runtime deps        | several         | minimal         | per SDK         | Rust binary      | none                   |
| Streaming I/O            | Yes             | Yes             | -- (downloads)  | bytes-oriented   | Yes (BinaryIO)         |
| Native async             | Yes             | --              | --              | Yes              | Yes (`remote_store.aio`) |
| PyArrow interop          | native          | --              | --              | via obspec       | `ext.arrow`, `ext.parquet` |
| Observability hooks      | --              | --              | --              | --               | `ext.observe` + OTel   |
| Config model             | per-filesystem  | URI-based       | per-client      | per-store kwargs | immutable Registry     |
| Formal contract          | --              | --              | --              | --               | Dafny-verified, conformance suite |
| Typing                   | limited         | limited         | good            | strong           | strict mypy            |

Yes / -- (dash) used per repo convention. Method counts and download
figures intentionally omitted — those drift faster than this document.

### Niche, in one sentence

More than `open()` (smart_open), less than a full filesystem (fsspec),
with SFTP, streaming, atomic writes, immutable config, native async, and
a formally verified backend contract.

---

## 3. Core Messaging

### Principle: share the way of working, don't sell

> "Here's a problem we had. Here's how we solved it. Here's what we
> learned. Maybe it helps you too."

### Message pillars

**Pillar 1 — The problem is real and boring.** Every team that touches
multiple storage systems writes the same glue code. Nobody maintains it
after the author leaves.

**Pillar 2 — One API, swap the config.** `store.read("data.parquet")`
works the same against local, S3, SFTP, Azure, HTTP, or SQL blob. Change
the config, not the code. Develop with `MemoryBackend`, deploy to S3
without touching application logic.

**Pillar 3 — Honest about boundaries.** A storage I/O layer. Not a query
engine, table format, catalog, or scheduler. Delegates to the SDKs you'd
pick anyway.

**Pillar 4 — A formally verified contract (the v1.0 differentiator).**
Backend behaviour is specified in Dafny and exercised by a conformance
suite that every backend (and every custom backend you write) runs
against. Mutation testing in CI prevents the test suite from going soft.
This is the strongest trust signal in the niche — nobody else in this
neighbourhood verifies their backend contract formally.

**Pillar 5 — Spec-Driven Development as a way of working.** Specs first,
tests against specs, code to pass tests, transparent backlog and audits.
The methodology is documented and reusable. Often as interesting to
readers as the library itself.

**Pillar 6 — Citizen developers as a design force.** Immutable config so
non-experts can't accidentally break state. Clear errors instead of raw
SDK tracebacks. Streaming that just works.

### Avoid

- "Better than fsspec / obstore / X" — position alongside, not against.
- Feature lists without a problem statement.
- "Production-ready" without evidence — link to test coverage,
  conformance suite, Dafny verification, the backlog.
- Marketing language ("revolutionary", "blazing fast").
- Overselling scope — be explicit about what it does NOT do.

---

## 4. Channels — Where to Announce

Curated, not exhaustive. Each entry below is one we'd actually use; the
previous version's long menu of speculative pitches has been cut.

### Tier 1 — Developer communities (launch week)

- **Hacker News (Show HN)** — link to GitHub. First comment explains the
  motivation, the formal-verification angle, and known limits. HN
  rewards candor.
- **Reddit r/Python** — "I built this" post. Code example showing the
  backend swap, honest "what this doesn't do" section, link to repo.
- **Python Discourse — Showcase** — design-focused writeup. This
  audience cares about *how* things are built; lead with SDD + Dafny.
- **lobste.rs** — short post if a member invite is available; technical
  audience that overlaps with HN but rewards substance differently.

### Tier 2 — Where citizen devs and data folks actually hang out

- **DataTalks.Club Slack** — largest data Slack. Data lake guide is the
  natural lead-in.
- **dbt Community Slack** — analytics engineers; SFTP-source +
  cloud-warehouse story resonates.
- **Polars Discord** — `ext.parquet` + `ext.arrow` adapter is the hook.
- **DuckDB Discord** — same story; remote-store as I/O layer under
  DuckDB's Parquet scanner.
- **MLOps Community Slack** — `MemoryBackend` for testing ML pipelines;
  `ext.integrity` for artifact verification.
- **Reddit r/dataengineering** — data lake patterns guide entry point.
- **Reddit r/datascience** + **r/learnpython** — reproducibility +
  beginner angles respectively.
- **Kaggle** — runnable notebook beats a blog post for this audience.

### Tier 3 — Industry segments with the pain right now

- **Fintech / banking data teams** — SFTP bank feeds + cloud analytics;
  immutable config and credential masking are direct hits.
- **Bioinformatics / health data** — SFTP for institutional exchange,
  S3 for analytics; one API for both.
- **MLOps / ML platforms** — multi-backend artifact storage, in-memory
  testing.
- **Data orchestrator integrations** — open discussions on Dagster,
  Airflow, Prefect repos. Dagster integration already ships
  (`ext.dagster`); use it as the example.
- **Consultancies / agencies** — reusable codebases across clients with
  different infra.

### Tier 4 — Content and media

- **Blog posts** (publish on personal site; cross-post to dev.to):
  1. **Methodology** — "Spec-driven development with formal verification:
     building a Python storage library". The most distinctive piece.
  2. **Problem story** — "Every team writes the same S3 wrapper. Here's
     why we open-sourced ours."
  3. **Use case** — "A portable data lake with Python — no Spark
     required." Built on the shipped data lake patterns guide.
  4. **SFTP bridge** — "SFTP isn't dead: bridging legacy and cloud with
     one Python API." Targets finance / healthcare specifically.
- **Newsletters** — Python Weekly, PyCoders, Data Engineering Weekly,
  Console.dev, TLDR, Changelog.
- **Podcasts** — pitch Talk Python, Python Bytes, Data Engineering
  Podcast, Changelog. Lead angle: SDD + formal methods, not "new lib".
- **Conferences** — PyCon lightning talk; PyData / SciPy poster or
  short talk. Sprint slot to attract contributors.

---

## 5. Calendar — Three Waves, Not One Splash

The previous day-by-day grid created false precision and went stale fast.
This version specifies pools and ordering principles; pick days based on
signal as it comes in.

### Pre-launch checklist (before the v1.0 tag)

- README quickstart works in under 30 seconds, end to end
- `FEATURES.md` regenerated against the v1.0 build
- 2-minute terminal screencast: install → write local → swap config →
  same code against MemoryBackend (or S3 if creds permit)
- Methodology blog post drafted (the long-lead piece)
- v1.0 release notes finalised; CHANGELOG ordered per repo convention

### Wave 1 — Launch week (developer communities)

Pool: HN Show HN, Reddit r/Python, Python Discourse, Twitter/X +
Bluesky thread, LinkedIn short post, methodology blog post, newsletter
submissions.

Ordering principles:
- Publish the methodology blog post first so HN/Reddit have a deep link.
- Stagger HN and Reddit by at least a day; both feeds dislike duplicates.
- Submit newsletters at the end of the week to capture the residual
  traffic into a recurring audience.

### Wave 2 — Citizen-dev and data communities (week 2)

Pool: DataTalks.Club, Polars Discord, DuckDB Discord, dbt Slack,
PySlackers, Reddit r/dataengineering / r/datascience / r/learnpython,
MLOps Community, Kaggle notebook.

Ordering principles:
- Lead in each community with the artefact most relevant to it
  (Parquet/Polars hook for Polars, data lake guide for r/dataeng,
  MemoryBackend for MLOps).
- Don't cross-post the same body — rewrite the lede per audience.

### Wave 3 — Industry-specific outreach (week 3+)

Pool: SFTP-bridge blog post + LinkedIn (fintech), bioinformatics post,
Dagster/Airflow/Prefect integration discussions.

Sustain (weeks 4+):
- Respond to every comment and issue. Trust is built here.
- Turn recurring questions into follow-up posts.
- Submit lightning talk proposals to PyCon / PyData / SciPy.
- Pitch podcasts.

---

## 6. The Trust Story — What's New Since the Last Plan

The previous version of this document leaned on "21 specs, 95% coverage,
strict mypy". Since then the trust story has grown into something
genuinely distinctive in this niche:

- **Dafny-verified backend contract.** Backend behaviour is specified in
  Dafny; the proofs are in `sdd/formal/` and run as a conformance gate.
- **Backend conformance suite.** Every backend (built-in and custom)
  exercises the same behavioural test suite. The Build-Your-Own-Backend
  guide ties the conformance suite to user code.
- **Mutation testing in CI.** Weekly mutation runs catch the case where
  tests pass but no longer test what they claim.
- **CodeQL hardening.** All open security/quality alerts resolved;
  CodeQL gates on PR.
- **Transparent audits.** Multiple published adversarial and
  design-compliance audits in `sdd/audits/` with tracked fixes.
- **Research-driven design.** Design decisions ship with published
  research docs in `sdd/research/`. This document is one of them.
- **Human + AI collaboration.** SDD pipeline, specs, audits, and much
  of the implementation were developed collaboratively with Claude.
  A real story about working with AI on production-grade software,
  beyond "I used Copilot for autocomplete."

These collectively are the v1.0 headline. Lead with them on HN and in
the methodology blog post.

---

## 7. Use the Existing Artefacts

The previous plan referred to PRs #113 and #114 as future content. Both
are shipped and live in the docs. Reference them:

- **Data lake patterns guide** — the strongest concrete use case. Lead
  with it in r/dataengineering, on Polars/DuckDB Discords, and in the
  use-case blog post.
- **Build-Your-Own-Backend guide** — the entry point for the "extend
  it" audience. Mention on Python Discourse and in integration
  discussions.
- **Retry policy guide** — concrete answer to "how does this handle
  flaky networks". Useful in fintech and platform-team conversations.
- **Async guide + `remote_store.aio`** — kills the previous plan's "no
  async yet" caveat. Lead with native Azure async as the proof point.
- **Performance guide and benchmark suite** — present numbers as
  numbers (ms + %), not judgments, per repo style.

For each artefact, link, don't paraphrase. The repo is the source of
truth; this plan should not duplicate it.

---

## 8. Metrics

Track after launch to learn what resonates, not to optimise vanity:

- **GitHub referrers** — which channel actually drives traffic.
- **PyPI downloads** via pypistats — adoption signal, lagging indicator.
- **Issue and discussion quality** — what people ask reveals messaging
  gaps; what they request reveals audience fit.
- **Conda-forge installs** once ID-018 lands — separate adoption
  channel, often institutional users.

Vanity metrics (stars, thread upvotes) are directional only. Don't tune
the next wave around them.

---

## 9. Recommended Approach — Summary

1. **Lead with the formal-verification + conformance-suite story.**
   This is the v1.0 differentiator and the strongest defensible claim
   on HN-style scrutiny.
2. **Lead with the problem, not the solution.**
3. **Be explicit about what it does NOT do.**
4. **Position alongside, not against** — fsspec, smart_open,
   cloudpathlib, obstore, UPath solve related but different problems.
5. **Three waves**: developer communities → citizen-dev / data
   communities → industry-specific outreach.
6. **Go where citizen devs are** — data Slacks and Discords, Kaggle —
   not just HN and r/Python.
7. **Tell the way-of-working story** — SDD + Dafny + AI collaboration is
   genuinely unusual.
8. **Make it trivially easy to try** — `pip install remote-store`, paste
   the quickstart, run it in 30 seconds.
9. **Engage deeply** — respond to every comment; incorporate feedback.
10. **Link, don't paraphrase.** `FEATURES.md`, the guides, the research
    docs, the audits all live in the repo. Point to them.

---

## Appendix — Draft messages

Drafts are intentionally short. Copy will go stale faster than the plan;
treat these as starting points, not templates.

**HN — Show HN title:**
> Show HN: remote-store v1.0 — One Python API for Local, S3, SFTP, Azure file storage

**HN — first comment lede:**
> Author here. remote-store gives every storage backend the same front
> door. Same `read`/`write`/`list`/`delete` whether the backend is local
> disk, S3, SFTP, Azure, HTTP, or a SQL table. The differentiator at
> v1.0 is a Dafny-verified backend contract and a conformance suite that
> every backend (including ones you write) runs against. It's not a
> query engine, table format, or fsspec replacement. Happy to answer
> questions on the methodology or the design choices.

**Reddit r/Python — title:**
> remote-store v1.0 — one Python API for files on local, S3, SFTP,
> Azure, HTTP, and SQL, with a formally verified backend contract

**LinkedIn — opener:**
> We enabled analyst teams to work with S3 and SFTP without learning
> boto3 or paramiko. The result is now an open-source Python library at
> v1.0, with a formally verified backend contract.
