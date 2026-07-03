# Research: `lx` as Tooling for an `llms-full.txt` / Repo-Context Bundle

**Date:** 2026-05-30
**Context:** Evaluation request against ID-161 (publish `llms.txt`). The
question: could [`rasros/lx`](https://github.com/rasros/lx) be a sound tool to
produce a "long LLM version" of either repo content or docs content for
remote-store? This doc records the evaluation, separates the two distinct
deliverables it touches, and routes the durable outcome into backlog items
(ID-161 adapted; ID-216 created).

---

## 1. What `lx` is

[`lx`](https://github.com/rasros/lx) is an "LLM context bundler": a CLI that
walks directories and consolidates files into a single LLM-ready blob.

| Attribute | Value |
|---|---|
| Language | Go |
| License | MIT |
| Maturity | 48★, v1.2.0 (2026-04-20), 13 releases, single-maintainer |
| Inputs | file paths, directories, URLs, archives (zip/tar/7z/rar), documents (PDF/DOCX/XLSX/PPTX) |
| Filtering | respects `.gitignore` / `.lxignore`; `-i`/`-e` include/exclude; skips binaries |
| Output | Markdown (default), XML (Claude-optimised), HTML, bare text |
| Extras | token estimation, tree/skeleton views, clipboard, stdin/stdout |

It is a capable, general-purpose tool. The evaluation below is about *fit for a
specific job*, not capability in the abstract.

## 2. The two deliverables `lx` is being measured against

The request conflates two things that ID-161 deliberately keeps separate:

1. **`llms.txt`** — the ID-161 core deliverable. A small, **hand-curated**
   discovery file (one H1, a one-paragraph summary, a short link list) per the
   [llmstxt.org](https://llmstxt.org/) §2 standard. There is nothing to bundle;
   a generator is the wrong category of tool. **`lx` is not applicable here.**

2. **`llms-full.txt`** — the "long version": concatenated full prose of the
   guides, for tools that prefer one large context file. ID-161 lists this as an
   **out-of-scope optional follow-on** ("Worth a separate ID if demand
   appears"). This is the only deliverable where a bundler like `lx` is even a
   candidate.

So evaluating `lx` "for ID-161" really means evaluating it for a *future,
separate* `llms-full.txt` effort, not for ID-161's exit criteria.

## 3. Evaluation: `lx` for a published `llms-full.txt`

`lx` *can* concatenate `docs-src/` into one file. But for a **published**
artifact built from this repo's docs pipeline, it is a weak fit. The pipeline
(`mkdocs.yml`) is the reason:

| Pipeline element | Effect on a raw-source bundler like `lx` |
|---|---|
| `gen-files` + `scripts/gen_pages.py` | API reference pages are **generated at build time** from `src/`. `lx` reading `docs-src/` would **omit the entire API reference.** |
| `scripts/mkdocs_hooks.py` (BK-171) | Rewrites on-disk repo paths to `docs.remotestore.dev` URLs. `lx` would emit **on-disk relative links**, not site URLs. |
| `literate-nav` + `SUMMARY.md` | Reading order is curated. `lx` traverses filesystem/ignore order, **not nav order**, so a long bundle would read out of sequence without hand-maintained section args. |
| `mkdocstrings` | Docstring-rendered API surface lives only in the built HTML, never in `docs-src/`. Invisible to a source bundler. |

Two further concerns, independent of the pipeline:

- **Standard mismatch (repo vs docs).** The `llms-full.txt` convention is
  concatenated *documentation prose*, not source code. Pointing `lx` at the
  *repo* produces a code dump (a different artifact for a different audience).
  Only `docs-src/` is the right target, and per the table above even that is
  lossy.
- **Ecosystem friction / drift.** Adding a Go binary to a Python/hatch +
  pip-MkDocs build means CI install, a pinned version, and supply-chain trust in
  a single-maintainer tool. A manual `lx` run would silently rot, violating
  CLAUDE.md principle 3 (repo describes reality at every commit).

## 4. Better-fit alternative for `llms-full.txt`

A MkDocs-native plugin solves every row of the §3 table because it operates on
the **rendered** output, inside `mkdocs build`, in the existing pip ecosystem:

- **[`mkdocs-llmstxt`](https://github.com/pawamoy/mkdocs-llmstxt)** (PyPI) — by
  pawamoy, **the same author as `mkdocstrings`, which this repo already uses.**
  Emits both `llms.txt` and `llms-full.txt` (`full_output:` + `sections:`),
  respects nav, captures generated API pages and rewritten URLs, and pins via
  the existing docs env.
- Alternatives in the same niche:
  [`mkdocs-llms-source`](https://pypi.org/project/mkdocs-llms-source/),
  [`mkdocs-llmstxt-md`](https://github.com/noklam/mkdocs-llmstxt-md).

If the long-version idea gathers demand, the sound path is a separate ID specced
around `mkdocs-llmstxt`, not an external Go bundler. ID-161 stays the small
curated file.

## 5. Where `lx` genuinely shines (→ ID-216)

`lx` is well-suited to a different, **orthogonal** job: **ad-hoc, on-demand
bundling of *repo* content** to hand a coding agent (or a one-off prompt)
whole-codebase or whole-subtree context. The XML/Claude format, token
estimation, `.gitignore` honouring, and tree/skeleton views are exactly right
for that developer-convenience workflow.

Crucially, this use-case:

- targets **source**, not published docs, so the §3 pipeline concerns do not
  apply;
- produces **nothing committed or deployed**, so drift and supply-chain-in-CI
  concerns do not apply;
- is a **DX tool**, evaluated on local ergonomics, not on standard conformance.

This is captured as **ID-216** ("Evaluate `lx` as an ad-hoc repo-context
bundler for coding agents"). It is an *idea*, not a commitment: a thin candidate
worth a timeboxed trial, kept deliberately distinct from the docs-site
`llms.txt`/`llms-full.txt` lineage.

## 6. Dispositions

| Question | Verdict |
|---|---|
| `lx` for ID-161 (`llms.txt`)? | **No** — that file is hand-curated; wrong tool category. |
| `lx` for a published `llms-full.txt`? | **Not the soundest** — misses generated API pages and URL rewrites, ignores nav order, adds a Go binary to a Python build. Prefer `mkdocs-llmstxt`. |
| `lx` for ad-hoc repo→agent context? | **Yes, plausibly** — its real strength. Tracked as ID-216 for a timeboxed trial. |

Actions taken with this doc:

- **ID-161 adapted:** the follow-on note now points here and recommends the
  MkDocs-native route for `llms-full.txt`, not an external bundler.
- **ID-216 created** under Docs & Discoverability for the ad-hoc bundling
  use-case.

## 7. Trial run (ID-216, 2026-06-24)

Timeboxed local trial of `lx` v1.2.1 (`go install github.com/rasros/lx/cmd/lx`)
against this repo, comparing it to a plain `git archive` baseline. Verdict:
**keep**, as a documented optional DX convenience. No `.lxignore` committed; no
CI / docs-build wiring (per the item's guardrails).

| Bundle | Invocation | Files | ~Tokens |
|---|---|---|---|
| Full source, Claude XML | `lx --xml src/remote_store/` | 69 | ~262k |
| Source **skeleton** (signatures + types) | `lx --xml -u -Y src/remote_store/` | 69 | **~29k** |
| Structure only | `lx -t src/remote_store/` | 69 | — |
| Whole repo | `lx --xml .` | 1,512 | ~3.72M |
| `git archive` baseline | `git archive HEAD src/remote_store` | — | — (opaque tarball) |

Findings:

- **`.gitignore` honoured out of the box** — zero leakage of `tmp/`, `.venv/`,
  or caches; the 69-file source count matched `git ls-files src` exactly. So an
  `.lxignore` is **not** needed to keep junk out.
- **AST skeleton (`-u -Y`) is the standout differentiator** — class/method
  signatures, type fields, and docstrings at **~11%** the token cost of the full
  source (~29k vs ~262k). `git archive` has no equivalent; reproducing it needs
  bespoke tooling.
- **Single LLM-ready artifact vs a tarball.** `git archive` emits an opaque
  `.tar` that must be unpacked, concatenated, formatted, and token-counted before
  an agent can use it — i.e. exactly the bespoke script the item asked us to
  weigh `lx` against. `lx` replaces that whole script with one command and prints
  a token estimate.
- **No `.lxignore` committed.** The differentiated workflows are *subtree* and
  *skeleton* bundles (`lx src/...`), which need no ignore file; a whole-repo
  walk is dominated by `tests/` (~1.66M) and `sdd/` (~1.09M) and is rarely the
  right agent context anyway. A global `.lxignore` would impose policy on an
  optional, non-endorsed-in-CI tool for little gain — prefer explicit subtree
  args (and `-e` where needed). This revises the item's tentative "likely an
  `.lxignore`" hypothesis.

Outcome: a short, optional subsection landed in `CONTRIBUTING.md` §
Development Setup, framed around the skeleton view — two `lx` commands (the
`-u -Y` skeleton and a `git diff | lx -c` changed-files bundle); `lx` is **not**
a project dependency, **not** installed by any script, and **not** in CI.

## 7a. Follow-up (2026-06-30): skeleton fidelity bug

A later public-API handover run surfaced a **correctness bug in the `-u -Y`
skeleton**: it silently drops the `class` header of decorated dataclasses, so
their fields orphan under the previous class and the bundle quietly loses a
class. On `src/remote_store/_models.py` this lost **4 of the 5** public
data-model class headers (`FileInfo`, `WriteResult`, `FolderEntry`,
`FolderInfo`), and dropped some fields (`FolderInfo.file_count`, `total_size`,
its `name` property) entirely. Reproduced on `lx v1.2.1` across
`--md`/`--xml`/`--bare`, so it is the AST extraction, not the formatter. A
deterministic two-class repro narrows the trigger to a comment-led, multi-line
method body in the preceding class, though it did not reduce to a minimal case.

Filed upstream as
[rasros/lx#76](https://github.com/rasros/lx/issues/76); `CONTRIBUTING.md`'s
skeleton subsection now carries a workaround caveat (bundle `_models.py` as full
source until the fix lands). The §6 **keep** verdict stands: only the
type-skeleton path is affected, while full-file and changed-file bundles, the
bulk of the value, are fine.

## 7b. Resolution (2026-07-03): fixed in `lx` v1.2.2

`lx` v1.2.2 (released 2026-07-02) fixes the §7a skeleton bug. Validated
empirically by re-running the exact repro on both versions against
`src/remote_store/`:

- **v1.2.1 (before):** `lx --xml -u -Y src/remote_store/_models.py` drops 4 of 5
  public data-model class headers (`FileInfo`, `WriteResult`, `FolderEntry`,
  `FolderInfo`), orphaning their fields under `ContentDigest` — reproduced the
  documented failure exactly.
- **v1.2.2 (after):** the same command emits all five public classes with headers
  and fields intact. A whole-subtree sweep (`lx --xml -u -Y src/remote_store/`,
  68 files) drops **0 of 90 public classes**, with no orphaned fields.

The v1.2.2 release notes corroborate ("a comment on a function's first body line
no longer leaks into the signature"; "an f-string in a class body no longer drops
the next definition header"; `gotreesitter` bumped to v0.20.8).

Two notes for anyone re-checking:

- **The skeleton is public-API-only by design.** `lx`'s `-u -Y` intentionally
  omits leading-underscore (`_`) classes and functions. Across `src/remote_store/`
  that hides 22 private helper classes (e.g. `_AzureBinaryIO`, `_S3RangeReader`),
  verified deliberate with a two-class probe (a trivial `_Foo` is dropped while a
  public `Bar` is kept). This is expected filtering, not the §7a bug, and matches
  the skeleton's purpose of surfacing the public API a consumer codes against.
- **Upstream [rasros/lx#76](https://github.com/rasros/lx/issues/76) is still open**
  at the time of writing even though the fix shipped in v1.2.2 — the behaviour is
  resolved, the tracker item just has not been closed.

`CONTRIBUTING.md`'s skeleton subsection now records the fix (upgrade to ≥ v1.2.2;
workaround only needed on ≤ v1.2.1).

## 8. References

- [`rasros/lx`](https://github.com/rasros/lx) — the tool under evaluation.
- [llmstxt.org](https://llmstxt.org/) — the `llms.txt` open standard.
- [`mkdocs-llmstxt`](https://github.com/pawamoy/mkdocs-llmstxt) ·
  [PyPI](https://pypi.org/project/mkdocs-llmstxt/) — recommended `llms-full.txt`
  generator.
- [`mkdocs-llms-source`](https://pypi.org/project/mkdocs-llms-source/) ·
  [`mkdocs-llmstxt-md`](https://github.com/noklam/mkdocs-llmstxt-md) —
  alternatives.
- `mkdocs.yml`, `scripts/gen_pages.py`, `scripts/mkdocs_hooks.py` — the local
  docs pipeline this evaluation turns on.
