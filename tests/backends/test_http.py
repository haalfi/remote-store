"""Backend-specific tests for ReadOnlyHttpBackend."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")

from remote_store._errors import BackendUnavailable, CapabilityNotSupported, NotFound, PermissionDenied  # noqa: E402
from remote_store._models import FileInfo  # noqa: E402
from remote_store.backends._http import ReadOnlyHttpBackend, UrllibTransport  # noqa: E402


def _httpx_installed() -> bool:
    try:
        import httpx  # noqa: F401

        return True
    except ImportError:
        return False


if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer
    from werkzeug.wrappers import Request, Response


@pytest.fixture()
def httpserver_with_files(httpserver: HTTPServer) -> HTTPServer:
    """Pre-seed an HTTP server with test files."""
    # Override respond_nohandler to return 404 instead of 500
    from werkzeug.wrappers import Response as WerkzeugResponse

    httpserver.respond_nohandler = lambda request, extra_message="": WerkzeugResponse(  # type: ignore[assignment]
        b"Not Found", status=404
    )

    httpserver.expect_request("/files/hello.txt").respond_with_data(
        b"hello world",
        content_type="text/plain",
        headers={"Content-Length": "11", "Last-Modified": "Sun, 15 Mar 2026 12:00:00 GMT", "ETag": '"abc123"'},
    )
    httpserver.expect_request("/files/data.bin").respond_with_data(
        b"\x00\x01\x02\x03",
        content_type="application/octet-stream",
        headers={"Content-Length": "4"},
    )
    httpserver.expect_request("/files/no-headers.txt").respond_with_data(
        b"minimal",
        content_type="text/plain",
    )
    httpserver.expect_request("/files/large.bin").respond_with_data(
        b"A" * 1000,
        content_type="application/octet-stream",
        headers={"Content-Length": "1000"},
    )
    return httpserver


@pytest.fixture()
def backend(httpserver_with_files: HTTPServer) -> ReadOnlyHttpBackend:
    """Create a ReadOnlyHttpBackend pointed at the test server."""
    return ReadOnlyHttpBackend(
        base_url=httpserver_with_files.url_for("/files/"),
        http_client="urllib",
    )


class TestHttpRead:
    """HTTP-001, HTTP-002: read operations."""

    @pytest.mark.spec("SIO-001")
    def test_read_returns_streaming_binary(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-001: read() returns streaming BinaryIO, chunked read works."""
        stream = backend.read("hello.txt")
        data = stream.read()
        assert data == b"hello world"
        stream.close()

    @pytest.mark.spec("SIO-001")
    def test_read_supports_chunked_reads(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-001: Chunked reads work."""
        stream = backend.read("large.bin")
        chunks = []
        while True:
            chunk = stream.read(100)
            if not chunk:
                break
            chunks.append(chunk)
        assert b"".join(chunks) == b"A" * 1000
        stream.close()

    @pytest.mark.spec("BE-007")
    def test_read_bytes(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-002: read_bytes() returns full content."""
        assert backend.read_bytes("hello.txt") == b"hello world"

    @pytest.mark.spec("BE-006")
    def test_read_not_found(self, backend: ReadOnlyHttpBackend) -> None:
        """Read of missing file raises NotFound."""
        with pytest.raises(NotFound):
            backend.read("nonexistent.txt")

    @pytest.mark.spec("BE-007")
    def test_read_bytes_not_found(self, backend: ReadOnlyHttpBackend) -> None:
        """Read_bytes of missing file raises NotFound."""
        with pytest.raises(NotFound):
            backend.read_bytes("nonexistent.txt")


class TestHttpExists:
    """HTTP-003: exists(), is_file(), is_folder()."""

    @pytest.mark.spec("BE-004")
    def test_exists_true(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-003: exists() returns True for 200."""
        assert backend.exists("hello.txt") is True

    @pytest.mark.spec("BE-004")
    def test_exists_false(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-003: exists() returns False for 404."""
        assert backend.exists("nonexistent.txt") is False

    @pytest.mark.spec("BE-005")
    def test_is_file(self, backend: ReadOnlyHttpBackend) -> None:
        """is_file() matches exists() for HTTP resources."""
        assert backend.is_file("hello.txt") is True
        assert backend.is_file("nonexistent.txt") is False

    @pytest.mark.spec("BE-005")
    def test_is_folder_always_false(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-017: is_folder() always returns False."""
        assert backend.is_folder("hello.txt") is False
        assert backend.is_folder("any/path") is False
        assert backend.is_folder("") is False


class TestHttpMetadata:
    """HTTP-004, HTTP-005: get_file_info()."""

    @pytest.mark.spec("BE-016")
    def test_get_file_info_maps_headers(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-004: get_file_info() maps headers to FileInfo fields."""
        fi = backend.get_file_info("hello.txt")
        assert isinstance(fi, FileInfo)
        assert fi.name == "hello.txt"
        assert fi.size == 11
        assert fi.checksum == '"abc123"'
        assert fi.content_type == "text/plain"
        assert fi.extra is not None
        assert "headers" in fi.extra

    @pytest.mark.spec("BE-016")
    def test_get_file_info_missing_headers(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-005: Missing Content-Length/Last-Modified handled gracefully."""
        fi = backend.get_file_info("no-headers.txt")
        assert fi.name == "no-headers.txt"
        # Content-Length may or may not be present depending on server behavior
        # The key test: no exceptions raised, FileInfo is valid
        assert isinstance(fi.size, int)
        assert fi.modified_at is not None

    @pytest.mark.spec("BE-016")
    def test_get_file_info_not_found(self, backend: ReadOnlyHttpBackend) -> None:
        """get_file_info() raises NotFound for 404."""
        with pytest.raises(NotFound):
            backend.get_file_info("nonexistent.txt")

    @pytest.mark.spec("BE-017")
    def test_get_folder_info_always_not_found(self, backend: ReadOnlyHttpBackend) -> None:
        """get_folder_info() always raises NotFound."""
        with pytest.raises(NotFound):
            backend.get_folder_info("any/path")


class TestHttpErrorMapping:
    """HTTP-006: Error mapping from HTTP status codes."""

    def test_401_raises_permission_denied(self, httpserver: HTTPServer) -> None:
        """401 -> PermissionDenied."""
        httpserver.expect_request("/auth/secret.txt", method="GET").respond_with_data(b"", status=401)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/auth/"), http_client="urllib")
        with pytest.raises(PermissionDenied):
            b.read_bytes("secret.txt")

    def test_403_raises_permission_denied(self, httpserver: HTTPServer) -> None:
        """403 -> PermissionDenied."""
        httpserver.expect_request("/auth/forbidden.txt", method="GET").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/auth/"), http_client="urllib")
        with pytest.raises(PermissionDenied):
            b.read_bytes("forbidden.txt")

    def test_500_raises_backend_unavailable(self, httpserver: HTTPServer) -> None:
        """500 -> BackendUnavailable."""
        httpserver.expect_request("/err/broken.txt", method="GET").respond_with_data(b"", status=500)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/err/"), http_client="urllib")
        with pytest.raises(BackendUnavailable):
            b.read_bytes("broken.txt")

    def test_404_raises_not_found(self, httpserver: HTTPServer) -> None:
        """404 -> NotFound."""
        httpserver.expect_request("/err/missing.txt", method="GET").respond_with_data(b"", status=404)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/err/"), http_client="urllib")
        with pytest.raises(NotFound):
            b.read_bytes("missing.txt")


class TestHttpPaths:
    """HTTP-007, HTTP-008, HTTP-009: path handling."""

    @pytest.mark.spec("NPR-003")
    def test_native_path_returns_full_url(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-007: native_path() returns full URL."""
        url = backend.native_path("population/2024.csv")
        assert url.endswith("/files/population/2024.csv")
        assert url.startswith("http://")

    @pytest.mark.spec("NPR-003")
    def test_to_key_strips_base_url(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-008: to_key() strips base_url prefix."""
        url = backend.native_path("data/file.csv")
        key = backend.to_key(url)
        assert key == "data/file.csv"

    @pytest.mark.spec("NPR-003")
    def test_native_path_round_trip(self, backend: ReadOnlyHttpBackend) -> None:
        """Round-trip: to_key(native_path(key)) == key."""
        key = "some/nested/path.txt"
        assert backend.to_key(backend.native_path(key)) == key

    def test_path_with_special_characters(self, httpserver: HTTPServer) -> None:
        """HTTP-009: Special characters are URL-encoded."""
        from werkzeug.wrappers import Response as WerkzeugResponse

        httpserver.respond_nohandler = lambda request, extra_message="": WerkzeugResponse(  # type: ignore[assignment]
            b"Not Found", status=404
        )

        def handler(request: Request) -> Response:
            from werkzeug.wrappers import Response

            # werkzeug decodes the percent-encoded path
            if request.path == "/enc/file name.txt":
                return Response(b"ok", status=200)
            return Response(b"not found", status=404)

        httpserver.expect_request("/enc/file name.txt").respond_with_handler(handler)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/enc/"), http_client="urllib")
        assert b.read_bytes("file name.txt") == b"ok"

    def test_native_path_empty_returns_base_url(self, backend: ReadOnlyHttpBackend) -> None:
        """native_path('') returns the base_url."""
        result = backend.native_path("")
        assert result.endswith("/files/")

    def test_to_key_non_matching_prefix_passthrough(self) -> None:
        """to_key returns path unchanged when it doesn't start with base_url."""
        b = ReadOnlyHttpBackend(base_url="http://example.com/data/", http_client="urllib")
        assert b.to_key("http://other.com/file.txt") == "http://other.com/file.txt"

    def test_round_trip_with_special_chars(self) -> None:
        """to_key(native_path(key)) == key for paths with spaces and unicode."""
        b = ReadOnlyHttpBackend(base_url="http://example.com/data/", http_client="urllib")
        for key in ("file name.txt", "path/with spaces/file.txt", "données/résumé.csv"):
            assert b.to_key(b.native_path(key)) == key


class TestHttpCustomHeaders:
    """HTTP-010: Custom headers are sent with every request."""

    def test_custom_headers_sent(self, httpserver: HTTPServer) -> None:
        """HTTP-010: Custom headers are included in requests."""

        def handler(request: Request) -> Response:
            from werkzeug.wrappers import Response

            if request.headers.get("X-Api-Key") == "test-key-123":
                return Response(b"authorized", status=200)
            return Response(b"unauthorized", status=401)

        httpserver.expect_request("/api/data.txt").respond_with_handler(handler)
        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/api/"),
            headers={"X-Api-Key": "test-key-123"},
            http_client="urllib",
        )
        assert b.read_bytes("data.txt") == b"authorized"


class TestHttpTimeout:
    """HTTP-012: Timeout raises BackendUnavailable."""

    def test_timeout_raises_backend_unavailable(self, httpserver: HTTPServer) -> None:
        """HTTP-012: Connection timeout raises BackendUnavailable."""
        import threading

        gate = threading.Event()

        def slow_handler(request: Request) -> Response:
            from werkzeug.wrappers import Response

            gate.wait(timeout=5)  # blocks until client disconnects or test ends
            return Response(b"slow", status=200)

        httpserver.expect_request("/slow/data.txt").respond_with_handler(slow_handler)
        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/slow/"),
            timeout=0.05,
            http_client="urllib",
        )
        try:
            with pytest.raises(BackendUnavailable):
                b.read_bytes("data.txt")
        finally:
            gate.set()  # unblock the server thread


class TestHttpHealthCheck:
    """HTTP-013: check_health()."""

    @pytest.mark.spec("BE-020")
    def test_check_health_success(self, httpserver: HTTPServer) -> None:
        """HTTP-013: check_health() sends HEAD to base_url."""
        httpserver.expect_request("/health/", method="HEAD").respond_with_data(b"", status=200)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/health/"), http_client="urllib")
        b.check_health()  # Should not raise

    @pytest.mark.spec("BE-020")
    def test_check_health_failure(self, httpserver: HTTPServer) -> None:
        """check_health() raises BackendUnavailable on server error."""
        httpserver.expect_request("/bad/", method="HEAD").respond_with_data(b"", status=500)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/bad/"), http_client="urllib")
        with pytest.raises(BackendUnavailable):
            b.check_health()


class TestHttpUnsupportedOperations:
    """HTTP-014: Write/delete/move/copy raise CapabilityNotSupported."""

    def test_write_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.write("x.txt", b"data")

    def test_write_atomic_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.write_atomic("x.txt", b"data")

    def test_open_atomic_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.open_atomic("x.txt")

    def test_delete_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.delete("x.txt")

    def test_delete_folder_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.delete_folder("dir")

    def test_list_files_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            list(backend.list_files(""))

    def test_list_folders_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            list(backend.list_folders(""))

    def test_iter_children_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            list(backend.iter_children(""))

    def test_move_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.move("a.txt", "b.txt")

    def test_copy_raises(self, backend: ReadOnlyHttpBackend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.copy("a.txt", "b.txt")


class TestHttpLifecycle:
    """HTTP-015: close() and transport."""

    @pytest.mark.spec("BE-020")
    def test_close_is_callable(self, backend: ReadOnlyHttpBackend) -> None:
        """HTTP-015: close() is callable and safe."""
        backend.close()
        backend.close()  # Double-close is safe

    def test_unwrap_urllib_transport(self, backend: ReadOnlyHttpBackend) -> None:
        """unwrap(UrllibTransport) returns the transport."""
        transport = backend.unwrap(UrllibTransport)
        assert isinstance(transport, UrllibTransport)

    def test_unwrap_unknown_raises(self, backend: ReadOnlyHttpBackend) -> None:
        """unwrap(str) raises CapabilityNotSupported."""
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)


class TestHttpTransportDetection:
    """HTTP-016: Transport auto-detection."""

    def test_urllib_is_default(self, httpserver: HTTPServer) -> None:
        """HTTP-016: urllib is the baseline fallback."""
        httpserver.expect_request("/detect/test.txt").respond_with_data(b"ok")
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/detect/"), http_client="urllib")
        assert b.read_bytes("test.txt") == b"ok"

    def test_invalid_http_client_raises(self) -> None:
        """Unknown http_client raises ValueError."""
        with pytest.raises(ValueError, match="Unknown http_client"):
            ReadOnlyHttpBackend(base_url="http://example.com/", http_client="invalid")


class TestHttpConstructor:
    """Constructor validation and normalization."""

    def test_trailing_slash_normalization(self) -> None:
        """base_url gets trailing slash added if missing."""
        b = ReadOnlyHttpBackend(base_url="http://example.com/data", http_client="urllib")
        assert b.native_path("") == "http://example.com/data/"

    def test_trailing_slash_preserved(self) -> None:
        """base_url with trailing slash is preserved."""
        b = ReadOnlyHttpBackend(base_url="http://example.com/data/", http_client="urllib")
        assert b.native_path("") == "http://example.com/data/"

    def test_empty_base_url_raises(self) -> None:
        """Empty base_url raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            ReadOnlyHttpBackend(base_url="", http_client="urllib")

    def test_invalid_scheme_raises(self) -> None:
        """Non-http(s) schemes are rejected."""
        with pytest.raises(ValueError, match="http or https scheme"):
            ReadOnlyHttpBackend(base_url="ftp://example.com/data/", http_client="urllib")

    def test_file_scheme_raises(self) -> None:
        """file:// scheme is rejected (security)."""
        with pytest.raises(ValueError, match="http or https scheme"):
            ReadOnlyHttpBackend(base_url="file:///etc/passwd", http_client="urllib")

    def test_https_scheme_accepted(self) -> None:
        """https:// scheme is accepted."""
        b = ReadOnlyHttpBackend(base_url="https://example.com/", http_client="urllib")
        assert b.native_path("") == "https://example.com/"

    def test_repr_masks_headers(self) -> None:
        """AF-008: repr masks header values."""
        b = ReadOnlyHttpBackend(
            base_url="http://example.com/",
            headers={"Authorization": "Bearer secret-token"},
            http_client="urllib",
        )
        r = repr(b)
        assert "secret-token" not in r
        assert "***" in r
        assert "Authorization" in r

    def test_verify_ssl_false(self) -> None:
        """verify_ssl=False creates an opener with a permissive SSL handler."""
        import urllib.request

        b = ReadOnlyHttpBackend(
            base_url="http://example.com/",
            http_client="urllib",
            verify_ssl=False,
        )
        transport = b.unwrap(UrllibTransport)
        https_handlers = [h for h in transport._opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
        assert len(https_handlers) == 1
        assert https_handlers[0]._context.check_hostname is False


class TestHttpRetry:
    """HTTP-RETRY-001: Retry with backoff and Retry-After."""

    def test_retry_on_transient_status(self, httpserver: HTTPServer) -> None:
        """Transient 503 is retried and succeeds on next attempt."""
        from werkzeug.wrappers import Response as WerkzeugResponse

        call_count = 0

        def handler(request: Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return WerkzeugResponse(b"unavailable", status=503)
            return WerkzeugResponse(b"ok", status=200, content_type="text/plain")

        httpserver.expect_request("/retry/file.txt", method="GET").respond_with_handler(handler)
        from remote_store._config import RetryPolicy

        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/retry/"),
            http_client="urllib",
            retry=RetryPolicy(max_attempts=3, backoff_base=0.01, backoff_max=0.02, jitter=0.0),
        )
        assert b.read_bytes("file.txt") == b"ok"
        assert call_count == 2

    def test_retry_exhausted_returns_last_response(self, httpserver: HTTPServer) -> None:
        """All attempts fail with transient error -> raises."""
        httpserver.expect_request("/retry/fail.txt", method="GET").respond_with_data(b"", status=503)
        from remote_store._config import RetryPolicy

        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/retry/"),
            http_client="urllib",
            retry=RetryPolicy(max_attempts=2, backoff_base=0.01, backoff_max=0.02, jitter=0.0),
        )
        with pytest.raises(BackendUnavailable):
            b.read_bytes("fail.txt")

    def test_retry_honours_retry_after_header(self, httpserver: HTTPServer) -> None:
        """Retry-After header is used as delay floor."""
        from werkzeug.wrappers import Response as WerkzeugResponse

        call_count = 0

        def handler(request: Request) -> Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return WerkzeugResponse(
                    b"rate limited",
                    status=429,
                    headers={"Retry-After": "0"},
                )
            return WerkzeugResponse(b"ok", status=200, content_type="text/plain")

        httpserver.expect_request("/retry/rate.txt", method="GET").respond_with_handler(handler)
        from remote_store._config import RetryPolicy

        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/retry/"),
            http_client="urllib",
            retry=RetryPolicy(max_attempts=3, backoff_base=0.01, backoff_max=0.02, jitter=0.0),
        )
        assert b.read_bytes("rate.txt") == b"ok"
        assert call_count == 2

    def test_retry_on_connection_error(self, httpserver: HTTPServer) -> None:
        """Connection errors are retried."""
        from remote_store._config import RetryPolicy

        # Point at a port that's not listening
        b = ReadOnlyHttpBackend(
            base_url="http://127.0.0.1:1/retry/",
            http_client="urllib",
            timeout=0.1,
            retry=RetryPolicy(max_attempts=2, backoff_base=0.01, backoff_max=0.02, jitter=0.0),
        )
        with pytest.raises(BackendUnavailable):
            b.read_bytes("file.txt")

    def test_retry_timeout_aborts_early(self, httpserver: HTTPServer) -> None:
        """Retry stops when total timeout is exceeded."""
        httpserver.expect_request("/retry/slow.txt", method="GET").respond_with_data(b"", status=503)
        from remote_store._config import RetryPolicy

        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/retry/"),
            http_client="urllib",
            retry=RetryPolicy(max_attempts=100, backoff_base=0.01, backoff_max=0.02, jitter=0.0, timeout=0.01),
        )
        with pytest.raises(BackendUnavailable):
            b.read_bytes("slow.txt")


class TestUrllibMaxRedirects:
    """max_redirects enforcement for urllib transport."""

    def test_max_redirects_prevents_infinite_loop(self, httpserver: HTTPServer) -> None:
        """Redirect loop terminates after max_redirects and raises."""
        from remote_store._errors import RemoteStoreError

        httpserver.expect_request("/redir/a", method="GET").respond_with_data(
            b"", status=302, headers={"Location": httpserver.url_for("/redir/b")}
        )
        httpserver.expect_request("/redir/b", method="GET").respond_with_data(
            b"", status=302, headers={"Location": httpserver.url_for("/redir/a")}
        )
        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/redir/"),
            http_client="urllib",
            max_redirects=2,
        )
        # Should complete (not hang) and raise on non-2xx status.
        with pytest.raises(RemoteStoreError):
            b.read_bytes("a")

    def test_successful_redirect(self, httpserver: HTTPServer) -> None:
        """A redirect within limits resolves to the target."""
        httpserver.expect_request("/rd/start", method="GET").respond_with_data(
            b"", status=302, headers={"Location": httpserver.url_for("/rd/end")}
        )
        httpserver.expect_request("/rd/end", method="GET").respond_with_data(b"final", content_type="text/plain")
        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/rd/"),
            http_client="urllib",
            max_redirects=5,
        )
        assert b.read_bytes("start") == b"final"


