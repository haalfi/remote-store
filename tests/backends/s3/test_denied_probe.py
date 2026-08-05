"""A real 403 on an S3 *type probe* maps to ``PermissionDenied``, never ``NotFound``.

BE-021. BK-324 promoted the narrow type probes
(``_S3Base._s3_is_object`` / ``_s3_has_children``) from error-path-only
helpers to the **existence determinant** at the head of ``delete``,
``delete_folder``, the ``move``/``copy`` source and ``get_folder_info``,
replacing the ``s3fs.exists`` call those operations used before. The probes
swallowed every SDK error, so an ACL denial — which ``s3fs`` surfaces as
``PermissionError``, an ``OSError`` — was reported to the caller as
``NotFound``: "the object is absent" for an object that exists and the caller
cannot see. This module pins both halves of the corrected split.

Why this cannot ride on the moto fixtures
-----------------------------------------

moto enforces neither IAM nor credential validity, so a 403 is unreachable
in-process — which is why ``_s3fs_errors``' ``PermissionError`` branch carries
``# pragma: no cover -- moto doesn't raise PermissionError``. A moto-only test
would have stayed green through the whole regression.

How a real 403 is produced without AWS
--------------------------------------

A ``pytest-httpserver`` stub speaking the S3 wire protocol: it answers the
control-path requests with genuine ``403 AccessDenied`` / ``404 NoSuchKey``
bodies. Nothing is mocked or patched — botocore parses the status, s3fs's
``translate_boto_error`` maps it, and the backend decides. The stub therefore
also pins the *routing* assumption (that a 403 on ``HeadObject`` /
``ListObjectsV2`` reaches our mapper as ``PermissionError``) rather than
asserting it, which a patched ``call_s3`` could only assume. Stage 1: in
process, no Docker, no credentials.

The two postures, and why the second test exists
------------------------------------------------

* **Determinant** (``TestProbeDenialIsPermissionDenied``): the probe *is* the
  answer, so a failure must propagate. Swallowing invents a verdict.
* **Error path** (``TestErrorPathProbeStaysFailOpen``): the probe runs only
  after the operation already failed, purely to reclassify. Swallowing keeps
  the operation's own truthful error standing rather than replacing it with a
  transport error. Making *everything* strict would regress this half, so it is
  asserted, not assumed.

``S3Boto3Backend`` is parametrized alongside the two s3fs backends. It never
regressed — its ``_head_or_none`` / ``_prefix_has_children`` are strict and the
swallowing closures live inside its ``_reject_*`` pair — so it doubles as the
in-suite positive control for the shape the other two now match.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("s3fs", reason="s3fs not installed")
pytest.importorskip("boto3", reason="boto3 not installed")
pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")
pytest.importorskip("werkzeug", reason="werkzeug not installed")

from remote_store._errors import NotFound, PermissionDenied  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_httpserver import HTTPServer

    from remote_store._backend import Backend


_BUCKET = "denied-probe"
_KEY = "folder/object.txt"
_FOLDER = "folder"

_ACCESS_DENIED_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message>"
    b"<RequestId>rq</RequestId><HostId>hi</HostId></Error>"
)
_NO_SUCH_KEY_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<Error><Code>NoSuchKey</Code><Message>The specified key does not exist.</Message>"
    b"<RequestId>rq</RequestId><HostId>hi</HostId></Error>"
)
_EMPTY_LISTING_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    b"<Name>" + _BUCKET.encode() + b"</Name><Prefix>folder/</Prefix>"
    b"<KeyCount>0</KeyCount><MaxKeys>1</MaxKeys><IsTruncated>false</IsTruncated>"
    b"</ListBucketResult>"
)

_S3 = "remote_store.backends._s3:S3Backend"
_S3PA = "remote_store.backends._s3_pyarrow:S3PyArrowBackend"
_S3B3 = "remote_store.backends._s3_boto3:S3Boto3Backend"

_BACKEND_NAMES = {_S3: "s3", _S3PA: "s3-pyarrow", _S3B3: "s3-boto3"}

_BACKEND_PARAMS = [
    pytest.param(_S3, id="s3", marks=pytest.mark.spec("BE-021", "S3-016")),
    pytest.param(_S3PA, id="s3-pyarrow", marks=pytest.mark.spec("BE-021", "S3PA-018", "S3PA-019")),
    pytest.param(_S3B3, id="s3-boto3", marks=pytest.mark.spec("BE-021", "S3-016")),
]

# Every operation BK-324 rewired onto a type probe, grouped by which request is
# its *determinant*: the object HEAD for the file-shaped ones, the prefix
# listing for the folder-shaped ones. The fail-open tests deny the other one.
_FILE_SHAPED_OPS: dict[str, Callable[[Backend], Any]] = {
    "delete": lambda b: b.delete(_KEY),
    "move-src": lambda b: b.move(_KEY, "folder/moved.txt"),
    "copy-src": lambda b: b.copy(_KEY, "folder/copied.txt"),
}
_FOLDER_SHAPED_OPS: dict[str, Callable[[Backend], Any]] = {
    "delete_folder": lambda b: b.delete_folder(_FOLDER, recursive=True),
    "get_folder_info": lambda b: b.get_folder_info(_FOLDER),
}
# The idempotent-delete idiom, split out because its clean-return outcome needs
# a different assertion. Value: which request the operation's determinant is,
# expressed as the (object_denied, listing_denied) stub the fail-open case needs.
_TOLERANT_OPS: dict[str, tuple[Callable[[Backend], Any], bool, bool]] = {
    "delete-missing-ok": (lambda b: b.delete(_KEY, missing_ok=True), False, True),
    "delete_folder-missing-ok": (
        lambda b: b.delete_folder(_FOLDER, recursive=True, missing_ok=True),
        True,
        False,
    ),
}
_ALL_OPS: dict[str, Callable[[Backend], Any]] = {
    **_FILE_SHAPED_OPS,
    **_FOLDER_SHAPED_OPS,
    **{name: call for name, (call, _o, _l) in _TOLERANT_OPS.items()},
}


def _is_listing(request: Any) -> bool:
    """``True`` for a ``ListObjectsV2`` request (the prefix probe)."""
    return "list-type" in request.args


def _serve_s3_stub(httpserver: HTTPServer, *, object_denied: bool, listing_denied: bool) -> str:
    """Answer every S3 request with a canned status; return the endpoint URL.

    ``HeadObject`` answers 403 ``AccessDenied`` or 404 ``NoSuchKey``;
    ``ListObjectsV2`` answers 403 ``AccessDenied`` or an empty 200 listing.
    Those four combinations are the whole matrix the probes can face.
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        denied = listing_denied if _is_listing(request) else object_denied
        if denied:
            return Response(_ACCESS_DENIED_XML, status=403, content_type="application/xml")
        if _is_listing(request):
            return Response(_EMPTY_LISTING_XML, status=200, content_type="application/xml")
        return Response(_NO_SUCH_KEY_XML, status=404, content_type="application/xml")

    httpserver.expect_request(re.compile("^/.*$")).respond_with_handler(handler)
    return httpserver.url_for("/").rstrip("/")


