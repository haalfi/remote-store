"""Async twin of the absent-container deviation suite.

BE-012 / BE-013, ASYNC-012 / ASYNC-013. ``AsyncAzureBackend`` carries its own
copy of the non-HNS ``delete_folder`` body rather than delegating to the sync
one, so the rule needs its own copy of the assertions — a sync-only suite would
have passed while the async twin still raised. It did, on the first run.

See the sync sibling (``../test_absent_container.py``) for the rule and why it
is decided this way round, and ``.._helpers`` for the wire stubs both use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")
pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")
pytest.importorskip("werkzeug", reason="werkzeug not installed")

from remote_store._errors import NotFound, PermissionDenied  # noqa: E402
from tests.backends.azure._helpers import (  # noqa: E402
    CONTAINER,
    FOLDER,
    KEY,
    connection_string,
    serve_absent_container,
    serve_denied,
)

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer


def _backend_at(endpoint: str) -> Any:
    from remote_store.aio.backends._azure import AsyncAzureBackend

    return AsyncAzureBackend(container=CONTAINER, hns=False, connection_string=connection_string(endpoint))


@pytest.fixture
async def backend(httpserver: HTTPServer) -> Any:
    """An ``AsyncAzureBackend`` (non-HNS) bound to a container that does not exist."""
    instance = _backend_at(serve_absent_container(httpserver))
    try:
        yield instance
    finally:
        await instance.aclose()


@pytest.fixture
async def denied_backend(httpserver: HTTPServer) -> Any:
    """An ``AsyncAzureBackend`` (non-HNS) whose every request is refused with a 403."""
    instance = _backend_at(serve_denied(httpserver))
    try:
        yield instance
    finally:
        await instance.aclose()


class TestAbsentContainerReadsAsAbsentPath:
    """An absent container is an absent path, for both deletes."""

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-012")
    async def test_delete_tolerates_absent_container(self, backend: Any) -> None:
        assert await backend.delete(KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013")
    async def test_delete_folder_tolerates_absent_container(self, backend: Any) -> None:
        assert await backend.delete_folder(FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-012", "AZ-026")
    async def test_delete_raises_not_found_when_strict(self, backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            await backend.delete(KEY)
        assert exc_info.value.backend == "async-azure"

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013", "AZ-026")
    async def test_delete_folder_raises_not_found_when_strict(self, backend: Any) -> None:
        """The tolerance belongs to ``missing_ok``, not to the container 404."""
        with pytest.raises(NotFound) as exc_info:
            await backend.delete_folder(FOLDER, recursive=True)
        assert exc_info.value.backend == "async-azure"


class TestDeniedListingIsNotAnAbsentContainer:
    """The determinant's catch stays narrow: a 403 is not an answer about the folder.

    Async half of the control case. The async determinant has its own
    ``_achildren_or_absent_container`` re-raise branch, so this is the cell that
    executes it — without this test that branch is unreached code.
    """

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013", "AZ-026")
    async def test_denied_listing_raises_permission_denied(self, denied_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            await denied_backend.delete_folder(FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "async-azure"
