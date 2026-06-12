"""Microsoft Graph cassette profile: scrub declarations and replay identifiers.

Declares ``GRAPH_PROFILE`` — the ``CassetteProfile`` shared by ``graph_live``
(record) and ``graph_replay`` (playback) — plus the fixed identifiers the
replay fixture builds its backend from.

Security gate: the Graph backend sends ``Authorization: Bearer <token>`` on
every request and downloads content from pre-signed URLs whose query carries
its own access token; the OAuth token exchange carries credentials in the
request body and base64-encoded account identity in the response. None may
survive into a committed cassette.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tests.backends.fixtures._cassettes import (
    CassetteProfile,
    EnvRedact,
    PresignedPolicy,
    RedactPattern,
    UriRewrite,
)

CASSETTE_DIR_GRAPH: Path = Path(__file__).resolve().parent.parent / "cassettes" / "graph"
"""Absolute path to ``tests/backends/cassettes/graph/`` (TEST-007)."""

# region: fixed replay identifiers

FAKE_DRIVE_ID = "graphreplaydrive"
"""Placeholder drive id written into every recorded Graph cassette URL.

The replay fixture constructs the backend with this same drive id so the
``/drives/{drive_id}/...`` path in every outgoing request matches the
cassette. Not a secret — an arbitrary well-formed token.
"""

GRAPH_CONFORMANCE_BASE_PATH = "rs-conformance"
"""Canonical ``base_path`` (GR-058) the ``graph_replay`` fixture roots under.

``graph_live`` isolates each conformance test in a unique
``rs-conformance-<uuid>`` drive subfolder; the scrub rewrites that per-test
uuid form back to this stable token in recorded URIs and bodies, so a
cassette recorded under a random folder replays against this fixed path.
"""

GRAPH_PRESIGNED_PLACEHOLDER = "https://graph-download.invalid/REDACTED"
"""Stable replacement for every pre-signed Graph URL in recorded cassettes.

