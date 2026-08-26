"""Rank references by the negative outcome tags traces attach to them.

Every step in an ``sdd/traces/*.yml`` trace may carry an ``outcome`` of
``ok``, ``unclear`` or ``misleading``. The negative two are recorded by
the agent who did the work, at the moment a read failed to deliver:
``unclear`` for a section that was on-topic but vague, ``misleading`` for
one that proved wrong, stale, or contradictory with another authority —
"the strongest doc-failure signal in the schema", per
``sdd/traces/_schema.yml``.

Those tags were committed and attributed for years and never aggregated.
This script does the aggregation: it ranks the referenced files by
``misleading`` + ``unclear`` count and names the traces that cited each
one, so a recurring complaint about a document becomes visible as a
number instead of staying spread across hundreds of YAML files.

Run with::

    hatch run report-trace-outcomes
    hatch run report-trace-outcomes -- --top 15 --min-count 2
    python scripts/report_trace_outcomes.py

Why this is a report, not a gate
================================
Nothing here fails a build, and the exit code never depends on what is
found. [`sdd/DRIFT-RULES.md` Rule 5](../sdd/DRIFT-RULES.md#mandatory-path)
defaults a new check into ``preflight``/``lint``/CI and requires a
deliberately advisory one to say why. The reasons:

* **There is no correct threshold.** "More than N `misleading` tags on a
  file" is not a defect; it is a prompt to go read the file. A number
  picked to make today's corpus pass would gate tomorrow's on an
  arbitrary line.
* **The input is retrospective self-assessment, not an observed
  invariant.** A pairwise cross-artifact check compares two mechanical
  descriptions and can name the element that differs — which side is
  *wrong* is a separate question its Rule 4 authority rule settles, not
  something the check decides. This one has neither: no second
  description, and nothing to localize beyond where an author *said*
  they were misled. Failing a build on that would manufacture exactly
  the false-positive fatigue that defeats rule checkers elsewhere.

What this report does NOT catch
===============================
State the bound, per [Rule 7](../sdd/DRIFT-RULES.md#miss-rate):

* **It measures recorded confusion, not confusing documentation.** The
  corpus is written by the same agents doing the work, so an unrecorded
  failure is invisible and a mis-attributed tag ranks the wrong artifact.
  A real instance: PR #941 moved two ``misleading`` tags off a backend
  module and a test module onto the backlog entry that had actually
  misled, explicitly because the original tags would have ranked source
  files as documentation failures here.
* **No miss rate is estimated.** Rule 7 asks for one "where feasible".
  Seeding known discrepancies into a self-reported corpus would measure
  the seeding, not the detector, so the honest answer is that the recall
  of this signal is unknown.
* **Granularity stops at the step's ``file`` and ``section`` strings**
  ([Rule 3](../sdd/DRIFT-RULES.md#claim-space)). It does not check that
  the section still exists, that the tag is honest, or that two traces
  citing the same file meant the same part of it.
* **The Detail section renders ``extract``, which carries two registers
  and does not say which one you got.** The schema licenses both a
  prospective phrase ("what to take from this read", written before the
  outcome is known) and a retrospective clause recording how the step
  landed. Rendering either after the tag reads as an explanation of the
  failure, and only the second kind is one — nothing distinguishes them
  mechanically. So the report localizes to a file and a section and
  stops: it can tell you *where* to look and never reliably *what* to
  fix.
* **Corpus validity is assumed, not re-derived**
  ([Rule 8](../sdd/DRIFT-RULES.md#independence)). ``check_traces.py``
  gates schema conformance in ``lint`` and ``docs-gate``; a trace that
  fails to parse here is reported to stderr and skipped rather than
  re-validated.
* **The ranking key is a path string, which is not a stable identifier**
  ([Rule 3](../sdd/DRIFT-RULES.md#claim-space) asks for one). Renaming a
  file silently restarts its count: the old path drops into
  "unresolvable" carrying the accumulated tags, and the new path begins
  at zero. So a long-standing offender can leave the top of the table by
  being moved rather than by being fixed. The unresolvable section is
  where that shows up, which is one reason it is printed rather than
  dropped.
* **Drain files, and nothing surfaces them.** When content migrates
  between two paths that *both* keep resolving, no row moves and no
  section flags it. ``sdd/BACKLOG.md`` drains into
  ``sdd/BACKLOG-DONE.md`` as items complete, so a tag written against a
  live item stays pinned to ``BACKLOG.md`` after the cited section has
  moved out of it. **Two things break: localization and the count.** The
  ranked row sends a reader to a file where the cited section no longer
  lives, and the split count sinks the drained artifact below where its
  combined signal belongs — which matters because the count is the sort
  key. Renames at least land in "unresolvable"; a drain lands nowhere.
  ``rate`` is the one column a drain can leave alone, and the reason is
  specific to a ratio: each half is a subsample of the original, and a
  subsample's *ratio* still estimates the whole when the drained sections
  are no worse than average, whereas a subsample's *sum* cannot estimate
  anything. That proviso is what makes this contingent rather than
  guaranteed — a drain that moved preferentially-tagged sections would
  move each half's rate, while the combined ratio held either way (as it
  does for every column, which is why combination alone distinguishes
  nothing). On this corpus the two halves agree to within a rounding
  step; run the report for the current figures.
* **``rate``'s denominator mixes assessed and never-assessed reads.**
  ``reads`` counts every citing step, but well under half of all steps
  carry an explicit ``outcome`` — and that fraction *varies by
  reference*, so two rows showing the same ``rate`` can rest on very
  different amounts of actual assessment. The header prints one global
  coverage figure, which cannot correct any individual row. Treat
  ``rate`` as "negative tags per citation", which is what it measures,
  and not as a failure rate; it is reported to interrogate a row, never
  to order rows against each other. The schema licenses treating an
  absent ``outcome`` as ``ok`` for ranking, which is what makes this a
  bound to state rather than a bug to fix.

Reading the ranking
===================
**The count measures exposure at least as much as failure rate.**
``CLAUDE.md`` makes "open the backlog item" the first step of nearly
every trace, so ``sdd/BACKLOG.md`` gets a chance to earn a tag in almost
all of them, while a spec read by three traces gets three. A file that
misled every reader it ever had can sort below one that misled a small
fraction of many.

So the table carries ``reads`` (every step citing the reference, tagged
or not) and ``rate`` (tags/reads) beside the absolute count. **They are
meant to be read together**: ``rate`` alone over-promotes a file read
twice and tagged once, which is why it is reported rather than sorted
on. The sort key is the absolute count — see ``rank_key``; whether it
should become ``rate`` is a judgement to make against real output, not a
default to assume.

How references are classified
=============================
A silent filter is the same defect class as a silent truncation, so the
report prints these rules itself (see ``_classification_legend``) — a
reader holding the rendered Markdown in a terminal or a PR comment
cannot be sent to a Python docstring. What follows is the reasoning
behind each class; the report carries the rules.

* **Ranked** — everything that resolves to a path in the working tree,
  plus the two forms the schema licenses that never name a file:
  placeholders like ``sdd/specs/{analog}`` and directory paths like
  ``tests/aio/ext/``. Those skip resolution-checking rather than being
  filed as missing.
* **External** — paths outside the repo (``.venv/``, ``site-packages/``,
  absolute paths). Segregated from the ranking: a third-party file that
  misled an agent is not a repo documentation failure, and leaving it in
  distorts the ranking this report exists to produce.
* **Unresolvable** — repo-shaped paths not present in the working tree
  (a since-deleted or since-renamed file). Also segregated: a trace
  records what was read at the time, so this is history, not an error.
* **Unattributed** — a negative tag on a step with no ``file``. Ranked
  nowhere, since there is nothing to rank it against, but counted into
  the totals and disclosed in the header. Only reachable on a corpus
  that already fails ``check_traces`` (the schema requires ``file`` at
  ``minLength: 1``), which is why it is a count rather than a section.

Every tag counts toward the corpus totals regardless of class — including
the unattributed ones. Only the ranking is filtered.

Extraction method
=================
Both halves are load-bearing:

* the ``sdd/traces/[!_]*.yml`` glob, shared with ``check_traces.py`` via
  ``scripts/_trace_corpus.py`` rather than re-declared here;
* ``phases[].steps[]`` read as **parsed YAML**, taking ``file`` from the
  same mapping as ``outcome``. The schema makes them siblings of one
  object with ``additionalProperties: false``, so attribution is exact by
  construction. A nearest-preceding-key text scan would re-introduce an
  imprecision that has already cost a review round, and it is legal YAML
  that breaks it: a step may list ``outcome`` before ``file``, and a
  block-scalar ``extract`` may contain a line reading ``file: ...``.

Exit codes
==========
* ``0`` — always, including when the report is full of findings, when the
  corpus is empty, and when a trace file cannot be read or parsed (bad
  YAML, undecodable bytes, or a directory caught by the glob — ``Path.glob``
  does not filter to files). There is deliberately no exit code that
  signals findings; adding one would make this a gate.
* ``2`` — argparse usage error: an unusable ``--traces-dir`` or
  ``--repo-root``, or a negative ``--top`` / ``--min-count``. These are
  wrong invocations, not findings.

Drift-gate::

    kind:       rule
    rule: aggregates trace outcome tags per referenced document and ranks the documents that failed
        their readers
    domain:     process
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from _trace_corpus import ROOT, TRACES_DIR, iter_trace_files  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterable

#: The two ``outcome`` values that mark a read as having failed. ``ok``
#: and an absent tag are both non-negative; the schema says aggregators
#: treat absent as ``ok`` for ranking.
NEGATIVE_OUTCOMES = ("misleading", "unclear")

#: Path segments that mark a reference as living outside the repo.
_EXTERNAL_SEGMENTS = (".venv", "site-packages", "node_modules")


@dataclass(frozen=True)
class Step:
    """One negatively-tagged step, kept for localization (Rule 2)."""

    outcome: str
    section: str
    extract: str


@dataclass(frozen=True)
class Citation:
    """One trace's negative tags against one reference."""

    trace_id: str
    trace_file: str
    total: int
    misleading: int
    unclear: int
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class ReferenceRow:
    """One referenced file and every negative tag pointed at it."""

    reference: str
    total: int
    misleading: int
    unclear: int
    citations: tuple[Citation, ...]
    #: How many steps cited this reference at all, tagged or not — the
    #: denominator for ``rate``.
    reads: int = 0

    @property
    def rate(self) -> float:
        """Negative tags per read, as a fraction. ``0.0`` if never read."""
        return self.total / self.reads if self.reads else 0.0


