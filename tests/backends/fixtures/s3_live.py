"""``s3_live`` fixture: S3Backend against a real AWS S3 account.

Stage 3, real-live. Each factory call provisions a fresh bucket named
``rs-conformance-<uuid>`` on the configured AWS account; cleanup empties
and deletes it. Per-call isolation keeps conformance tests from leaking
state into each other on a shared real account.

Gating
------

Two layers, both required:

1. ``--stage=3`` (or ``RS_TEST_STAGE=3``). Lower stages exclude this
   fixture from the registry walk and no parametrize id is generated.
2. ``RS_TEST_LIVE_S3=1`` env var. When unset, the factory calls
   ``pytest.skip(...)`` per TEST-006 — collection still succeeds and
   tests parametrised over other backends still run.

Once both are set, ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, and
``AWS_DEFAULT_REGION`` become fail-loud preconditions: empty or pointing
at an emulator is a configuration bug, not a reason to silent-skip a
test the user explicitly opted into (see
``_live_env.require_s3_live_credentials``).

The ``pytest.mark.live`` mark rides along with the parametrize entry so
the default ``addopts = -m 'not live'`` deselects every test
parametrised over this fixture unless the user opts in with ``-m live``.

Cost discipline
---------------

Each factory call performs one ``create_bucket`` and one
``delete_bucket`` SDK round trip (plus a paginator sweep to empty the
bucket). Data-plane traffic per test stays small because conformance
payloads are deliberately tiny. A run with N parametrised tests therefore
costs ``N × (create + delete + per-test ops)`` against a real account —
affordable for Stage 3 cadence (manual or scheduled CI), not for default CI.

``eu-central-1`` note
---------------------

``create_bucket`` for any region other than ``us-east-1`` requires a
``CreateBucketConfiguration`` with a ``LocationConstraint``. The factory
reads the region from ``AWS_DEFAULT_REGION`` and always passes it.
``S3Backend`` is constructed without ``key=`` / ``secret=`` /
``region_name=`` so it defers to boto3's default credential chain.

Required IAM permissions
------------------------

The IAM user in ``.env`` must have the following permissions (this is a
setup prerequisite, not checked at runtime)::

    s3:CreateBucket       arn:aws:s3:::rs-conformance-*
    s3:DeleteBucket       arn:aws:s3:::rs-conformance-*
    s3:ListBucket         arn:aws:s3:::rs-conformance-*
    s3:ListBucketMultipartUploads  arn:aws:s3:::rs-conformance-*
    s3:GetBucketLocation  arn:aws:s3:::rs-conformance-*
    s3:GetObject               arn:aws:s3:::rs-conformance-*/*
    s3:PutObject               arn:aws:s3:::rs-conformance-*/*
    s3:DeleteObject            arn:aws:s3:::rs-conformance-*/*
    s3:ListMultipartUploadParts  arn:aws:s3:::rs-conformance-*/*
    s3:AbortMultipartUpload    arn:aws:s3:::rs-conformance-*/*

Note: ``CopyObject`` and ``HeadObject`` are S3 API methods, not IAM action
names; IAM maps them to ``s3:PutObject``/``s3:GetObject`` (already above).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._live_env import require_s3_live_credentials
from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

if TYPE_CHECKING:
    from remote_store._backend import Backend

_meta = load_fixture("s3_live")

_LOG = logging.getLogger(__name__)

# id(backend) -> (bucket name, boto3 client) so cleanup can tear down
# what factory created without threading state through the Backend instance.
_BUCKETS: dict[int, tuple[str, object]] = {}


def _factory() -> Backend:
    if os.environ.get("RS_TEST_LIVE_S3") != "1":
        pytest.skip("s3_live opt-in via RS_TEST_LIVE_S3=1")
    try:
        import boto3
    except ImportError:
        pytest.skip("boto3 not installed")

    from remote_store.backends._s3 import S3Backend

    creds = require_s3_live_credentials()
    region = creds["AWS_DEFAULT_REGION"]
    bucket = f"rs-conformance-{uuid.uuid4().hex[:12]}"
    client = boto3.client(
        "s3",
        aws_access_key_id=creds["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["AWS_SECRET_ACCESS_KEY"],
        region_name=region,
    )
    try:
        create_kwargs: dict = {"Bucket": bucket}
        if region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**create_kwargs)
    except Exception:
        client.close()
        raise
    try:
        backend = S3Backend(bucket=bucket)
        _BUCKETS[id(backend)] = (bucket, client)
    except Exception:
        try:
            client.delete_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001 -- best-effort on init failure
            _LOG.warning("failed to delete bucket %s after S3Backend init failure", bucket, exc_info=True)
        client.close()
        raise
    return backend


def _cleanup(backend: Backend) -> None:
    # Guard backend.close() so a transient close failure cannot strand a
    # real S3 bucket. The deletion path below is the load-bearing step.
    try:
        backend.close()
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("backend.close() failed during cleanup", exc_info=True)
    entry = _BUCKETS.pop(id(backend), None)
    if entry is None:
        return
    bucket, client = entry
    try:
        paginator = client.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            while objects:
                chunk, objects = objects[:1000], objects[1000:]
                client.delete_objects(  # type: ignore[attr-defined]
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in chunk]},
                )
        client.delete_bucket(Bucket=bucket)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 -- teardown is best-effort
        _LOG.warning("failed to delete live S3 bucket %s", bucket, exc_info=True)
    finally:
        client.close()  # type: ignore[attr-defined]


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._s3 import S3Backend
    except ImportError:
        return frozenset()
    return frozenset(S3Backend.CAPABILITIES)


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        marks=(pytest.mark.live,),
        **_meta.to_kwargs(),
    )
)
