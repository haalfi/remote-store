"""HTTP transport using the ``httpx`` library."""

from __future__ import annotations

import io
from typing import BinaryIO, cast  # noqa: TCH003 — runtime ref needed for CodeQL

from remote_store._errors import BackendUnavailable
from remote_store.backends._http import HttpResponse

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    msg = "httpx is required for HttpxTransport. Install it with: pip install remote-store[httpx]"
    raise ImportError(msg) from exc


class _HttpxStreamAdapter(io.RawIOBase):
    """Adapts an ``httpx.Response`` stream to a ``BinaryIO`` interface.

    Reads chunks from ``httpx.Response.iter_bytes()`` and buffers them
    so callers get a standard ``read()`` / ``readinto()`` interface
    without loading the full response into memory.

    httpx stream errors (``ReadError``, ``RemoteProtocolError``, etc.)
    are converted to ``OSError`` so ``_ErrorMappingStream`` can catch them.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self._iter = response.iter_bytes(chunk_size=65536)
        self._buf = b""

    def readable(self) -> bool:
        return True

    def _next_chunk(self) -> bytes:
        """Get the next chunk, converting httpx errors to OSError."""
        try:
            return next(self._iter)
        except StopIteration:
            raise
        except httpx.StreamError as exc:
            raise OSError(str(exc)) from exc

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        """Read up to len(b) bytes into *b*."""
        data = self.read(len(b))
        if not data:
            return 0
        view = memoryview(b)[: len(data)]
        view[:] = data
        return len(data)

    def read(self, size: int = -1) -> bytes:
        """Read up to *size* bytes (all remaining if *size* < 0)."""
        if size < 0:
            chunks = [self._buf]
            self._buf = b""
            try:
                for chunk in self._iter:
                    chunks.append(chunk)
            except httpx.StreamError as exc:
                raise OSError(str(exc)) from exc
            return b"".join(chunks)

        while len(self._buf) < size:
            try:
                self._buf += self._next_chunk()
            except StopIteration:
                break

        result = self._buf[:size]
        self._buf = self._buf[size:]
        return result

    def close(self) -> None:
        self._response.close()
        super().close()


class HttpxTransport:
    """HTTP transport using ``httpx.Client`` for connection pooling and HTTP/2."""

    def __init__(self, *, verify_ssl: bool = True, max_redirects: int = 5) -> None:
        self._client = httpx.Client(verify=verify_ssl, follow_redirects=True, max_redirects=max_redirects)

    def get(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a streaming GET request."""
        try:
            resp = self._client.send(
                self._client.build_request("GET", url, headers=headers, timeout=timeout),
                stream=True,
            )
        except (httpx.TransportError, httpx.HTTPStatusError, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast(BinaryIO, _HttpxStreamAdapter(resp)),  # noqa: TC006
        )

    def head(self, url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
        """Send a HEAD request."""
        try:
            resp = self._client.head(url, headers=headers, timeout=timeout)
        except (httpx.TransportError, httpx.HTTPStatusError, OSError) as exc:
            raise BackendUnavailable(f"HTTP request failed: {exc}", backend="http") from exc
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=cast(BinaryIO, io.BytesIO(b"")),  # noqa: TC006
        )

    def close(self) -> None:
        """Close the httpx client."""
        self._client.close()