@dataclass(frozen=True)
class Corpus:
    """The whole aggregation: totals, the ranking, and what it excludes."""

    traces_scanned: int
    steps: int
    steps_tagged: int
    negatives: int
    misleading: int
    unclear: int
    traces_with_negatives: int
    references: tuple[ReferenceRow, ...]
    external: tuple[ReferenceRow, ...]
    unresolved: tuple[ReferenceRow, ...]
    parse_errors: tuple[tuple[str, str], ...]
    #: Negative tags carrying no ``file``. Counted into the totals above
    #: and excluded from every row, so the two can be reconciled.
    unattributed: int = 0


def rank_key(row: ReferenceRow) -> tuple[int, int, str]:
    """Sort key: most tags first, then most ``misleading``, then by path.

    Deliberately absolute count, not ``rate``: see the "Reading the
    ranking" section of the module docstring for why the choice is open
    rather than settled. Changing this is one line, and the tie-break is
    documented and tested because ties dominate the tail — most
    references carry one or two tags — and an undocumented one silently
    reorders the report between runs. The research behind this report
    records two entries being dropped "at a tie by an approximate
    extraction", which is the same failure with the ordering left
    implicit.
    """
    return (-row.total, -row.misleading, row.reference)


def _is_external(reference: str) -> bool:
    """True if the reference names a file outside the repository."""
    parts = PurePosixPath(reference).parts
    return reference.startswith(("/", "~")) or any(p in _EXTERNAL_SEGMENTS for p in parts)


