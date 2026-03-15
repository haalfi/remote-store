"""HTTP transport using the ``requests`` library."""

from __future__ import annotations

import io
from typing import BinaryIO, cast

from remote_store._errors import BackendUnavailable
from remote_store.backends._http import HttpResponse

try:
    import requests
except ImportError as exc:  # pragma: no cover
    msg = "requests is required for RequestsTransport. Install it with: pip install remote-store[requests]"
    raise ImportError(msg) from exc


class RequestsTransport:
    """HTTP transport using ``requests.Session`` for connection pooling."""

    def __init__(self, *, verify_ssl: bool = True, max_redirects: int = 5) -> None:
        self._session = requests.Session()
        self._session.verify = verify_ssl
        self._session.max_redirects = max_redirects

    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a GET request."""
        try:
            resp = self._session.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
        except (requests.ConnectionError, requests.Timeout, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp.raw.decode_content = True
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast("BinaryIO", resp.raw),
        )

    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a HEAD request."""
        try:
            resp = self._session.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        except (requests.ConnectionError, requests.Timeout, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast("BinaryIO", io.BytesIO(b"")),
        )

    def close(self) -> None:
        """Close the requests session."""
        self._session.close()
