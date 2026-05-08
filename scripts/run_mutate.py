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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mutate_scopes import SCOPES  # noqa: E402


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

    os.execvp(sys.executable, [sys.executable, *_build_pytest_argv(args.scope)])
    return 0  # unreachable; execvp replaces the process


if __name__ == "__main__":
    sys.exit(main())
