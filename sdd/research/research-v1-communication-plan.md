# Research: v1 Communication & Announcement Plan

**Date:** 2026-03-06
**Status:** Research complete — ready for review and refinement

---

## 1. What Is remote-store and Who Is It For

Before choosing channels and messages, the positioning needs to be clear.

### The one-liner

> One simple API for file storage. Local, S3, SFTP, Azure. Same methods,
> swappable backends, zero reinvention.

### What it actually is

A Python library that gives every storage backend the same front door.
`store.read()`, `store.write()`, `store.list_files()` — same call whether
files sit on a local disk, in S3, on an SFTP server, or in Azure Blob.
Streaming by default, atomic writes where the backend supports it, zero
runtime dependencies in the core package.

### What it is _not_

- Not a query engine (no SQL, no predicate pushdown)
- Not a table format (no Delta Lake log, no Iceberg manifests)
- Not a filesystem reimplementation (delegates to `boto3`, `paramiko`,
  `azure-storage-file-datalake`, `pyarrow` — the libraries you'd pick anyway)
- Not competing with `fsspec` on the same axis (see § 2)

### Primary audiences

1. **Citizen developers** — analysts, scientists, domain experts who write
   Python but shouldn't need to learn cloud SDKs to read and write files.
2. **Platform teams** — engineers who set up infrastructure and want to hand
   colleagues a simple, safe, immutable-config API that can't be misused.
3. **Anyone tired of rewriting storage glue** — if you've wrapped S3 or SFTP
   access more than once, this is that wrapper, tested and maintained.

### Secondary audiences

4. **Data engineers** building lightweight data lakes (Bronze/Silver/Gold via
   `Store.child()` + PyArrow adapter — see PR #114's data lake patterns guide).
5. **Teams that need observability** — `ext.observe` hooks + OpenTelemetry
   bridge give visibility into every I/O operation without instrumenting
   application code.

---

## 2. The Landscape — Where remote-store Sits

Understanding the ecosystem is essential for honest, non-salesy positioning.

### fsspec (Filesystem Spec)

- **What:** The de facto Python filesystem abstraction. 56+ public methods,
  async support, caching, transactions, built-in backends for dozens of
  storage systems.
- **Strengths:** Ubiquitous. Dask, Intake, pandas, and many tools integrate
  natively. Huge ecosystem of `fsspec`-based backends (`s3fs`, `adlfs`,
  `sshfs`, `gcsfs`).
- **Criticisms:** Large API surface, statefulness (caching surprises), poor
  static typing, "filesystem on top of object stores" impedance mismatch.
- **remote-store's angle:** remote-store is _not_ an fsspec replacement.
  It's a simpler, narrower tool for teams that want `read/write/list/delete`
  with zero learning curve and immutable config. fsspec is a power tool;
  remote-store is the box cutter that just works.

### obstore (by Development Seed)

- **What:** Rust-backed (via PyO3) object store client. Wraps the Apache
  `object_store` crate. S3, GCS, Azure. First-class async.
- **Strengths:** 9x throughput over fsspec for concurrent small reads,
  stateless API, self-contained (no boto3/Azure SDK), strong types.
- **Criticisms:** No SFTP, no streaming file-like interface, newer ecosystem.
- **remote-store's angle:** obstore optimises for raw throughput on object
  stores (cloud + local). remote-store optimises for _simplicity and
  portability_ across heterogeneous backends including SFTP, with streaming
  file-like I/O, observability, and immutable config. Different goals,
  overlapping but distinct audiences.

### smart_open (by RaRe Technologies)

- **What:** Drop-in replacement for Python's `open()` that handles S3, GCS,
  Azure, HDFS, SFTP, HTTP, and local files. 14M+ weekly PyPI downloads.
  A **key ecosystem project** with 120+ contributors.
- **Strengths:** Ubiquitous adoption, dead-simple API (`open("s3://...")` just
  works), transparent compression, minimal learning curve.
- **Criticisms:** Focused on open/read/write — no `list_files()`, no `glob()`,
  no `move()`, no `delete()`, no metadata. Not a storage management layer.
- **remote-store's angle:** smart_open solves "open a file at a URI."
  remote-store solves "manage files across backends with listing, deletion,
  atomic writes, observability, and immutable config." Complementary scopes.
  Teams that outgrow `smart_open("s3://…").read()` because they need listing,
  deletion, or observability are remote-store's exact audience.

### cloudpathlib (by DrivenData)

- **What:** `pathlib.Path`-style classes for S3, GCS, Azure. 608 GitHub stars.
  Familiar API, seamless caching, local-filesystem mocks for testing.
- **Strengths:** Pathlib muscle memory, automatic local caching, clean
  `CloudPath("s3://bucket/key")` constructor.
- **Criticisms:** No SFTP. Caching is implicit (can surprise). No streaming
  (downloads full files). No observability. No immutable config model.
- **remote-store's angle:** cloudpathlib is great for teams that think in
  `pathlib` and want caching. remote-store is for teams that need streaming,
  SFTP, atomic writes, and want explicit control over config and lifecycle.
  The pathlib metaphor breaks down for object stores; remote-store doesn't
  pretend files have a filesystem.

### universal_pathlib (UPath, by fsspec)

- **What:** Extends `pathlib` API over fsspec backends. `UPath("s3://…")`
  auto-dispatches to the right fsspec implementation.
- **Strengths:** Pathlib API everywhere, huge backend coverage via fsspec,
  converging with CPython 3.13+ pathlib ABC.
- **Criticisms:** Inherits fsspec's statefulness and large surface. Still
  stabilising internal implementation.
- **remote-store's angle:** UPath wraps fsspec in pathlib syntax.
  remote-store wraps native SDKs in a purpose-built storage API. Different
  philosophy — UPath says "paths are universal," remote-store says "stores
  are the abstraction."

### obspec (Protocol)

- **What:** A 10-method protocol formalising object store interfaces.
  Obstore is the primary implementation.
- **remote-store's angle:** Complementary. remote-store's `Backend` protocol
  could potentially implement `obspec` in the future for interop, but the
  scope differs — remote-store includes filesystem-style backends (local,
  SFTP) that obspec explicitly doesn't target.

### Raw SDKs (boto3, paramiko, azure-storage-*)

- **What:** The official clients. Full-featured, cloud-specific.
- **remote-store's angle:** remote-store _wraps_ these. It doesn't replace
  them — it provides a unified front door so application code doesn't need
  to know which SDK is underneath. `unwrap()` gives escape-hatch access
  when you need the native handle.

### Key differentiators for messaging

| Dimension              | fsspec          | smart_open      | cloudpathlib    | obstore          | remote-store        |
|------------------------|-----------------|-----------------|-----------------|------------------|---------------------|
| API surface            | ~56 methods     | `open()` only   | pathlib-style   | ~10 methods      | ~18 methods         |
| Backend scope          | 30+ filesystems | S3,GCS,Az,SFTP  | S3,GCS,Azure    | S3, GCS, Azure   | Local,S3,SFTP,Az,Mem|
| SFTP support           | via sshfs       | Yes             | No              | No               | Built-in            |
| Local filesystem       | Yes             | Yes (fallback)  | Mock only       | Yes (LocalStore) | Built-in            |
| Memory backend (test)  | Yes             | No              | Local mock      | No               | Built-in            |
| List/glob/delete       | Yes             | No              | Yes (pathlib)   | Yes              | Yes                 |
| Atomic writes          | No              | No              | No              | No               | Yes (capability-gated)|
| Runtime dependencies   | Yes             | Minimal         | SDK-based       | Rust binary      | Zero (core)         |
| Streaming I/O          | Yes             | Yes             | No (downloads)  | Bytes-oriented   | Yes (BinaryIO)      |
| Async                  | Yes             | No              | No              | Yes (first-class)| Sync-only (for now) |
| PyArrow interop        | Native          | No              | No              | Via obspec       | `ext.arrow` adapter |
| Observability          | No              | No              | No              | No               | `ext.observe`+OTel  |
| Config model           | Per-filesystem  | URI-based       | Per-client      | Per-store kwargs | Immutable Registry  |
| Typing                 | Limited         | Limited         | Good            | Strong           | Strict mypy         |
| Weekly PyPI downloads  | ~30M+           | ~14M+           | ~200K           | ~150K            | New                 |

### Positioning takeaway

remote-store occupies a specific niche: **teams that need more than `open()`
(smart_open) but less than a full filesystem abstraction (fsspec), with
streaming, SFTP, atomic writes, observability, and immutable config.** The
closest comparison is cloudpathlib, but remote-store adds SFTP, streaming,
atomic writes, observability, and rejects the pathlib metaphor for object stores.

---

## 3. Core Messaging — What to Say

### Principle: share the benefit and the way of working, don't sell

The goal is not "use remote-store instead of X." The goal is:

> "Here's a problem we had. Here's how we solved it. Here's what we learned.
> Maybe it helps you too."

### Message pillars

**Pillar 1: The problem is real and boring**

> Every team that touches multiple storage systems ends up writing the same
> glue code. A wrapper around S3 here, an SFTP helper there, a local
> fallback for testing. It's not hard work — it's tedious work that nobody
> maintains after the person who wrote it leaves.

**Pillar 2: One API, swap the config**

> `store.read("data.parquet")` works the same whether `store` points at a
> local directory, an S3 bucket, an SFTP server, or Azure Blob. Change the
> config, not the code. Develop locally with `MemoryBackend`, deploy to S3
> without touching application logic.

**Pillar 3: Honest about the boundaries**

> remote-store is a storage I/O layer. It does not do queries, table formats,
> catalogs, or scheduling. It delegates to the SDKs you'd pick anyway
> (boto3, paramiko, Azure SDK). It's the thin layer that makes them
> interchangeable.

**Pillar 4: The way of working (Spec-Driven Development)**

> The library is built with a spec-driven workflow: every feature starts as
> a spec, tests are written against the spec, then code is written to pass
> the tests. 21 specs, 95%+ coverage, strict mypy. The methodology itself
> may be as interesting as the library to some audiences.

**Pillar 5: Citizen developers as a design force**

> Born from enabling analyst teams who write Python but shouldn't need to
> learn boto3 or paramiko. Immutable config so non-experts can't accidentally
> break state. Clear errors instead of raw SDK tracebacks. Streaming that
> just works without tuning buffer sizes.

### Avoid

- "Better than fsspec / obstore / X" — position alongside, not against
- Feature lists without context — always lead with the problem
- "Production-ready" without evidence — share test coverage, spec count,
  the backlog transparency instead
- Marketing language — no "revolutionary", "game-changing", "blazing fast"
- Overselling scope — be clear about what it does NOT do

---

## 4. Where to Announce — Channels and Formats

### Tier 1: High-signal developer communities

#### Reddit r/Python

- **Format:** "I built" / "What I'm working on" post
- **Tone:** First person, conversational, honest about tradeoffs
- **What to include:**
  - The problem (rewriting storage glue)
  - Quick code example showing backend swap
  - Link to GitHub repo (not a landing page)
  - Honest "what this doesn't do" section
  - Ask for feedback in a first comment
- **Flair:** Use "I Made This" or similar project-showcase flair
- **Timing:** Weekday morning US Eastern tends to perform best
- **Example title:**
  > I built a Python library that gives S3, SFTP, Azure, and local files the
  > same read/write/list/delete API — here's what I learned

#### Hacker News — Show HN

- **Format:** `Show HN: remote-store — One API for file storage across
  Local, S3, SFTP, Azure` → link to GitHub repo
- **Tone:** Technical, concise, curious. HN rewards candor and punishes
  marketing-speak. First person, explain _why_ you built it.
- **First comment:** Add a comment explaining the motivation, the
  spec-driven approach, what's done, what's not. Ask: "What would you
  need to try this?"
- **Key:** Link to GitHub, not a docs site or landing page. Make it easy
  to try (`pip install remote-store`, copy the quickstart, run it).
- **What resonates on HN:**
  - The spec-driven development methodology
  - Zero runtime dependencies in core
  - The citizen-developer angle (enabling non-infrastructure people)
  - Honest "known limitations" section
- **Example title:**
  > Show HN: remote-store – One Python API for Local, S3, SFTP, Azure file storage

#### Python Discourse (discuss.python.org)

- **Category:** "Packaging" or general "Python Help" → "Showcase"
- **Format:** Longer-form post explaining the design decisions
- **Good for:** Reaching library authors, packaging enthusiasts, CPython
  contributors
- **Angle:** Lead with the spec-driven methodology and how it shaped the
  API design. This audience cares about _how_ things are built.

### Tier 2: Where citizen developers actually hang out

Citizen developers — analysts, scientists, domain experts who write Python —
don't frequent r/Python or Hacker News. They're in **domain-specific and
learning-focused communities.** This is where remote-store's "you don't need
to learn boto3" message lands hardest.

#### Slack communities (the watercoolers)

- **DataTalks.Club** (80K+ members) — The largest data Slack. Active channels
  for data engineering, analytics, ML. The data lake patterns guide is perfect
  content here. Citizen devs ask "how do I read from S3" in #general daily.
- **dbt Community** (66K+ members) — Analytics engineers who build transforms.
  They already deal with multi-backend storage for staging/output. The
  "immutable config + SFTP for legacy sources" angle resonates.
- **Locally Optimistic** (8K+ members) — Analytics leadership. The pitch here
  is platform-team-facing: "give your analysts a safe API, stop them from
  writing raw boto3."
- **PySlackers** (40K+ members) — General Python Slack. Good for the "I built
  this" announcement. More technical than the data Slacks.
- **Data Quality Camp** (9K+ members) — Teams obsessed with data reliability.
  Atomic writes + observability hooks are directly relevant.
- **Real Python Slack** — Learners and intermediate devs. The quickstart
  tutorial format works here. "Read from S3 in 5 lines" is compelling.

#### Discord communities

- **Polars Discord** — Users of Polars are reading/writing Parquet constantly.
  The PyArrow adapter that makes `store` a drop-in for `pq.read_table()` is
  the hook. These users currently deal with `fsspec` or raw `boto3` for I/O.
- **DuckDB Discord** + **MotherDuck Community Slack** — Same story: DuckDB
  users need file I/O to feed their queries. `remote-store` as the I/O layer
  under DuckDB's Parquet scanner is a natural fit.
- **Data Science Discord** (14K+) — Broad data science audience. The
  "MemoryBackend for tests, S3 for prod" story resonates with anyone tired
  of mocking S3 in unit tests.
- **Python Discord** (300K+) — Massive general Python community. Good for
  visibility, but noisy. Time announcements for when channels are active.

#### Kaggle (6M+ data scientists)

- **Format:** Notebook showing remote-store + Polars/DuckDB reading Parquet
  from multiple backends with identical code. Kaggle users are hands-on —
  a runnable notebook beats a blog post.
- **Discussion forums:** "Tips & Techniques" discussions about data loading
  are common. A post about "simplifying multi-backend file access" fits.

#### Reddit (domain-specific subs)

- **r/dataengineering** (350K+) — The data lake patterns guide is the entry
  point. Bronze/Silver/Gold with `Store.child()` + PyArrow. Be explicit about
  what remote-store is NOT.
- **r/datascience** (900K+) — Scientists who write Python. The "swap backend
  without changing code" story for reproducibility (local dev → cloud prod).
- **r/bioinformatics** (100K+) — SFTP is everywhere in genomics data exchange.
  "One API for your SFTP data sources and your S3 results bucket" hits home.
- **r/learnpython** (900K+) — Beginners learning file I/O. A tutorial post
  "Beyond `open()`: reading files from S3, SFTP, Azure" could drive awareness.

#### YouTube / tutorial platforms

- **Audience:** Self-taught analysts, bootcamp grads, career switchers.
  These people learn by watching, not reading docs.
- **Format:** 10-minute tutorial: "Read files from anywhere in Python"
  showing local → S3 → SFTP with the same code. Terminal-focused, no slides.
- **Channels to pitch:** Real Python, ArjanCodes, mCoding, Tech With Tim,
  Rob Mulla (data science focus).

#### Newsletters that reach citizen devs

- **Python Weekly** / **PyCoders Weekly** — Standard Python newsletters
- **Data Engineering Weekly** — Targeted at the data infra crowd
- **Pandas Illustrated** (Substack) — Reaches DataFrame-oriented analysts
- **Data Engineering Central** (Substack) — DuckDB/Polars audience
- **Console.dev** — Curates interesting developer tools weekly
- **TLDR** / **Changelog** — Broader dev newsletters with Python sections

### Tier 3: Startup and industry segments

These are organisations that would _use_ remote-store, not just _discuss_ it.
Reaching them requires different channels than developer communities.

#### Startup segments that benefit directly

**1. Data infrastructure startups (Airbyte, dltHub, Meltano, Dagster)**
- These build ETL/ELT tools. Their users deal with multi-backend file I/O
  constantly. remote-store could be a dependency or recommended companion.
- **Action:** Open issues or discussions on their repos showing integration
  examples. "Here's how remote-store + Dagster simplifies multi-backend I/O."

**2. Healthcare / life sciences data platforms**
- SFTP is mandated by HIPAA-adjacent workflows (lab results, claims files,
  imaging metadata). S3 is where analytics happens. Both in one pipeline.
- **Channels:** Health Data Science Slack, r/bioinformatics, AMIA forums
- **Pitch:** "SFTP for ingest, S3 for analytics, one API, credential masking
  built in."

**3. Fintech / banking data teams**
- Bank feeds arrive via SFTP. Analytics sits in S3/Azure. Legacy systems
  aren't going away. The "SFTP + cloud" story is their daily reality.
- **Channels:** Fintech Slack communities, LinkedIn fintech groups
- **Pitch:** "Stop maintaining separate SFTP and S3 wrappers. Credential
  masking in logs. Atomic writes for reconciliation files."

**4. IoT / manufacturing / edge computing**
- Devices write to local storage or edge SFTP. Cloud aggregation in S3/Azure.
  The local → cloud pipeline is remote-store's sweet spot.
- **Channels:** r/IoT, industrial Python meetups, AWS IoT community

**5. ML platforms / MLOps teams**
- Model artifacts, training data, evaluation results — all need multi-backend
  storage. The MemoryBackend for testing ML pipelines is a differentiator.
- **Channels:** MLOps Community Slack (9.3K), Weights & Biases community,
  r/mlops

**6. Consultancies and agencies**
- Build for multiple clients with different infra. "One storage API that
  works whether the client uses S3, Azure, or on-prem SFTP" is a real
  selling point for reusable codebases.
- **Channels:** LinkedIn, agency-focused tech meetups

**7. Research labs and universities**
- Scientists share data via institutional SFTP, compute on cloud. The
  "develop locally with MemoryBackend, deploy to S3" story maps to
  laptop → HPC cluster workflows.
- **Channels:** Jupyter Discourse, Scientific Python community, domain
  conferences (SciPy, PyData, PyCon sprints)

#### Tool-specific communities (where users have the problem right now)

| Tool community | The pain point remote-store solves |
|---------------|----------------------------------|
| **Polars** Discord/GitHub | "How do I read Parquet from S3?" → PyArrow adapter |
| **DuckDB** Discord | "How do I scan files across backends?" → `ext.arrow` |
| **Pandas** (SO/Reddit) | "How do I write to S3?" → `store.write()` |
| **Airflow** Slack | "How do I abstract file transfers?" → Store API (`read`/`write` across backends) |
| **Dagster** Slack | "How do I make I/O manager backend-agnostic?" → Registry |
| **Prefect** community | Same as Dagster — pipeline I/O abstraction |
| **FastAPI** Discord | "How do I handle file uploads to S3/local?" → Store |
| **Jupyter** Discourse | "How do I read remote files in notebooks?" → quickstart |

### Tier 4: Content and media

#### Blog posts (dev.to / Medium / personal)

- **Post 1 — The methodology story:** "Building a spec-driven Python library:
  what I learned." The SDD process, 21 specs, adversarial audits, AI
  collaboration. This is the most distinctive and shareable piece.
- **Post 2 — The problem story:** "Every team writes the same S3 wrapper.
  Here's why I open-sourced ours." Problem-first, practical, code examples.
- **Post 3 — The use-case story:** "A portable data lake with Python — no
  Spark required." Based on PR #114's data lake patterns guide. The
  Bronze/Silver/Gold architecture diagram is visually compelling.
- **Post 4 — The SFTP story:** "SFTP isn't dead: bridging legacy and cloud
  with one Python API." Targets the finance/healthcare audience specifically.

#### LinkedIn

- **Format:** Short post (< 300 words) with a clear hook
- **Angle 1 (platform teams):** "We enabled our analyst teams to work with
  S3 and SFTP without learning boto3 or paramiko."
- **Angle 2 (engineering managers):** "How spec-driven development with AI
  produced a 1,400-test Python library in ~11 weeks."
- **Angle 3 (data leads):** "Our analysts stopped asking how to upload to S3.
  Here's the library that made it a non-question."

#### Twitter/X, Bluesky, Mastodon

- **Format:** Thread (4–6 posts) or single post with link
- **Hook:** Start with the problem, not the solution
- **Example thread opener:**
  > Every team I've worked with has written their own S3 wrapper.
  > Then their own SFTP wrapper. Then a "unified" one that wraps both.
  > Then someone leaves and nobody maintains it.
  >
  > I open-sourced the version that broke the cycle. 🧵

#### Python/Data podcasts and newsletters

- **Python Bytes, Talk Python, Real Python newsletter, Data Engineering
  Weekly, PyCoders Weekly**
- **Format:** Submit for inclusion / suggest as a topic
- **Angle:** "New library for unified file storage" or "Spec-driven
  development in practice"

#### PyCon / local meetups

- **Lightning talk:** 5 minutes on the spec-driven approach
- **Poster session:** Architecture diagram + live demo
- **Sprint:** Get contributors to tackle backlog items

---

## 5. Content Calendar — Suggested Sequence

The goal is a wave, not a single splash. Each piece builds on the previous.

### Pre-launch (before v1.0 tag)

1. **Polish README** — ensure quickstart works in < 30 seconds
2. **Merge PR #114** (data lake patterns guide) — gives a compelling
   use-case document to reference
3. **Record a 2-minute demo** — terminal screencast showing:
   - `pip install remote-store`
   - Write a file to local
   - Change config to S3 (or MemoryBackend for demo)
   - Same code, different backend
4. **Write the blog post** — "Building a spec-driven Python library"
   (methodology story, not a product launch)

### Launch week (v1.0 tag) — developer communities

| Day | Channel | Content |
|-----|---------|---------|
| Mon | Blog post (dev.to/Medium) | Publish methodology story |
| Tue | Hacker News | Show HN with GitHub link |
| Tue | Reddit r/Python | "I built this" post |
| Wed | Python Discourse | Design-focused writeup |
| Wed | Twitter/X, Bluesky | Thread with problem hook |
| Thu | Reddit r/dataengineering | Data lake patterns angle |
| Thu | LinkedIn | Professional short post |
| Fri | Submit to newsletters | Python Bytes, PyCoders, Data Eng Weekly, Console.dev |

### Week 2 — citizen-dev and data communities

| Day | Channel | Content |
|-----|---------|---------|
| Mon | DataTalks.Club Slack | Share in #general with data lake angle |
| Mon | Polars Discord | "PyArrow adapter for multi-backend Parquet I/O" |
| Tue | DuckDB Discord | "Using remote-store as I/O layer for DuckDB" |
| Tue | dbt Community Slack | Short post: SFTP sources + S3 staging |
| Wed | Reddit r/datascience | "Swap storage backends for reproducibility" |
| Wed | PySlackers Slack | "I built this" announcement |
| Thu | Kaggle notebook | Runnable notebook: multi-backend Parquet |
| Thu | Reddit r/learnpython | Tutorial: "Beyond open() — files from anywhere" |
| Fri | MLOps Community Slack | "MemoryBackend for testing ML pipelines" |

### Week 3 — industry-specific outreach

| Day | Channel | Content |
|-----|---------|---------|
| Mon | Blog post #2 | "SFTP isn't dead: bridging legacy and cloud" |
| Mon | LinkedIn (fintech angle) | Short post for financial data teams |
| Tue | Reddit r/bioinformatics | "One API for SFTP data sources + S3 results" |
| Wed | Data Quality Camp Slack | Atomic writes + observability hooks angle |
| Thu | YouTube pitch | Contact ArjanCodes / Real Python for collab |
| Fri | Locally Optimistic Slack | Platform-team angle for analytics leaders |

### Week 4+ — sustain and expand

- Respond to every comment and issue — this is where trust is built
- Write follow-up posts addressing recurring questions
- Submit lightning talk proposals to PyCon, PyData, SciPy
- If traction in a specific community, write targeted content for it
- Write a comparison post (not "vs" — "how remote-store complements
  smart_open, cloudpathlib, fsspec, and obstore")
- Pitch to podcast hosts: Talk Python, Python Bytes, Data Engineering
  Podcast, Changelog
- Open integration discussions on Dagster/Airflow/Prefect repos

---

## 6. Concrete Draft Messages

### Reddit r/Python — post title + body

**Title:**
> I built a Python library that gives S3, SFTP, Azure, and local files the
> same read/write API — what I learned along the way

**Body:**

```
Hey r/Python,

I've been working on `remote-store`, a library that came out of a real
problem: enabling analyst teams to work with files on S3, SFTP servers,
and local disks without having to learn boto3, paramiko, or Azure SDKs.

The idea is simple — one `Store` object with `read()`, `write()`,
`list_files()`, `delete()`. Swap the backend config, the code stays the
same. MemoryBackend for tests, LocalBackend for dev, S3Backend for prod.

```python
from remote_store import BackendConfig, Registry, RegistryConfig, StoreProfile

config = RegistryConfig(
    backends={"s3": BackendConfig(type="s3", options={"bucket": "my-bucket"})},
    stores={"data": StoreProfile(backend="s3", root_path="data")},
)

with Registry(config) as registry:
    store = registry.get_store("data")
    store.write("hello.txt", b"Hello, world!")
    print(store.read_bytes("hello.txt"))
```

**What it does:**
- read, write, list, delete, move, copy, exists, glob
- Streaming I/O by default (large files don't blow up memory)
- Atomic writes where the backend supports it
- PyArrow filesystem adapter (works with Parquet, Polars, DuckDB)
- Observability hooks + OpenTelemetry bridge
- Zero runtime dependencies in the core package

**What it does NOT do:**
- No query execution (that's Polars/DuckDB/Spark)
- No table format protocols (that's Delta Lake/Iceberg)
- No async yet (sync-only, `asyncio.to_thread()` as workaround)
- No GCS backend yet (S3, SFTP, Azure, Local, Memory today)

The whole thing is built spec-driven: 21 specs, tests written against
specs before code, 95%+ coverage, strict mypy. The methodology was as
interesting to develop as the library itself.

GitHub: https://github.com/haalfi/remote-store
PyPI: https://pypi.org/project/remote-store/
Docs: https://remote-store.readthedocs.io/

Happy to answer questions. Feedback welcome — especially on what
you'd need that isn't there.
```

**First comment:**

```
Author here. Some context on why this exists:

I work with teams where analysts write Python but aren't (and shouldn't
need to be) infrastructure engineers. They need to read CSV files from
SFTP, write Parquet to S3, and shouldn't have to learn three different
SDKs to do it.

The config is immutable by design — once created, a Store can't be
accidentally reconfigured. Credentials are auto-masked in logs and repr().
Errors are clear (`NotFound`, `AlreadyExists`, `PermissionDenied`) instead
of raw SDK tracebacks.

The spec-driven approach: every feature starts as a written spec (we have
21 now), tests are written against the spec, then code passes the tests.
It's slower but catches design issues before they become API debt.

What would make you try something like this? Curious what the gap is
between "interesting" and "I'd actually use it."
```

### Hacker News — Show HN

**Title:**
> Show HN: remote-store – One Python API for Local, S3, SFTP, Azure file storage

**First comment:**

```
Hi HN — I'm the author. remote-store came out of enabling analyst teams
who write Python but shouldn't need to learn boto3 or paramiko.

The pitch: store.read("file.csv") works the same whether the store points
at a local directory, S3 bucket, SFTP server, or Azure. Change the config,
not the code. MemoryBackend for tests, cloud for prod.

What's different from fsspec: much smaller API surface (~18 methods vs ~56),
immutable config (no stateful surprises), zero runtime dependencies in core,
built-in observability hooks + OpenTelemetry bridge.

What it's NOT: not a query engine, not a table format, not async (yet).
Delegates to boto3/paramiko/Azure SDK under the hood. The scope is
deliberately narrow — unified I/O, nothing more.

Built spec-driven: 21 formal specs, tests against specs before code,
95%+ coverage, strict mypy. The methodology is documented in the repo
if that's interesting to anyone.

v0.13 is current. Approaching v1. Would love feedback on what's missing
or what would make you reach for this vs writing your own wrapper.

GitHub: https://github.com/haalfi/remote-store
```

### Blog post — outline

**Title:** "Spec-Driven Development in Practice: Building a Python Storage Library"

**Sections:**
1. The problem (everyone writes storage wrappers, nobody maintains them)
2. The decision to open-source it
3. What spec-driven development means in practice
   - A spec before code — show a real spec excerpt
   - Tests against specs, not against implementation
   - The adversarial audit (sdd/audit-001)
   - Backlog as living document
4. The API design choices and why
   - Why 18 methods, not 56
   - Why immutable config
   - Why zero core dependencies
   - Why `MemoryBackend` matters more than you'd think
5. What I'd do differently
6. The roadmap (retry policy research, async, GCS)
7. Try it: `pip install remote-store`

### LinkedIn — short post

```
We enabled our analyst teams to work with S3 and SFTP without learning
boto3 or paramiko. The result became an open-source Python library.

remote-store gives every storage backend — local disk, S3, SFTP, Azure —
the same simple API. Change the config, not the code. Stream large files
without blowing up memory. Test with an in-memory backend, deploy to
cloud without changing a line.

Built spec-driven: 21 formal specs, tests before code, 95%+ coverage.

It's not a query engine, not a table format, and it doesn't try to
replace your existing SDKs. It just gives them the same front door.

GitHub: https://github.com/haalfi/remote-store

What storage problems does your team keep solving over and over?
```

---

## 7. Leveraging PR #113 and PR #114

### PR #113 — Retry policy research (ID-010)

This research document is _itself_ shareable content:

- **Blog post angle:** "How we're designing retry policy for a multi-backend
  storage library" — shows the research-driven, transparent approach
- **HN/Reddit angle:** The survey of retry approaches across boto3, paramiko,
  Azure, tenacity, urllib3, obstore is genuinely useful reference material
- **Timing:** Share after the spec and implementation ship (post-v1), not
  as a standalone

### PR #114 — Data lake patterns guide (ID-034)

This is the strongest "use case" content available:

- **r/dataengineering:** Lead with the Bronze/Silver/Gold pattern, the
  architecture diagram, and the honest "what this does not get you" section
- **Blog post:** "Building a portable data lake with Python — no Spark
  required" (the guide's content is essentially ready for this)
- **The architecture diagram** from the guide is visually compelling:

```
┌──────────────────────────────────┐
│  Query / Compute                 │
│  Polars · DuckDB · Pandas        │
├──────────────────────────────────┤
│  Table Format (optional)         │
│  Delta Lake · PyIceberg           │
├──────────────────────────────────┤
│  PyArrow FileSystem interface    │
├──────────────────────────────────┤
│  remote-store                    │
├──────────────────────────────────┤
│  Backend                         │
│  Local · Memory · S3 · SFTP · Azure│
└──────────────────────────────────┘
```

- **Key message:** remote-store owns the I/O layer. Everything above — formats,
  queries, catalogs — belongs to purpose-built tools. This honest boundary
  makes the library more trustworthy, not less.

---

## 8. The "Way of Working" Story

This is potentially the most distinctive and shareable angle. Most library
announcements focus on features. Few talk about _how_ they were built.

### What makes remote-store's process unusual

1. **21 formal specs** before any code — each spec has an ID, test markers
   reference spec sections (`@pytest.mark.spec("S3-003")`)
2. **Adversarial audits** — two documented audits (one adversarial review,
   one design-compliance audit) with published findings and tracked fixes
3. **Transparent backlog** — `sdd/BACKLOG.md` is in the repo, shows what's
   done, what's in progress, what's deferred, with version tags
4. **Research documents** — design decisions start with published research
   (async API research, retry policy research, logging/monitoring research)
5. **Claude Code as development partner** — the SDD pipeline, specs, audits,
   and much of the implementation were developed collaboratively with AI.
   This is a genuine story about human-AI collaborative software development
   that goes beyond "I used Copilot for autocomplete."

### Where to tell this story

- **Blog post** (primary) — the methodology is the headline
- **PyCon lightning talk** — 5 minutes on SDD with live examples
- **Python Discourse** — the process-oriented audience will engage deeply
- **HN first comment** — mention it, link to the specs directory

---

## 9. Metrics to Track

After launch, track these to understand what resonates:

- **GitHub stars and forks** — vanity but directional
- **PyPI downloads** (via pypistats.org) — actual adoption signal
- **GitHub issues opened** — engagement quality
- **Which channel drove the most traffic** (GitHub referrers page)
- **What questions people ask** — reveals messaging gaps
- **What feature requests come in** — reveals audience fit

---

## 10. Summary — Recommended Approach

### Strategy: three waves, not one splash

**Wave 1 (launch week):** Developer communities — r/Python, HN, Discourse,
Twitter/Bluesky, LinkedIn. Establish credibility and get initial feedback.

**Wave 2 (week 2):** Citizen-dev communities — DataTalks.Club, Polars/DuckDB
Discord, dbt Slack, Kaggle, r/datascience, r/learnpython. Go where the
people who _have the problem_ actually hang out.

**Wave 3 (week 3+):** Industry-specific outreach — finance (SFTP + S3),
healthcare (HIPAA workflows), bioinformatics (data exchange), ML platforms
(artifact storage). Plus integration discussions on Dagster/Airflow/Prefect.

### Principles

1. **Lead with the problem**, not the solution
2. **Be honest about boundaries** — what it does NOT do is as important as
   what it does
3. **Tell the methodology story** — SDD is genuinely unusual and interesting
4. **Use the data lake guide** (PR #114) as a concrete use-case showcase
5. **Go where citizen devs are** — Slack communities (DataTalks 80K, dbt 66K,
   PySlackers 40K), Discord (Polars, DuckDB, Python 300K), Kaggle (6M).
   These people don't read Hacker News.
6. **Engage deeply** — respond to every comment, incorporate feedback
7. **Position alongside, not against** — smart_open, cloudpathlib, fsspec,
   obstore all solve related but different problems. Be specific about the
   niche: "more than `open()`, less than a full filesystem, with SFTP,
   streaming, atomic writes, and observability."
8. **Target startups with the pain** — fintech (SFTP bank feeds), healthcare
   (HIPAA file exchange), data platforms (multi-backend I/O), consultancies
   (client-agnostic codebases)
9. **Make it trivially easy to try** — `pip install remote-store`, paste the
   quickstart, run it in 30 seconds. Kaggle notebook for hands-on learners.
10. **The way of working (SDD + AI collaboration) is the most distinctive
    story** — most libraries don't ship with 21 specs, adversarial audits,
    and a transparent backlog
11. **Create tool-specific integration content** — show remote-store + Polars,
    remote-store + DuckDB, remote-store + Dagster. Meet people in _their_
    ecosystem, not yours.
12. **Write four blog posts**, not one — methodology, problem story, data lake
    patterns, SFTP bridge story. Each targets a different audience.
