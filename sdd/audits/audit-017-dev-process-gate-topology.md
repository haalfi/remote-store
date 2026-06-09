# Audit 017 — Dev-process gate topology (commit / push / lint / PR / CI in sync)

**Backlog item:** — (ad-hoc audit of the change-validation machinery; follow-ups proposed at the end)
**Date:** 2026-06-09
**Scope:** The whole gate topology that validates a change before it reaches
master: the pre-commit / pre-push hooks (`.pre-commit-config.yaml`), the
`hatch run` script layer (`pyproject.toml` `[tool.hatch.envs.default.scripts]`),
the `scripts/check_*.py` / `gen_*.py` checkers, the CI workflows
(`.github/workflows/*.yml`), the `/pr` · `/fix-pr` · `/orchestrate` · `/release`
skills, and the authority docs (`CONTRIBUTING.md`, `CLAUDE.md`,
`sdd/CLAUDE-REFERENCE.md`). The concern is **over-specialization and drift**:
each surface encodes its own per-change-type gate logic, the logic overlaps and
diverges, and some change types reach CI with no meaningful local gate.
**Method:** Read every real source (no assumptions). Built a change-type ×
enforcement-point matrix from the actual filters and script lists, then assessed
each gate on three axes — value, redundancy, drift/sync. This is a
**report-only** audit: nothing was modified. Findings carry `file:line`
evidence; the recommendations are advisory (the user decides what becomes work).

**Severity key:** 🔴 High · 🟠 Medium · 🟡 Low / Nit.
Each finding tag (H1, M3, …) is referenced by the recommendations table at the end.

---

## Summary

The CI **gate** job is well-built (it closes the silent-skip hole), the
path-filter design is sound, and the `check_*` scripts are scoped with explicit,
auditable in/out-of-scope docstrings. The machinery's defects are structural, not
local:

