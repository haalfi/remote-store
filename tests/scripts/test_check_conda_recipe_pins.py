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
requires-python = ">=3.10"

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


_VARIANTS = """\
# Comment above the value, as the real file has.
python_min:
  - "3.10"
"""

_CI = """\
      - name: Resolve Python versions
        env:
          ALL_PYTHONS: '["3.10", "3.11"]'
          MIN_PYTHON: "3.10"
"""


def _tree(
    tmp_path: Path,
    *,
    pyproject: str = _PYPROJECT,
    recipe: str = _RECIPE,
    variants: str = _VARIANTS,
    ci: str = _CI,
) -> Path:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    recipe_path = tmp_path / "packaging" / "conda-forge"
    recipe_path.mkdir(parents=True)
    (recipe_path / "recipe.yaml").write_text(recipe, encoding="utf-8")
    (recipe_path / "variants.yaml").write_text(variants, encoding="utf-8")
    ci_path = tmp_path / ".github" / "workflows"
    ci_path.mkdir(parents=True)
    (ci_path / "ci.yml").write_text(ci, encoding="utf-8")
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


class TestUnsupportedOperators:
    """A clause the collapse cannot express must be reported, never folded.

    Folding `>1.2` into `>=1.2` made the gate demand a weaker pin than declared
    and fail the recipe for carrying the correct one — the inverse of its own
    authority rule. None of these is live today; that is why they need a test.
    """

    @pytest.mark.parametrize("clause", [">3.1", "==3.1", "~=3.1", "!=3.1", "==3.1.*"])
    def test_reported_not_collapsed(self, tmp_path, clause):
        tree = _tree(tmp_path, pyproject=_PYPROJECT.replace("paramiko>=3.1", f"paramiko{clause}"))
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["paramiko"]
        assert "does not collapse" in violations[0].reason

    def test_wildcard_does_not_raise_invalidversion(self, tmp_path):
        """`==1.2.*` reached `Version()` and crashed before it was rejected."""
        tree = _tree(tmp_path, pyproject=_PYPROJECT.replace("paramiko>=3.1", "paramiko==3.1.*"))
        assert _mod.collect_violations(tree)  # a violation, not a traceback


class TestIrreconcilableExtras:
    """Floor and ceiling come from different extras and need not be compatible."""

    def test_crossing_bounds_are_reported_not_demanded(self, tmp_path):
        # s3-pyarrow keeps >=14.0.0; arrow gains a <13 cap. The collapse is
        # `>=14.0.0,<13`, which SpecifierSet accepts and nothing satisfies.
        tree = _tree(
            tmp_path, pyproject=_PYPROJECT.replace('arrow = ["pyarrow>=12.0.0"]', 'arrow = ["pyarrow>=12.0.0,<13"]')
        )
        violations = _mod.collect_violations(tree)
        assert [v.package for v in violations] == ["pyarrow"]
        assert "no version satisfies" in violations[0].reason
        assert "fix pyproject, not the recipe" in violations[0].reason

    def test_touching_bounds_are_irreconcilable_too(self, tmp_path):
        """`>=13,<13` is empty as surely as `>=14,<13`."""
        tree = _tree(
            tmp_path, pyproject=_PYPROJECT.replace('arrow = ["pyarrow>=12.0.0"]', 'arrow = ["pyarrow>=12.0.0,<14.0.0"]')
        )
        assert "no version satisfies" in _mod.collect_violations(tree)[0].reason


class TestPythonMin:
    """requires-python governs; variants.yaml and ci.yml restate it."""

    def test_agreement_is_clean(self, tmp_path):
        assert _mod.python_min_violations(_tree(tmp_path)) == []

    def test_repo_itself_agrees(self):
        assert _mod.python_min_violations(_REPO_ROOT) == []

    def test_variants_drift_is_caught(self, tmp_path):
        tree = _tree(tmp_path, variants=_VARIANTS.replace('"3.10"', '"3.11"'))
        violations = _mod.python_min_violations(tree)
        assert [v.package for v in violations] == ["python_min"]
        assert "variants.yaml" in violations[0].reason

    def test_ci_drift_is_caught(self, tmp_path):
        tree = _tree(tmp_path, ci=_CI.replace('MIN_PYTHON: "3.10"', 'MIN_PYTHON: "3.11"'))
        violations = _mod.python_min_violations(tree)
        assert [v.package for v in violations] == ["python_min"]
        assert "MIN_PYTHON" in violations[0].reason

    def test_requires_python_bump_flags_both_restatements(self, tmp_path):
        """The realistic direction: the floor rises and the two copies lag."""
        tree = _tree(tmp_path, pyproject=_PYPROJECT.replace('">=3.10"', '">=3.12"'))
        assert len(_mod.python_min_violations(tree)) == 2

    def test_missing_python_min_is_a_violation(self, tmp_path):
        tree = _tree(tmp_path, variants="python_min:\n")
        assert "declares no python_min" in _mod.python_min_violations(tree)[0].reason

    def test_lookup_is_anchored_to_its_key(self, tmp_path):
        """A variant config holds several keys; an unanchored search reads the wrong one.

        With `numpy` listed above, an unanchored regex matches `1.26` and
        compares *that* against requires-python — passing while python_min is
        wrong, or failing while naming a value that is not python_min at all.
        """
        variants = 'numpy:\n  - "1.26"\npython_min:\n  - "3.10"\n'
        assert _mod.python_min_violations(_tree(tmp_path, variants=variants)) == []

    def test_anchored_lookup_still_sees_a_wrong_value_below_another_key(self, tmp_path):
        variants = 'numpy:\n  - "1.26"\npython_min:\n  - "3.12"\n'
        violations = _mod.python_min_violations(_tree(tmp_path, variants=variants))
        assert [v.package for v in violations] == ["python_min"]
        assert "'3.12'" in violations[0].reason


class TestParsing:
    def test_trailing_yaml_comment_is_stripped(self, tmp_path):
        """Reading the block textually makes comment syntax this parser's job.

        Without the strip, `>=14.0.0  # shared` becomes `>=14.0.0#shared` and
        SpecifierSet raises InvalidSpecifier — an uncaught traceback out of
        `lint` and `docs-gate` rather than a reported recipe problem. This is
        the most comment-dense block in the recipe, so a trailing one is a
        normal thing for the next editor to write.
        """
        recipe = _RECIPE.replace("- pyarrow >=14.0.0", "- pyarrow >=14.0.0  # three extras share this")
        tree = _tree(tmp_path, recipe=recipe)
        parsed = _mod.recipe_constraints(tree / "packaging" / "conda-forge" / "recipe.yaml")
        assert str(parsed["pyarrow"]) == ">=14.0.0"
        assert _mod.collect_violations(tree) == []

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
