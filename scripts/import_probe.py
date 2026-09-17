"""BK-372: import one real module per distribution an extra declares.

The isolation half of the drift guard. Both lanes install an extra **alone**,
then run this before any test tooling joins the environment: the pytest plugins
drag in packages of their own, and after they are installed an under-declared
extra imports perfectly well on somebody else's dependency.

Run by ``.github/actions/drift-smoke/action.yml`` as
``python scripts/import_probe.py <extra>``. It exits non-zero on the first
import that raises, and the action records that as the ``import-extra`` phase.

**It lives here rather than in the action's here-document so it can be tested.**
The selection rules below were wrong twice on this branch — once reading
``top_level.txt`` on an interpreter that does not infer, once walking into a
PEP-420 namespace root — and both times the only thing standing between a
broken probe and a green leg was a ``grep`` for its output. Selection rules with
edge cases belong where ``tests/scripts/`` can reach them.

Note this file is invoked from a composite action, which
``gen_gate_inventory.py``'s ``_WIRING_SOURCES`` does not scan, so it would not
appear in ``sdd/GATE-INVENTORY.md``'s *Runs in* column if it carried a
``Drift-gate::`` block. It carries none: it surfaces nothing and compares
nothing, it is one phase of a mechanism ``drift_check.py`` already declares.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from drift_check import _direct_requirements_for  # noqa: E402


def dotted_modules(dist) -> set[str]:
    """Every importable dotted module name a distribution's own files define.

    Read from the distribution's file list rather than from
    ``packages_distributions()`` or ``top_level.txt``. Two reasons, both
    measured: on Python 3.10 ``packages_distributions()`` reads
    ``top_level.txt`` only, and a hatchling-built wheel ships none — httpx,
    pydantic-settings and opentelemetry-api all resolved to nothing and the
    probe reported three working installs as failures. And a top-level name is
    the wrong unit anyway for a PEP-420 namespace, where it belongs to no
    distribution in particular.
    """
    names: set[str] = set()
    for path in dist.files or []:
        if path.suffix != ".py":
            continue
        parts = list(path.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][: -len(".py")]
        if parts and all(part.isidentifier() for part in parts):
            names.add(".".join(parts))
    return names


def first_real_module(names: set[str]) -> str | None:
    """The shallowest public name that is a real module, not an empty namespace.

    ``import azure`` and ``import opentelemetry`` both succeed while executing
    no code from any distribution: they are namespace roots shared by every
    ``azure-*`` / ``opentelemetry-*`` package installed. Probing one proves
    nothing, and would have reported ``import ok`` for a floor whose
    ``azure-storage-file-datalake`` could not load at all. A real module has a
    spec with an origin; a PEP-420 namespace portion has ``origin is None``.

    **Bound, because the rule is narrower than it reads.** That test identifies
    an *implicit* namespace only. A pkgutil- or ``pkg_resources``-style
    namespace ships a real ``__init__.py``, so its root has an origin and would
    be selected — and importing it executes almost nothing. No distribution any
    tracked extra declares is in that shape (checked across all 14), so this is
    a stated bound rather than a live defect.

    Public before shallow: a distribution's private accelerator (PyYAML's
    ``_yaml``, which is optional and absent from an sdist build without libyaml)
    says less about the surface a user reaches than its public module does.
    """
    ordered = sorted(names, key=lambda n: (any(p.startswith("_") for p in n.split(".")), n.count("."), n))
    for name in ordered:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError, ModuleNotFoundError):
            continue
        if spec is not None and spec.origin is not None:
            return name
    return None


def probe(extra: str) -> int:
    """Import one real module per declared distribution. 0 if all imported.

    A distribution shipping no importable module at all is **skipped**, not
    failed: `types-paramiko` ships only stubs, and a data-only distribution
    ships none. A run where *nothing* was probed is a failure, because a probe
    that silently checks nothing looks identical to a clean one.

    **One deliberate departure from the inlined version this replaces**, stated
    because the commit that moved this code described itself as an extraction:
    the inline probe called ``distribution()`` bare, so a requirement declared
    but not installed propagated ``PackageNotFoundError`` and failed the leg.
    Here it is skipped. After ``pip install .[extra]`` has already succeeded,
    the only way a declared requirement is absent is an environment marker that
    excludes this interpreter — the resolver was right not to install it, and
    failing the leg would report a working install as broken, which is the
    exact class of false negative this probe has produced twice. No tracked
    extra carries a marker-gated requirement today (measured: none of the 14),
    so the branch is unreachable from the workflow and is insurance rather than
    live behaviour.
    """
    requirements = sorted(_direct_requirements_for(extra))
    probed = 0
    for requirement in requirements:
        try:
            dist = distribution(requirement)
        except PackageNotFoundError:
            # Declared under a marker that excludes this interpreter. Not a
            # finding: the resolver was right not to install it.
            print(f"skip (not installed on this interpreter): {requirement}")
            continue
        module = first_real_module(dotted_modules(dist))
        if module is None:
            print(f"skip (no importable module ships with {requirement})")
            continue
        importlib.import_module(module)
        probed += 1
        print(f"import ok: {requirement} -> {module}")
    if not probed:
        print(f"no importable module found for any of {requirements}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: import_probe.py <extra>", file=sys.stderr)
        return 2
    return probe(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
