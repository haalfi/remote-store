"""Tests for the Microsoft Graph cassette scrub profile (ID-127 / GR-FOUNDATION).

The **security gate** for the cassette spine: a cassette recorded from a
live Graph run must never carry the bearer token or the pre-signed
``@microsoft.graph.downloadUrl`` token (GR-035 / TEST-007). These tests
feed a request and response carrying fake secrets through the scrub hooks
and assert that nothing sensitive survives — the assertion that makes it
safe to record against a real tenant.
"""

from __future__ import annotations

import json
import types
from typing import Any

import pytest

from tests.backends.fixtures._cassettes import (
    CASSETTE_DIR_GRAPH,
    FAKE_DRIVE_ID,
    GRAPH_PRESIGNED_PLACEHOLDER,
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

    def test_client_secret_redacted_from_request_body(self) -> None:
        """The client-credentials token POST body must not leak the secret (PR #750 review)."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        req = _request({"Content-Type": "application/x-www-form-urlencoded"})
        req.body = b"grant_type=client_credentials&client_id=app&client_secret=SUPERSECRET&scope=.default"
        out = cfg["before_record_request"](req)
        assert b"SUPERSECRET" not in out.body
        assert b"client_secret=REDACTED" in out.body
        # Non-secret form fields survive so the cassette still matches on replay.
        assert b"grant_type=client_credentials" in out.body
        assert b"client_id=app" in out.body

    def test_certificate_and_refresh_credentials_redacted_from_str_body(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        req = _request({})
        req.body = "client_assertion=JWTSECRET&assertion=CERTJWT&refresh_token=RT123&grant_type=refresh_token"
        out = cfg["before_record_request"](req)
        assert isinstance(out.body, str)  # str in -> str out
        for secret in ("JWTSECRET", "CERTJWT", "RT123"):
            assert secret not in out.body
        assert "grant_type=refresh_token" in out.body

    def test_binary_request_body_left_intact(self) -> None:
        """A non-form (binary upload) body has no credential keys, so it is untouched."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        req = _request({})
        req.body = bytes(range(256))
        out = cfg["before_record_request"](req)
        assert out.body == bytes(range(256))

    def test_downloadurl_redacted_from_body(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = (
            b'{"id":"01ABC","name":"f.txt",'
            b'"@microsoft.graph.downloadUrl":"https://host/path?tempauth=SECRETSIG123&e=2026-01-01"}'
        )
        resp: dict[str, Any] = {"headers": {"Content-Type": ["application/json"]}, "body": {"string": body}}
        scrubbed = cfg["before_record_response"](resp)["body"]["string"]
        assert b"SECRETSIG123" not in scrubbed
        # The value is replaced with the valid placeholder URL (not a bare token),
        # so the backend reads back a real URL it can re-request on replay (BK-262).
        assert GRAPH_PRESIGNED_PLACEHOLDER.encode() in scrubbed
        # Structure preserved: the key stays, only its value is redacted.
        assert b"@microsoft.graph.downloadUrl" in scrubbed
        assert b'"name":"f.txt"' in scrubbed

    def test_uploadurl_redacted_from_body(self) -> None:
        # createUploadSession returns a pre-authorised uploadUrl whose query
        # carries its own token — the same leak threat as downloadUrl (GR-019).
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = (
            b'{"uploadUrl":"https://up.example.com/session/abc?tempauth=UPLOADSECRET999",'
            b'"expirationDateTime":"2026-01-01T00:00:00Z","nextExpectedRanges":["0-"]}'
        )
        resp: dict[str, Any] = {"headers": {"Content-Type": ["application/json"]}, "body": {"string": body}}
        scrubbed = cfg["before_record_response"](resp)["body"]["string"]
        assert b"UPLOADSECRET999" not in scrubbed
        # Replaced with the placeholder URL (not a bare token) so chunk PUTs on
        # replay target a valid, recorded-and-matchable host (BK-262).
        assert GRAPH_PRESIGNED_PLACEHOLDER.encode() in scrubbed
        # Structure preserved: the key and the non-secret fields stay.
        assert b'"uploadUrl"' in scrubbed
        assert b'"nextExpectedRanges":["0-"]' in scrubbed

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

    def test_download_token_redacted_from_302_location_header(self) -> None:
        """GR-015: GET /content -> 302 whose Location is the pre-signed downloadUrl.

        The Location points at a pre-signed content host, so it collapses to the
        placeholder — removing the query token AND the drive id Graph embeds in
        the path (BK-262). Replay-safe: the download request the backend issues
        from this header normalises to the same placeholder (PR #750 review — the
        primary leak path the streaming proof de-risks).
        """
        cfg = build_graph_vcr_config(real_drive_id=None)
        loc = (
            "https://abc.microsoftpersonalcontent.com/personal/x/Documents/f.bin"
            "?tempauth=TEMPAUTHSECRET&Expires=1700000000&access_token=ACCESSTOKENSECRET"
        )
        resp: dict[str, Any] = {"headers": {"Location": [loc], "Content-Type": ["text/html"]}, "body": {"string": b""}}
        scrubbed = cfg["before_record_response"](resp)["headers"]["Location"][0]
        assert "TEMPAUTHSECRET" not in scrubbed
        assert "ACCESSTOKENSECRET" not in scrubbed
        assert scrubbed == GRAPH_PRESIGNED_PLACEHOLDER

    def test_presigned_location_drops_drive_id_in_path(self) -> None:
        """BK-262 regression: the async copy/move monitor Location at a pre-signed
        host carries the drive id (the cid AND the long ``b!…`` form) in its PATH,
        which the old query-only wipe left intact. The pre-signed-host collapse
        removes both."""
        cfg = build_graph_vcr_config(real_drive_id="4fde4d5aac63bdf1")
        loc = (
            "https://my.microsoftpersonalcontent.com/personal/4FDE4D5AAC63BDF1"
            "/_api/v2.0/drives/b!3XW1UgCSb0aoUxhAGtlXy8vVrIsFxBxJm9hrzwaK5lr1q/operations/copy"
        )
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        scrubbed = cfg["before_record_response"](resp)["headers"]["Location"]
        assert scrubbed == GRAPH_PRESIGNED_PLACEHOLDER
        assert "4FDE4D5AAC63BDF1" not in scrubbed
        assert "b!3XW1Ug" not in scrubbed

    def test_api_host_location_preserved_and_id_normalised(self) -> None:
        """A Graph-API-host Location (a 201 Created item URL the backend never
        re-requests) keeps host + path for review; only the token query is wiped
        and the drive id in the path is id-normalised."""
        cfg = build_graph_vcr_config(real_drive_id="realdrive123")
        loc = "https://graph.microsoft.com/v1.0/drives/realdrive123/items/01ABC?novel_token=SECRET"
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        scrubbed = cfg["before_record_response"](resp)["headers"]["Location"]
        assert "SECRET" not in scrubbed  # value-based query wipe
        assert "realdrive123" not in scrubbed  # drive id id-normalised
        assert scrubbed == f"https://graph.microsoft.com/v1.0/drives/{FAKE_DRIVE_ID}/items/01ABC?REDACTED"

    def test_api_host_location_without_query_is_unchanged(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        loc = "https://graph.microsoft.com/v1.0/drives/d/items/01ABC"
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        assert cfg["before_record_response"](resp)["headers"]["Location"] == loc

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

    def test_drive_id_rewrite_is_case_insensitive(self) -> None:
        """BK-262: Graph echoes the drive id (cid) UPPER-cased inside item ids,
        eTags, and webUrls but lower-cased in URIs. A case-sensitive replace of
        the lower-cased env value leaked the upper-cased copies; the rewrite is
        case-insensitive and maps every casing to the same ``FAKE_DRIVE_ID`` so
        id/eTag self-comparisons within a cassette still match."""
        cfg = build_graph_vcr_config(real_drive_id="4fde4d5aac63bdf1")
        body = (
            b'{"id":"4FDE4D5AAC63BDF1!s0123abcd",'
            b'"eTag":"\\"4FDE4D5AAC63BDF1!112.0\\"",'
            b'"name":"f.txt",'
            b'"webUrl":"https://onedrive.live.com?cid=4fde4d5aac63bdf1&id=4FDE4D5AAC63BDF1!112"}'
        )
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        # No casing of the real cid survives, in either the lower- or upper-cased form.
        assert b"4FDE4D5AAC63BDF1" not in scrubbed
        assert b"4fde4d5aac63bdf1" not in scrubbed
        # Every occurrence maps to the same fake id, so the eTag/id/webUrl agree.
        assert scrubbed.count(FAKE_DRIVE_ID.encode()) == 4
        # The load-bearing item name is untouched.
        assert b'"name":"f.txt"' in scrubbed

    def test_identity_and_site_pii_redacted_from_body(self) -> None:
        """BK-262: the createdBy / lastModifiedBy user objects (email, displayName,
        userPrincipalName, loginName) and the siteId Graph embeds in item responses
        are blanked; none are read by the backend or asserted by conformance. The
        load-bearing ``name`` field — which IS read — must survive intact."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        body = (
            b'{"name":"keep.txt","siteId":"site-guid-1234",'
            b'"createdBy":{"user":{"email":"real@example.com",'
            b'"displayName":"Real Name","userPrincipalName":"real@tenant.onmicrosoft.com"}},'
            b'"lastModifiedBy":{"user":{"loginName":"i:0#.f|membership|real@example.com"}}}'
        )
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        for leaked in (b"real@example.com", b"Real Name", b"real@tenant.onmicrosoft.com", b"site-guid-1234"):
            assert leaked not in scrubbed
        # The item name is NOT redacted (it shares no key with displayName).
        assert b'"name":"keep.txt"' in scrubbed
        assert b'"email":"REDACTED"' in scrubbed
        assert b'"displayName":"REDACTED"' in scrubbed
        assert b'"siteId":"REDACTED"' in scrubbed

    def test_presigned_host_request_uri_rewritten_to_placeholder(self) -> None:
        """BK-262: a request to a pre-signed content host (downloadUrl / uploadUrl /
        copy-move monitor URL) has its whole URI replaced with the placeholder, so
        the recorded request matches what the backend re-issues on replay."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        out = cfg["before_record_request"](
            _request({}, uri="https://abc.microsoftpersonalcontent.com/personal/x/f.bin?tempauth=SECRET")
        )
        assert out.uri == GRAPH_PRESIGNED_PLACEHOLDER

    def test_graph_api_host_request_uri_preserved(self) -> None:
        """An API-host request (graph.microsoft.com) is id-normalised, not blanked:
        the placeholder rewrite is reserved for pre-signed content hosts."""
        cfg = build_graph_vcr_config(real_drive_id=None)
        uri = "https://graph.microsoft.com/v1.0/drives/d/root:/a.txt:/content"
        assert cfg["before_record_request"](_request({}, uri=uri)).uri == uri

    def test_downloadurl_body_value_replays_against_recorded_request(self) -> None:
        """End-to-end BK-262 proof: the scrubbed downloadUrl the backend reads from
        a response body, fed back as the URI of the GET it then issues, normalises
        to the same placeholder the recorded live GET was rewritten to — so vcrpy
        matches them. The bare ``"REDACTED"`` token it replaced did not (it is not
        a URL), which is exactly why Graph reads could not replay."""
        cfg = build_graph_vcr_config(real_drive_id="realdrive123")
        # Record side: scrub the metadata body carrying the live downloadUrl.
        body = b'{"@microsoft.graph.downloadUrl":"https://live-cdn.example/path?tempauth=SECRET"}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        # The backend reads that value back out of the body on replay...
        download_url = json.loads(scrubbed)["@microsoft.graph.downloadUrl"]
        assert download_url == GRAPH_PRESIGNED_PLACEHOLDER
        # ...and issues a GET to it; before_record_request normalises that request
        # the same way it normalised the recorded live GET → identical URIs match.
        replay_uri = cfg["before_record_request"](_request({}, uri=download_url)).uri
        recorded_uri = cfg["before_record_request"](
            _request({}, uri="https://live-cdn.example/path?tempauth=SECRET")
        ).uri
        assert replay_uri == recorded_uri == GRAPH_PRESIGNED_PLACEHOLDER

    def test_query_params_filtered(self) -> None:
        cfg = build_graph_vcr_config(real_drive_id=None)
        for param in ("tempauth", "Expires", "access_token", "sig"):
            assert param in cfg["filter_query_parameters"]

    def test_cassette_dir_is_per_backend_graph(self) -> None:
        assert CASSETTE_DIR_GRAPH.name == "graph"
        assert CASSETTE_DIR_GRAPH.parent.name == "cassettes"
