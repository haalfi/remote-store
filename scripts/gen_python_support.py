#!/usr/bin/env python3
"""BK-373: draw the Python support window the policy page states in prose.

Rule 8 of the published dependency policy promises support for as long as
CPython ships security fixes. As prose that asks a reader to know five release
dates, add five years to each, and compare against today — three steps before
the rule says anything. SPEC 0's own page does not ask that: it renders a Gantt
chart, one bar per version, and the argument lands without being read.

So this writes ``docs-src/_data/python-support-window.mmd``, a Mermaid ``gantt``
body that ``docs-src/explanation/dependency-policy.md`` pulls into a
``mermaid`` fence with a ``pymdownx.snippets`` include. Sources are
``scripts/python_support.py``: the classifiers decide which versions appear, the
release-date table decides where each bar starts, and the window constants
decide where it ends.

**Two bars per version, and why the second one is a milestone.** The bar is the
promise — release to release plus five years. The milestone is SPEC 0's
three-year floor, drawn because the rule names both and a reader comparing them
is the point: our window is the longer one. Mermaid puts each task on its own
row, so the two share a section label rather than a row.

**Nothing here writes a date relative to today, deliberately.** The artefact is
committed and ``--check`` compares it byte for byte, so anything derived from
``date.today()`` would go red on every unrelated pull request the next day —
the trap a rasterised image walks into, and the reason
``drift_check.py``'s own generator reads its date out of a lock file. The
"where are we now" line is Mermaid's own today marker, drawn **client-side** at
page-view time.

**The today marker is left at its default, and that is load-bearing.** Measured
against mermaid 11.17.2 (the version Material's mermaid component fetches):
``ganttDb.js`` initialises ``todayMarker`` to the empty string, and
``ganttRenderer.js``'s ``drawToday`` returns early only on the literal string
``off``; any other value is applied to the line as an **inline CSS style
string**. So a ``todayMarker on`` directive does not "turn the marker on" — the
marker is already on, and ``on`` would be pushed into ``style="on"``, an invalid
declaration the browser discards. Leaving the directive out keeps the line
styled by Mermaid's own ``todayLineColor``, which follows the Material palette
in both light and dark themes; a hard-coded colour here is the one way to break
one of them.

**Bounds — what this reaches, and the one hole it had to close by hand.**
Nothing here can tell you the chart *renders*: no documentation build executes
Mermaid, because ``pymdownx.superfences`` only emits a
``<pre class="mermaid">`` and Material fetches the renderer in the browser. So
a diagram that will not parse ships with ``mkdocs build --strict`` green and
the page showing raw source, and ``--check`` is no help either — the artefact
still matches itself. That happened on this file's first draft, over a bare
``%%`` line, which is why ``assert_renderable`` exists: it is a syntax floor
over the two mistakes this generator can make, not a renderer. Anything past
those two needs a browser, and the recipe for that is recorded in
``sdd/traces/bk-373-python-support-chart.yml``'s verify phase — build the site,
serve it, load the page in Chromium with the renderer request answered from the
registry tarball, and screenshot, because Material injects the SVG into a
**closed** shadow root and a pixel capture is the only readable check.

The include *resolving* is not this generator's job either; ``mkdocs.yml`` sets
``check_paths: true`` on the snippets extension for that, since the default
silently drops a missing include and leaves an empty fence behind.

Drift-gate::

    kind:       pair
    compares: the Programming Language :: Python classifiers in pyproject.toml and the release dates
        in scripts/python_support.py ↔ the committed Mermaid gantt body in
        docs-src/_data/python-support-window.mmd that the dependency-policy page includes
    domain:     process ↔ explanation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from python_support import (  # noqa: E402  — sibling module, imported the way the other generators do
    PYTHON_RELEASES,
    SECURITY_SUPPORT_YEARS,
    SPEC0_WINDOW_YEARS,
    UnknownInterpreterError,
    spec0_end,
    support_end,
    supported_versions,
)

ARTEFACT = Path(__file__).resolve().parent.parent / "docs-src" / "_data" / "python-support-window.mmd"

# Every header line carries text after its `%%`, and a BARE `%%` line must
# never appear. Measured against mermaid 11.17.2: its comment stripper removes
# the text after a marker but leaves a contentless marker behind, so a `%%`
# alone collapses onto the following line and the parser answers
# `Parse error on line 1: %%gantt ... Expecting 'gantt', got 'NL'`. The page
# then shows the raw source where the chart should be, and nothing catches it:
# `mkdocs build --strict` passes because no documentation build executes
# mermaid, and `--check` passes because the artefact still matches itself.
# `assert_renderable()` below is the guard; tests/scripts/test_gen_python_support.py
# pins it.
_HEADER = """%% Generated by scripts/gen_python_support.py -- do not edit by hand.
%% Sources: the `Programming Language :: Python` classifiers in pyproject.toml
%% (which versions) and PYTHON_RELEASES in scripts/python_support.py (when each
%% was released). Regenerate with `hatch run gen-python-support`.
%% Carries no date relative to today: the vertical "today" line is Mermaid's
%% own, drawn client-side, so this file stays byte-stable between releases.
gantt
    dateFormat YYYY-MM-DD
    axisFormat %Y
    title Python versions supported, and until when
