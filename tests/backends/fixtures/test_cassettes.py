"""Tests for the Microsoft Graph cassette scrub profile (ID-127 / GR-FOUNDATION).

The **security gate** for the cassette spine: a cassette recorded from a
live Graph run must never carry the bearer token or the pre-signed
``@microsoft.graph.downloadUrl`` token (GR-035 / TEST-007). These tests
feed a request and response carrying fake secrets through the scrub hooks
and assert that nothing sensitive survives — the assertion that makes it
safe to record against a real tenant.
"""

from __future__ import annotations

import types
from typing import Any

import pytest

from tests.backends.fixtures._cassettes import (
    CASSETTE_DIR_GRAPH,
    FAKE_DRIVE_ID,
    build_graph_vcr_config,
)

_FAKE_BEARER = "eyJ0eXAiOiThisLooksLikeAJwt.payload-segment.signature-segment"


def _request(headers: dict[str, str], uri: str = "https://graph.microsoft.com/v1.0/me/drive") -> Any:
    """Minimal stand-in for vcrpy's request object (``.headers`` / ``.uri``)."""
    return types.SimpleNamespace(headers=dict(headers), uri=uri)


@pytest.mark.spec("TEST-007")
class TestGraphCassetteScrub:
    """The bearer token and download-URL token must not survive scrubbing."""

    def test_bearer_token_dropped_from_request(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        req = _request({"Authorization": f"Bearer {_FAKE_BEARER}", "Accept": "application/json"})
        out = cfg["before_record_request"](req)
        blob = " ".join(out.headers) + " " + " ".join(out.headers.values())
        assert "Authorization" not in out.headers
        assert "Bearer" not in blob
        assert _FAKE_BEARER not in blob
        # Non-sensitive headers are retained.
        assert out.headers["Accept"] == "application/json"

    def test_correlation_request_header_dropped(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        out = cfg["before_record_request"](_request({"client-request-id": "abc-123"}))
        assert "client-request-id" not in {k.lower() for k in out.headers}

    def test_downloadurl_redacted_from_body(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = (
            b'{"id":"01ABC","name":"f.txt",'
            b'"@microsoft.graph.downloadUrl":"https://host/path?tempauth=SECRETSIG123&e=2026-01-01"}'
        )
        resp: dict[str, Any] = {"headers": {"Content-Type": ["application/json"]}, "body": {"string": body}}
        scrubbed = cfg["before_record_response"](resp)["body"]["string"]
        assert b"SECRETSIG123" not in scrubbed
        assert b"REDACTED" in scrubbed
        # Structure preserved: the key stays, only its value is redacted.
        assert b"@microsoft.graph.downloadUrl" in scrubbed
        assert b'"name":"f.txt"' in scrubbed

    def test_oauth_tokens_redacted_from_body(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = b'{"access_token":"AAAsecretAAA","refresh_token":"RRRsecretRRR","expires_in":3600}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert b"AAAsecretAAA" not in scrubbed
        assert b"RRRsecretRRR" not in scrubbed
        assert b'"expires_in":3600' in scrubbed

    def test_string_body_round_trips_as_str(self) -> None:
        """A ``str`` body is scrubbed and returned as ``str`` (not bytes)."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = '{"@microsoft.graph.downloadUrl":"https://host?tempauth=SECRET"}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert isinstance(scrubbed, str)
        assert "SECRET" not in scrubbed

    def test_response_correlation_headers_dropped(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        resp: dict[str, Any] = {
            "headers": {"request-id": ["r1"], "x-ms-ags-diagnostic": ["d1"], "Content-Type": ["application/json"]},
            "body": {"string": b"{}"},
        }
        remaining = {k.lower() for k in cfg["before_record_response"](resp)["headers"]}
        assert "request-id" not in remaining
        assert "x-ms-ags-diagnostic" not in remaining
        assert "content-type" in remaining

    def test_drive_id_rewritten_in_uri_and_body(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id="realdrive123")
        out = cfg["before_record_request"](
            _request({}, uri="https://graph.microsoft.com/v1.0/drives/realdrive123/root:/a.txt:")
        )
        assert "realdrive123" not in out.uri
        assert FAKE_DRIVE_ID in out.uri
        scrubbed = cfg["before_record_response"](
            {"body": {"string": b'{"parentReference":{"driveId":"realdrive123"}}'}}
        )
        assert b"realdrive123" not in scrubbed["body"]["string"]
        assert FAKE_DRIVE_ID.encode() in scrubbed["body"]["string"]

    def test_query_params_filtered(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        for param in ("tempauth", "Expires", "access_token", "sig"):
            assert param in cfg["filter_query_parameters"]

    def test_cassette_dir_is_per_backend_graph(self) -> None:
        assert CASSETTE_DIR_GRAPH.name == "graph"
        assert CASSETTE_DIR_GRAPH.parent.name == "cassettes"
