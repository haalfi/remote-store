"""Unit tests for scripts/check_repo_traps.py (BK-444).

Every invisible character below is built with ``chr()``: a four-digit unicode
escape in a tool parameter decodes into the raw character, which is the very
trap rule 1 exists to catch, and this file would then fail its own gate.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_repo_traps.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_repo_traps", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_repo_traps", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()

LS = chr(0x2028)
NBSP = chr(0x00A0)
ZWSP = chr(0x200B)
BOM = chr(0xFEFF)

# The 21 code points of sdd/backlog/bk-444-repo-traps-lint.md Plan step 1, plus
# the three directional marks its dated departure note adds (U+061C, U+200E, U+200F).
_PLANNED_CODE_POINTS = (
    (0x0000, 0x0008, 0x001A, 0x001B, 0x00A0, 0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029)
    + tuple(range(0x202A, 0x202F))
    + (0x2060,)
    + tuple(range(0x2066, 0x206A))
    + (0xFEFF,)
)


# ---------------------------------------------------------------------------
# Rule 1: invisible characters
# ---------------------------------------------------------------------------


class TestScanInvisible:
    def test_clean_text_passes(self):
        assert _mod.scan_invisible("x = 1\ny = '×–é'\n", "a.py") == []

    def test_line_separator_reported_with_position_and_named_escape(self):
        [v] = _mod.scan_invisible(f"a = 1\nb = 'x{LS}y'\n", "t.py")
        assert v.location == "t.py:2:7"
        assert "U+2028 LINE SEPARATOR" in v.message
        assert "\\N{LINE SEPARATOR}" in v.message

    def test_non_python_file_is_not_told_to_use_a_python_escape(self):
        # `\N{…}` is an escape only in a Python string; in Markdown it is literal text.
        [v] = _mod.scan_invisible(f"a{NBSP}b\n", "docs/page.md")
        assert "U+00A0 NO-BREAK SPACE" in v.message
        assert "\\N{" not in v.message
        assert "remove it" in v.message

    def test_line_numbers_after_a_line_separator_are_not_shifted(self):
        # str.splitlines would split on U+2028 and report the NBSP on line 3.
        found = _mod.scan_invisible(f"a{LS}b\nc{NBSP}\n", "t.py")
        assert [v.location for v in found] == ["t.py:1:2", "t.py:2:2"]

    @pytest.mark.parametrize("code_point", _PLANNED_CODE_POINTS)
    def test_every_planned_code_point_is_refused(self, code_point):
        [v] = _mod.scan_invisible(f"s = '{chr(code_point)}'", "t.py")
        assert f"U+{code_point:04X}" in v.message

    def test_refused_set_is_exactly_the_planned_one(self):
        # A literal, not the module's dict: dropping or adding a code point must
        # change this test too, so the set cannot narrow while the gate passes.
        assert set(_mod._INVISIBLE) == set(_PLANNED_CODE_POINTS)

    @pytest.mark.parametrize("code_point", [0x0000, 0x0008, 0x001A, 0x001B])
    def test_c0_control_names_are_valid_python_escapes(self, code_point):
        name = _mod._name(code_point)
        assert eval(f'"\\N{{{name}}}"') == chr(code_point)

    def test_leading_bom_is_refused(self):
        [v] = _mod.scan_invisible(f"{BOM}x = 1\n", "t.py")
        assert v.location == "t.py:1:1"

    def test_named_escape_text_is_not_a_hit(self):
        assert _mod.scan_invisible('s = "\\N{ZERO WIDTH SPACE}"\n', "t.py") == []


def _git(tmp_path: Path, attributes: str = "", *, ignorecase: bool = False) -> Path:
    """A scratch repo, so binary detection runs through git check-attr as in the gate."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    # Pinned, not inherited: git defaults it per platform (true on Windows).
    subprocess.run(["git", "config", "core.ignorecase", str(ignorecase).lower()], cwd=tmp_path, check=True)
    if attributes:
        (tmp_path / ".gitattributes").write_text(attributes, encoding="utf-8")
    return tmp_path


def _write(root: Path, *rels: str) -> None:
    for rel in rels:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(f"x{ZWSP}\n", encoding="utf-8")


