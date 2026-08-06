"""What the two tolerant deletes do when the Azure *container* itself is gone.

BE-012 / BE-013, BUG-243. ``missing_ok`` is tolerance for a missing path, and a
container that does not exist holds no path either — so both ``delete`` and
``delete_folder`` return silently under ``missing_ok=True`` and raise
``NotFound`` without it. Before BUG-243 the pair disagreed: ``delete_blob``
surfaces ``ContainerNotFound`` as a plain ``ResourceNotFoundError`` that the
existing ``missing_ok`` branch already swallowed, while ``delete_folder``'s
prefix listing raised the same 404 out of its determinant and past the
tolerance check.

Why this cannot ride on the Azurite fixture
-------------------------------------------

``azurite`` is Docker-gated (``pytest.mark.requires_docker``), so on a machine
without a daemon the Azure half of a cross-backend rule is implemented,
typechecked, and never executed. BK-324 shipped exactly that way and CI found
two real Azure defects behind the gate — both reproducible offline once someone
knew where to look. A ``pytest-httpserver`` stub speaking the Blob wire protocol
removes the gate for this rule: Stage 1, in process, no Docker, no credentials.

Nothing is mocked or patched. The stub answers with genuine
``404 ContainerNotFound`` responses, the Azure SDK raises
``ResourceNotFoundError`` from parsing them, and the backend decides — so the
routing assumption (that a container 404 reaches our mapper as
``ResourceNotFoundError``) is *pinned* rather than asserted, which a patched
client could only assume.

Both axes, sync and async
-------------------------

Tolerance alone is not enough to pin the rule: a backend that simply stopped
raising on the listing's 404 would pass the tolerant cells and silently turn a
strict ``delete_folder`` into a no-op. The ``missing_ok=False`` cells are what
forbid that. The async backend carries its own copy of the non-HNS
``delete_folder`` body, so it gets its own copy of both.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")
pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")
pytest.importorskip("werkzeug", reason="werkzeug not installed")

from remote_store._errors import NotFound, PermissionDenied  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_httpserver import HTTPServer

_ACCOUNT = "devstoreaccount1"
# The published Azurite development key. Not a credential: the stub never
# validates a signature, and this value is in Microsoft's own documentation.
_ACCOUNT_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
_CONTAINER = "absent-container"
_KEY = "folder/object.txt"
_FOLDER = "folder"

_CONTAINER_NOT_FOUND_XML = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b"<Error><Code>ContainerNotFound</Code>"
    b"<Message>The specified container does not exist.</Message></Error>"
)


def _serve_absent_container(httpserver: HTTPServer) -> str:
    """Answer every Blob request the way an absent container does; return the endpoint.

    One canned response covers the whole surface these two operations touch —
    the blob ``DELETE``, the ``restype=container&comp=list`` listing, and the
    blob ``HEAD`` the wrong-type probe spends afterwards. A HEAD response
    carries no body, exactly as on the wire, so the probe sees a bare 404.
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        body = b"" if request.method == "HEAD" else _CONTAINER_NOT_FOUND_XML
        return Response(
            body,
            status=404,
            content_type="application/xml",
            headers={"x-ms-error-code": "ContainerNotFound"},
        )

    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


_AUTH_FAILURE_XML = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b"<Error><Code>AuthorizationPermissionMismatch</Code>"
    b"<Message>This request is not authorized to perform this operation using this permission.</Message></Error>"
)


