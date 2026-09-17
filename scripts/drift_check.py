"""ID-182: Scheduled CI drift guard for unbounded extra-dependency floors.

Resolves each ``remote-store[<extra>]`` against the latest available
transitive versions (including pre-releases) and diffs the resolution
against a committed baseline in ``infra/drift-locks/``. The scheduled
workflow that drives this lives at ``.github/workflows/drift-guard.yml``.

The script depends only on the standard library on Python 3.11+
(``tomllib`` is stdlib). On Python 3.10 the ``tomli`` package is required
— ``[dev]`` brings it in for local development, and the workflow runs on
Python 3.13 so CI is not affected. A standalone 3.10 invocation needs
``pip install tomli`` first.

Subcommands:

* ``extras``            — list testable extras (JSON array on stdout).
* ``resolve <extra>``   — install ``remote-store[<extra>]`` in a fresh
                           venv with ``--upgrade --pre`` and emit the
                           pinned set on stdout.
* ``diff <extra>``      — call ``resolve`` and diff against the baseline
                           in ``infra/drift-locks/<extra>.txt``. Emits a
                           JSON report on stdout. ``--emit-freeze PATH``
                           also writes the (single) resolved freeze so the
                           smoke and candidate baseline reuse it.
* ``floor <extra>``     — resolve ``remote-store[<extra>]`` at the floor of
                           every range it declares (``uv pip install
                           --resolution lowest-direct``) and emit a JSON
                           report. ``--emit-freeze PATH`` writes the resolved
                           freeze for the smoke to pin against.
* ``min-python``        — print the oldest interpreter ``requires-python``
                           admits; the floor lane runs there.
* ``refresh-baseline    — overwrite ``infra/drift-locks/<extra>.txt`` with
   <extra>``              a fresh resolution. Maintainer command.
* ``render-docs``       — regenerate ``docs-src/reference/tested-versions.md``
                           from the lock files. ``--check`` exits 1 on drift.

The list of testable extras is derived from ``pyproject.toml``'s
``[project.optional-dependencies]`` table, minus the dev/build aggregates
(``_AGGREGATE_EXTRAS``, held equal to ``gen_features._EXCLUDE_EXTRAS`` by a
test rather than imported from it — see the comment on that constant) and any
extra whose requirements carry an environment marker, whose resolution depends
on the running Python in a way that breaks the lock model.

**There is no committed lock for the floor lane, deliberately.** The ``diff``
lane needs one because "what did this resolve to last time" has no other home;
a floor has one already — the specifier in ``pyproject.toml`` — and a committed
floor lock would be a second copy of it to keep in step. So the floor lane
resolves, smokes, and reports, and compares nothing.

Drift-gate::

    kind:       pair
    entrypoint: diff
    compares: the freshly resolved dependency set for each extra in pyproject.toml's
        optional-dependencies table ↔ the committed baseline in infra/drift-locks/
    domain:     process

Drift-gate::

    kind:       report
    entrypoint: floor
    surfaces: the versions each extra's declared floors in pyproject.toml resolve to, and whether
        that resolution installs; it compares nothing committed, and under --out (the way the
        workflow runs it) a failed resolve is a synthetic error report rather than a non-zero
        exit, so it asserts nothing about what it finds. Run by hand without --out it re-raises,
        because there is no report for the reason to land in
    domain:     process

Drift-gate::

    kind:       pair
    entrypoint: render-docs
    compares: the lock files in infra/drift-locks/, the declared ranges in pyproject.toml's
        optional-dependencies table, the minimum interpreter in its requires-python, and each
        extra's smoke target in scripts/drift_smoke_map.py, over the extras derived from the
        same table ↔ docs-src/reference/tested-versions.md
    domain:     process ↔ explanation

What the ``floor`` lane does **not** reach, stated because a lane that
installs a floor is easily read as one that verifies it:

* **One interpreter.** It runs on the oldest ``requires-python`` admits, so a
  floor that breaks only on a *newer* one is invisible to it. Two of the five
  floor bugs found by hand were of exactly that shape: ``sqlalchemy>=2.0``
  (all of 2.0.x installs and runs on 3.10; 2.0.0-2.0.30 die at import on 3.13)
  and ``urllib3>=1.26.0`` (1.26.0-1.26.4 raise ``ModuleNotFoundError`` on 3.13
  through their vendored six shim, and are fine on 3.10). The other three —
  ``tenacity>=4.0``, ``dagster>=1.9``, ``paramiko>=3.0`` — fail at the declared
  floor on *every* supported interpreter, so this lane catches them. Derived
  from their entries in ``sdd/BACKLOG-DONE.md``, not recalled; tenacity is the
  one most easily miscounted, because releases above its floor are that shape
  while the floor itself is not, and ``lowest-direct`` installs the floor.
* **Transitives float.** ``lowest-direct`` lowers only what this project
  declares, so a red leg can be a floor interacting with a *newest* transitive
  rather than a wrong floor. That is not noise: it is how a floor stops working
  without anyone editing it.
* **Reach is the smoke's.** Each leg runs that extra's entry in
  ``drift_smoke_map.py`` and no more, so an import-only target passes on a
  floor that breaks past module load.
* **The smoke is stricter than a user's runtime**, in the other direction: it
  inherits this repo's ``filterwarnings = error``, so a floor whose combination
  with current transitives merely *warns* fails the leg. That is deliberate — a
  deprecation at the floor is a floor about to break — but it means a red leg
  is not always something a user would see today, and the verdict's ``reason``
  is what separates the two.
* **The smoke installs pytest plugins beside the extra**, so a package the
  extra failed to declare can arrive from one of them. An isolated leg is
  evidence about the versions, weaker evidence about the set.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover — Python <3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]


sys.path.insert(0, str(Path(__file__).resolve().parent))

import drift_smoke_map  # noqa: E402  — single source for each extra's smoke target

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LOCK_DIR = ROOT / "infra" / "drift-locks"
DOCS_PAGE = ROOT / "docs-src" / "reference" / "tested-versions.md"

_LOCK_HEADER_RE = re.compile(
    r"^# extra: (?P<extra>[\w-]+)\s*\n"
    r"# python: (?P<python>[\d.]+)\s*\n"
    r"# captured: (?P<captured>[\d-]+)\s*\n",
    re.MULTILINE,
)


@dataclass(frozen=True)
class LockFile:
    """Parsed contents of an ``infra/drift-locks/<extra>.txt`` file."""

    extra: str
    python: str
    captured: str
    packages: dict[str, str]  # name (lower) -> version

    @property
    def is_empty(self) -> bool:
        return not self.packages


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def min_python() -> str:
    """The oldest interpreter ``requires-python`` admits, as ``"X.Y"``.

    The floor lane runs on this interpreter and the docs page names it, so
    both derive it from the one place it is declared. ``check_conda_recipe_pins``
    already holds three hand-written spellings of the minimum equal; a fourth
    is what this avoids.
    """
    spec = _load_pyproject()["project"]["requires-python"]
    match = re.search(r">=\s*(\d+)\.(\d+)", spec)
    if not match:
        raise ValueError(f"requires-python {spec!r} has no `>=X.Y` lower bound to derive a minimum from")
    return f"{match.group(1)}.{match.group(2)}"


def _marker_gated_extras() -> frozenset[str]:
    """Extras with any requirement carrying an environment marker.

    Such an extra resolves differently per interpreter, which breaks the
    one-lock-per-extra model: the committed baseline would record whichever
    Python the guard happened to run on. Derived rather than listed, so a new
    marker-gated extra excludes itself.
    """
    extras = _load_pyproject()["project"]["optional-dependencies"]
    return frozenset(name for name, reqs in extras.items() if any(";" in spec for spec in reqs))


# The developer/build aggregates. `gen_features.py` keeps an equal set for a
# different question — which extras to omit from the README's install list —
# and `tests/scripts/test_drift_check.py` asserts the two stay equal. Deliberately
# asserted rather than imported: that one is a presentation list, and importing it
# would let a decision about what the install docs show silently shrink the drift
# matrix, which `list_extras()` drives. An equality test fails loudly where an
# import would go quiet.
_AGGREGATE_EXTRAS: frozenset[str] = frozenset({"bench", "dev", "docs", "mutate"})


def excluded_extras() -> frozenset[str]:
    """Extras the drift guard does not track.

    Two disjoint reasons, and the docs page names only the second: the
    developer/build aggregates never reach a user's environment, and a
    marker-gated extra resolves per interpreter.
    """
    return _AGGREGATE_EXTRAS | _marker_gated_extras()


def list_extras() -> list[str]:
    """Return the sorted list of extras the drift guard tracks."""
    data = _load_pyproject()
    declared = list(data["project"]["optional-dependencies"].keys())
    excluded = excluded_extras()
    return sorted(e for e in declared if e not in excluded)


def _parse_freeze(text: str) -> dict[str, str]:
    """Parse ``pip freeze`` output into ``{name_lower: version}``.

    Skips editable installs (``-e``), VCS / direct-URL specs (``@``), the
    ``remote-store`` package itself (it's the project under test, not a
    transitive dep), and comment / blank lines.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-e "):
            continue
        if "@" in line or " " in line:
            # Direct URL / VCS / editable specifier — not a stable lock entry.
            continue
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        name_norm = name.strip().lower().replace("_", "-")
        # Skip the project itself and venv bootstrap packages: they always
        # appear in pip freeze --all but are not transitive deps of any extra.
        if name_norm in _SKIP_PACKAGES:
            continue
        out[name_norm] = version.strip()
    return out