class TestHttpErrorPaths:
    """Additional error path coverage."""

    def test_exists_raises_on_server_error(self, httpserver: HTTPServer) -> None:
        """exists() raises on 500."""
        httpserver.expect_request("/errp/err.txt", method="HEAD").respond_with_data(b"", status=500)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/errp/"), http_client="urllib")
        with pytest.raises(BackendUnavailable):
            b.exists("err.txt")

    def test_read_raises_on_403(self, httpserver: HTTPServer) -> None:
        """read() raises PermissionDenied on 403."""
        httpserver.expect_request("/errp/secret.txt", method="GET").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/errp/"), http_client="urllib")
        with pytest.raises(PermissionDenied):
            b.read("secret.txt")

    def test_get_file_info_raises_on_403(self, httpserver: HTTPServer) -> None:
        """get_file_info() raises PermissionDenied when HEAD and GET both 403."""
        httpserver.expect_request("/errp/secret.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/errp/secret.txt", method="GET").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/errp/"), http_client="urllib")
        with pytest.raises(PermissionDenied):
            b.get_file_info("secret.txt")

    def test_health_check_non_2xx_raises(self, httpserver: HTTPServer) -> None:
        """Health check rejects 403."""
        httpserver.expect_request("/hc403/", method="HEAD").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/hc403/"), http_client="urllib")
        with pytest.raises(BackendUnavailable, match="403"):
            b.check_health()

    def test_health_check_connection_refused(self) -> None:
        """Health check raises BackendUnavailable on connection error."""
        b = ReadOnlyHttpBackend(base_url="http://127.0.0.1:1/", http_client="urllib", timeout=0.1)
        with pytest.raises(BackendUnavailable):
            b.check_health()

    def test_health_check_generic_exception(self) -> None:
        """Health check wraps non-BackendUnavailable exceptions."""
        from unittest.mock import patch

        b = ReadOnlyHttpBackend(base_url="http://example.com/", http_client="urllib")
        with (
            patch.object(b._transport, "head", side_effect=RuntimeError("unexpected")),
            pytest.raises(BackendUnavailable, match="unexpected"),
        ):
            b.check_health()

    def test_classify_status_generic(self, httpserver: HTTPServer) -> None:
        """Unknown status codes map to RemoteStoreError."""
        from remote_store._errors import RemoteStoreError

        httpserver.expect_request("/errp/teapot.txt", method="GET").respond_with_data(b"", status=418)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/errp/"), http_client="urllib")
        with pytest.raises(RemoteStoreError, match="418"):
            b.read_bytes("teapot.txt")

    def test_file_info_simple_name(self, httpserver: HTTPServer) -> None:
        """FileInfo name for a non-nested path."""
        httpserver.expect_request("/simple/file.txt", method="HEAD").respond_with_data(
            b"", status=200, headers={"Content-Length": "5"}
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/simple/"), http_client="urllib")
        fi = b.get_file_info("file.txt")
        assert fi.name == "file.txt"

    def test_stream_error_is_mapped(self, httpserver: HTTPServer) -> None:
        """Stream read errors are mapped to BackendUnavailable."""
        from unittest.mock import MagicMock

        from remote_store.backends._http import HttpResponse

        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/stream/"), http_client="urllib")
        # Create a mock response whose body raises on read
        broken_body = MagicMock()
        broken_body.read.side_effect = OSError("connection reset")
        mock_resp = HttpResponse(status=200, headers={}, body=broken_body)
        from unittest.mock import patch

        with patch.object(b, "_get", return_value=mock_resp):
            stream = b.read("data.bin")
            with pytest.raises(BackendUnavailable, match="Stream error"):
                stream.read()


class TestHeadFallback:
    """HTTP-FALLBACK-001: HEAD 403 falls back to ranged GET."""

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_exists_falls_back_on_head_403(self, httpserver: HTTPServer) -> None:
        """exists() succeeds via ranged GET when HEAD returns 403."""
        httpserver.expect_request("/cdn/file.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/file.txt", method="GET").respond_with_data(
            b"\x00", status=206, headers={"Content-Range": "bytes 0-0/1024"}
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        assert b.exists("file.txt") is True

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_exists_fallback_returns_false_on_404(self, httpserver: HTTPServer) -> None:
        """exists() returns False when HEAD 403 but GET 404."""
        httpserver.expect_request("/cdn/gone.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/gone.txt", method="GET").respond_with_data(b"", status=404)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        assert b.exists("gone.txt") is False

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_exists_raises_when_both_fail(self, httpserver: HTTPServer) -> None:
        """exists() raises PermissionDenied when HEAD and GET both 403."""
        httpserver.expect_request("/cdn/locked.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/locked.txt", method="GET").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        with pytest.raises(PermissionDenied):
            b.exists("locked.txt")

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_get_file_info_falls_back_on_head_403(self, httpserver: HTTPServer) -> None:
        """get_file_info() extracts metadata from ranged GET response."""
        httpserver.expect_request("/cdn/info.csv", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/info.csv", method="GET").respond_with_data(
            b"a",
            status=206,
            headers={
                "Content-Range": "bytes 0-0/5000",
                "Content-Type": "text/csv",
                "ETag": '"cdn-etag"',
                "Last-Modified": "Sun, 15 Mar 2026 12:00:00 GMT",
            },
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        fi = b.get_file_info("info.csv")
        assert fi.size == 5000
        assert fi.checksum == '"cdn-etag"'
        assert fi.content_type == "text/csv"

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_fallback_200_when_server_ignores_range(self, httpserver: HTTPServer) -> None:
        """get_file_info() works when server returns 200 ignoring Range."""
        httpserver.expect_request("/cdn/full.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/full.txt", method="GET").respond_with_data(
            b"full content",
            status=200,
            headers={"Content-Length": "12", "Content-Type": "text/plain"},
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        fi = b.get_file_info("full.txt")
        assert fi.size == 12

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_head_blocked_cached_across_calls(self, httpserver: HTTPServer) -> None:
        """After first fallback, subsequent calls skip HEAD entirely."""
        httpserver.expect_request("/cdn/a.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/a.txt", method="GET").respond_with_data(
            b"\x00", status=206, headers={"Content-Range": "bytes 0-0/10"}
        )
        httpserver.expect_request("/cdn/b.txt", method="GET").respond_with_data(
            b"\x00", status=206, headers={"Content-Range": "bytes 0-0/20"}
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        # First call triggers fallback
        assert b.exists("a.txt") is True
        assert b._head_blocked is True
        # Second call skips HEAD — no HEAD handler needed for b.txt
        fi = b.get_file_info("b.txt")
        assert fi.size == 20

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_head_401_also_triggers_fallback(self, httpserver: HTTPServer) -> None:
        """401 on HEAD also triggers ranged GET fallback."""
        httpserver.expect_request("/cdn/auth.txt", method="HEAD").respond_with_data(b"", status=401)
        httpserver.expect_request("/cdn/auth.txt", method="GET").respond_with_data(
            b"\x00", status=206, headers={"Content-Range": "bytes 0-0/100"}
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        assert b.exists("auth.txt") is True

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_check_health_falls_back_on_head_403(self, httpserver: HTTPServer) -> None:
        """check_health() succeeds via ranged GET when HEAD returns 403."""
        httpserver.expect_request("/cdn/", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/", method="GET").respond_with_data(b"\x00", status=206)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        b.check_health()  # Should not raise
        assert b._head_blocked is True

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_check_health_cached_skips_head(self, httpserver: HTTPServer) -> None:
        """check_health() skips HEAD when _head_blocked is already True."""
        httpserver.expect_request("/cdn/", method="GET").respond_with_data(b"\x00", status=200)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        b._head_blocked = True
        b.check_health()  # Should not raise, no HEAD handler needed

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_check_health_raises_when_both_fail(self, httpserver: HTTPServer) -> None:
        """check_health() raises when HEAD and GET both fail."""
        httpserver.expect_request("/cdn/", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/", method="GET").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        with pytest.raises(BackendUnavailable, match="403"):
            b.check_health()

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_fallback_get_network_error_closes_head_resp(self, httpserver: HTTPServer) -> None:
        """HEAD resp.body is closed if fallback GET raises a network error."""
        from unittest.mock import patch

        httpserver.expect_request("/cdn/err.txt", method="HEAD").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        with (
            patch.object(b, "_range_get", side_effect=BackendUnavailable("connection reset", backend="http")),
            pytest.raises(BackendUnavailable, match="connection reset"),
        ):
            b.exists("err.txt")

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_check_health_fallback_network_error_closes_head_resp(self, httpserver: HTTPServer) -> None:
        """check_health() closes HEAD resp.body if fallback GET raises."""
        from unittest.mock import patch

        httpserver.expect_request("/cdn/", method="HEAD").respond_with_data(b"", status=403)
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        with (
            patch.object(b._transport, "get", side_effect=BackendUnavailable("timeout", backend="http")),
            pytest.raises(BackendUnavailable, match="timeout"),
        ):
            b.check_health()

    @pytest.mark.spec("HTTP-FALLBACK-001")
    def test_content_range_unknown_total(self, httpserver: HTTPServer) -> None:
        """Content-Range with unknown total (*) falls back to Content-Length."""
        httpserver.expect_request("/cdn/unk.txt", method="HEAD").respond_with_data(b"", status=403)
        httpserver.expect_request("/cdn/unk.txt", method="GET").respond_with_data(
            b"\x00",
            status=206,
            headers={"Content-Range": "bytes 0-0/*", "Content-Length": "1"},
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/cdn/"), http_client="urllib")
        fi = b.get_file_info("unk.txt")
        assert fi.size == 1


class TestParseContentRangeTotal:
    """Unit tests for _parse_content_range_total."""

    def test_standard_range(self) -> None:
        from remote_store.backends._http import _parse_content_range_total

        assert _parse_content_range_total("bytes 0-0/12345") == 12345

    def test_unknown_total(self) -> None:
        from remote_store.backends._http import _parse_content_range_total

        assert _parse_content_range_total("bytes 0-0/*") is None

    def test_none(self) -> None:
        from remote_store.backends._http import _parse_content_range_total

        assert _parse_content_range_total(None) is None

    def test_empty(self) -> None:
        from remote_store.backends._http import _parse_content_range_total

        assert _parse_content_range_total("") is None

    def test_star_total(self) -> None:
        from remote_store.backends._http import _parse_content_range_total

        assert _parse_content_range_total("bytes */5000") == 5000


class TestParseRetryAfter:
    """Unit tests for _parse_retry_after."""

    def test_integer_seconds(self) -> None:
        from remote_store.backends._http import _parse_retry_after

        assert _parse_retry_after("120") == 120.0

    def test_none_value(self) -> None:
        from remote_store.backends._http import _parse_retry_after

        assert _parse_retry_after(None) is None

    def test_empty_string(self) -> None:
        from remote_store.backends._http import _parse_retry_after

        assert _parse_retry_after("") is None

    def test_http_date(self) -> None:
        from remote_store.backends._http import _parse_retry_after

        # A date in the past should return 0.0
        result = _parse_retry_after("Sun, 15 Mar 2020 12:00:00 GMT")
        assert result == 0.0

    def test_unparseable(self) -> None:
        from remote_store.backends._http import _parse_retry_after

        assert _parse_retry_after("not-a-date-or-number") is None


class TestHttpTransportAutoDetection:
    """Transport resolution and factory coverage."""

    def test_resolve_requests_transport(self) -> None:
        """Explicit requests transport can be created (if installed)."""
        try:
            b = ReadOnlyHttpBackend(base_url="http://example.com/", http_client="requests")
            b.close()
        except ImportError:
            pytest.skip("requests not installed")

    def test_resolve_httpx_transport(self) -> None:
        """Explicit httpx transport can be created (if installed)."""
        try:
            b = ReadOnlyHttpBackend(base_url="http://example.com/", http_client="httpx")
            b.close()
        except ImportError:
            pytest.skip("httpx not installed")

    def test_auto_detect_falls_back_to_urllib(self) -> None:
        """Auto-detection eventually falls back to urllib."""
        from unittest.mock import patch

        with (
            patch("remote_store.backends._http._make_httpx_transport", side_effect=ImportError),
            patch("remote_store.backends._http._make_requests_transport", side_effect=ImportError),
        ):
            b = ReadOnlyHttpBackend(base_url="http://example.com/")
            assert isinstance(b.unwrap(UrllibTransport), UrllibTransport)
            b.close()


def _requests_installed() -> bool:
    try:
        import requests  # noqa: F401

        return True
    except ImportError:
        return False


_TRANSPORT_IDS = ["requests", "httpx"]
_TRANSPORT_MARKS = [
    pytest.param("requests", marks=pytest.mark.skipif(not _requests_installed(), reason="requests not installed")),
    pytest.param("httpx", marks=pytest.mark.skipif(not _httpx_installed(), reason="httpx not installed")),
]


class TestOptionalTransports:
    """Shared tests for requests and httpx transports (parametrized)."""

    @pytest.mark.parametrize("http_client", _TRANSPORT_MARKS)
    def test_get_returns_body(self, httpserver: HTTPServer, http_client: str) -> None:
        """GET returns correct body."""
        httpserver.expect_request("/tp/data.txt", method="GET").respond_with_data(
            b"transport-body", content_type="text/plain"
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/tp/"), http_client=http_client)
        assert b.read_bytes("data.txt") == b"transport-body"
        b.close()

    @pytest.mark.parametrize("http_client", _TRANSPORT_MARKS)
    def test_head_succeeds(self, httpserver: HTTPServer, http_client: str) -> None:
        """HEAD returns valid FileInfo."""
        httpserver.expect_request("/tp/info.txt", method="HEAD").respond_with_data(
            b"", status=200, headers={"ETag": '"tp-etag"'}
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/tp/"), http_client=http_client)
        fi = b.get_file_info("info.txt")
        assert fi.checksum == '"tp-etag"'
        b.close()

    @pytest.mark.parametrize("http_client", _TRANSPORT_MARKS)
    def test_connection_error_get(self, http_client: str) -> None:
        """Connection error on GET raises BackendUnavailable."""
        b = ReadOnlyHttpBackend(base_url="http://127.0.0.1:1/", http_client=http_client, timeout=0.1)
        with pytest.raises(BackendUnavailable):
            b.read_bytes("file.txt")
        b.close()

    @pytest.mark.parametrize("http_client", _TRANSPORT_MARKS)
    def test_connection_error_head(self, http_client: str) -> None:
        """Connection error on HEAD raises BackendUnavailable."""
        b = ReadOnlyHttpBackend(base_url="http://127.0.0.1:1/", http_client=http_client, timeout=0.1)
        with pytest.raises(BackendUnavailable):
            b.exists("file.txt")
        b.close()


_httpx_available = pytest.mark.skipif(
    not _httpx_installed(),
    reason="httpx not installed",
)


@_httpx_available
class TestHttpxStreaming:
    """httpx-specific streaming tests."""

    def test_streaming_read(self, httpserver: HTTPServer) -> None:
        """GET via httpx transport streams data (not buffered in memory)."""
        payload = b"X" * 10_000
        httpserver.expect_request("/hx/stream.bin", method="GET").respond_with_data(
            payload, content_type="application/octet-stream"
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/hx/"), http_client="httpx")
        stream = b.read("stream.bin")
        chunks = []
        while True:
            chunk = stream.read(256)
            if not chunk:
                break
            chunks.append(chunk)
        assert b"".join(chunks) == payload
        stream.close()
        b.close()

    def test_stream_adapter_readinto(self, httpserver: HTTPServer) -> None:
        """_HttpxStreamAdapter.readinto() works correctly."""
        httpserver.expect_request("/hx/ri.txt", method="GET").respond_with_data(
            b"readinto-test", content_type="text/plain"
        )
        b = ReadOnlyHttpBackend(base_url=httpserver.url_for("/hx/"), http_client="httpx")
        stream = b.read("ri.txt")
        buf = bytearray(5)
        n = stream.readinto(buf)
        assert n == 5
        assert buf == b"readi"
        stream.close()
        b.close()
