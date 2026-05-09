#!/usr/bin/env python3
"""Placement checks for the ``tests/`` tree.

Three independent rules, all derived from
[`sdd/TESTING.md`](../sdd/TESTING.md) § Test Subpackage Placement and
[`sdd/specs/048-testing-architecture.md`](../sdd/specs/048-testing-architecture.md)
§ TEST-003 / TEST-010.

S — **scripts/ sys.path.** A test file anywhere under ``tests/`` (except
``tests/scripts/``) that loads modules from ``scripts/`` via ``sys.path``
manipulation belongs in ``tests/scripts/``.

B — **backend imports at root.** Top-level ``tests/test_*.py`` may import
from ``remote_store.backends`` only the in-process backends
(``MemoryBackend``, ``LocalBackend``). Concrete cloud / network backends
(Azure / S3 / SFTP / SQL / HTTP) are TEST-003 violations at root and
belong under ``tests/backends/<backend>/``.

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

# Concrete backends that may NOT be imported from a top-level ``tests/test_*.py``.
# Mirrors the ``_BACKEND_CLASS_NAMES`` list in
# ``tests/backends/fixtures/test_registry.py`` minus the in-process backends
# (``MemoryBackend`` / ``LocalBackend``) which are explicitly allowed at root
# per spec 048's note "Top-level non-backend tests use a single concrete
# backend (typically MemoryBackend)".
_BANNED_BACKEND_NAMES: frozenset[str] = frozenset(
    {
        "AzureBackend",
        "AsyncAzureBackend",
        "S3Backend",
        "S3PyArrowBackend",
        "SFTPBackend",
        "SQLBlobBackend",
        "SQLQueryBackend",
        "ReadOnlyHttpBackend",
    }
)

# Backend modules under ``remote_store.backends._*`` that may be imported at root.
# ``_memory`` / ``_local`` are explicitly allowed (in-process backends, see TEST-010).
# ``_fileinfo`` is a shared backend helper (FileInfo / FolderEntry construction
# utilities), not a backend. Anything else (``_azure``, ``_s3``, ``_sftp``,
# ``_sqlalchemy`` …) is banned.
_ALLOWED_BACKEND_MODULES: frozenset[str] = frozenset({"_memory", "_local", "_fileinfo"})

# Grandfathered top-level test files that import concrete cloud / network
# backends today. These exercise cross-cutting features whose contracts are
# protocol-spanning (config loaders, depth listing, ping/health, seekable
# reads, PBT WriteResult, examples, coverage padding); each also imports
# ``MemoryBackend`` or ``LocalBackend`` as the cross-cutting baseline.
# Migrating them under ``tests/backends/<x>/`` (or to conformance) is tracked
# as the BK-190 follow-up audit. Until then, the rule is grandfathered for
# these specific files only — newly added top-level test files are still held
# to the strict standard.
_BACKEND_AT_ROOT_GRANDFATHERED: frozenset[str] = frozenset(
    {
        "test_config.py",
        "test_coverage_gaps.py",
        "test_depth_listing.py",
        "test_examples.py",
        "test_pbt_write_result.py",
        "test_ping.py",
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


def _check_backend_imports_at_root(path: Path) -> list[str]:
    """Rule B. Flag concrete-backend imports in a top-level ``tests/test_*.py``.

    Returns a list of ``"<path>:<lineno>: <message>"`` strings; empty when
    the file is clean. Files in
    ``_BACKEND_AT_ROOT_GRANDFATHERED`` are skipped (BK-190 audit follow-up).
    """
    if path.name in _BACKEND_AT_ROOT_GRANDFATHERED:
        return []
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
        # ``from remote_store.backends import <Name>, …`` — flag banned names.
        if node.module == "remote_store.backends":
            banned = sorted(a.name for a in node.names if a.name in _BANNED_BACKEND_NAMES)
            if banned:
                violations.append(
                    f"{path}:{node.lineno}: imports concrete backend(s) "
                    f"{banned!r} from remote_store.backends: "
                    "move to tests/backends/<backend>/ (TEST-003)"
                )
    return violations


def _check_root_ext_naming(tests_dir: Path) -> list[str]:
    """Rule E (a). Flag any top-level ``tests/test_ext_*.py`` (banned by BK-189)."""
    violations: list[str] = []
    for path in sorted(tests_dir.glob("test_ext_*.py")):
        if path.parent != tests_dir:
            continue
        target_stem = path.stem.removeprefix("test_ext_")
        violations.append(
            f"{path}: top-level test_ext_*.py is banned: move to tests/ext/test_{target_stem}.py (TEST-002 / TEST-010)"
        )
    return violations


def _check_ext_orphans(tests_dir: Path, src_root: Path) -> list[str]:
    """Rule E (b). Each ``tests/ext/test_<x>.py`` must have a matching
    ``src/remote_store/ext/<x>.py``, or be on the namespace-contract allow-list.
    """
    ext_dir = tests_dir / "ext"
    if not ext_dir.is_dir():
        return []
    ext_src_dir = src_root / "ext"
    known_modules = (
        {p.stem for p in ext_src_dir.glob("*.py") if p.name != "__init__.py"} if ext_src_dir.is_dir() else set()
    )
    violations: list[str] = []
    for path in sorted(ext_dir.glob("test_*.py")):
        if path.parent != ext_dir:
            continue
        if path.name in _EXT_ORPHAN_ALLOWLIST:
            continue
        target_stem = path.stem.removeprefix("test_")
        if target_stem not in known_modules:
            violations.append(
                f"{path}: no matching src/remote_store/ext/{target_stem}.py: "
                "rename, remove, or add to the contract allow-list "
                "in scripts/check_test_placement.py (TEST-002)"
            )
    return violations


def main(directories: list[str] | None = None, src_root: Path | None = None) -> int:
    if directories is None:
        directories = ["tests"]
    if src_root is None:
        src_root = ROOT / "src" / "remote_store"

    scripts_violations: list[str] = []
    backend_violations: list[str] = []
    ext_violations: list[str] = []

    for directory in directories:
        tests_dir = Path(directory)
        scripts_subpkg = tests_dir / "scripts"
        for path in sorted(tests_dir.rglob("test_*.py")):
            # Rule S — applies everywhere except tests/scripts/ itself.
            if not path.is_relative_to(scripts_subpkg):
                msg = _check_file(path)
                if msg is not None:
                    scripts_violations.append(msg)
            # Rule B — top-level tests/test_*.py only.
            if path.parent == tests_dir:
                backend_violations.extend(_check_backend_imports_at_root(path))

        # Rule E — directory-level scans.
        ext_violations.extend(_check_root_ext_naming(tests_dir))
        ext_violations.extend(_check_ext_orphans(tests_dir, src_root))

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
