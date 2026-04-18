"""Shared pure functions for sync and async Azure backends."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import ContentDigest, FileInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from remote_store._config import RetryPolicy

log = logging.getLogger(__name__)


def validate_azure_params(
    container: str,
    account_name: str | None,
    account_url: str | None,
    connection_string: Any,
    max_concurrency: int,
) -> None:
    """Validate Azure backend constructor parameters.

    Args:
        container: Azure Storage container name.
        account_name: Storage account name.
        account_url: Full account URL.
        connection_string: Azure Storage connection string (may be ``Secret``).
        max_concurrency: Maximum number of parallel connections.

    Raises:
        ValueError: If any parameter is invalid.
    """
    if not container or not container.strip():
        raise ValueError("container must be a non-empty string")
    if not account_name and not account_url and not connection_string:
        raise ValueError("At least one of account_name, account_url, or connection_string must be provided")
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")


def azure_path(path: str) -> str:
    """Normalize path for Azure (strip leading ``/``, collapse double separators).

    Args:
        path: Backend-relative key.

    Returns:
        Normalized Azure blob/path name.
    """
    return re.sub(r"/+", "/", path).lstrip("/")


def classify_azure_error(exc: Exception, path: str, backend_name: str) -> RemoteStoreError:
    """Classify an Azure SDK exception into a remote_store error type.

    When called via ``_ErrorMappingStream`` on an ``_AzureRangeReader``,
    the exception may be an ``OSError`` wrapping the original Azure SDK
    exception (via ``__cause__``).  Unwrap before matching.

    Args:
        exc: The Azure SDK exception.
        path: Backend-relative key involved in the operation.
        backend_name: Name of the backend for error reporting.

    Returns:
        An appropriate ``RemoteStoreError`` subclass.
    """
    from azure.core.exceptions import (
        AzureError,
        ClientAuthenticationError,
        HttpResponseError,
        ResourceExistsError,
        ResourceNotFoundError,
        ServiceRequestError,
        ServiceResponseError,
    )

    # Unwrap OSError wrapper from _AzureRangeReader.readinto().
    if isinstance(exc, OSError) and isinstance(exc.__cause__, AzureError):
        exc = exc.__cause__

    if isinstance(exc, ResourceNotFoundError):
        return NotFound(f"Not found: {path}", path=path, backend=backend_name)
    if isinstance(exc, ResourceExistsError):
        return AlreadyExists(f"Already exists: {path}", path=path, backend=backend_name)
    if isinstance(exc, ClientAuthenticationError):
        return PermissionDenied(f"Authentication failed: {path}", path=path, backend=backend_name)
    if isinstance(exc, ServiceRequestError | ServiceResponseError):
        return BackendUnavailable(str(exc), path=path, backend=backend_name)
    if isinstance(exc, HttpResponseError):
        status = getattr(exc, "status_code", None)
        if status == 404:
            return NotFound(f"Not found: {path}", path=path, backend=backend_name)
        if status == 403:
            return PermissionDenied(f"Permission denied: {path}", path=path, backend=backend_name)
        if status == 409:
            return AlreadyExists(f"Already exists: {path}", path=path, backend=backend_name)
        return RemoteStoreError(str(exc), path=path, backend=backend_name)  # pragma: no cover
    return RemoteStoreError(str(exc), path=path, backend=backend_name)  # pragma: no cover


def props_to_fileinfo(props: Any, path: str) -> FileInfo:
    """Convert Azure blob/path properties to ``FileInfo``.

    Args:
        props: Azure SDK blob or path properties object.
        path: Backend-relative key for the file.

    Returns:
        A ``FileInfo`` populated from the properties.
    """
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    size = getattr(props, "size", None) or getattr(props, "content_length", 0) or 0
    modified = getattr(props, "last_modified", None)
    if modified is not None and modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)  # pragma: no cover
    if modified is None:
        modified = datetime.now(tz=timezone.utc)  # pragma: no cover
    # ETag: Azure returns it double-quoted (e.g. '"0x8D4BCC2E4835CD0"'); strip and lowercase.
    raw_etag = getattr(props, "etag", None)
    etag = raw_etag.strip('"').lower() if isinstance(raw_etag, str) else None
    # Content-MD5: blob properties carry it as raw bytes when set; convert to hex ContentDigest.
    content_settings = getattr(props, "content_settings", None)
    md5_bytes = getattr(content_settings, "content_md5", None) if content_settings is not None else None
    digest: ContentDigest | None = None
    if isinstance(md5_bytes, (bytes, bytearray)) and md5_bytes:
        digest = ContentDigest("md5", md5_bytes.hex())
    # User metadata: strip Azure-internal keys (e.g. hdi_isfolder used by HNS).
    raw_meta = getattr(props, "metadata", None) or {}
    user_meta: dict[str, str] | None = {k: v for k, v in raw_meta.items() if k != "hdi_isfolder"} or None
    return FileInfo(
        path=RemotePath(path),
        name=name,
        size=int(size),
        modified_at=modified,
        etag=etag,
        digest=digest,
        metadata=user_meta,
    )


def resolve_credential(
    credential: Any,
    account_key: str | None,
    sas_token: str | None,
    *,
    is_async: bool,
    backend_name: str,
) -> Any:
    """Build credential from constructor parameters.

    Args:
        credential: Explicit credential object, or ``None``.
        account_key: Storage account key.
        sas_token: Shared Access Signature token.
        is_async: If ``True``, import ``DefaultAzureCredential`` from
            ``azure.identity.aio`` instead of ``azure.identity``.
        backend_name: Name of the backend for error reporting.

    Returns:
        A credential suitable for passing to Azure SDK service clients.

    Raises:
        BackendUnavailable: If no credential is provided and ``azure-identity``
            is not installed.
    """
    cred = credential
    if cred is None and account_key is not None:
        cred = account_key
    elif cred is None and sas_token is not None:
        cred = sas_token
    elif cred is None:
        try:
            if is_async:
                import azure.identity.aio as _id_mod
            else:
                import azure.identity as _id_mod  # type: ignore[no-redef]
            cred = _id_mod.DefaultAzureCredential()
        except ImportError:
            raise BackendUnavailable(
                "No credential provided and azure-identity is not installed. "
                "Install azure-identity or provide account_key/sas_token/credential.",
                backend=backend_name,
            ) from None
    return cred


def build_azure_retry(retry: RetryPolicy | None) -> Any | None:
    """Build an Azure ``ExponentialRetry`` from the retry policy, or ``None``.

    Args:
        retry: The retry policy, or ``None`` to skip.

    Returns:
        An ``ExponentialRetry`` instance, or ``None``.
    """
    if retry is None:
        return None
    from azure.storage.blob import ExponentialRetry

    rp = retry
    if rp.backoff_max != 60.0 or rp.timeout is not None:
        log.debug(
            "Azure retry: backoff_max=%.1f and timeout=%s are not mappable "
            "to ExponentialRetry; only max_attempts, backoff_base, jitter are used",
            rp.backoff_max,
            rp.timeout,
        )
    return ExponentialRetry(
        retry_total=max(rp.max_attempts - 1, 0),
        initial_backoff=max(1, round(rp.backoff_base)),
        random_jitter_range=round(rp.jitter),
    )
