"""Unit tests for scripts/check_rst_roles.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_rst_roles.py"

# Single backtick stored in a variable so that test fixture strings that contain
# RST-role patterns do not self-trigger the scanner when it covers tests/.
_B = "`"


def _load():
    spec = importlib.util.spec_from_file_location("check_rst_roles", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_rst_roles", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()
RST_ROLE = _mod.RST_ROLE
scan_file = _mod.scan_file
main = _mod.main

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# f-strings with _B avoid embedding a literal colon-word-colon-backtick pattern
# in the source of this file, which would self-flag when the scanner covers tests/.
_MATCH_LINES = [
    f":class:{_B}Foo{_B}",
    f":func:{_B}bar{_B}",
    f":meth:{_B}baz.qux{_B}",
    f":attr:{_B}some_attr{_B}",
    f":exc:{_B}SomeError{_B}",
    f":mod:{_B}remote_store{_B}",
    f"    See :class:{_B}Store{_B} for details.",
]

_NO_MATCH_LINES = [
    ":class:``",
    "``double backticks``",
    ":word: no backtick follows",
    "plain text only",
    "If ``True``, replace existing file.",
    ":class: space before backtick",
]


class TestRstRolePattern:
    @pytest.mark.parametrize("line", _MATCH_LINES)
    def test_matches_rst_roles(self, line):
        assert RST_ROLE.search(line)

    @pytest.mark.parametrize("line", _NO_MATCH_LINES)
    def test_no_match_for_clean_lines(self, line):
        assert not RST_ROLE.search(line)


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_violation_reported(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(
            f'def foo():\n    """:class:{_B}Foo{_B} is great."""\n',
            encoding="utf-8",
        )
        result = scan_file(f)
        assert len(result) == 1
        assert str(f) in result[0]
        assert ":2:" in result[0]

    def test_clean_file_returns_empty(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text('def foo():\n    """Clean docstring."""\n', encoding="utf-8")
        assert scan_file(f) == []

    def test_double_backtick_not_flagged(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text('"""Use :class:`` for inline code."""\n', encoding="utf-8")
        assert scan_file(f) == []

    def test_multiple_violations_all_reported(self, tmp_path):
        f = tmp_path / "multi.py"
        f.write_text(
            f":class:{_B}A{_B}\nclean line\n:func:{_B}b{_B}\n",
            encoding="utf-8",
        )
        result = scan_file(f)
        assert len(result) == 2

    def test_unreadable_file_skipped(self, tmp_path, capsys):
        f = tmp_path / "bad.py"
        f.write_bytes(b"\xff\xfe")
        result = scan_file(f)
        assert result == []
        assert "Skipping" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_clean_tree_returns_zero(self, tmp_path):
        (tmp_path / "clean.py").write_text("def foo(): pass\n", encoding="utf-8")
        assert main([str(tmp_path)]) == 0

    def test_violation_returns_one(self, tmp_path, capsys):
        (tmp_path / "bad.py").write_text(f":class:{_B}Foo{_B}\n", encoding="utf-8")
        assert main([str(tmp_path)]) == 1
        assert "RST role found" in capsys.readouterr().err

    def test_missing_directory_returns_one(self, tmp_path, capsys):
        assert main([str(tmp_path / "nonexistent")]) == 1
        assert "not found" in capsys.readouterr().err

    def test_multiple_dirs_all_scanned(self, tmp_path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        (d1 / "ok.py").write_text("def foo(): pass\n", encoding="utf-8")
        (d2 / "bad.py").write_text(f":func:{_B}bar{_B}\n", encoding="utf-8")
        assert main([str(d1), str(d2)]) == 1

    def test_real_codebase_is_clean(self):
        # Integration guard: no RST roles should exist in src/, tests/, scripts/.
        assert main() == 0