def _skips_resolution(reference: str) -> bool:
    """True for the two schema-licensed forms that never name a file.

    ``sdd/specs/{analog}`` is a "pick one similar spec" placeholder and
    ``tests/aio/ext/`` is a "browse this tree" directory. Both are legal
    ``file`` values, so resolution-checking them would file legal
    references as missing.
    """
    return "{" in reference or reference.endswith("/")


def _iter_steps(document: Any) -> Iterable[dict[str, Any]]:
    """Yield every ``phases[].steps[]`` mapping of one parsed trace."""
    if not isinstance(document, dict):
        return
    for phase in document.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        for step in phase.get("steps") or []:
            if isinstance(step, dict):
                yield step


def collect_outcomes(
    *,
    traces_dir: Path = TRACES_DIR,
    repo_root: Path = ROOT,
) -> Corpus:
    """Aggregate negative outcome tags across the trace corpus."""
    # Keyed by trace *filename*, never by the trace's `id`:
    # sdd/traces/_schema.yml `properties/id` is the authority and states
    # `id` is not unique, because the convention it mandates reuses the
    # backlog ID across a multi-PR item. An id-keyed accumulator drops
    # all but the last of those. The filename is the only per-trace key
    # the filesystem guarantees.
    per_reference: dict[str, dict[str, Citation]] = {}
    parse_errors: list[tuple[str, str]] = []
    traces_scanned = 0
    steps = 0
    steps_tagged = 0
    traces_with_negatives = 0
    # Counted while scanning rather than summed back from the rows, so
    # the row totals have something independent to be checked against.
    negatives = 0
    misleading = 0
    unclear = 0
    unattributed = 0
    # reference -> how many steps cited it at all, tagged or not.
    reads: dict[str, int] = {}

    for path in iter_trace_files(traces_dir):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            # OSError and UnicodeDecodeError come from read_text, not from
            # the parser, and neither is a yaml.YAMLError: the glob admits
            # directories (Path.glob does not filter to files) and a
            # truncated or mis-encoded file after a bad rebase decodes to
            # neither. Letting either escape would exit 1 with a traceback
            # — the code the exit-code contract above says does not exist.
            parse_errors.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue

        traces_scanned += 1
        trace_id = str(document.get("id", path.stem)) if isinstance(document, dict) else path.stem
        # Accumulate per (reference, trace) so one trace citing a file
        # three times is one citation with a count, not three citations.
        found: dict[str, list[Step]] = {}

        for step in _iter_steps(document):
            steps += 1
            outcome = step.get("outcome")
            if outcome is not None:
                steps_tagged += 1
            reference = str(step.get("file", "")).strip()
            # Counted for every step, not only tagged ones: this is the
            # ranking's denominator. Without it the table measures how
            # often a file is *read* as much as how often it misleads —
            # `CLAUDE.md` makes opening the backlog item step one of
            # nearly every trace, which is most of why it ranks first.
            if reference:
                reads[reference] = reads.get(reference, 0) + 1
            if outcome not in NEGATIVE_OUTCOMES:
                continue
            # A negative tag with no `file` is counted into the corpus
            # totals before being dropped from the ranking, so the
            # docstring's "every tag counts toward the corpus totals
            # regardless of class" stays true. Only the ranking is
            # filtered; a silently uncounted tag would be the defect
            # class this report exists to name.
            negatives += 1
            if outcome == "misleading":
                misleading += 1
            else:
                unclear += 1
            if not reference:
                unattributed += 1
                continue
            found.setdefault(reference, []).append(
                Step(
                    outcome=str(outcome),
                    section=str(step.get("section", "")),
                    extract=str(step.get("extract", "")),
                )
            )

        if found:
            traces_with_negatives += 1
        for reference, hits in found.items():
            per_reference.setdefault(reference, {})[path.name] = Citation(
                trace_id=trace_id,
                trace_file=path.name,
                total=len(hits),
                misleading=sum(1 for h in hits if h.outcome == "misleading"),
                unclear=sum(1 for h in hits if h.outcome == "unclear"),
                steps=tuple(hits),
            )

    ranked: list[ReferenceRow] = []
    external: list[ReferenceRow] = []
    unresolved: list[ReferenceRow] = []

    for reference, citations in per_reference.items():
        ordered = tuple(sorted(citations.values(), key=lambda c: c.trace_file))
        row = ReferenceRow(
            reference=reference,
            total=sum(c.total for c in ordered),
            misleading=sum(c.misleading for c in ordered),
            unclear=sum(c.unclear for c in ordered),
            citations=ordered,
            reads=reads.get(reference, 0),
        )
        if _is_external(reference):
            external.append(row)
        elif _skips_resolution(reference) or (repo_root / reference).exists():
            ranked.append(row)
        else:
            unresolved.append(row)

    ranked.sort(key=rank_key)
    external.sort(key=rank_key)
    unresolved.sort(key=rank_key)

    return Corpus(
        traces_scanned=traces_scanned,
        steps=steps,
        steps_tagged=steps_tagged,
        negatives=negatives,
        misleading=misleading,
        unclear=unclear,
        traces_with_negatives=traces_with_negatives,
        references=tuple(ranked),
        external=tuple(external),
        unresolved=tuple(unresolved),
        parse_errors=tuple(parse_errors),
        unattributed=unattributed,
    )


