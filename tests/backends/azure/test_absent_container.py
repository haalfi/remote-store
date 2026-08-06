"""What the two tolerant deletes do when the Azure *container* itself is gone.

BE-012 / BE-013. ``missing_ok`` is tolerance for a missing path, and a container
that does not exist holds no path either — so both ``delete`` and
``delete_folder`` return silently under ``missing_ok=True`` and raise
``NotFound`` without it. Before this rule the pair disagreed: ``delete_blob``
surfaces ``ContainerNotFound`` as a plain ``ResourceNotFoundError`` that the
existing ``missing_ok`` branch already swallowed, while ``delete_folder``'s
prefix listing raised the same 404 out of its determinant and past the
tolerance check.

Sync half. The async twin carries its own copy of the non-HNS ``delete_folder``
body and so gets its own file, ``aio/test_absent_container.py`` (TEST-003); the
wire stubs both use live in ``.._helpers``, which also explains why this runs on
a stub rather than the Docker-gated ``azurite`` fixture.

Both axes are asserted, not just tolerance: a backend that simply stopped
raising on the listing's 404 would pass the tolerant cells and silently turn a
strict ``delete_folder`` into a no-op. The ``missing_ok=False`` cells forbid
that, and ``TestDeniedListingIsNotAnAbsentContainer`` forbids the other
overshoot — widening the catch past the container's own 404.
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
    from collections.abc import Iterator

    from pytest_httpserver import HTTPServer


def _backend_at(endpoint: str) -> Any:
    from remote_store.backends._azure import AzureBackend

    return AzureBackend(container=CONTAINER, hns=False, connection_string=connection_string(endpoint))


@pytest.fixture
def backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) bound to a container that does not exist."""
    instance = _backend_at(serve_absent_container(httpserver))
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def denied_backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) whose every request is refused with a 403."""
    instance = _backend_at(serve_denied(httpserver))
    try:
        yield instance
    finally:
        instance.close()


class TestAbsentContainerReadsAsAbsentPath:
    """An absent container is an absent path, for both deletes."""

    @pytest.mark.spec("BE-012", "BE-021", "AZ-025")
    def test_delete_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete(KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "AZ-015")
    def test_delete_folder_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete_folder(FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "AZ-025", "AZ-026")
    def test_delete_raises_not_found_when_strict(self, backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            backend.delete(KEY)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-013", "BE-021", "AZ-015", "AZ-026")
    def test_delete_folder_raises_not_found_when_strict(self, backend: Any) -> None:
        """The tolerance belongs to ``missing_ok``, not to the container 404."""
        with pytest.raises(NotFound) as exc_info:
            backend.delete_folder(FOLDER, recursive=True)
        assert exc_info.value.backend == "azure"


class TestDeniedListingIsNotAnAbsentContainer:
    """The determinant's catch stays narrow: a 403 is not an answer about the folder.

    The control case for the tolerance above, and the failure mode worth
    guarding — widening the catch to every ``AzureError`` would make this pass
    silently as a clean return, reporting "nothing to delete" for a folder the
    caller merely cannot see. It goes through ``delete_folder``, whose
    determinant is the listing this rule touched, in its tolerant form: that is
    the one that would swallow the denial.
    """

    @pytest.mark.spec("BE-013", "BE-021", "AZ-025", "AZ-026")
    def test_denied_listing_raises_permission_denied(self, denied_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            denied_backend.delete_folder(FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "azure"