_SKIP_PACKAGES: frozenset[str] = frozenset({"remote-store", "pip", "setuptools", "wheel"})


def resolve_extra(extra: str) -> dict[str, str]:
    """Install ``remote-store[<extra>]`` in a fresh venv and freeze it.

    Uses ``--upgrade --pre`` to pick the latest available versions of every
    transitive dependency, surfacing pre-releases the drift report will
    later separate from stable drift. The project itself is installed from
    the current checkout (``pip install .[<extra>]``) so feature-branch
    edits to ``pyproject.toml`` extras are honoured.
    """
    with tempfile.TemporaryDirectory(prefix="drift-") as tmp:
        venv_dir = Path(tmp) / "venv"
        venv.create(venv_dir, with_pip=True, clear=True)
        pip = venv_dir / "bin" / "pip"
        if not pip.exists():  # Windows fallback — not used in CI but harmless.
            pip = venv_dir / "Scripts" / "pip.exe"
        # Pin pip's streams. Without this, --quiet still leaks deprecation
        # notices / retry messages on transient PyPI failures to the parent
        # stdout, which corrupts the JSON / candidate-lock the workflow
        # redirects script stdout into. Stderr is captured so we can surface
        # it if the install fails.
        try:
            subprocess.run(
                [str(pip), "install", "--upgrade", "--pre", "--quiet", f".[{extra}]"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(exc.stderr or "")
            raise
        result = subprocess.run(
            [str(pip), "freeze", "--all"],
            check=True,
            capture_output=True,
            text=True,
        )
    return _parse_freeze(result.stdout)


def _uv(args: list[str], *, capture: bool = False) -> str:
    """Run ``uv`` with the ambient target-selection variables stripped.

    ``uv pip install`` with no explicit target honours ``UV_SYSTEM_PYTHON`` and
    ``VIRTUAL_ENV``, and ``astral-sh/setup-uv`` is what lets other workflows run
    a bare ``uv pip install`` against ``setup-python``'s interpreter with no
    venv in sight. Inheriting that here would install the floor into the runner
    Python — the same interpreter the smoke then uses — so the lane would report
    green having tested nothing. Every call below also passes ``--python``
    explicitly; this strips the variables that could override it.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("UV_SYSTEM_PYTHON", "VIRTUAL_ENV", "CONDA_PREFIX")}
    try:
        result = subprocess.run(
            ["uv", *args],
            cwd=ROOT,
            check=True,
            env=env,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or "")
        raise
    return result.stdout or ""


def resolve_floor(extra: str) -> dict[str, str]:
    """Install ``remote-store[<extra>]`` at its declared floors and freeze it.

    ``--resolution lowest-direct`` takes the floors from ``pyproject.toml``
    itself, so the lane needs no second copy of every floor to keep in step.
    Deliberately not ``lowest``: that would put *transitive* packages at their
    minimums too — floors this repo neither declares nor can fix — and the claim
    under test is the one we declare.

    The venv is built from the interpreter running this script, so the caller
    chooses which Python the floors are resolved against by choosing how to
    invoke the script.
    """
    with tempfile.TemporaryDirectory(prefix="floor-") as tmp:
        venv_dir = Path(tmp) / "venv"
        _uv(["venv", "--python", sys.executable, str(venv_dir)])
        python = venv_dir / "bin" / "python"
        if not python.exists():  # Windows fallback — not used in CI but harmless.
            python = venv_dir / "Scripts" / "python.exe"
        _uv(
            [
                "pip",
                "install",
                "--python",
                str(python),
                "--resolution",
                "lowest-direct",
                "--quiet",
                f".[{extra}]",
            ]
        )
        frozen = _uv(["pip", "freeze", "--python", str(python)], capture=True)
    return _parse_freeze(frozen)


def _lock_path(extra: str) -> Path:
    return LOCK_DIR / f"{extra}.txt"


def write_lock(extra: str, packages: dict[str, str]) -> None:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
    # Preserve `captured:` when the resolved package set has not changed,
    # so a no-op refresh does not churn the lock file (and through it the
    # docs page) just to bump the date.
    existing = read_lock(extra)
    if existing.packages == packages and existing.python == pyver and existing.captured:
        captured = existing.captured
    else:
        captured = _dt.date.today().isoformat()
    lines = [
        f"# extra: {extra}",
        f"# python: {pyver}",
        f"# captured: {captured}",
        "# Regenerate with: hatch run drift-check refresh-baseline " + extra,
        "",
    ]
    for name in sorted(packages):
        lines.append(f"{name}=={packages[name]}")
    _lock_path(extra).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_lock(extra: str) -> LockFile:
    """Read ``infra/drift-locks/<extra>.txt``.

    Stub files (no ``==`` lines under the header) parse to an empty
    ``packages`` dict; callers should branch on ``LockFile.is_empty``.
    """
    path = _lock_path(extra)
    if not path.exists():
        return LockFile(extra=extra, python="", captured="", packages={})
    text = path.read_text(encoding="utf-8")
    match = _LOCK_HEADER_RE.search(text)
    python = match.group("python") if match else ""
    captured = match.group("captured") if match else ""
    return LockFile(
        extra=extra,
        python=python,
        captured=captured,
        packages=_parse_freeze(text),
    )


def _direct_requirements_for(extra: str) -> dict[str, str]:
    """Top-level requirements an extra declares, as ``{name: specifier}``.

    The specifier is everything the declaration carries after the package
    name — the version range and any environment marker — because the
    "tested versions" page publishes the *declared* range beside the
    resolved one, and a name alone cannot answer "what does this require
    at minimum?". Recursively expands ``remote-store[<other>]`` references;
    a package reached twice keeps both specifiers, joined with ``,``, so a
    duplicated declaration is visible rather than silently halved.

    **The unit of deduplication is the whole declaration, marker included.**
    Two declarations of one package that differ only in their marker are
    therefore kept as a pair and joined, which is a string no resolver would
    accept (``dev``'s ``tomli`` is the live example). No tracked extra is in
    that shape — it needs one extra to aggregate another that declares the same
    package under a marker — and the published page only renders
    ``list_extras()``, so this is a stated bound rather than a defect. Splitting
    on the marker would need the callers to agree on which side wins, and none
    of them has that question today.
    """
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    # One list of WHOLE declarations per package, joined at the end. Comparing a
    # candidate against the accumulated string split on `,` cannot match a
    # declaration that itself contains a comma, so two identical multi-clause
    # ranges were concatenated instead of deduplicated: `[graph]` and `[httpx]`
    # both declare `httpx>=0.24.0,<1.0`, and `[dev]` reaches both, which
    # rendered `>=0.24.0,<1.0,>=0.24.0,<1.0`. That is neither of the two things
    # the contract below offers — it is not visible as a duplicate and it is
    # not a range. Measured on `_direct_requirements_for("dev")`.
    seen: dict[str, list[str]] = {}

    def walk(name: str) -> None:
        for raw in extras.get(name, []):
            spec = raw.strip()
            m = re.match(r"remote-store\[([^\]]+)\]", spec)
            if m:
                for child in m.group(1).split(","):
                    walk(child.strip())
                continue
            # Conservative: the package name is everything up to the first
            # non-identifier character; the rest is the specifier.
            pkg = re.match(r"[A-Za-z0-9_.\-]+", spec)
            if not pkg:
                continue
            key = pkg.group(0).lower().replace("_", "-")
            specifier = spec[pkg.end() :].strip()
            declarations = seen.setdefault(key, [])
            if specifier and specifier not in declarations:
                declarations.append(specifier)

    walk(extra)
    return {key: ",".join(declarations) for key, declarations in seen.items()}


def _direct_deps_for(extra: str) -> set[str]:
    """Top-level package names declared by an extra in ``pyproject.toml``.

    The key set of ``_direct_requirements_for``; used to project a
    resolution (full transitive closure) down to the user-meaningful
    packages.
    """
    return set(_direct_requirements_for(extra))


def diff_extra(extra: str, resolved: dict[str, str] | None = None) -> dict:
    """Resolve the extra and diff against the committed baseline.

    Returns a structured report with separate buckets for stable-version
    drift (loud) and pre-release-only resolutions (informational).

    ``resolved`` lets the caller pass a freeze it already computed so the
    extra is resolved only once per invocation (ID-231): the same set then
    feeds the report, the smoke's constraints file, and the candidate
    baseline. When ``None`` the diff resolves the extra itself.
    """
    baseline = read_lock(extra)
    if resolved is None:
        resolved = resolve_extra(extra)

    pyver_run = f"{sys.version_info.major}.{sys.version_info.minor}"
    if baseline.is_empty:
        return {
            "extra": extra,
            "status": "needs_refresh",
            "reason": "baseline lock is empty or missing",
            "python_run": pyver_run,
            "resolved": resolved,
        }

    drifts_stable: list[dict] = []
    drifts_prerelease: list[dict] = []
    for name in sorted(set(baseline.packages) | set(resolved)):
        old = baseline.packages.get(name)
        new = resolved.get(name)
        if old == new:
            continue
        entry = {"package": name, "baseline": old, "resolved": new}
        if new is not None and _is_prerelease(new):
            drifts_prerelease.append(entry)
        else:
            drifts_stable.append(entry)

    return {
        "extra": extra,
        "status": "ok" if not drifts_stable and not drifts_prerelease else "drift",
        "python_baseline": baseline.python,
        "python_run": pyver_run,
        "captured": baseline.captured,
        "stable_drift": drifts_stable,
        "prerelease_drift": drifts_prerelease,
    }


def _is_prerelease(version: str) -> bool:
    """Heuristic: PEP 440 pre/dev/rc markers in the version string."""
    return bool(re.search(r"(a|b|rc|dev|alpha|beta|pre)\d", version, re.IGNORECASE))


def floor_report(extra: str, resolved: dict[str, str]) -> dict:
    """Project a floor resolution onto the packages the extra declares.

    There is nothing to diff against: the claim under test is what
    ``pyproject.toml`` already says, so a committed floor lock would be a
    second copy of it. The report therefore *surfaces* the versions the
    floors resolved to rather than asserting anything about them — the smoke
    that follows is what turns them into a verdict.
    """
    direct = _direct_requirements_for(extra)
    return {
        "extra": extra,
        "lane": "floor",
        "status": "resolved",
        "python_run": f"{sys.version_info.major}.{sys.version_info.minor}",
        "floor": {name: resolved[name] for name in sorted(direct) if name in resolved},
    }


def render_docs() -> str:
    """Render ``docs-src/reference/tested-versions.md`` from the lock files.

    The output is a published docs-site page, so the template prose below
    must stay free of backlog / spec / RFC / ADR / PR-N references.
    ``scripts/check_no_tracker_refs.py`` enforces this; a leaking token
    in this template would surface as a lint failure on the generated
    output rather than on the template itself — fix it here.
    """
    extras = list_extras()

    buf = io.StringIO()
    buf.write("<!-- generated by scripts/drift_check.py — do not edit by hand -->\n")
    buf.write("# Tested versions\n\n")
    buf.write(
        "Each `[<extra>]` below lists the range it declares and the versions "
        "CI was last green against. **Declared** is the range a resolver is "
        "held to — a floor always, plus a ceiling only where a "
        "known-incompatible major looms. **Tested up to** is the exact version "
        "pinned when that extra's resolution was last recorded. "
        "Why the ranges are shaped that way, and what this page does and does "
        "not promise, is on "
        "[Dependency and version policy]"
        "(../explanation/dependency-policy.md).\n\n"
    )
    buf.write(
        "The drift guard (`.github/workflows/drift-guard.yml`) keeps both ends "
        "of each range under a weekly check. It re-resolves every extra "
        "against the latest available versions, pre-releases included, and "
        "diffs the result against the record in `infra/drift-locks/` that the "
        '"Tested up to" column is taken from. It also installs each extra at '
        "the **floor** of every range above and runs that extra's smoke "
        f"against it, on Python {min_python()} — the oldest interpreter this "
        "package supports. Findings from either end land on a rolling issue "
        "for a maintainer to read; neither end blocks a release on its own.\n\n"
    )
    buf.write(
        "_Smoke_ names how far that check reaches for each extra. A smoke that "
        "imports a module exercises less than one that runs a test suite, and "
        "a version pair below is evidence only as far as its smoke goes.\n\n"
    )

    any_pending = False
    for extra in extras:
        lock = read_lock(extra)
        declared = _direct_requirements_for(extra)
        buf.write(f"## `[{extra}]`\n\n")
        if lock.is_empty:
            any_pending = True
            buf.write(
                "_First population pending. Run "
                f"`hatch run drift-check refresh-baseline {extra}` on Linux "
                "with the primary Python — a lock is OS- as well as "
                "Python-specific — and commit the generated "
                f"`infra/drift-locks/{extra}.txt`._\n\n"
            )
            continue
        buf.write(f"_Captured {lock.captured} on Python {lock.python}._\n")
        buf.write(f"_Smoke:_ {_smoke_reach(extra)}\n\n")
        buf.write("| Package | Declared | Tested up to |\n|---|---|---|\n")
        for pkg in sorted(declared):
            version = lock.packages.get(pkg, "—")
            buf.write(f"| `{pkg}` | `{declared[pkg]}` | `{version}` |\n")
        buf.write("\n")

    if any_pending:
        buf.write(
            "\n---\n\n"
            '_Sections marked "first population pending" will fill in once a '
            "maintainer runs `hatch run drift-check refresh-baseline <extra>` "
            "on Linux with the primary Python and commits the generated "
            "`infra/drift-locks/<extra>.txt`._\n"
        )

    uncovered = sorted(_marker_gated_extras() - _AGGREGATE_EXTRAS)
    if uncovered:
        buf.write("## Extras this page does not cover\n\n")
        buf.write(
            "These are installable and maintained like any other, and the "
            "check above does not reach them: what each one resolves to "
            "depends on the interpreter you install it on, so there is no "
            "single resolution to record or to smoke. Read its range in "
            "`pyproject.toml`.\n\n"
        )
        buf.write("| Extra | Why it has no row above |\n|---|---|\n")
        for extra in uncovered:
            reasons = sorted(
                {spec.partition(";")[2].strip() for spec in _direct_requirements_for(extra).values() if ";" in spec}
            )
            buf.write(f"| `[{extra}]` | declared only for `{'`, `'.join(reasons)}` |\n")
        buf.write("\n")

    return buf.getvalue()


def _smoke_reach(extra: str) -> str:
    """One line naming how far this extra's drift smoke reaches.

    Derived from the single mapping the workflow dispatches on, so the page
    cannot describe a target the run does not use.

    **Selection is reported, the selector is not.** Six of the fourteen extras
    dispatch a ``-k`` expression (every ``SMOKE_TARGETS`` entry naming
    ``tests/backends/conformance/``: ``azure``, ``s3``, ``s3-pyarrow``,
    ``sftp``, ``sql``, ``sql-query``), and naming the paths alone would claim a
    whole-suite run that cannot happen — an extra is installed alone, and no
    one extra can pass every backend's conformance. Three of the six share the
    identical path list, so for those the paths alone would also publish one
    string for three different runs. The `-k`
    expression itself stays out: it carries harness facts (a parked proof of
    concept excluded by name) that would read as product statements on a
    published page. So the page says *that* a selection applies, never which.
    """
    argv = drift_smoke_map.smoke_for(extra)
    if argv and argv[0] == "--import-only":
        module = argv[1] if len(argv) > 1 else "remote_store"
        return f"import of `{module}` only"
    targets = ", ".join(f"`{a}`" for a in argv if "/" in a or a.endswith(".py"))
    if "-k" in argv:
        return f"the `[{extra}]` selection from {targets}"
    return targets


# ---------------------------------------------------------------------------
# Subcommand wiring
# ---------------------------------------------------------------------------


def _cmd_extras(_args: argparse.Namespace) -> int:
    print(json.dumps(list_extras()))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    # Same rendering as ``diff --emit-freeze`` so a manual ``resolve`` and the
    # workflow's emitted freeze are byte-identical (single format definition).
    sys.stdout.write(_freeze_text(resolve_extra(args.extra)))
    return 0


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (tempfile in the same dir + rename).

    A mid-execution failure never leaves a truncated file behind for a
    downstream reader — drift_report.py's ``_load_reports`` (JSON reports) or
    the workflow's constraints install (the resolved freeze).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as f:
        f.write(text)
        tmp_path = Path(f.name)
    tmp_path.replace(path)


def _freeze_text(packages: dict[str, str]) -> str:
    """Render a resolved set as a sorted ``name==version`` block.

    Byte-identical to a lock file's payload (see ``write_lock``) and to what
    the ``resolve`` subcommand prints, so the freeze doubles as both the
    uploaded candidate baseline and a pip constraints file for the smoke.
    """
    return "".join(f"{name}=={packages[name]}\n" for name in sorted(packages))


def _cmd_diff(args: argparse.Namespace) -> int:
    # Resolve the extra ONCE and reuse the freeze for the report, the smoke's
    # constraints file (``--emit-freeze``), and the uploaded candidate
    # baseline (ID-231) — so all three describe the same resolution rather
    # than three independent ones that can disagree.
    #
    # When ``--out`` is set, catch resolve / subprocess errors and emit a
    # synthetic ``status: error`` report instead of crashing. drift_report.py
    # surfaces error rows in the rolling issue so a single per-extra failure
    # does not mask drift on the other extras.
    resolved: dict[str, str] | None = None
    try:
        resolved = resolve_extra(args.extra)
        report = diff_extra(args.extra, resolved=resolved)
    except Exception as exc:
        if args.out is None:
            raise
        report = {
            "extra": args.extra,
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
            "python_run": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
    # Emit the resolved freeze for the smoke to pin against and the workflow
    # to upload as the candidate baseline. Skipped when the resolve failed
    # (``resolved is None``): the synthetic error report already signals it,
    # and ``status != "drift"`` keeps the smoke from running.
    if args.emit_freeze is not None and resolved is not None:
        _atomic_write(Path(args.emit_freeze), _freeze_text(resolved))

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out is None:
        print(payload)
        return 0
    # Atomic write: a mid-execution failure inside diff_extra would leave a
    # zero-length file under the shell's ``> path`` redirect. Writing to a
    # tempfile and ``os.replace``-ing keeps the report dir free of truncated
    # JSON that would crash drift_report.py's _load_reports for every extra.
    _atomic_write(Path(args.out), payload)
    return 0


def _cmd_floor(args: argparse.Namespace) -> int:
    # Same one-resolve-per-leg shape as ``_cmd_diff`` (ID-231): the freeze the
    # report is computed from is the freeze the smoke pins against, so a green
    # floor smoke is a statement about the versions this report names and not
    # about a second resolution nobody recorded.
    #
    # A failed resolve is a synthetic ``status: error`` report rather than a
    # crash, for the same reason ``diff`` does it: one extra's failure must not
    # cost the other thirteen their rows on the rolling issue. Here it is also
    # the *finding* — a floor that will not install is what this lane is for —
    # so the reason text is the thing a maintainer reads.
    resolved: dict[str, str] | None = None
    try:
        resolved = resolve_floor(args.extra)
        report = floor_report(args.extra, resolved)
    except Exception as exc:
        if args.out is None:
            raise
        reason = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            reason = f"{reason}\n{exc.stderr.strip()}"
        report = {
            "extra": args.extra,
            "lane": "floor",
            "status": "error",
            "reason": reason,
            "python_run": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
    if args.emit_freeze is not None and resolved is not None:
        _atomic_write(Path(args.emit_freeze), _freeze_text(resolved))

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out is None:
        print(payload)
        return 0
    _atomic_write(Path(args.out), payload)
    return 0


def _cmd_min_python(_args: argparse.Namespace) -> int:
    print(min_python())
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    targets = list_extras() if args.extra == "all" else [args.extra]
    for extra in targets:
        print(f"Resolving {extra}…", file=sys.stderr)
        packages = resolve_extra(extra)
        write_lock(extra, packages)
        print(
            f"  wrote {_lock_path(extra).relative_to(ROOT)} ({len(packages)} packages)",
            file=sys.stderr,
        )
    return 0


def _cmd_render_docs(args: argparse.Namespace) -> int:
    rendered = render_docs()
    if args.check:
        existing = DOCS_PAGE.read_text(encoding="utf-8") if DOCS_PAGE.exists() else ""
        if existing.replace("\r\n", "\n") != rendered:
            print(
                "tested-versions.md is out of date.\nRun:  hatch run drift-check render-docs",
                file=sys.stderr,
            )
            return 1
        print("tested-versions.md is up to date.")
        return 0
    DOCS_PAGE.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PAGE.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {DOCS_PAGE.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("extras", help="List testable extras as JSON.").set_defaults(func=_cmd_extras)

    p_resolve = sub.add_parser("resolve", help="Resolve one extra and emit a freeze.")
    p_resolve.add_argument("extra")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_diff = sub.add_parser("diff", help="Diff resolved vs baseline (JSON report).")
    p_diff.add_argument("extra")
    p_diff.add_argument(
        "--out",
        default=None,
        help="Write the JSON report atomically to PATH instead of stdout.",
    )
    p_diff.add_argument(
        "--emit-freeze",
        default=None,
        metavar="PATH",
        help=(
            "Also write the resolved freeze (sorted name==version) atomically "
            "to PATH. Doubles as the smoke's pip constraints file and the "
            "uploaded candidate baseline, so all three come from one resolve."
        ),
    )
    p_diff.set_defaults(func=_cmd_diff)

    p_floor = sub.add_parser("floor", help="Resolve one extra at its declared floors (JSON report).")
    p_floor.add_argument("extra")
    p_floor.add_argument(
        "--out",
        default=None,
        help="Write the JSON report atomically to PATH instead of stdout.",
    )
    p_floor.add_argument(
        "--emit-freeze",
        default=None,
        metavar="PATH",
        help=(
            "Also write the floor freeze (sorted name==version) atomically to "
            "PATH. It is the smoke's pip constraints file, so the smoke runs "
            "against exactly the resolution this report names."
        ),
    )
    p_floor.set_defaults(func=_cmd_floor)

    sub.add_parser(
        "min-python",
        help="Print the oldest interpreter requires-python admits.",
    ).set_defaults(func=_cmd_min_python)

    p_refresh = sub.add_parser(
        "refresh-baseline",
        help="Regenerate the baseline lock (operator command).",
    )
    p_refresh.add_argument("extra", help='Extra name, or "all".')
    p_refresh.set_defaults(func=_cmd_refresh)

    p_docs = sub.add_parser("render-docs", help="Render tested-versions.md from locks.")
    p_docs.add_argument("--check", action="store_true", help="Exit 1 if the doc is stale.")
    p_docs.set_defaults(func=_cmd_render_docs)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