class TestCheckInvisible:
    def test_binary_pattern_and_non_utf8_files_are_skipped(self, tmp_path):
        root = _git(tmp_path, "* text=auto eol=lf\n*.png binary\n")
        (root / "img").mkdir()
        (root / "img" / "a.png").write_bytes(f"x{ZWSP}".encode())
        (root / "latin.txt").write_bytes(b"caf\xe9")
        (root / "bad.md").write_text(f"x{ZWSP}\n", encoding="utf-8")
        found = _mod.check_invisible(root, ["img/a.png", "latin.txt", "bad.md", "gone.py"])
        assert [v.location for v in found] == ["bad.md:1:2"]

    def test_decision_logs_are_skipped(self, tmp_path):
        # record_decision.py stores dialog payloads as received (ensure_ascii=False).
        root = _git(tmp_path)
        (root / "sdd" / "decisions").mkdir(parents=True)
        (root / "sdd" / "decisions" / "s.jsonl").write_text(f'{{"q": "a{LS}b"}}\n', encoding="utf-8")
        (root / "sdd" / "notes.md").write_text(f"a{LS}b\n", encoding="utf-8")
        found = _mod.check_invisible(root, ["sdd/decisions/s.jsonl", "sdd/notes.md"])
        assert [v.location for v in found] == ["sdd/notes.md:1:2"]

    @pytest.mark.parametrize(
        ("pattern", "skipped", "scanned"),
        [
            ("assets/*.svg", "assets/x.svg", "assets/icons/x.svg"),  # `*` does not cross `/`
            ("/assets/*.svg", "assets/x.svg", "sub/assets/x.svg"),  # anchored at the root
            ("**/gen/*.bin", "gen/a.bin", "gen/sub/a.bin"),  # `**/` also matches the root
            ("data/**", "data/sub/a.txt", "other/data/a.txt"),
            ("*.[!t]xt", "a.bxt", "a.txt"),  # git negates with `!`
            ("*.[[:digit:]]", "a.1", "a.x"),
        ],
        ids=[
            "star-stays-in-segment",
            "leading-slash",
            "double-star-prefix",
            "double-star-suffix",
            "bang-negates",
            "posix-class",
        ],
    )
    def test_patterns_match_as_git_does(self, tmp_path, pattern, skipped, scanned):
        root = _git(tmp_path, f"{pattern} binary\n")
        _write(root, skipped, scanned)
        found = _mod.check_invisible(root, [skipped, scanned])
        assert [v.location for v in found] == [f"{scanned}:1:2"]

    def test_nested_gitattributes_is_honoured(self, tmp_path):
        root = _git(tmp_path)
        (root / "sub").mkdir()
        (root / "sub" / ".gitattributes").write_text("*.dat binary\n", encoding="utf-8")
        _write(root, "sub/x.dat", "x.dat")
        found = _mod.check_invisible(root, ["sub/x.dat", "x.dat"])
        assert [v.location for v in found] == ["x.dat:1:2"]

    @pytest.mark.parametrize(("ignorecase", "reported"), [(True, []), (False, ["LOGO.PNG:1:2"])])
    def test_case_folding_follows_core_ignorecase(self, tmp_path, ignorecase, reported):
        root = _git(tmp_path, "*.png binary\n", ignorecase=ignorecase)
        _write(root, "LOGO.PNG")
        assert [v.location for v in _mod.check_invisible(root, ["LOGO.PNG"])] == reported

    def test_minus_text_alone_is_still_scanned(self, tmp_path):
        # Only the `binary` macro skips a file; `-text` leaves it readable as text.
        root = _git(tmp_path, "*.raw -text\n")
        _write(root, "a.raw")
        assert [v.location for v in _mod.check_invisible(root, ["a.raw"])] == ["a.raw:1:2"]

    def test_no_files_needs_no_git(self, tmp_path):
        assert _mod.binary_files(tmp_path, []) == set()

    def test_listed_files_includes_untracked_and_excludes_ignored(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (tmp_path / "tracked.py").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
        (tmp_path / "new.py").write_text("x\n", encoding="utf-8")
        (tmp_path / "ignored.txt").write_text("x\n", encoding="utf-8")
        assert _mod.listed_files(tmp_path) == [".gitignore", "new.py", "tracked.py"]


# ---------------------------------------------------------------------------
# Rule 2: write_text without newline=
# ---------------------------------------------------------------------------


class TestScanWriteText:
    def test_call_with_newline_keyword_passes(self):
        src = 'p.write_text(s, encoding="utf-8", newline="\\n")\n'
        assert _mod.scan_write_text(src, "s.py") == []

    def test_call_without_newline_fails_with_line(self):
        [v] = _mod.scan_write_text('x = 1\np.write_text(s, encoding="utf-8")\n', "s.py")
        assert v.location == "s.py:2"
        assert "newline=" in v.message

    def test_one_line_content_is_still_flagged(self):
        # No allowlist: the rule never guesses what the content holds.
        assert len(_mod.scan_write_text('p.write_text("{}", encoding="utf-8")\n', "s.py")) == 1

    @pytest.mark.parametrize(
        "src",
        [
            'p.write_text(s, "utf-8", None, "\\n")\n',
            "p.write_text(s, **kw)\n",
            'p.write_text(s, newline="")\n',
            "p.write_text(s, newline=nl)\n",
        ],
        ids=["fourth-positional", "double-star", "empty-string", "non-constant-is-a-bound"],
    )
    def test_newline_passed_another_way_is_accepted(self, src):
        assert _mod.scan_write_text(src, "s.py") == []

    @pytest.mark.parametrize(
        "src",
        [
            "p.write_text(s, newline=None)\n",
            'p.write_text(s, newline="\\r\\n")\n',
            'p.write_text(s, "utf-8", None, None)\n',
        ],
        ids=["none-is-the-default", "crlf", "fourth-positional-none"],
    )
    def test_newline_that_still_writes_crlf_fails(self, src):
        [v] = _mod.scan_write_text(src, "s.py")
        assert v.location == "s.py:1"

    @pytest.mark.parametrize(
        "src",
        ['open(p, "w").write(s)\n', 'p.open("w").write(s)\n', "write_text(s)\n", "p.write_bytes(b)\n"],
        ids=["open", "path-open", "bare-name", "write-bytes"],
    )
    def test_stated_bounds_are_not_checked(self, src):
        assert _mod.scan_write_text(src, "s.py") == []

    def test_unparsable_source_is_reported_not_raised(self):
        # A raw NBSP between tokens is rule 1's subject; rule 2 must not crash on it.
        [v] = _mod.scan_write_text(f"x = 1{NBSP}+ 2\n", "s.py")
        assert v.location == "s.py:1"
        assert "does not parse" in v.message


class TestCheckWriteText:
    def test_reads_scripts_only(self, tmp_path):
        (tmp_path / "scripts" / "sub").mkdir(parents=True)
        (tmp_path / "sdd").mkdir()
        bad = 'p.write_text(s, encoding="utf-8")\n'
        (tmp_path / "scripts" / "sub" / "g.py").write_text(bad, encoding="utf-8")
        (tmp_path / "sdd" / "h.py").write_text(bad, encoding="utf-8")
        assert [v.location for v in _mod.check_write_text(tmp_path)] == ["scripts/sub/g.py:1"]

    def test_non_utf8_script_is_reported_not_raised(self, tmp_path):
        # A cp1252 save (an `é` in a comment) must not crash the gate.
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "w.py").write_bytes(b"# caf\xe9\n")
        [v] = _mod.check_write_text(tmp_path)
        assert v.location == "scripts/w.py"
        assert "not UTF-8" in v.message


