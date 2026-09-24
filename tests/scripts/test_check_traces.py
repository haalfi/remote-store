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

import _trace_corpus  # noqa: E402  — the shared loader both consumers use


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

    @pytest.mark.parametrize("kind", ["undecodable", "directory"])
    def test_unreadable_trace_is_a_violation_not_a_traceback(self, tmp_path, kind):
        # Neither is a yaml.YAMLError: both come out of read_text before
        # the parser. Uncaught they abort this gate with a traceback in
        # `lint` and `docs-gate` instead of printing the violation it
        # exists to print. The glob admits directories because Path.glob
        # does not filter to files, and a bad rebase can leave a file
        # undecodable. report_trace_outcomes.py handles the same three —
        # one driver, so the consumers must agree, and both must be shown
        # to agree rather than asserted to.
        schema = _write_schema(tmp_path)
        traces = tmp_path / "traces"
        traces.mkdir(parents=True, exist_ok=True)
        if kind == "undecodable":
            (traces / "bad.yml").write_bytes(b'id: ID-1\ntitle: "\xff\xfe"\n')
            expected = "UnicodeDecodeError"
        else:
            (traces / "adir.yml").mkdir()
            expected = "IsADirectoryError"

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
        escapes the `except` arm both consumers report `(parse)` violations
        from, and the gate aborts with a traceback instead. Measured before the
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
        because a `TypeError` or `ValueError` escapes the arm both consumers
        report `(parse)` violations from and aborts the gate with a traceback.
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
    """Both trace consumers parse through the same function, and it is pinned.

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
        """Every script that reads the trace corpus, derived rather than listed.

        A hard-coded pair is the DRIFT-RULES Rule 3 shape this suite removes
        elsewhere: a third consumer added later would reach for
        `yaml.safe_load`, restore last-wins silently, and leave the guard
        written to prevent exactly that still green.
        """
        found = {}
        for path in sorted(_SCRIPTS_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "_trace_corpus" in source and path.name != "_trace_corpus.py":
                found[path.name] = source
        assert found, "no trace-corpus consumers found; the derivation is wrong"
        return found

    def test_no_consumer_calls_safe_load_directly(self) -> None:
        for name, source in self._consumers().items():
            body = source.split('"""', 2)[-1]  # skip the module docstring, which may discuss it
            assert "yaml.safe_load" not in body, (
                f"{name} parses trace YAML outside _trace_corpus.load_trace, "
                "which silently restores the last-wins duplicate-key behaviour"
            )

    def test_every_consumer_imports_the_shared_loader(self) -> None:
        # Asserted over the body, not the whole file: `check_traces.py`'s module
        # docstring names `load_trace` in prose, so a substring search over the
        # whole file passes with both the import and the call deleted.
        for name, source in self._consumers().items():
            body = source.split('"""', 2)[-1]
            assert "load_trace" in body, f"{name} no longer uses the shared loader"


class TestMain:
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
