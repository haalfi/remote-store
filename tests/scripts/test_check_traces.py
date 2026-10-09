"""Unit tests for scripts/check_traces.py (ID-179 trace schema gate).

The gate jsonschema-validates every ``sdd/traces/[!_]*.yml`` against
``sdd/traces/_schema.yml``. Most tests run against a hermetic tmp_path
schema + trace fixtures so they stay stable as real traces are added; a
final test asserts the live repo passes its own gate.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_traces.py"
_SCRIPTS_DIR = _SCRIPT.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _trace_corpus  # noqa: E402  — the shared loader every consumer uses


def _load():
    spec = importlib.util.spec_from_file_location("check_traces", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_traces", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()

# A minimal but representative schema: one required string with a pattern,
# additionalProperties:false, and a self-validating examples block. Keeps
# the tests independent of the (evolving) real trace schema.
_SCHEMA = textwrap.dedent(
    """
    $schema: "https://json-schema.org/draft/2020-12/schema"
    type: object
    required: [id, title]
    additionalProperties: false
    properties:
      id:
        type: string
        pattern: "^ID-[0-9]+$"
      title:
        type: string
        minLength: 1
      decisions:
        type: array
        uniqueItems: true
        items:
          type: string
          pattern: '^sdd/decisions/[A-Za-z0-9_-]+\\.jsonl$'
    examples:
      - id: ID-1
        title: "valid example"
    """
)


def _write_schema(tmp_path: Path) -> Path:
    path = tmp_path / "_schema.yml"
    path.write_text(_SCHEMA, encoding="utf-8")
    return path


def _write_trace(traces_dir: Path, name: str, body: str) -> None:
    traces_dir.mkdir(parents=True, exist_ok=True)
    (traces_dir / name).write_text(textwrap.dedent(body), encoding="utf-8")


class TestValidation:
    def test_conforming_trace_passes(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "id-1-x.yml", 'id: "ID-1"\ntitle: "ok"\n')
        assert _mod.collect_violations(schema_path=schema, traces_dir=traces) == []

    def test_pattern_violation_is_reported(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "bad.yml", 'id: "BK-1"\ntitle: "ok"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].source.endswith("bad.yml")
        assert violations[0].path == "id"

    def test_missing_required_field_is_reported(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "bad.yml", 'id: "ID-2"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert "title" in violations[0].message

    def test_additional_property_is_reported(self, tmp_path):
        # The schema's additionalProperties:false is the constraint that
        # caught the real-world top-level `notes` leak.
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "bad.yml", 'id: "ID-3"\ntitle: "ok"\nnotes: "nope"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert "notes" in violations[0].message

    def test_underscore_files_are_skipped(self, tmp_path):
        # The schema file itself lives in the traces dir; the [!_] glob must
        # not validate it as a trace.
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        traces.mkdir()
        schema_copy = traces / "_schema.yml"
        schema_copy.write_text(_SCHEMA, encoding="utf-8")
        _write_trace(traces, "id-1-x.yml", 'id: "ID-1"\ntitle: "ok"\n')
        assert list(_mod.iter_trace_files(traces)) == [traces / "id-1-x.yml"]
        assert _mod.collect_violations(schema_path=schema, traces_dir=traces) == []

    def test_yaml_parse_error_is_reported(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "broken.yml", "id: ID-1\ntitle: [unterminated\n")
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(parse)"
        # The message names the exception class, so the three kinds of
        # unreadable trace are distinguishable in CI output.
        assert "ParserError" in violations[0].message

    @pytest.mark.os_sensitive
    @pytest.mark.parametrize("kind", ["undecodable", "directory"])
    def test_unreadable_trace_is_a_violation_not_a_traceback(self, tmp_path, kind):
        # Neither is a yaml.YAMLError: both come out of read_text before
        # the parser. Uncaught they abort this gate with a traceback in
        # `lint` and `docs-gate` instead of printing the violation it
        # exists to print. The glob admits directories because Path.glob
        # does not filter to files, and a bad rebase can leave a file
        # undecodable. Every consumer handles the same cases — one driver,
        # so they must agree, and each must be shown to agree rather than
        # asserted to: report_trace_outcomes.py and report_token_usage.py
        # pin them in their own suites.
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        traces.mkdir(parents=True, exist_ok=True)
        if kind == "undecodable":
            (traces / "bad.yml").write_bytes(b'id: ID-1\ntitle: "\xff\xfe"\n')
            expected = "UnicodeDecodeError"
        else:
            (traces / "adir.yml").mkdir()
            # Windows refuses to open a directory with EACCES, not EISDIR.
            expected = "PermissionError" if sys.platform == "win32" else "IsADirectoryError"

        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)

        assert len(violations) == 1
        assert violations[0].path == "(parse)"
        assert expected in violations[0].message

    def test_broken_schema_short_circuits(self, tmp_path):
        # A malformed schema must fail loudly, not silently pass every trace.
        schema = tmp_path / "_schema.yml"
        schema.write_text('type: "not-a-real-type"\n', encoding="utf-8")
        traces = tmp_path / "traces"
        _write_trace(traces, "id-1-x.yml", 'id: "ID-1"\ntitle: "ok"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(schema)"

    def test_schema_examples_are_validated(self, tmp_path):
        # A drifted example in the schema's own examples block is a violation,
        # even when every trace file is fine. ``examples`` is a JSON Schema
        # annotation jsonschema never validates, so the gate must do it.
        schema = tmp_path / "_schema.yml"
        schema.write_text(
            textwrap.dedent(
                """
                $schema: "https://json-schema.org/draft/2020-12/schema"
                type: object
                required: [id, title]
                additionalProperties: false
                properties:
                  id:
                    type: string
                    pattern: "^ID-[0-9]+$"
                  title:
                    type: string
                examples:
                  - id: ID-1
                    title: "drifted example"
                    extra: "nope"
                """
            ),
            encoding="utf-8",
        )
        traces = tmp_path / "traces"
        _write_trace(traces, "id-1-x.yml", 'id: "ID-1"\ntitle: "ok"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert "examples[0]" in violations[0].source
        assert "extra" in violations[0].message


class TestDuplicateKeys:
    """How the gate parses: the strict loader, and the arm that reports its failures.

    Covers the duplicate-key rule below and the read-and-parse failures of
    `load_schema`, which share one `except` arm and arrived together. A guard
    about *what the schema says* belongs in `TestValidation`; a guard about
    whether a file parses at all, or about what happens when it cannot, belongs
    here.

    A repeated mapping key is a violation, not a silent last-wins merge.

    ``yaml.safe_load`` resolves a duplicate key to the last occurrence and says
    nothing, so a trace carrying one validated while half its content was
    discarded. Measured on the live corpus before this gate existed:
    ``BK-221-test-pbt-write-result-s3-azure-per-backend.yml`` carried
    ``surprising_ripples`` twice and the gate reported the corpus clean.

    The reachable authoring path is RFC-0015 D4's paste-the-block workflow —
    pasting the ``review:`` block a second time instead of replacing it yields
    two top-level ``review:`` keys — but the defect is not specific to it, so
    neither is the check.
    """

    def test_duplicate_top_level_key_is_reported(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "dup.yml", 'id: "ID-1"\ntitle: "first"\ntitle: "second"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(parse)"
        assert "title" in violations[0].message

    def test_duplicate_nested_key_is_reported(self, tmp_path):
        """Nested, not only top-level: last-wins discards content at any depth."""
        schema = tmp_path / "_schema.yml"
        schema.write_text(
            textwrap.dedent(
                """
                $schema: "https://json-schema.org/draft/2020-12/schema"
                type: object
                properties:
                  outer:
                    type: object
                """
            ),
            encoding="utf-8",
        )
        traces = tmp_path / "traces"
        _write_trace(traces, "dup.yml", "outer:\n  a: 1\n  a: 2\n")
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(parse)"

    def test_an_unhashable_key_is_reported_not_raised(self, tmp_path):
        """A complex key must not escape as `TypeError`.

        PyYAML's own `construct_mapping` checks `isinstance(key, Hashable)`
        before using the key and raises `ConstructorError` when it is not.
        A duplicate-detector that tests membership first does the unhashable
        lookup itself, and `TypeError` is not a `yaml.YAMLError` — so it
        escapes the `except yaml.YAMLError` arm every consumer has, and the
        gate aborts with a traceback instead. Measured before the
        guard: `load_trace('? [a, b]\\n: value\\n')` raised `TypeError`.
        """
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "complex.yml", "? [a, b]\n: value\n")
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert violations, "an unhashable key must be reported, not raised"
        assert violations[0].path == "(parse)"

    def test_a_duplicate_key_in_the_schema_is_reported(self, tmp_path):
        """The authority file is inside the guard, not outside it.

        `_schema.yml` is the one YAML whose duplicate key disarms the gate for
        the *whole* corpus: two `required:` keys under `properties.review`
        leave a well-formed schema that `check_schema` passes, and every trace
        then validates against constraints nobody wrote. Reported rather than
        raised, symmetric with the malformed-schema path beside it.
        """
        schema = tmp_path / "_schema.yml"
        schema.write_text(
            textwrap.dedent(
                """
                $schema: "https://json-schema.org/draft/2020-12/schema"
                type: object
                required: [id]
                required: [title]
                """
            ),
            encoding="utf-8",
        )
        traces = tmp_path / "traces"
        _write_trace(traces, "ok.yml", 'id: "ID-1"\n')
        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(schema)"
        assert "required" in violations[0].message

    def test_distinct_keys_still_parse(self, tmp_path):
        """The guard must not fire on a mapping that merely repeats a *value*."""
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "ok.yml", 'id: "ID-1"\ntitle: "ID-1"\n')
        assert _mod.collect_violations(schema_path=schema, traces_dir=traces) == []

    @pytest.mark.parametrize("kind", ["missing", "undecodable"])
    def test_an_unreadable_schema_is_a_violation_not_a_traceback(self, tmp_path, kind):
        """The `OSError` and `UnicodeDecodeError` members of the new arm.

        `load_schema` reads and parses, so its failures are not only
        `YAMLError`: the path may not exist, and a bad rebase can leave the
        file undecodable. Untested, the arm could be narrowed to
        `except yaml.YAMLError` and every other test here would still pass —
        while the gate aborted with a traceback on the two cases the trace loop
        already handles for the same reasons.
        """
        schema = tmp_path / "_schema.yml"
        if kind == "undecodable":
            schema.write_bytes(b"\xff\xfe$schema: x\n")
        traces = tmp_path / "traces"
        _write_trace(traces, "ok.yml", 'id: "ID-1"\n')

        violations = _mod.collect_violations(schema_path=schema, traces_dir=traces)
        assert len(violations) == 1
        assert violations[0].path == "(schema)"
        assert violations[0].source.endswith("_schema.yml"), "the failing artifact must be named (Rule 2)"

    # The invariant, as a table: `load_trace` equals `yaml.safe_load` for every
    # document with no repeated *literal* key, and raises a `yaml.YAMLError` for
    # every document that has one. Three loader attempts each passed the shapes
    # they were written against and broke one they were not, so the shapes are
    # enumerated rather than sampled — the repeat-site escalation in `/ship`.
    # The four marked (regression) are the ones earlier attempts got wrong.
    _SHAPES = [
        ("plain", "a: 1\nb: 2\n", False),
        ("duplicate_top_level", "a: 1\na: 2\n", True),
        ("duplicate_nested", "o:\n  a: 1\n  a: 2\n", True),
        ("duplicate_in_sequence_of_mappings", "- a: 1\n  a: 2\n", True),
        ("merge_no_overlap", "base: &b\n  a: 1\nd:\n  <<: *b\n  c: 2\n", False),
        ("merge_override", "base: &b\n  a: 1\nd:\n  <<: *b\n  a: 2\n", False),  # regression
        ("merge_of_two_anchors", "x: &x\n  a: 1\ny: &y\n  b: 2\nd:\n  <<: [*x, *y]\n  c: 3\n", False),
        ("merge_plus_real_duplicate", "base: &b\n  a: 1\nd:\n  <<: *b\n  c: 1\n  c: 2\n", True),
        ("anchor_alias_no_merge", "a: &v 1\nb: *v\n", False),
        ("unhashable_key", "? [a, b]\n: value\n", True),  # regression
        ("map_tag_on_sequence", "x: !!map\n  - a\n", True),  # regression
        ("set_tag_on_scalar", "x: !!set hello\n", True),  # regression
        ("set_tag_proper", "x: !!set\n  ? a\n  ? b\n", False),
        ("empty_mapping", "{}\n", False),
        ("document_is_a_list", "- 1\n- 2\n", False),
    ]

    @pytest.mark.parametrize(("name", "doc", "must_refuse"), _SHAPES, ids=[s[0] for s in _SHAPES])
    def test_the_loader_restricts_safe_load_and_nothing_more(self, name, doc, must_refuse):
        """Refuse exactly the repeated-key documents, and agree with `safe_load` on the rest.

        Both halves matter and each caught a real defect. Refusing too little
        was the original bug; refusing too *much* — a merge override, a
        `!!map` on a sequence — was introduced by the fixes for it, twice. The
        `must_refuse` cases also assert the refusal is a `yaml.YAMLError`,
        because a `TypeError` or `ValueError` escapes the `yaml.YAMLError` arm
        every consumer has and aborts the gate with a traceback.
        """
        import yaml as _yaml

        if must_refuse:
            with pytest.raises(_yaml.YAMLError):
                _trace_corpus.load_trace(doc)
            return

        try:
            expected, expected_error = _yaml.safe_load(doc), None
        except _yaml.YAMLError as exc:
            expected, expected_error = None, type(exc)

        if expected_error is not None:
            with pytest.raises(expected_error):
                _trace_corpus.load_trace(doc)
        else:
            assert _trace_corpus.load_trace(doc) == expected

    def test_a_merge_key_is_not_a_duplicate(self, tmp_path):
        """`<<` splices; it is not a repeated key, and must parse as `safe_load` does.

        The strict loader is a *restriction* of `SafeLoader` to documents with
        no repeated key, so anything `yaml.safe_load` accepts and that has no
        duplicate must still parse. A scan that treats the literal `<<` as an
        ordinary key breaks that, refusing a document `safe_load` expands with
        an error naming `tag:yaml.org,2002:merge`. The loader skips that tag
        instead, and leaves the splice to `SafeConstructor`; see
        `StrictTraceLoader.construct_mapping`, which states why that order and
        not the reverse.
        """
        import yaml as _yaml

        schema = tmp_path / "_schema.yml"
        schema.write_text(
            textwrap.dedent(
                """
                $schema: "https://json-schema.org/draft/2020-12/schema"
                type: object
                """
            ),
            encoding="utf-8",
        )
        traces = tmp_path / "traces"
        body = "base: &b\n  a: 1\nderived:\n  <<: *b\n  c: 2\n"
        _write_trace(traces, "merge.yml", body)

        assert _mod.collect_violations(schema_path=schema, traces_dir=traces) == []
        # And the parse agrees with the loader it restricts, rather than merely
        # not failing: a merge that silently dropped `a` would also pass above.
        assert _trace_corpus.load_trace(body) == _yaml.safe_load(body)


class TestOneLoader:
    """Every trace consumer parses through the same function, and it is pinned.

    `_trace_corpus`'s docstring makes this the load-bearing claim: "A consumer
    reaching for `yaml.safe_load` directly opts back out of it silently, which
    is why there is one function rather than a documented convention." Nothing
    enforced it — reverting `report_trace_outcomes.py` to `yaml.safe_load` left
    its whole suite green, and ruff removed the orphaned import without
    complaint, so the revert was clean.

    Asserted over the source rather than by parsing a fixture, for the reason
    `test_check_backlog_ids_vs_base.py`'s `TestReuse` gives: the defect is a
    second spelling of one rule, and only reading the text catches it before
    the two disagree.
    """

    @staticmethod
    def _consumers() -> dict[str, str]:
        """Every script under `scripts/` that reads the trace corpus, derived rather than listed.

        **Bound**: `scripts/` only. `sdd/rfcs/rfc-0015-rounds.py` also reads
        the corpus and is outside it — it text-scans rather than parsing
        YAML, so it cannot hit the last-wins defect today, but it is a live
        counterexample to a broader reading of this docstring.

        A hard-coded pair is the DRIFT-RULES Rule 3 shape this suite removes
        elsewhere: a third consumer added later would reach for
        `yaml.safe_load`, restore last-wins silently, and leave the guard
        written to prevent exactly that still green.
        """
        found = {}
        # rglob, not glob: `scripts/docs/` already holds five modules
        # (`check_links.py`, `link.py`, `nav.py`, `render.py`, `scan.py`), so a
        # consumer one directory down is not hypothetical, and a non-recursive
        # walk leaves the very hole this derivation exists to close. Measured:
        # a consumer planted at `scripts/docs/` passed both guards under `glob`.
        for path in sorted(_SCRIPTS_DIR.rglob("*.py")):
            if path.name == "_trace_corpus.py":
                continue
            source = path.read_text(encoding="utf-8")
            # Keyed on what makes a script a trace consumer — that it reads the
            # corpus — not on whether it already imports the shared module. The
            # failure this guards is a NEW consumer reaching for `yaml.safe_load`
            # directly, and such a script contains no `_trace_corpus` reference,
            # so a predicate keyed on that could never see it.
            if "sdd/traces" in source or "iter_trace_files" in source or "TRACE_GLOB" in source:
                found[path.name] = source
        assert found, "no trace-corpus consumers found; the derivation is wrong"
        return found

    @staticmethod
    def _unsafe_yaml_calls(source: str) -> list[str]:
        """Calls that restore last-wins, found in the AST rather than in the text.

        Three instruments were tried and the first two were wrong the same way —
        they keyed on a *spelling* rather than on the thing. `"yaml.safe_load" in
        source` missed `from yaml import safe_load`, `import yaml as y`, and
        `yaml.load(..., Loader=SafeLoader)`; widening to the bare substring
        `"safe_load"` then fired on `check_traces.py`'s own prose explaining why
        the strict loader exists. Parsing the module answers the actual question —
        is this call made — and no comment, docstring or import alias changes it.
        """
        import ast

        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover — a broken script is lint's problem
            return []

        aliases = {"yaml"}
        bare: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases |= {a.asname or a.name for a in node.names if a.name == "yaml"}
            elif isinstance(node, ast.ImportFrom) and node.module == "yaml":
                bare |= {a.asname or a.name for a in node.names}

        unsafe = {"safe_load", "safe_load_all", "load", "load_all"}
        found: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id in aliases and func.attr in unsafe:
                    found.append(f"{func.value.id}.{func.attr}")
            elif isinstance(func, ast.Name) and func.id in bare and func.id in unsafe:
                found.append(func.id)
        return found

    def test_no_consumer_parses_the_corpus_outside_the_shared_loader(self) -> None:
        for name, source in self._consumers().items():
            calls = self._unsafe_yaml_calls(source)
            assert not calls, (
                f"{name} parses YAML directly ({', '.join(sorted(set(calls)))}) instead of "
                "_trace_corpus.load_trace, which silently restores the last-wins "
                "duplicate-key behaviour"
            )

    def test_every_parsing_consumer_uses_the_shared_loader(self) -> None:
        """Bound: the consumers that *parse* the corpus, not every reader of it.

        Most scripts `_consumers` matches name `sdd/traces` as a path and never
        parse a trace — `check_no_retrospective.py` scans it as text. Requiring
        `load_trace` of those would demand an import they have no use for. The
        `safe_load` prohibition above is the half that binds all of them, and
        it is the half that catches a new consumer.
        """
        parsing = {n: src for n, src in self._consumers().items() if "yaml." in src or "load_trace" in src}
        assert parsing, "no parsing consumers found; the derivation is wrong"
        for name, source in parsing.items():
            # Over the body, not the whole file: `check_traces.py`'s module
            # docstring names `load_trace` in prose, so a whole-file search
            # passes with both the import and the call deleted.
            body = source.split('"""', 2)[-1]
            assert "load_trace" in body, f"{name} parses the corpus without the shared loader"


