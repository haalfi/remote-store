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


_ONE_BLOB_THEN_MORE = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<EnumerationResults ServiceEndpoint="http://127.0.0.1/" ContainerName="' + CONTAINER.encode() + b'">'
    b"<Blobs><Blob><Name>folder/object.txt</Name><Properties>"
    b"<Last-Modified>Mon, 01 Jan 2026 00:00:00 GMT</Last-Modified>"
    b"<Content-Length>3</Content-Length><Etag>abc</Etag>"
    b"<BlobType>BlockBlob</BlobType></Properties></Blob></Blobs>"
    b"<NextMarker>M2</NextMarker></EnumerationResults>"
)


# The mirror shape: a first page of one common prefix and no blob. Ordinary
# rather than contrived — a container organised into folders returns exactly this
# from ``walk_blobs`` — and the shape an item-keyed bound goes blind on.
_ONE_PREFIX_THEN_MORE = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<EnumerationResults ServiceEndpoint="http://127.0.0.1/" ContainerName="' + CONTAINER.encode() + b'">'
    b"<Delimiter>/</Delimiter>"
    b"<Blobs><BlobPrefix><Name>folder/</Name></BlobPrefix></Blobs>"
    b"<NextMarker>M2</NextMarker></EnumerationResults>"
)


def serve_container_vanishing_mid_listing(httpserver: HTTPServer, *, page_one: bytes = _ONE_BLOB_THEN_MORE) -> str:
    """One good page carrying a ``NextMarker``, then ``ContainerNotFound``.

    The shape that separates "the container was never there" from "the container
    went away underneath the scan". The first page must carry real content: a
    stub that 404s immediately would pass under an unbounded tolerance too, and
    prove nothing about the bound.

    ``page_one`` selects that content: a blob by default, a common prefix with
    ``_ONE_PREFIX_THEN_MORE``. Each listing must meet the shape *it* discards
    entirely — see ``MID_SCAN_BLIND_PAGES``.
    """
    from werkzeug.wrappers import Response

    state = {"lists": 0}

    def handler(request: Any) -> Any:
        if request.method == "HEAD":
            return Response(b"", status=404, content_type="application/xml")
        state["lists"] += 1
        if state["lists"] == 1:
            return Response(page_one, status=200, content_type="application/xml")
        return Response(
            _CONTAINER_NOT_FOUND_XML,
            status=404,
            content_type="application/xml",
            headers={"x-ms-error-code": "ContainerNotFound"},
        )

    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


# Each listing paired with the page-one shape that yields it nothing — the pairs
# an item-keyed bound is blind on. ``iter_children`` yields both kinds, so it has
# no blind shape and takes the blob page as its control.
MID_SCAN_BLIND_PAGES: dict[str, bytes] = {
    "list_files": _ONE_PREFIX_THEN_MORE,
    "list_files-recursive": _ONE_PREFIX_THEN_MORE,
    "list_folders": _ONE_BLOB_THEN_MORE,
    "iter_children": _ONE_BLOB_THEN_MORE,
    "glob": _ONE_PREFIX_THEN_MORE,
}


def connection_string(endpoint: str) -> str:
    """A Blob connection string pointing at a local stub endpoint."""
    return (
        f"DefaultEndpointsProtocol=http;AccountName={ACCOUNT};"
        f"AccountKey={ACCOUNT_KEY};BlobEndpoint={endpoint}/{ACCOUNT};"
        f"DfsEndpoint={endpoint}/{ACCOUNT};"
    )


# --- HNS (ADLS Gen2) ---------------------------------------------------------
#
# ADLS Gen2's ``List Path`` is an ordinary JSON REST call, so the same stub
# technique the flat lane uses reaches the HNS branches: Stage 1, in process, no
# Docker. Those branches were argued rather than executed for the whole of
# BUG-246, on the false premise that only the Docker-gated fixture could reach
# them (BUG-246, verification pass 2).

_FILESYSTEM_NOT_FOUND_JSON = (
    b'{"error":{"code":"FilesystemNotFound","message":"The specified filesystem does not exist."}}'
)

# A page of one directory, and a page of one file: ``list_folders`` discards
# files, ``list_files`` and ``glob`` discard directories.
_HNS_DIR_PAGE = b'{"paths":[{"name":"folder","isDirectory":"true","lastModified":"Mon, 01 Jan 2026 00:00:00 GMT"}]}'
_HNS_FILE_PAGE = (
    b'{"paths":[{"name":"folder/object.txt","contentLength":"3","etag":"abc",'
    b'"lastModified":"Mon, 01 Jan 2026 00:00:00 GMT"}]}'
)

HNS_MID_SCAN_BLIND_PAGES: dict[str, bytes] = {
    "list_files": _HNS_DIR_PAGE,
    "list_files-recursive": _HNS_DIR_PAGE,
    "list_folders": _HNS_FILE_PAGE,
    "iter_children": _HNS_FILE_PAGE,
    "glob": _HNS_DIR_PAGE,
}


def _serve_hns(httpserver: HTTPServer, handler: Any) -> str:
    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


def serve_hns_absent_filesystem(httpserver: HTTPServer) -> str:
    """Answer every ADLS Gen2 request the way an absent filesystem does."""
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        return Response(
            b"" if request.method == "HEAD" else _FILESYSTEM_NOT_FOUND_JSON,
            status=404,
            content_type="application/json",
            headers={"x-ms-error-code": "FilesystemNotFound"},
        )

    return _serve_hns(httpserver, handler)


def serve_hns_denied(httpserver: HTTPServer) -> str:
    """Answer every ADLS Gen2 request with a genuine 403.

    The narrowness control for the HNS half: a denial is not an answer about
    whether the folder is there, so the mid-scan guard must not read it as one.
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        return Response(
            b"" if request.method == "HEAD" else _AUTH_FAILURE_XML,
            status=403,
            content_type="application/json",
            headers={"x-ms-error-code": "AuthorizationPermissionMismatch"},
        )

    return _serve_hns(httpserver, handler)


def serve_hns_filesystem_vanishing_mid_listing(httpserver: HTTPServer, *, page_one: bytes = _HNS_FILE_PAGE) -> str:
    """One good ``List Path`` page carrying a continuation, then ``FilesystemNotFound``.

    ``x-ms-continuation`` is what makes the SDK ask for a second page; without it
    the listing ends before the deletion can be observed.
    """
    from werkzeug.wrappers import Response

    state = {"lists": 0}

    def handler(request: Any) -> Any:
        if request.method == "HEAD":
            return Response(b"", status=404, content_type="application/json")
        state["lists"] += 1
        if state["lists"] == 1:
            return Response(
                page_one,
                status=200,
                content_type="application/json",
                headers={"x-ms-continuation": "C2"},
            )
        return Response(
            _FILESYSTEM_NOT_FOUND_JSON,
            status=404,
            content_type="application/json",
            headers={"x-ms-error-code": "FilesystemNotFound"},
        )

    return _serve_hns(httpserver, handler)
