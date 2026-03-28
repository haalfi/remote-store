"""HTTP transport using the ``requests`` library."""

from __future__ import annotations

import io
from typing import BinaryIO, cast

from remote_store._errors import BackendUnavailable
from remote_store.backends._http import HttpResponse

try:
    import requests
    import urllib3
except ImportError as exc:  # pragma: no cover
    msg = "requests is required for RequestsTransport. Install it with: pip install remote-store[requests]"
    raise ImportError(msg) from exc


class _Urllib3StreamAdapter(io.RawIOBase):
    """Wraps ``urllib3.HTTPResponse`` to convert urllib3 exceptions to ``OSError``.

    ``urllib3.exceptions.ProtocolError`` and ``IncompleteRead`` are not
    ``OSError`` subclasses, so ``_ErrorMappingStream`` cannot catch them.
    This adapter re-raises them as ``OSError``.
    """

    def __init__(self, raw: urllib3.HTTPResponse) -> None:
        self._raw = raw

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        try:
            return self._raw.readinto(b)  # type: ignore[arg-type]
        except urllib3.exceptions.HTTPError as exc:
            raise OSError(str(exc)) from exc

    def read(self, size: int = -1) -> bytes:
        try:
            return self._raw.read(amt=size if size >= 0 else None)
        except urllib3.exceptions.HTTPError as exc:
            raise OSError(str(exc)) from exc

    def close(self) -> None:
        self._raw.close()
        super().close()


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
            body=cast("BinaryIO", _Urllib3StreamAdapter(resp.raw)),
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
