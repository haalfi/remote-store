"""Tests for the cassette scrub core and the per-backend profiles (spec 049).

The **security gate** for the cassette spine: a cassette recorded from a
live run must never carry the bearer token, the pre-signed
``@microsoft.graph.downloadUrl`` token, or the live Azure account name
(GR-035 / TEST-007). These tests feed requests and responses carrying fake
secrets through the scrub pipeline and assert that nothing sensitive
survives — the assertion that makes it safe to record against a real
tenant / account.

Request-side tests run the **composed** filter chain exactly as vcrpy
builds it (``_composed_request_filter``): the request-header deletes and
the User-Agent rewrite ride vcrpy's native ``filter_headers`` (REC-005),
so calling the custom hook alone would assert a weaker gate than a real
recording run applies.
"""

from __future__ import annotations

import json
import re
import types
from typing import Any
from urllib.parse import urlsplit

import pytest
import vcr
from vcr.request import Request as VcrRequest

import tests.backends.fixtures._cassettes as _cassettes_core
from tests.backends.fixtures import all_fixtures
from tests.backends.fixtures._cassettes import (
    FORBIDDEN_ENVELOPE,
    CassetteProfile,
    build_profile_vcr_config,
    dump_scrub_manifest,
    reset_scrub_fire_counts,
    scrub_fire_counts,
)
from tests.backends.fixtures._cassettes_azure import (
    AZURE_PROFILE,
    FAKE_ACCOUNT,
    FAKE_FILESYSTEM,
    LIVE_HNS_ROOT_FS,
    _resolve_live_account,
    _resolve_live_hns_container,
)
from tests.backends.fixtures._cassettes_graph import (
    FAKE_DRIVE_ID,
    GRAPH_PRESIGNED_PLACEHOLDER,
    GRAPH_PROFILE,
    _drive_id_forms,
)

_FAKE_BEARER = "eyJ0eXAiOiThisLooksLikeAJwt.payload-segment.signature-segment"


def _request(
    headers: dict[str, str],
    uri: str = "https://graph.microsoft.com/v1.0/me/drive",
    method: str = "GET",
    body: Any = None,
) -> VcrRequest:
    """A real vcrpy request object, as the recording/replay pipeline sees it.

    Note vcrpy's ``Request.body`` setter encodes ``str`` bodies to bytes on
    assignment, so request bodies below are always asserted as bytes — the
    ``str`` branch of the custom hook's body dispatch is defensive and is
    unit-tested directly against the hook with a ``SimpleNamespace``.
    """
    return VcrRequest(method=method, uri=uri, body=body, headers=dict(headers))


def _composed_request_filter(cfg: dict[str, Any]) -> Any:
    """The full request-side filter chain as vcrpy composes it.

    vcrpy applies the native filters (``filter_headers``,
    ``filter_query_parameters``, ``filter_post_data_parameters``) BEFORE the
    custom ``before_record_request`` hook — in record and replay mode alike.
    Building the chain through ``vcr.VCR._build_before_record_request``
    (private API, deliberately) means these tests assert exactly what a
    recording run does; a vcrpy upgrade that changes filter composition
    fails here, not in a leaked cassette.
    """
    return vcr.VCR(**cfg)._build_before_record_request({})


def _graph_cfg(real_drive_id: str | None = None) -> dict[str, Any]:
    """The Graph profile's config; a non-None id stands in for record mode."""
    return build_profile_vcr_config(GRAPH_PROFILE, {"graph.drive-id": real_drive_id})


def _azure_cfg(real_account: str | None = None) -> dict[str, Any]:
    """The Azure profile's config; a non-None account stands in for record mode."""
    return build_profile_vcr_config(AZURE_PROFILE, {"azure.account": real_account})


def _registered_profiles() -> list[CassetteProfile]:
    """Every distinct cassette profile carried by a registered fixture."""
    seen: dict[int, CassetteProfile] = {}
    for fixture in all_fixtures():
        if fixture.cassette_profile is not None:
            seen[id(fixture.cassette_profile)] = fixture.cassette_profile
    return sorted(seen.values(), key=lambda p: p.backend)