1. **CI re-encodes the `hatch` script layer by hand.** No CI job calls
   `hatch run lint` / `preflight` / `format-check`; the `lint` job inlines all
   18 commands as `- run:` steps (`ci.yml:100-117`). There are now **three
   divergent definitions of "lint"** — the pre-commit subset, `hatch run lint`,
   and the CI `lint` job — and adding a check to one does not propagate to the
   others. This is drift-by-construction against CLAUDE.md principle 4 (single
   source of truth: link, don't copy).

2. **`sdd/specs`-only changes fall through the gates that exist to validate
   them.** The CI `CODE_PAT` does not match `sdd/`, so a spec-only PR **skips the
   entire `lint` job** — `check_spec_marks` and `check_formal_trace` (the spec ↔
   test / spec ↔ Dafny drift gates) never run, neither in CI nor at commit
   (locally the only gate at commit is the backlog-id check). These are existing
   gates firing in the wrong place, not missing ones.

3. **The skills hand-roll a partial subset of the gate instead of delegating.**
   `/pr` never runs `hatch run lint` or `hatch run all` (CONTRIBUTING's
   prescribed pre-PR command); it reconstructs a coverage + manual-review + trace
   + local-machine subset, and for "docs/config-only" diffs prescribes
   `hatch run test` — the suite least relevant to a doc/spec change — while never
   prescribing `hatch run lint`, the gate most relevant to it.

The rest are redundancy and dead-config findings: a mypy pre-push hook that the
documented install command never wires up, doc-only PRs that skip
`check_no_tracker_refs` / `check_links` in CI, and `drift render-docs --check`
that runs in no PR CI lane.

---

## Topology matrix

What actually runs, per change type, at each enforcement point. Cells:
✅ runs · — does not run · ⚠ runs but see finding.

**Local enforcement** (`pre-commit` = `git commit`; `pre-push` = `git push`;
`lint`/`all` = the `hatch run` targets a contributor types):

| Change type            | pre-commit            | pre-push (mypy) | `hatch run lint` | `hatch run all` |
|------------------------|-----------------------|-----------------|------------------|-----------------|
| `src/**.py`            | ruff, ruff-format, pygrep×2, backlog-id | ⚠ M4 (`^src/`) | ✅ 13 checks | ✅ |
| `tests/**.py`          | ruff, ruff-format, no-rst-roles, backlog-id | — | ✅ | ✅ |
| `scripts/**.py`        | ruff, ruff-format, no-rst-roles, backlog-id | — | ✅ | ✅ |
| `sdd/specs/**.md`      | **backlog-id only**   | —               | ✅ (spec-marks, formal-trace) | ✅ |
| `sdd/traces/*.yml`     | backlog-id only       | —               | — (trace-schema check parked: ID-179) | — |
| `sdd/audits, research` | backlog-id only       | —               | ⚠ docs-framework only | ✅ |
| `docs-src/guides/*.md` | **backlog-id only**   | —               | ✅ (tracker-refs, links, docs-framework) | ✅ |
| `pyproject.toml`       | backlog-id only       | —               | ⚠ (no toml-specific gate) | ✅ |

**CI routing** (`ci.yml` `setup` job path filters; a job runs only if its filter
matches):

| Change type            | `lint` (code) | `typecheck`/`test*` (code) | `docs` (docs) | `verify-formal` (formal) |
|------------------------|---------------|----------------------------|---------------|--------------------------|
| `src` / `tests` / `scripts` / `pyproject` | ✅ | ✅ | ✅ (src/docs paths) | ⚠ specs/formal only |
| `sdd/specs/**`         | **— skipped** | **— skipped**              | ✅ docs-framework + mkdocs | ✅ dafny + capability-parity |
| `sdd/traces`, `sdd/audits`, `sdd/adrs`, `sdd/rfcs` | **— skipped** | **— skipped** | ✅ docs-framework + mkdocs | — |
| `docs-src/guides/*.md` (no FEATURES) | **— skipped** | **— skipped**     | ✅ docs-framework + mkdocs | — |

The two **bold "skipped"** columns are the load-bearing observation: every gate
that lives only in the CI `lint` job — `check_spec_marks`, `check_formal_trace`,
`check_no_tracker_refs`, `check_rst_roles`, `check_infra_settings`,
`check_test_*`, `check_mock_spec`, the four `gen_* --check` artifact-drift
checks — is invisible to any PR whose diff does not match `CODE_PAT`
(`ci.yml:40`).

---

## 🔴 High

### H1 — CI hand-duplicates the `hatch` script layer; three divergent "lint" definitions drift independently

**Files:** `ci.yml:100-117` (inline lint steps) vs
`pyproject.toml:163` (`preflight`), `:164` (`lint`), `:166` (`format-check`);
`.pre-commit-config.yaml:1-35` (the commit subset).

No CI job invokes `hatch run`. The `lint` job re-lists all 18 commands inline:

```yaml
- run: ruff check src/ tests/ examples/ scripts/
- run: ruff format --check src/ tests/ examples/ scripts/
- run: python scripts/check_test_assertions.py tests
  …                                       # 13 more, ending in:
- run: python scripts/gen_backlogid.py --check
```

This is the union of three separate `hatch` targets —
`lint` (13 checks), `format-check` (1), and `preflight`'s four `gen_* --check` —
transcribed by hand. The consequence is three definitions of "lint" that must be
kept in sync manually:

| "lint" | Source | Contents |
|--------|--------|----------|
| commit | `.pre-commit-config.yaml` | `ruff --fix`, `ruff-format`, 2 pygrep, `backlog-id` |
| `hatch run lint` | `pyproject.toml:164` | 13 checks (no `format-check`, no `gen_*`) |
| CI `lint` job | `ci.yml:100-117` | 18 checks (= `hatch lint` + `format-check` + 4 `gen_*`) |

Adding a checker to `hatch run lint` does **not** add it to CI, and vice-versa;
the two lists already diverge (CI carries `ruff format --check` and the four
`gen_* --check`; `hatch run lint` carries none of them). A contributor who types
the obvious `hatch run lint` runs a *different and smaller* gate than CI enforces
(see L3). This is the central principle-4 violation in the topology.

**Note:** `mutation.yml:121` documents a *deliberate* reason one job avoids
`hatch run` (it re-derives the env). That rationale is job-specific; it does not
explain why the `lint` job inlines a 18-line copy of script lists that already
exist as named targets.

### H2 — `sdd/specs`-only changes skip the gates built to validate them

**Files:** `ci.yml:40` (`CODE_PAT`), `:49-51` (`FORMAL_PAT`), `:66-68`
(`lint` gated `if: needs.setup.outputs.code == 'true'`), `:364-374`
(`verify-formal` runs only `dafny verify` + `check_capability_parity`);
`.pre-commit-config.yaml:30-35` (commit = backlog-id only for non-python).

`CODE_PAT` matches `src|tests|examples|scripts`, `pyproject.toml`, FEATURES,
graph data, and workflow paths — **not** `sdd/`. So for a PR that touches only
`sdd/specs/`:

- the CI `lint` job is **skipped** → `check_spec_marks.py` (the BK-251 spec ↔
  mark drift gate) and `check_formal_trace.py` (the ID-206 spec ↔ Dafny ↔ test
  gate) **do not run** — neither in CI nor at commit;
- `verify-formal` does run (FORMAL_PAT matches `^sdd/specs/`), but it executes
  only `dafny verify …` and `check_capability_parity.py` (`ci.yml:364-374`) —
  not the two spec-mark checks;
- locally, the only commit-time gate is `backlogid-check` (`always_run`); the
  natural validator (`check_spec_marks`) fires only if the contributor remembers
  `hatch run lint`/`all`.

**Net:** a new shipped spec ID added without a test (the exact `drift` failure
mode `check_spec_marks` exists to catch — `check_spec_marks.py:27-28`), or a
marker citing a renamed ID (the `stale` mode), ships green on a spec-only PR. The
fix is routing, not a new gate: the gates already exist; the path filter just
does not send `sdd/specs/` changes through them.

*(Trace-YAML validation — the adjacent "`sdd/traces` reaches no gate" question —
is deliberately out of scope here: it is a missing-validator request, already
parked as **ID-179**, not a topology/drift defect.)*

---

## 🟠 Medium

### M1 — `/pr` never runs `hatch run lint` (or `all`); it reconstructs a partial subset

**Files:** `pr/SKILL.md:30-54` (gates 2a/2b/2c/2e/2d); `CONTRIBUTING.md:358`
("Pre-PR validation: run `hatch run all`"); contrast `fix-pr/SKILL.md:107`
("Run `hatch run lint`. Fix failures, re-run until clean.").

`/pr`'s pre-PR gate is a hand-rolled subset: a manual TESTING.md read (2a), a
manual CONTENT-RULES.md read (2b), a coverage run (2c), a local-machine grep
(2e), and a trace existence check (2d). It runs **no** `hatch run lint` and **no**
`hatch run all`. So `/pr` will happily open a PR that fails CI on any of the 13+
`lint` checks it does not run (`check_mock_spec`, `check_test_placement`,
`check_spec_marks`, `check_formal_trace`, `check_infra_settings`,
`check_no_tracker_refs`, the `gen_* --check` drift gates …). `/fix-pr` runs
`hatch run lint` unconditionally; `/pr` does not — an asymmetry with no stated
rationale, and a divergence from CONTRIBUTING's own instruction.

### M2 — Both skills prescribe `hatch run test` for docs/spec diffs — the least-relevant gate — and never `hatch run lint`

**Files:** `pr/SKILL.md:36-38`, `fix-pr/SKILL.md:109-111`.

The coverage gate keys only on `src/`, `tests/`, `examples/`:

> If none match (docs/config-only): run `hatch run test`.

For a zero-code `sdd/`/markdown diff this runs the **pytest suite** (which
exercises nothing the diff changed) and skips `hatch run lint` — the target that
holds `check_docs_framework`, `check_no_tracker_refs`, `check_spec_marks`, and
`check_formal_trace`, i.e. the checks that *do* validate a doc/spec change. The
skills run the most expensive irrelevant gate and skip the relevant one. (The
`scripts/`-only carve-out in the same branch is correct — those have guard tests
under `tests/scripts/` — but it is reasoning about test coverage, not lint.)

### M3 — Docs-only PRs skip `check_no_tracker_refs` and `check_links` in CI

**Files:** `ci.yml:312-326` (`docs` job: `check_docs_framework` + `mkdocs build
--strict` only); `check_no_tracker_refs.py:14-49` (scope = `docs-src/**`, README,
FEATURES, CONTRIBUTING, src docstrings); `pyproject.toml:259` (`all` includes
`check-links`, CI does not).

A PR that touches only `docs-src/guides/*.md` is `code=false, docs=true`, so the
`lint` job is skipped and the `docs` job runs only `check_docs_framework` and
`mkdocs build --strict`. `check_no_tracker_refs` — the gate written specifically
for guide prose (its in-scope set is exactly `docs-src/**`) — lives only in the
code-gated `lint` job, so a tracker-ID leak into a guide-only PR reaches master
unless a human runs `hatch run lint`/`all`. `check_links` (`scripts/docs/
check_links.py`) runs in `hatch run all` but in **no** CI job — `mkdocs build
--strict` covers internal nav links but not the broader link scan.

### M4 — The mypy pre-push hook is never installed by the documented command

**Files:** `.pre-commit-config.yaml:8-15` (mypy `stages: [pre-push]`);
`pyproject.toml:256` (`pre-commit-install = "pre-commit install"`); no
`default_install_hook_types` in the config; no doc mentions
`--hook-type pre-push` (grep over `*.md` returns zero hits).

`pre-commit install` with no `--hook-type` (and no `default_install_hook_types`
in the config) installs **only** the `pre-commit` stage script. The mypy hook,
gated `stages: [pre-push]`, therefore never runs on `git push` for anyone who
followed the documented setup. Type checking still happens via `hatch run
typecheck`/`all` and CI, so this is not a correctness hole — but it is a declared
gate that does not fire, i.e. dead config that reads as protection.

### M5 — Redundant cross-job runs and an artifact-drift check absent from PR CI

**Files:** `ci.yml:107` + `:373` (`check_capability_parity` twice);
`:105` + `:388` (`check_tla_no_emdash` twice); `:109` + `:325`
(`check_docs_framework` twice); `pyproject.toml:163` (`drift_check render-docs
--check` in `preflight`/`all`) with no counterpart in `ci.yml`.

The duplicate `capability_parity` / `tla_no_emdash` / `docs_framework` runs are
defensible (each fires under a *different* path filter, so a formal-only or
docs-only PR still gets the check), but they compound H1: each duplicated command
is one more hand-maintained copy. Separately, `drift_check render-docs --check`
(which verifies `docs-src/reference/tested-versions.md` is in sync) runs in
`hatch run all` and the weekly drift-guard does a different job (resolve/diff) —
so **tested-versions drift is caught by no PR CI lane**, only by a local `all`.

---

## 🟡 Low / Nits

### L1 — `ruff`, `ruff-format`, `gen_backlogid --check` run in three places each

`ruff`/`ruff-format`: pre-commit (`--fix`) + `hatch format-check` + CI `lint`.
`gen_backlogid --check`: pre-commit (`backlogid-check`, `always_run`) +
`hatch lint` + CI `lint`. The layering itself is sound defense-in-depth (fast
local feedback, authoritative CI); the cost is that the CI copy is hand-kept (H1).

### L2 — `/pr` gate steps are numbered out of order

`pr/SKILL.md` runs 2a → 2b → 2c → **2e → 2d** (`:40` then `:44`). Harmless, but
the re-lettered insertion is a visible accretion smell — the gate grew by
patching rather than by re-deriving from one list.

### L3 — `hatch run lint` is a strict subset of CI `lint`; the obvious command under-checks

A contributor types `hatch run lint` and gets 13 checks; CI runs 18
(`+ format-check + 4 gen_*`). The documented complete gate is `hatch run all`
(`CONTRIBUTING.md:358`, `pyproject.toml:259`), but `lint` is the more obvious
thing to type and silently does less than CI. Subset of H1.

---

## Verified strengths (checked, not rubber-stamped)

- **The CI `gate` job closes the silent-skip hole.** `ci.yml:419-424` fails
  explicitly if the `setup` job did not succeed (path filters never ran →
  downstream auto-skips would otherwise pass vacuously), and `:439-443` treats
  only `success`/`skipped` as acceptable. This is the correct shape for a
  fan-out-then-aggregate gate.
- **Path-filter design is sound.** Routing the heavy matrix (`test`,
  `typecheck`, `e2e`, `package`) behind `code==true` and docs behind `docs==true`
  avoids running the full gauntlet on a typo-fix PR, without weakening the gate
  for code changes.
- **`check_*` scripts are scope-auditable.** `check_no_tracker_refs.py:14-49`,
  `check_spec_marks.py:45-55`, and `check_formal_trace.py:29-54` each carry an
  explicit in-scope / out-of-scope / "what this does not prove" docstring. The
  gates are honest about their own limits — `check_spec_marks` states it proves
  *citation, not assertion*. This is the opposite of drift; it is the part of the
  topology most resistant to it.
- **Coverage strict gate is deliberately CI/publish-only, documented.**
  `pyproject.toml:181-195` and `CONTRIBUTING.md:367` both explain that
  `hatch run all` uses the no-Docker `test-cov-s1` variant and the 95% floor
  lives in CI / publish. The split is intentional and recorded, not accidental.
- **`/fix-pr` runs the right gate.** `fix-pr/SKILL.md:107` runs `hatch run lint`
  unconditionally before committing — the behaviour M1 recommends for `/pr`.
- **The ripple-check has a real anti-drift guard.** `CLAUDE-REFERENCE.md:19-22`
  pins "row names, count, and order must match between both presentations" and is
  reviewer-enforced, with a documented escalation path (promote to a check script
  if drift recurs).

---

## Recommendations (advisory, consolidation-first)

The north star is **fewer composable gates and one source of truth**, not more
special-casing. Grouped by theme; the user accepts, splits, or declines. No
backlog items are created here (CLAUDE.md § Audits; ask-before-new-followup).

| Group | Findings | Recommendation | Effort |
|-------|----------|----------------|--------|
| **R1 — CI delegates to `hatch`** | H1, L1, L3 | Replace the inline `lint`-job steps with `hatch run preflight` + `hatch run lint` + `hatch run format-check` (install hatch in the job, as the publish/drift jobs already reference). The `hatch` script lists become the single source; CI inherits any future check automatically. Keep `mutation.yml`'s deliberate no-`hatch` exception. Optionally fold `format-check` + the four `gen_* --check` into `hatch run lint` so the three "lint" definitions collapse toward one. | Low |
| **R2 — Close the `sdd/specs`-only gate gap** | H2 | Pick **one** place: either widen `CODE_PAT` (`ci.yml:40`) to include `^sdd/specs/` so the `lint` job runs on spec-only PRs, or add `check_spec_marks` + `check_formal_trace` to the `verify-formal` job (which already triggers on `sdd/specs/`). Widening the filter is the leaner option — it routes spec changes through the existing single gate rather than adding a second copy. | Low |
| **R3 — Skills delegate, stop re-encoding** | M1, M2, L2 | Define "what validates a change" **once** as `hatch run all` and have `/pr` and `/fix-pr` both run it, dropping the `src/tests/examples`-keyed coverage branch and the manual TESTING/CONTENT sub-gates (those rules are already inside `check_*`/`docs-check`). This is the largest consolidation: it removes the per-type logic the skills currently duplicate from CONTRIBUTING and CI. If a lighter gate is wanted for fast iteration, document one thin target and have both skills call it — but only one. | Medium |
| **R4 — Docs-only PRs get their relevant gate** | M3, M5 (drift-docs) | Subsumed by R3 for the skill path. For CI: add `check_no_tracker_refs`, `check_links`, and `drift_check render-docs --check` to the `docs` job (or widen the lint filter), so a docs-only PR is gated by the checks built for docs. | Low |
| **R5 — Resolve the dead mypy pre-push hook** | M4 | Either set `default_install_hook_types: [pre-commit, pre-push]` in `.pre-commit-config.yaml` (so `hatch run pre-commit-install` wires both stages), or drop the pre-push mypy hook and rely on `hatch run typecheck`/`all` + CI. Don't leave a declared gate that never fires. | Trivial |

**Priority ordering:** R1 + R3 (the two consolidation wins that remove the
hand-maintained duplication) → R2 + R4 (close the real CI/skill gaps for `sdd/specs`
and docs-only changes) → R5 (dead-config cleanup).
