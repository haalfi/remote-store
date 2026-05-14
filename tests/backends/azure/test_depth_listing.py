"""Azure backend depth-limited listing -- DEPTH-003.

The behavioural DEPTH-003 invariant for Azure (`list_files(max_depth=…)`
returns files at depth <= N) is owned by
`tests/backends/azure/test_config.py::test_list_files_max_depth`, which
runs against the Azurite emulator at Stage 2. Per spec 037 DEPTH-003,
Azure has no native pruning -- it accepts the parameter and the
Store-level client-side filter does the work.

This file pins the Stage-1 signature contract: `AzureBackend.list_files`
must declare the `max_depth` keyword. The check is static
(`inspect.signature`) and `_azure` imports without the Azure SDK, so it
needs no emulator and no extras -- mirroring
`tests/backends/s3/test_depth_listing.py`.

Migrated from tests/test_depth_listing.py (BK-218 / BK-191 slice 3/6).
"""

from __future__ import annotations

import pytest


@pytest.mark.spec("DEPTH-003")
def test_azure_accepts_max_depth() -> None:
    """Azure backend signature accepts max_depth kwarg."""
    import inspect

    from remote_store.backends._azure import AzureBackend

    sig = inspect.signature(AzureBackend.list_files)
    assert "max_depth" in sig.parameters
