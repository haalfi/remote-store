"""Unit tests for scripts/report_trace_outcomes.py (BK-330 outcome report).

The report ranks references by ``misleading`` + ``unclear`` count across
``sdd/traces/[!_]*.yml``. Most tests run against hermetic ``tmp_path``
corpora so they stay stable as real traces are added; one test runs the
report against the live repo and asserts structural invariants only —
never counts, because a frozen count of a growing corpus is the exact
defect this report exists to retire.

Two of BK-330's constraints guard failure modes that are **latent** in
the real corpus: at the time of writing, a nearest-preceding-key text
scan agrees with the parsed-YAML reader on all 193 tags, and
``_schema.yml`` contributes no tags under a parsed-YAML reader whatever
the glob. Neither hazard can therefore be demonstrated against real
data, so each is tested with a synthetic corpus **plus a positive
control** proving the fixture actually exercises the hazard — per
``sdd/TESTING.md`` § "A green test can be vacuous", a fixture that
cannot fail proves nothing.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import textwrap
from pathlib import Path

import pytest

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


def _trace(trace_id: str, steps_yaml: str, *, title: str = "fixture") -> str:
    """A schema-valid trace wrapping *steps_yaml* in a single phase."""
    return textwrap.dedent(
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
        # `id` is pattern-constrained, not unique: 13 committed traces
        # share `ID-127` and two share `BK-181`. Accumulating citations
        # by id drops every one but the last — which is the "entries
        # dropped by an approximate extraction" defect this report
        # exists to retire, so it gets its own regression test.
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "id-127-one.yml", _trace("ID-127", _step("a.md", "misleading")))
        _write(traces, "id-127-two.yml", _trace("ID-127", _step("a.md", "unclear")))
        corpus = _collect(root, traces)

        row = _row(corpus, "a.md")
        assert row.total == 2
        assert (row.misleading, row.unclear) == (1, 1)
        assert sorted(c.trace_file for c in row.citations) == ["id-127-one.yml", "id-127-two.yml"]

    def test_corpus_totals_are_counted_independently_of_the_rows(self, tmp_path):
        # The totals are counted during the scan, not summed back from
        # the rows, so the live-corpus consistency assertion compares two
        # derivations instead of restating one.
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "id-127-one.yml", _trace("ID-127", _step("a.md", "misleading")))
        _write(traces, "id-127-two.yml", _trace("ID-127", _step("a.md", "unclear")))
        corpus = _collect(root, traces)

        assert corpus.negatives == 2
        assert (corpus.misleading, corpus.unclear) == (1, 1)
        assert corpus.traces_with_negatives == 2

    def test_citing_traces_carry_per_trace_counts(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading") + _step("a.md", "unclear")))
        _write(traces, "bk-2-y.yml", _trace("BK-2", _step("a.md", "misleading")))
        row = _row(_collect(root, traces), "a.md")

        assert [(c.trace_file, c.total) for c in row.citations] == [("bk-1-x.yml", 2), ("bk-2-y.yml", 1)]
        # Rule 2 (localize): the citation names the section, not just the file.
        assert [s.section for s in row.citations[0].steps] == ["S", "S"]


class TestSegregation:
    def test_external_paths_are_segregated_not_ranked(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md")
        ext = ".venv/lib/python3.11/site-packages/dagster/_core/storage/x.py"
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

    @pytest.mark.parametrize("reference", ["sdd/specs/{analog}", "tests/aio/ext/"])
    def test_placeholders_and_directories_skip_resolution(self, tmp_path, reference):
        # The schema licenses both forms; neither names a file on disk, so
        # resolution-checking them would file legal references as missing.
        root, traces = _repo(tmp_path)
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step(reference, "misleading")))
        corpus = _collect(root, traces)

        assert [r.reference for r in corpus.references] == [reference]
        assert corpus.unresolved == ()


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
    @pytest.mark.parametrize("case", ["negatives", "empty", "unparseable"])
    def test_findings_never_change_the_exit_code(self, tmp_path, capsys, case):
        root, traces = _repo(tmp_path, "a.md")
        if case == "negatives":
            _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading")))
        elif case == "unparseable":
            _write(traces, "broken.yml", "id: BK-1\ntitle: [unterminated\n")

        rc = _mod.main(["--traces-dir", str(traces), "--repo-root", str(root)])

        assert rc == 0
        if case == "unparseable":
            assert "broken.yml" in capsys.readouterr().err

    def test_no_exit_code_signals_findings(self):
        # check_traces.py documents exit 1 as "one or more violations".
        # The absence of that code here is the structural signal that this
        # is a report; a future promotion to a gate has to delete this test.
        assert "not a gate" in _mod.__doc__.lower()
        assert not hasattr(_mod, "EXIT_FINDINGS")


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
        # A truncated table that silently moved the denominator would be
        # the same defect class as the _schema.yml off-by-one.
        assert "3 (`misleading` 2, `unclear` 1)" in full
        assert "3 (`misleading` 2, `unclear` 1)" in topped

    def test_min_count_drops_the_tail(self, tmp_path):
        root, traces = _repo(tmp_path, "a.md", "b.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("a.md", "misleading") + _step("a.md", "unclear")))
        _write(traces, "bk-2-y.yml", _trace("BK-2", _step("b.md", "unclear")))
        corpus = _collect(root, traces)

        rendered = _mod.render_markdown(corpus, min_count=2).split("## Detail")[0]
        assert "`a.md`" in rendered
        assert "`b.md`" not in rendered

    def test_paths_render_posix_on_every_platform(self, tmp_path):
        root, traces = _repo(tmp_path, "sdd/BACKLOG.md")
        _write(traces, "bk-1-x.yml", _trace("BK-1", _step("sdd/BACKLOG.md", "misleading")))
        rendered = _mod.render_markdown(_collect(root, traces))

        assert "sdd/BACKLOG.md" in rendered
        assert "\\" not in rendered


# --------------------------------------------------------------------------
# Live corpus
# --------------------------------------------------------------------------


def test_repo_corpus_report_runs():
    """The report must run green against the committed corpus.

    Structural invariants only. Asserting a count here would freeze a
    number that moves on every merged PR — the defect BK-330 exists to
    retire, and one this PR reproduces the moment it adds its own trace.
    """
    corpus = _mod.collect_outcomes()
    traces_dir = Path(__file__).resolve().parents[2] / "sdd" / "traces"

    assert corpus.traces_scanned > 0
    assert corpus.references, "the committed corpus carries negative outcome tags"
    assert corpus.negatives == corpus.misleading + corpus.unclear
    assert corpus.parse_errors == ()

    ranked = list(corpus.references)
    assert ranked == sorted(ranked, key=_mod.rank_key)

    total_from_rows = sum(r.total for r in ranked + list(corpus.external) + list(corpus.unresolved))
    assert total_from_rows == corpus.negatives

    for row in ranked:
        assert row.total == row.misleading + row.unclear >= 1
        for citation in row.citations:
            assert (traces_dir / citation.trace_file).exists()

    assert _mod.main([]) == 0