def _classification_legend() -> list[str]:
    """The filtering rules, rendered for the reader of the report.

    These live in the output rather than only in this module's docstring
    because the audience for them is whoever is looking at the table —
    in a terminal, a pasted file or a PR comment — and "open the Python
    module" is not a pointer they can follow from there. The docstring
    keeps the *reasoning* behind each class; this is the rule itself.
    """
    return [
        "**How the ranking is filtered.** Ranked: references resolving in the working "
        "tree, plus the schema's `{placeholder}` and directory forms, which skip "
        "resolution. Not ranked, but still counted in the totals above: paths outside "
        "the repo, paths no longer present, and tags carrying no `file`. Only the "
        "ranking is filtered — no tag is dropped.",
    ]


def _one_line(text: str) -> str:
    """Flatten *text* so it cannot break out of a Markdown list item.

    ``extract`` and ``section`` are free-form author strings, and the
    schema licenses YAML block scalars: at the time of writing the corpus
    holds hundreds of multi-line ``extract`` values. Interpolated raw,
    each embedded newline ends the list item — fragmenting the Detail
    section into loose lists — and a continuation line beginning ``#``,
    ``|``, ``>`` or four spaces renders as a heading, table, blockquote or
    code block *inside* the report. A forged ``###`` is the worst case,
    since ``###`` headings are the Detail section's navigation.

    Collapsing whitespace is enough: the danger is structural Markdown at
    the start of a *line*, so with no line breaks there is nothing for it
    to start.
    """
    return " ".join(text.split())


