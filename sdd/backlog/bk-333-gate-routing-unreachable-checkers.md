# BK-333 — Gate routing: checkers unreachable for the diffs that invalidate them
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Two classifiers decide which gates a diff runs, they disagree in both
directions, and between them three checkers are unreachable for exactly the
change that breaks them. `CODE_PAT` does not match `^sdd/`, so CI's `lint` job
(and `preflight` inside it) is skipped; `FORMAL_PAT` is `^sdd/(formal|specs)/`
**minus `sdd/formal/tla/`**, so the second-wiring escape hatch used for
`check_spec_marks`, `check_formal_trace`, `check_capability_parity` and
`check_dafny_twin_parity` does not reach these three; and `docs-gate` invokes
none of them:
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
**The ADR digest half is measured, twice** (was BK-347, absorbed here). A
standalone `gen-adr-digest-check` alias exists in `pyproject.toml` and
**nothing composes it**, so the checker is one alias away from any gate that
wants it. Commit `dc10a23` (PR #956): `gate`, `docs` and `setup` ran, `lint`
skipped. Commit `26cf75b` (PR #958) adds an ADR *and* touches
`.claude/skills/`, `CLAUDE.md` and `sdd/traces/` — not an ADR-only diff by any
reading — and `lint` still skipped, with every test lane skipped alongside it.
So the CI trigger is not how narrow the diff is; it is that **no path in it
matches `CODE_PAT`**, which is true of most process deliveries. The local
classifier misses a different set: an ADR plus a `.claude/hooks/` edit is
outside `CODE_PAT` yet locally runs `all` → `preflight` → the check, while an
ADR plus a `.github/workflows/` edit is inside `CODE_PAT` yet routes to
`lint` + `docs-gate`, which compose it nowhere. **Scope any fix to both
classifiers, not to one name.**
**Consequence:** a hand-edited or stale `DIGEST.md` ships on the author's care
alone, and the `STALE:` failure lands on the *next* PR that happens to touch
code — the wrong PR to pay for it, and one whose author did not cause it.
**Two claims to fix or qualify, not just the routing.** The
[PR validation gates](../CLAUDE-REFERENCE.md#pr-validation-gates) section says
"the two paths stay equivalent on docs coverage despite composing different
targets", which is false for this checker; and the Detailed checklist's **ADR**
row names `preflight` as the gate, which is accurate and is precisely why the
routing is wrong.
Fix shape: add each checker to `docs-gate` beside the two BK-329 wired,
following the precedent `check_ripple_parity` documents, and widen CI's path
filter to treat `sdd/adrs/**` as lint-triggering. Filed rather than fixed in
BK-329 because that PR touched no ADR, no TLA module and not the handbook.

## Correction, 2026-09-28

The TLA bullet no longer holds as written: `ci.yml`'s `verify-tla` job, gated by
`TLA_PAT` (`^sdd/formal/tla/…`, `:84`), runs `check_tla_no_emdash.py` (`:698`),
but `gate`'s `needs` (`:723`) omits it, so a TLA-only change runs the check
without being blocked by it (`rg -n 'check_tla_no_emdash|verify-tla:|TLA_PAT|needs:'
.github/workflows/ci.yml`). Locally, both the TLA and the CI-inventory checks
ride `lint` (`pyproject.toml:314`), which the no-code path runs, so only the
ADR-digest gap exists on both routes; the other two are CI-only.
`gen-adr-digest-check` is still composed nowhere (`rg -n --hidden
'gen-adr-digest-check' --glob '!sdd/**' --glob '!CHANGELOG.md' .` finds only
its definition), and `CLAUDE-REFERENCE.md` still says the two paths "stay
equivalent on docs coverage". Found by the ADR-0040 § 5 conversion.