# ---------------------------------------------------------------------------
# Rule 3: hatch alias without {args}
# ---------------------------------------------------------------------------


class TestTakesOptions:
    @pytest.mark.parametrize(
        "src",
        [
            "import argparse\nargparse.ArgumentParser().add_argument('--x')\n",
            "import sys\nmain(sys.argv[1:])\n",
            "import sys\nx = sys.argv[1]\n",
        ],
        ids=["add-argument", "argv-slice", "argv-index"],
    )
    def test_detects_options(self, src):
        assert _mod.takes_options(src)

    @pytest.mark.parametrize(
        "src",
        ["print('hi')\n", "import sys\nprint(sys.argv)\n", "argv = [1]\nargv[0]\n"],
        ids=["none", "whole-argv-is-a-bound", "other-argv"],
    )
    def test_no_options(self, src):
        assert not _mod.takes_options(src)


def _repo(tmp_path: Path, scripts: str, *, takes: bool = True) -> Path:
    (tmp_path / "scripts").mkdir()
    body = "import sys\nmain(sys.argv[1:])\n" if takes else "print('hi')\n"
    (tmp_path / "scripts" / "x.py").write_text(body, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(scripts, encoding="utf-8")
    return tmp_path


class TestCheckHatchArgs:
    def test_alias_forwarding_args_passes(self, tmp_path):
        root = _repo(tmp_path, '[tool.hatch.envs.default.scripts]\nx = "python scripts/x.py {args}"\n')
        assert _mod.check_hatch_args(root) == []

    def test_alias_dropping_args_fails_naming_env_and_alias(self, tmp_path):
        root = _repo(tmp_path, '[tool.hatch.envs.docs.scripts]\nx = "python scripts/x.py"\n')
        [v] = _mod.check_hatch_args(root)
        assert v.location == "pyproject.toml [tool.hatch.envs.docs.scripts] x"
        assert "scripts/x.py" in v.message

    def test_unparsable_script_is_reported_not_raised(self, tmp_path):
        root = _repo(tmp_path, '[tool.hatch.envs.default.scripts]\nx = "python scripts/x.py"\n')
        (root / "scripts" / "x.py").write_text(f"x = 1{NBSP}+ 2\n", encoding="utf-8")
        [v] = _mod.check_hatch_args(root)
        assert v.location == "pyproject.toml [tool.hatch.envs.default.scripts] x"
        assert "does not parse" in v.message

    def test_script_without_options_needs_no_args(self, tmp_path):
        root = _repo(tmp_path, '[tool.hatch.envs.default.scripts]\nx = "python scripts/x.py"\n', takes=False)
        assert _mod.check_hatch_args(root) == []

    @pytest.mark.parametrize(
        "entry",
        [
            '"python scripts/x.py --check"',
            '["python scripts/x.py"]',
            '"python scripts/x.py && ruff check"',
            '"pytest scripts/x.py"',
        ],
        ids=["pinned-argument", "array-form", "several-commands", "other-runner"],
    )
    def test_entries_outside_the_bare_shape_are_exempt(self, tmp_path, entry):
        root = _repo(tmp_path, f"[tool.hatch.envs.default.scripts]\nx = {entry}\n")
        assert _mod.check_hatch_args(root) == []

    def test_alias_to_a_missing_script_is_reported(self, tmp_path):
        # A typo or a rename leaves an alias that fails at `hatch run` time.
        root = _repo(tmp_path, '[tool.hatch.envs.default.scripts]\nx = "python scripts/missing.py"\n')
        [v] = _mod.check_hatch_args(root)
        assert v.location == "pyproject.toml [tool.hatch.envs.default.scripts] x"
        assert "scripts/missing.py does not exist" in v.message


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_each_rule_reports_and_fails(self, tmp_path, capsys):
        root = _repo(tmp_path, '[tool.hatch.envs.default.scripts]\nx = "python scripts/x.py"\n')
        (root / "scripts" / "w.py").write_text(f'p.write_text("{NBSP}", encoding="utf-8")\n', encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        assert _mod.main(root) == 1
        err = capsys.readouterr().err
        assert "1 invisible characters found" in err
        assert "1 write_text that can write CRLF found" in err
        assert "1 hatch alias without {args} found" in err

    def test_unparsable_script_still_gets_rule_1_report(self, tmp_path, capsys):
        root = _repo(tmp_path, "[tool.hatch.envs.default.scripts]\n")
        (root / "scripts" / "bad.py").write_text(f"x = 1{NBSP}+ 2\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        assert _mod.main(root) == 1
        err = capsys.readouterr().err
        assert "scripts/bad.py:1:6: U+00A0 NO-BREAK SPACE" in err
        assert "scripts/bad.py:1: does not parse" in err

    def test_real_repo_is_clean(self, capsys):
        assert _mod.main() == 0, capsys.readouterr().err
