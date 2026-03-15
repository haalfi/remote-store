"""Backend-specific tests for ReadOnlyHttpBackend."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from remote_store._errors import BackendUnavailable, CapabilityNotSupported, NotFound, PermissionDenied
from remote_store._models import FileInfo
from remote_store.backends._http import ReadOnlyHttpBackend, UrllibTransport

if TYPE_CHECKING:
    from werkzeug.wrappers import Request, Response

    from pytest_httpserver import HTTPServer


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
        import time

        def slow_handler(request: Request) -> Response:
            from werkzeug.wrappers import Response

            time.sleep(5)
            return Response(b"slow", status=200)

        httpserver.expect_request("/slow/data.txt").respond_with_handler(slow_handler)
        b = ReadOnlyHttpBackend(
            base_url=httpserver.url_for("/slow/"),
            timeout=0.1,
            http_client="urllib",
        )
        with pytest.raises(BackendUnavailable):
            b.read_bytes("data.txt")


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
