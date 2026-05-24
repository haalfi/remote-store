"""ID-182: Scheduled CI drift guard for unbounded extra-dependency floors.

Resolves each ``remote-store[<extra>]`` against the latest available
transitive versions (including pre-releases) and diffs the resolution
against a committed baseline in ``infra/drift-locks/``. The scheduled
workflow that drives this lives at ``.github/workflows/drift-guard.yml``.

The script is deliberately stdlib-only so it can run in a freshly created
venv before any project dependency is installed.

Subcommands:

* ``extras``            — list testable extras (JSON array on stdout).
* ``resolve <extra>``   — install ``remote-store[<extra>]`` in a fresh
                           venv with ``--upgrade --pre`` and emit the
                           pinned set on stdout.
* ``diff <extra>``      — call ``resolve`` and diff against the baseline
                           in ``infra/drift-locks/<extra>.txt``. Emits a
                           JSON report on stdout.
* ``refresh-baseline    — overwrite ``infra/drift-locks/<extra>.txt`` with
   <extra>``              a fresh resolution. Maintainer command.
* ``render-docs``       — regenerate ``docs-src/reference/tested-versions.md``
                           from the lock files. ``--check`` exits 1 on drift.

The list of testable extras is derived from ``pyproject.toml``'s
``[project.optional-dependencies]`` table, minus the dev/build aggregates
and the marker-gated ``toml`` extra.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
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


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LOCK_DIR = ROOT / "infra" / "drift-locks"
DOCS_PAGE = ROOT / "docs-src" / "reference" / "tested-versions.md"

# Extras excluded from drift checking: developer-only aggregates (dev, docs,
# bench) and marker-gated extras whose resolution depends on the running
# Python version in a way that breaks the lock model.
_EXCLUDED_EXTRAS: frozenset[str] = frozenset({"dev", "docs", "bench", "toml"})

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


def list_extras() -> list[str]:
    """Return the sorted list of extras the drift guard tracks."""
    data = _load_pyproject()
    declared = list(data["project"]["optional-dependencies"].keys())
    return sorted(e for e in declared if e not in _EXCLUDED_EXTRAS)


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
        # Quiet pip; we only care about the freeze output.
        subprocess.run(
            [str(pip), "install", "--upgrade", "--pre", "--quiet", f".[{extra}]"],
            cwd=ROOT,
            check=True,
        )
        result = subprocess.run(
            [str(pip), "freeze", "--all"],
            check=True,
            capture_output=True,
            text=True,
        )
    return _parse_freeze(result.stdout)


def _lock_path(extra: str) -> Path:
    return LOCK_DIR / f"{extra}.txt"


def write_lock(extra: str, packages: dict[str, str]) -> None:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
    lines = [
        f"# extra: {extra}",
        f"# python: {pyver}",
        f"# captured: {today}",
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


def _direct_deps_for(extra: str) -> set[str]:
    """Top-level package names declared by an extra in ``pyproject.toml``.

    Used to project the lock (full transitive closure) down to the
    user-meaningful packages for the "tested versions" doc page.
    Recursively expands ``remote-store[<other>]`` references.
    """
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    seen: set[str] = set()

    def walk(name: str) -> None:
        for spec in extras.get(name, []):
            spec = spec.strip()
            m = re.match(r"remote-store\[([^\]]+)\]", spec)
            if m:
                for child in m.group(1).split(","):
                    walk(child.strip())
                continue
            # Strip version spec, env-marker, extras. Conservative: take
            # the package name only (before the first non-identifier char).
            pkg = re.match(r"[A-Za-z0-9_.\-]+", spec)
            if pkg:
                seen.add(pkg.group(0).lower().replace("_", "-"))

    walk(extra)
    return seen


def diff_extra(extra: str) -> dict:
    """Resolve the extra and diff against the committed baseline.

    Returns a structured report with separate buckets for stable-version
    drift (loud) and pre-release-only resolutions (informational).
    """
    baseline = read_lock(extra)
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


def render_docs() -> str:
    """Render ``docs-src/reference/tested-versions.md`` from the lock files."""
    today = _dt.date.today().isoformat()
    extras = list_extras()

    buf = io.StringIO()
    buf.write("<!-- generated by scripts/drift_check.py — do not edit by hand -->\n")
    buf.write("# Tested upper-bound versions\n\n")
    buf.write(
        "Each ``[<extra>]`` declares a floor in ``pyproject.toml`` and "
        "deliberately no ceiling. The drift guard "
        "(`.github/workflows/drift-guard.yml`, ID-182) records the last "
        "known-good resolution per extra in ``infra/drift-locks/`` and "
        "re-resolves weekly against the latest available versions "
        "(including pre-releases) to surface silent transitive upgrades "
        "before they reach users.\n\n"
    )
    buf.write(
        "The table below is the projection of those lock files onto the "
        'top-level packages each extra declares. "Tested up to" is the '
        "exact version pinned in the lock at capture time — that is what "
        "CI was last green against.\n\n"
    )

    any_pending = False
    for extra in extras:
        lock = read_lock(extra)
        direct = _direct_deps_for(extra)
        buf.write(f"## `[{extra}]`\n\n")
        if lock.is_empty:
            any_pending = True
            buf.write(
                "_First population pending. Run "
                f"`hatch run drift-check refresh-baseline {extra}` on the "
                "primary Python and commit the generated "
                f"`infra/drift-locks/{extra}.txt`._\n\n"
            )
            continue
        buf.write(f"_Captured {lock.captured} on Python {lock.python}._\n\n")
        buf.write("| Package | Tested up to |\n|---|---|\n")
        for pkg in sorted(direct):
            version = lock.packages.get(pkg, "—")
            buf.write(f"| `{pkg}` | `{version}` |\n")
        buf.write("\n")

    if any_pending:
        buf.write(
            "\n---\n\n"
            "_Page rendered "
            f'{today}. Sections marked "first population pending" will '
            "fill in once a maintainer runs the refresh command and "
            "commits the lock._\n"
        )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Subcommand wiring
# ---------------------------------------------------------------------------


def _cmd_extras(_args: argparse.Namespace) -> int:
    print(json.dumps(list_extras()))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    packages = resolve_extra(args.extra)
    for name in sorted(packages):
        print(f"{name}=={packages[name]}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    report = diff_extra(args.extra)
    print(json.dumps(report, indent=2, sort_keys=True))
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
    p_diff.set_defaults(func=_cmd_diff)

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
