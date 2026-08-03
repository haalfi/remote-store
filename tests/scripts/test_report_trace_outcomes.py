"""Unit tests for the trace outcome report.

The report ranks references by ``misleading`` + ``unclear`` count across
``sdd/traces/[!_]*.yml``. Most tests run against hermetic ``tmp_path``
corpora so they stay stable as real traces are added; one test runs the
report against the live repo and asserts structural invariants only —
never counts, because a frozen count of a growing corpus is the exact
defect this report exists to retire.

Two of the report's extraction constraints guard failure modes that are
**latent** in the real corpus: a nearest-preceding-key text scan agrees
with the parsed-YAML reader on every committed tag, and ``_schema.yml``
contributes no tags under a parsed-YAML reader whatever the glob.
Neither hazard can therefore be demonstrated against real data, so each
is tested with a synthetic corpus **plus a positive control** proving
the fixture actually exercises the hazard — per ``sdd/TESTING.md``
§ "A green test can be vacuous", a fixture that cannot fail proves
nothing.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import textwrap
from pathlib import Path

import pytest

# The suite writes trace corpora to disk and resolves references against
# a filesystem root, so it is OS-sensitive: CI's macOS and Windows legs
# select tests with `pytest -m "os_sensitive"`, making the marker the
# inclusion mechanism rather than a label.
pytestmark = pytest.mark.os_sensitive

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_SCRIPT = _SCRIPTS / "report_trace_outcomes.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load("report_trace_outcomes", _SCRIPT)
_gate_mod = _load("check_traces", _SCRIPTS / "check_traces.py")
# Both scripts import the shared driver themselves; take it from
# sys.modules rather than re-executing the file, so the identity
# assertion below tests one driver and not three copies of one.
_corpus_mod = sys.modules["_trace_corpus"]

_REAL_SCHEMA = Path(__file__).resolve().parents[2] / "sdd" / "traces" / "_schema.yml"


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


def _trace(
    trace_id: str,
    steps_yaml: str,
    *,
    title: str = "fixture",
    second_phase_steps: str | None = None,
) -> str:
    """A schema-valid trace wrapping *steps_yaml* in a phase.

    ``second_phase_steps`` adds a second ``phases[]`` entry. Real traces
    carry three to five phases and most negative tags live outside the
    first, so a corpus that is single-phase everywhere cannot tell a
    full ``phases[]`` walk from one that reads only ``phases[0]``.
    """
    body = textwrap.dedent(
        f"""\
            id: {trace_id}
            title: "{title}"
            trigger: "a fixture trigger"
            source_items:
              - {trace_id}
            audience:
              - contributor.tooling
            phases:
              - id: orient
                name: Orient
                steps:
            """
    ) + textwrap.indent(textwrap.dedent(steps_yaml), " " * 6)
    if second_phase_steps is not None:
        body += "  - id: verify\n    name: Verify\n    steps:\n" + textwrap.indent(
            textwrap.dedent(second_phase_steps), " " * 6
        )
    return body


def _step(file: str, outcome: str | None = None, *, section: str = "S", extract: str = "take this") -> str:
    body = f'- file: {file}\n  section: "{section}"\n  read_type: gate\n  extract: "{extract}"\n'
    if outcome is not None:
        body += f"  outcome: {outcome}\n"
    return body


def _repo(tmp_path: Path, *existing: str) -> tuple[Path, Path]:
    """Build a fake repo root with *existing* files; return (root, traces_dir)."""
    root = tmp_path / "repo"
    traces = root / "sdd" / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    for rel in existing:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("placeholder\n", encoding="utf-8")
    return root, traces


def _write(traces: Path, name: str, body: str) -> Path:
    path = traces / name
    path.write_text(body, encoding="utf-8")
    return path


def _collect(root: Path, traces: Path):
    return _mod.collect_outcomes(traces_dir=traces, repo_root=root)


def _row(corpus, reference: str):
    for row in corpus.references:
        if row.reference == reference:
            return row
    return None


# --------------------------------------------------------------------------
# The naive reader BK-330 forbids — kept here as a positive control only.
# --------------------------------------------------------------------------

_FILE_RE = re.compile(r"^\s*-?\s*file:\s*(\S+)")
_OUTCOME_RE = re.compile(r"^\s*outcome:\s*(\w+)")


def _naive_text_scan(path: Path) -> dict[str, int]:
    """Attribute each ``outcome:`` line to the nearest preceding ``file:``.

    This is the extraction method BK-330 rules out. It exists in the test
    module, never in the script, so the hazard fixtures can be shown to
    actually discriminate between the two readers.
    """
    counts: dict[str, int] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _FILE_RE.match(line)
        if m:
            current = m.group(1).strip("\"'")
            continue
        m2 = _OUTCOME_RE.match(line)
        if m2 and m2.group(1) in {"unclear", "misleading"} and current is not None:
            counts[current] = counts.get(current, 0) + 1
    return counts


# --------------------------------------------------------------------------
# Core behaviour
# --------------------------------------------------------------------------


class TestRanking:
    def test_ranks_references_by_negative_count(self, tmp_path):
        # Distinct totals, so this test is about ranking by count alone;
        # ties are the next test's subject.
        root, traces = _repo(tmp_path, "a.md", "b.md", "c.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                _step("a.md", "misleading") + _step("b.md", "unclear") + _step("a.md", "unclear"),
            ),
        )
        _write(
            traces,
            "bk-2-y.yml",
            _trace("BK-2", _step("a.md", "misleading") + _step("b.md", "unclear") + _step("c.md", "misleading")),
        )
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == ["a.md", "b.md", "c.md"]
        assert (corpus.references[0].total, corpus.references[0].misleading, corpus.references[0].unclear) == (3, 2, 1)
        assert corpus.negatives == 6

    def test_ok_and_absent_outcomes_are_not_negative(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md", "b.md", "c.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "ok") + _step("b.md") + _step("c.md", "misleading")),
        )
        corpus = _collect(root, traces)

        assert corpus.negatives == 1
        assert [r.reference for r in corpus.references] == ["c.md"]
        # Coverage is itself a signal (schema: "12% of steps carry an
        # explicit outcome tag"), so tagged/untagged steps still count.
        assert corpus.steps == 3
        assert corpus.steps_tagged == 2

    def test_tie_break_prefers_misleading_then_path(self, tmp_path):
        root, traces = _repo(tmp_path, "zebra.md", "alpha.md", "beta.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                # zebra and alpha tie at 2 total; zebra has more `misleading`.
                _step("zebra.md", "misleading")
                + _step("zebra.md", "misleading")
                + _step("alpha.md", "unclear")
                + _step("alpha.md", "unclear")
                # beta ties with alpha on both counts -> path decides.
                + _step("beta.md", "unclear")
                + _step("beta.md", "unclear"),
            ),
        )
        corpus = _collect(root, traces)
        assert [r.reference for r in corpus.references] == ["zebra.md", "alpha.md", "beta.md"]

    def test_traces_sharing_an_id_are_not_collapsed(self, tmp_path):
        # `id` is pattern-constrained, not unique — sdd/traces/_schema.yml
        # `properties/id` is the authority, and the convention it mandates
        # reuses one backlog ID across a multi-PR item. Accumulating
        # citations by id drops every one but the last, which is the
        # "entries dropped by an approximate extraction" defect this
        # report exists to retire, so it gets its own regression test.
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "id-127-one.yml", _trace("ID-127", _step("a.md", "misleading")))
        _write(traces, "id-127-two.yml", _trace("ID-127", _step("a.md", "unclear")))
        corpus = _collect(root, traces)

        row = _row(corpus, "a.md")
        assert row.total == 2
        assert (row.misleading, row.unclear) == (1, 1)
        assert sorted(c.trace_file for c in row.citations) == ["id-127-one.yml", "id-127-two.yml"]

    def test_corpus_totals_count_each_outcome_into_its_own_bucket(self, tmp_path):
        # Asymmetric on purpose: a (1, 1) fixture is invariant under
        # swapping the two counters, so the test named for the totals
        # could not see them swapped.
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "id-127-one.yml",
            _trace("ID-127", _step("a.md", "misleading") + _step("a.md", "misleading")),
        )
        _write(traces, "id-127-two.yml", _trace("ID-127", _step("a.md", "unclear")))
        # A scanned trace carrying NO negative tag, so
        # traces_with_negatives is falsifiable: without it, counting
        # every scanned trace instead is indistinguishable, and the
        # header line would overstate the corpus's reach.
        _write(traces, "bk-9-clean.yml", _trace("BK-9", _step("a.md", "ok")))
        corpus = _collect(root, traces)

        assert corpus.negatives == 3
        assert (corpus.misleading, corpus.unclear) == (2, 1)
        assert corpus.traces_scanned == 3
        assert corpus.traces_with_negatives == 2

    def test_steps_outside_the_first_phase_are_counted(self, tmp_path):
        # Real traces carry three to five phases and most negative tags
        # live outside the first, so a single-phase corpus cannot tell a
        # full phases[] walk from one that reads only phases[0].
        root, traces = _repo(tmp_path, "a.md", "b.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                _step("a.md", "misleading"),
                second_phase_steps=_step("b.md", "unclear"),
            ),
        )
        corpus = _collect(root, traces)

        assert corpus.steps == 2
        assert corpus.negatives == 2
        assert [r.reference for r in corpus.references] == ["a.md", "b.md"]

    def test_reads_count_every_citation_not_only_tagged_ones(self, tmp_path):
        # The denominator exists to separate exposure from failure rate,
        # so it must count untagged reads. Counting only tagged steps
        # would make rate 100% everywhere and say nothing.
        root, traces = _repo(tmp_path, "a.md", "b.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                _step("a.md", "misleading") + _step("a.md", "ok") + _step("a.md") + _step("a.md", "ok"),
                second_phase_steps=_step("b.md", "misleading") + _step("b.md", "misleading"),
            ),
        )
        corpus = _collect(root, traces)

        widely_read, always_wrong = _row(corpus, "a.md"), _row(corpus, "b.md")
        assert (widely_read.total, widely_read.reads) == (1, 4)
        assert widely_read.rate == 0.25
        assert (always_wrong.total, always_wrong.reads) == (2, 2)
        assert always_wrong.rate == 1.0
        # The hazard the denominator exists to expose: the more-read file
        # outranks the one that misled every reader it ever had.
        assert [r.reference for r in corpus.references] == ["b.md", "a.md"]

    def test_negative_tag_without_a_file_still_counts_in_the_totals(self, tmp_path):
        # Reachable only on a corpus that already fails check_traces, but
        # the docstring promises every tag counts toward the totals
        # regardless of class. Dropping it before the counters would make
        # this the one silent filter in a report about silent filters.
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "misleading") + _step('""', "unclear")),
        )
        corpus = _collect(root, traces)

        assert corpus.negatives == 2
        assert corpus.unattributed == 1
        assert [r.reference for r in corpus.references] == ["a.md"]
        assert "1 tag(s) carry no `file`" in _mod.render_markdown(corpus)

    def test_citing_traces_carry_per_trace_counts(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                _step("a.md", "misleading", section="Rules", extract="first read")
                + _step("a.md", "unclear", section="Exit codes", extract="second read"),
            ),
        )
        _write(traces, "bk-2-y.yml", _trace("BK-2", _step("a.md", "misleading")))
        row = _row(_collect(root, traces), "a.md")

        assert [(c.trace_file, c.total) for c in row.citations] == [("bk-1-x.yml", 2), ("bk-2-y.yml", 1)]
        # Rule 2 (localize) is why Step carries `section` AND `extract`.
        # Distinct values on both, so this pins ordering and pairing too —
        # the builder defaults could not detect steps being swapped.
        assert [(s.section, s.extract) for s in row.citations[0].steps] == [
            ("Rules", "first read"),
            ("Exit codes", "second read"),
        ]


class TestSegregation:
    @pytest.mark.parametrize(
        "ext",
        [
            ".venv/lib/python3.11/site-packages/dagster/_core/storage/x.py",
            "node_modules/left-pad/index.js",
            # The absolute/home clauses are documented classification rules
            # and need their own cases: `_EXTERNAL_SEGMENTS` membership
            # alone does not reach them, and an absolute path left ranked
            # would resolve — `repo_root / "/etc/hosts"` is `/etc/hosts` —
            # and file a system file as a repo documentation failure.
            "/etc/hosts",
            "~/notes.md",
        ],
    )
    def test_external_paths_are_segregated_not_ranked(self, tmp_path, ext):
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading") + _step(ext, "misleading")))
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == ["a.md"]
        assert [r.reference for r in corpus.external] == [ext]
        # Segregated, not dropped: the tag still counts toward the corpus total.
        assert corpus.negatives == 2

    def test_unresolved_paths_are_segregated_not_ranked(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md")
        gone = "sdd/plans/ID-127-graph-backend-implementation.md"
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading") + _step(gone, "unclear")))
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == ["a.md"]
        assert [r.reference for r in corpus.unresolved] == [gone]
        assert corpus.negatives == 2

    def test_not_ranked_sections_are_actually_rendered(self, tmp_path):
        # The segregation tests above stop at the Corpus object. The
        # stated Rule 7 bound names the printing as its own mitigation
        # ("the unresolvable section is where that shows up, which is one
        # reason it is printed"), so a bound whose mitigation can be
        # deleted silently is not a bound.
        root, traces = _repo(tmp_path, "a.md")
        gone = "sdd/plans/ID-127-graph-backend-implementation.md"
        ext = ".venv/lib/python3.11/site-packages/dagster/x.py"
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "misleading") + _step(gone, "unclear") + _step(ext, "misleading")),
        )
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "Not present in the working tree" in rendered
        assert f"`{gone}`" in rendered
        assert "External to the repository" in rendered
        assert f"`{ext}`" in rendered

    @pytest.mark.parametrize("reference", ["sdd/specs/{analog}", "tests/aio/ext/"])
    def test_placeholders_and_directories_skip_resolution(self, tmp_path, reference):
        # The schema licenses both forms; neither names a file on disk, so
        # resolution-checking them would file legal references as missing.
        root, traces = _repo(tmp_path)
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step(reference, "misleading")))
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == [reference]
        assert corpus.unresolved == ()


class TestIdCollisionSurvivesRendering:
    """The id-uniqueness fix has a rendering half; collection is not enough.

    A regression re-keyed on ``trace_id`` would be caught in collection
    and pass silently here, which is the same information loss in a
    different place.
    """

    @staticmethod
    def _same_id_corpus(tmp_path):
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "id-127-one.yml", _trace("ID-127", _step("a.md", "misleading", extract="from one")))
        _write(traces, "id-127-two.yml", _trace("ID-127", _step("a.md", "unclear", extract="from two")))
        return _collect(root, traces)

    def test_detail_lines_distinguish_traces_sharing_an_id(self, tmp_path):
        detail = _mod.render_markdown(self._same_id_corpus(tmp_path)).split("## Detail")[1]

        assert "id-127-one" in detail
        assert "id-127-two" in detail

    def test_rank_citation_orders_same_id_citations_by_filename(self):
        # Hand-built rather than collected, because a collected fixture
        # cannot discriminate this at all: `collect_outcomes` already
        # returns `row.citations` sorted by trace_file, and Python's sort
        # is stable, so ANY tying key reproduces the expected order. The
        # inputs must therefore be equal on `total` AND on `misleading`
        # — otherwise (-total, -misleading) decides first — and supplied
        # in reverse filename order so only the third element can undo it.
        step = _mod.Step(outcome="misleading", section="S", extract="e")
        later = _mod.Citation(
            trace_id="ID-127", trace_file="id-127-two.yml", total=1, misleading=1, unclear=0, steps=(step,)
        )
        earlier = _mod.Citation(
            trace_id="ID-127", trace_file="id-127-one.yml", total=1, misleading=1, unclear=0, steps=(step,)
        )

        ordered = sorted([later, earlier], key=_mod.rank_citation)

        assert [c.trace_file for c in ordered] == ["id-127-one.yml", "id-127-two.yml"]

    def test_summary_counts_ids_not_files(self, tmp_path):
        # The prefix, the listed entries and the "+N more" tail must all
        # count the same unit, or the line does not add up.
        summary = _mod._citation_summary(_row(self._same_id_corpus(tmp_path), "a.md"))

        assert summary == "1 id: ID-127 (2)"

    def test_summary_caps_the_list_and_discloses_the_remainder(self, tmp_path):
        # The cap and the "+N more" tail are a silent truncation the
        # moment either stops working, which is the same defect class as
        # the ranking-table filter fixed elsewhere in this module. One
        # reference cited by six distinct ids reaches both.
        root, traces = _repo(tmp_path, "a.md")
        for n in range(6):
            _write(traces, f"bk-{n}-x.yml", _trace(f"BK-{n}", _step("a.md", "misleading")))
        summary = _mod._citation_summary(_row(_collect(root, traces), "a.md"))

        assert summary == "6 ids: BK-0 (1), BK-1 (1), BK-2 (1), BK-3 (1), +2 more"


# --------------------------------------------------------------------------
# Named failure mode A: the _schema.yml off-by-one from a looser glob
# --------------------------------------------------------------------------

_SCHEMA_SHAPED = _trace("BK-9", _step("schema/example.md", "misleading"), title="schema example")


class TestSchemaGlobCarveOut:
    def test_schema_file_is_not_a_trace(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md", "schema/example.md")
        _write(traces, "_schema.yml", _SCHEMA_SHAPED)
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))
        corpus = _collect(root, traces)

        assert corpus.traces_scanned == 1
        assert [r.reference for r in corpus.references] == ["a.md"]

    def test_nonunderscore_file_is_collected(self, tmp_path):
        # Positive control: the same content under a non-underscore name IS
        # collected. Without this, the test above passes for an
        # implementation that simply never reads schema-shaped files.
        root, traces = _repo(tmp_path, "a.md", "schema/example.md")
        _write(traces, "zz-decoy.yml", _SCHEMA_SHAPED)
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))
        corpus = _collect(root, traces)

        assert corpus.traces_scanned == 2
        assert _row(corpus, "schema/example.md") is not None

    def test_glob_is_the_gate_s_glob_not_a_copy(self):
        # Rule 1: one driver. The report and the gate must resolve their
        # file list through the same helper, so the carve-out cannot drift.
        assert _mod.iter_trace_files is _corpus_mod.iter_trace_files
        assert _gate_mod.iter_trace_files is _corpus_mod.iter_trace_files


# --------------------------------------------------------------------------
# Named failure mode B: attribution imprecision from a text scan
# --------------------------------------------------------------------------

# (a) `outcome` listed before `file` in the same step mapping. JSON Schema
#     constrains presence, not key order, so this is legal.
_HAZARD_KEY_ORDER = _trace(
    "BK-8",
    """\
    - file: docs/previous.md
      section: "A"
      read_type: gate
      extract: "first step"
      outcome: ok
    - section: "B"
      read_type: gate
      extract: "second step"
      outcome: misleading
      file: docs/actual.md
    """,
)

# (b) a block-scalar `extract` whose text contains a `file:` line.
_HAZARD_BLOCK_SCALAR = _trace(
    "BK-7",
    """\
    - file: docs/actual.md
      section: "C"
      read_type: gate
      extract: |
        the section quoted another step verbatim:
        file: docs/decoy.md
        which is prose, not a mapping key
      outcome: misleading
    """,
)

_HAZARDS = {
    "key_order": (_HAZARD_KEY_ORDER, "docs/previous.md"),
    "block_scalar": (_HAZARD_BLOCK_SCALAR, "docs/decoy.md"),
}


class TestAttributionIsStructural:
    @pytest.mark.parametrize("hazard", sorted(_HAZARDS))
    def test_attribution_follows_the_mapping_not_the_text(self, tmp_path, hazard):
        body, wrong_ref = _HAZARDS[hazard]
        root, traces = _repo(tmp_path, "docs/actual.md", "docs/previous.md", "docs/decoy.md")
        _write(traces, "bk-1-x.yml", body)
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == ["docs/actual.md"]
        assert _row(corpus, wrong_ref) is None

    @pytest.mark.parametrize("hazard", sorted(_HAZARDS))
    def test_naive_text_scan_gets_these_wrong(self, tmp_path, hazard):
        # Positive control. The hazards are latent in the real corpus — a
        # naive scan agrees with the parser on every committed trace — so
        # without this assertion the test above could pass against a
        # fixture that discriminates nothing.
        body, wrong_ref = _HAZARDS[hazard]
        _, traces = _repo(tmp_path)
        path = _write(traces, "bk-1-x.yml", body)

        assert _naive_text_scan(path) == {wrong_ref: 1}

    @pytest.mark.parametrize("hazard", sorted(_HAZARDS))
    def test_hazard_fixtures_are_schema_valid(self, tmp_path, hazard):
        # The hazards must be reachable by a *legal* trace, not only by a
        # malformed one, or the constraint they justify is theoretical.
        body, _ = _HAZARDS[hazard]
        _, traces = _repo(tmp_path)
        _write(traces, "bk-1-x.yml", body)

        assert _gate_mod.collect_violations(schema_path=_REAL_SCHEMA, traces_dir=traces) == []


# --------------------------------------------------------------------------
# The report/gate boundary
# --------------------------------------------------------------------------


class TestNeverAGate:
    # check_traces.py documents exit 1 as "one or more violations". This
    # test is the structural tripwire for the absence of that code here:
    # it asserts the return value, so any promotion to a gate fails it by
    # construction and cannot be reworded around.
    @pytest.mark.parametrize(
        "case",
        ["negatives", "empty", "unparseable", "undecodable", "directory"],
    )
    def test_findings_never_change_the_exit_code(self, tmp_path, capsys, case):
        root, traces = _repo(tmp_path, "a.md")
        unreadable = {
            # Neither of these is a yaml.YAMLError: both come out of
            # read_text before the parser is reached, and both used to
            # escape as an exit-1 traceback.
            "undecodable": lambda: (traces / "bad.yml").write_bytes(b'id: BK-1\ntitle: "\xff\xfe"\n'),
            "directory": lambda: (traces / "adir.yml").mkdir(),
        }
        if case == "negatives":
            _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))
        elif case == "unparseable":
            _write(traces, "broken.yml", "id: BK-1\ntitle: [unterminated\n")
        elif case in unreadable:
            unreadable[case]()

        rc = _mod.main(["--traces-dir", str(traces), "--repo-root", str(root)])

        assert rc == 0
        if case in {"unparseable", *unreadable}:
            # Skipped, and said so: silence would make a corrupt corpus
            # indistinguishable from a clean one.
            assert ".yml" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--top", "--min-count"])
    def test_zero_is_a_legal_filter_not_a_usage_error(self, tmp_path, flag):
        # The reject side is tested below; this is the accept side of the
        # same boundary. Without it, tightening `< 0` to `<= 0` starts
        # rejecting the invocation the docstring documents as legal, and
        # nothing notices — the rendering test for `top=0` calls
        # render_markdown directly and never reaches argparse.
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))

        assert _mod.main(["--traces-dir", str(traces), "--repo-root", str(root), flag, "0"]) == 0

    @pytest.mark.parametrize(
        "argv",
        [
            ["--traces-dir", "definitely-absent"],
            ["--repo-root", "definitely-absent"],
            ["--top", "-1"],
            ["--min-count", "-1"],
        ],
    )
    def test_wrong_invocation_is_a_usage_error(self, argv):
        # Exit 2 is the module's only failure path. `--top -1` matters
        # most: shown[:-1] silently drops the lowest-ranked row and
        # renders as a complete table.
        with pytest.raises(SystemExit) as exc:
            _mod.main(argv)

        assert exc.value.code == 2


class TestRendering:
    def test_top_does_not_change_the_reported_total(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md", "b.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "misleading") + _step("a.md", "misleading") + _step("b.md", "unclear")),
        )
        corpus = _collect(root, traces)

        full = _mod.render_markdown(corpus)
        topped = _mod.render_markdown(corpus, top=1)

        assert "`b.md`" in full
        assert "`b.md`" not in topped.split("## Detail")[0]
        # Truncating must move neither the denominator nor the reader's
        # knowledge that it happened. Both halves, or the report can stop
        # disclosing that it truncated and nothing notices.
        assert "3 (`misleading` 2, `unclear` 1)" in full
        assert "3 (`misleading` 2, `unclear` 1)" in topped
        assert "1 further ranked reference(s) not shown" in topped
        assert "not shown" not in full

    def test_min_count_drops_the_tail(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md", "b.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading") + _step("a.md", "unclear")))
        _write(traces, "bk-2-y.yml", _trace("BK-2", _step("b.md", "unclear")))
        corpus = _collect(root, traces)

        rendered = _mod.render_markdown(corpus, min_count=2).split("## Detail")[0]
        assert "`a.md`" in rendered
        assert "`b.md`" not in rendered
        assert "1 further ranked reference(s) not shown" in rendered

    @pytest.mark.parametrize("filters", [{"min_count": 9999}, {"top": 0}])
    def test_hiding_everything_does_not_claim_there_is_nothing(self, tmp_path, filters):
        # The disclosure used to live inside the `if shown:` branch, so it
        # vanished at exactly the moment 100% of the ranking was hidden —
        # and the empty-corpus sentence took its place, stating something
        # false. This is the silent-filter class the report exists to name.
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))
        corpus = _collect(root, traces)

        rendered = _mod.render_markdown(corpus, **filters)

        assert "No ranked references carry a negative outcome tag" not in rendered
        assert "Every ranked reference was hidden by the active filters." in rendered
        assert "1 further ranked reference(s) not shown" in rendered

    def test_empty_ranking_says_so(self, tmp_path):
        # The counterpart: with nothing to hide, the sentence is true and
        # must still be reachable.
        root, traces = _repo(tmp_path)
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "ok")))
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "No ranked references carry a negative outcome tag." in rendered
        assert "not shown" not in rendered

    def test_reads_and_rate_reach_the_rendered_table(self, tmp_path):
        # The columns are the point of the denominator, and asserting them
        # only on the ReferenceRow leaves them deletable from the table in
        # silence — the same gap `test_not_ranked_sections_are_actually_
        # rendered` exists to close for the segregated sections.
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "misleading") + _step("a.md", "ok") + _step("a.md", "ok")),
        )
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "| Total | misleading | unclear | reads | rate | Reference | Citing traces |" in rendered
        assert "| 1 | 1 | 0 | 3 | 33.3% | `a.md` |" in rendered

    def test_rate_below_one_percent_does_not_render_as_zero(self, tmp_path):
        # `:.0%` floored a real finding to "0%", which reads as "never
        # misled anyone" on a row that exists because it did.
        root, traces = _repo(tmp_path, "a.md")
        steps = _step("a.md", "misleading") + _step("a.md", "ok") * 200
        _write(traces, "bk-1-x.yml", _trace("BK-1", steps))
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "| 201 | 0.5% |" in rendered

    def test_header_totals_are_not_re_derived_from_the_ranked_rows(self, tmp_path):
        # The docstring's headline invariant is a claim about this header
        # line: every tag counts toward the totals regardless of class.
        # Only a corpus carrying all four classes at once can separate
        # "counted during the scan" from "summed back from the table".
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                _step("a.md", "misleading")
                + _step("sdd/plans/gone.md", "misleading")
                + _step(".venv/lib/x.py", "unclear")
                + _step('""', "unclear"),
            ),
        )
        corpus = _collect(root, traces)
        rendered = _mod.render_markdown(corpus)

        # One ranked, one unresolved, one external, one unattributed.
        assert (len(corpus.references), len(corpus.unresolved), len(corpus.external)) == (1, 1, 1)
        assert corpus.unattributed == 1
        assert "Negative tags: 4 (`misleading` 2, `unclear` 2) across 1 traces and 3 references." in rendered
        assert "Segregated from the ranking, not discarded" in rendered

    def test_coverage_percentage_is_rendered(self, tmp_path):
        # Coverage is quoted content, not decoration: the schema names it
        # as its own signal about authoring discipline.
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace("BK-1", _step("a.md", "misleading") + _step("a.md") + _step("a.md") + _step("a.md")),
        )
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "4 steps · 1 carry an explicit `outcome` (25.0%)" in rendered

    def test_multiline_extract_cannot_break_out_of_its_list_item(self, tmp_path):
        # Block-scalar `extract` values are legal and common in the real
        # corpus. Interpolated raw, the embedded newlines end the list
        # item and a continuation line starting `###` forges a heading in
        # the section whose `###` headings are the reader's navigation.
        root, traces = _repo(tmp_path, "a.md")
        _write(
            traces,
            "bk-1-x.yml",
            _trace(
                "BK-1",
                """\
                - file: a.md
                  section: "S"
                  read_type: gate
                  extract: |
                    first line
                    ### forged heading
                    | forged | table |
                  outcome: misleading
                """,
            ),
        )
        rendered = _mod.render_markdown(_collect(root, traces))

        detail = rendered.split("## Detail")[1]
        item = next(line for line in detail.splitlines() if line.startswith("- bk-1-x"))
        assert "first line ### forged heading | forged | table |" in item
        # Nothing escaped onto a line of its own. The Detail section's own
        # `### <reference>` headings are its navigation, which is exactly
        # what a forged one would be indistinguishable from.
        assert not any(line.startswith(("### forged", "| forged")) for line in detail.splitlines())


# --------------------------------------------------------------------------
# Live corpus
# --------------------------------------------------------------------------


def test_repo_corpus_report_runs():
    """The report must run green against the committed corpus.

    Structural invariants only. Asserting a count here would freeze a
    number that moves on every merged PR — the defect this report exists
    to retire, and one this very trace reproduces by being added.

    Assertions that restate one derivation by a longer route were
    removed: ``negatives == misleading + unclear`` and
    ``row.total == row.misleading + row.unclear`` hold by construction
    for every input, and ``trace_file`` is taken from the same directory
    it was then checked against. What survives is the one genuine
    two-derivation comparison — row totals accumulated through
    ``per_reference`` against counters incremented during the scan — which
    is what catches a regression to id-keyed accumulation.
    """
    corpus = _mod.collect_outcomes()

    assert corpus.traces_scanned > 0
    assert corpus.references, "the committed corpus carries negative outcome tags"
    assert corpus.parse_errors == ()

    ranked = list(corpus.references)
    assert ranked == sorted(ranked, key=_mod.rank_key)

    total_from_rows = sum(r.total for r in ranked + list(corpus.external) + list(corpus.unresolved))
    assert total_from_rows + corpus.unattributed == corpus.negatives

    for row in ranked:
        assert row.total >= 1
        # Every tagged step is also a read, so the denominator can never
        # be smaller than the numerator and `rate` can never exceed 1.
        # A denominator counted only over tagged steps would peg every
        # rate at 100% and say nothing; one counted over the wrong
        # reference would breach this.
        assert row.reads >= row.total
        assert 0 < row.rate <= 1

    assert _mod.main([]) == 0
