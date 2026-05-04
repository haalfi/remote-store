"""Shared test helpers for the backends suite.

Single source of truth for pyarrow version checks consumed by `conftest.py`
and the per-backend test modules. Defining the helper here (rather than in
`conftest.py`) keeps it importable as a normal module and avoids the
upward-import gotcha that conftest plays poorly with.
"""

from __future__ import annotations


def pyarrow_ge_24() -> bool:
    """True when the installed pyarrow major version is 24 or higher.

    Returns False if pyarrow is not installed. Used to gate moto-backed
    S3-PyArrow tests off pyarrow 24 (BK-172) — moto's `ThreadedMotoServer`
    returns a `CompleteMultipartUpload` response shape that pyarrow 24's
    C++ S3 client rejects as `INTERNAL_FAILURE`.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        return int(version("pyarrow").split(".")[0]) >= 24
    except PackageNotFoundError:
        return False
