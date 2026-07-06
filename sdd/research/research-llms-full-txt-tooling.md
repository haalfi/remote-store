# Research: `llms-full.txt` / Markdown-twin tooling for ID-220 (2026 refresh)

**Date:** 2026-07-06
**Context:** ID-220 picks up the "serve Markdown page twins + `llms-full.txt`"
follow-on to ID-161. Its background note (the 2026-05-30
[`research-lx-llms-context-tooling.md`](research-lx-llms-context-tooling.md))
recommended the [`mkdocs-llmstxt`](https://github.com/pawamoy/mkdocs-llmstxt)
plugin. Two things have since changed the ground under that recommendation:

1. **`mkdocs-llmstxt` is now in maintenance mode** — its author has redirected
   his time to Zensical (below), with an uncertain future for the plugin.
2. **`lx` proved correct at v1.2.2** (the §7a skeleton bug is fixed; see the
   prior doc §7b), reopening the question of whether it belongs in this picture.

This doc is a fresh evaluation of the `llms-full.txt` / Markdown-twin tooling
choice. It supersedes the *recommendation* in the prior doc's §4/§6; the prior
doc's **architectural analysis (§3) still holds** and is reused below.

---

## 1. What actually changed (and what did not)

**Changed — the whole docs stack is pivoting.** The decisive new fact is not
about `llms-full.txt` plugins specifically; it is that our entire docs
foundation is entering maintenance mode as its authors converge on a successor:

- **Material for MkDocs is entering maintenance mode** — critical bug and
  security fixes for at least 12 months, **no new features**, as the team
  ships [**Zensical**](https://github.com/zensical/zensical), a new
  MIT-licensed static site generator (Rust core, reads `mkdocs.yml` natively,
  with a migration path). Zensical is pre-1.0 (v0.0.47, 2026-07-05).
- **`mkdocstrings`' author (pawamoy) is joining Zensical** to build its
  API-reference-from-docstrings feature — i.e. the exact capability this repo
  relies on `mkdocstrings` for. That capability does **not** exist in Zensical
  yet.
- **`mkdocs-llmstxt`'s maintenance mode is the same pivot**, in the author's
  own words: *"This project is in maintenance mode. I'm now dedicating my time
  to Zensical. Feel free to reach out for a responsible transfer of
  maintainership."* (v0.5.0, 2025-11-20).

So ID-220 is no longer a self-contained "trial a plugin, keep/drop" decision.
The `llms-full.txt` tooling choice is now **coupled to a Material → Zensical
migration decision** that this repo has not yet taken (or tracked).

**Not changed — the architectural constraint.** The prior doc's §3 argument
turns on our *generated/transformed* pipeline, and every element of it is still
true today:

| Pipeline element | Consequence for a tool that reads **raw `docs-src/`** |
|---|---|
| `gen-files` + `scripts/gen_pages.py` + `mkdocstrings` | The API reference is built at `mkdocs build` time from `src/`. It exists only in rendered output — a raw-source reader **omits the entire API reference**, which is one of the `## Docs` links in `llms.txt`. |
| `scripts/mkdocs_hooks.py` (BK-171) | Rewrites on-disk repo paths to `docs.remotestore.dev` URLs. A raw-source reader emits **on-disk links**, not site URLs. |
| `literate-nav` + `SUMMARY.md` | Reading order is curated. A filesystem/ignore-order walk reads a long bundle **out of sequence**. |

The dividing line between tools is therefore **rendered-output capture vs
raw-source reading**, not correctness or maturity. Only a tool that operates on
the *built* site produces a faithful twin of our pages.

## 2. Does `lx` v1.2.2 change its fitness here? No.

The user's prompt pairs "`mkdocs-llmstxt` is maintenance-only" with "`lx`
already proved correct (1.2.2)", which invites reconsidering `lx` for this job.
It should not be reconsidered, and the reason is worth stating plainly because
it is easy to conflate two different verdicts:

- **What v1.2.2 fixed** was the AST **skeleton** bug (`-u -Y` dropping decorated
  dataclass headers) — relevant to **ID-216**, the *ad-hoc repo-context bundler
  for coding agents*. That verdict is **keep**, and it stands.
- **What disqualifies `lx` for `llms-full.txt`** was never a correctness bug.
  It is that `lx` is a **raw-source bundler**: it reads files off disk, so it
  falls in the right-hand column of the §1 table — no API reference, no URL
  rewrites, no nav order — *plus* the ecosystem friction of adding a pinned Go
  binary to a Python/hatch + pip-MkDocs build (prior doc §3).

Those are architectural, not version-dependent. A correct `lx` is still the
wrong *category* of tool for a published docs bundle. The two use cases stay
separate exactly as the prior doc drew them: `lx` for repo→agent context
(ID-216, kept), a MkDocs-native rendered-output plugin for docs `llms-full.txt`
(ID-220).

## 3. Candidate tools, re-surveyed (2026-07)

| Tool | Approach | Captures our generated pipeline? | Maturity (2026-07) | Health |
|---|---|---|---|---|
| [`mkdocs-llmstxt`](https://github.com/pawamoy/mkdocs-llmstxt) (pawamoy) | Rendered HTML → Markdown (BeautifulSoup + markdownify), inside `mkdocs build` | **Yes** — the only candidate that does | Established; v0.5.0 (2025-11-20); `full_output` + `sections` | **Maintenance mode** (author → Zensical); transfer offered |
| [`mkdocs-llmstxt-md`](https://github.com/noklam/mkdocs-llmstxt-md) (noklam) | Raw Markdown source; serves `.md` twins | **No** — misses generated API pages, hook rewrites, nav order | Early; ~17★; no automated tests yet | Active but young |
| [`mkdocs-llms-source`](https://github.com/TimChild/mkdocs-llms-source) (TimChild) | Raw Markdown source; nav-derived sections | **No** — same raw-source gap | Early; ~2★; v1.1.0 (2026-03-23) | Lightweight single-maintainer |
| [`lx`](https://github.com/rasros/lx) (rasros) | External Go source bundler | **No** — raw source + non-Python-ecosystem | v1.2.2; external CLI | Healthy but wrong category (see §2) |
| **Zensical native** | (future) built-in | Unknown — not shipped | Pre-1.0; API reference + llms.txt **not yet available** | The stated future of the stack |

Two observations:

- **The only tool that is architecturally correct for our pipeline is the one
  in maintenance mode.** The raw-source plugins (`-md`, `-source`, and `lx`) are
  all newer/healthier but share the fatal §1 gap. There is no
  actively-featured, rendered-output MkDocs plugin to switch *to*.
- **Zensical is the eventual home** of both the API reference (pawamoy's remit)
  and, plausibly, `llms.txt` generation — its roadmap already speaks of LLM/agent
  consumption and generated context files — but none of that is shipped, and
  Zensical itself is pre-1.0.

## 4. What "maintenance mode" actually costs us here

Maintenance mode is not abandonment, and the cost depends on the job:

- `mkdocs-llmstxt` does **one narrow, stable thing** (walk the built site,
  HTML→Markdown, concatenate). It is not chasing a moving spec; the
  llmstxt.org format is stable. A frozen-but-working plugin pinned in the docs
  env carries low near-term risk.
- The author **explicitly offers a responsible maintainership transfer**, so
  "unmaintained" is not a foregone conclusion.
- The real cost is **at migration**: whenever we move off Material for MkDocs to
  Zensical, an HTML→Markdown MkDocs plugin is exactly the kind of thing that
  gets ripped out and replaced by a native feature. Adopting it now means
  owning that removal later.

So the question ID-220 really faces is a timing/sequencing one, not a
tool-quality one.

## 5. Options

**A. Adopt `mkdocs-llmstxt` now, pinned, and accept it is interim.**
It is the only correct-category tool; it captures the API reference, applies the
BK-171 URL rewrites (it reads the *built* pages), and respects nav order. Pin an
exact version in the docs env. Repoint the `## Docs` links at the generated
twins and publish `llms-full.txt`. Treat it as tooling with a known sunset at
the Zensical migration. *Cost:* we own a maintenance-mode dependency and its
eventual removal.

**B. Defer ID-220 and fold `llms-full.txt` into a Material → Zensical
migration evaluation.** The migration is coming regardless (Material is
feature-frozen; our `mkdocstrings` dependency is being reimplemented in
Zensical). Deciding the bundler independently risks adopting-then-ripping-out.
*Cost:* `llms.txt`'s `## Docs` links keep pointing at HTML chrome until the
migration lands (which is gated on Zensical reaching API-reference parity —
i.e. not soon).

**C. Raw-source plugin (`-md` / `-source`) or `lx`.** Rejected: all miss the
generated API reference and the BK-171 link rewrites (§1). A twin set that
silently omits the API reference and emits on-disk links is worse than the
status quo, not better.

## 6. Recommended disposition

**The tool decision is now downstream of a migration decision the repo has not
made.** The soundest move is to *surface that decision* rather than quietly
adopt a maintenance-mode dependency under it:

1. **Open a backlog item for the Material for MkDocs → Zensical migration
   evaluation** (framework-level, `ID`-class: unevaluated, no committed
   outcome). It should own the timing question — Zensical is pre-1.0 and lacks
   the API-reference feature we depend on, so "not yet, revisit when pawamoy's
   API reference ships" is a legitimate outcome. ID-220 links to it.
2. **For ID-220 itself, recommend Option A *if* `llms-full.txt` is wanted before
   that migration lands** — `mkdocs-llmstxt` remains the only architecturally
   correct choice, its job is narrow and stable, and it is pinnable. Frame it in
   the item as *interim tooling with a known sunset*, not a permanent adoption,
   and record the migration item as its removal trigger.
3. **Keep `lx` out of ID-220.** Its v1.2.2 fix is an ID-216 fact; it does not
   make a raw-source bundler correct for published docs (§2).

Per the CLAUDE.md audit protocol this is **report-only**: the migration-vs-adopt
call and any backlog edits are the user's to make. My recommendation is A-guarded-by-1,
but B is defensible if the team would rather not carry a sunsetting dependency.

## 7. References

- [`research-lx-llms-context-tooling.md`](research-lx-llms-context-tooling.md) —
  the 2026-05-30 evaluation this refreshes (§3 architecture reused; §4/§6
  recommendation superseded).
- [`mkdocs-llmstxt`](https://github.com/pawamoy/mkdocs-llmstxt) ·
  [PyPI](https://pypi.org/project/mkdocs-llmstxt/) — rendered-output plugin, now
  maintenance mode.
- [`mkdocs-llmstxt-md`](https://github.com/noklam/mkdocs-llmstxt-md) ·
  [`mkdocs-llms-source`](https://github.com/TimChild/mkdocs-llms-source) —
  raw-source alternatives.
- [Zensical](https://github.com/zensical/zensical) ·
  [announcement](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)
  · [roadmap](https://zensical.org/about/roadmap/) — the successor stack; where
  API reference and (plausibly) `llms.txt` are headed.
- [Material for MkDocs native-`llms.txt` discussion #8384](https://github.com/squidfunk/mkdocs-material/discussions/8384)
  — maintainer redirects to the plugin; no native support planned in Material.
- [llmstxt.org](https://llmstxt.org/) — the standard.
- `mkdocs.yml`, `scripts/gen_pages.py`, `scripts/mkdocs_hooks.py` — the local
  pipeline this evaluation turns on.
