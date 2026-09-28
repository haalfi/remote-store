# ID-250 — The drift smoke never type-checks, so a signature-only narrowing reaches PRs as a red gate
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`.github/workflows/drift-guard.yml` resolves every extra with
`--upgrade --pre`, diffs against the committed baselines and runs the smoke —
which is a pytest target or an `--import-only` module import, per
`scripts/drift_smoke_map.py`. It never runs `mypy`: `rg 'mypy'
.github/workflows/drift-guard.yml` returns nothing. So a dependency change that
is invisible at runtime and visible only to a type checker passes the smoke,
the rolling `[drift-guard]` issue reports the version bump with a green
verdict, and the first person to learn that it breaks us is whoever opens the
next PR.
**Measured, in BUG-258.** Dagster narrowed
`ComputeLogManager.get_log_keys_for_log_key_prefix` from
`Sequence[Sequence[str]]` to `Sequence[list[str]]`. Nothing raised, nothing
failed to import, no test changed behaviour — and every open PR's
`typecheck (3.13)` job went red against code no commit had touched. The version
drift itself was inside drift-guard's remit; the consequence was outside its
instrument.
This is the sibling of BUG-250 one layer up: that item is about the smoke
reaching the *packages* an extra pins, this one about the smoke reaching the
*properties* of them that we actually depend on. Both are the same failure —
a green verdict from an instrument that never looked.
Fix shape is open, and the cheap option may not be the right one. Adding
`mypy` to the smoke leg is small but types the whole tree against one drifted
extra, so a failure will not say which; typing only the extra's own module is
narrower but needs a map from extra to source path, which is
`drift_smoke_map.py`'s existing shape. Either way the verdict must be
*advisory* like the rest of drift-guard — the point is a triaged rolling-issue
row before the PR, not a second gate that blocks one.
**Not** about pinning `dagster`, which BUG-258 considered and rejected:
`infra/drift-locks/dagster.txt` already freezes the extra, and the annotation
fix it shipped is valid against both supertype versions, so no upper bound was
needed.

## Correction, 2026-09-28

Two statements above are imprecise. `--upgrade --pre` is not in
`drift-guard.yml`: it is in `scripts/drift_check.py:278`, which the workflow's
newest lane runs, and a second, floor lane now resolves with
`--resolution lowest-direct` (`rg -n 'upgrade|--pre' scripts/drift_check.py`).
And `scripts/drift_smoke_map.py` maps each extra to a pytest target or an
import module, not to a source path, so per-extra typing needs a map that does
not exist yet. The central claim holds: `rg mypy .github/workflows/drift-guard.yml
.github/actions/drift-smoke/action.yml` finds nothing. Found by the ADR-0040 § 5 conversion.
