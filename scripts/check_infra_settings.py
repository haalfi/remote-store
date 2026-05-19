"""Drift-check that ``infra/.env`` remains the single source of truth.

Three independent gates:

1. ``infra/.env`` parses cleanly and has the keys ``infra/_settings.py``
   expects.
2. ``infra/_settings.py`` imports without error and exposes the documented
   constants.
3. The compose file and CI workflows contain no literal ``-p N:M`` port
   mappings. Every host-side port must reference an env var sourced from
   ``infra/.env`` (e.g. ``-p ${MINIO_HOST_PORT}:9000``).

Wired into ``hatch run lint`` and the lint job in ``.github/workflows/ci.yml``.
"""

from __future__ import annotations

import contextlib
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / "infra" / ".env"
_COMPOSE_FILE = _ROOT / "infra" / "docker-compose.yml"

# CI files that spawn backends with raw ``docker run -p ...``. Each must
# source ``infra/.env`` and reference variables, not literals.
_CI_FILES = (
    _ROOT / ".github" / "actions" / "start-backends" / "action.yml",
    _ROOT / ".github" / "workflows" / "mutation.yml",
    _ROOT / ".github" / "workflows" / "publish.yml",
)

# Keys the Python loader requires. Kept in sync with infra/_settings.py.
_REQUIRED_KEYS = (
    "MINIO_HOST",
    "MINIO_HOST_PORT",
    "MINIO_CONSOLE_HOST_PORT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "AZURITE_HOST",
    "AZURITE_HOST_PORT",
    "SFTP_HOST",
    "SFTP_HOST_PORT",
    "SFTP_USER",
    "SFTP_PASS",
    "LEGACY_SFTP_HOST",
    "LEGACY_SFTP_HOST_PORT",
    "LEGACY_SFTP_USER",
    "LEGACY_SFTP_PASS",
    "TOXIPROXY_HOST",
    "TOXIPROXY_API_PORT",
    "TOXIPROXY_MINIO_PORT",
    "TOXIPROXY_SFTP_PORT",
    "TOXIPROXY_AZURITE_PORT",
)

# Matches ``-p 9000:9000`` (literal host:container). The variable form
# ``-p ${MINIO_HOST_PORT}:9000`` and ``-p "${VAR}:9000"`` contains a $ and
# is not flagged.
_LITERAL_DASH_P = re.compile(r"-p\s+\d+:\d+")


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            msg = f"{path}:{lineno}: missing '=' in '{raw}'"
            raise ValueError(msg)
        key = key.strip()
        if key in values:
            msg = f"{path}:{lineno}: duplicate key {key!r}"
            raise ValueError(msg)
        values[key] = value.strip()
    return values


def check_env_file() -> list[str]:
    """Gate 1: ``infra/.env`` parses and has the required keys."""
    if not _ENV_FILE.is_file():
        return [f"{_ENV_FILE}: not found"]
    try:
        values = _parse_env(_ENV_FILE)
    except ValueError as exc:
        return [str(exc)]
    missing = [k for k in _REQUIRED_KEYS if k not in values]
    if missing:
        return [f"{_ENV_FILE}: missing required keys: {', '.join(missing)}"]
    return []


def check_python_loader() -> list[str]:
    """Gate 2: ``infra/_settings.py`` imports and exposes documented constants."""
    sys.path.insert(0, str(_ROOT))
    try:
        from infra import _settings
    except Exception as exc:  # noqa: BLE001 — surface every import failure
        return [f"infra/_settings.py: import failed: {exc}"]
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(str(_ROOT))
    missing = [
        name
        for name in ("MINIO_PORT", "MINIO_ENDPOINT", "AZURITE_PORT", "SFTP_PORT", "TOXIPROXY_MINIO_PORT")
        if not hasattr(_settings, name)
    ]
    if missing:
        return [f"infra/_settings.py: missing attributes: {', '.join(missing)}"]
    return []


def check_compose_no_port_literals() -> list[str]:
    """Gate 3a: compose file ``ports:`` entries must reference env vars."""
    if not _COMPOSE_FILE.is_file():
        return [f"{_COMPOSE_FILE}: not found"]
    violations: list[str] = []
    ports_indent: int | None = None  # indent of the ``ports:`` key when in a block
    for lineno, raw in enumerate(_COMPOSE_FILE.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        indent = len(stripped) - len(stripped.lstrip())
        if ports_indent is not None and indent <= ports_indent:
            # Same- or shallower-indent line ends the ports block.
            ports_indent = None
        match = re.match(r"^(\s*)ports:\s*$", raw)
        if match:
            ports_indent = len(match.group(1))
            continue
        if ports_indent is None:
            continue
        content = stripped.lstrip()
        if content.startswith("-") and "$" not in content:
            violations.append(
                f"{_COMPOSE_FILE}:{lineno}: literal port in ports list ('{content}'); use ${{VAR}} from infra/.env"
            )
    return violations


def check_ci_no_dash_p_literals() -> list[str]:
    """Gate 3b: CI workflows must use ``-p $VAR:N``, not ``-p N:N``."""
    violations: list[str] = []
    for path in _CI_FILES:
        if not path.is_file():
            violations.append(f"{path}: not found")
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _LITERAL_DASH_P.finditer(raw):
                violations.append(
                    f"{path}:{lineno}: literal port mapping '{match.group(0)}'; source infra/.env and use $VAR"
                )
    return violations


def main() -> int:
    violations: list[str] = []
    violations += check_env_file()
    violations += check_python_loader()
    violations += check_compose_no_port_literals()
    violations += check_ci_no_dash_p_literals()
    if violations:
        for v in violations:
            sys.stderr.write(f"error: {v}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
