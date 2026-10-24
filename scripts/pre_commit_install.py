"""Install the pre-commit framework's hook into ``.git/hooks`` while ``core.hooksPath`` is set.

``pre-commit install`` refuses while ``core.hooksPath`` is set ("Cowardly refusing
to install hooks"), and the agent gates set it to ``.githooks/`` (BK-486).
``.githooks/pre-commit`` chains to ``.git/hooks/pre-commit``, so the framework's
hook belongs there. This runs ``pre-commit install`` with ``core.hooksPath``
blanked for that one process through git's ``GIT_CONFIG_COUNT`` (git 2.31+),
which makes it install into ``.git/hooks`` and leaves the repository's setting
as it is (measured). Extra arguments are passed through.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    """Run ``pre-commit install`` with ``core.hooksPath`` blanked; return its exit code."""
    args = sys.argv[1:] if argv is None else argv
    env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0="")
    return subprocess.call(["pre-commit", "install", *args], env=env)


if __name__ == "__main__":
    sys.exit(main())
