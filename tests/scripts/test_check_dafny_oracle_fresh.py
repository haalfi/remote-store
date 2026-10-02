"""Tests for scripts/check_dafny_oracle_fresh.py (ID-263).

The real build needs dafny and takes over a minute, so the cells that reach a
build drive the script against a fake ``dafny`` executable: it answers
``--version`` and, for ``build``, records its argv and working directory, then
writes a fixture ``MemoryBackend-py/``.  That exercises everything the script
owns (pin handling, the source copy, the build command, the reorder, the
comparison) and leaves Dafny's own output to the ``verify-formal`` run against
the committed tree.  Most setup-error cells exit 2 before any dafny runs, and
the three ``test_real_wrapper_*`` cells parse the real ``scripts/dafny_translate.sh``,
so reshaping it out of the grammar turns ``tooling-tests`` red before
``verify-formal`` runs.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"

# Classes out of importable order, as Dafny emits them; reorder() moves Backend first.
RAW_MODULE = "import _dafny\n\nclass MemoryBackend(Backend):\n    pass\n\nclass Backend:\n    pass\n"
# The pin, the source copy and the build line, shaped as scripts/dafny_translate.sh writes them.
WRAPPER = (
    "#!/bin/bash\nDAFNY_VERSION=4.11.0\nDAFNY_SHA256=abc\n"
    'CMDS="$CMDS && mkdir -p /build && cp /work/*.dfy /build/ && cd /build"\n'
    "  CMDS=\"$CMDS && echo '==> Translating $f' && (/opt/dafny/dafny build -t py $f --output:$stem 2>&1"
    " | grep -v 'Unable to start python3' || true)\"\n"
)


@pytest.fixture(scope="module")
def mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import check_dafny_oracle_fresh

    return check_dafny_oracle_fresh


@pytest.fixture
def env(tmp_path: Path, mod, monkeypatch):
    """A formal dir, a pinned translate script, a fake dafny, and a build fixture."""
    formal = tmp_path / "formal"
    formal.mkdir()
    for name in ("MemoryBackend.dfy", "BackendContract.dfy", "RootPath.dfy", "ResourceSafety.dfy"):
        (formal / name).write_text(f"// {name}\n")
    translate = tmp_path / "dafny_translate.sh"
    translate.write_text(WRAPPER)

    build_out = tmp_path / "build_out"  # what the fake build writes, pre-reorder
    (build_out / "_dafny").mkdir(parents=True)
    (build_out / "module_.py").write_text(RAW_MODULE)
    (build_out / "_dafny" / "__init__.py").write_text("runtime\n")

    committed = formal / "MemoryBackend-py"
    (committed / "_dafny").mkdir(parents=True)
    from _dafny_classorder import reorder

    (committed / "module_.py").write_text(reorder(RAW_MODULE))
    (committed / "_dafny" / "__init__.py").write_text("runtime\n")

    log = tmp_path / "dafny_calls.json"
    fake = tmp_path / "dafny"
    fake.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, os, shutil, sys
            from pathlib import Path
            if sys.argv[1:] == ["--version"]:
                if os.environ.get("FAKE_DAFNY_VERSION_EXIT"):
                    print("dotnet runtime missing", file=sys.stderr)
                    sys.exit(int(os.environ["FAKE_DAFNY_VERSION_EXIT"]))
                if os.environ.get("FAKE_DAFNY_VERSION_HEX"):
                    sys.stdout.buffer.write(bytes.fromhex(os.environ["FAKE_DAFNY_VERSION_HEX"]))
                    sys.exit(0)
                print(os.environ.get("FAKE_DAFNY_VERSION", "4.11.0+deadbeef"))
                sys.exit(0)
            Path({str(log)!r}).write_text(json.dumps({{
                "argv": sys.argv[1:],
                "cwd_files": sorted(os.listdir(".")),
            }}))
            if os.environ.get("FAKE_DAFNY_WRITE", "1") == "1":
                shutil.copytree({str(build_out)!r}, "MemoryBackend-py")
            sys.exit(int(os.environ.get("FAKE_DAFNY_EXIT", "0")))
            """
        )
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    for var in (
        "FAKE_DAFNY_VERSION",
        "FAKE_DAFNY_VERSION_EXIT",
        "FAKE_DAFNY_VERSION_HEX",
        "FAKE_DAFNY_WRITE",
        "FAKE_DAFNY_EXIT",
    ):
        monkeypatch.delenv(var, raising=False)

    def run(*extra: str) -> int:
        return mod.main(
            ["--formal-dir", str(formal), "--translate-script", str(translate), "--dafny", str(fake), *extra]
        )

    return {
        "run": run,
        "formal": formal,
        "committed": committed,
        "build_out": build_out,
        "log": log,
        "translate": translate,
    }


