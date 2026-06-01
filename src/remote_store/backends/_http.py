"""Read-only HTTP backend — fetch files from HTTP/HTTPS URLs."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, BinaryIO, ClassVar, Protocol, TypeVar, cast, runtime_checkable

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    BackendUnavailable,
    CapabilityNotSupported,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)
from remote_store._models import FileInfo, WriteResult
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from contextlib import AbstractContextManager

    from remote_store._config import RetryPolicy
    from remote_store._models import FolderEntry, FolderInfo
    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")

_CAPABILITIES = CapabilitySet({Capability.READ, Capability.METADATA, Capability.LAZY_READ})

_TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# Transport abstraction
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class HttpResponse:
    """Transport-level HTTP response."""

    status: int
    headers: dict[str, str]
    body: BinaryIO


@runtime_checkable
class HttpTransport(Protocol):
    """Internal protocol for pluggable HTTP transports."""

    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        pass

    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        pass

    def close(self) -> None:
        pass


_TransportMethod = Callable[[str, dict[str, str], float], HttpResponse]


# ---------------------------------------------------------------------------
# urllib transport (stdlib, zero deps)
# ---------------------------------------------------------------------------


class _LimitedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that enforces a maximum number of redirects."""

    def __init__(self, max_redirects: int) -> None:
        self.max_redirects = max_redirects
        self._redirect_count = 0

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: BinaryIO,  # type: ignore[override]
        code: int,
        msg: str,
        headers: dict[str, str],  # type: ignore[override]
        newurl: str,
    ) -> urllib.request.Request | None:
        self._redirect_count += 1
        if self._redirect_count > self.max_redirects:
            raise urllib.error.HTTPError(
                newurl,
                code,
                f"Too many redirects (max {self.max_redirects})",
                headers,  # type: ignore[arg-type]
                fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


class UrllibTransport:
    """HTTP transport using stdlib ``urllib.request``.

    Note:
        Not thread-safe. The shared redirect handler's counter is reset
        per request, so concurrent calls to ``_request()`` would race on
        ``_redirect_count``. urllib openers are not thread-safe in general.
    """

    def __init__(self, *, verify_ssl: bool = True, max_redirects: int = 5) -> None:
        self._redirect_handler = _LimitedRedirectHandler(max_redirects)
        handlers: list[urllib.request.BaseHandler] = [self._redirect_handler]
        if not verify_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        self._opener = urllib.request.build_opener(*handlers)

    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a GET request."""
        return self._request(url, headers, timeout, method="GET")

    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a HEAD request."""
        return self._request(url, headers, timeout, method="HEAD")

    def close(self) -> None:
        """No-op — urllib has no connection pool to close."""

    def _request(self, url: str, headers: dict[str, str], timeout: float, *, method: str) -> HttpResponse:
        """Execute an HTTP request."""
        self._redirect_handler._redirect_count = 0
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            resp = self._opener.open(  # noqa: S310 — URL is user-provided base_url + validated path
                req,
                timeout=timeout,
            )
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            return HttpResponse(status=resp.status, headers=resp_headers, body=cast(BinaryIO, resp))  # noqa: TC006
        except urllib.error.HTTPError as exc:
            with contextlib.closing(exc):
                resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
                code = exc.code
            return HttpResponse(status=code, headers=resp_headers, body=cast(BinaryIO, io.BytesIO(b"")))  # noqa: TC006
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise BackendUnavailable(
                f"HTTP request failed: {exc}",
                backend="http",
            ) from exc


# ---------------------------------------------------------------------------
# Transport auto-detection
# ---------------------------------------------------------------------------


def _resolve_transport(
    http_client: str | None,
    *,
    verify_ssl: bool,
    max_redirects: int,
) -> HttpTransport:
    """Select and instantiate the best available HTTP transport."""
    if http_client is not None:
        if http_client == "urllib":
            return UrllibTransport(verify_ssl=verify_ssl, max_redirects=max_redirects)
        if http_client == "requests":
            return _make_requests_transport(verify_ssl=verify_ssl, max_redirects=max_redirects)
        if http_client == "httpx":
            return _make_httpx_transport(verify_ssl=verify_ssl, max_redirects=max_redirects)
        msg = f"Unknown http_client: {http_client!r}. Choose 'urllib', 'requests', or 'httpx'."
        raise ValueError(msg)

    # Auto-detect: httpx -> requests -> urllib
    with contextlib.suppress(ImportError):
        return _make_httpx_transport(verify_ssl=verify_ssl, max_redirects=max_redirects)
    with contextlib.suppress(ImportError):
        return _make_requests_transport(verify_ssl=verify_ssl, max_redirects=max_redirects)
    return UrllibTransport(verify_ssl=verify_ssl, max_redirects=max_redirects)


def _make_requests_transport(*, verify_ssl: bool, max_redirects: int) -> HttpTransport:
    """Create a RequestsTransport (raises ImportError if requests not installed)."""
    from remote_store.backends._http_requests import RequestsTransport

    return RequestsTransport(verify_ssl=verify_ssl, max_redirects=max_redirects)


def _make_httpx_transport(*, verify_ssl: bool, max_redirects: int) -> HttpTransport:
    """Create an HttpxTransport (raises ImportError if httpx not installed)."""
    from remote_store.backends._http_httpx import HttpxTransport

    return HttpxTransport(verify_ssl=verify_ssl, max_redirects=max_redirects)


# ---------------------------------------------------------------------------
# ReadOnlyHttpBackend
# ---------------------------------------------------------------------------


class ReadOnlyHttpBackend(Backend):
    """Read-only backend for HTTP/HTTPS URLs.

    Treats an HTTP endpoint as a file store with
    ``{READ, METADATA, LAZY_READ}`` capabilities (``read()`` streams the
    response body lazily rather than buffering the whole file). Write,
    delete, list, move, and copy operations raise
    ``CapabilityNotSupported``.

    Args:
        base_url: Root URL. A trailing ``/`` is appended if missing.
        headers: Custom headers sent with every request (e.g. API keys).
        timeout: Request timeout in seconds.
        retry: Retry policy for transient errors.
        http_client: Force a specific transport (``"urllib"``, ``"requests"``,
            or ``"httpx"``). Auto-detected if ``None``.
        verify_ssl: Whether to verify TLS certificates.
        max_redirects: Maximum number of redirects to follow.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _CAPABILITIES

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        retry: RetryPolicy | None = None,
        http_client: str | None = None,
        verify_ssl: bool = True,
        max_redirects: int = 5,
    ) -> None:
        if not base_url:
            msg = "base_url must not be empty"
            raise ValueError(msg)
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            msg = f"base_url must use http or https scheme, got {parsed.scheme!r}"
            raise ValueError(msg)
        self._base_url = base_url if base_url.endswith("/") else base_url + "/"
        self._headers = dict(headers) if headers else {}
        self._timeout = timeout
        self._retry = retry
        self._transport = _resolve_transport(http_client, verify_ssl=verify_ssl, max_redirects=max_redirects)
        self._head_blocked = False

    # region: properties

    @property
    def name(self) -> str:
        return "http"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    # endregion

    # region: read operations

    def exists(self, path: str) -> bool:
        """Check existence via HEAD request (falls back to ranged GET)."""
        resp = self._head_or_range_get(path)
        try:
            if resp.status == 404:
                return False
            if 200 <= resp.status < 300:
                return True
            raise self._classify_status(resp.status, path)
        finally:
            resp.body.close()

    def is_file(self, path: str) -> bool:
        """HTTP resources are always files."""
        return self.exists(path)

    def is_folder(self, path: str) -> bool:
        """HTTP has no folder concept — always returns False."""
        return False

    def read(self, path: str) -> BinaryIO:
        """Stream-read a file via GET."""
        resp = self._get(path)
        try:
            self._check_status(resp, path)
        except Exception:
            resp.body.close()
            raise
        return cast(BinaryIO, _ErrorMappingStream(resp.body, self._map_stream_error, path))  # noqa: TC006

    def read_bytes(self, path: str) -> bytes:
        """Buffered-read a file via GET."""
        resp = self._get(path)
        try:
            self._check_status(resp, path)
            return resp.body.read()
        finally:
            resp.body.close()

    # endregion

    # region: metadata

    def get_file_info(self, path: str) -> FileInfo:
        """Get file metadata via HEAD request (falls back to ranged GET)."""
        resp = self._head_or_range_get(path)
        try:
            self._check_status(resp, path)
            return self._build_file_info(path, resp.headers)
        finally:
            resp.body.close()

    def get_folder_info(self, path: str) -> FolderInfo:
        """HTTP has no folder concept — always raises NotFound."""
        raise NotFound(f"No folder concept in HTTP backend: {path}", path=path, backend=self.name)

    # endregion

    # region: unsupported operations

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="write", backend=self.name)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="atomic_write", backend=self.name)

    def open_atomic(self, path: str, *, overwrite: bool = False) -> AbstractContextManager[BinaryIO]:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="atomic_write", backend=self.name)

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="delete", backend=self.name)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="delete", backend=self.name)

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        raise CapabilityNotSupported("HTTP backend does not support listing", capability="list", backend=self.name)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        raise CapabilityNotSupported("HTTP backend does not support listing", capability="list", backend=self.name)

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        raise CapabilityNotSupported("HTTP backend does not support listing", capability="list", backend=self.name)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="move", backend=self.name)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        raise CapabilityNotSupported("HTTP backend is read-only", capability="copy", backend=self.name)

    # endregion

    # region: lifecycle

    def check_health(self) -> None:
        """Verify connectivity by sending HEAD to base_url (or GET if HEAD is blocked).

        Note:
            The health check probes ``base_url`` (the root), not a specific
            file.  Many HTTP servers and CDNs return 403 or 404 for directory
            URLs while serving individual files normally.  A failing health
            check therefore does not necessarily mean ``read()`` or
            ``exists()`` will fail on actual file paths.
        """
        try:
            if self._head_blocked:
                resp = self._transport.get(self._base_url, {**self._headers, "Range": "bytes=0-0"}, self._timeout)
            else:
                resp = self._transport.head(self._base_url, self._headers, self._timeout)
                if resp.status in (401, 403):
                    try:
                        fallback = self._transport.get(
                            self._base_url, {**self._headers, "Range": "bytes=0-0"}, self._timeout
                        )
                    except Exception:
                        resp.body.close()
                        raise
                    if 200 <= fallback.status < 300 or fallback.status == 404:
                        resp.body.close()
                        self._head_blocked = True
                        resp = fallback
                    else:
                        fallback.body.close()
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable(f"Health check failed: {exc}", backend=self.name) from exc
        try:
            if not (200 <= resp.status < 300):
                raise BackendUnavailable(f"Health check returned HTTP {resp.status}", backend=self.name)
        finally:
            resp.body.close()

    def close(self) -> None:
        """Close the underlying transport."""
        self._transport.close()

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the transport if it matches the requested type."""
        if isinstance(self._transport, type_hint):
            return self._transport
        return super().unwrap(type_hint)

    def native_path(self, path: str) -> str:
        """Return the full URL for a backend-relative key."""
        if not path:
            return self._base_url
        return self._base_url + urllib.parse.quote(path, safe="/")

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with HTTP-specific details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="http"`` and ``details`` containing
            ``url`` and ``method``.
        """
        from remote_store._resolution import ResolutionPlan as _RP
        from remote_store._resolution import _strip_userinfo

        url = self.native_path(path)
        return _RP(
            kind="http",
            backend=self.name,
            key=path,
            native_path=url,
            details={
                "url": _strip_userinfo(url),
                "method": "GET",
            },
        )

    def to_key(self, native_path: str) -> str:
        """Strip base_url prefix to get a backend-relative key."""
        if native_path.startswith(self._base_url):
            return urllib.parse.unquote(native_path[len(self._base_url) :])
        return native_path

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        masked_headers = {k: "***" for k in self._headers} if self._headers else {}
        return f"ReadOnlyHttpBackend(base_url={self._base_url!r}, headers={masked_headers!r}, timeout={self._timeout})"

    # endregion

    # region: private helpers

    def _check_status(self, resp: HttpResponse, path: str) -> None:
        """Raise on non-2xx status codes."""
        if resp.status == 404:
            raise NotFound(f"Not found: {path}", path=path, backend=self.name)
        if not (200 <= resp.status < 300):
            raise self._classify_status(resp.status, path)

    def _url(self, path: str) -> str:
        """Build a full URL from a backend-relative path."""
        return self.native_path(path)

    def _get(self, path: str) -> HttpResponse:
        """Send a GET request with retry support."""
        return self._request_with_retry(self._transport.get, path)

    def _head(self, path: str) -> HttpResponse:
        """Send a HEAD request with retry support."""
        return self._request_with_retry(self._transport.head, path)

    def _head_or_range_get(self, path: str) -> HttpResponse:
        """HEAD with transparent fallback to ranged GET on 401/403.

        Some CDN-fronted servers (e.g. Cloudflare) block HEAD while allowing
        GET.  When HEAD returns 401 or 403, a ``GET`` with ``Range: bytes=0-0`` is
        tried instead — downloading at most 1 byte.  On success the result
        is cached for the backend's lifetime so subsequent calls skip HEAD.
        """
        if self._head_blocked:
            return self._range_get(path)
        resp = self._head(path)
        if resp.status not in (401, 403):
            return resp
        # HEAD was denied — try ranged GET before raising.
        try:
            fallback = self._range_get(path)
        except Exception:
            resp.body.close()
            raise
        if 200 <= fallback.status < 300 or fallback.status == 404:
            resp.body.close()
            self._head_blocked = True
            return fallback
        # Ranged GET also failed — raise from the original HEAD status.
        fallback.body.close()
        return resp

    def _range_get(self, path: str) -> HttpResponse:
        """Send a single GET with ``Range: bytes=0-0`` (no retry)."""
        url = self._url(path)
        headers = {**self._headers, "Range": "bytes=0-0"}
        return self._transport.get(url, headers, self._timeout)

    def _request_with_retry(
        self,
        transport_method: _TransportMethod,
        path: str,
    ) -> HttpResponse:
        """Execute a request with optional retry on transient errors."""
        import random
        import time

        url = self._url(path)

        if self._retry is None or self._retry.max_attempts <= 1:
            return transport_method(url, self._headers, self._timeout)

        last_exc: Exception | None = None
        last_resp: HttpResponse | None = None
        start = time.monotonic()

        for attempt in range(self._retry.max_attempts):
            if self._retry.timeout is not None and time.monotonic() - start >= self._retry.timeout:
                break

            try:
                resp = transport_method(url, self._headers, self._timeout)
            except BackendUnavailable as exc:
                last_exc = exc
                last_resp = None
            else:
                if resp.status not in _TRANSIENT_STATUSES:
                    return resp
                last_resp = resp
                last_exc = None

            if attempt < self._retry.max_attempts - 1:
                delay = min(
                    self._retry.backoff_base * (2**attempt),
                    self._retry.backoff_max,
                )
                delay += random.uniform(0, self._retry.jitter)  # noqa: S311
                # Honour Retry-After header as delay floor (HTTP-RETRY-001)
                if last_resp is not None:
                    retry_after = _parse_retry_after(last_resp.headers.get("retry-after"))
                    if retry_after is not None:
                        delay = max(delay, retry_after)
                time.sleep(delay)

        if last_exc is not None:
            raise last_exc
        if last_resp is not None:
            return last_resp
        raise BackendUnavailable("All retry attempts exhausted", backend=self.name)  # pragma: no cover

    def _classify_status(self, status: int, path: str) -> RemoteStoreError:
        """Map an HTTP status code to a remote-store error."""
        if status == 404:  # pragma: no cover — 404 handled inline before _classify_status
            return NotFound(f"Not found: {path}", path=path, backend=self.name)
        if status in (401, 403):
            return PermissionDenied(f"Access denied: {path}", path=path, backend=self.name)
        if status in _TRANSIENT_STATUSES:
            return BackendUnavailable(f"HTTP {status}: {path}", path=path, backend=self.name)
        return RemoteStoreError(f"HTTP {status}: {path}", path=path, backend=self.name)

    def _map_stream_error(self, exc: Exception, path: str) -> RemoteStoreError:
        """Error mapper for _ErrorMappingStream."""
        return BackendUnavailable(f"Stream error: {exc}", path=path, backend=self.name)

    def _build_file_info(self, path: str, headers: dict[str, str]) -> FileInfo:
        """Build a FileInfo from HTTP response headers."""
        name = path.rsplit("/", 1)[-1] if "/" in path else path

        # Prefer Content-Range total (present in 206 ranged GET fallback).
        size = _parse_content_range_total(headers.get("content-range"))
        if size is None:
            size_str = headers.get("content-length", "")
            size = int(size_str) if size_str.isdigit() else 0

        modified_at = datetime.min.replace(tzinfo=timezone.utc)
        last_modified = headers.get("last-modified")
        if last_modified:
            with contextlib.suppress(Exception):
                modified_at = parsedate_to_datetime(last_modified)
                if modified_at.tzinfo is None:  # pragma: no cover — defensive for non-standard dates
                    modified_at = modified_at.replace(tzinfo=timezone.utc)

        etag = headers.get("etag")
        content_type = headers.get("content-type")

        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=size,
            modified_at=modified_at,
            etag=etag,
            content_type=content_type,
            extra={"headers": dict(headers)},
        )

    # endregion


def _parse_content_range_total(value: str | None) -> int | None:
    """Extract the total size from a ``Content-Range`` header.

    Parses ``bytes 0-0/12345`` and returns ``12345``.  Returns ``None``
    when the header is absent, unparseable, or uses ``*`` (unknown length).
    """
    if not value:
        return None
    # Format: "bytes 0-0/12345" or "bytes */12345"
    parts = value.rsplit("/", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    Supports both delay-seconds (``120``) and HTTP-date formats.
    Returns ``None`` if the header is missing or unparseable.
    """
    if not value:
        return None
    # Try integer seconds first
    try:
        return float(value)
    except ValueError:
        pass
    # Try HTTP-date format
    try:
        target = parsedate_to_datetime(value)
        delta = (target - datetime.now(tz=timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:  # noqa: BLE001
        return None
