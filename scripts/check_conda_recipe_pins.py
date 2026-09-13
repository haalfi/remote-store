"""Gate: the conda recipe's ``run_constraints`` agree with pyproject's extras.

``packaging/conda-forge/recipe.yaml`` restates every optional dependency
``pyproject.toml`` declares, because conda has no extras: the package installs
whole, and a ``run_constraints`` entry is the only thing that keeps a user from
pairing remote-store with a version of ``pyarrow`` or ``paramiko`` it does not
work with. The recipe said so in a comment -- "keep this exhaustive ... the ones
nobody enumerates are the ones that drift" -- and nothing enforced it.
``.github/workflows/conda-recipe.yml`` runs ``rattler-build --render-only``,
which validates syntax and never reads ``pyproject.toml``.

It drifted, and the conda-forge reviewer on ``staged-recipes#32401`` is who
caught it: ``pyarrow`` sat at ``>=12.0.0`` while the ``s3-pyarrow`` extra needed
``>=14.0.0``. That review does not recur -- staged-recipes is a one-time
submission -- so this gate is what replaces the reviewer (BK-368).

Authority (Rule 4)
==================

``pyproject.toml`` governs; the recipe restates. A disagreement is always the
recipe's to fix. The one transformation the recipe is licensed to make is the
**strictest-floor collapse**: conda allows one pin per package where pyproject
may declare a package under several extras at different floors, so the recipe
carries the strictest bound of the set. It never carries a weaker one, because a
``run_constraints`` entry asserts compatibility and the weakest floor asserts it
for a surface that does not have it.

What is checked
===============

Per package named by any user-facing extra (the extras
``gen_features._EXCLUDE_EXTRAS`` leaves out are dev/build tooling and are not
shipped to conda users):

* **Present.** A package pyproject declares has a ``run_constraints`` entry.
* **No strays.** A ``run_constraints`` entry names a package some extra declares.
* **Equal to the strictest.** The entry's specifier equals the collapse of every
  declaration of that package: the greatest lower bound, plus the least upper
  bound when any extra caps.

Bounds (Rule 7)
===============

* Reads ``[project.optional-dependencies]`` only. ``[project.dependencies]``,
  the recipe's ``host`` / ``run`` sections, ``build``, ``tests`` and ``about``
  are outside the enumeration; so is the ``source`` sha256.
* **Environment markers are dropped**, matching what the recipe already does for
  ``tomli ... python_version < '3.11'``: conda has no per-Python marker at this
  position, so a marker-gated dependency is required here unconditionally. A
  marker that made a dependency genuinely inapplicable would therefore be
  mis-required, and no such case exists today.
* Self-referential requirements (``remote-store[...]``) are skipped, not
  followed. Every extra they aggregate is enumerated on its own.
* It compares two *declarations*. It does not check that either floor is
  **right** -- that a version actually carries the API the code uses. That is
  what ``tests/scripts/test_pyproject_pins.py`` does, per package, and it does
  not generalise.
* Version equality is exact after normalisation: ``>=12.0.0`` and ``>=12`` are
  different strings but the same ``SpecifierSet``, and compare equal.

Exit codes
==========

* ``0`` -- every user-facing dependency is constrained, at the strictest floor.
* ``1`` -- one or more disagreements (one line each to stderr, plus remediation).

Drift-gate::

    kind:       pair
    compares:   packaging/conda-forge/recipe.yaml run_constraints <-> pyproject.toml
        [project.optional-dependencies]
    domain:     intent <-> realization
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover — py3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_features import _EXCLUDE_EXTRAS  # noqa: E402  — single source for the dev/build extras

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RECIPE = Path("packaging/conda-forge/recipe.yaml")
_PYPROJECT = Path("pyproject.toml")

# A run_constraints entry: "- name >=1.2,<2".  Conda spells the separator with a
# space and joins clauses with "," exactly as PEP 440 does.
_ENTRY_RE = re.compile(r"^\s*-\s+(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<spec>[<>=!~].*)?$")

_LOWER_OPS = frozenset({">=", ">", "==", "~="})
_UPPER_OPS = frozenset({"<", "<="})


def _canonical(name: str) -> str:
    """PEP 503 name normalisation; conda and PyPI spell separators differently."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Violation:
    package: str
    reason: str


