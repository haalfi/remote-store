#!/usr/bin/env python3
"""Placement checks for the ``tests/`` tree.

Three independent rules, all derived from
[`sdd/TESTING.md`](../sdd/TESTING.md) § Test Subpackage Placement and
[`sdd/specs/048-testing-architecture.md`](../sdd/specs/048-testing-architecture.md)
§ TEST-003 / TEST-010.

S — **scripts/ sys.path.** A test file anywhere under ``tests/`` (except
``tests/scripts/``) that loads modules from ``scripts/`` via ``sys.path``
manipulation belongs in ``tests/scripts/``.

B — **backend imports at root.** Top-level ``tests/test_*.py`` and
``tests/aio/test_async_*.py`` may import from ``remote_store.backends``
only the in-process backend modules (``_memory``, ``_local``) and the
shared ``_fileinfo`` helper module — every public class in those
modules is allowed. Concrete cloud / network backends (Azure / S3 /
SFTP / SQL / HTTP) are TEST-003 violations and belong under
``tests/backends/<backend>/``. Banned class names are derived at script
import via ``_discover_banned_backend_names``; star-imports
(``from remote_store.backends import *``) are flagged unconditionally
because they may pull in any current or future banned class.

A grandfathered allow-list (``_BACKEND_AT_ROOT_GRANDFATHERED``) covers
legacy cross-cutting test files. The list is *self-pruning*: an entry
that no longer triggers a violation (file removed, refactored, or
moved) is reported as a stale entry so the list shrinks monotonically.

E — **ext placement.** Ext-module tests live in
``tests/ext/test_<x>.py`` (BK-189). Top-level ``tests/test_ext_*.py`` is
banned. Each ``tests/ext/test_<x>.py`` must have a matching
``src/remote_store/ext/<x>.py`` (allow-list: ``test_contract.py`` for the
namespace-wide ``__all__`` / private-import contract).

CI enforcement. Exit code 0 = ok; 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Backend modules under ``remote_store.backends._*`` and
# ``remote_store.aio.backends._*`` that may be imported at root.
# ``_memory`` / ``_local`` are explicitly allowed (in-process backends, see
# TEST-010). ``_fileinfo`` is a shared backend helper (FileInfo /
# FolderEntry construction utilities), not a backend. Anything else
# (``_azure``, ``_s3``, ``_sftp``, ``_sqlalchemy`` …) is banned.
_ALLOWED_BACKEND_MODULES: frozenset[str] = frozenset({"_memory", "_local", "_fileinfo"})


def _discover_banned_backend_names(src_root: Path) -> frozenset[str]:
    """Discover concrete backend class names that are TEST-003 violations
    when imported into a top-level ``tests/test_*.py``.

    AST-walks ``src/remote_store/backends/_*.py`` and
    ``src/remote_store/aio/backends/_*.py`` (the only two homes for
    ``Backend`` / ``AsyncBackend`` implementations), collects every
    top-level class whose name ends in ``Backend`` (the repo-wide naming
    convention), and excludes classes defined in modules listed in
    ``_ALLOWED_BACKEND_MODULES``.

    Static-only: never imports the package, so optional backend deps
    are not required to compute the list. A new backend file added under
    either backends directory automatically extends the banned set —
    no hand-maintained roster to drift.
    """
    banned: set[str] = set()
    for backends_dir in (src_root / "backends", src_root / "aio" / "backends"):
        if not backends_dir.is_dir():
            continue
        for py in sorted(backends_dir.glob("_*.py")):
            if py.name == "__init__.py" or py.stem in _ALLOWED_BACKEND_MODULES:
                continue
            try:
                source = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                sys.stderr.write(f"Skipping {py}: {type(exc).__name__}\n")
                continue
            try:
                tree = ast.parse(source, filename=str(py))
            except SyntaxError:
                sys.stderr.write(f"Skipping {py}: SyntaxError\n")
                continue
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name.endswith("Backend"):
                    banned.add(node.name)
    return frozenset(banned)


# Concrete backends that may NOT be imported from a top-level
# ``tests/test_*.py``. Discovered dynamically at script import via
# ``_discover_banned_backend_names`` — see that function for the contract
# and for why a hand-maintained list was unsuitable.
_BANNED_BACKEND_NAMES: frozenset[str] = _discover_banned_backend_names(ROOT / "src" / "remote_store")

# Grandfathered top-level test files that import concrete cloud / network
# backends today. These exercise cross-cutting features whose contracts are
# protocol-spanning (config loaders, depth listing, ping/health, seekable
# reads, PBT WriteResult, examples, coverage padding); each also imports
# ``MemoryBackend`` or ``LocalBackend`` as the cross-cutting baseline.
#
# Per-file disposition (BK-191 audit, sdd/audits/audit-014):
#
#   - ``test_examples.py`` is justified at root permanently: it harnesses the
#     full ``examples/`` corpus and the example/test 1:1 invariant (ID-044)
#     means each published example demo has exactly one postcondition test
#     here. The single banned-backend site (``ReadOnlyHttpBackend`` for the
#     HTTP read-only example) is structural, not migration-pending.
#
#   - The remaining four files are migration-pending follow-ups of BK-191
#     (a per-backend split, or b conformance reshape); see the audit doc for
#     the per-file plan. Each retires its allow-list entry when its slice
#     lands.
#
# Newly added top-level test files are still held to the strict standard;
# this allow-list is not a license to add new entries.
_BACKEND_AT_ROOT_GRANDFATHERED: frozenset[str] = frozenset(
    {
        "test_coverage_gaps.py",
        "test_depth_listing.py",
        "test_examples.py",
        "test_pbt_write_result.py",
        "test_seekable.py",
    }
)

# ``tests/ext/`` files that have no matching ``ext/<x>.py`` source by design —
# they police namespace-wide invariants rather than a single module.
_EXT_ORPHAN_ALLOWLIST: frozenset[str] = frozenset({"test_contract.py"})


def _names_referencing_scripts(tree: ast.Module) -> set[str]:
    """Collect variable names assigned to paths containing 'scripts'.

    Covers plain and annotated assignments:
        SCRIPTS = ROOT / "scripts"
        SCRIPTS: Path = ROOT / "scripts"
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            value = node.value
            targets = [node.target]
        else:
            continue
        for child in ast.walk(value):
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and "scripts" in child.value:
                for target in targets:
                    names.add(target.id)
                break
    return names