@pytest.mark.skipif(os.name == "nt", reason="fake dafny is a shebang script")
class TestFreshness:
    def test_fresh_tree_passes(self, env, capsys):
        assert env["run"]() == 0
        assert "OK:" in capsys.readouterr().out

    def test_wrapper_build_command_runs_on_every_dfy(self, env):
        """The wrapper's build, with $f/$stem bound to the oracle, on all of sdd/formal/*.dfy."""
        env["run"]()
        call = json.loads(env["log"].read_text())
        assert call["argv"] == ["build", "-t", "py", "MemoryBackend.dfy", "--output:MemoryBackend"]
        assert call["cwd_files"] == ["BackendContract.dfy", "MemoryBackend.dfy", "ResourceSafety.dfy", "RootPath.dfy"]

    def test_build_flags_come_from_the_wrapper(self, env):
        """A flag added to the wrapper's build reaches the check, so a regenerated tree stays fresh."""
        env["translate"].write_text(WRAPPER.replace("build -t py $f", "build -t py --foo $f"))
        env["run"]()
        call = json.loads(env["log"].read_text())
        assert call["argv"] == ["build", "-t", "py", "--foo", "MemoryBackend.dfy", "--output:MemoryBackend"]

    def test_directory_matching_the_glob_exits_2(self, env, capsys):
        """The wrapper's cp exits 1 on a directory operand and aborts its chain; the check reports, not skips."""
        (env["formal"] / "notes.dfy").mkdir()
        assert env["run"]() == 2
        err = capsys.readouterr().err
        assert "notes.dfy" in err
        assert "wrapper's cp would fail" in err
        assert not env["log"].exists()

    def test_rebuilt_module_that_is_not_utf8_is_a_build_failure(self, env, capsys):
        (env["build_out"] / "module_.py").write_bytes(b"\xff\xfe not text\n")
        assert env["run"]() == 1
        assert "not UTF-8" in capsys.readouterr().out

    def test_version_output_that_is_not_utf8_is_skew_not_a_traceback(self, env, monkeypatch, capsys):
        monkeypatch.setenv("FAKE_DAFNY_VERSION_HEX", "ff342e31312e30")  # b"\xff4.11.0"
        assert env["run"]() == 1
        assert "nothing checked" in capsys.readouterr().out

    def test_environment_error_while_building_exits_2(self, env, monkeypatch, mod, capsys):
        """A copy that the OS refuses is a setup error, not a traceback read as drift."""

        def refuse(src, dst, **_):
            raise PermissionError(13, "Permission denied", str(src))

        monkeypatch.setattr(mod.shutil, "copy2", refuse)
        assert env["run"]() == 2
        assert "Permission denied" in capsys.readouterr().err

    def test_dotfiles_are_not_copied(self, env):
        """bash's `*` skips a leading dot and Path.glob's does not; the check follows bash."""
        (env["formal"] / ".scratch.dfy").write_text("// editor backup\n")
        env["run"]()
        assert ".scratch.dfy" not in json.loads(env["log"].read_text())["cwd_files"]

    def test_source_set_comes_from_the_wrapper(self, env):
        """The files copied into the build are the wrapper's `cp /work/<glob>`, not a pattern restated here."""
        env["translate"].write_text(WRAPPER.replace("cp /work/*.dfy", "cp /work/Memory*.dfy"))
        env["run"]()
        assert json.loads(env["log"].read_text())["cwd_files"] == ["MemoryBackend.dfy"]

    def test_hand_edited_module_fails_and_names_the_line(self, env, capsys):
        module = env["committed"] / "module_.py"
        module.write_text(module.read_text().replace("    pass\n", "    hacked = 1\n", 1))
        assert env["run"]() == 1
        out = capsys.readouterr().out
        assert "differs: module_.py" in out
        assert "-    hacked = 1" in out

    def test_untranslated_source_change_fails(self, env, capsys):
        """A rebuilt module that differs from the committed one is drift, whichever side moved."""
        (env["build_out"] / "module_.py").write_text(RAW_MODULE + "\nclass Extra:\n    pass\n")
        assert env["run"]() == 1
        assert "+class Extra:" in capsys.readouterr().out

    def test_reorder_is_applied_before_comparing(self, env, capsys):
        """Without the reorder the raw build output would differ from the committed file."""
        assert (env["build_out"] / "module_.py").read_text() != (env["committed"] / "module_.py").read_text()
        assert env["run"]() == 0

    def test_file_only_in_committed_tree_is_named(self, env, capsys):
        (env["committed"] / "stale.py").write_text("x\n")
        assert env["run"]() == 1
        assert "only in committed tree: stale.py" in capsys.readouterr().out

    def test_file_only_in_rebuilt_tree_is_named(self, env, capsys):
        (env["committed"] / "_dafny" / "__init__.py").unlink()
        assert env["run"]() == 1
        assert "only in rebuilt tree: _dafny/__init__.py" in capsys.readouterr().out

    def test_pycache_is_ignored(self, env):
        cache = env["committed"] / "__pycache__"
        cache.mkdir()
        (cache / "module_.cpython-312.pyc").write_bytes(b"\0")
        assert env["run"]() == 0

    def test_version_skew_fails_without_comparing(self, env, monkeypatch, capsys):
        monkeypatch.setenv("FAKE_DAFNY_VERSION", "4.12.0+cafe")
        assert env["run"]() == 1
        assert "4.12.0" in capsys.readouterr().out
        assert not env["log"].exists()

    def test_build_failure_fails(self, env, monkeypatch, capsys):
        monkeypatch.setenv("FAKE_DAFNY_EXIT", "4")
        assert env["run"]() == 1
        assert "exited 4" in capsys.readouterr().out

    def test_build_without_output_dir_fails(self, env, monkeypatch, capsys):
        monkeypatch.setenv("FAKE_DAFNY_WRITE", "0")
        assert env["run"]() == 1
        assert "wrote no MemoryBackend-py/" in capsys.readouterr().out


