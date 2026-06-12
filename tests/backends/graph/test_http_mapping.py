"""Graph error-mapping table and credential masking (GR-028..034/045/054, GR-035).

Pure-function tests over ``classify_graph_error`` / ``error_code`` /
``mask_headers`` — no HTTP, no event loop. The request-path behaviour that
exercises these (graph_send, iter_pages) lives in ``aio/test_http.py``.
"""

from __future__ import annotations

import pytest

from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
    ResourceLocked,
)
from remote_store.aio.backends._graph.http import classify_graph_error, error_code, mask_headers


class TestClassifyGraphError:
    """The single status+error.code mapping table (GR-028)."""

    @pytest.mark.spec("GR-029")
    def test_401_maps_to_permission_denied(self) -> None:
        exc = classify_graph_error(401, "InvalidAuthenticationToken", path="a.txt")
        assert isinstance(exc, PermissionDenied)
        assert exc.backend == "graph"
        assert exc.path == "a.txt"

    @pytest.mark.spec("GR-030")
    def test_403_access_denied(self) -> None:
        assert isinstance(classify_graph_error(403, "accessDenied"), PermissionDenied)

    @pytest.mark.spec("GR-031")
    def test_404_item_scope_is_not_found(self) -> None:
        exc = classify_graph_error(404, "itemNotFound", path="missing", scope="item")
        assert isinstance(exc, NotFound)

    @pytest.mark.spec("GR-031")
    def test_404_drive_scope_is_backend_unavailable(self) -> None:
        exc = classify_graph_error(404, "itemNotFound", scope="drive")
        assert isinstance(exc, BackendUnavailable)

    @pytest.mark.spec("GR-031")
    def test_404_resource_not_found_is_backend_unavailable(self) -> None:
        # resourceNotFound at item scope still escalates to a drive-identity
        # failure for error-raising operations (read/write/delete/move/copy).
        exc = classify_graph_error(404, "resourceNotFound", scope="item")
        assert isinstance(exc, BackendUnavailable)

    @pytest.mark.spec("GR-031")
    @pytest.mark.parametrize("code", ["itemNotFound", "resourceNotFound", None])
    def test_404_probe_scope_is_not_found(self, code: str | None) -> None:
        # Probe scope (exists/is_file/is_folder) treats ANY 404 as missing — the
        # drive-identity escalation must not escape the probes (BE-004/BE-005).
        exc = classify_graph_error(404, code, path="maybe", scope="probe")
        assert isinstance(exc, NotFound)

    @pytest.mark.spec("GR-032")
    def test_409_already_exists(self) -> None:
        assert isinstance(classify_graph_error(409, "nameAlreadyExists"), AlreadyExists)

    @pytest.mark.spec("GR-045")
    def test_423_resource_locked(self) -> None:
        exc = classify_graph_error(423, "resourceLocked", path="locked.docx")
        assert isinstance(exc, ResourceLocked)
        assert exc.backend == "graph"

    @pytest.mark.spec("GR-034")
    def test_429_throttled_is_backend_unavailable(self) -> None:
        assert isinstance(classify_graph_error(429, "activityLimitReached"), BackendUnavailable)

    @pytest.mark.spec("GR-054")
    def test_507_insufficient_storage(self) -> None:
        assert isinstance(classify_graph_error(507, None), BackendUnavailable)

    @pytest.mark.spec("GR-054")
    def test_quota_limit_reached_any_status(self) -> None:
        # quotaLimitReached maps regardless of the carrying status (GR-054).
        assert isinstance(classify_graph_error(400, "quotaLimitReached"), BackendUnavailable)

    @pytest.mark.spec("GR-033")
    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_backend_unavailable(self, status: int) -> None:
        assert isinstance(classify_graph_error(status, None), BackendUnavailable)

    @pytest.mark.spec("GR-028")
    def test_unclassified_status_is_generic_error(self) -> None:
        exc = classify_graph_error(418, "imATeapot")
        assert type(exc) is RemoteStoreError
        assert exc.backend == "graph"


class TestErrorCode:
    """Structured ``error.code`` extraction (GR-028, no message matching)."""

    @pytest.mark.spec("GR-028")
    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            ({"error": {"code": "itemNotFound", "message": "no"}}, "itemNotFound"),
            ({"error": {"message": "no code here"}}, None),
            ({"error": {"code": 404}}, None),  # non-str code
            ({"value": []}, None),  # not an error envelope
            ("plain string body", None),
            (None, None),
        ],
    )
    def test_extract(self, body: object, expected: str | None) -> None:
        assert error_code(body) == expected


class TestMaskHeaders:
    """GR-035: the bearer token is redacted before any record is formatted."""

    @pytest.mark.spec("GR-035")
    def test_authorization_redacted(self) -> None:
        masked = mask_headers({"Authorization": "Bearer super-secret", "Accept": "application/json"})
        assert masked["Authorization"] == "***"
        assert masked["Accept"] == "application/json"

    @pytest.mark.spec("GR-035")
    def test_redaction_is_case_insensitive(self) -> None:
        assert mask_headers({"authorization": "Bearer t"})["authorization"] == "***"

    @pytest.mark.spec("GR-035")
    def test_token_never_survives(self) -> None:
        assert "super-secret" not in str(mask_headers({"Authorization": "Bearer super-secret"}))
