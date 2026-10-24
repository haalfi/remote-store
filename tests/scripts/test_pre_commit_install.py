"""``scripts/pre_commit_install.py`` installs beside the agent gates' ``core.hooksPath`` (BK-486).

Plain ``pre-commit install`` refuses while ``core.hooksPath`` is set; the
script blanks it for that one process. A stub ``pre-commit`` on ``PATH`` stands
in for the framework and reports the override it was given, so what the real
framework does with it (install into ``.git/hooks``, measured once by hand) is
not exercised here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pre_commit_install.py"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stub is a POSIX shell script")


def test_runs_pre_commit_install_with_core_hooks_path_blanked(tmp_path: Path) -> None:
    stub = tmp_path / "pre-commit"
    stub.write_text(
        '#!/bin/sh\necho "args=$* count=$GIT_CONFIG_COUNT key=$GIT_CONFIG_KEY_0 value=[$GIT_CONFIG_VALUE_0]"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--overwrite"], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "args=install --overwrite count=1 key=core.hooksPath value=[]"


def test_returns_the_frameworks_exit_code(tmp_path: Path) -> None:
    stub = tmp_path / "pre-commit"
    stub.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, check=False)

    assert result.returncode == 3