# --------------------------------------------------------------------------- #
# pyproject side
# --------------------------------------------------------------------------- #


def declared_constraints(pyproject: Path) -> dict[str, SpecifierSet]:
    """Strictest specifier per package across every user-facing extra.

    The collapse the recipe is licensed to make: greatest lower bound, least
    upper bound. A package declared with no specifier at all collapses to an
    empty `SpecifierSet`, which the recipe must then also leave unconstrained.
    """
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extras: dict[str, list[str]] = data["project"]["optional-dependencies"]

    per_package: dict[str, list[SpecifierSet]] = {}
    for extra, reqs in extras.items():
        if extra in _EXCLUDE_EXTRAS:
            continue
        for raw in reqs:
            req = Requirement(raw)
            if _canonical(req.name) == "remote-store":
                continue  # aggregate of other extras; each is enumerated already
            per_package.setdefault(_canonical(req.name), []).append(req.specifier)

    return {name: _collapse(specs) for name, specs in per_package.items()}


def _collapse(specs: list[SpecifierSet]) -> SpecifierSet:
    clauses = [c for spec in specs for c in spec]
    lower = [c for c in clauses if c.operator in _LOWER_OPS]
    upper = [c for c in clauses if c.operator in _UPPER_OPS]

    out: list[str] = []
    if lower:
        strictest = max(lower, key=lambda c: Version(c.version))
        out.append(str(Specifier(f">={strictest.version}")))
    if upper:
        strictest = min(upper, key=lambda c: Version(c.version))
        out.append(str(strictest))
    return SpecifierSet(",".join(out))


# --------------------------------------------------------------------------- #
# recipe side
# --------------------------------------------------------------------------- #


def recipe_constraints(recipe: Path) -> dict[str, SpecifierSet]:
    """Parse the ``run_constraints:`` block into package -> specifier.

    Read textually rather than through a YAML loader: the recipe carries
    ``${{ }}`` template expressions elsewhere in the file, and this block is a
    flat list whose shape a loader adds nothing to.
    """
    out: dict[str, SpecifierSet] = {}
    inside = False
    indent = 0
    for line in recipe.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not inside:
            if stripped.startswith("run_constraints:"):
                inside = True
                indent = len(line) - len(line.lstrip())
            continue
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break  # dedent ends the block
        m = _ENTRY_RE.match(line)
        if m:
            out[_canonical(m["name"])] = SpecifierSet((m["spec"] or "").replace(" ", ""))
    return out


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def collect_violations(repo_root: Path = _REPO_ROOT) -> list[Violation]:
    declared = declared_constraints(repo_root / _PYPROJECT)
    present = recipe_constraints(repo_root / _RECIPE)

    out: list[Violation] = []
    for name in sorted(set(declared) | set(present)):
        want = declared.get(name)
        have = present.get(name)
        if want is None:
            out.append(Violation(name, f"constrained as {str(have)!r} but no user-facing extra declares it"))
        elif have is None:
            out.append(Violation(name, f"declared by an extra as {str(want)!r} but absent from run_constraints"))
        elif set(have) != set(want):
            out.append(Violation(name, f"recipe says {str(have)!r}, extras collapse to {str(want)!r}"))
    return out


_REMEDIATION = (
    "pyproject.toml governs. Edit packaging/conda-forge/recipe.yaml's run_constraints to match: "
    "one entry per package any user-facing extra declares, carrying the strictest floor across "
    "those extras (conda allows one pin per package, and a weaker floor asserts a compatibility "
    "the strictest surface does not have)."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT,
        help="Repository root (default: the checkout this script lives in).",
    )
    args = parser.parse_args(argv)

    violations = collect_violations(args.repo_root)
    if not violations:
        print("check_conda_recipe_pins: run_constraints agree with pyproject's extras.")
        return 0

    for v in violations:
        print(f"{_RECIPE}: {v.package}: {v.reason}", file=sys.stderr)
    print(
        f"\ncheck_conda_recipe_pins: {len(violations)} package(s) disagree.",
        file=sys.stderr,
    )
    print(_REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