_LOG = "sdd/decisions/s1.jsonl"
_QUESTION = "Which way?"
# The harness's dismissal string, as observed in RFC-0018 § Step 0 follow-up case a'.
_SENTINEL = "[User dismissed — do not proceed, wait for next instruction]"


def _asked(tool_use_id: str = "toolu_1", *, header: str = "Way") -> dict:
    return {
        "event": "asked",
        "tool_use_id": tool_use_id,
        "tool_input": {
            "questions": [
                {
                    "question": _QUESTION,
                    "header": header,
                    "options": [{"label": "A (Recommended)"}, {"label": "B"}],
                    "multiSelect": False,
                }
            ]
        },
    }


def _answered(tool_use_id: str = "toolu_1", answer: str | None = "A (Recommended)") -> dict:
    answers = {} if answer is None else {_QUESTION: answer}
    return {"event": "answered", "tool_use_id": tool_use_id, "tool_response": {"answers": answers}}


class TestDecisionLogs:
    """RFC-0018 D4.2: every log a trace lists exists, parses, and pairs each dialog at most once.

    `unanswered` and unknown event kinds are reported, not failed: declining a
    dialog is a legitimate act, and a later hook registration must not break a
    reader written before it (D3).
    """

    @staticmethod
    def _run(tmp_path, lines=None, *, raw=None, listed=(_LOG,)):
        import json

        schema = _write_schema(tmp_path)
        traces = tmp_path / "sdd" / "traces"
        body = 'id: "ID-1"\ntitle: "ok"\n'
        if listed:
            body += "decisions:\n" + "".join(f'  - "{p}"\n' for p in listed)
        _write_trace(traces, "id-1-x.yml", body)
        if lines is not None or raw is not None:
            log = tmp_path / _LOG
            log.parent.mkdir(parents=True, exist_ok=True)
            text = raw if raw is not None else "".join(json.dumps(line) + "\n" for line in lines or [])
            log.write_text(text, encoding="utf-8")
        return _mod.collect(schema_path=schema, traces_dir=traces, root=tmp_path)

    def test_a_clean_log_passes_with_nothing_to_report(self, tmp_path):
        report = self._run(tmp_path, [_asked(), _answered()])
        assert report.violations == []
        assert report.notes == []

    def test_a_trace_without_decisions_reads_no_log(self, tmp_path):
        report = self._run(tmp_path, listed=())
        assert report.violations == []
        assert report.notes == []

    def test_a_missing_log_is_a_violation(self, tmp_path):
        report = self._run(tmp_path)
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.source.endswith("id-1-x.yml")
        assert v.path == "decisions[0]"
        assert _LOG in v.message
        assert "does not exist" in v.message

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"event": "asked", "tool_use_id": "toolu_1"}\n{not json\n', "line 2"),
            ('{"event": "asked", "tool_use_id": "toolu_1"}\n\n', "line 2"),
            ('["a list, not an object"]\n', "line 1"),
        ],
        ids=["malformed", "blank", "not_an_object"],
    )
    def test_a_line_that_does_not_parse_is_a_violation_naming_the_line(self, tmp_path, raw, expected):
        report = self._run(tmp_path, raw=raw)
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.path == "decisions[0]"
        assert _LOG in v.message
        assert expected in v.message

    def test_an_undecodable_log_is_a_violation_not_a_traceback(self, tmp_path):
        (tmp_path / "sdd" / "decisions").mkdir(parents=True)
        (tmp_path / _LOG).write_bytes(b'{"event": "\xff"}\n')
        report = self._run(tmp_path)
        assert len(report.violations) == 1
        assert "line 1: not UTF-8" in report.violations[0].message

    def test_an_append_cut_inside_a_multibyte_character_is_localized_to_its_line(self, tmp_path):
        # The recorder writes ensure_ascii=False, so a truncated append can end
        # mid-character. That is the schema remedy's "line that does not parse",
        # and it must be named by line, with the rest of the log still checked.
        import json

        good = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in [_asked("toolu_9")])
        cut = json.dumps(_asked(header="A → B"), ensure_ascii=False).encode("utf-8")
        cut = cut[: cut.index("→".encode()) + 1]  # one byte of a three-byte character
        (tmp_path / "sdd" / "decisions").mkdir(parents=True)
        (tmp_path / _LOG).write_bytes(good.encode("utf-8") + cut)
        report = self._run(tmp_path)
        assert len(report.violations) == 1, report.violations
        assert "line 2: not UTF-8" in report.violations[0].message
        assert [n for n in report.notes if "toolu_9" in n.message], "line 1 must still be checked"

    def test_a_dialog_answered_twice_is_a_violation_naming_its_id(self, tmp_path):
        report = self._run(tmp_path, [_asked(), _answered(), _answered(answer="B")])
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.path == "decisions[0]"
        assert "toolu_1" in v.message
        assert "line 3" in v.message, "the second answered line is the one to inspect (Rule 2)"
        # Two different answers are not a merge artifact: the maintainer decides.
        assert "differs from line 2" in v.message

    def test_an_identical_second_answered_line_is_named_as_a_copy(self, tmp_path):
        # The union-merge artifact the schema's remedy lets an author delete.
        report = self._run(tmp_path, [_asked(), _answered(), _answered()])
        assert len(report.violations) == 1
        assert "identical copy of line 2" in report.violations[0].message

    def test_a_path_the_schema_rejects_is_not_read(self, tmp_path):
        # The pattern confines the verdict; the reader must honour it too, or a
        # listed path outside the log directory is opened and echoed.
        (tmp_path / "outside.jsonl").write_text('{"event": "secret-content"}\n{not json\n', encoding="utf-8")
        report = self._run(tmp_path, listed=("outside.jsonl",))
        assert len(report.violations) == 1, report.violations
        assert report.violations[0].path == "decisions[0]"
        assert "does not match" in report.violations[0].message
        assert report.notes == [], "nothing from the unlisted-directory file may be echoed"

    def test_an_asked_event_with_unreadable_questions_is_reported(self, tmp_path):
        # A reshaped tool_input must not silently drop the unanswered report.
        asked = {"event": "asked", "tool_use_id": "toolu_1", "tool_input": {"questions": "reshaped"}}
        report = self._run(tmp_path, [asked])
        assert report.violations == []
        assert len(report.notes) == 1
        assert "toolu_1" in report.notes[0].message
        assert "no readable questions" in report.notes[0].message

    @pytest.mark.parametrize("separator", [chr(0x2028), chr(0x2029), chr(0x85)], ids=["LS", "PS", "NEL"])
    def test_a_record_holding_a_unicode_line_break_still_parses(self, tmp_path, separator):
        # The recorder writes ensure_ascii=False, which leaves these unescaped;
        # str.splitlines() breaks on them, and the remedy would then delete a record.
        import json

        lines = [_asked(), _answered(answer=f"free text {separator} spanning")]
        raw = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        assert separator in raw, "the fixture must carry the raw character, as the recorder writes it"
        report = self._run(tmp_path, raw=raw)
        assert report.violations == []

    def test_a_log_listed_twice_is_read_once(self, tmp_path):
        # uniqueItems reports at `decisions`, not `decisions[1]`, so the
        # per-entry skip alone would read the copy and duplicate its notes.
        report = self._run(tmp_path, [_asked()], listed=(_LOG, _LOG))
        assert [v.path for v in report.violations] == ["decisions"]
        assert len(report.notes) == 1, report.notes

    def test_an_unhashable_tool_use_id_is_reported_not_raised(self, tmp_path):
        lines = [{"event": "asked", "tool_use_id": ["not", "a", "key"]}, _asked(), _answered()]
        report = self._run(tmp_path, lines)
        assert report.violations == []
        assert len(report.notes) == 1
        assert "line 1" in report.notes[0].message
        assert "tool_use_id" in report.notes[0].message

    def test_id_less_dialogs_are_skipped_not_paired_under_none(self, tmp_path):
        # The recorder writes payload.get("tool_use_id"), null when the payload
        # omits it. Pairing two unrelated id-less dialogs under None would fail
        # them as "answered twice", and the remedy would delete a real record.
        lines = [
            {**_asked(), "tool_use_id": None},
            {**_answered(), "tool_use_id": None},
            {k: v for k, v in _asked().items() if k != "tool_use_id"},
            {**_answered(answer="B"), "tool_use_id": None},
        ]
        report = self._run(tmp_path, lines)
        assert report.violations == []
        assert len(report.notes) == 4, report.notes
        assert all("tool_use_id is not a string" in n.message for n in report.notes)

    def test_an_answered_event_with_no_asked_is_reported(self, tmp_path):
        report = self._run(tmp_path, [_answered()])
        assert report.violations == []
        assert len(report.notes) == 1
        assert "toolu_1" in report.notes[0].message
        assert "no asked event" in report.notes[0].message

    def test_two_dialogs_each_answered_once_pass(self, tmp_path):
        lines = [_asked("toolu_1"), _answered("toolu_1"), _asked("toolu_2"), _answered("toolu_2", "B")]
        assert self._run(tmp_path, lines).violations == []

    @pytest.mark.parametrize(
        "lines",
        [
            [_asked()],
            [_asked(), _answered(answer=_SENTINEL)],
            [_asked(), _answered(answer=None)],
        ],
        ids=["denied_no_answered_event", "dismissed_sentinel", "question_absent_from_answers"],
    )
    def test_an_unanswered_question_is_reported_not_failed(self, tmp_path, lines):
        report = self._run(tmp_path, lines)
        assert report.violations == []
        assert len(report.notes) == 1
        note = report.notes[0]
        assert note.path == "decisions[0]"
        assert "unanswered" in note.message
        assert "toolu_1" in note.message
        assert "Way" in note.message, "the header is what a reader recognises the question by"

    def test_free_text_starting_with_the_prefix_reads_as_dismissal(self, tmp_path):
        # D3's stated bound: the sentinel is matched by prefix, so this is read as dismissal.
        report = self._run(tmp_path, [_asked(), _answered(answer="[User dismissed it, then typed this")])
        assert [n.message for n in report.notes if "unanswered" in n.message]

    def test_an_unknown_event_kind_is_reported_not_failed(self, tmp_path):
        lines = [_asked(), {"event": "PostToolUseFailure", "tool_use_id": "toolu_1"}, _answered()]
        report = self._run(tmp_path, lines)
        assert report.violations == []
        assert len(report.notes) == 1
        assert "PostToolUseFailure" in report.notes[0].message
        assert "line 2" in report.notes[0].message

    def test_the_live_schema_confines_listed_paths_to_the_log_directory(self):
        # Anything else (an absolute path, a `..` escape, another extension) is
        # not a recorder log; the pattern mirrors record_decision.py's session-id rule.
        from jsonschema.validators import validator_for

        schema = _mod.load_schema()
        validator = validator_for(schema)(schema["properties"]["decisions"])
        assert validator.is_valid(["sdd/decisions/8352892b-3229-4a0a-9656-c75b8d1d153b.jsonl"])
        for bad in ["/etc/passwd", "sdd/decisions/../traces/x.jsonl", "sdd/decisions/a.json", "x.jsonl"]:
            assert not validator.is_valid([bad]), bad
        assert not validator.is_valid([_LOG, _LOG]), "a log listed twice is a copy-paste slip"