@contextmanager
def _backend_at(dotted: str, endpoint: str) -> Iterator[Backend]:
    import importlib

    module_path, cls_name = dotted.split(":")
    backend_cls = getattr(importlib.import_module(module_path), cls_name)
    backend = backend_cls(
        bucket=_BUCKET,
        key="AKIAIOSFODNN7EXAMPLE",
        secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region_name="us-east-1",
        endpoint_url=endpoint,
    )
    try:
        yield backend
    finally:
        backend.close()


class TestProbeDenialIsPermissionDenied:
    """A denied probe is the *determinant*, so the denial must reach the caller.

    BE-021's ACL row: an operation denied by credentials or ACL maps to
    ``PermissionDenied``. Reporting ``NotFound`` instead is not merely the wrong
    type — it asserts the object is absent, which is the opposite of true.
    ``delete(missing_ok=True)`` is included because the swallow made it return
    *cleanly*: the caller was told the delete had nothing to do.
    """

    @pytest.mark.parametrize("dotted", _BACKEND_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_ALL_OPS))
    def test_denied_probe_maps_permission_denied(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        endpoint = _serve_s3_stub(httpserver, object_denied=True, listing_denied=True)
        with _backend_at(dotted, endpoint) as backend:
            with pytest.raises(PermissionDenied) as exc_info:
                _ALL_OPS[op_name](backend)
            assert exc_info.value.backend == _BACKEND_NAMES[dotted]


class TestErrorPathProbeStaysFailOpen:
    """The *reclassification* probe still fails open, and must keep doing so.

    Here the operation has already established its own answer — the object is a
    genuine 404, or the prefix is genuinely empty — and the second probe exists
    only to ask "was it the other type?". A denial there cannot answer that
    question, so the operation's own ``NotFound`` stands. Replacing it with
    ``PermissionDenied`` would report a failure the operation did not have; this
    is the half a blanket "make every probe strict" fix would break.
    """

    @pytest.mark.parametrize("dotted", _BACKEND_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_FILE_SHAPED_OPS))
    def test_denied_folder_probe_leaves_not_found_standing(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        """Object HEAD 404s (a real miss); the ``is-this-a-folder?`` listing 403s."""
        endpoint = _serve_s3_stub(httpserver, object_denied=False, listing_denied=True)
        with _backend_at(dotted, endpoint) as backend, pytest.raises(NotFound) as exc_info:
            _FILE_SHAPED_OPS[op_name](backend)
        assert exc_info.value.backend == _BACKEND_NAMES[dotted]

    @pytest.mark.parametrize("dotted", _BACKEND_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_FOLDER_SHAPED_OPS))
    def test_denied_file_probe_leaves_not_found_standing(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        """Prefix listing is empty (a real miss); the ``is-this-a-file?`` HEAD 403s."""
        endpoint = _serve_s3_stub(httpserver, object_denied=True, listing_denied=False)
        with _backend_at(dotted, endpoint) as backend, pytest.raises(NotFound) as exc_info:
            _FOLDER_SHAPED_OPS[op_name](backend)
        assert exc_info.value.backend == _BACKEND_NAMES[dotted]

    @pytest.mark.parametrize("dotted", _BACKEND_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_TOLERANT_OPS))
    def test_missing_ok_still_tolerates_a_genuine_miss(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        """``missing_ok`` returns cleanly when only the reclassification probe is denied.

        The mirror of the determinant case above: there the same call had to
        stop *raising nothing* and report ``PermissionDenied``; here the miss is
        real and the denial is on the second probe, so returning cleanly is
        still correct. Without this pair, "raise on 403" and "tolerate a miss"
        cannot both be pinned.
        """
        call, object_denied, listing_denied = _TOLERANT_OPS[op_name]
        endpoint = _serve_s3_stub(httpserver, object_denied=object_denied, listing_denied=listing_denied)
        with _backend_at(dotted, endpoint) as backend:
            assert call(backend) is None