class TestSetupErrors:
    def test_missing_dafny_exits_2(self, env, capsys):
        assert env["run"]("--dafny", "no-such-dafny-binary") == 2
        assert "not found" in capsys.readouterr().err

    def test_unreadable_pin_exits_2(self, env, capsys):
        env["translate"].write_text("#!/bin/bash\n")
        assert env["run"]() == 2
        assert "DAFNY_VERSION" in capsys.readouterr().err

    def test_wrapper_without_build_line_exits_2(self, env, capsys):
        env["translate"].write_text("#!/bin/bash\nDAFNY_VERSION=4.11.0\n")
        assert env["run"]() == 2
        assert "dafny build" in capsys.readouterr().err

    def test_wrapper_without_source_copy_exits_2(self, env, capsys):
        env["translate"].write_text(WRAPPER.replace("cp /work/*.dfy /build/", "true"))
        assert env["run"]() == 2
        err = capsys.readouterr().err
        assert "/work/<glob>" in err
        assert "found 0" in err

    def test_wrapper_with_two_build_lines_exits_2(self, env):
        """Two invocations: which one produced the committed tree is not decidable from the text."""
        build_line = next(line for line in WRAPPER.splitlines() if "dafny build" in line)
        env["translate"].write_text(WRAPPER + build_line + "\n")
        assert env["run"]() == 2

    def test_wrapper_that_is_not_utf8_exits_2(self, env, capsys):
        env["translate"].write_bytes(WRAPPER.encode() + "# café\n".encode("latin-1"))
        assert env["run"]() == 2
        assert "cannot read" in capsys.readouterr().err

    def test_wrapper_with_two_source_copies_exits_2(self, env):
        copy_line = next(line for line in WRAPPER.splitlines() if "cp /work/" in line)
        env["translate"].write_text(WRAPPER + copy_line + "\n")
        assert env["run"]() == 2

    # Outside the allowlist grammar: each is exit 2 naming the offending token, and dafny never runs.
    @pytest.mark.parametrize(
        ("old", "new", "named"),
        [
            ("-t py $f", "-t py $EXTRA $f", "$EXTRA"),  # a variable the check cannot bind
            ("-t py $f", "-t py $file", "$file"),  # shares the `$f` prefix
            ("-t py $f", "-t py $flags $f", "$flags"),
            ("--output:$stem", "--output:$stem_out", "$stem_out"),  # shares the `$stem` prefix
            ("-t py $f", '-t py \\"$f\\"', '\\"'),  # quoting bash removes twice
            ("-t py $f", "-t py 'x $f", "'x"),  # unbalanced quote
            ("-t py $f", "-t py \\$f", "\\"),  # escaped: the wrapper's shell would not bind it
            ("--output:$stem", "--output:$stem >/build/log", ">/build/log"),  # redirection
            ("--output:$stem", "--output:$stem && true", "&&"),  # operator
            ("--output:$stem", "--output:$stem ; true", ";"),
            ("-t py $f", "-t py `echo` $f", "`echo`"),  # command substitution
            ("-t py $f", "-t py $(echo) $f", "$(echo)"),
            ("-t py $f", "-t py *.dfy", "*.dfy"),  # a glob bash expands in /build
            ("cp /work/*.dfy", "cp /work/{A,B}.dfy", "{A,B}.dfy"),  # brace expansion Path.glob lacks
            ("cp /work/*.dfy", "cp /work/'*.dfy'", "'*.dfy'"),
            ("cp /work/*.dfy", "cp /work/$GLOB", "$GLOB"),
            (
                "cp /work/*.dfy",
                "cp /work/**.dfy",
                "**.dfy",
            ),  # Path.glob reads `**` differently (raised on 3.11); bash reads `*`
            ("cp /work/*.dfy", "cp /work/.", "glob `.`"),  # whole-dir copy: not a .dfy glob
            ("cp /work/*.dfy", "cp -r /work/*", "cp [-p|-f|-v]"),  # recursion
            ("cp /work/*.dfy", "cp -S /work/*.dfy", "cp [-p|-f|-v]"),  # -S eats an operand
            ("--output:$stem 2>&1", "2>&1 --output:$stem", "dafny build"),  # words after the redirect
            # Context before the build: only `echo '<literal>'` steps may precede `&& (/opt/dafny/dafny`.
            ("&& (/opt/dafny/dafny", "&& (echo /opt/dafny/dafny", "dafny build"),  # never builds
            ("(/opt/dafny/dafny", "(DAFNY_X=1 /opt/dafny/dafny", "dafny build"),  # env prefix
            ("(/opt/dafny/dafny", "(timeout 5 /opt/dafny/dafny", "dafny build"),
            ("&& (/opt/dafny/dafny", "&& cd sub && (/opt/dafny/dafny", "dafny build"),
            ("CMDS=\"$CMDS && echo '==> Translating $f' && (", 'CMDS="$CMDS"\' && (', "dafny build"),
            # Separators: bash splits on space and tab only; other whitespace stays in the word.
            ("-t py $f", "-t py $f", "-t py"),
            ("--output:$stem 2>&1", "--output:$stem\x0b2>&1", "dafny build"),
            # Copy target: nothing may follow `/build[/]` but `&&`, `;`, `|`, `)`, `"` or the line end.
            ("/build/ && cd", "/build/ extra/ && cd", "cp [-p|-f|-v]"),
        ],
        ids=[
            "upper",
            "f-prefix",
            "f-prefix-2",
            "stem-prefix",
            "escaped-quotes",
            "unbalanced",
            "escaped-dollar",
            "redirect",
            "and-op",
            "semicolon",
            "backtick",
            "dollar-paren",
            "bare-glob",
            "brace-glob",
            "quoted-glob",
            "glob-var",
            "double-star",
            "whole-dir",
            "cp-recursive",
            "cp-flag-with-operand",
            "after-redirect",
            "echo-prefix",
            "env-prefix",
            "timeout-prefix",
            "cd-before",
            "single-quoted-piece",
            "nbsp-token",
            "vtab-before-redirect",
            "copy-extra-operand",
        ],
    )
    def test_wrapper_outside_the_grammar_exits_2(self, env, capsys, old, new, named):
        """Anything not in the grammar is a setup error, never a mangled argument that fails as drift."""
        assert old in WRAPPER
        env["translate"].write_text(WRAPPER.replace(old, new))
        assert env["run"]() == 2
        assert named in capsys.readouterr().err
        assert not env["log"].exists()

    @pytest.mark.skipif(os.name == "nt", reason="exec-format errors are POSIX")
    def test_dafny_that_cannot_be_executed_exits_2(self, env, tmp_path, capsys):
        """An executable the OS refuses to run is a setup error, not a traceback that reads as drift."""
        broken = tmp_path / "broken-dafny"
        broken.write_bytes(b"\x00\x01not a program\n")
        broken.chmod(broken.stat().st_mode | stat.S_IXUSR)
        assert env["run"]("--dafny", str(broken)) == 2
        assert "--version" in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="fake dafny is a shebang script")
    def test_dafny_that_cannot_run_exits_2_with_its_stderr(self, env, monkeypatch, capsys):
        """A broken toolchain is a setup error, not version skew."""
        monkeypatch.setenv("FAKE_DAFNY_VERSION_EXIT", "134")
        assert env["run"]() == 2
        err = capsys.readouterr().err
        assert "exited 134" in err
        assert "runtime missing" in err


