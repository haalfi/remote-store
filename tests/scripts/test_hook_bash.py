"""Tests for ``tests._helpers.hook_bash``, the bash the hook tests run scripts with.

Three ``tests/scripts/`` modules run repo shell scripts through it
(``test_ruff_format_hook.py``, ``test_record_decision.py``,
``test_check_readthedocs_python.py``). On Windows the system ``PATH`` puts
``System32`` first, so from a plain PowerShell shell ``shutil.which("bash")``
returned WSL's launcher, which cannot resolve a ``K:/...`` script path: ten of
those modules' tests failed that way, while passing inside a Claude Code session
whose ``PATH`` already led with Git Bash (BUG-314 review).

The Windows branch is exercised on every OS by faking ``sys.platform`` and
``shutil.which`` and building a real Git install tree under ``tmp_path``, so CI's
Linux runner pins it too.
"""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING

import pytest

from tests._helpers import hook_bash

if TYPE_CHECKING:
    from pathlib import Path

_WSL = "C:/Windows/System32/bash.exe"


def _git_install(tmp_path: Path, bash_rel: str | None) -> Path:
    """A Git for Windows layout with ``git.exe`` in ``cmd/`` and bash at *bash_rel*."""
    root = tmp_path / "Git"
    (root / "cmd").mkdir(parents=True)
    (root / "cmd" / "git.exe").write_bytes(b"")
    if bash_rel is not None:
        bash = root / bash_rel
        bash.parent.mkdir(parents=True, exist_ok=True)
        bash.write_bytes(b"")
    return root


def _fake_which(monkeypatch: pytest.MonkeyPatch, found: dict[str, str | None]) -> None:
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: found.get(name))


@pytest.mark.parametrize("launcher", [_WSL, "C:/Users/u/AppData/Local/Microsoft/WindowsApps/bash.exe"])
def test_windows_skips_the_wsl_launcher_for_git_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launcher: str
) -> None:
    root = _git_install(tmp_path, "usr/bin/bash.exe")
    monkeypatch.setattr(sys, "platform", "win32")
    _fake_which(monkeypatch, {"bash": launcher, "git": str(root / "cmd" / "git.exe")})

    assert hook_bash() == str((root / "usr/bin/bash.exe").resolve())


def test_windows_falls_back_to_the_bin_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _git_install(tmp_path, "bin/bash.exe")
    monkeypatch.setattr(sys, "platform", "win32")
    _fake_which(monkeypatch, {"bash": _WSL, "git": str(root / "cmd" / "git.exe")})

    assert hook_bash() == str((root / "bin/bash.exe").resolve())


def test_windows_keeps_a_path_bash_that_is_not_wsl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _fake_which(monkeypatch, {"bash": "F:/Coding/Git/usr/bin/bash.exe", "git": None})

    assert hook_bash() == "F:/Coding/Git/usr/bin/bash.exe"


def test_windows_without_git_bash_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _git_install(tmp_path, None)
    monkeypatch.setattr(sys, "platform", "win32")
    _fake_which(monkeypatch, {"bash": _WSL, "git": str(root / "cmd" / "git.exe")})

    assert hook_bash() is None


def test_posix_uses_path_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    _fake_which(monkeypatch, {"bash": "/usr/bin/bash"})

    assert hook_bash() == "/usr/bin/bash"
