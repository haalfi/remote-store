"""Live AWS S3 error-mapping tests for ``S3Backend`` (BK-248).

Stage 3, real-live. Confirms over the wire what the ID-200 audit could
only verify at the *mapping boundary*: that a genuine S3 403 on the read
and write paths surfaces as ``PermissionDenied`` — i.e. the live request
actually routes through ``s3fs.translate_boto_error`` rather than being
swallowed inside an aiobotocore streaming read.

Why this cannot live in the conformance walk
--------------------------------------------

moto (the Stage-1 backend) enforces neither IAM nor credential validity,
so a real 403 is unreachable in-process (see
``sdd/research/research-s3-error-mapping-fidelity.md`` rows (b)/(c)). The
``s3_live`` conformance fixture provisions a bucket the IAM user *can*
access, so it never produces a 403 either. These tests drive a real 403
the happy-path fixture cannot.

How a real 403 is produced
--------------------------

A backend constructed with a **bogus access key / secret**. Any
``GetObject`` / ``PutObject`` is rejected at request signing → real 403
``InvalidAccessKeyId`` / ``SignatureDoesNotMatch`` over the wire (ID-200
row (c)). s3fs's ``translate_boto_error`` maps the 403 error *code* to a
``PermissionError`` regardless of which credential failure produced it,
and ``_s3fs_errors`` maps that to ``PermissionDenied``.

Note on the distinct ``AccessDenied`` row (b). A genuine ``AccessDenied``
(valid credentials, forbidden resource) is *not* separately exercised:
producing it requires an existing-but-forbidden bucket, and the
single-credential ``s3_live`` IAM user has full access within its
``rs-conformance-*`` grant and cannot provision one. Targeting a bucket
*outside* the grant returns **404 NoSuchBucket**, not 403 — S3 reports a
non-existent bucket as 404 to a credentialed caller, regardless of IAM
(confirmed empirically, BK-248). Because ``translate_boto_error`` keys on
the 403 error code identically for ``AccessDenied`` and the
invalid-credential codes (ID-200 §3(b)/(c)), the credential-failure 403
confirms the same boundary the ``AccessDenied`` row would.

What the read tests pin down
----------------------------

s3fs front-loads a HEAD/GET *inside* the ``_s3fs_errors`` context (both
``cat_file`` and ``open`` issue the request eagerly), so the 403 is always
caught by the context manager and never reaches the ``_ErrorMappingStream``
wrapper returned by ``read``. That is the resolution of ID-200's residual
risk — the streaming-read swallow ID-200 worried about cannot occur for an
auth/permission failure, because the error surfaces before any stream is
handed to the caller. The streaming ``read`` test asserts this directly.

Spec: S3-016 (PermissionDenied mapping), S3-018 (no native exception
leakage); TEST-006 (Stage-3 live gating).

Gating
------

Two layers, both required:

1. ``pytest.mark.live`` at module level. Default ``addopts`` is
   ``-m 'not live'``, so plain ``hatch run test`` skips the file entirely.
2. ``RS_TEST_LIVE_S3=1`` env var (matches the ``s3_live`` fixture gate).
   When set, ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` /
   ``AWS_DEFAULT_REGION`` become fail-loud preconditions via
   ``require_s3_live_credentials`` — a silent skip here would mean "I
   thought I tested it" but didn't.

Cost discipline
---------------

Each test issues one failing SDK round trip against real AWS and
provisions no buckets (the 403 precedes any resource access). Payloads are
a few bytes.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import PermissionDenied
from tests.backends.fixtures._live_env import require_s3_live_credentials

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store.backends._s3 import S3Backend


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RS_TEST_LIVE_S3") != "1",
        reason="live S3 error-mapping suite is opt-in via RS_TEST_LIVE_S3=1",
    ),
]

# A key we never write. The 403 fires at request signing, before object
# existence is checked, so the key is irrelevant to the outcome.
_PROBE_KEY = "bk-248-probe.txt"


def _read_stream_fully(backend: S3Backend, key: str) -> None:
    """Open ``key`` and drain the stream, closing it afterwards.

    Wraps the multi-statement open/read/close so the streaming-read test's
    ``pytest.raises`` block stays a single statement (ruff PT012). Draining
    forces the GetObject even if s3fs ever defers it past ``open``.
    """
    stream = backend.read(key)
    try:
        stream.read()
    finally:
        stream.close()


@pytest.fixture
def invalid_credential_backend() -> Iterator[S3Backend]:
    """``S3Backend`` constructed with a bogus access key / secret.

    Any S3 operation is rejected at request signing with a real 403
    ``InvalidAccessKeyId`` / ``SignatureDoesNotMatch`` (row c). The bucket
    is in the conformance namespace but is never provisioned, because the
    403 precedes resource access.

    ``region_name`` comes from the real env so the request reaches the
    correct regional endpoint; the credentials are the only invalid part.
    """
    from remote_store.backends._s3 import S3Backend  # noqa: PLC0415 -- intentional late import

    creds = require_s3_live_credentials()
    backend = S3Backend(
        bucket="rs-conformance-bk248-invalid",
        key="AKIAIOSFODNN7EXAMPLE",
        secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region_name=creds["AWS_DEFAULT_REGION"],
    )
    try:
        yield backend
    finally:
        backend.close()


class TestS3LiveInvalidCredentials:
    """A real 403 from invalid credentials maps to ``PermissionDenied`` over the wire.

    Row (c) of the ID-200 audit (``InvalidAccessKeyId`` /
    ``SignatureDoesNotMatch``), confirmed over the wire on the read
    (``GetObject``) and write (``PutObject``) paths the moto audit could
    not exercise. ``backend == "s3"`` is asserted per S3-018.
    """

    @pytest.mark.spec("S3-016", "S3-018")
    def test_read_bytes_maps_permission_denied(self, invalid_credential_backend: S3Backend) -> None:
        """``read_bytes`` → ``cat_file`` (eager): the s3fs-translated ``PermissionError``
        hits the dedicated branch in ``_s3fs_errors``."""
        with pytest.raises(PermissionDenied) as exc_info:
            invalid_credential_backend.read_bytes(_PROBE_KEY)
        assert exc_info.value.backend == "s3"

    @pytest.mark.spec("S3-016", "S3-018")
    def test_read_stream_maps_permission_denied(self, invalid_credential_backend: S3Backend) -> None:
        """Streaming ``read``: the 403 surfaces at ``open`` inside ``_s3fs_errors``.

        s3fs issues an eager HEAD/GET when ``open`` is called, so the 403
        is raised and mapped *before* a stream is returned — it never
        reaches the ``_ErrorMappingStream`` wrapper. This is the direct
        resolution of ID-200's "swallowed inside an aiobotocore streaming
        read" concern: there is no stream to swallow it. The stream is
        consumed defensively so that, were s3fs ever to defer the GetObject,
        the error would still be forced and asserted here.
        """
        with pytest.raises(PermissionDenied) as exc_info:
            _read_stream_fully(invalid_credential_backend, _PROBE_KEY)
        assert exc_info.value.backend == "s3"

    @pytest.mark.spec("S3-016", "S3-018")
    def test_write_maps_permission_denied(self, invalid_credential_backend: S3Backend) -> None:
        """``write`` → ``pipe_file`` (``PutObject``): the bad-signature 403 maps
        through the dedicated ``_s3fs_errors`` branch."""
        with pytest.raises(PermissionDenied) as exc_info:
            invalid_credential_backend.write(_PROBE_KEY, b"bk-248", overwrite=True)
        assert exc_info.value.backend == "s3"