A pre-signed URL (``@microsoft.graph.downloadUrl``, the upload-session
``uploadUrl``, the copy/move monitor URL) carries its own access token. It
is wiped to this one valid placeholder in two coupled places so record and
replay agree: the response-body value and the request URI of any
pre-signed-host request (REC-004). The ``.invalid`` TLD (RFC 6761) never
resolves, so the placeholder is obviously fake and non-routable; it is a
well-formed URL — not a bare token — because the backend reads the value
back out of the scrubbed body and re-requests it on replay.
"""

# endregion

# region: scrub patterns

# Hosts whose request URIs are preserved (id-normalised only): the Graph API
# and the MSAL token endpoint. Every OTHER host a recording touches is a
# pre-signed content host whose URI carries an access token.
_GRAPH_API_HOSTS: tuple[str, ...] = ("graph.microsoft.com", "login.microsoftonline.com")

# Per-test conformance-root normalisation (GR-058 isolation <-> replay):
# the unique ``rs-conformance-<uuid>`` subfolder rewrites back to the stable
# base-path token in URIs and bodies.
_CONFORMANCE_ROOT_PATTERN: re.Pattern[str] = re.compile(r"rs-conformance-[0-9a-f]+")

# Request-body redactions for the OAuth token-exchange POST: MSAL sends the
# client-credentials / certificate / refresh flows form-encoded over
# ``requests`` (which vcrpy also patches), so the credential fields must
# never reach a cassette. The device-code flow carries none of them; the
# app-only recording path (graph-setup.md) does. Kept as byte-preserving,
# method-agnostic regexes rather than vcrpy's ``filter_post_data_parameters``,
# which is POST-only and re-serialises every ``application/json`` body even
# when nothing matches — churning the security-review diff on re-record
# (REC-005). Revisit only if vcrpy gains a non-rewriting filter.
_REQUEST_CREDENTIAL_REDACTIONS: tuple[RedactPattern, ...] = (
    RedactPattern(
        name="graph.req-body.client-secret",
        pattern=re.compile(rb"(client_secret=)[^&\r\n]+"),
        replacement=rb"\1REDACTED",
    ),
    RedactPattern(
        name="graph.req-body.client-assertion",
        pattern=re.compile(rb"(client_assertion=)[^&\r\n]+"),
        replacement=rb"\1REDACTED",
    ),
    RedactPattern(
        name="graph.req-body.assertion",
        pattern=re.compile(rb"(assertion=)[^&\r\n]+"),
        replacement=rb"\1REDACTED",
    ),
    RedactPattern(
        name="graph.req-body.refresh-token",
        pattern=re.compile(rb"(refresh_token=)[^&\r\n]+"),
        replacement=rb"\1REDACTED",
    ),
)

_PRESIGNED_PLACEHOLDER_BYTES = GRAPH_PRESIGNED_PLACEHOLDER.encode()


def _resolve_live_drive_id() -> str | None:
    """``EnvRedact`` resolver: the real drive id (record mode only)."""
    return os.environ.get("GRAPH_DRIVE_ID") or None


def _drive_id_forms(value: str) -> tuple[str, ...]:
    """The shapes Graph echoes the drive cid in.

    On consumer OneDrive — the recorded tier — the drive id IS the account
    cid: exactly 16 hex chars, lower-cased in URIs and UPPER-cased inside
    item ids / eTags / webUrls (hence the case-insensitive match). Beyond
    that contiguous form, MSAL's ``X-AnchorMailbox: Oid:...`` request header
    embeds the cid hyphen-split as the last two GUID groups
    (``XXXX-XXXXXXXXXXXX``). The header itself is deleted (filter_headers),
    but the split form is matched everywhere as belt and braces. Any other
    length (e.g. a business ``b!...`` drive resource id, which embeds no
    bare cid to split) passes through as the single contiguous form.
    """
    if len(value) == 16:
        return (value, f"{value[:4]}-{value[4:]}")
    return (value,)


# endregion

GRAPH_PROFILE = CassetteProfile(
    backend="graph",
    cassette_dir=CASSETTE_DIR_GRAPH,
    # Graph is async-only (no sync twin), so live (record) and replay
    # (playback) share one canonical "graph" suffix.
    fixture_aliases={
        "graph_live": "graph",
        "graph_replay": "graph",
    },
    # The bearer token, cookies, and correlation header are deleted;
    # ``X-AnchorMailbox`` embeds the account oid (the drive cid in
    # hyphen-split form) on MSAL token POSTs and the backend never reads it
    # on replay, so it is dropped outright. The ``User-Agent`` tuple value
    # matches the Azure profile's so the corpus stays uniform (the literal
    # is recorded in every committed cassette; changing it is a corpus
    # rewrite).
    filter_headers=(
        "authorization",
        "cookie",
        "client-request-id",
        "x-anchormailbox",
        ("User-Agent", "azsdk-python-replay"),
    ),
    # Pre-signed download-URL query parameters: consumer OneDrive uses
    # ``tempauth`` / ``Expires``; SharePoint uses the SAS-style set;
    # ``access_token`` covers the rare in-query token form. Request URIs
    # keep their query *structure* (it is part of vcrpy's match key), so
    # tokens are removed surgically by name here — unlike URL-valued
    # response headers, which get the value-based whole-query wipe.
    filter_query_parameters=(
        "sig",
        "se",
        "st",
        "sp",
        "sv",
        "sr",
        "skoid",
        "sktid",
        "skt",
        "ske",
        "sks",
        "skv",
        "tempauth",
        "Expires",
        "access_token",
    ),
    env_redacts=(
        EnvRedact(
            name="graph.drive-id",
            resolve=_resolve_live_drive_id,
            fake=FAKE_DRIVE_ID,
            case_insensitive=True,
            forms=_drive_id_forms,
        ),
    ),
    uri_rewrites=(
        UriRewrite(
            name="graph.uri.conformance-root",
            pattern=_CONFORMANCE_ROOT_PATTERN,
            replacement=GRAPH_CONFORMANCE_BASE_PATH,
            expectation="required-to-fire",
        ),
    ),
    presigned=PresignedPolicy(api_hosts=_GRAPH_API_HOSTS, placeholder=GRAPH_PRESIGNED_PLACEHOLDER),
    request_body_redactions=(
        *_REQUEST_CREDENTIAL_REDACTIONS,
        # The move/copy parentReference body carries the conformance root in
        # ``/drives/{id}/root:`` paths (the drive id itself rides the
        # env-redact, applied to bodies by the core).
        RedactPattern(
            name="graph.req-body.conformance-root",
            pattern=re.compile(_CONFORMANCE_ROOT_PATTERN.pattern.encode()),
            replacement=GRAPH_CONFORMANCE_BASE_PATH.encode(),
        ),
    ),
    response_body_redactions=(
        # A pre-signed URL value is replaced with the placeholder URL (not a
        # bare token) so the value the backend reads back is a valid,
        # replay-matchable URL (REC-004). ``uploadUrl`` (createUploadSession)
        # is pre-authorised with its own query token — the same threat.
        RedactPattern(
            name="graph.body.download-url",
            pattern=re.compile(rb'("@microsoft\.graph\.downloadUrl"\s*:\s*")[^"]*(")'),
            replacement=rb"\1" + _PRESIGNED_PLACEHOLDER_BYTES + rb"\2",
            expectation="required-to-fire",
        ),
        # Opportunistic: the conformance payloads are small enough that the
        # backend's simple-PUT path records no createUploadSession today.
        RedactPattern(
            name="graph.body.upload-url",
            pattern=re.compile(rb'("uploadUrl"\s*:\s*")[^"]*(")'),
            replacement=rb"\1" + _PRESIGNED_PLACEHOLDER_BYTES + rb"\2",
        ),
        # The OAuth token-exchange response (recorded whenever MSAL refreshes
        # mid-suite; a warm in-memory cache hides it). Beyond access/refresh
        # tokens it carries ``id_token`` (a JWT) and ``client_info`` (base64)
        # whose payloads embed the account email, display name, tenant id,
        # and an ``oid`` containing the drive cid — none caught by the
        # drive-id / email scrubs because they are base64-encoded, so all
        # four fields are redacted wholesale. Replay never re-issues the
        # token request (``graph_replay`` uses a constant stub token).
        RedactPattern(
            name="graph.body.token-response",
            pattern=re.compile(rb'("(?:access_token|refresh_token|id_token|client_info)"\s*:\s*")[^"]*(")'),
            replacement=rb"\1REDACTED\2",
        ),
        RedactPattern(
            name="graph.body.bearer",
            pattern=re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=\-]+"),
            replacement=b"Bearer REDACTED",
        ),
        # Identity / tenant PII embedded in item responses: the ``createdBy``
        # / ``lastModifiedBy`` user objects (real account email + display
        # name) and the personal-OneDrive ``siteId`` GUID. None are read by
        # the backend or asserted by conformance. Keys are matched whole (the
        # opening quote is part of the match) so ``"displayName"`` is
        # redacted while the load-bearing ``"name"`` item field — which the
        # backend DOES read — is untouched.
        RedactPattern(
            name="graph.body.identity-pii",
            pattern=re.compile(rb'("(?:email|displayName|userPrincipalName|loginName|siteId)"\s*:\s*")[^"]*(")'),
            replacement=rb"\1REDACTED\2",
            expectation="required-to-fire",
        ),
        RedactPattern(
            name="graph.body.conformance-root",
            pattern=re.compile(_CONFORMANCE_ROOT_PATTERN.pattern.encode()),
            replacement=GRAPH_CONFORMANCE_BASE_PATH.encode(),
            expectation="required-to-fire",
        ),
    ),
    response_header_deletes=frozenset(
        {
            # ``docID`` rides on every pre-signed-content response embedding
            # the personal-OneDrive site GUID; the backend never reads it, so
            # the whole header is dropped rather than partially normalised.
            # The rest are per-request correlation / diagnostic ids (ESTS,
            # SharePoint, CDN) the backend never reads: dropping them keeps
            # cassette diffs stable across re-records.
            "request-id",
            "client-request-id",
            "x-ms-ags-diagnostic",
            "set-cookie",
            "date",
            "docid",
            "x-ms-request-id",
            "x-ms-ests-server",
            "sprequestguid",
            "splogid",
            "ms-cv",
            "x-msedge-ref",
        }
    ),
    # ``GET /content`` answers 302 whose ``Location`` IS the pre-signed
    # downloadUrl (GR-015); the 202 async copy/move monitor URL rides the
    # same header. A pre-signed-host value collapses to the placeholder; an
    # API-host value keeps host + path with its query wiped value-based.
    url_response_headers=("location", "content-location"),
    forbidden_patterns=(
        # The pre-signed-content ``docID`` header carries the OneDrive
        # site-collection GUID as ``...content.com_<site-guid>_<doc-guid>``.
        ("pre-signed docID / site GUID", rb"microsoftpersonalcontent\.com_[0-9a-fA-F-]{36}_"),
        # A business-drive pre-signed content host is tenant-identifying
        # (``<tenant>-my.sharepoint.com``); consumer recordings never contain
        # ``sharepoint.com``, so any hit is a leak.
        ("tenant SharePoint host", rb"-my\.sharepoint\.com"),
        # The long ``b!...`` drive resource id (the cid's full form).
        ("long b! drive id", rb"b![A-Za-z0-9_-]{20,}"),
        # Identity keys that escaped the PII body redaction.
        ("unredacted identity key", rb'"(?:email|userPrincipalName)"\s*:\s*"(?!REDACTED)'),
    ),
)
"""The Microsoft Graph scrub profile (spec 049; GR-035, TEST-007).

What it strips: the bearer token, cookies, correlation and
``X-AnchorMailbox`` request headers and the pre-signed query parameters
(native filters); OAuth credentials from token-exchange request bodies;
every pre-signed URL (URI, ``Location``, body values) collapsed to one
placeholder; the token-exchange response fields carrying base64-encoded
account identity; the ``createdBy`` / ``lastModifiedBy`` / ``siteId``
identity PII in item responses; and the live drive id (every casing and
the hyphen-split oid form) plus the per-test conformance root, rewritten
to fixed replay tokens.
"""

__all__ = [
    "CASSETTE_DIR_GRAPH",
    "FAKE_DRIVE_ID",
    "GRAPH_CONFORMANCE_BASE_PATH",
    "GRAPH_PRESIGNED_PLACEHOLDER",
    "GRAPH_PROFILE",
]