class TestMain:
    def test_main_prints_notes_and_still_returns_zero(self, tmp_path, capsys):
        import json

        schema = _write_schema(tmp_path)
        traces = tmp_path / "sdd" / "traces"
        _write_trace(traces, "id-1-x.yml", f'id: "ID-1"\ntitle: "ok"\ndecisions:\n  - "{_LOG}"\n')
        log = tmp_path / _LOG
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps(_asked()) + "\n", encoding="utf-8")
        rc = _mod.main(["--schema", str(schema), "--traces-dir", str(traces), "--root", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "unanswered" in out
        assert "toolu_1" in out

    def test_main_prints_log_text_through_a_cp1252_stdout(self, tmp_path):
        # Notes echo headers from logs. A redirected Windows stdout encodes
        # with the locale codec; forced here so the case runs on every OS.
        import json
        import os
        import subprocess

        schema = _write_schema(tmp_path)
        traces = tmp_path / "sdd" / "traces"
        _write_trace(traces, "id-1-x.yml", f'id: "ID-1"\ntitle: "ok"\ndecisions:\n  - "{_LOG}"\n')
        log = tmp_path / _LOG
        log.parent.mkdir(parents=True)
        log.write_text(json.dumps(_asked(header="A → B"), ensure_ascii=False) + "\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONUTF8", "PYTHONIOENCODING"}}
        env["PYTHONIOENCODING"] = "cp1252"
        args = ["--schema", str(schema), "--traces-dir", str(traces), "--root", str(tmp_path)]
        result = subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, env=env, check=False)
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        assert "A → B" in result.stdout.decode("utf-8")

    def test_main_hint_names_the_log_case(self, tmp_path, capsys):
        # A log violation is not a trace disagreeing with the schema; the hint
        # must send the reader to the log and its remedy.
        schema = _write_schema(tmp_path)
        traces = tmp_path / "sdd" / "traces"
        _write_trace(traces, "id-1-x.yml", f'id: "ID-1"\ntitle: "ok"\ndecisions:\n  - "{_LOG}"\n')
        rc = _mod.main(["--schema", str(schema), "--traces-dir", str(traces), "--root", str(tmp_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "`decisions[N]`" in err
        assert "under `decisions:` in sdd/traces/_schema.yml" in err, "the hint points at the remedy's home"

    def test_main_clean_returns_zero(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "id-1-x.yml", 'id: "ID-1"\ntitle: "ok"\n')
        rc = _mod.main(["--schema", str(schema), "--traces-dir", str(traces)])
        assert rc == 0

    def test_main_dirty_returns_one(self, tmp_path):
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        _write_trace(traces, "bad.yml", 'id: "BK-1"\ntitle: "ok"\n')
        rc = _mod.main(["--schema", str(schema), "--traces-dir", str(traces)])
        assert rc == 1


def test_repo_traces_validate():
    """The live repo must pass its own gate."""
    assert _mod.collect_violations() == []