# Spellings the wrapper's shell reads identically: the check must build exactly what it builds.
@pytest.mark.skipif(os.name == "nt", reason="fake dafny is a shebang script")
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("--output:$stem", "--output:${stem}"),
        ("-t py $f", "-t py ${f}"),
        ("cp /work/*.dfy /build/", "cp /work/*.dfy /build"),
        ("cp /work/*.dfy", "cp -p /work/*.dfy"),
    ],
    ids=["braced-stem", "braced-f", "build-no-slash", "cp-flag"],
)
def test_equivalent_wrapper_spellings_build_the_same(env, old, new):
    assert old in WRAPPER
    env["translate"].write_text(WRAPPER.replace(old, new))
    assert env["run"]() == 0
    call = json.loads(env["log"].read_text())
    assert call["argv"] == ["build", "-t", "py", "MemoryBackend.dfy", "--output:MemoryBackend"]
    assert call["cwd_files"] == ["BackendContract.dfy", "MemoryBackend.dfy", "ResourceSafety.dfy", "RootPath.dfy"]


def test_real_wrapper_carries_a_readable_pin(mod):
    """Renaming the wrapper's DAFNY_VERSION= line would turn the CI step into a setup error."""
    pin = mod.read_pin(SCRIPTS / "dafny_translate.sh")
    assert pin is not None
    assert pin.count(".") == 2


def test_real_wrapper_source_copy_parses(mod):
    assert mod.read_source_glob(SCRIPTS / "dafny_translate.sh") == "*.dfy"


def test_real_wrapper_build_line_parses(mod):
    """Reshaping the wrapper's build line must keep it readable, or the CI step becomes a setup error."""
    assert mod.read_build_args(SCRIPTS / "dafny_translate.sh") == [
        "build",
        "-t",
        "py",
        "MemoryBackend.dfy",
        "--output:MemoryBackend",
    ]
