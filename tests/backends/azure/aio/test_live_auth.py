"""Live ADLS Gen2 auth-failure error-mapping for ``AsyncAzureBackend`` (BUG-222).

Stage-3, real-account. Validates that genuine Azure auth-failure wire
responses map to ``PermissionDenied`` through ``classify_azure_error``:

* A **bad AAD bearer token** -> real ``ClientAuthenticationError(status=401)``.
  Azurite cannot reproduce this — it returns ``403`` for a bad shared-key
  signature — so the 401 leg is **Stage-3-only**.
* A **bad shared-key signature** -> real ``ClientAuthenticationError(status=403)``.
  (Azurite surfaces the same condition as a *bare* ``HttpResponseError(403)``;
  that complementary shape is covered by
  ``test_live.py::TestAsyncAzureLiveErrorMapping::test_bad_signature_maps_to_permission_denied``.)

These exercise the real SDK's exception *subtype* selection — a cassette or
mock encodes our assumed shape, not the service's. Throttling (``429``) and
server errors (``5xx``) are **deliberately not forced** here: producing them
needs sustained high-volume load against a pay-per-use account, against the
live-tier cost discipline (see ``AZ-025`` and BUG-222). Their classifier
branches are covered deterministically in ``test_config.py``.

Gating (both required to run):

1. ``pytest.mark.live`` at module level (default ``addopts`` is ``-m 'not live'``).
2. ``RS_TEST_LIVE_HNS=1`` — the de-facto "real Azure account" opt-in, shared
   with the HNS live suites.

Fixture-time precondition: ``AZURE_STORAGE_CONNECTION_STRING`` must point at a
real account (``require_azure_live_connection_string`` fails loud otherwise).
The tests are read-only and target a probe key that need not exist — auth
fails before any resource lookup — so there is nothing to provision or tear down.

Spec: AZ-025, ASYNC-024.
"""

from __future__ import annotations

import base64
import os
import time

import pytest

pytest.importorskip("azure.storage.filedatalake", reason="azure-storage-file-datalake not installed")

from azure.core.credentials import AccessToken  # noqa: E402
from azure.core.exceptions import HttpResponseError  # noqa: E402
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient  # noqa: E402

from remote_store._errors import PermissionDenied  # noqa: E402
from remote_store.backends._azure_common import classify_azure_error  # noqa: E402
from tests.backends.fixtures._live_env import (  # noqa: E402
    require_azure_live_connection_string,
    require_azure_live_hns_container,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RS_TEST_LIVE_HNS") != "1",
        reason="live Azure suite is opt-in via RS_TEST_LIVE_HNS=1",
    ),
]


def _account_url(conn: str) -> str:
    """Derive the blob endpoint from the connection string (no secret exposed)."""
    for part in conn.split(";"):
        if part.startswith("BlobEndpoint="):
            return part[len("BlobEndpoint=") :]
    name = next(p[len("AccountName=") :] for p in conn.split(";") if p.startswith("AccountName="))
    return f"https://{name}.blob.core.windows.net"


class _BadAsyncToken:
    """AsyncTokenCredential handing the SDK a syntactically-bogus bearer token."""

    async def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        return AccessToken("this.is.not.a.valid.jwt", int(time.time()) + 3600)

    async def close(self) -> None:
        return None


class TestAsyncLiveAuthErrorMapping:
    """BUG-222: real-wire Azure auth failures map to ``PermissionDenied``."""

    @pytest.mark.spec("AZ-025")
    @pytest.mark.spec("ASYNC-024")
    async def test_bad_bearer_token_maps_to_permission_denied(self) -> None:
        """A real ``401`` from an invalid AAD bearer token -> ``PermissionDenied``.

        Stage-3-only: Azurite returns ``403`` for bad signatures and never a
        ``401``, so this AAD-token-shaped failure is reachable only against a
        real account.

        Coverage intent: the real SDK types a ``401`` as
        ``ClientAuthenticationError``, so this re-confirms the pre-existing
        ``isinstance(exc, ClientAuthenticationError)`` branch (which runs
        before any ``status_code`` check) — it does **not** exercise the new
        bare-``HttpResponseError`` ``status == 401`` branch BUG-222 adds. That
        branch is covered deterministically by the ``http-401`` param in
        ``test_config.py``. The value here is real-SDK subtype characterisation.
        """
        conn = require_azure_live_connection_string()
        url, container = _account_url(conn), require_azure_live_hns_container()
        svc = AsyncBlobServiceClient(url, credential=_BadAsyncToken())
        try:
            with pytest.raises(HttpResponseError) as exc_info:
                await svc.get_container_client(container).get_blob_client("probe.txt").get_blob_properties()
        finally:
            await svc.close()
        assert getattr(exc_info.value, "status_code", None) == 401
        mapped = classify_azure_error(exc_info.value, "probe.txt", "async-azure")
        assert isinstance(mapped, PermissionDenied)
        assert mapped.backend == "async-azure"

    @pytest.mark.spec("AZ-025")
    @pytest.mark.spec("ASYNC-024")
    async def test_bad_shared_key_maps_to_permission_denied(self) -> None:
        """A real ``403`` from a wrong shared-key signature -> ``PermissionDenied``.

        Real Azure types this as ``ClientAuthenticationError`` (status ``403``),
        a different SDK shape than Azurite's bare ``HttpResponseError(403)`` —
        both must map to ``PermissionDenied``.
        """
        conn = require_azure_live_connection_string()
        container = require_azure_live_hns_container()
        bad_conn = ";".join(
            "AccountKey=" + base64.b64encode(b"wrong-key-padding-wrong-key-padding-xxxx").decode()
            if seg.startswith("AccountKey=")
            else seg
            for seg in conn.split(";")
        )
        svc = AsyncBlobServiceClient.from_connection_string(bad_conn)
        try:
            with pytest.raises(HttpResponseError) as exc_info:
                await svc.get_container_client(container).get_blob_client("probe.txt").get_blob_properties()
        finally:
            await svc.close()
        assert getattr(exc_info.value, "status_code", None) == 403
        mapped = classify_azure_error(exc_info.value, "probe.txt", "async-azure")
        assert isinstance(mapped, PermissionDenied)
        assert mapped.backend == "async-azure"
