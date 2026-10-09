"""Tests for .claude/hooks/ruff-format.sh, the PostToolUse formatter (BUG-314).

The hook runs after every Edit and Write. Its ``ruff check --fix`` must not
apply F401: an import is often added one edit before the code that uses it, and
removing it in between leaves a ``NameError`` behind. Unused imports stay the
``lint`` gate's job, which runs ``ruff check`` without ``--fix``.

The hook runs for real, with real ``bash``, ``jq`` and ``ruff`` (``sdd/TESTING.md``
Rule 6): a stub could not tell which fixes ruff applies. All three are required,
so a missing one fails rather than skips, because a skipped test reads as a pass
(``sdd/TESTING.md`` § A green test can be vacuous). Files are written to
``tmp_path``, outside the repo, so ruff runs its default rule set, which selects
F401 and treats it as fixable, as the repo's own ``select`` does.

Not marked ``os_sensitive``: what is pinned is which fixes ruff applies, which
does not vary by OS, and ``tooling-tests`` runs this module on every
``.claude/hooks/`` change.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "ruff-format.sh"

# Resolved through PATH, not left to the OS: on Windows, CreateProcess searches
# System32 before PATH and a bare "bash" runs WSL's launcher instead of the Git
# Bash that Claude Code runs hooks with.
BASH = shutil.which("bash") or "bash"


def _run_hook(target: Path) -> None:
    missing = [name for name in ("bash", "jq", "ruff") if shutil.which(name) is None]
    if missing:
        pytest.fail(f"not on PATH: {', '.join(missing)}; the hook needs them, and a skip would read as a pass")
    # Claude Code passes the absolute, platform-native path, so the test does too.
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(target)}})
    result = subprocess.run(
        [BASH, HOOK.as_posix()], input=payload, capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_hook_keeps_an_import_whose_use_is_not_written_yet(tmp_path: Path) -> None:
    target = tmp_path / "mid_edit.py"
    target.write_text("import json\n", encoding="utf-8")

    _run_hook(target)

    assert target.read_text(encoding="utf-8") == "import json\n"


def test_hook_still_formats_and_applies_other_fixes(tmp_path: Path) -> None:
    # Positive control: without it, a hook that silently stopped running ruff
    # would pass the test above. F541 (f-string without placeholders) is a safe
    # fix in the default rule set; `x=` exercises the formatter.
    target = tmp_path / "other.py"
    target.write_text('import json\nx=f"plain"\n', encoding="utf-8")

    _run_hook(target)

    text = target.read_text(encoding="utf-8")
    assert "import json\n" in text
    assert 'x = "plain"\n' in text
