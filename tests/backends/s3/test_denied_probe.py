"""What the S3 *type probes* do when the wire refuses to answer them.

The 403 case first (a denial is never ``NotFound``), then the missing-bucket
404 case, which is the other shape a probe can meet instead of an answer.

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

The missing-bucket half (``TestAbsentBucketReadsAsAbsentPath``)
--------------------------------------------------------------

The two probes still catch *different* exceptions, and that remains the wire
shape rather than an inconsistency. What changed with BUG-243 is that the wire
shape no longer decides what the caller sees:

* ``HeadObject`` answers a bodyless 404, so a missing **bucket** is
  indistinguishable from a missing key and ``delete`` cannot tell them apart
  even if it wanted to.
* ``ListObjectsV2`` answers an absent prefix with ``200 KeyCount=0``, so the
  only 404 it can raise is the bucket's — a 404 whose body *does* carry
  ``NoSuchBucket``.

Left alone, that split gave ``delete(missing_ok=True)`` a silent return and
``delete_folder(missing_ok=True)`` a ``NotFound`` against the very same absent
bucket. BE-012/BE-013 now decide it instead of the protocol: **an absent
container reads as an absent path**, so both tolerate it under ``missing_ok``
and both raise ``NotFound`` without it. ``delete_folder`` reaches that answer by
treating the bucket 404 its listing raises as "no children", which costs no
extra request — the strict-discrimination alternative would have cost ``delete``
a second ``HeadBucket`` on every miss.

All four cells are asserted so neither half drifts: making the HEAD probe strict
about bucket 404s breaks the tolerant ``delete``, dropping ``delete_folder``'s
catch breaks the tolerant ``delete_folder``, and swallowing the 404 past
``missing_ok`` breaks the two strict cells.
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

from remote_store._errors import NotFound, PermissionDenied, RemoteStoreError  # noqa: E402

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
_NO_SUCH_BUCKET_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<Error><Code>NoSuchBucket</Code><Message>The specified bucket does not exist.</Message>"
    b"<BucketName>" + _BUCKET.encode() + b"</BucketName>"
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

# Denial suites: the per-backend clause is the PermissionDenied mapping.
_BACKEND_PARAMS = [
    pytest.param(_S3, id="s3", marks=pytest.mark.spec("BE-021", "S3-016")),
    pytest.param(_S3PA, id="s3-pyarrow", marks=pytest.mark.spec("BE-021", "S3PA-018", "S3PA-019")),
    pytest.param(_S3B3, id="s3-boto3", marks=pytest.mark.spec("BE-021", "S3-016")),
]

# Absent-bucket suite: a separate list, because param-level marks ride onto
# *every* test that consumes them. Sharing the list above would re-attach
# S3-016 (PermissionDenied Mapping) to cells whose subject is the NotFound
# mapping — false traceability no gate can see, since `check_spec_marks.py`
# verifies that a cited ID exists, never that it fits. The pyarrow entry keeps
# S3PA-018, which is that backend's umbrella for S3-015/016/017 and so covers
# this half too.
_ABSENT_BUCKET_PARAMS = [
    pytest.param(_S3, id="s3", marks=pytest.mark.spec("BE-021", "S3-015")),
    pytest.param(_S3PA, id="s3-pyarrow", marks=pytest.mark.spec("BE-021", "S3PA-018")),
    pytest.param(_S3B3, id="s3-boto3", marks=pytest.mark.spec("BE-021", "S3-015")),
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
# The same two deletes with tolerance *off*, for the absent-container cells: the
# rule is that an absent container reads as an absent path, which still raises
# under ``missing_ok=False``.
_STRICT_DELETES: dict[str, Callable[[Backend], Any]] = {
    "delete": lambda b: b.delete(_KEY),
    "delete_folder": lambda b: b.delete_folder(_FOLDER, recursive=True),
}
_ALL_OPS: dict[str, Callable[[Backend], Any]] = {
    **_FILE_SHAPED_OPS,
    **_FOLDER_SHAPED_OPS,
    **{name: call for name, (call, _o, _l) in _TOLERANT_OPS.items()},
}
# The probes BE-004 and BE-005 forbid from raising at all. Kept out of
# ``_ALL_OPS`` because these two suites want opposite things from them: a denied
# bucket must still reach the caller as ``PermissionDenied`` (the probe is the
# determinant and fails closed), while an absent one answers ``False``.
_PROBES: dict[str, Callable[[Backend], Any]] = {
    "exists-file": lambda b: b.exists(_KEY),
    "exists-folder": lambda b: b.exists(_FOLDER),
    "is_file": lambda b: b.is_file(_KEY),
    "is_folder": lambda b: b.is_folder(_FOLDER),
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


def _serve_missing_bucket_stub(httpserver: HTTPServer) -> str:
    """Answer every S3 request the way a *missing bucket* does; return the endpoint.

    The two shapes differ: ``ListObjectsV2`` (a GET) answers 404 with a
    ``NoSuchBucket`` body, while ``HeadObject`` answers a bodyless 404 — HTTP
    forbids a body on a HEAD response, so the bucket-level cause never reaches
    the client and the probe cannot tell it from a missing key. Serving both
    faithfully is what lets ``TestAbsentBucketReadsAsAbsentPath`` assert that
    the difference no longer reaches the caller.
    """
    from werkzeug.wrappers import Response

    def handler(request: Any) -> Any:
        if request.method == "HEAD":
            return Response(b"", status=404, content_type="application/xml")
        return Response(_NO_SUCH_BUCKET_XML, status=404, content_type="application/xml")

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

    @pytest.mark.parametrize("dotted", _BACKEND_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_PROBES))
    def test_denied_probe_is_not_an_absent_container(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        """The control case for the absent-bucket cells below, and the overshoot to fear.

        BE-004 and BE-005 forbid these three from raising ``NotFound``; they say
        nothing that would let a *denial* be reported as ``False``. The two are
        one narrowing apart — an absent-container catch widened from the bucket's
        own 404 to every error would turn "you may not look" into "there is
        nothing there", which is the invented-answer regression this backend
        family has already shipped once (BUG-242). A tolerance-only test cannot
        see it: swallowing the 403 makes the cells below *more* green.
        """
        endpoint = _serve_s3_stub(httpserver, object_denied=True, listing_denied=True)
        with _backend_at(dotted, endpoint) as backend:
            with pytest.raises(PermissionDenied) as exc_info:
                _PROBES[op_name](backend)
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


class TestAbsentBucketReadsAsAbsentPath:
    """An absent bucket is an absent path, one level up — for *both* deletes.

    BE-012/BE-013. The two probes meet a missing bucket in different shapes (a
    bodyless HEAD 404 versus a ``NoSuchBucket`` listing 404), and letting that
    difference reach the caller is what made one delete tolerant and its sibling
    strict against the same absent bucket. The rule is decided at the contract
    now, so the wire shape only determines how each backend *reaches* it.

    Both axes are asserted — tolerance under ``missing_ok=True`` and
    ``NotFound`` without it — so the fix cannot overshoot into swallowing the
    strict case, which is the failure mode a tolerance-only test would miss.
    """

    @pytest.mark.spec("BE-012", "BE-013", "BE-021")
    @pytest.mark.parametrize("dotted", _ABSENT_BUCKET_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_TOLERANT_OPS))
    def test_absent_bucket_is_tolerated(self, httpserver: HTTPServer, dotted: str, op_name: str) -> None:
        """``missing_ok=True`` returns cleanly for both deletes."""
        call, _object_denied, _listing_denied = _TOLERANT_OPS[op_name]
        endpoint = _serve_missing_bucket_stub(httpserver)
        with _backend_at(dotted, endpoint) as backend:
            assert call(backend) is None

    @pytest.mark.spec("BE-012", "BE-013", "BE-021")
    @pytest.mark.parametrize("dotted", _ABSENT_BUCKET_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_STRICT_DELETES))
    def test_absent_bucket_raises_not_found_when_strict(
        self,
        httpserver: HTTPServer,
        dotted: str,
        op_name: str,
    ) -> None:
        """Without ``missing_ok`` the same absent bucket is a plain ``NotFound``.

        The tolerance belongs to ``missing_ok``, not to the bucket 404: a
        backend that simply stopped raising on the listing's ``NoSuchBucket``
        would pass the tolerant cells above and silently turn a strict delete
        into a no-op.
        """
        endpoint = _serve_missing_bucket_stub(httpserver)
        with _backend_at(dotted, endpoint) as backend:
            with pytest.raises(NotFound) as exc_info:
                _STRICT_DELETES[op_name](backend)
            assert exc_info.value.backend == _BACKEND_NAMES[dotted]


# The three listings on S3Boto3Backend that did not wrap `_paginate` in
# `_boto_errors` the way every other method on the class wraps its call, plus
# `glob`, which reaches the wire only through `list_files` and so inherits
# whatever that method does.
_BOTO3_LISTINGS: dict[str, Callable[[Backend], Any]] = {
    "list_files": lambda b: list(b.list_files("")),
    "list_files-recursive": lambda b: list(b.list_files("folder", recursive=True)),
    "list_folders": lambda b: list(b.list_folders("")),
    "iter_children": lambda b: list(b.iter_children("")),
    "glob": lambda b: list(b.glob("**/*.txt")),
}


class TestEveryLaneAnswersAnAbsentBucketTheSameWay:
    """The three lanes agree against a missing bucket, on probes and listings alike.

    Two divergences used to live here, and both were backend-local omissions
    rather than contract questions — the same wire response, the same operation,
    two lanes answering correctly and one not:

    * ``S3Boto3Backend.exists`` and ``.is_folder`` raised ``NotFound``, because
      the strict prefix probe was reached once the tolerant HEAD came back empty.
      BE-004 and BE-005 forbid these from raising at all (BUG-246).
    * ``S3Boto3Backend``'s three listings let a raw
      ``botocore.exceptions.ClientError`` escape — a type from a library the
      caller may never have imported and cannot catch through ``remote_store``'s
      hierarchy — because they were the only methods on the class calling the
      wire without ``_boto_errors`` around it (BUG-249).

    Parametrising over all three lanes rather than testing the fixed one is the
    point: the s3fs lanes are the control that says what the answer *is*.
    """

    @pytest.mark.spec("BE-004", "BE-005", "BE-021")
    @pytest.mark.parametrize("dotted", _ABSENT_BUCKET_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_PROBES))
    def test_probe_answers_false(self, httpserver: HTTPServer, dotted: str, op_name: str) -> None:
        """An absent bucket holds no path, so the probes answer ``False``, not ``NotFound``."""
        endpoint = _serve_missing_bucket_stub(httpserver)
        with _backend_at(dotted, endpoint) as backend:
            assert _PROBES[op_name](backend) is False

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize("dotted", _ABSENT_BUCKET_PARAMS)
    @pytest.mark.parametrize("op_name", sorted(_BOTO3_LISTINGS))
    def test_listing_comes_back_empty(self, httpserver: HTTPServer, dotted: str, op_name: str) -> None:
        """An absent container holds nothing, and nothing native escapes on the way out.

        Asserting the empty listing alone would pass on a backend that mapped the
        404 to a ``NotFound`` it then swallowed somewhere else, so the guard that
        matters is the one below it: no ``botocore`` type reaches the caller.
        """
        endpoint = _serve_missing_bucket_stub(httpserver)
        with _backend_at(dotted, endpoint) as backend:
            assert _BOTO3_LISTINGS[op_name](backend) == []

    @pytest.mark.spec("BE-021")
    @pytest.mark.parametrize("op_name", sorted(_BOTO3_LISTINGS))
    def test_no_native_error_escapes_a_broken_listing(self, httpserver: HTTPServer, op_name: str) -> None:
        """BE-021's never-leak invariant, on the lane that used to breach it.

        A 403 is the case that still raises, so it is the one that shows *which*
        type comes out. The absent-bucket cells above cannot: an empty listing
        raises nothing, so they would stay green with the mapping removed.
        """
        from botocore.exceptions import ClientError

        endpoint = _serve_s3_stub(httpserver, object_denied=True, listing_denied=True)
        with _backend_at(_S3B3, endpoint) as backend:
            with pytest.raises(RemoteStoreError) as exc_info:
                _BOTO3_LISTINGS[op_name](backend)
            assert not isinstance(exc_info.value, ClientError), f"{op_name} leaks its native error"
            assert isinstance(exc_info.value, PermissionDenied), f"{op_name} misclassified a denial"