def _uses_scripts_sys_path(tree: ast.Module, scripts_names: set[str]) -> int | None:
    """Return the line number of the first sys.path manipulation that adds scripts/.

    Matches:
        sys.path.insert(N, str(SCRIPTS))
        sys.path.append(str(SCRIPTS))
        sys.path.insert(N, "…/scripts")

    Only inspects the path argument (index 1 for insert, 0 for append) to avoid
    false positives from variable names used as the index slot.

    Returns None if no such call is found.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in {"insert", "append"}
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "path"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "sys"
        ):
            continue
        # Select only the path argument to avoid false positives from the index slot.
        if func.attr == "insert":
            if len(node.args) < 2:
                continue
            path_arg = node.args[1]
        else:  # append
            if not node.args:
                continue
            path_arg = node.args[0]
        for arg in ast.walk(path_arg):
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "scripts" in arg.value:
                return node.lineno
            if isinstance(arg, ast.Name) and arg.id in scripts_names:
                return node.lineno
    return None


def _check_file(path: Path) -> str | None:
    """Return a violation message if the file belongs in tests/scripts/, else None.

    Rule S. Kept as the original function name so existing callers and unit
    tests keep working.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
        return None
    if "sys.path" not in source or "scripts" not in source:
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        sys.stderr.write(f"Skipping {path}: SyntaxError\n")
        return None
    scripts_names = _names_referencing_scripts(tree)
    line = _uses_scripts_sys_path(tree, scripts_names)
    if line is not None:
        return f"{path}:{line}: loads scripts/ module via sys.path: move to tests/scripts/"
    return None


