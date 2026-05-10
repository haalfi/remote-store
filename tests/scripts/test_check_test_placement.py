"""Unit tests for scripts/check_test_placement.py.

Exercises all three placement rules:

S — scripts/ sys.path: variable-name match, string-literal match,
    AnnAssign handling, and the false-positive guard on the index slot.
B — backend imports at root: TEST-003 enforcement and the BK-190
    grandfathered allow-list.
E — ext placement: ``test_ext_*.py`` ban at root and the ext-source
    matching contract under ``tests/ext/``.
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
_check_backend_imports_at_root = _mod._check_backend_imports_at_root
_check_root_ext_naming = _mod._check_root_ext_naming
_check_ext_orphans = _mod._check_ext_orphans
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

    def test_unicode_decode_error_returns_none(self, tmp_path, capsys):
        f = tmp_path / "test_bad_encoding.py"
        # Raw bytes not valid UTF-8 — read_text raises UnicodeDecodeError.
        f.write_bytes(b"# scripts sys.path\n\xff\xfe")
        result = _check_file(f)
        assert result is None
        assert "UnicodeDecodeError" in capsys.readouterr().err


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


# ---------------------------------------------------------------------------
# Rule B — backend imports at root (TEST-003)
# ---------------------------------------------------------------------------


_AZURE_AT_ROOT = """\
from remote_store.backends._azure import AzureBackend

def test_uses_azure():
    assert AzureBackend is not None
"""

_S3_PUBLIC_IMPORT = """\
from remote_store.backends import S3Backend

def test_uses_s3():
    assert S3Backend is not None
"""

_MEMORY_OK = """\
from remote_store.backends._memory import MemoryBackend

def test_memory_only():
    assert MemoryBackend() is not None
"""

_LOCAL_OK = """\
from remote_store.backends._local import LocalBackend

def test_local_only():
    assert LocalBackend is not None
"""

_FILEINFO_OK = """\
from remote_store.backends._fileinfo import build_file_info

def test_fileinfo():
    assert build_file_info is not None
"""

_MIXED_BANNED_ALLOWED = """\
from remote_store.backends import S3Backend, MemoryBackend

def test_mixed():
    assert S3Backend is not None
    assert MemoryBackend is not None
"""

_BARE_IMPORT_AZURE = """\
import remote_store.backends._azure

def test_bare():
    assert remote_store.backends._azure is not None
"""

_BARE_IMPORT_AZURE_AS = """\
import remote_store.backends._sftp as _sftp_mod

def test_bare_as():
    assert _sftp_mod is not None
"""

_BARE_IMPORT_MEMORY = """\
import remote_store.backends._memory

def test_bare_memory():
    assert remote_store.backends._memory is not None
