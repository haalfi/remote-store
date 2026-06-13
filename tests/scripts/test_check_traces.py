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

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_traces.py"


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