def _compute_backend_violations(path: Path, banned_names: frozenset[str]) -> list[str]:
    """Raw Rule B scan: returns concrete-backend import violations for one file.

    Does *not* apply the grandfather-skip; callers who need that should
    use ``_check_backend_imports_at_root``. Splitting the two lets
    ``main()`` detect stale grandfather entries (entries that no longer
    have any actual violation to skip).

    Three import styles are inspected:
      1. ``from remote_store.backends._<x> import …``
         (private path; flagged when ``<x>`` is not in
         ``_ALLOWED_BACKEND_MODULES``)
      2. ``import remote_store.backends._<x>`` (with or without alias)
         (same allow-list)
      3. ``from remote_store.backends import <Name>, …``
         (public namespace; flagged when any name is in ``banned_names``,
         and unconditionally when the import is a wildcard
         ``import *`` — the wildcard could pull in any current or future
         banned class)
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(f"Skipping {path}: {type(exc).__name__}\n")
        return []
    if "remote_store.backends" not in source:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        sys.stderr.write(f"Skipping {path}: SyntaxError\n")
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        # ``import remote_store.backends._<x>`` (and ``... as alias``).
        # ``ast.Import`` is a separate node type from ``ast.ImportFrom``;
        # walking only the latter would silently miss this style.
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith("remote_store.backends._"):
                    continue
                submodule = alias.name.removeprefix("remote_store.backends.").split(".", 1)[0]
                if submodule not in _ALLOWED_BACKEND_MODULES:
                    violations.append(
                        f"{path}:{node.lineno}: imports backend module "
                        f"{alias.name!r}: move to tests/backends/<backend>/ (TEST-003)"
                    )
            continue
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        # ``from remote_store.backends._<x> import …``
        if node.module.startswith("remote_store.backends._"):
            submodule = node.module.removeprefix("remote_store.backends.")
            if submodule not in _ALLOWED_BACKEND_MODULES:
                violations.append(
                    f"{path}:{node.lineno}: imports backend module "
                    f"{node.module!r}: move to tests/backends/<backend>/ (TEST-003)"
                )
            continue
        # ``from remote_store.backends import <Name>, …`` and
        # ``from remote_store.backends import *``.
        if node.module == "remote_store.backends":
            star_import = any(a.name == "*" for a in node.names)
            banned = sorted(a.name for a in node.names if a.name in banned_names)
            if star_import:
                violations.append(
                    f"{path}:{node.lineno}: wildcard import from "
                    "remote_store.backends may pull in concrete backend "
                    "classes: list explicit imports instead (TEST-003)"
                )
            if banned:
                violations.append(
                    f"{path}:{node.lineno}: imports concrete backend(s) "
                    f"{banned!r} from remote_store.backends: "
                    "move to tests/backends/<backend>/ (TEST-003)"
                )
    return violations


def _check_backend_imports_at_root(path: Path, banned_names: frozenset[str] | None = None) -> list[str]:
    """Rule B with grandfather-skip applied. Wrapper around
    ``_compute_backend_violations`` for direct callers (e.g. unit tests)
    that don't need the stale-entry tracking ``main()`` does.

    ``banned_names`` defaults to the module-level
    ``_BANNED_BACKEND_NAMES`` discovered at import. Pass a custom set to
    drive the check from a synthetic ``src_root`` (e.g. in unit tests).
    """
    if path.name in _BACKEND_AT_ROOT_GRANDFATHERED:
        return []
    if banned_names is None:
        banned_names = _BANNED_BACKEND_NAMES
    return _compute_backend_violations(path, banned_names)


def _check_root_ext_naming(tests_dir: Path) -> list[str]:
    """Rule E (a). Flag banned top-level ext-prefix test files in both the
    sync and async trees.

    - ``tests/test_ext_*.py`` (sync) is banned by BK-189; canonical
      home is ``tests/ext/test_<x>.py``.
    - ``tests/aio/test_async_ext_*.py`` (async) follows the same
      1:1 invariant per the TEST-010 amendment; canonical home is
      ``tests/aio/ext/test_async_<x>.py``.
    """
    violations: list[str] = []
    for path in sorted(tests_dir.glob("test_ext_*.py")):
        if path.parent != tests_dir:
            continue
        target_stem = path.stem.removeprefix("test_ext_")
        violations.append(
            f"{path}: top-level test_ext_*.py is banned: move to tests/ext/test_{target_stem}.py (TEST-002 / TEST-010)"
        )
    aio_dir = tests_dir / "aio"
    if aio_dir.is_dir():
        for path in sorted(aio_dir.glob("test_async_ext_*.py")):
            if path.parent != aio_dir:
                continue
            target_stem = path.stem.removeprefix("test_async_ext_")
            violations.append(
                f"{path}: top-level tests/aio/test_async_ext_*.py is banned: "
                f"move to tests/aio/ext/test_async_{target_stem}.py (TEST-002 / TEST-010)"
            )
    return violations


def _check_ext_orphans(tests_dir: Path, src_root: Path) -> list[str]:
    """Rule E (b). Each ext test must pair with a matching ext source.

    Two parallel scans, mirroring the TEST-010 1:1 invariant:
      - sync: ``tests/ext/test_<x>.py`` ↔ ``src/remote_store/ext/<x>.py``
      - async: ``tests/aio/ext/test_async_<x>.py`` ↔
        ``src/remote_store/aio/ext/<x>.py``

    Files in ``_EXT_ORPHAN_ALLOWLIST`` (namespace-wide invariants like
    ``test_contract.py``) are exempt.
    """
    violations: list[str] = []
    for ext_test_dir, src_ext_dir, prefix, src_label in (
        (tests_dir / "ext", src_root / "ext", "test_", "src/remote_store/ext"),
        (tests_dir / "aio" / "ext", src_root / "aio" / "ext", "test_async_", "src/remote_store/aio/ext"),
    ):
        if not ext_test_dir.is_dir():
            continue
        known_modules = (
            {p.stem for p in src_ext_dir.glob("*.py") if p.name != "__init__.py"} if src_ext_dir.is_dir() else set()
        )
        for path in sorted(ext_test_dir.glob("test_*.py")):
            if path.parent != ext_test_dir:
                continue
            if path.name in _EXT_ORPHAN_ALLOWLIST:
                continue
            target_stem = path.stem.removeprefix(prefix)
            if target_stem not in known_modules:
                violations.append(
                    f"{path}: no matching {src_label}/{target_stem}.py: "
                    "rename, remove, or add to the contract allow-list "
                    "in scripts/check_test_placement.py (TEST-002)"
                )
    return violations


def _is_rule_b_candidate(path: Path, tests_dir: Path) -> bool:
    """True if ``path`` is a top-level cross-cutting test that Rule B applies to.

    Two homes per spec 048 TEST-010:
      - sync top-level: ``<tests_dir>/test_*.py``
      - async top-level: ``<tests_dir>/aio/test_async_*.py``

    Async backend-specific tests live under ``tests/backends/<backend>/aio/``
    (TEST-003) and ext-module async tests live under ``tests/aio/ext/``;
    both are *not* candidates here.
    """
    if path.parent == tests_dir:
        return True
    aio_dir = tests_dir / "aio"
    return path.parent == aio_dir and path.name.startswith("test_async_")


def main(
    directories: list[str] | None = None,
    src_root: Path | None = None,
    grandfathered: frozenset[str] | None = None,
) -> int:
    if directories is None:
        directories = ["tests"]
    if src_root is None:
        src_root = ROOT / "src" / "remote_store"
    if grandfathered is None:
        grandfathered = _BACKEND_AT_ROOT_GRANDFATHERED

    # Thread src_root through Rule B: discover banned names once for this
    # run instead of relying on the module-global computed at import.
    # Synthetic src trees in unit tests now drive Rule B correctly.
    banned_names = _discover_banned_backend_names(src_root)

    scripts_violations: list[str] = []
    backend_violations: list[str] = []
    ext_violations: list[str] = []
    # Track which grandfather entries actually fired so we can report
    # stale ones (entries where the file is absent or no longer violates).
    grandfather_actually_violating: set[str] = set()

    for directory in directories:
        tests_dir = Path(directory)
        scripts_subpkg = tests_dir / "scripts"
        for path in sorted(tests_dir.rglob("test_*.py")):
            # Rule S — applies everywhere except tests/scripts/ itself.
            if not path.is_relative_to(scripts_subpkg):
                msg = _check_file(path)
                if msg is not None:
                    scripts_violations.append(msg)
            # Rule B — top-level sync and top-level async cross-cutting tests.
            if _is_rule_b_candidate(path, tests_dir):
                raw = _compute_backend_violations(path, banned_names)
                if not raw:
                    continue
                if path.name in grandfathered:
                    grandfather_actually_violating.add(path.name)
                else:
                    backend_violations.extend(raw)

        # Rule E — directory-level scans.
        ext_violations.extend(_check_root_ext_naming(tests_dir))
        ext_violations.extend(_check_ext_orphans(tests_dir, src_root))

    # Stale grandfather entries: any name in ``grandfathered`` that didn't
    # fire is dead weight (file removed, refactored, or no longer
    # importing a banned backend). Keeps the list shrinking monotonically
    # without manual audits.
    stale = grandfathered - grandfather_actually_violating
    if stale:
        backend_violations.append(
            f"stale grandfather entry/ies: {sorted(stale)!r} no longer "
            "import a banned backend (file absent or clean) — remove from "
            "_BACKEND_AT_ROOT_GRANDFATHERED in scripts/check_test_placement.py"
        )

    total = len(scripts_violations) + len(backend_violations) + len(ext_violations)
    if total:
        if scripts_violations:
            print(f"Found {len(scripts_violations)} misplaced script test(s):\n")
            for v in scripts_violations:
                print(f"  {v}")
            print("\nMove these files to tests/scripts/.")
        if backend_violations:
            print(f"\nFound {len(backend_violations)} TEST-003 backend-at-root violation(s):\n")
            for v in backend_violations:
                print(f"  {v}")
            print("\nMove these files under tests/backends/<backend>/.")
        if ext_violations:
            print(f"\nFound {len(ext_violations)} TEST-002 ext placement violation(s):\n")
            for v in ext_violations:
                print(f"  {v}")
            print("\nSee sdd/TESTING.md § Test Subpackage Placement.")
        return 1

    print("All test placements are correct (rules S, B, E).")
    return 0


if __name__ == "__main__":
    dirs = sys.argv[1:] or None
    raise SystemExit(main(dirs))
