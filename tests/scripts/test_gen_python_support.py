"""Tests for scripts/gen_python_support.py (BK-373).

The generator's own `--check` is the drift gate, so what these tests add is the
class of defect `--check` structurally cannot see: an artefact that agrees with
itself and will not render. `mkdocs build --strict` cannot see it either,
because no documentation build executes Mermaid.

That is not hypothetical. This file's first draft put a bare `%%` line in the
header, the documentation build went green, `--check` went green, and the
published page showed the Mermaid source as plain text. Measured against
mermaid 11.17.2 in Chromium: `mermaid.parse` answered
``Parse error on line 1: %%gantt ... Expecting 'gantt', got 'NL'``.

**The failure is positional, and the guard is deliberately broader than it.**
A bare marker is fatal *anywhere before* `gantt` — first header line, last, or
mid-header, and even when the line it joins is another comment — because the
joined line still has to be the diagram type. The same marker inserted *after*
`gantt` parses and loses no row. Every comment *carrying* text parsed at every
position tried. `assert_renderable` refuses a bare marker anywhere anyway, and
also refuses `%%` plus a space, which parses: it is a floor under what this
generator can emit, not a model of the parser. The tests below keep both the
fatal case and the deliberate over-reach honest.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import gen_python_support

    return gen_python_support


class TestRenderedArtefact:
    """What the committed artefact says, and what it must never say."""

    def test_committed_artefact_is_current(self, gen):
        """The gate's own question, asserted here so a stale file fails a test too."""
        assert gen.ARTEFACT.read_text(encoding="utf-8") == gen.render()

    def test_check_passes_on_the_committed_artefact(self, gen):
        assert gen.check() == 0

    def test_one_bar_and_one_milestone_per_supported_version(self, gen):
        """Five classifiers, five sections, and two task lines in each."""
        text = gen.render()
        for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
            assert f"    section Python {version}" in text
        assert text.count(":milestone,") == 5
        assert text.count("security fixes (5y)") == 5

    def test_bars_run_from_release_to_the_security_window_end(self, gen):
        """3.10: released 2021-10-04, security support ends five years later."""
        assert "security fixes (5y) :sup310, 2021-10-04, 2026-10-04" in gen.render()

    def test_milestone_marks_the_spec0_floor_not_the_promise(self, gen):
        """The diamond is the 3-year point, which is earlier than the bar's end."""
        assert "SPEC 0 minimum (3y) :milestone, spec310, 2024-10-04, 0d" in gen.render()

    def test_carries_no_date_relative_to_today(self, gen):
        """Byte-stability is the whole reason `--check` can live in `preflight`.

        Any of today's date in the artefact would turn every unrelated pull
        request red the next day. The today line is Mermaid's, drawn
        client-side, so it leaves no trace here.

        **Asserted without reading the clock**, deliberately. An earlier
        spelling added `date.today().isoformat() not in found`, which fails on
        any day that is itself one of the window dates -- measured as 15 such
        days, two of them `2026-10-02` and `2026-10-04`. A test that reddens CI
        on 15 dates is the very hazard this test exists to rule out. The two
        assertions below are the honest form: the set of dates in the artefact
        is exactly the set derivable from the release table, so nothing is left
        over for a clock to have supplied; and `render()` takes no `today`
        argument, which makes the property structural rather than observed.
        """
        import inspect
        import re

        import python_support

        text = gen.render()
        allowed = set()
        for version in python_support.supported_versions():
            allowed.add(python_support.PYTHON_RELEASES[version].isoformat())
            allowed.add(python_support.spec0_end(version).isoformat())
            allowed.add(python_support.support_end(version).isoformat())
        found = set(re.findall(r"\d{4}-\d{2}-\d{2}", text))
        assert found == allowed
        assert inspect.signature(gen.render).parameters == {}

    def test_no_todaymarker_directive(self, gen):
        """`todayMarker on` would be pushed into the line's inline CSS as `style="on"`.

        Measured against mermaid 11.17.2: only the literal string `off`
        suppresses the marker, the default already draws it, and any other value
        is applied as a CSS declaration. Leaving the directive out keeps the
        line on Mermaid's theme colour, which follows the Material palette in
        both themes.
        """
        assert "todayMarker" not in gen.render()