def _citation_summary(row: ReferenceRow) -> str:
    """``N ids: BK-1 (2), BK-2 (1)`` — bounded so the table stays legible.

    Counts are grouped by trace ``id`` for display, because ids are not
    unique (``sdd/traces/_schema.yml`` ``properties/id``) and an
    ungrouped list would print the same id repeatedly and read as a bug.
    The prefix therefore counts **ids, not files**, and
    says so: counting files here while the list and its ``+N more`` tail
    count ids would not add up on any row where two citing traces share
    an id. The Detail section below names the individual trace files.
    """
    grouped: dict[str, int] = {}
    for citation in row.citations:
        grouped[citation.trace_id] = grouped.get(citation.trace_id, 0) + citation.total
    ordered = sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = [f"{trace_id} ({total})" for trace_id, total in ordered[:4]]
    more = len(ordered) - len(shown)
    tail = f", +{more} more" if more > 0 else ""
    plural = "s" if len(ordered) != 1 else ""
    return f"{len(ordered)} id{plural}: " + ", ".join(shown) + tail


def rank_citation(citation: Citation) -> tuple[int, int, str]:
    """Order citations the way references are ordered, for consistency.

    Tie-breaks on the trace *filename*, which is unique; ``trace_id`` is
    not, so it cannot give a stable order.
    """
    return (-citation.total, -citation.misleading, citation.trace_file)


