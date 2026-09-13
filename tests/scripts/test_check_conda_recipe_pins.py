"""Unit tests for scripts/check_conda_recipe_pins.py.

The seeded discrepancies are the ones that actually happened. ``pyarrow`` at
``>=12.0.0`` against an ``s3-pyarrow`` extra needing ``>=14.0.0`` is the live
drift a conda-forge reviewer caught on ``staged-recipes#32401``; ``paramiko`` is
the same shape one package over. If the gate stops catching these it has decayed
back into the comment it replaced.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_conda_recipe_pins.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_conda_recipe_pins", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_conda_recipe_pins", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()

_PYPROJECT = """\
[project]
name = "remote-store"

[project.optional-dependencies]
s3 = ["s3fs>=2024.2.0"]
s3-pyarrow = ["s3fs>=2024.2.0", "pyarrow>=14.0.0"]
arrow = ["pyarrow>=12.0.0"]
sftp = ["paramiko>=3.1"]
httpx = ["httpx>=0.24.0,<1.0"]
toml = ["tomli>=1.1.0; python_version < '3.11'"]
bench = ["remote-store[s3-pyarrow]", "matplotlib>=3.8"]
dev = ["remote-store[s3,sftp]", "pytest"]
"""

# Matches _PYPROJECT: strictest floor per package, dev/bench extras excluded.
_RECIPE = """\
requirements:
  run:
    - python >=3.10
  run_constraints:
    # A comment inside the block is skipped.
    - s3fs >=2024.2.0
    - pyarrow >=14.0.0
    - paramiko >=3.1
    - httpx >=0.24.0,<1.0
    - tomli >=1.1.0

tests:
  - python:
      imports:
        - remote_store
"""


def _tree(tmp_path: Path, *, pyproject: str = _PYPROJECT, recipe: str = _RECIPE) -> Path:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    recipe_path = tmp_path / "packaging" / "conda-forge"
    recipe_path.mkdir(parents=True)
    (recipe_path / "recipe.yaml").write_text(recipe, encoding="utf-8")
    return tmp_path


class TestAgreement:
    def test_matching_tree_is_clean(self, tmp_path):
        assert _mod.collect_violations(_tree(tmp_path)) == []

    def test_repo_itself_is_clean(self):
        """The gate's whole point: the shipped recipe agrees with the shipped extras."""
        assert _mod.collect_violations(_REPO_ROOT) == []

    def test_equivalent_spellings_compare_equal(self, tmp_path):
        """`>=14.0.0` and `>=14.0.0` written differently are one specifier, not two."""
        tree = _tree(tmp_path, recipe=_RECIPE.replace("pyarrow >=14.0.0", "pyarrow >= 14.0.0"))
        assert _mod.collect_violations(tree) == []


class TestSeededDiscrepancies:
    """One per failure mode the gate claims to catch."""

    def test_weaker_floor_than_the_strictest_extra(self, tmp_path):
        """The live drift: pyarrow pinned at the `arrow` floor, not `s3-pyarrow`'s."""
        tree = _tree(tmp_path, recipe=_RECIPE.replace("pyarrow >=14.0.0", "pyarrow >=12.0.0"))
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["pyarrow"]
        assert ">=12.0.0" in violations[0].reason
        assert ">=14.0.0" in violations[0].reason

    def test_missing_entry(self, tmp_path):
        tree = _tree(tmp_path, recipe=_RECIPE.replace("    - paramiko >=3.1\n", ""))
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["paramiko"]
        assert "absent from run_constraints" in violations[0].reason

    def test_stray_entry(self, tmp_path):
        """A package no user-facing extra declares. `pytest` is dev-only."""
        tree = _tree(tmp_path, recipe=_RECIPE.replace("    - tomli", "    - pytest >=8.0\n    - tomli"))
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["pytest"]
        assert "no user-facing extra declares it" in violations[0].reason

    def test_dropped_ceiling(self, tmp_path):
        """An upper bound in pyproject that the recipe does not carry."""
        tree = _tree(tmp_path, recipe=_RECIPE.replace("httpx >=0.24.0,<1.0", "httpx >=0.24.0"))
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["httpx"]
        assert "<1.0" in violations[0].reason

    def test_marker_gated_dependency_is_still_required(self, tmp_path):
        """`tomli` is marker-gated in pyproject; conda has no marker, so it is required."""
        tree = _tree(tmp_path, recipe=_RECIPE.replace("    - tomli >=1.1.0\n", ""))
        assert [v.package for v in _mod.collect_violations(tree)] == ["tomli"]


class TestParsing:
    def test_block_ends_at_dedent(self, tmp_path):
        """`tests:` follows the block; its entries must not be read as constraints."""
        parsed = _mod.recipe_constraints(_tree(tmp_path) / "packaging" / "conda-forge" / "recipe.yaml")
        assert set(parsed) == {"s3fs", "pyarrow", "paramiko", "httpx", "tomli"}

    def test_self_referential_extras_are_not_followed(self, tmp_path):
        """`remote-store[...]` aggregates; it is never itself a constraint."""
        declared = _mod.declared_constraints(_tree(tmp_path) / "pyproject.toml")
        assert "remote-store" not in declared

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("azure_storage_file_datalake", "azure-storage-file-datalake"), ("MSAL", "msal")],
    )
    def test_names_normalise(self, name, expected):
        assert _mod._canonical(name) == expected


class TestExitCode:
    def test_clean_tree_exits_zero(self, tmp_path, capsys):
        assert _mod.main(["--repo-root", str(_tree(tmp_path))]) == 0

    def test_dirty_tree_exits_one_and_localises(self, tmp_path, capsys):
        tree = _tree(tmp_path, recipe=_RECIPE.replace("pyarrow >=14.0.0", "pyarrow >=12.0.0"))
        assert _mod.main(["--repo-root", str(tree)]) == 1
        err = capsys.readouterr().err
        assert "pyarrow" in err
        assert "pyproject.toml governs" in err
