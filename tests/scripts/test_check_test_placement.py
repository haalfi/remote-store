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
_discover_banned_backend_names = _mod._discover_banned_backend_names
_BANNED_BACKEND_NAMES = _mod._BANNED_BACKEND_NAMES
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
        # ``grandfathered=frozenset()`` opts out of stale-entry detection;
        # we're testing rule S in isolation here, not rule B's grandfather
        # tracking. Synthetic trees lack the grandfathered legacy files
        # entirely, so the real grandfather list would otherwise fire as "stale".
        assert main([str(tmp_path)], grandfathered=frozenset()) == 0

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
        # See note above: opt out of grandfather tracking on a synthetic tree.
        assert main([str(tmp_path)], grandfathered=frozenset()) == 0


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

_STAR_IMPORT_PUBLIC = """\
from remote_store.backends import *  # noqa: F403

def test_star():
    pass
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

    def test_flags_wildcard_import_from_public_namespace(self, tmp_path):
        # ``from remote_store.backends import *`` could pull in any
        # banned class; flag unconditionally regardless of whether the
        # banned set knows specific names. Bypass-prevention.
        f = tmp_path / "test_at_root.py"
        f.write_text(_STAR_IMPORT_PUBLIC, encoding="utf-8")
        violations = _check_backend_imports_at_root(f)
        assert len(violations) == 1
        assert "wildcard import" in violations[0]
        assert "remote_store.backends" in violations[0]

    def test_banned_names_parameter_overrides_module_global(self, tmp_path):
        # Rule B's banned roster must be drivable per-call so synthetic
        # ``src_root`` trees in tests can pin the public-namespace branch
        # without fighting the module-global computed at import.
        f = tmp_path / "test_at_root.py"
        f.write_text(
            "from remote_store.backends import FakeBackend\n",
            encoding="utf-8",
        )
        # With the synthetic banned set, the import is flagged.
        violations = _check_backend_imports_at_root(f, banned_names=frozenset({"FakeBackend"}))
        assert len(violations) == 1
        assert "FakeBackend" in violations[0]
        # With the empty banned set, the same import is clean.
        assert _check_backend_imports_at_root(f, banned_names=frozenset()) == []

    def test_main_flags_new_root_violation(self, tmp_path):
        bad = tmp_path / "test_new_module.py"
        bad.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        rc = main([str(tmp_path)], src_root=tmp_path / "missing_src")
        assert rc == 1

    def test_main_scans_top_level_aio_test_async_files(self, tmp_path):
        # tests/aio/test_async_*.py is the async analog of top-level
        # tests/test_*.py and must be subject to Rule B per spec 048
        # TEST-010 + TEST-003. Async ext-module tests under tests/aio/ext/
        # are governed by Rule E; async backend-specific tests live under
        # tests/backends/<backend>/aio/ per TEST-010 (not under
        # tests/aio/backends/, which the spec does not define).
        aio = tmp_path / "aio"
        aio.mkdir()
        bad = aio / "test_async_misplaced.py"
        bad.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        rc = main([str(tmp_path)], src_root=tmp_path / "missing_src", grandfathered=frozenset())
        assert rc == 1

    def test_main_does_not_scan_tests_aio_ext(self, tmp_path):
        # tests/aio/ext/ is governed by Rule E (async branch), not
        # Rule B. A banned-import file there must not trigger Rule B;
        # the async-ext orphan check (Rule E) is satisfied by pairing
        # the test with src/remote_store/aio/ext/<x>.py.
        ext_dir = tmp_path / "aio" / "ext"
        ext_dir.mkdir(parents=True)
        f = ext_dir / "test_async_foo.py"
        f.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        # Synthetic src must include both ext trees so neither Rule E
        # branch fires; the test isolates Rule B's (non-)scan behaviour.
        src = tmp_path / "src"
        (src / "ext").mkdir(parents=True)
        (src / "aio" / "ext").mkdir(parents=True)
        (src / "aio" / "ext" / "foo.py").write_text("", encoding="utf-8")
        rc = main([str(tmp_path)], src_root=src, grandfathered=frozenset())
        assert rc == 0


# ---------------------------------------------------------------------------
# Stale grandfather entry detection
# ---------------------------------------------------------------------------


class TestStaleGrandfatherDetection:
    """The grandfather list (``_BACKEND_AT_ROOT_GRANDFATHERED``) is a
    transitional measure (BK-191). Entries whose underlying file no longer
    violates Rule B are dead weight; the script self-prunes by reporting
    them as stale so the list shrinks monotonically.
    """

    def test_main_reports_stale_entry_when_file_absent(self, tmp_path):
        # No grandfathered files exist in the tmp tree → all entries
        # in the supplied grandfather set are stale.
        rc = main(
            [str(tmp_path)],
            src_root=tmp_path / "fake",
            grandfathered=frozenset({"test_legacy.py"}),
        )
        assert rc == 1

    def test_main_reports_stale_entry_when_file_clean(self, tmp_path):
        # File exists but doesn't violate → still stale.
        clean = tmp_path / "test_legacy.py"
        clean.write_text("def test_clean(): assert True\n", encoding="utf-8")
        rc = main(
            [str(tmp_path)],
            src_root=tmp_path / "fake",
            grandfathered=frozenset({"test_legacy.py"}),
        )
        assert rc == 1

    def test_main_clean_when_grandfathered_file_actually_violates(self, tmp_path):
        # Grandfathered file exists and DOES violate → grandfather skip
        # applies → no Rule B violation surfaces, and the entry is *not*
        # stale (it fired). Use a private-path import (no banned_names
        # required) to drive the check via the synthetic src.
        violating = tmp_path / "test_legacy.py"
        violating.write_text(_AZURE_AT_ROOT, encoding="utf-8")
        rc = main(
            [str(tmp_path)],
            src_root=tmp_path / "fake",
            grandfathered=frozenset({"test_legacy.py"}),
        )
        assert rc == 0


# ---------------------------------------------------------------------------
# Banned-backend discovery (Rule B's ground truth)
# ---------------------------------------------------------------------------


class TestDiscoverBannedBackendNames:
    """``_discover_banned_backend_names`` is the SSoT for Rule B's class
    roster; the previous hand-maintained ``_BANNED_BACKEND_NAMES`` constant
    drifted whenever a new backend landed.
    """

    def test_includes_known_concrete_backends(self):
        # A representative sample — the function returns whatever currently
        # exists under src/, so any new backend joins automatically.
        assert "S3Backend" in _BANNED_BACKEND_NAMES
        assert "AzureBackend" in _BANNED_BACKEND_NAMES
        assert "SFTPBackend" in _BANNED_BACKEND_NAMES

    def test_excludes_in_process_backends(self):
        assert "MemoryBackend" not in _BANNED_BACKEND_NAMES
        assert "LocalBackend" not in _BANNED_BACKEND_NAMES

    def test_excludes_async_in_process_backends(self):
        # ``aio/backends/_memory.py`` is excluded because its file stem
        # (``_memory``) is in ``_ALLOWED_BACKEND_MODULES``; the async sibling
        # gets the same allow-list treatment as the sync one.
        assert "AsyncMemoryBackend" not in _BANNED_BACKEND_NAMES

    def test_synthetic_src_tree_returns_only_backend_classes(self, tmp_path: Path) -> None:
        # Build a minimal fake src tree to pin the static-AST contract:
        # one banned class, one allowed module, one helper class with a
        # non-Backend suffix.
        src = tmp_path / "remote_store"
        backends = src / "backends"
        backends.mkdir(parents=True)
        (backends / "_fake_cloud.py").write_text(
            "class FakeCloudBackend:\n    pass\n\nclass FakeCloudOptions:\n    pass\n",
            encoding="utf-8",
        )
        (backends / "_memory.py").write_text(
            "class FakeMemoryBackend:\n    pass\n",
            encoding="utf-8",
        )
        result = _discover_banned_backend_names(src)
        assert result == frozenset({"FakeCloudBackend"})

    def test_handles_missing_src_tree(self, tmp_path: Path) -> None:
        # When src doesn't exist (e.g., script run outside the repo), the
        # function returns an empty set rather than raising.
        result = _discover_banned_backend_names(tmp_path / "nonexistent")
        assert result == frozenset()


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

    def test_flags_root_aio_test_async_ext_prefix(self, tmp_path):
        # tests/aio/test_async_ext_*.py is the async analog of the banned
        # sync prefix. Per the TEST-010 1:1 invariant, the canonical home
        # is tests/aio/ext/test_async_<x>.py.
        aio = tmp_path / "aio"
        aio.mkdir()
        bad = aio / "test_async_ext_foo.py"
        bad.write_text("def test_x(): assert True\n", encoding="utf-8")
        violations = _check_root_ext_naming(tmp_path)
        assert len(violations) == 1
        assert "test_async_ext_foo.py" in violations[0]
        assert "tests/aio/ext/test_async_foo.py" in violations[0]

    def test_clean_root_returns_empty(self, tmp_path):
        (tmp_path / "test_seekable.py").write_text("", encoding="utf-8")
        # An aio sibling without the banned prefix is also clean.
        aio = tmp_path / "aio"
        aio.mkdir()
        (aio / "test_async_drift.py").write_text("", encoding="utf-8")
        assert _check_root_ext_naming(tmp_path) == []


class TestExtOrphans:
    def _setup_src(self, tmp_path: Path, modules: list[str], async_modules: list[str] | None = None) -> Path:
        src = tmp_path / "src"
        ext = src / "ext"
        ext.mkdir(parents=True)
        for m in modules:
            (ext / f"{m}.py").write_text("", encoding="utf-8")
        if async_modules:
            aio_ext = src / "aio" / "ext"
            aio_ext.mkdir(parents=True)
            for m in async_modules:
                (aio_ext / f"{m}.py").write_text("", encoding="utf-8")
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

    def test_flags_unmatched_async_ext_test(self, tmp_path):
        # tests/aio/ext/test_async_<x>.py without
        # src/remote_store/aio/ext/<x>.py is the async analog of the
        # sync orphan check. Pinned by the TEST-010 1:1 invariant.
        src_root = self._setup_src(tmp_path, [], async_modules=["write"])
        aio_ext_tests = tmp_path / "tests" / "aio" / "ext"
        aio_ext_tests.mkdir(parents=True)
        (aio_ext_tests / "test_async_write.py").write_text("", encoding="utf-8")
        (aio_ext_tests / "test_async_typo.py").write_text("", encoding="utf-8")
        violations = _check_ext_orphans(tmp_path / "tests", src_root)
        assert len(violations) == 1
        assert "test_async_typo.py" in violations[0]
        assert "no matching src/remote_store/aio/ext/typo.py" in violations[0]

    def test_allows_namespace_contract_test(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        ext_tests = tmp_path / "tests" / "ext"
        ext_tests.mkdir(parents=True)
        (ext_tests / "test_contract.py").write_text("", encoding="utf-8")
        assert _check_ext_orphans(tmp_path / "tests", src_root) == []

    def test_no_ext_dir_returns_empty(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        assert _check_ext_orphans(tmp_path / "tests", src_root) == []

    def test_async_ext_pairing_passes(self, tmp_path):
        # Positive: a properly paired async ext test does not violate.
        src_root = self._setup_src(tmp_path, [], async_modules=["write"])
        aio_ext_tests = tmp_path / "tests" / "aio" / "ext"
        aio_ext_tests.mkdir(parents=True)
        (aio_ext_tests / "test_async_write.py").write_text("", encoding="utf-8")
        assert _check_ext_orphans(tmp_path / "tests", src_root) == []

    def test_main_flags_ext_violations(self, tmp_path):
        src_root = self._setup_src(tmp_path, [])
        ext_tests = tmp_path / "tests" / "ext"
        ext_tests.mkdir(parents=True)
        (ext_tests / "test_orphan.py").write_text("", encoding="utf-8")
        rc = main([str(tmp_path / "tests")], src_root=src_root)
        assert rc == 1

    def test_main_flags_async_ext_violations(self, tmp_path):
        # End-to-end: the rule fires from main() for both async-ext
        # asymmetries (Rule E (a) ban + Rule E (b) orphan).
        src_root = self._setup_src(tmp_path, [], async_modules=[])
        aio_ext_tests = tmp_path / "tests" / "aio" / "ext"
        aio_ext_tests.mkdir(parents=True)
        (aio_ext_tests / "test_async_orphan.py").write_text("", encoding="utf-8")
        rc = main([str(tmp_path / "tests")], src_root=src_root, grandfathered=frozenset())
        assert rc == 1
