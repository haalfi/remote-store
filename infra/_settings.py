"""Single-source infra settings loader.

Reads ``infra/.env`` once at import time and exposes typed constants for
the test suite, benchmarks, and any other Python caller. The same file is
auto-loaded by ``docker compose -f infra/docker-compose.yml`` for variable
substitution, and sourced by CI workflows before they invoke
``docker run``. One file, three readers, zero drift.

Environment variables win over the file. A test that needs to override a
port for one run can ``MINIO_HOST_PORT=12345 pytest ...``; the file value
acts as the default. This preserves the override path that the old
``BENCH_*`` / ``E2E_*`` env vars used to provide.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _parse_env(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE file with ``#`` comments. Stdlib only."""
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


_FILE_VALUES: dict[str, str] = _parse_env(_ENV_FILE)


def _get(name: str) -> str:
    """Return ``os.environ[name]`` if set, otherwise the file value."""
    env = os.environ.get(name)
    if env is not None and env != "":
        return env
    if name not in _FILE_VALUES:
        msg = f"infra/.env: missing required key {name!r}"
        raise KeyError(msg)
    return _FILE_VALUES[name]


# MinIO ----------------------------------------------------------------------
MINIO_HOST: str = _get("MINIO_HOST")
MINIO_PORT: int = int(_get("MINIO_HOST_PORT"))
MINIO_CONSOLE_PORT: int = int(_get("MINIO_CONSOLE_HOST_PORT"))
MINIO_ACCESS_KEY: str = _get("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY: str = _get("MINIO_SECRET_KEY")
MINIO_ENDPOINT: str = f"http://{MINIO_HOST}:{MINIO_PORT}"

# Azurite --------------------------------------------------------------------
AZURITE_HOST: str = _get("AZURITE_HOST")
AZURITE_PORT: int = int(_get("AZURITE_HOST_PORT"))

# Public Azurite key, baked into the emulator. Same constant used everywhere
# the test suite needs an Azurite connection string.
_AZURITE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

AZURITE_CONN_STR: str = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    f"AccountKey={_AZURITE_KEY};"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
)

# SFTP -----------------------------------------------------------------------
SFTP_HOST: str = _get("SFTP_HOST")
SFTP_PORT: int = int(_get("SFTP_HOST_PORT"))
SFTP_USER: str = _get("SFTP_USER")
SFTP_PASS: str = _get("SFTP_PASS")

LEGACY_SFTP_HOST: str = _get("LEGACY_SFTP_HOST")
LEGACY_SFTP_PORT: int = int(_get("LEGACY_SFTP_HOST_PORT"))
LEGACY_SFTP_USER: str = _get("LEGACY_SFTP_USER")
LEGACY_SFTP_PASS: str = _get("LEGACY_SFTP_PASS")

# Toxiproxy ------------------------------------------------------------------
TOXIPROXY_HOST: str = _get("TOXIPROXY_HOST")
TOXIPROXY_API_PORT: int = int(_get("TOXIPROXY_API_PORT"))
TOXIPROXY_MINIO_PORT: int = int(_get("TOXIPROXY_MINIO_PORT"))
TOXIPROXY_SFTP_PORT: int = int(_get("TOXIPROXY_SFTP_PORT"))
TOXIPROXY_AZURITE_PORT: int = int(_get("TOXIPROXY_AZURITE_PORT"))

TOXIPROXY_MINIO_ENDPOINT: str = f"http://{TOXIPROXY_HOST}:{TOXIPROXY_MINIO_PORT}"

TOXIPROXY_AZURITE_CONN_STR: str = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    f"AccountKey={_AZURITE_KEY};"
    f"BlobEndpoint=http://{TOXIPROXY_HOST}:{TOXIPROXY_AZURITE_PORT}/devstoreaccount1;"
)
