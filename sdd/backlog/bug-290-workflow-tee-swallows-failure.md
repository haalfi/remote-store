# BUG-290 — A workflow `run:` step that pipes into `tee` cannot fail, and one of them is a gate
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

A workflow `run:` with no `shell:` key runs under `bash -e {0}` — `-e` without
`-o pipefail` — so a pipeline takes its LAST command's exit status. Any step
spelled `python … | tee …` therefore reports `tee`'s success and swallows the
script's failure.
**`benchmark.yml:105` is the live instance, and it is a gate**:
`python benchmarks/report.py --regression … | tee -a "$GITHUB_STEP_SUMMARY"`.
The comment above it says the check "fails only on a >2x blow-up (catches
gross/algorithmic regressions)"; as written it fails on nothing. A performance
regression, or a crash in `report.py`, leaves the step green.
**Found** by review of the same shape in `drift-guard.yml`'s dry-run step,
which was fixed in place by adding `shell: bash` (BK-369's PR). Derived from
`rg -n '\| tee' .github/workflows/ .github/actions/`: seven hits, of which two
are workflow `run:` steps (drift-guard's, now fixed, and this one) and five are
inside `.github/actions/drift-smoke/action.yml` — four pipelines and one
comment about them — where `shell: bash` is mandatory and already supplies
`-eo pipefail`. Those are not instances.
Fix is one line per step — `shell: bash`, which GitHub runs with `-eo
pipefail` — plus a check that no `run:` step pipes without it, if the class is
worth gating rather than fixing twice.
**Not** the same as a step that pipes deliberately and tolerates failure:
`benchmark.yml:111-113` ends each line with `|| true` and means it.
