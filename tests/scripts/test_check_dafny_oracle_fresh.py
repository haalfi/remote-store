"""Tests for scripts/check_dafny_oracle_fresh.py (ID-263).

The real build needs dafny and takes over a minute, so every cell drives the
script against a fake ``dafny`` executable: it answers ``--version`` and, for
``build``, records its argv and working directory, then writes a fixture
``MemoryBackend-py/``.  That exercises everything the script owns (pin
handling, the source copy, the build command, the reorder, the comparison)
and leaves Dafny's own output to the ``verify-formal`` run against the
committed tree.
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
    translate.write_text("#!/bin/bash\nDAFNY_VERSION=4.11.0\nDAFNY_SHA256=abc\n")

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
    for var in ("FAKE_DAFNY_VERSION", "FAKE_DAFNY_WRITE", "FAKE_DAFNY_EXIT"):
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

    def test_build_command_matches_the_wrapper_and_sees_every_dfy(self, env):
        """The verifying build, on all of sdd/formal/*.dfy, never --no-verify."""
        env["run"]()
        call = json.loads(env["log"].read_text())
        assert call["argv"] == ["build", "-t", "py", "MemoryBackend.dfy", "--output:MemoryBackend"]
        assert call["cwd_files"] == ["BackendContract.dfy", "MemoryBackend.dfy", "ResourceSafety.dfy", "RootPath.dfy"]

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


def test_real_wrapper_carries_a_readable_pin(mod):
    """Renaming the wrapper's DAFNY_VERSION= line would turn the CI step into a setup error."""
    pin = mod.read_pin(SCRIPTS / "dafny_translate.sh")
    assert pin is not None
    assert pin.count(".") == 2
