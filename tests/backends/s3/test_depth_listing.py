"""S3 backend depth-limited listing -- DEPTH-003.

The cross-protocol depth-filtering invariant is owned by
`tests/backends/conformance/test_listing.py::TestListFilesCompleteness`,
which parametrizes `list_files(max_depth=…)` over the full fixture
registry (the `s3_moto` fixture covers S3 behaviourally at Stage 2). This
file pins the Stage-1 signature contract for the shared S3 base: every
S3-family backend (`_s3`, `_s3_pyarrow`) inherits `_S3Base.list_files`,
which must declare the `max_depth` keyword per the DEPTH-003 ABC
signature. The check is static, so it needs no SDK and no Docker.

Migrated from tests/test_depth_listing.py (BK-218 / BK-191 slice 3/6).
"""

from __future__ import annotations

import pytest


@pytest.mark.spec("DEPTH-003")
def test_s3_base_accepts_max_depth() -> None:
    """S3 base backend signature accepts max_depth kwarg."""
    import inspect

    from remote_store.backends._s3_base import _S3Base

    sig = inspect.signature(_S3Base.list_files)
    assert "max_depth" in sig.parameters
