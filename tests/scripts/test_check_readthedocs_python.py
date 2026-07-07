"""The repo's .readthedocs.yaml must build docs on the primary Python."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "check_readthedocs_python.py"
_GEN_SCRIPT = _ROOT / "scripts" / "docs" / "gen_llms_api.sh"


def _load():
    spec = importlib.util.spec_from_file_location("check_readthedocs_python", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_readthedocs_python", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_repo_config_is_consistent():
    assert _load().check() is None


def _post_build_commands() -> list[str]:
    cfg = yaml.safe_load((_ROOT / ".readthedocs.yaml").read_text(encoding="utf-8"))
    return cfg["build"]["jobs"].get("post_build", [])


def test_post_build_commands_are_single_line():
    """No post_build command may contain an embedded newline.

    BUG-226: an inline ``>-`` folded YAML scalar with an over-indented
    continuation line folded to a *multi-line* string whose second line began
    with ``|``. RTD runs post_build under ``/bin/sh`` (dash), which aborted with
    a parse error *before* the intended ``|| echo`` non-fatal guard could run,
    reddening the whole docs build. A newline surviving into the parsed command
    is the fingerprint of that mis-fold. Keep post_build commands as single-line
    scalars; put any multi-step logic in a committed script and call it.
    """
    for cmd in _post_build_commands():
        assert "\n" not in cmd, f"post_build command spans multiple lines (BUG-226 mis-fold): {cmd!r}"


def test_post_build_scripts_exist_and_parse():
    """Every ``bash <script>`` invoked from post_build must exist and parse.

    RTD has no way to surface a syntax error in a build script except by failing
    the build, so validate it here where a break is a cheap red test instead.
    """
    bash = shutil.which("bash")
    for cmd in _post_build_commands():
        parts = cmd.split()
        if len(parts) >= 2 and parts[0] == "bash":
            script = _ROOT / parts[1]
            assert script.is_file(), f"post_build calls missing script: {parts[1]}"
            if bash is None:
                pytest.skip("bash unavailable; cannot syntax-check the script")
            result = subprocess.run(  # noqa: S603
                [bash, "-n", str(script)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"{parts[1]} failed `bash -n`:\n{result.stderr}"


def _run_gen_script(bash: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [bash, str(_GEN_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=_ROOT,
    )


def _gen_script_bash_or_skip() -> str:
    if not _GEN_SCRIPT.is_file():
        pytest.skip("gen_llms_api.sh absent")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable; cannot run the script")
    return bash


def test_gen_llms_api_is_non_fatal_when_env_unset():
    """gen_llms_api.sh exits 0 on the ``READTHEDOCS_OUTPUT``-unset short-circuit.

    BUG-226's essence was not the YAML fold per se — it was that a failure path
    became *fatal* and reddened the whole docs build. This covers the *first*
    guard specifically: with ``READTHEDOCS_OUTPUT`` unset the script returns via
    ``skip`` before any network step. The sibling test below reaches a *later*
    skip branch; together they assert the non-fatal ``exit 0`` funnel on two
    distinct paths. The network paths (curl/lx) and the happy path need the RTD
    fetch env, so they stay a post-deploy check rather than a unit test.
    """
    bash = _gen_script_bash_or_skip()
    env = {k: v for k, v in os.environ.items() if k != "READTHEDOCS_OUTPUT"}
    result = _run_gen_script(bash, env)
    assert result.returncode == 0, (
        f"gen_llms_api.sh must be non-fatal (exit 0) on the env-unset path, got {result.returncode}:\n{result.stderr}"
    )


def test_gen_llms_api_is_non_fatal_when_a_post_guard_step_fails(tmp_path):
    """A failure *after* the env guard must still exit 0, not just the first path.

    Reachable offline without stubbing the network: set ``READTHEDOCS_OUTPUT``
    (so the first guard passes) but point ``PATH`` at an empty directory, so the
    first external command the script runs — ``mkdir`` at the install-dir step —
    is not found and its ``|| skip`` fires. This directly regression-tests the
    concern behind BUG-226: a dropped ``|| skip`` on a post-guard step would let
    a failure escape as a non-zero exit and red the build. The reviewer's
    ``mv``-fails variant is not hermetic (``mv`` runs only after curl+lx, which
    need the network); the ``mkdir`` branch is the offline-reachable analog.
    """
    bash = _gen_script_bash_or_skip()
    empty_dir = tmp_path / "no-tools-on-path"
    empty_dir.mkdir()
    env = {**os.environ, "READTHEDOCS_OUTPUT": str(tmp_path), "PATH": str(empty_dir)}
    result = _run_gen_script(bash, env)
    assert result.returncode == 0, (
        f"gen_llms_api.sh must be non-fatal (exit 0) when a post-guard step fails, "
        f"got {result.returncode}:\n{result.stderr}"
    )
    assert "skipped" in result.stderr, f"expected a skip() on a post-guard branch, got:\n{result.stderr or '(empty)'}"
