"""Build and execute the pytest-gremlins command for a named mutate scope.

Reads the scope manifest in ``scripts/mutate_scopes.py``. Used by
``hatch run mutate <scope>`` (single shim in ``pyproject.toml``) and by
``.github/workflows/mutation.yml`` (introspection flags emit JSON for
matrix and container-startup decisions).

Usage::

    python scripts/run_mutate.py <scope>            # exec pytest
    python scripts/run_mutate.py --list-scopes      # JSON array of names
    python scripts/run_mutate.py --container-needs minio
                                                    # JSON array of scopes
                                                    # that need MinIO
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mutate_scopes import SCOPES  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Default path pytest-gremlins writes its JSON report to, mirrored by the
# ``record`` step in ``.github/workflows/mutation.yml``. pytest-gremlins writes
# NO report when a scope's target files hold zero mutation candidates (the
# plugin returns from ``pytest_terminal_summary`` before the report write), so a
# green leg can legitimately leave this absent — see ``_ensure_report_for_empty_scope``.
_GREMLINS_JSON = _REPO_ROOT / "coverage" / "gremlins" / "gremlins.json"

# Identical in shape to what ``pytest_gremlins.reporting.JsonReporter`` emits
# for an empty ``MutationScore`` (``total == 0``). ``mutation_report.py record``
# reads ``summary.{zapped,survived,timeout,error}``; ``classify_scopes`` then
# sees ``survived == 0`` and classifies the scope ``ok``.
_EMPTY_REPORT = {
    "summary": {"total": 0, "zapped": 0, "survived": 0, "timeout": 0, "error": 0, "pardoned": 0, "percentage": 0.0},
    "files": {},
    "results": [],
}


def _scope_has_no_mutation_candidates(scope) -> bool:
    """True only when every target file of *scope* yields zero gremlins.

    Asks pytest-gremlins' own transformer (the same generation path the plugin
    runs in ``_generate_gremlins``), so the answer can never drift from what the
    plugin counts. Returns ``False`` on any uncertainty — the plugin not
    installed (the bare ``--list-scopes`` introspection runner, or the <3.11
    matrix), an unreadable target, or a transform error — so a synthesised
    report is written only when "zero candidates" is positively confirmed.
    """
    try:
        from pytest_gremlins.instrumentation.transformer import get_default_registry, transform_source
    except ImportError:
        return False
    operators = get_default_registry().get_all()
    for target in scope.targets:
        path = _REPO_ROOT / target
        try:
            source = path.read_text(encoding="utf-8")
            gremlins, _ = transform_source(source, str(path), operators)
        except Exception:  # noqa: BLE001 — any failure means "cannot confirm zero"; do not synthesise
            return False
        if gremlins:
            return False
    return True


def _ensure_report_for_empty_scope(scope, returncode: int, report_path: Path = _GREMLINS_JSON) -> None:
    """Write the canonical empty report when a green run produced none *because
    the scope has no mutation candidates*.

    pytest-gremlins writes no report for a zero-candidate scope, and
    ``mutation_report.py record`` would otherwise read that absent report on a
    green leg as a silent reporting break (counts ``None`` -> harness failure),
    turning the weekly run red forever for a scope that simply has nothing to
    mutate. Synthesising the all-zero report the plugin would have written for
    an empty score lets such a scope classify as clean, while the genuine break
    case — gremlins exist but no report — still leaves the file absent and fails
    the leg (BUG-215).
    """
    if returncode != 0 or report_path.exists():
        return
    if not _scope_has_no_mutation_candidates(scope):
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_EMPTY_REPORT, indent=2), encoding="utf-8")
    print(f"run_mutate: scope has no mutation candidates; wrote empty report to {report_path}", file=sys.stderr)


def _build_pytest_argv(scope_name: str) -> list[str]:
    scope = SCOPES[scope_name]
    argv = [
        "-m",
        "pytest",
        "--gremlins",
        f"--gremlin-targets={','.join(scope.targets)}",
        *scope.tests,
    ]
    if scope.filter is not None:
        argv += ["-k", scope.filter]
    return argv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scope",
        nargs="?",
        help=f"Scope to run. One of: {', '.join(SCOPES)}",
    )
    parser.add_argument(
        "--list-scopes",
        action="store_true",
        help="Print all scope names as a JSON array and exit.",
    )
    parser.add_argument(
        "--container-needs",
        metavar="CONTAINER",
        help=("Print scopes needing the given container (minio/azurite/sftp) as a JSON array and exit."),
    )
    args = parser.parse_args()

    if args.list_scopes:
        print(json.dumps(list(SCOPES.keys())))
        return 0

    if args.container_needs:
        names = [n for n, s in SCOPES.items() if args.container_needs in s.needs]
        print(json.dumps(names))
        return 0

    if args.scope is None:
        parser.error("scope is required (or pass --list-scopes / --container-needs)")
    if args.scope not in SCOPES:
        parser.error(f"unknown scope {args.scope!r}; available: {', '.join(SCOPES)}")

    # subprocess.run + sys.exit, not os.execvp: the latter is a real exec on
    # POSIX but spawn+wait+exit on Windows, and a launch failure raises
    # rather than returning an exit code. subprocess.run is platform-neutral
    # and surfaces non-zero exit codes uniformly.
    completed = subprocess.run([sys.executable, *_build_pytest_argv(args.scope)], check=False)
    _ensure_report_for_empty_scope(SCOPES[args.scope], completed.returncode)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