"""


class TestBackendImportsAtRoot:
    def test_flags_private_module_import(self, tmp_path):
        f = tmp_path / "test_at_root.py"
        f.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "remote_store.backends._azure" in violations[0]
        assert "TEST-003" in violations[0]

    def test_flags_public_concrete_class_import(self, tmp_path):
        f = tmp_path / "test_at_root.py"
        f.write_text(_S3_PUBLIC_IMPORT, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "S3Backend" in violations[0]

    def test_allows_memory(self, tmp_path):
        f = tmp_path / "test_at_root.py"
        f.write_text(_MEMORY_OK, encoding="utf-8")
        assert _check_backend_imports_at_root(f) == []

    def test_allows_local(self, tmp_path):
        f = tmp_path / "test_at_root.py"
        f.write_text(_LOCAL_OK, encoding="utf-8")
        assert _check_backend_imports_at_root(f) == []

    def test_allows_fileinfo_helper(self, tmp_path):
        # _fileinfo is a backend helper module, not a backend per se.
        f = tmp_path / "test_at_root.py"
        f.write_text(_FILEINFO_OK, encoding="utf-8")
        assert _check_backend_imports_at_root(f) == []

    def test_grandfathered_files_skipped(self, tmp_path):
        # A grandfathered name on a path that imports a banned backend must
        # still report no violations — the BK-190 audit owns the migration.
        f = tmp_path / "test_seekable.py"
        f.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        assert _check_backend_imports_at_root(f) == []

    def test_mixed_banned_allowed_flags_only_banned(self, tmp_path):
        # ``from remote_store.backends import S3Backend, MemoryBackend`` —
        # one banned + one allowed name on the same line. The check must
        # report S3Backend and not flag MemoryBackend; pin the filter so a
        # future refactor cannot accidentally drop or invert it.
        f = tmp_path / "test_at_root.py"
        f.write_text(_MIXED_BANNED_ALLOWED, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "S3Backend" in violations[0]
        assert "MemoryBackend" not in violations[0]

    def test_flags_bare_import_of_banned_module(self, tmp_path):
        # ``import remote_store.backends._azure`` — bare ``ast.Import`` form,
        # not ``from … import``. Must be flagged the same as the ``from``-form
        # so a new file can't sneak through by switching import styles.
        f = tmp_path / "test_at_root.py"
        f.write_text(_BARE_IMPORT_AZURE, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "remote_store.backends._azure" in violations[0]

    def test_flags_bare_import_with_alias(self, tmp_path):
        # ``import remote_store.backends._sftp as _sftp_mod`` — alias form.
        f = tmp_path / "test_at_root.py"
        f.write_text(_BARE_IMPORT_AZURE_AS, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "remote_store.backends._sftp" in violations[0]

    def test_allows_bare_import_of_memory(self, tmp_path):
        f = tmp_path / "test_at_root.py"
        f.write_text(_BARE_IMPORT_MEMORY, encoding="utf-8")
        assert _check_backend_imports_at_root(f) == []

    def test_main_flags_new_root_violation(self, tmp_path):
        bad = tmp_path / "test_new_module.py"
        bad.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        rc = main([str(tmp_path)], src_root=tmp_path / "missing_src")
        assert rc == 1


# ---------------------------------------------------------------------------
# Rule E — ext placement (TEST-002 / TEST-010)
# ---------------------------------------------------------------------------


class TestRootExtNaming:
    def test_flags_root_test_ext_prefix(self, tmp_path):
        bad = tmp_path / "test_ext_foo.py"
        bad.write_text("def test_x(): assert True\n", encoding="utf-8")
        violations = _check_root_ext_naming(tmp_path)
        assert len(violations) == 1
        assert "test_ext_foo.py" in violations[0]
        assert "tests/ext/test_foo.py" in violations[0]

    def test_clean_root_returns_empty(self, tmp_path):
        (tmp_path / "test_seekable.py").write_text("", encoding="utf-8")
        assert _check_root_ext_naming(tmp_path) == []


class TestExtOrphans:
    def _setup_src(self, tmp_path: Path, modules: list[str]) -> Path:
        src = tmp_path / "src"
        ext = src / "ext"
        ext.mkdir(parents=True)
        for m in modules:
            (ext / f"{m}.py").write_text("", encoding="utf-8")
        return src

    def test_flags_unmatched_ext_test(self, tmp_path):
        src_root = self._setup_src(tmp_path, ["arrow"])
        ext_tests = tmp_path / "tests" / "ext"
        ext_tests.mkdir(parents=True)
        (ext_tests / "test_arrow.py").write_text("", encoding="utf-8")
        (ext_tests / "test_typo.py").write_text("", encoding="utf-8")
        violations = _check_ext_orphans(tmp_path / "tests", src_root)
        assert len(violations) == 1
        assert "test_typo.py" in violations[0]
        assert "no matching src/remote_store/ext/typo.py" in violations[0]

    def test_allows_namespace_contract_test(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        ext_tests = tmp_path / "tests" / "ext"
        ext_tests.mkdir(parents=True)
        (ext_tests / "test_contract.py").write_text("", encoding="utf-8")
        assert _check_ext_orphans(tmp_path / "tests", src_root) == []

    def test_no_ext_dir_returns_empty(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        assert _check_ext_orphans(tmp_path / "tests", src_root) == []

    def test_main_flags_ext_violations(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        ext_tests = tmp_path / "tests" / "ext"
        ext_tests.mkdir(parents=True)
        (ext_tests / "test_orphan.py").write_text("", encoding="utf-8")
        rc = main([str(tmp_path / "tests")], src_root=src_root)
        assert rc == 1
