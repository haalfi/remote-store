# BK-380 — Python 3.10 stops getting security fixes on 2026-10-04, and the drop is a breaking change of its own
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

[ADR-0039](../adrs/0039-support-tracks-upstream-security-fixes.md) decided that a
Python version is supported for as long as CPython ships security fixes for
it, and Rule 8 of the
[dependency policy](../../docs-src/explanation/dependency-policy.md#rule-8) now
publishes that. 3.10's security support ends **2026-10-04** — five years after
its 2021-10-04 release, per
[PEP 619](https://peps.python.org/pep-0619/)'s own schedule. So the decision
this item carries out was already taken; what is left is the work, and the
work is why it is not folded into the change that took it.
**It moves seven spellings of the supported set at once**, which is the whole
reason for a separate item. The ripple-check's
[Supported interpreter set](../CLAUDE-REFERENCE.md#pre-work-index) row enumerates
them and says which are watched: `requires-python`, the
`Programming Language :: Python` classifiers,
`packaging/conda-forge/variants.yaml`'s `python_min`, `ci.yml`'s `MIN_PYTHON`
and `ALL_PYTHONS`, `ci-full.yml`'s `test-full` matrix, and `README.md`'s
"**Requires Python 3.10+.**" prose. **What watches which, with no total** —
the total has been wrong at every value it has been given: `requires-python`,
`python_min` and `MIN_PYTHON` are held equal to each other by
`check_conda_recipe_pins.py`; `ALL_PYTHONS` and `ci-full.yml`'s `test-full`
matrix against each other by `check_ci_full_matrix.py`, which never reads
`pyproject.toml`; the classifiers against the committed chart by
`gen_python_support.py --check`, so a classifier edit without a regenerate is
caught (measured: dropping one exits 1) though nothing holds them against
another spelling; and `README.md`'s prose by nothing, as with ADR-0032. **No
gate compares the three groups to each other**, which is the gap this item
has to close by hand.
**Two things become dead rather than merely stale.**
`toml = ["tomli>=1.1.0; python_version < '3.11'"]` exists only to keep 3.10
resolving — `tomllib` is stdlib from 3.11 — so a 3.11 floor makes it a
marker-gated extra that can never match. And `drift_check.py`'s
marker-gated-extra exclusion, plus the Tested-versions page's "extras this
page does not cover" section, both lose their one user-facing example; check
whether either still earns its wording. `python_support.py`'s `PYTHON_RELEASES`
row for 3.10 **stays**: a past release date is immutable, and the row is read
by version rather than iterated, so it simply goes unused. Dropping the
classifier is what stops the chart drawing 3.10's bar — `windows()` walks the
classifiers and looks each one up — so deleting the date row buys nothing and
would reintroduce `UnknownInterpreterError` if the classifier ever came back.
**Breaking, with the obligations that follow.**
[CONTRIBUTING § When to bump](../../CONTRIBUTING.md#when-to-bump) prices dropping
an interpreter as breaking: a `**Breaking**` CHANGELOG entry and a
`## vPREV to vX.Y.Z` section in `docs-src/reference/migration.md`, both in this
change. Pre-1.0 that still lands in a minor bump.
**Supersede [ADR-0032](../adrs/0032-tiered-ci-gate-with-full-matrix-backstop.md)
rather than editing it.** It names the interpreter set twice ("all five
supported interpreters (3.10-3.14)" and "Non-primary interpreters
(3.10/3.11/3.12/3.14)"), and an ADR is superseded rather than amended
([`000-process.md` Rule 4](../000-process.md#rules)). ADR-0039 left it standing
deliberately, because the set did not change there.
**What it buys, measured.** `ci-full.yml`'s `test-full (3.10)` was the longest
job in all three runs measured for BK-375, so dropping it takes a mean 0.92 min
off a 8.74 min run and 8.27 job-min with it; in `ci.yml` the leg is never on
the critical path, so the saving there is 5.94 job-min and about no wall-clock.
BK-375's entry in [`BACKLOG-DONE.md`](../BACKLOG-DONE.md) carries the
derivations and the caveats; ADR-0039 states the rule and carries no figure.
**Do not wait for the weekly report to ask.** The drift-guard issue will
surface the crossing on the first Monday after 2026-10-04 and hold itself open
until this lands or a row in `infra/drift-locks/PYTHON-SUPPORT.md` records a
decision to keep 3.10 anyway — which would need a reason, since the new rule's
whole premise is that security support is the line.