class TestAssertRenderable:
    """The syntax floor, in both directions."""

    def test_the_committed_render_passes(self, gen):
        """Pinned in the passing direction too: a guard hard-coded to raise would
        otherwise look identical to a guard that works.

        Asserted on the two properties the guard is about rather than on the
        absence of an exception, so the test says what renderable *means*.
        """
        text = gen.render()
        gen.assert_renderable(text)
        lines = text.splitlines()
        assert not any(line.strip() == "%%" for line in lines)
        assert next(line for line in lines if not line.startswith("%%")) == "gantt"

    def test_a_bare_comment_marker_is_refused(self, gen):
        """The measured failure: mermaid joins a contentless `%%` to the next line."""
        with pytest.raises(gen.UnrenderableChartError, match="bare `%%`"):
            gen.assert_renderable("%% a header\n%%\ngantt\n    dateFormat YYYY-MM-DD\n")

    def test_a_bare_marker_after_gantt_is_refused_too(self, gen):
        """Stricter than the parser, on purpose, and pinned as such.

        Measured, a bare marker after `gantt` parses: **the committed artefact**
        with one inserted before a `section` renders to a byte-identical SVG,
        all five sections and ten tasks intact. The four-line snippet below is
        not that input and carries one section and no tasks — it is the minimum
        that reaches the guard, and the earlier wording attached the artefact's
        figure to it, which is the attribution error ADR-0037 is about.

        The guard refuses it anyway, because the header is the only place this
        generator emits a comment, so every bare marker it can actually produce
        is the fatal one. Pinned so a later reader does not "fix" the guard to
        match the parser and lose the header case.
        """
        with pytest.raises(gen.UnrenderableChartError, match="line 3"):
            gen.assert_renderable("%% a header\ngantt\n%%\n    section Python 3.10\n")

    def test_a_bare_marker_before_gantt_is_refused_wherever_it_sits(self, gen):
        """The fatal case is not only the *last* header line.

        Measured: a bare marker at any position before `gantt` produces the same
        `Expecting 'gantt', got 'NL'`, including one whose following line is
        another comment rather than `gantt` itself. An earlier wording here said
        "the last header line", from which a reader would conclude an earlier
        marker is harmless; it is not, and narrowing the guard on that reading
        would lose every earlier header position.
        """
        with pytest.raises(gen.UnrenderableChartError, match="line 1"):
            gen.assert_renderable("%%\n%% a header\ngantt\n    dateFormat YYYY-MM-DD\n")

    def test_the_offending_line_is_named(self, gen):
        """DRIFT-RULES Rule 2: say which line, not that a line is wrong."""
        with pytest.raises(gen.UnrenderableChartError, match="line 2"):
            gen.assert_renderable("%% a header\n%%\ngantt\n")

    def test_the_wrong_diagram_type_is_named_with_its_line_too(self, gen):
        """The `Raises:` clause promises a number, and this path gave none.

        `assert_renderable` has two refusals and only the first carried a line
        number; the second built its `body` with a filtering comprehension that
        discarded them, so a contributor got `the first non-comment line must be
        `gantt`, found 'flowchart TD'` with nothing to jump to. Rule 2 asks a
        mechanism to name the element, and the docstring above claimed it did.
        """
        with pytest.raises(gen.UnrenderableChartError, match="line 2"):
            gen.assert_renderable("%% a header\nflowchart TD\n    A --> B\n")

    def test_comments_carrying_text_are_allowed_anywhere(self, gen):
        """Measured: before `gantt`, after it, indented, repeated, all parse.

        The guard must not overreach into rejecting comments generally, which is
        what a naive "no `%%` before the diagram type" rule would have done.
        """
        text = "%% one\n%% two\ngantt\n    %% three\n    dateFormat YYYY-MM-DD\n"
        gen.assert_renderable(text)
        assert text.count("%%") == 3

    def test_a_first_line_that_is_not_gantt_is_refused(self, gen):
        """The diagram type has to be the first thing the parser reaches."""
        with pytest.raises(gen.UnrenderableChartError, match="must be `gantt`"):
            gen.assert_renderable("%% a header\nflowchart TD\n    a --> b\n")

    def test_comment_only_text_is_refused(self, gen):
        """The one shape with no line to name, which must not invent one.

        It used to report `found '<nothing>'`, a placeholder standing where a
        line number and a line belong. Now it says the artefact has no
        non-comment line, which is the actual condition.
        """
        with pytest.raises(gen.UnrenderableChartError, match="no non-comment line"):
            gen.assert_renderable("%% only a comment\n")


class TestCheckReportsWhatChanged:
    """`--check`'s failure output, since a gate nobody can act on is noise."""

    def test_stale_artefact_is_reported_with_the_differing_line(self, gen, tmp_path, monkeypatch, capsys):
        stale = tmp_path / "python-support-window.mmd"
        text = gen.render().replace("2021-10-04, 2026-10-04", "2021-10-04, 2025-10-04")
        stale.write_text(text, encoding="utf-8")
        monkeypatch.setattr(gen, "ARTEFACT", stale)
        assert gen.check() == 1
        err = capsys.readouterr().err
        assert "STALE" in err
        assert "2026-10-04" in err

    def test_missing_artefact_names_the_command_that_writes_it(self, gen, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(gen, "ARTEFACT", tmp_path / "absent.mmd")
        assert gen.check() == 1
        err = capsys.readouterr().err
        assert "MISSING" in err
        assert "gen-python-support" in err

    def test_an_undated_classifier_fails_the_gate_without_a_traceback(self, gen, monkeypatch, capsys):
        """A gate reports; it does not hand a contributor a stack trace."""
        import python_support

        def boom(*_args, **_kwargs):
            raise python_support.UnknownInterpreterError("3.99 has no release date")

        monkeypatch.setattr(gen, "supported_versions", boom)
        assert gen.main(["--check"]) == 1
        assert "UNDATED CLASSIFIER" in capsys.readouterr().err
