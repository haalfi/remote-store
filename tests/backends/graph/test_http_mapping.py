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
from remote_store.aio.backends._graph.http import GraphScope, classify_graph_error, error_code, mask_headers


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

    # The 404 space is two axes — four scopes by three error codes — so it is
    # enumerated rather than sampled, and each cell's expected value is written
    # out as data. Re-deriving it from the same predicate the implementation
    # uses would assert only that the classifier agrees with a copy of itself,
    # and a misreading shared by both copies is exactly what an adjudication
    # test exists to catch. Values transcribed from ADR-0038 § Decision; the row
    # order is the classifier's own, so do not read it as a claim about that
    # file's ordering.
    @pytest.mark.spec("BE-004", "BE-005", "BE-021", "GR-031")
    @pytest.mark.parametrize(
        ("scope", "code", "expected"),
        [
            # item — the path-addressed data plane: absence, whatever the code.
            ("item", "itemNotFound", NotFound),
            ("item", "resourceNotFound", NotFound),
            ("item", None, NotFound),
            # probe — never raises past the caller; same answer, own obligation.
            ("probe", "itemNotFound", NotFound),
            ("probe", "resourceNotFound", NotFound),
            ("probe", None, NotFound),
            # identity — write, check_health, drive-id resolution, the monitor
            # poller: the drive-identity code escalates and nothing else does.
            ("identity", "itemNotFound", NotFound),
            ("identity", "resourceNotFound", BackendUnavailable),
            ("identity", None, NotFound),
            # drive — the bare /drives/{id} resource: no path, so no absence.
            ("drive", "itemNotFound", BackendUnavailable),
            ("drive", "resourceNotFound", BackendUnavailable),
            ("drive", None, BackendUnavailable),
        ],
        ids=lambda v: v.__name__ if isinstance(v, type) else str(v),
    )
    def test_404_maps_by_scope_and_code(
        self, scope: GraphScope, code: str | None, expected: type[RemoteStoreError]
    ) -> None:
        exc = classify_graph_error(404, code, path="subject", scope=scope)
        assert isinstance(exc, expected), f"404 {code} at {scope} scope must map to {expected.__name__}"
        assert exc.backend == "graph"

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