@pytest.mark.spec("TEST-007")
class TestGraphCassetteScrub:
    """The bearer token and download-URL token must not survive scrubbing."""

    def test_bearer_token_dropped_from_request(self) -> None:
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({"Authorization": f"Bearer {_FAKE_BEARER}", "Accept": "application/json"}))
        blob = " ".join(out.headers) + " " + " ".join(out.headers.values())
        assert "Authorization" not in out.headers
        assert "Bearer" not in blob
        assert _FAKE_BEARER not in blob
        # Non-sensitive headers are retained.
        assert out.headers["Accept"] == "application/json"

    def test_correlation_request_header_dropped(self) -> None:
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({"client-request-id": "abc-123", "Cookie": "session=1"}))
        survivors = {k.lower() for k in out.headers}
        assert "client-request-id" not in survivors
        assert "cookie" not in survivors

    def test_anchor_mailbox_header_dropped(self) -> None:
        """The MSAL token POST carries ``X-AnchorMailbox: Oid:<guid>@<tenant>``
        whose GUID embeds the drive cid hyphen-split — the backend never reads
        it on replay, so the whole header is deleted natively."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({"X-AnchorMailbox": "Oid:00000000-0000-0000-dead-beefcafe0123@72f988bf"}))
        assert "x-anchormailbox" not in {k.lower() for k in out.headers}

    def test_user_agent_normalised(self) -> None:
        """The native ``("User-Agent", ...)`` tuple rewrites the value in place,
        preserving the capitalised key every committed cassette records."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({"User-Agent": "python-httpx/0.27.0 CPython/3.11 Linux/6.1"}))
        assert out.headers["User-Agent"] == "azsdk-python-replay"
        assert "User-Agent" in list(out.headers.keys())  # exact key case kept

    @pytest.mark.spec("REC-005")
    def test_user_agent_absent_stays_absent(self) -> None:
        """The ``("User-Agent", ...)`` tuple *rewrites* an existing header but must
        never *add* one when absent — vcrpy 8.1.1 ``filters.replace_headers`` guards
        the rewrite with ``if k in new_headers:``. Byte-identity of re-records
        depends on it: a request that carried no User-Agent must record none."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({"Accept": "application/json"}))  # no User-Agent in
        assert "user-agent" not in {k.lower() for k in out.headers}

    @pytest.mark.spec("REC-005")
    def test_native_filters_run_before_custom_hook(self) -> None:
        """Pin vcrpy's composition order (``VCR._build_before_record_request``):
        the native header filter runs first, then the custom hook — so a single
        pre-signed request gets BOTH the Authorization delete (native) and the
        URI/Host placeholder collapse (custom)."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(
            _request(
                {"Authorization": f"Bearer {_FAKE_BEARER}", "Host": "tenant-my.sharepoint.com"},
                uri="https://tenant-my.sharepoint.com/personal/x/f.bin?tempauth=SECRET",
            )
        )
        assert "Authorization" not in out.headers  # native half applied
        assert out.uri == GRAPH_PRESIGNED_PLACEHOLDER  # custom half applied

    def test_client_secret_redacted_from_request_body(self) -> None:
        """The client-credentials token POST body must not leak the secret."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(
            _request(
                {"Content-Type": "application/x-www-form-urlencoded"},
                uri="https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
                method="POST",
                body=b"grant_type=client_credentials&client_id=app&client_secret=SUPERSECRET&scope=.default",
            )
        )
        assert b"SUPERSECRET" not in out.body
        assert b"client_secret=REDACTED" in out.body
        # Non-secret form fields survive so the cassette still matches on replay.
        assert b"grant_type=client_credentials" in out.body
        assert b"client_id=app" in out.body

    def test_certificate_and_refresh_credentials_redacted_from_str_body(self) -> None:
        """Direct unit test of the custom hook's ``str`` body dispatch.

        Real vcrpy requests never carry ``str`` bodies (``Request.body``
        encodes on assignment), so this defensive branch is exercised against
        the bare hook with a stand-in object.
        """
        cfg = _graph_cfg()
        req = types.SimpleNamespace(headers={}, uri="https://login.microsoftonline.com/tenant/token")
        req.body = "client_assertion=JWTSECRET&assertion=CERTJWT&refresh_token=RT123&grant_type=refresh_token"
        out = cfg["before_record_request"](req)
        assert isinstance(out.body, str)  # str in -> str out
        for secret in ("JWTSECRET", "CERTJWT", "RT123"):
            assert secret not in out.body
        assert "grant_type=refresh_token" in out.body

    def test_binary_request_body_left_intact(self) -> None:
        """A non-form (binary upload chunk) body has no credential keys, so it is untouched."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(
            _request(
                {},
                uri="https://graph.microsoft.com/v1.0/drives/d/root:/a.bin:/content",
                method="PUT",
                body=bytes(range(256)),
            )
        )
        assert out.body == bytes(range(256))

    def test_downloadurl_redacted_from_body(self) -> None:
        cfg = _graph_cfg()
        body = (
            b'{"id":"01ABC","name":"f.txt",'
            b'"@microsoft.graph.downloadUrl":"https://host/path?tempauth=SECRETSIG123&e=2026-01-01"}'
        )
        resp: dict[str, Any] = {"headers": {"Content-Type": ["application/json"]}, "body": {"string": body}}
        scrubbed = cfg["before_record_response"](resp)["body"]["string"]
        assert b"SECRETSIG123" not in scrubbed
        # The value is replaced with the valid placeholder URL (not a bare token),
        # so the backend reads back a real URL it can re-request on replay (REC-004).
        assert GRAPH_PRESIGNED_PLACEHOLDER.encode() in scrubbed
        # Structure preserved: the key stays, only its value is redacted.
        assert b"@microsoft.graph.downloadUrl" in scrubbed
        assert b'"name":"f.txt"' in scrubbed

    def test_uploadurl_redacted_from_body(self) -> None:
        # createUploadSession returns a pre-authorised uploadUrl whose query
        # carries its own token — the same leak threat as downloadUrl (GR-019).
        cfg = _graph_cfg()
        body = (
            b'{"uploadUrl":"https://up.example.com/session/abc?tempauth=UPLOADSECRET999",'
            b'"expirationDateTime":"2026-01-01T00:00:00Z","nextExpectedRanges":["0-"]}'
        )
        resp: dict[str, Any] = {"headers": {"Content-Type": ["application/json"]}, "body": {"string": body}}
        scrubbed = cfg["before_record_response"](resp)["body"]["string"]
        assert b"UPLOADSECRET999" not in scrubbed
        # Replaced with the placeholder URL (not a bare token) so chunk PUTs on
        # replay target a valid, recorded-and-matchable host (REC-004).
        assert GRAPH_PRESIGNED_PLACEHOLDER.encode() in scrubbed
        # Structure preserved: the key and the non-secret fields stay.
        assert b'"uploadUrl"' in scrubbed
        assert b'"nextExpectedRanges":["0-"]' in scrubbed

    def test_oauth_tokens_redacted_from_body(self) -> None:
        cfg = _graph_cfg()
        body = b'{"access_token":"AAAsecretAAA","refresh_token":"RRRsecretRRR","expires_in":3600}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert b"AAAsecretAAA" not in scrubbed
        assert b"RRRsecretRRR" not in scrubbed
        assert b'"expires_in":3600' in scrubbed

    def test_string_body_round_trips_as_str(self) -> None:
        """A ``str`` body is scrubbed and returned as ``str`` (not bytes)."""
        cfg = _graph_cfg()
        body = '{"@microsoft.graph.downloadUrl":"https://host?tempauth=SECRET"}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert isinstance(scrubbed, str)
        assert "SECRET" not in scrubbed

    def test_response_correlation_headers_dropped(self) -> None:
        cfg = _graph_cfg()
        resp: dict[str, Any] = {
            "headers": {"request-id": ["r1"], "x-ms-ags-diagnostic": ["d1"], "Content-Type": ["application/json"]},
            "body": {"string": b"{}"},
        }
        remaining = {k.lower() for k in cfg["before_record_response"](resp)["headers"]}
        assert "request-id" not in remaining
        assert "x-ms-ags-diagnostic" not in remaining
        assert "content-type" in remaining

    def test_docid_header_dropped(self) -> None:
        """The ``docID`` response header on pre-signed-content interactions
        embeds the OneDrive site-collection GUID (the same value ``"siteId"``
        is blanked to in bodies) as ``...content.com_<site-guid>_<doc-guid>``.
        The body regexes never run on headers, so the header is dropped
        wholesale."""
        cfg = _graph_cfg()
        site_guid = "52b575dd-9200-466f-a853-18401ad957cb"
        resp: dict[str, Any] = {
            "headers": {
                "docID": [f"my.microsoftpersonalcontent.com_{site_guid}_6a30444f-3aac-4f4c-a049-deadbeef"],
                "Content-Type": ["application/json"],
            },
            "body": {"string": b"{}"},
        }
        out = cfg["before_record_response"](resp)["headers"]
        assert "docid" not in {k.lower() for k in out}
        assert site_guid not in " ".join(str(v) for v in out.values())

    @pytest.mark.spec("REC-004")
    def test_download_token_redacted_from_302_location_header(self) -> None:
        """GR-015: GET /content -> 302 whose Location is the pre-signed downloadUrl.

        The Location points at a pre-signed content host, so it collapses to the
        placeholder — removing the query token AND the drive id Graph embeds in
        the path. Replay-safe: the download request the backend issues from this
        header normalises to the same placeholder.
        """
        cfg = _graph_cfg()
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
        """The async copy/move monitor Location at a pre-signed host carries the
        drive id (the cid AND the long ``b!…`` form) in its PATH, which a
        query-only wipe would leave intact. The pre-signed-host collapse removes
        both."""
        cfg = _graph_cfg("deadbeefcafe0123")
        loc = (
            "https://my.microsoftpersonalcontent.com/personal/DEADBEEFCAFE0123"
            "/_api/v2.0/drives/b!3XW1UgCSb0aoUxhAGtlXy8vVrIsFxBxJm9hrzwaK5lr1q/operations/copy"
        )
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        scrubbed = cfg["before_record_response"](resp)["headers"]["Location"]
        assert scrubbed == GRAPH_PRESIGNED_PLACEHOLDER
        assert "DEADBEEFCAFE0123" not in scrubbed
        assert "b!3XW1Ug" not in scrubbed

    def test_api_host_location_preserved_and_id_normalised(self) -> None:
        """A Graph-API-host Location (a 201 Created item URL the backend never
        re-requests) keeps host + path for review; only the token query is wiped
        and the drive id in the path is id-normalised."""
        cfg = _graph_cfg("realdrive123")
        loc = "https://graph.microsoft.com/v1.0/drives/realdrive123/items/01ABC?novel_token=SECRET"
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        scrubbed = cfg["before_record_response"](resp)["headers"]["Location"]
        assert "SECRET" not in scrubbed  # value-based query wipe
        assert "realdrive123" not in scrubbed  # drive id id-normalised
        assert scrubbed == f"https://graph.microsoft.com/v1.0/drives/{FAKE_DRIVE_ID}/items/01ABC?REDACTED"

    def test_api_host_location_without_query_is_unchanged(self) -> None:
        cfg = _graph_cfg()
        loc = "https://graph.microsoft.com/v1.0/drives/d/items/01ABC"
        resp: dict[str, Any] = {"headers": {"Location": loc}, "body": {"string": b""}}
        assert cfg["before_record_response"](resp)["headers"]["Location"] == loc

    def test_drive_id_rewritten_in_uri_and_body(self) -> None:
        cfg = _graph_cfg("realdrive123")
        scrub = _composed_request_filter(cfg)
        out = scrub(_request({}, uri="https://graph.microsoft.com/v1.0/drives/realdrive123/root:/a.txt:"))
        assert "realdrive123" not in out.uri
        assert FAKE_DRIVE_ID in out.uri
        scrubbed = cfg["before_record_response"](
            {"body": {"string": b'{"parentReference":{"driveId":"realdrive123"}}'}}
        )
        assert b"realdrive123" not in scrubbed["body"]["string"]
        assert FAKE_DRIVE_ID.encode() in scrubbed["body"]["string"]

    def test_drive_id_rewrite_is_case_insensitive(self) -> None:
        """Graph echoes the drive id (cid) UPPER-cased inside item ids, eTags,
        and webUrls but lower-cased in URIs. A case-sensitive replace of the
        lower-cased env value would leak the upper-cased copies; the rewrite is
        case-insensitive and maps every casing to the same ``FAKE_DRIVE_ID`` so
        id/eTag self-comparisons within a cassette still match."""
        cfg = _graph_cfg("deadbeefcafe0123")
        body = (
            b'{"id":"DEADBEEFCAFE0123!s0123abcd",'
            b'"eTag":"\\"DEADBEEFCAFE0123!112.0\\"",'
            b'"name":"f.txt",'
            b'"webUrl":"https://onedrive.live.com?cid=deadbeefcafe0123&id=DEADBEEFCAFE0123!112"}'
        )
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        # No casing of the real cid survives, in either the lower- or upper-cased form.
        assert b"DEADBEEFCAFE0123" not in scrubbed
        assert b"deadbeefcafe0123" not in scrubbed
        # Every occurrence maps to the same fake id, so the eTag/id/webUrl agree.
        assert scrubbed.count(FAKE_DRIVE_ID.encode()) == 4
        # The load-bearing item name is untouched.
        assert b'"name":"f.txt"' in scrubbed

    @pytest.mark.spec("REC-003")
    def test_drive_id_hyphen_split_form_rewritten_in_header_values(self) -> None:
        """The drive cid rides request headers in hyphen-split oid form (the
        last two GUID groups of an MSAL ``Oid:`` anchor) — a shape the
        contiguous-id rewrite misses. Every request-header value gets the
        env-redact chain, and the Graph profile's ``forms`` declares the split
        shape, so the cid is rewritten wherever it rides."""
        scrub = _composed_request_filter(_graph_cfg("deadbeefcafe0123"))
        out = scrub(
            _request(
                # Not X-AnchorMailbox (deleted natively) — an arbitrary header
                # proves the generic value-rewrite half.
                {"X-Diag": "Oid:00000000-0000-0000-DEAD-BEEFCAFE0123@72f988bf"},
                uri="https://graph.microsoft.com/v1.0/me/drive",
            )
        )
        value = out.headers["X-Diag"]
        assert "dead-beefcafe0123" not in value.lower()
        assert "deadbeefcafe0123" not in value.lower()
        assert FAKE_DRIVE_ID in value

    @pytest.mark.spec("REC-003")
    def test_non_cid_drive_id_redacted_as_single_form(self) -> None:
        """A drive id that is not a 16-hex consumer cid (the business
        ``b!...`` resource-id shape) embeds no bare cid to hyphen-split:
        ``forms`` yields only the contiguous value, and the redact still
        fires on it."""
        long_id = "b!0123456789abcdefghijklmnopqrstuv"
        assert _drive_id_forms(long_id) == (long_id,)
        scrub = _composed_request_filter(_graph_cfg(long_id))
        out = scrub(_request({}, uri=f"https://graph.microsoft.com/v1.0/drives/{long_id}/root:/a.txt:"))
        assert long_id not in out.uri
        assert FAKE_DRIVE_ID in out.uri

    def test_identity_and_site_pii_redacted_from_body(self) -> None:
        """The createdBy / lastModifiedBy user objects (email, displayName,
        userPrincipalName, loginName) and the siteId Graph embeds in item
        responses are blanked; none are read by the backend or asserted by
        conformance. The load-bearing ``name`` field — which IS read — must
        survive intact."""
        cfg = _graph_cfg()
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

    def test_token_response_identity_fields_redacted(self) -> None:
        """The OAuth token-exchange response (recorded when MSAL refreshes
        mid-suite) carries ``id_token`` (a JWT) and ``client_info`` (base64)
        alongside ``access_token`` / ``refresh_token``. The JWT/base64 payloads
        embed the account email, name, tenant id, and an ``oid`` holding the
        drive cid — none caught by the drive-id or email scrubs because they
        are base64-encoded, so all four token-response fields are redacted
        wholesale."""
        cfg = _graph_cfg("deadbeefcafe0123")
        # A synthetic token response: the id_token / client_info base64 stands in
        # for the account email / tenant id / oid-embedded cid a live response carries.
        jwt = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJwcmVmZXJyZWRfdXNlcm5hbWUiOiAidXNlckBleGFtcGxlLmNvbSJ9"
        body = (
            b'{"token_type":"Bearer","scope":"Files.ReadWrite",'
            b'"access_token":"' + jwt.encode() + b'.sig",'
            b'"refresh_token":"0.AXkA-secret",'
            b'"id_token":"' + jwt.encode() + b'.sig2",'
            b'"client_info":"eyJ2ZXIiOiIxLjAiLCJzdWIiOiJBQUE"}'
        )
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        for field in (b"access_token", b"refresh_token", b"id_token", b"client_info"):
            assert b'"' + field + b'":"REDACTED"' in scrubbed
        # No JWT prefix survives anywhere, so the base64'd identity is gone.
        assert b"eyJ" not in scrubbed
        # The non-secret scope field is untouched.
        assert b'"scope":"Files.ReadWrite"' in scrubbed

    @pytest.mark.spec("REC-004")
    def test_presigned_host_request_uri_rewritten_to_placeholder(self) -> None:
        """A request to a pre-signed content host (downloadUrl / uploadUrl /
        copy-move monitor URL) has its whole URI replaced with the placeholder,
        so the recorded request matches what the backend re-issues on replay."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(_request({}, uri="https://abc.microsoftpersonalcontent.com/personal/x/f.bin?tempauth=SECRET"))
        assert out.uri == GRAPH_PRESIGNED_PLACEHOLDER

    def test_graph_api_host_request_uri_preserved(self) -> None:
        """An API-host request (graph.microsoft.com) is id-normalised, not
        blanked: the placeholder rewrite is reserved for pre-signed content
        hosts."""
        scrub = _composed_request_filter(_graph_cfg())
        uri = "https://graph.microsoft.com/v1.0/drives/d/root:/a.txt:/content"
        assert scrub(_request({}, uri=uri)).uri == uri

    @pytest.mark.spec("REC-004")
    def test_downloadurl_body_value_replays_against_recorded_request(self) -> None:
        """End-to-end round-trip proof: the scrubbed downloadUrl the backend
        reads from a response body, fed back as the URI of the GET it then
        issues, normalises to the same placeholder the recorded live GET was
        rewritten to — so vcrpy matches them. A bare ``"REDACTED"`` token would
        not (it is not a URL), which is exactly why Graph reads could not
        replay before the placeholder."""
        cfg = _graph_cfg("realdrive123")
        scrub = _composed_request_filter(cfg)
        # Record side: scrub the metadata body carrying the live downloadUrl.
        body = b'{"@microsoft.graph.downloadUrl":"https://live-cdn.example/path?tempauth=SECRET"}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        # The backend reads that value back out of the body on replay...
        download_url = json.loads(scrubbed)["@microsoft.graph.downloadUrl"]
        assert download_url == GRAPH_PRESIGNED_PLACEHOLDER
        # ...and issues a GET to it; the composed filter normalises that request
        # the same way it normalised the recorded live GET -> identical URIs match.
        replay_uri = scrub(_request({}, uri=download_url)).uri
        recorded_uri = scrub(_request({}, uri="https://live-cdn.example/path?tempauth=SECRET")).uri
        assert replay_uri == recorded_uri == GRAPH_PRESIGNED_PLACEHOLDER

    def test_presigned_request_host_header_normalised(self) -> None:
        """The pre-signed branch rewrites the URI to the placeholder; the
        ``Host`` header naming the live content host (generic for consumer
        OneDrive, but tenant-identifying ``<tenant>-my.sharepoint.com`` on a
        business drive) is rewritten to the placeholder host so nothing of the
        live URL survives."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(
            _request(
                {"Host": "tenant-my.sharepoint.com", "User-Agent": "x"},
                uri="https://tenant-my.sharepoint.com/personal/x/f.bin?tempauth=SECRET",
            )
        )
        assert out.uri == GRAPH_PRESIGNED_PLACEHOLDER
        expected_host = urlsplit(GRAPH_PRESIGNED_PLACEHOLDER).hostname
        assert out.headers["Host"] == expected_host
        assert "sharepoint.com" not in out.headers["Host"]

    def test_presigned_request_body_credential_form_scrubbed(self) -> None:
        """An OAuth token exchange against an auth host outside the API hosts
        (login.live.com, a sovereign cloud) lands on the pre-signed branch too,
        so the credential-form scrub runs there before the early return."""
        scrub = _composed_request_filter(_graph_cfg())
        out = scrub(
            _request(
                {},
                uri="https://login.live.com/oauth20_token.srf",
                method="POST",
                body=b"grant_type=refresh_token&refresh_token=REALSECRET&client_secret=ALSOSECRET",
            )
        )
        # login.live.com is NOT an API host, so this is the pre-signed path.
        assert out.uri == GRAPH_PRESIGNED_PLACEHOLDER
        assert b"REALSECRET" not in out.body
        assert b"ALSOSECRET" not in out.body
        assert b"refresh_token=REDACTED" in out.body
        assert b"client_secret=REDACTED" in out.body

    def test_correlation_diagnostic_headers_dropped(self) -> None:
        """Per-request correlation / diagnostic headers (the ESTS
        ``x-ms-request-id`` a bare ``request-id`` entry would miss,
        ``x-ms-ests-server``, and the SharePoint/CDN ``sprequestguid`` /
        ``splogid`` / ``ms-cv`` / ``x-msedge-ref``) are dropped — parity with
        the Azure profile and stable cassette diffs across re-records."""
        cfg = _graph_cfg()
        resp: dict[str, Any] = {
            "headers": {
                "x-ms-request-id": ["abc-123"],
                "x-ms-ests-server": ["2.1 FRC ProdSlices"],
                "SPRequestGuid": ["guid-1"],
                "SPLogId": ["log-1"],
                "MS-CV": ["cv-1"],
                "X-MSEdge-Ref": ["edge-1"],
                "Content-Type": ["application/json"],
            },
            "body": {"string": b"{}"},
        }
        out = cfg["before_record_response"](resp)["headers"]
        survivors = {k.lower() for k in out}
        for dropped in ("x-ms-request-id", "x-ms-ests-server", "sprequestguid", "splogid", "ms-cv", "x-msedge-ref"):
            assert dropped not in survivors
        assert "content-type" in survivors  # unrelated headers kept

    def test_query_params_filtered(self) -> None:
        cfg = _graph_cfg()
        for param in ("tempauth", "Expires", "access_token", "sig"):
            assert param in cfg["filter_query_parameters"]

    def test_cassette_dir_is_per_backend_graph(self) -> None:
        assert GRAPH_PROFILE.cassette_dir.name == "graph"
        assert GRAPH_PROFILE.cassette_dir.parent.name == "cassettes"