"""


def render() -> str:
    """The Mermaid ``gantt`` body, as the committed artefact spells it."""
    lines = [_HEADER.rstrip("\n")]
    for version in supported_versions():
        tag = version.replace(".", "")
        lines.append("")
        lines.append(f"    section Python {version}")
        lines.append(
            f"    security fixes ({SECURITY_SUPPORT_YEARS}y)"
            f" :sup{tag}, {PYTHON_RELEASES[version]}, {support_end(version)}"
        )
        lines.append(f"    SPEC 0 minimum ({SPEC0_WINDOW_YEARS}y) :milestone, spec{tag}, {spec0_end(version)}, 0d")
    return "\n".join(lines) + "\n"


class UnrenderableChartError(Exception):
    """The rendered text carries something Mermaid's gantt parser rejects."""


def assert_renderable(text: str) -> None:
    """Refuse text Mermaid would reject, for the two reasons it can be rejected.

    Not a Mermaid parser, and not trying to be: a renderer needs a browser (see
    the module docstring's bounds). This is a floor under the two mistakes a
    change to this generator can introduce, both measured against mermaid
    11.17.2 by rendering the artefact in Chromium:

    * **a bare ``%%`` line.** Comment text is stripped and the contentless
      marker is not, so the marker joins the next line. **Measured, the failure
      is positional**: a bare ``%%`` as the last header line makes the parser
      see ``%%gantt`` and answer ``Expecting 'gantt', got 'NL'``, while the same
      line inserted after ``gantt`` — before a ``section``, between tasks, or at
      the end — parses and loses no row. Every comment *carrying text* passed at
      every position tried, including indented, several in a row, and carrying
      backticks, quotes or apostrophes.

      **This guard is deliberately stricter than the parser**, refusing a bare
      marker anywhere rather than only in the header. The generator emits
      comments only in the header, so every bare marker it can produce is the
      fatal one; a body comment is a shape it has no way to emit, and a guard
      that tracked the position would be modelling a parser it is not trying to
      be.
    * **a first non-comment line that is not ``gantt``.** The diagram type has
      to be the first thing the parser reaches.

    Raises:
        UnrenderableChartError: Naming the offending line and its number, per
            DRIFT-RULES Rule 2.
    """
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "%%":
            raise UnrenderableChartError(
                f"line {number} is a bare `%%` comment marker, which joins itself to the next line. "
                f"In the header that is fatal — the parser reads `%%gantt` and answers "
                f"`Expecting 'gantt', got 'NL'`. This check refuses it anywhere, because the header is "
                f"the only place this generator emits comments. Put text after every `%%`."
            )
    body = [line for line in text.splitlines() if not line.lstrip().startswith("%%") and line.strip()]
    if not body or body[0].strip() != "gantt":
        found = body[0].strip() if body else "<nothing>"
        raise UnrenderableChartError(f"the first non-comment line must be `gantt`, found {found!r}")


def generate() -> int:
    rendered = render()
    assert_renderable(rendered)
    ARTEFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTEFACT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {ARTEFACT.relative_to(ARTEFACT.parent.parent.parent)}")
    return 0


def check() -> int:
    expected = render()
    assert_renderable(expected)
    if not ARTEFACT.exists():
        print(f"MISSING: {ARTEFACT} — run: hatch run gen-python-support", file=sys.stderr)
        return 1
    actual = ARTEFACT.read_text(encoding="utf-8")
    if actual == expected:
        return 0
    # Localize, per DRIFT-RULES Rule 2: name the differing lines rather than
    # reporting that the file differs. A classifier added without a release date
    # never reaches here — `supported_versions()` raises first.
    print(f"STALE: {ARTEFACT} disagrees with the classifiers and the release-date table.", file=sys.stderr)
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    # `strict=False`: the two files can differ in length, and that case is
    # reported on its own below rather than raised out of the loop.
    for number, (want, got) in enumerate(zip(expected_lines, actual_lines, strict=False), start=1):
        if want != got:
            print(f"  line {number}: expected {want!r}, found {got!r}", file=sys.stderr)
    if len(expected_lines) != len(actual_lines):
        print(f"  line count: expected {len(expected_lines)}, found {len(actual_lines)}", file=sys.stderr)
    print("Run: hatch run gen-python-support", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only: exit 1 if the committed artefact is missing or stale; 0 otherwise.",
    )
    args = parser.parse_args(argv)
    # A gate reports; it does not hand a contributor a traceback. Both of these
    # are conditions with one obvious remedy each, so say the remedy.
    try:
        return check() if args.check else generate()
    except UnknownInterpreterError as exc:
        print(f"UNDATED CLASSIFIER: {exc}", file=sys.stderr)
        return 1
    except UnrenderableChartError as exc:
        print(f"WOULD NOT RENDER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
