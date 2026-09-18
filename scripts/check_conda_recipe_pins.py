"""Gate: the conda recipe's ``run_constraints`` agree with pyproject's extras.

``packaging/conda-forge/recipe.yaml`` restates every optional dependency
``pyproject.toml`` declares, because conda has no extras: there is one package
rather than a family of opt-in ones, nothing optional is installed with it, and
a ``run_constraints`` entry is the only thing that keeps a user who installs
``pyarrow`` or ``paramiko`` alongside it from pairing remote-store with a
version it does not work with. The recipe said so in a comment -- "keep this exhaustive ... the ones
nobody enumerates are the ones that drift" -- and nothing enforced it.
``.github/workflows/conda-recipe.yml`` runs ``rattler-build --render-only``,
which validates syntax and never reads ``pyproject.toml``.

It drifted, and the conda-forge reviewer on ``staged-recipes#32401`` is who
caught it: ``pyarrow`` sat at ``>=12.0.0`` while the ``s3-pyarrow`` extra needed
``>=14.0.0``. That review does not recur -- staged-recipes is a one-time
submission -- so this gate is what replaces the reviewer (BK-368).

Wired into ``hatch run lint`` **and** ``hatch run docs-gate``. Both, because the
pair straddles CI's two classifiers: ``pyproject.toml`` is in ``CODE_PAT`` and
the recipe is in ``DOCS_PAT``, so a gate in only one of them is unreachable for
exactly half the diffs that can invalidate it -- and the recipe half is the one
this gate was built for. ``scripts/gen_backlogid.py`` documents the
mirror image of the same trap.

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
* **Only ``>=``, ``<`` and ``<=`` are understood.** Every other PEP 440
  operator -- ``>``, ``==``, ``~=``, ``!=``, ``===`` and any wildcard such as
  ``==1.2.*`` -- is **reported, not collapsed**. An earlier spelling folded them
  into ``>=`` silently, which meant a pyproject ``pkg>1.2`` made this gate demand
  the recipe carry the *weaker* ``>=1.2`` and fail it for carrying the correct
  ``>1.2`` -- inverting the authority rule above. No user-facing extra uses one
  today, so this fires on the day someone writes one rather than producing a
  confidently wrong expectation.
* The collapse takes its floor and its ceiling **independently across extras**,
  so they need not be compatible: ``s3-pyarrow`` at ``>=14`` beside an ``arrow``
  capped ``<13`` yields ``>=14,<13``, which ``SpecifierSet`` accepts and no
  version satisfies. That is reported as an irreconcilable disagreement between
  the extras rather than as a recipe violation, because the recipe is not the
  side that can be fixed.
* The ``run_constraints`` block is read textually, so **YAML comment handling is
  this parser's job**: a whole-line comment is skipped and a trailing one is
  stripped at the first ``#``. A ``#`` inside a quoted version string would be
  mis-stripped; no such spelling is valid in a conda constraint.

The python_min pair
===================

A second, smaller pair rides here rather than in its own script, because it has
the same two files and the same wiring problem. ``recipe.yaml`` deliberately does
**not** define ``python_min`` (conda-forge supplies it globally), so
``packaging/conda-forge/variants.yaml`` supplies it for our own render. That
value has to equal the floor of ``requires-python``, and ``ci.yml``'s
``MIN_PYTHON`` has to equal it too. Nothing compared the three; a divergence
leaves ``rattler-build --render-only`` green while rendering a recipe for an
interpreter the package no longer supports.

Exit codes
==========

* ``0`` -- every user-facing dependency is constrained, at the strictest floor,
  and the three ``python_min`` spellings agree.
* ``1`` -- one or more disagreements (one line each to stderr, plus remediation).

Drift-gate::

    kind:       pair
    compares:   packaging/conda-forge/recipe.yaml run_constraints ↔ pyproject.toml
        [project.optional-dependencies]; and packaging/conda-forge/variants.yaml python_min
        ↔ pyproject.toml requires-python ↔ .github/workflows/ci.yml MIN_PYTHON
    domain:     intent ↔ realization
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
_VARIANTS = Path("packaging/conda-forge/variants.yaml")
_CI = Path(".github/workflows/ci.yml")

# A run_constraints entry: "- name >=1.2,<2".  Conda spells the separator with a
# space and joins clauses with "," exactly as PEP 440 does.
_ENTRY_RE = re.compile(r"^\s*-\s+(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<spec>[<>=!~].*)?$")

# The only operators this gate can collapse without changing what a pin means.
# Everything else is reported -- see the Bounds section.
_LOWER_OPS = frozenset({">="})
_UPPER_OPS = frozenset({"<", "<="})
_SUPPORTED_OPS = _LOWER_OPS | _UPPER_OPS


class UnsupportedSpecifier(Exception):
    """A pyproject clause this gate refuses to guess at. Carries the package."""

    def __init__(self, package: str, clause: str) -> None:
        super().__init__(f"{package}: {clause}")
        self.package = package
        self.clause = clause


class IrreconcilableExtras(Exception):
    """Two extras bound the same package so that nothing satisfies both."""

    def __init__(self, package: str, collapsed: str) -> None:
        super().__init__(f"{package}: {collapsed}")
        self.package = package
        self.collapsed = collapsed


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

    return {name: _collapse(specs, package=name) for name, specs in per_package.items()}


def _collapse(specs: list[SpecifierSet], *, package: str = "?") -> SpecifierSet:
    clauses = [c for spec in specs for c in spec]
    for clause in clauses:
        # Refuse rather than guess. Folding `>`, `==` or `~=` into `>=` changes
        # what the pin means, and `!=` / `===` would vanish entirely -- making
        # the gate demand a recipe entry that is wrong. See Bounds.
        if clause.operator not in _SUPPORTED_OPS:
            raise UnsupportedSpecifier(package, str(clause))
    lower = [c for c in clauses if c.operator in _LOWER_OPS]
    upper = [c for c in clauses if c.operator in _UPPER_OPS]

    out: list[str] = []
    floor: Version | None = None
    ceiling: Version | None = None
    if lower:
        strictest = max(lower, key=lambda c: Version(c.version))
        floor = Version(strictest.version)
        out.append(str(Specifier(f">={strictest.version}")))
    if upper:
        strictest = min(upper, key=lambda c: Version(c.version))
        ceiling = Version(strictest.version)
        out.append(str(strictest))
    # The bounds can come from *different* extras, and nothing requires them to
    # be compatible: `s3-pyarrow` at >=14 beside an `arrow` capped <13 collapses
    # to `>=14,<13`, which SpecifierSet accepts and no version satisfies. The
    # gate would then name an impossible target and tell the author to edit the
    # recipe to match it -- advice that cannot be followed, on a pair where the
    # recipe is not the side that is wrong.
    if floor is not None and ceiling is not None and floor >= ceiling:
        raise IrreconcilableExtras(package, ",".join(out))
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
            # Strip a trailing YAML comment before parsing. Reading the block
            # textually makes comment syntax this parser's job, and this is the
            # most comment-dense region of the recipe: without it
            # `- pyarrow >=14.0.0  # shared` becomes `>=14.0.0#shared` and
            # SpecifierSet raises InvalidSpecifier, so the gate dies with a
            # traceback instead of reporting a recipe problem.
            spec_text = (m["spec"] or "").split("#", 1)[0]
            out[_canonical(m["name"])] = SpecifierSet(spec_text.replace(" ", ""))
    return out


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #


def python_min_violations(repo_root: Path = _REPO_ROOT) -> list[Violation]:
    """The three spellings of the minimum Python must agree. See the docstring.

    `requires-python` governs; `variants.yaml` and `ci.yml`'s `MIN_PYTHON`
    restate it. Absence of either restatement is a violation too — a missing
    `python_min` is what makes `rattler-build --render-only` fail on an
    undefined variable, and a missing `MIN_PYTHON` would silently drop a matrix
    leg.
    """
    data = tomllib.loads((repo_root / _PYPROJECT).read_text(encoding="utf-8"))
    floor = SpecifierSet(data["project"]["requires-python"])
    lower = [c for c in floor if c.operator in _LOWER_OPS]
    if len(lower) != 1:
        return [Violation("python_min", f"requires-python {str(floor)!r} has no single '>=' floor to compare against")]
    want = lower[0].version

    out: list[Violation] = []

    # Anchored to the `python_min:` key, not "the first list item in the file".
    # A variant config exists to hold several keys, so an unanchored search
    # starts comparing a `numpy` or compiler pin against requires-python the
    # moment one is added above this one — and passes while python_min is wrong.
    variants = (repo_root / _VARIANTS).read_text(encoding="utf-8")
    found = re.search(
        r'^python_min:[^\S\n]*\n(?:[^\S\n]*#[^\n]*\n)*[^\S\n]*-[^\S\n]*["\']?(?P<v>\d+\.\d+)["\']?[^\S\n]*$',
        variants,
        re.MULTILINE,
    )
    if found is None:
        out.append(Violation("python_min", f"{_VARIANTS} declares no python_min value"))
    elif found["v"] != want:
        out.append(Violation("python_min", f"{_VARIANTS} says {found['v']!r}, requires-python floor is {want!r}"))

    ci = (repo_root / _CI).read_text(encoding="utf-8")
    ci_min = re.search(r'^\s*MIN_PYTHON:\s*["\']?(?P<v>\d+\.\d+)["\']?\s*$', ci, re.MULTILINE)
    if ci_min is None:
        out.append(Violation("python_min", f"{_CI} declares no MIN_PYTHON"))
    elif ci_min["v"] != want:
        out.append(Violation("python_min", f"{_CI} MIN_PYTHON is {ci_min['v']!r}, requires-python floor is {want!r}"))

    return out


def collect_violations(repo_root: Path = _REPO_ROOT) -> list[Violation]:
    try:
        declared = declared_constraints(repo_root / _PYPROJECT)
    except UnsupportedSpecifier as exc:
        return [
            Violation(
                exc.package,
                f"pyproject clause {exc.clause!r} uses an operator this gate does not collapse "
                f"(only >=, < and <= are understood); express it as those, or widen _collapse",
            )
        ]
    except IrreconcilableExtras as exc:
        return [
            Violation(
                exc.package,
                f"the extras bound it to {exc.collapsed!r}, which no version satisfies — "
                f"they disagree irreconcilably, so no recipe entry can be right; "
                f"fix pyproject, not the recipe",
            )
        ]
    present = recipe_constraints(repo_root / _RECIPE)

    out: list[Violation] = python_min_violations(repo_root)
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
    "the strictest surface does not have). Then run `hatch run gen-conda-feedstock`: the shipped "
    "copy beside it is generated, and this gate's sibling fails on a stale one."
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
        print(
            "check_conda_recipe_pins: run_constraints agree with pyproject's extras; "
            "python_min agrees in all three files."
        )
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