@pytest.mark.spec("TEST-007")
class TestAzureCassetteScrub:
    """The SharedKey signature headers and live account identity must not survive."""

    def test_credential_headers_dropped_case_insensitively(self) -> None:
        scrub = _composed_request_filter(_azure_cfg())
        out = scrub(
            _request(
                {
                    # Mixed case on purpose: vcrpy's HeadersDict matches filter
                    # entries case-insensitively.
                    "AUTHORIZATION": "SharedKey liveacct:c2lnbmF0dXJl",
                    "x-ms-date": "Tue, 09 Jun 2026 10:00:00 GMT",
                    "X-Ms-Client-Request-Id": "abc-123",
                    "Cookie": "session=1",
                    "Accept": "application/xml",
                },
                uri="https://azreplay.dfs.core.windows.net/fs/path",
            )
        )
        survivors = {k.lower() for k in out.headers}
        for dropped in ("authorization", "x-ms-date", "x-ms-client-request-id", "cookie"):
            assert dropped not in survivors
        assert out.headers["Accept"] == "application/xml"

    def test_user_agent_normalised(self) -> None:
        scrub = _composed_request_filter(_azure_cfg())
        out = scrub(
            _request(
                {"User-Agent": "azsdk-python-storage-file-datalake/12.14 Python/3.11 (Linux)"},
                uri="https://azreplay.dfs.core.windows.net/fs/path",
            )
        )
        assert out.headers["User-Agent"] == "azsdk-python-replay"
        assert "User-Agent" in list(out.headers.keys())  # exact key case kept

    @pytest.mark.spec("REC-005")
    def test_user_agent_absent_stays_absent(self) -> None:
        """The ``("User-Agent", ...)`` tuple rewrites but never adds (vcrpy
        ``replace_headers`` guards on ``if k in new_headers:``). A request with
        no User-Agent must record none — the byte-identity property the native
        half rests on."""
        scrub = _composed_request_filter(_azure_cfg())
        out = scrub(_request({"Accept": "application/xml"}, uri="https://azreplay.dfs.core.windows.net/fs/path"))
        assert "user-agent" not in {k.lower() for k in out.headers}

    def test_account_filesystem_and_tmp_uuid_normalised_in_uri(self) -> None:
        """Record mode: the live account, the per-call conformance filesystem
        UUID, and the write_atomic temp suffix all normalise; the SAS-style
        query params ride the native ``filter_query_parameters`` delete."""
        scrub = _composed_request_filter(_azure_cfg("liveacct"))
        out = scrub(
            _request(
                {},
                uri=(
                    "https://liveacct.dfs.core.windows.net/conformance-12ab34cd"
                    "/dir/.~tmp.f.txt.0a1b2c3d?sig=QUERYSECRET"
                ),
            )
        )
        assert "liveacct" not in out.uri
        assert FAKE_ACCOUNT in out.uri
        assert FAKE_FILESYSTEM in out.uri
        assert "0a1b2c3d" not in out.uri  # temp-file uuid normalised
        assert "QUERYSECRET" not in out.uri  # native query filter ran

    def test_copy_source_header_rewritten_not_deleted(self) -> None:
        """The ``x-ms-copy-source`` / ``x-ms-rename-source`` value rewrites
        have no vcrpy-native equivalent and ride the generic header-value
        chain in the custom hook."""
        scrub = _composed_request_filter(_azure_cfg("liveacct"))
        out = scrub(
            _request(
                {"x-ms-rename-source": "/liveacct/conformance-12ab34cd/dir/.~tmp.f.txt.0a1b2c3d"},
                uri="https://liveacct.dfs.core.windows.net/conformance-12ab34cd/dir/f.txt",
            )
        )
        val = out.headers["x-ms-rename-source"]
        assert "liveacct" not in val
        assert FAKE_ACCOUNT in val
        assert FAKE_FILESYSTEM in val
        assert "0a1b2c3d" not in val

    def test_copy_source_response_header_rewritten(self) -> None:
        """Azure echoes the copy-source URL back in the response; the same
        account/filesystem rewrite applies (list- and scalar-valued alike)."""
        cfg = _azure_cfg("liveacct")
        resp: dict[str, Any] = {
            "headers": {"x-ms-copy-source": ["https://liveacct.dfs.core.windows.net/conformance-12ab34cd/src.txt"]},
            "body": {"string": b""},
        }
        val = cfg["before_record_response"](resp)["headers"]["x-ms-copy-source"][0]
        assert "liveacct" not in val
        assert FAKE_ACCOUNT in val
        assert FAKE_FILESYSTEM in val

    def test_account_and_request_id_scrubbed_from_response_body(self) -> None:
        """Response bodies (error XML, listings) carry the live account,
        filesystem uuid, and per-run RequestId/Time fragments — all normalised
        in the bytes domain so binary payloads never crash a decode."""
        cfg = _azure_cfg("liveacct")
        body = (
            b"<Error><Message>RequestId:0a1b2c3d-9999-4f4c-a049-deadbeefcafe\n"
            b"Time:2026-06-11T12:00:00.000Z</Message>"
            b"<Detail>https://liveacct.dfs.core.windows.net/conformance-12ab34cd/f.txt</Detail></Error>"
        )
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert b"liveacct" not in scrubbed
        assert FAKE_ACCOUNT.encode() in scrubbed
        assert FAKE_FILESYSTEM.encode() in scrubbed
        assert b"RequestId:SCRUBBED" in scrubbed
        assert b"Time:SCRUBBED" in scrubbed

    def test_hns_container_and_prefix_normalised_in_uri(self) -> None:
        """BK-303: the live ``RS_TEST_LIVE_HNS_CONTAINER`` filesystem name and
        the per-session ``live-hns/<uuid8>`` prefix both normalise so HNS
        cassettes replay against ``container=FAKE_FILESYSTEM`` and the replay
        fixture's fixed ``live-hns/REPLAY`` dirpath."""
        cfg = build_profile_vcr_config(AZURE_PROFILE, {"azure.account": "liveacct", "azure.hns-container": "myhnsfs"})
        scrub = _composed_request_filter(cfg)
        out = scrub(_request({}, uri="https://liveacct.dfs.core.windows.net/myhnsfs/live-hns/0a1b2c3d/dirblob"))
        assert "liveacct" not in out.uri
        assert "myhnsfs" not in out.uri  # azure.hns-container env-redact ran
        assert FAKE_ACCOUNT in out.uri
        assert FAKE_FILESYSTEM in out.uri
        assert "0a1b2c3d" not in out.uri  # azure.uri.hns-prefix ran
        assert "live-hns/REPLAY/dirblob" in out.uri

    def test_hns_async_prefix_normalised_in_uri(self) -> None:
        """BK-303: the async suite's ``live-hns-async/<uuid8>`` prefix normalises too."""
        cfg = build_profile_vcr_config(AZURE_PROFILE, {"azure.account": "liveacct", "azure.hns-container": "myhnsfs"})
        scrub = _composed_request_filter(cfg)
        out = scrub(_request({}, uri="https://liveacct.dfs.core.windows.net/myhnsfs/live-hns-async/deadbeef/dirblob"))
        assert "deadbeef" not in out.uri
        assert "live-hns-async/REPLAY/dirblob" in out.uri

    def test_hns_prefix_normalised_in_response_body(self) -> None:
        """BK-303 bytes twin (``azure.body.hns-prefix``): ``get_paths`` listing
        responses echo child paths carrying the per-session prefix uuid."""
        cfg = build_profile_vcr_config(AZURE_PROFILE, {"azure.account": "liveacct", "azure.hns-container": "myhnsfs"})
        body = b'{"paths":[{"name":"live-hns/0a1b2c3d/dirblob"},{"name":"live-hns-async/deadbeef/x"}]}'
        scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
        assert b"0a1b2c3d" not in scrubbed
        assert b"deadbeef" not in scrubbed
        assert b"live-hns/REPLAY/dirblob" in scrubbed
        assert b"live-hns-async/REPLAY/x" in scrubbed

    def test_root_probe_filesystem_normalised_in_uri(self) -> None:
        """BK-303 (``azure.uri.root-fs``): the dedicated empty root-probe
        filesystem name rewrites to ``FAKE_FILESYSTEM`` so the root
        ``get_folder_info("")`` cassette replays against ``container=FAKE_FILESYSTEM``."""
        cfg = build_profile_vcr_config(AZURE_PROFILE, {"azure.account": "liveacct"})
        scrub = _composed_request_filter(cfg)
        out = scrub(
            _request(
                {},
                uri=f"https://liveacct.dfs.core.windows.net/{LIVE_HNS_ROOT_FS}?directory=%2F&recursive=true&resource=filesystem",
            )
        )
        assert LIVE_HNS_ROOT_FS not in out.uri  # azure.uri.root-fs ran
        assert FAKE_FILESYSTEM in out.uri

    def test_hns_container_resolver_returns_none_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``None`` (the EnvRedact disable signal) when no live HNS container is
        configured — a blank value, like the account resolver. setenv rather than
        delenv so ``load_dotenv(override=False)`` cannot pull a real value from a
        developer's ``.env``."""
        monkeypatch.setenv("RS_TEST_LIVE_HNS_CONTAINER", "   ")
        assert _resolve_live_hns_container() is None

    def test_query_params_filtered(self) -> None:
        cfg = _azure_cfg()
        for param in ("sig", "se", "skoid"):
            assert param in cfg["filter_query_parameters"]

    def test_account_resolver_returns_none_without_live_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``None`` — the EnvRedact disable signal, never a crash or ``""``
        — when no real connection string is configured: blank value or an
        Azurite signature (its well-known account is not a secret). setenv
        rather than delenv so ``load_dotenv(override=False)`` cannot pull a
        real value from a developer's ``.env``."""
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "   ")
        assert _resolve_live_account() is None
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
        assert _resolve_live_account() is None

    def test_account_resolver_parses_live_connection_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "AZURE_STORAGE_CONNECTION_STRING",
            "DefaultEndpointsProtocol=https;AccountName=realacct;AccountKey=abc==;EndpointSuffix=core.windows.net",
        )
        assert _resolve_live_account() == "realacct"


