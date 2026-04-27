"""Unit tests for scripts/check_test_placement.py.

Exercises both detection paths (variable-name match and string-literal match),
the AnnAssign handling, and the false-positive guard on the index slot.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_test_placement.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_test_placement", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_test_placement", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
_names_referencing_scripts = _mod._names_referencing_scripts
_uses_scripts_sys_path = _mod._uses_scripts_sys_path
_check_file = _mod._check_file
main = _mod.main


# ---------------------------------------------------------------------------
# _names_referencing_scripts
# ---------------------------------------------------------------------------


class TestNamesReferencingScripts:
    def _parse(self, src: str) -> ast.Module:
        return ast.parse(src)

    def test_plain_assignment_detected(self):
        tree = self._parse('SCRIPTS = ROOT / "scripts"')
        assert "SCRIPTS" in _names_referencing_scripts(tree)

    def test_annotated_assignment_detected(self):
        tree = self._parse('SCRIPTS: Path = ROOT / "scripts"')
        assert "SCRIPTS" in _names_referencing_scripts(tree)

    def test_unrelated_variable_not_included(self):
        tree = self._parse('OTHER = ROOT / "src"')
        assert not _names_referencing_scripts(tree)

    def test_substring_match_in_path_string(self):
        tree = self._parse('SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"')
        assert "SCRIPTS_DIR" in _names_referencing_scripts(tree)

    def test_no_value_annotated_assignment_skipped(self):
        # Bare annotation with no value: `SCRIPTS: Path` — no RHS to inspect.
        tree = self._parse("SCRIPTS: Path")
        assert not _names_referencing_scripts(tree)


# ---------------------------------------------------------------------------
# _uses_scripts_sys_path
# ---------------------------------------------------------------------------

_PLAIN_ASSIGN = """\
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

import sys
sys.path.insert(0, str(SCRIPTS))
"""

_ANNOTATED_ASSIGN = """\
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS: Path = ROOT / "scripts"

import sys
sys.path.insert(0, str(SCRIPTS))
"""

_STRING_LITERAL = """\
import sys
sys.path.insert(0, "/home/user/project/scripts")
"""

_APPEND_VARIANT = """\
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

import sys
sys.path.append(str(SCRIPTS))
"""

_INDEX_SLOT_ONLY = """\
# SCRIPTS_IDX happens to have "scripts" in its assigned string,
# but is used as the INSERT INDEX, not the path — no false positive.
SCRIPTS_IDX = some_map["scripts_index"]
import sys
sys.path.insert(SCRIPTS_IDX, "/some/unrelated/path")
"""

_NO_SCRIPTS_SYS_PATH = """\
import sys
sys.path.insert(0, str(OTHER_DIR))
"""


class TestUsesScriptsSysPath:
    def _run(self, src: str):
        tree = ast.parse(src)
        names = _names_referencing_scripts(tree)
        return _uses_scripts_sys_path(tree, names)

    def test_plain_assignment_detected(self):
        assert self._run(_PLAIN_ASSIGN) is not None

    def test_annotated_assignment_detected(self):
        assert self._run(_ANNOTATED_ASSIGN) is not None

    def test_string_literal_detected(self):
        assert self._run(_STRING_LITERAL) is not None

    def test_append_detected(self):
        assert self._run(_APPEND_VARIANT) is not None

    def test_no_match_returns_none(self):
        assert self._run(_NO_SCRIPTS_SYS_PATH) is None

    def test_index_slot_does_not_trigger_false_positive(self):
        # scripts_names contains SCRIPTS_IDX (from "scripts_index"), but it's
        # used as the index arg of insert, not the path arg — must not flag.
        assert self._run(_INDEX_SLOT_ONLY) is None


# ---------------------------------------------------------------------------
# _check_file  (integration: real temp files)
# ---------------------------------------------------------------------------


class TestCheckFile:
    def test_misplaced_file_is_flagged(self, tmp_path):
        f = tmp_path / "test_something.py"
        f.write_text(_PLAIN_ASSIGN, encoding="utf-8")
        result = _check_file(f)
        assert result is not None
        assert "move to tests/scripts/" in result

    def test_clean_file_returns_none(self, tmp_path):
        f = tmp_path / "test_clean.py"
        f.write_text("import pytest\n\ndef test_ok():\n    assert True\n", encoding="utf-8")
        assert _check_file(f) is None

    def test_annotated_assignment_flagged(self, tmp_path):
        f = tmp_path / "test_annotated.py"
        f.write_text(_ANNOTATED_ASSIGN, encoding="utf-8")
        assert _check_file(f) is not None

    def test_syntax_error_returns_none(self, tmp_path, capsys):
        f = tmp_path / "test_broken.py"
        # Plant sys.path and scripts keywords so the pre-filter passes,
        # then break the syntax so ast.parse fails.
        f.write_text("scripts sys.path !!invalid!!", encoding="utf-8")
        result = _check_file(f)
        assert result is None
        assert "SyntaxError" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main()  (end-to-end)
# ---------------------------------------------------------------------------


class TestMain:
    def test_flags_misplaced_file_in_root(self, tmp_path):
        (tmp_path / "scripts").mkdir()  # tests/scripts/ subpackage
        (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        bad = tmp_path / "test_misplaced.py"
        bad.write_text(_PLAIN_ASSIGN, encoding="utf-8")
        assert main([str(tmp_path)]) == 1

    def test_skips_file_already_in_scripts_subpkg(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "__init__.py").write_text("", encoding="utf-8")
        good = scripts_dir / "test_correct.py"
        good.write_text(_PLAIN_ASSIGN, encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_flags_misplaced_file_in_subdir(self, tmp_path):
        # A scripts-loading test under tests/backends/ must also be flagged.
        backends = tmp_path / "backends"
        backends.mkdir()
        (tmp_path / "scripts").mkdir()
        bad = backends / "test_misplaced.py"
        bad.write_text(_PLAIN_ASSIGN, encoding="utf-8")
        assert main([str(tmp_path)]) == 1

    def test_clean_tree_returns_zero(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        f = tmp_path / "test_ok.py"
        f.write_text("def test_simple():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        assert main([str(tmp_path)]) == 0
