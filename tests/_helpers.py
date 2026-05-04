"""Shared test helpers."""

from __future__ import annotations


def pyarrow_ge_24() -> bool:
    """Return True if pyarrow is installed and its major version is >= 24."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return int(version("pyarrow").split(".")[0]) >= 24
    except PackageNotFoundError:
        return False
