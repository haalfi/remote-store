"""Shared test helpers."""

from __future__ import annotations

# Re-export from infra._settings so MinIO credentials change in exactly
# one place (infra/.env). Names kept stable for existing callers.
from infra._settings import MINIO_ACCESS_KEY as MINIO_KEY
from infra._settings import MINIO_SECRET_KEY as MINIO_SECRET

__all__ = ["MINIO_KEY", "MINIO_SECRET", "pyarrow_ge_24"]


def pyarrow_ge_24() -> bool:
    """Return True if pyarrow is installed and its major version is >= 24."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return int(version("pyarrow").split(".")[0]) >= 24
    except PackageNotFoundError:
        return False