class TestScrubCore:
    """Invariants of the backend-agnostic core (spec 049)."""

    @pytest.mark.spec("REC-001")
    def test_core_module_is_backend_agnostic(self) -> None:
        """The shared module exposes no backend-specific names: every constant
        or helper naming a concrete backend belongs in that backend's profile
        module, so a third backend extends the system without touching the
        core."""
        backend_tokens = ("azure", "graph", "s3", "sftp")
        offenders = [name for name in vars(_cassettes_core) if any(token in name.lower() for token in backend_tokens)]
        assert not offenders, f"backend-specific names in the shared core: {offenders}"

    @pytest.mark.spec("REC-002")
    @pytest.mark.parametrize("profile", _registered_profiles(), ids=lambda p: p.backend)
    def test_named_rules_unique_prefixed_and_typed(self, profile: CassetteProfile) -> None:
        """Every redaction rule carries a unique, backend-prefixed audit name
        and a declared expectation — the identity the Step-4 named audit
        gates on."""
        rules = profile.named_rules()
        assert rules, f"profile {profile.backend!r} declares no named rules"
        names = [name for name, _ in rules]
        assert len(names) == len(set(names)), f"duplicate rule names: {names}"
        for name, expectation in rules:
            assert name.startswith(f"{profile.backend}."), name
            assert expectation in ("required-to-fire", "opportunistic")

    @pytest.mark.spec("REC-003")
    def test_empty_string_live_value_fails_loud(self) -> None:
        """``None`` disables an env-redact; an empty string is a
        misconfigured resolver, and silently skipping the scrub would
        record unredacted — config build refuses instead."""
        with pytest.raises(ValueError, match="graph.drive-id"):
            build_profile_vcr_config(GRAPH_PROFILE, {"graph.drive-id": ""})

    @pytest.mark.spec("REC-003")
    def test_env_redact_covers_every_surface_and_form(self) -> None:
        """A declared live value is redacted in the request URI, request-header
        values, request body, and response body — bytes and str, every declared
        form, case-insensitively when declared (the Graph cid matrix)."""
        cid = "deadbeefcafe0123"
        cfg = _graph_cfg(cid)
        scrub = _composed_request_filter(cfg)
        out = scrub(
            _request(
                {"X-Diag": "Oid:00000000-0000-0000-DEAD-BEEFCAFE0123@72f988bf"},
                uri=f"https://graph.microsoft.com/v1.0/drives/{cid}/root:/a.txt:",
                method="POST",
                body=b'{"parentReference":{"driveId":"DEADBEEFCAFE0123"}}',
            )
        )
        request_blob = (out.uri + " " + " ".join(out.headers.values())).lower() + " " + out.body.decode().lower()
        assert cid not in request_blob
        assert f"{cid[:4]}-{cid[4:]}" not in request_blob
        assert FAKE_DRIVE_ID in out.uri
        assert FAKE_DRIVE_ID in out.headers["X-Diag"]
        assert FAKE_DRIVE_ID.encode() in out.body
        # Response body: bytes and str dispatch.
        for body in (b'{"id":"DEADBEEFCAFE0123!s1"}', '{"id":"deadbeefcafe0123!s1"}'):
            scrubbed = cfg["before_record_response"]({"body": {"string": body}})["body"]["string"]
            text = scrubbed.decode() if isinstance(scrubbed, bytes) else scrubbed
            assert isinstance(scrubbed, type(body))  # str in -> str out, bytes in -> bytes out
            assert cid not in text.lower()
            assert FAKE_DRIVE_ID in text

    @pytest.mark.spec("REC-006")
    @pytest.mark.parametrize("profile", _registered_profiles(), ids=lambda p: p.backend)
    def test_profile_forbidden_set_includes_envelope(self, profile: CassetteProfile) -> None:
        """Every profile's gate set starts from the shared envelope; per-profile
        additions extend it, never replace it."""
        combined = profile.all_forbidden_patterns()
        assert combined[: len(FORBIDDEN_ENVELOPE)] == FORBIDDEN_ENVELOPE
        labels = [label for label, _ in combined]
        assert len(labels) == len(set(labels)), f"duplicate forbidden-pattern labels: {labels}"

    @pytest.mark.spec("REC-006")
    def test_oid_anchor_marker_matches_live_header_shape(self) -> None:
        """The envelope's oid-anchor marker catches the X-AnchorMailbox value
        shape a cold-cache MSAL refresh POST records — the leak the
        contiguous-cid markers miss."""
        live_shape = b"X-AnchorMailbox: Oid:00000000-0000-0000-dead-beefcafe0123@9188040d-6c67-4c5b-b112-36a304b66dad"
        markers = dict(FORBIDDEN_ENVELOPE)
        assert re.search(markers["oid anchor (hyphen-split account id)"], live_shape, re.IGNORECASE)

    @pytest.mark.spec("REC-006")
    def test_fire_counts_accumulate_and_manifest_dumps(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each named rule application increments its audit counter; the
        manifest dump writes the snapshot only when the recorder exported the
        path."""
        reset_scrub_fire_counts()
        cfg = _graph_cfg("deadbeefcafe0123")
        scrub = _composed_request_filter(cfg)
        scrub(_request({}, uri="https://graph.microsoft.com/v1.0/drives/deadbeefcafe0123/root:/rs-conformance-ab12/x:"))
        cfg["before_record_response"]({"body": {"string": b'{"@microsoft.graph.downloadUrl":"https://h?t=s"}'}})
        counts = scrub_fire_counts()
        assert counts.get("graph.drive-id", 0) >= 1
        assert counts.get("graph.uri.conformance-root", 0) >= 1
        assert counts.get("graph.body.download-url", 0) >= 1
        # No env var -> no dump.
        monkeypatch.delenv("_RS_SCRUB_MANIFEST", raising=False)
        assert dump_scrub_manifest() is None
        # Env var set -> snapshot written (xdist workers suffix their own file).
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.setenv("_RS_SCRUB_MANIFEST", str(tmp_path / "manifest.json"))
        path = dump_scrub_manifest()
        assert path is not None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["graph.drive-id"] >= 1
        reset_scrub_fire_counts()


class TestCommittedCassettePIISweep:
    """Creds-free guard over every profile's *committed* cassette tree.

    The recorder's Step-4 scrub-verify asserts the forbidden patterns only on
    the live-record path. This sweep runs the identical combined gate set
    (envelope + per-profile additions) over the checked-in ``.yaml`` files
    with no live tier, so a hand edit, a bad merge, or a re-record on a
    machine without the env vars that reintroduces a bearer token / JWT /
    ``b!…`` id / site GUID / tenant host / credential form / identity key is
    caught in CI, not by a one-time manual grep.
    """

    @pytest.mark.spec("REC-006")
    @pytest.mark.parametrize("profile", _registered_profiles(), ids=lambda p: p.backend)
    def test_committed_cassettes_carry_no_forbidden_pii(self, profile: CassetteProfile) -> None:
        files = sorted(profile.cassette_dir.glob("*.yaml"))
        assert files, f"no committed cassettes under {profile.cassette_dir}; sweep would be vacuous"
        leaks: list[str] = []
        for path in files:
            raw = path.read_bytes()
            for label, pattern in profile.all_forbidden_patterns():
                if re.search(pattern, raw, re.IGNORECASE):
                    leaks.append(f"{path.name}: {label}")
        assert not leaks, "forbidden PII markers found in committed cassettes:\n" + "\n".join(leaks)
