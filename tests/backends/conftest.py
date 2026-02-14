"""Backend test fixtures — parameterized for conformance testing."""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING

import pytest

from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


@pytest.fixture(params=["local"])
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Parameterized backend fixture. Add new backends here."""
    if request.param == "local":
        with tempfile.TemporaryDirectory() as tmp:
            yield LocalBackend(root=tmp)
    else:
        pytest.skip(f"Unknown backend: {request.param}")
