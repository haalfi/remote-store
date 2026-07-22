"""Assert ci-full.yml's ``test-full`` matrix equals ci.yml's ``ALL_PYTHONS``.

The supported-interpreter matrix is single-sourced conceptually but has two
executable copies: ci.yml's ``setup`` job env ``ALL_PYTHONS`` (a JSON array,
validated against ``.python-version``) and ci-full.yml's ``test-full`` matrix
``python-version`` list. If someone adds or drops an interpreter in ci.yml but
misses ci-full.yml, the full-matrix backstop silently narrows with no signal.
This gate keeps the copies honest by comparing the two sets. Wired into
``hatch run lint``. A malformed workflow raises here, which is itself a lint
failure. (BK-319)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_CI_FULL = _ROOT / ".github" / "workflows" / "ci-full.yml"

# `on` is a YAML 1.1 boolean keyword, so PyYAML's safe_load parses a workflow's
# top-level `on:` mapping key as the Python bool ``True`` rather than "on". Job
# lookups below key into ``jobs``, not ``on``, but the same load reads both keys,
# so a workflow that leans on `on:` stays parseable regardless.


def _all_pythons(ci: Path) -> set[str]:
    """Return the set of interpreters in ci.yml's ``ALL_PYTHONS`` env (JSON array)."""
    data = yaml.safe_load(ci.read_text(encoding="utf-8"))
    raw = data["jobs"]["setup"]["steps"]
    for step in raw:
        env = step.get("env") if isinstance(step, dict) else None
        if isinstance(env, dict) and "ALL_PYTHONS" in env:
            return {str(v) for v in json.loads(env["ALL_PYTHONS"])}
    raise KeyError(f"no step with an ALL_PYTHONS env found in {ci.name} setup job")


def _test_full_matrix(ci_full: Path) -> set[str]:
    """Return the set of interpreters in ci-full.yml's ``test-full`` matrix."""
    data = yaml.safe_load(ci_full.read_text(encoding="utf-8"))
    versions = data["jobs"]["test-full"]["strategy"]["matrix"]["python-version"]
    return {str(v) for v in versions}


def check(ci: Path = _CI, ci_full: Path = _CI_FULL) -> str | None:
    """Return an error message if the two interpreter sets disagree, else ``None``."""
    all_pythons = _all_pythons(ci)
    matrix = _test_full_matrix(ci_full)
    if all_pythons != matrix:
        return (
            f"{ci_full.name} test-full matrix python-version {sorted(matrix)} does not "
            f"match {ci.name} ALL_PYTHONS {sorted(all_pythons)} "
            f"(only in {ci.name}: {sorted(all_pythons - matrix)}; "
            f"only in {ci_full.name}: {sorted(matrix - all_pythons)})"
        )
    return None


if __name__ == "__main__":
    error = check()
    if error:
        sys.exit(f"error: {error}")
