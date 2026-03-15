"""HTTP transport using the ``httpx`` library."""

from __future__ import annotations

import io
from typing import BinaryIO, cast

from remote_store._errors import BackendUnavailable
from remote_store.backends._http import HttpResponse

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    msg = "httpx is required for HttpxTransport. Install it with: pip install remote-store[httpx]"
    raise ImportError(msg) from exc


class HttpxTransport:
    """HTTP transport using ``httpx.Client`` for connection pooling and HTTP/2."""

    def __init__(self, *, verify_ssl: bool = True, max_redirects: int = 5) -> None:
        self._client = httpx.Client(verify=verify_ssl, follow_redirects=True, max_redirects=max_redirects)

    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a GET request."""
        try:
            resp = self._client.send(
                self._client.build_request("GET", url, headers=headers),
                stream=True,
                timeout=timeout,
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast("BinaryIO", resp.stream),
        )

    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a HEAD request."""
        try:
            resp = self._client.head(url, headers=headers, timeout=timeout)
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast("BinaryIO", io.BytesIO(b"")),
        )

    def close(self) -> None:
        """Close the httpx client."""
        self._client.close()
