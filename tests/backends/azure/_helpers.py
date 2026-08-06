"""Stage-1 Azure Blob wire stubs, shared by the sync and async deviation suites.

TEST-003 splits sync and async backend-specific tests into separate files; this
is the ``_helpers`` module that clause names as the home for logic both halves
need. Everything here is transport setup — no assertions and no test bodies.

Why a wire stub rather than the ``azurite`` fixture
---------------------------------------------------

``azurite`` is Docker-gated (``pytest.mark.requires_docker``), so on a machine
without a daemon the Azure half of a cross-backend rule is implemented,
typechecked, and never executed. BK-324 shipped exactly that way and CI found
two real Azure defects behind the gate, both reproducible offline once someone
knew where to look. A ``pytest-httpserver`` stub speaking the Blob wire protocol
removes the gate: Stage 1, in process, no Docker, no credentials.

Nothing is mocked or patched. The stubs answer with genuine 404 / 403 responses,
the Azure SDK raises ``ResourceNotFoundError`` / ``HttpResponseError`` from
parsing them, and the backend decides — so the routing assumption (that a
container 404 reaches our mapper as ``ResourceNotFoundError``) is *pinned*
rather than asserted, which a patched client could only assume.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer

ACCOUNT = "devstoreaccount1"
# The published Azurite development key. Not a credential: the stubs never
# validate a signature, and this value is in Microsoft's own documentation.
ACCOUNT_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
CONTAINER = "absent-container"
KEY = "folder/object.txt"
FOLDER = "folder"

_CONTAINER_NOT_FOUND_XML = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b"<Error><Code>ContainerNotFound</Code>"
    b"<Message>The specified container does not exist.</Message></Error>"
)
_AUTH_FAILURE_XML = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b"<Error><Code>AuthorizationPermissionMismatch</Code>"
    b"<Message>This request is not authorized to perform this operation using this permission.</Message></Error>"
)


def _serve_all(httpserver: HTTPServer, *, status: int, error_code: str, body: bytes) -> str:
    """Answer every Blob request with one canned error; return the endpoint.

    One response covers the whole surface the two deletes touch — the blob
    ``DELETE``, the ``restype=container&comp=list`` listing, and the blob
    ``HEAD`` the wrong-type probe spends afterwards. A HEAD response carries no
    body, exactly as on the wire, so a probe sees a bare status.
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        return Response(
            b"" if request.method == "HEAD" else body,
            status=status,
            content_type="application/xml",
            headers={"x-ms-error-code": error_code},
        )

    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


def serve_absent_container(httpserver: HTTPServer) -> str:
    """Answer every Blob request the way an absent container does."""
    return _serve_all(
        httpserver,
        status=404,
        error_code="ContainerNotFound",
        body=_CONTAINER_NOT_FOUND_XML,
    )


def serve_denied(httpserver: HTTPServer) -> str:
    """Answer every Blob request with a genuine 403.

    The control case for the absent-container tolerance. A denial is not an
    answer about whether the folder is there, so it must reach the caller as
    ``PermissionDenied``: the determinant may read only the container's *404*
    as "no children".
    """
    return _serve_all(
        httpserver,
        status=403,
        error_code="AuthorizationPermissionMismatch",
        body=_AUTH_FAILURE_XML,
    )


def connection_string(endpoint: str) -> str:
    """A Blob connection string pointing at a local stub endpoint."""
    return (
        f"DefaultEndpointsProtocol=http;AccountName={ACCOUNT};"
        f"AccountKey={ACCOUNT_KEY};BlobEndpoint={endpoint}/{ACCOUNT};"
    )
