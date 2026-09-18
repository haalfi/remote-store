# ADR-0039: A Python Version Is Supported While Upstream Still Fixes It

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

The published dependency policy's Rule 8 adopted [SPEC 0](https://scientific-python.org/specs/spec-0000/)
and promised support for at least three years after a Python version's release.
Read the way SPEC 0 intends, that licensed dropping the two oldest interpreters
the day the rule shipped. Nothing had decided either way: `requires-python` and
the `Programming Language :: Python` classifiers stood because nobody had
revisited them, and a reader could not tell that from a deliberate choice to be
generous.

**The window was the wrong one, not the decision.** The line that matters to a
user is the one upstream draws. CPython keeps publishing source-only security
releases for a version well past SPEC 0's window, and a version still receiving
them is one people are reasonably still running — so dropping a version upstream
is still fixing strands users for our convenience. SPEC 0's window is a floor
beneath the upstream one, not a schedule to follow to the letter.

**This record decides the rule, never the roster.** No version, date or count
appears below, deliberately: each would be a copy of something derived, and a
copy goes stale while the rule does not
([`sdd/CONTENT-RULES.md`](../CONTENT-RULES.md#six-month-test) Rules 1 and 2).
Where each fact lives:

| Fact | Home |
|---|---|
| Which versions are supported | the `Programming Language :: Python` classifiers in `pyproject.toml`, declared authoritative in the comment above them |
| Each version's release date, and the lifetime the window is built from | `scripts/python_support.py`, each date citing its release-schedule PEP |
| Where every version stands today | the **Support windows** section of the rolling `[drift-guard]` issue, and the chart on the policy page |
| What this decision was measured against | BK-375 in [`sdd/BACKLOG-DONE.md`](../BACKLOG-DONE.md) — the interpreter dates and their PEPs, the dependency survey, the CI cost of the oldest legs with its caveats, and one effect recorded as an unmeasured hypothesis |

## Decision

**A Python version is supported for as long as CPython ships security fixes for
it.** That is the promise Rule 8 now publishes, with SPEC 0's window named as
the ecosystem floor beneath it so a reader can see where ours sits relative to
the schedule their other dependencies follow. Ours is the longer of the two, and
the rule promises a floor rather than a ceiling: we may support a version past
the end of its security support, and will not support one for less.

**A version goes when upstream stops fixing it, and dropping it is its own
change.** Raising `requires-python` moves every spelling of the supported set at
once and is a breaking change, so the roster is the classifiers' to state and
each window's end is arithmetic over a release date. Until a drop lands, the
versions still supported are supported by this decision rather than by inertia,
which is the whole point of writing it down.

**The window is derived, not remembered.** `scripts/python_support.py` holds the
release dates and the arithmetic, the classifiers decide the set,
`scripts/gen_python_support.py` draws the chart the policy page publishes, and
`scripts/drift_report.py` reports each interpreter's standing on the weekly
drift-guard issue. A crossing licenses a drop; it never requires one.

**Revisit at the next minor release**, or when the weekly report shows a
crossing, whichever comes first.

## Consequences

The promise gets longer, which is a widening rather than a break: no user loses
a version they had. It also commits CI to the full interpreter matrix for longer
than SPEC 0 would have. That cost was measured and is asymmetric: in `ci.yml`
the oldest legs are never the critical path, so it is job-minutes and almost no
wall-clock, while in `ci-full.yml` an oldest leg is the longest job, so it sets
that workflow's duration.

[ADR-0032](0032-tiered-ci-gate-with-full-matrix-backstop.md) names the
interpreter set twice and is **not** superseded here, because the set does not
change. The change that drops an interpreter supersedes it.

SPEC 0's window survives in one place and for one reason: the chart marks it, so
a reader can see both windows at once. Nothing decides on it.
