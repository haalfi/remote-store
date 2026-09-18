<!-- doc: repo-only -->
# Interpreters supported past their window

Python versions the weekly drift-guard run has found past their support window
and that somebody has decided to keep anyway. Without this file the run reports
the same crossing every Monday, the rolling issue carries the same row
indefinitely, and the maintainer stops reading it — the failure
[`sdd/DRIFT-RULES.md` Rule 6](../../sdd/DRIFT-RULES.md#tolerated) requires a
register to prevent, on pain of the check being switched off instead.

`scripts/drift_report.py` reads the table below, keyed on **interpreter**. A row
renders its crossing as _known_, naming its owner, and — while its `Review by`
has not passed — stops it holding the rolling issue open; a crossing with no row,
or with an expired one, renders as new and does hold it open.
Removing a row is therefore how a crossing starts counting again — delete it in
the same change that drops the interpreter.

**The window this file is about is the one
[Rule 8](../../docs-src/explanation/dependency-policy.md#rule-8) publishes:** a
Python version is supported for as long as CPython ships security fixes for it,
which is five years after its `x.y.0` release. `scripts/python_support.py` holds
the dates and the arithmetic.

**Crossing a window licenses a drop; it never requires one.** A row here is not
an admission that something is broken — nothing is broken on the day a window
closes. It records who owns the decision and when it is re-read.

<a id="review-by-is-enforced"></a>
## `Review by` is read by code, here and in the sibling register

Past a row's `Review by` date the row **stops silencing** its crossing, and the
interpreter holds the rolling issue open again. So a row cannot outlive its
decision quietly: the date is the mechanism, not a note to a maintainer.

That is a change from how
[`KNOWN-FINDINGS.md`](KNOWN-FINDINGS.md) behaved before this file existed, and
the two now agree — one expiry predicate in `drift_report.py` serves both, so
there is one rule for the column rather than one per table. **A row with an
unparseable date is a hard failure**, not a row that never expires: a silencer
with no end date is the hazard this section exists to remove.

**Three bounds this file still does not enforce, stated so they are not
assumed.** Nothing checks that a row's `Owner` is still open, so a row outliving
the item it names silences that interpreter until its `Review by` arrives. A
registered crossing renders nowhere on a week whose findings are all registered,
because that week closes the issue — that is the intended trade, and this file
is where those rows live on such a week. And **a row the loader's row shape does
not match is skipped in silence**: a five-cell row, or a version cell without
its backticks, simply has no effect and nothing says why. It fails in the safe
direction — the crossing reappears as news rather than being wrongly silenced —
but the symptom is a row that does nothing, so check a new row against the
format below rather than against what looks reasonable.

**Scope: what the run reports, not what CI does.** No CI job fails because an
interpreter is past its window, registered or not. A row changes only whether
the crossing is presented as news.

## File format

One table, one row per interpreter. `Interpreter` is the minor version in
backticks, exactly as a `Programming Language :: Python` classifier spells it
(`` `3.10` ``, not `` `[3.10]` `` or `` `py310` ``) — the loader keys on that
shape, which is also what keeps it from matching `KNOWN-FINDINGS.md`'s rows.
`Owner` is the ADR or backlog item carrying the decision. `Rationale` says why
the version stays. `Review by` is when the row expires, per the section above.

| Interpreter | Owner | Rationale | Review by |
|---|---|---|---|

**The table is empty, and that is the current state rather than a stub.**
Derivation: `python_support.windows(date.today())` over the committed
classifiers — on 2026-09-17 no supported interpreter was past its window (3.10
was the closest, 17 days out, ending 2026-10-04). 3.10's drop is BK-380; the
weekly run will report the crossing when it happens, which is the mechanism
working rather than a gap in this file.