def render_markdown(
    corpus: Corpus,
    *,
    top: int | None = None,
    min_count: int | None = None,
) -> str:
    """Render the report. Filters affect the table only, never the totals."""
    lines: list[str] = ["# Trace outcome report", ""]

    coverage = (corpus.steps_tagged / corpus.steps * 100) if corpus.steps else 0.0
    lines.append(
        f"Corpus: {corpus.traces_scanned} traces · {corpus.steps} steps · "
        f"{corpus.steps_tagged} carry an explicit `outcome` ({coverage:.1f}%)."
    )
    lines.append(
        f"Negative tags: {corpus.negatives} (`misleading` {corpus.misleading}, "
        f"`unclear` {corpus.unclear}) across {corpus.traces_with_negatives} traces "
        f"and {len(corpus.references) + len(corpus.external) + len(corpus.unresolved)} references."
    )
    if corpus.unattributed:
        lines.append(f"{corpus.unattributed} tag(s) carry no `file` and are counted above but ranked nowhere.")
    lines.append("")
    lines.append("Ranked by `misleading` + `unclear`. Ties break by `misleading`, then by path.")
    lines.append(
        "`reads` counts every step citing the reference, tagged or not; `rate` is "
        "tags/reads. **Read them together, and read neither alone** — a high count "
        "on a file every trace opens is exposure rather than failure rate, and a "
        "high `rate` over a handful of reads is noise. Most of the corpus is "
        "untagged, and the tagged fraction varies per reference, so `rate` ranks "
        "poorly across rows: use it to interrogate a row, not to order them."
    )
    lines.append("**A report, not a gate** — the exit code never depends on what is below.")
    lines.extend(_classification_legend())
    lines.append("See the module docstring for why this is not a gate and what it does not catch.")
    lines.append("")

    shown = [r for r in corpus.references if min_count is None or r.total >= min_count]
    if top is not None:
        shown = shown[:top]

    if shown:
        lines.append("| Total | misleading | unclear | reads | rate | Reference | Citing traces |")
        lines.append("|---:|---:|---:|---:|---:|---|---|")
        for row in shown:
            lines.append(
                # One decimal: `:.0%` floors anything under 0.5% to "0%",
                # which reads as "never misled anyone" on a row that
                # exists because it did.
                f"| {row.total} | {row.misleading} | {row.unclear} | {row.reads} | "
                f"{row.rate:.1%} | `{row.reference}` | {_citation_summary(row)} |"
            )
    elif corpus.references:
        # Nothing shown but the ranking is non-empty: the filters hid all
        # of it. Saying "no references carry a tag" here would be false,
        # and it is the one case where a reader most needs telling — so
        # the disclosure below sits outside this branch, not inside it.
        lines.append("Every ranked reference was hidden by the active filters.")
    else:
        lines.append("No ranked references carry a negative outcome tag.")

    hidden = len(corpus.references) - len(shown)
    if hidden > 0:
        lines.append("")
        lines.append(f"{hidden} further ranked reference(s) not shown; the totals above are unfiltered.")
    lines.append("")

    if shown:
        lines.append("## Detail")
        lines.append("")
        for row in shown:
            lines.append(f"### `{row.reference}` — {row.total} (misleading {row.misleading}, unclear {row.unclear})")
            lines.append("")
            for citation in sorted(row.citations, key=rank_citation):
                # The file stem, not the id: ids are not unique
                # (sdd/traces/_schema.yml `properties/id`), and the stem
                # carries the id as its prefix anyway.
                origin = Path(citation.trace_file).stem
                for step in citation.steps:
                    section = _one_line(step.section) or "(no section)"
                    lines.append(f'- {origin} · {step.outcome} · "{section}" — {_one_line(step.extract)}')
            lines.append("")

    if corpus.unresolved or corpus.external:
        lines.append("## Not ranked")
        lines.append("")
        lines.append("Segregated from the ranking, not discarded: their tags still count toward the totals above.")
        lines.append("")
    if corpus.unresolved:
        total = sum(r.total for r in corpus.unresolved)
        lines.append(f"### Not present in the working tree — {len(corpus.unresolved)} reference(s), {total} tag(s)")
        lines.append("")
        lines.append(
            "A trace records what was read at the time, so a since-deleted or renamed file is history, not an error."
        )
        lines.append("")
        for row in corpus.unresolved:
            lines.append(f"- `{row.reference}` ({row.total}) — {_citation_summary(row)}")
        lines.append("")
    if corpus.external:
        total = sum(r.total for r in corpus.external)
        lines.append(f"### External to the repository — {len(corpus.external)} reference(s), {total} tag(s)")
        lines.append("")
        lines.append(
            "A third-party file that misled an agent is not a repo documentation failure, so it does not rank."
        )
        lines.append("")
        for row in corpus.external:
            lines.append(f"- `{row.reference}` ({row.total}) — {_citation_summary(row)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=TRACES_DIR,
        help="Directory of trace YAML files (default: sdd/traces).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Root the references are resolved against (default: the repo root).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Show only the N highest-ranked references (default: all of them). Totals stay unfiltered.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=None,
        help="Hide ranked references with fewer than N tags (default: no minimum). Totals stay unfiltered.",
    )
    args = parser.parse_args(argv)

    if not args.traces_dir.is_dir():
        parser.error(f"--traces-dir does not exist: {args.traces_dir}")
    # --repo-root decides the whole ranking: every reference is classified
    # by (repo_root / reference).exists(). Pointed somewhere wrong it does
    # not fail, it silently refiles the corpus as "not present in the
    # working tree" — under a heading that reassures the reader that is
    # expected. A wrong invocation must be loud, not plausible.
    if not args.repo_root.is_dir():
        parser.error(f"--repo-root does not exist: {args.repo_root}")
    # Negative values are silently destructive rather than inert:
    # shown[:-1] drops the lowest-ranked row and looks like a full table.
    if args.top is not None and args.top < 0:
        parser.error(f"--top must be >= 0, got {args.top}")
    if args.min_count is not None and args.min_count < 0:
        parser.error(f"--min-count must be >= 0, got {args.min_count}")

    corpus = collect_outcomes(traces_dir=args.traces_dir, repo_root=args.repo_root)
    for name, message in corpus.parse_errors:
        # Not fatal: check_traces.py owns corpus validity, and a report
        # that fails on input it does not gate would be a gate.
        print(f"report_trace_outcomes: skipped {name}: {message}", file=sys.stderr)

    print(render_markdown(corpus, top=args.top, min_count=args.min_count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