def _serve_denied(httpserver: HTTPServer) -> str:
    """Answer every Blob request with a genuine 403; return the endpoint.

    The control case for the tolerance above. A denial is not an answer about
    whether the folder is there, so it must reach the caller as
    ``PermissionDenied`` — the determinant may only read the container's *404*
    as "no children".
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        body = b"" if request.method == "HEAD" else _AUTH_FAILURE_XML
        return Response(
            body,
            status=403,
            content_type="application/xml",
            headers={"x-ms-error-code": "AuthorizationPermissionMismatch"},
        )

    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


def _connection_string(endpoint: str) -> str:
    return (
        f"DefaultEndpointsProtocol=http;AccountName={_ACCOUNT};"
        f"AccountKey={_ACCOUNT_KEY};BlobEndpoint={endpoint}/{_ACCOUNT};"
    )


@pytest.fixture
def denied_backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) whose every request is refused with a 403."""
    from remote_store.backends._azure import AzureBackend

    endpoint = _serve_denied(httpserver)
    instance = AzureBackend(
        container=_CONTAINER,
        hns=False,
        connection_string=_connection_string(endpoint),
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
async def denied_async_backend(httpserver: HTTPServer) -> Any:
    """The ``AsyncAzureBackend`` sibling, refused the same way."""
    from remote_store.aio.backends._azure import AsyncAzureBackend

    endpoint = _serve_denied(httpserver)
    instance = AsyncAzureBackend(
        container=_CONTAINER,
        hns=False,
        connection_string=_connection_string(endpoint),
    )
    try:
        yield instance
    finally:
        await instance.aclose()


@pytest.fixture
def backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) bound to a container that does not exist."""
    from remote_store.backends._azure import AzureBackend

    endpoint = _serve_absent_container(httpserver)
    instance = AzureBackend(
        container=_CONTAINER,
        hns=False,
        connection_string=_connection_string(endpoint),
    )
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
async def async_backend(httpserver: HTTPServer) -> Any:
    """The ``AsyncAzureBackend`` sibling, bound to the same absent container."""
    from remote_store.aio.backends._azure import AsyncAzureBackend

    endpoint = _serve_absent_container(httpserver)
    instance = AsyncAzureBackend(
        container=_CONTAINER,
        hns=False,
        connection_string=_connection_string(endpoint),
    )
    try:
        yield instance
    finally:
        await instance.aclose()


class TestAbsentContainerReadsAsAbsentPath:
    """An absent container is an absent path — for both deletes, sync and async."""

    @pytest.mark.spec("BE-012", "BE-021", "AZ-014")
    def test_delete_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete(_KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "AZ-014")
    def test_delete_folder_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete_folder(_FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "AZ-014")
    def test_delete_raises_not_found_when_strict(self, backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            backend.delete(_KEY)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-013", "BE-021", "AZ-014")
    def test_delete_folder_raises_not_found_when_strict(self, backend: Any) -> None:
        """The tolerance belongs to ``missing_ok``, not to the container 404."""
        with pytest.raises(NotFound) as exc_info:
            backend.delete_folder(_FOLDER, recursive=True)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-013")
    async def test_async_delete_tolerates_absent_container(self, async_backend: Any) -> None:
        assert await async_backend.delete(_KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013")
    async def test_async_delete_folder_tolerates_absent_container(self, async_backend: Any) -> None:
        assert await async_backend.delete_folder(_FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-013")
    async def test_async_delete_raises_not_found_when_strict(self, async_backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            await async_backend.delete(_KEY)
        assert exc_info.value.backend == "async-azure"

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013")
    async def test_async_delete_folder_raises_not_found_when_strict(self, async_backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            await async_backend.delete_folder(_FOLDER, recursive=True)
        assert exc_info.value.backend == "async-azure"


class TestDeniedListingIsNotAnAbsentContainer:
    """The determinant's catch stays narrow: a 403 is not an answer about the folder.

    The control case for the tolerance above, and the failure mode worth
    guarding — widening the catch to every ``AzureError`` would make these pass
    silently as clean returns, reporting "nothing to delete" for a folder the
    caller merely cannot see. Both cells go through ``delete_folder``, whose
    determinant is the listing this rule touched; the tolerant form is the one
    that would swallow the denial, so it is the one asserted.
    """

    @pytest.mark.spec("BE-013", "BE-021", "AZ-014")
    def test_denied_listing_raises_permission_denied(self, denied_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            denied_backend.delete_folder(_FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013")
    async def test_async_denied_listing_raises_permission_denied(self, denied_async_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            await denied_async_backend.delete_folder(_FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "async-azure"
