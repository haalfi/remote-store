"""Backend.check_health() conformance — universal ABC contract.

PING-002 declares ``check_health()`` as a concrete ABC method on every
backend. PING-009 declares that every failure path maps the underlying
SDK exception to a ``RemoteStoreError`` subclass — native botocore /
paramiko / azure-core exceptions never leak past the backend boundary.

Combining the two: **the outcome of ``backend.check_health()`` is either
``None`` (success) or a ``RemoteStoreError`` subclass (mapped failure)**.
This is the universal invariant; it holds whether the probe succeeds
against a healthy resource or fails because the probe target is not yet
established (fixture state varies — some pre-create buckets / files,
others don't, and HTTP servers can legitimately return 404 on directory
URLs while still serving files normally per the PING-004 spec note).

Per-backend tests in ``tests/backends/<x>/test_ping.py`` cover the
SDK-mocked probe identity (which method the probe calls — PING-003
through PING-007) and the error-mapping branches (PING-009). Those tests
inject specific SDK exceptions and assert the specific taxonomy classes;
this file owns only the cross-protocol "no native exceptions leak"
invariant.

Added in BK-217 (BK-191 slice 2/6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._errors import RemoteStoreError

if TYPE_CHECKING:
    from remote_store._backend import Backend


class TestCheckHealthConformance:
    @pytest.mark.spec("PING-002")
    def test_check_health_returns_none_or_raises_remote_store_error(
        self, backend: Backend, request: pytest.FixtureRequest
    ) -> None:
        # BUG-208: the S3 backend's check_health() does not await the
        # aiobotocore head_bucket coroutine — it leaks for GC and check_health
        # silently returns None. The leaked RuntimeWarning is escalated to an
        # error by the repo's pytest filterwarnings policy. xfail-strict so
        # this auto-flags for removal once BUG-208 lands and the call is awaited.
        if backend.name == "s3":
            request.applymarker(
                pytest.mark.xfail(
                    reason="BUG-208: the S3 backend's check_health() does not await the head_bucket coroutine",
                    raises=pytest.PytestUnraisableExceptionWarning,
                    strict=True,
                )
            )
        try:
            result = backend.check_health()
        except RemoteStoreError:
            return
        assert result is None
