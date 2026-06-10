"""Shared HTTP cassette helpers: constants, scrubbing, live-connection utilities.

Used by ``azure_replay`` / ``azure_replay_async`` fixtures and the
conformance conftest's ``vcr_config`` fixture.  The scrubbing layer
(``build_vcr_config``) is the single source of truth for what gets
stripped out of every recorded cassette so that replays carry no
credentials, per-run identifiers, or machine-specific strings.

Porting notes
-------------
* Carried forward from ``sdd/research/bk-181-poc/conftest.py`` (frozen
  spike) with the following additions required by BK-181 proper:
  - Filesystem-UUID rewrite (``_FILESYSTEM_PATTERN``) to normalise the
    per-call ``conformance-<uuid>`` filesystem name to the fixed
    ``FAKE_FILESYSTEM`` so live and replay cassettes share URLs.
  - Body-level regex scrub for ``RequestId:`` / ``Time:`` fragments that
    survive header scrubbing (error-response XML).
  - ``User-Agent`` normalisation so cassettes don't capture the recording
    machine's Python/OS version string.
* ``_SCRUB_QUERY_PARAMS`` carries the SAS-token parameters even though
  SharedKey auth keeps the signature in headers; listed so S3 replay (PR 2)
  and any future SAS-authenticated fixture inherit the intent.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Directory constant
# ---------------------------------------------------------------------------

CASSETTE_DIR_AZURE: Path = Path(__file__).resolve().parent.parent / "cassettes" / "azure"
"""Absolute path to ``tests/backends/cassettes/azure/``.

Used by ``tests/backends/conformance/conftest.py`` for both the
``vcr_cassette_dir`` fixture override and the missing-cassette skip hook.
"""

CASSETTE_DIR_GRAPH: Path = Path(__file__).resolve().parent.parent / "cassettes" / "graph"
"""Absolute path to ``tests/backends/cassettes/graph/`` (TEST-007).

Per-backend cassette directory for the Microsoft Graph backend (ID-127 /
GR-FOUNDATION). The conformance ``vcr_cassette_dir`` dispatch will route
``graph_*`` fixtures here once the backend's replay fixtures land in
GR-CORE; the constant exists now so the scrub profile below and its
security-gate test have a stable home to reference.
"""

# ---------------------------------------------------------------------------
# Fixed identifiers used in replay and scrubbing
# ---------------------------------------------------------------------------

FAKE_ACCOUNT = "azreplay"
"""Placeholder account name written into every recorded cassette URL.

The replay fixtures build the backend from a connection string naming this
same account so that the host in every outgoing request matches the cassette.
Not a secret — it is just a well-formed DNS label.
"""

FAKE_FILESYSTEM = "conformance-azure-replay"
"""Fixed filesystem (container) name used by replay fixtures.

Live fixtures mint a per-call ``conformance-<uuid>``; the scrubbing layer
rewrites those to this fixed name so cassettes are replay-compatible.
"""

_FAKE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
"""Azurite's well-known emulator key.

Valid base64 (so the SharedKey signer and ``from_connection_string`` both
accept it); publicly documented and not a secret.
"""

FAKE_CONN_STR = (
    f"DefaultEndpointsProtocol=https;AccountName={FAKE_ACCOUNT};AccountKey={_FAKE_KEY};EndpointSuffix=core.windows.net"
)
"""Fake connection string used by replay fixtures.

Contains no real credentials; the ``FAKE_ACCOUNT`` host is matched by
vcrpy against the scrubbed cassette URLs.
"""

# ---------------------------------------------------------------------------
# Scrub lists
# ---------------------------------------------------------------------------

_SCRUB_REQUEST_HEADERS: frozenset[str] = frozenset({"authorization", "x-ms-date", "x-ms-client-request-id", "cookie"})
_SCRUB_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {"x-ms-request-id", "x-ms-client-request-id", "x-ms-correlation-request-id", "set-cookie", "date"}
)
_SCRUB_QUERY_PARAMS: tuple[str, ...] = (
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
)

# Matches both ``conformance-12ab34cd`` (sync live) and
# ``conformance-async-12ab34cd`` (async live); replaced with FAKE_FILESYSTEM.
_FILESYSTEM_PATTERN: re.Pattern[str] = re.compile(r"conformance(?:-async)?-[0-9a-f]{8}")
# Bytes version used when the response body is raw binary (non-decodable).
_FILESYSTEM_PATTERN_BYTES: re.Pattern[bytes] = re.compile(_FILESYSTEM_PATTERN.pattern.encode())

# Matches the 8-char hex UUID suffix that write_atomic appends to temp files:
#   .~tmp.{basename}.{uuid8}
# The suffix differs between record and replay runs, so normalise it out so
# the cassette path matches on replay.  Applied to request URIs only.
_TMP_UUID_PATTERN: re.Pattern[str] = re.compile(r"(\.~tmp\.[^?/]*)\.[0-9a-f]{8}(?=[?/]|$)")

# Error-response XML body fragments that carry per-run identifiers.
# Applied to bytes bodies and (if they somehow arrive as str) str bodies alike.
_BODY_SCRUB: list[tuple[re.Pattern[bytes], bytes]] = [
    (re.compile(rb"RequestId:[0-9a-f-]+"), b"RequestId:SCRUBBED"),
    (re.compile(rb"Time:\d{4}-\d{2}-\d{2}T[^<\"&\r\n]+"), b"Time:SCRUBBED"),
]

_USER_AGENT_NORMALIZED = "azsdk-python-replay"

# ---------------------------------------------------------------------------
# Microsoft Graph scrub profile (ID-127 / GR-FOUNDATION; GR-035, TEST-007)
# ---------------------------------------------------------------------------
#
# Security gate: the Graph backend sends an ``Authorization: Bearer <token>``
# on every request and downloads content from a pre-signed
# ``@microsoft.graph.downloadUrl`` whose query carries its own access token.
# Neither may survive into a committed cassette. The profile below drops the
# bearer + cookies + correlation ids, redacts the downloadUrl and any
# bearer/access/refresh token from response bodies, filters the pre-signed
# download query params, and rewrites the live ``drive_id`` to a placeholder.

FAKE_DRIVE_ID = "graphreplaydrive"
"""Placeholder drive id written into every recorded Graph cassette URL.

Replay fixtures (GR-CORE) construct the backend with this same drive id so
the ``/drives/{drive_id}/...`` path in every outgoing request matches the
cassette. Not a secret — an arbitrary well-formed token.
"""

GRAPH_CONFORMANCE_BASE_PATH = "rs-conformance"
"""Canonical ``base_path`` (GR-058) the ``graph_replay`` fixture roots under.

``graph_live`` isolates each conformance test in a unique
``rs-conformance-<uuid>`` drive subfolder; the scrub below rewrites that
per-test uuid form back to this stable token in recorded cassette URIs and
bodies, so a cassette recorded under a random folder replays against this fixed
path. ``graph_replay`` constructs its backend with this same ``base_path`` so
every outgoing request matches. Not a secret — a normalisation token.
"""

_GRAPH_SCRUB_REQUEST_HEADERS: frozenset[str] = frozenset({"authorization", "cookie", "client-request-id"})
_GRAPH_SCRUB_RESPONSE_HEADERS: frozenset[str] = frozenset(
    # ``docID`` rides on every pre-signed-content response as
    # ``microsoftpersonalcontent.com_<site-collection-guid>_<doc-guid>`` — the
    # middle GUID is the personal-OneDrive site id, the same value
    # ``_GRAPH_PII_BODY_SCRUB`` blanks as ``"siteId"`` in bodies (the body regex
    # never runs on headers, so it survived here). The backend never reads it, so
    # drop the whole header rather than partially id-normalise it (BK-262 review).
    #
    # The trailing group are per-request correlation / diagnostic ids the backend
    # never reads: ``x-ms-request-id`` (the ESTS variant on ``login.microsoftonline.com``
    # responses that the ``request-id`` entry, no ``x-ms-`` prefix, missed — and
    # which the Azure profile already drops), ``x-ms-ests-server`` (ESTS
    # datacenter), and the SharePoint/CDN correlation ids ``sprequestguid`` /
    # ``splogid`` / ``ms-cv`` / ``x-msedge-ref`` on pre-signed-content responses.
    # None are credentials or account PII, but dropping them keeps cassette diffs
    # stable across re-records and matches the Azure profile's posture (BK-262
    # review). The transient ``innerError`` ``request-id`` / ``client-request-id``
    # GUIDs nested inside Graph error *bodies* are left as-is: they are not
    # identity/credential, and a JSON-body regex on those generic keys would add
    # matching surface for a churn-only gain.
    {
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
)
# Pre-signed download-URL query parameters. Consumer OneDrive uses
# ``tempauth`` / ``Expires``; SharePoint uses the SAS-style set already listed
# for Azure. ``access_token`` covers the rare in-query token form.
_GRAPH_SCRUB_QUERY_PARAMS: tuple[str, ...] = (*_SCRUB_QUERY_PARAMS, "tempauth", "Expires", "access_token")

# The pre-signed download token also rides the ``Location`` response header:
# ``GET /content`` answers ``302`` whose ``Location`` IS the
# ``@microsoft.graph.downloadUrl`` with the token in its query (spec 044
# GR-015). ``filter_query_parameters`` only touches request URIs, so the header
# is redacted here. The *whole query* is wiped value-based — mirroring the
# JSON-body downloadUrl scrub — rather than enumerating param names: the entire
# query of a downloadUrl is token machinery, so a novel/undocumented param name
# must not survive on the strength of not being in a list. Host + path are kept
# so the cassette stays reviewable.
_GRAPH_URL_QUERY_RE: re.Pattern[str] = re.compile(r"\?\S*")

# Hosts whose request URIs are preserved (id-normalised only): the Graph API and
# the MSAL token endpoint. Every *other* host a recording touches is a pre-signed
# content host — the ``@microsoft.graph.downloadUrl`` / ``uploadUrl`` CDN
# (consumer OneDrive) or the copy/move monitor URL — whose URI carries an access
# token. Those are rewritten wholesale to GRAPH_PRESIGNED_PLACEHOLDER below.
_GRAPH_API_HOSTS: tuple[str, ...] = ("graph.microsoft.com", "login.microsoftonline.com")

GRAPH_PRESIGNED_PLACEHOLDER = "https://graph-download.invalid/REDACTED"
"""Stable replacement for every pre-signed Graph URL in recorded cassettes.

A pre-signed URL (``@microsoft.graph.downloadUrl``, the upload-session
``uploadUrl``, the copy/move monitor URL) carries its own access token and must
not survive into a committed cassette. It is wiped to this one valid placeholder
in two coupled places so record and replay agree: the response-body value
(``_GRAPH_BODY_SCRUB``) and the request URI of any pre-signed-host request
(``before_record_request``). The ``.invalid`` TLD (RFC 6761) never resolves, so
the placeholder is obviously fake and non-routable; nothing of the live URL
(host, path, token) survives — strictly stronger redaction than the bare
``"REDACTED"`` token it replaces, which was not a URL and so broke replay
(the backend reads the value back out of the body and re-requests it).

``before_record_request`` runs in both record and replay mode, so the request
the backend issues on replay — built from the placeholder it read out of the
scrubbed body / ``Location`` header — normalises to the same value the recorded
request was rewritten to, and vcrpy matches them. This is the half that makes
Graph reads/writes/copies replay-able (BK-262).

Replay is order-dependent because every pre-signed interaction in a cassette
collapses to this one method+URI: vcrpy disambiguates the otherwise-identical
``GET https://graph-download.invalid/REDACTED`` entries (e.g. a copy cassette's
async monitor poll and its content download) solely by recorded order. That
holds for today's sequential conformance tests, but a backend change in
pre-signed call order/count (an extra poll, a retry, concurrent range reads)
will mis-serve or exhaust interactions with a confusing vcrpy mismatch rather
than an obvious one. Concurrent pre-signed requests within a single test are
unsupported under replay (BK-262 review)."""

_GRAPH_PRESIGNED_PLACEHOLDER_BYTES = GRAPH_PRESIGNED_PLACEHOLDER.encode()
_GRAPH_PRESIGNED_PLACEHOLDER_HOST = urlsplit(GRAPH_PRESIGNED_PLACEHOLDER).hostname or "graph-download.invalid"
"""Host of ``GRAPH_PRESIGNED_PLACEHOLDER`` (``graph-download.invalid``).

Written over the ``Host`` request header of any pre-signed-host request so the
live content host — generic ``my.microsoftpersonalcontent.com`` for consumer
OneDrive, but a tenant-identifying ``<tenant>-my.sharepoint.com`` on a business
drive — does not survive next to the redacted URI. vcrpy's default matcher
ignores ``Host``, so replay is unaffected.
"""


def _graph_is_presigned_host(uri: str) -> bool:
    """True when *uri*'s host is a pre-signed content host (not the Graph API / MSAL).

    A URI with no host (relative, or a bare token) is treated as *not* pre-signed
    so it is left for the normal id-normalisation path rather than being blanked —
    a defensive default that never over-redacts.
    """
    host = (urlsplit(uri).hostname or "").lower()
    if not host:
        return False
    return not any(host == h or host.endswith("." + h) for h in _GRAPH_API_HOSTS)


# Body-level redactions, applied in the bytes domain so binary payloads are
# safe. Each preserves surrounding JSON structure and replaces only the
# secret-bearing value. The ``uploadUrl`` returned by ``createUploadSession``
# is pre-authorised and carries its own token in the query (the same threat as
# ``downloadUrl``), so it is wiped alongside it — both to the placeholder URL so
# the value the backend reads back is a valid, replay-matchable URL.
_GRAPH_BODY_SCRUB: list[tuple[re.Pattern[bytes], bytes]] = [
    (
        re.compile(rb'("@microsoft\.graph\.downloadUrl"\s*:\s*")[^"]*(")'),
        rb"\1" + _GRAPH_PRESIGNED_PLACEHOLDER_BYTES + rb"\2",
    ),
    (re.compile(rb'("uploadUrl"\s*:\s*")[^"]*(")'), rb"\1" + _GRAPH_PRESIGNED_PLACEHOLDER_BYTES + rb"\2"),
    # The OAuth token-exchange response (``login.microsoftonline.com/.../token``)
    # is recorded whenever MSAL refreshes mid-suite (a warm in-memory cache hides
    # it, which is why earlier recordings happened to omit it). Beyond
    # ``access_token`` / ``refresh_token``, it carries an ``id_token`` (a JWT) and
    # ``client_info`` (base64) whose payloads embed the account email, display
    # name, tenant id, and an ``oid`` containing the drive cid — none caught by the
    # drive-id / email scrubs because they are base64-encoded. Redact all four
    # token-response fields wholesale (BK-262 review: the ``bare JWT`` marker
    # caught this on re-record). Replay never re-issues the token request — the
    # ``graph_replay`` backend uses a constant stub token — so the redacted value
    # is never parsed back.
    (re.compile(rb'("(?:access_token|refresh_token|id_token|client_info)"\s*:\s*")[^"]*(")'), rb"\1REDACTED\2"),
    (re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=\-]+"), b"Bearer REDACTED"),
]

# Identity / tenant PII redactions for response bodies. Graph item responses
# embed ``createdBy`` / ``lastModifiedBy`` user objects (real account email +
# display name) and a ``siteId`` (the personal-OneDrive site GUID); none of
# these are read by the backend or asserted by the conformance suite, so they
# can be blanked without breaking replay. Keys are matched whole (the opening
# quote is part of the match) so ``"displayName"`` is redacted while the
# load-bearing ``"name"`` item field — which the backend *does* read — is left
# untouched. The live ``drive_id`` (cid) embedded in item ids / eTags is handled
# separately by the case-insensitive ``real_drive_id`` rewrite, since Graph
# returns it upper-cased in those fields.
_GRAPH_PII_BODY_SCRUB: list[tuple[re.Pattern[bytes], bytes]] = [
    (
        re.compile(rb'("(?:email|displayName|userPrincipalName|loginName|siteId)"\s*:\s*")[^"]*(")'),
        rb"\1REDACTED\2",
    ),
]

# Per-test conformance-root normalisation (GR-058 isolation ↔ replay): rewrite
# the unique ``rs-conformance-<uuid>`` subfolder graph_live roots each test under
# back to the stable ``GRAPH_CONFORMANCE_BASE_PATH`` token, in both request URIs
# and request/response bodies (parentReference paths), so cassettes are
# reproducible on replay regardless of the random per-record uuid.
_GRAPH_CONFORMANCE_ROOT_RE_STR: re.Pattern[str] = re.compile(r"rs-conformance-[0-9a-f]+")
_GRAPH_CONFORMANCE_ROOT_RE_BYTES: re.Pattern[bytes] = re.compile(rb"rs-conformance-[0-9a-f]+")

# Request-body redactions for the OAuth token-exchange POST. MSAL sends this
# form-encoded over ``requests`` (which vcrpy also patches), so a recording made
# while the client-credentials / certificate / refresh flows acquire a token
# would otherwise capture the credential in the request body. The device-code
# flow carries none of these, but the app-only recipe shipped in graph-setup.md
# does — so the gate scrubs them rather than only covering the device-code path.
_GRAPH_REQUEST_BODY_SCRUB: list[tuple[re.Pattern[bytes], bytes]] = [
    (re.compile(rb"(client_secret=)[^&\r\n]+"), rb"\1REDACTED"),
    (re.compile(rb"(client_assertion=)[^&\r\n]+"), rb"\1REDACTED"),
    (re.compile(rb"(assertion=)[^&\r\n]+"), rb"\1REDACTED"),
    (re.compile(rb"(refresh_token=)[^&\r\n]+"), rb"\1REDACTED"),
]

# Env-independent "must never appear in a committed Graph cassette" markers. Each
# asserts a guarantee the scrub layer above is responsible for, so a re-record (or
# a hand edit / bad merge) cannot silently reintroduce the secret. The single
# source for two gates: the recorder's Step-4 scrub-verify (record_cassettes.py,
# live-creds path) AND a creds-free CI sweep over the committed tree
# (test_cassettes.py). Patterns are bytes and matched case-insensitively. They
# encode failure modes, not just leaks already found — the credential-form,
# tenant-host, identity-key, and JWT markers guard the surfaces a future scrub
# regression would expose (BK-262 review).
GRAPH_FORBIDDEN_CASSETTE_PATTERNS: tuple[tuple[str, bytes], ...] = (
    # A bearer token that did NOT get redacted to ``Bearer REDACTED``.
    ("bare bearer token", rb"Bearer (?!REDACTED)\S"),
    # Any JWT (access / id token) — base64url ``eyJ<header>.`` — regardless of the
    # surrounding key, so a token leaking outside an ``Authorization`` header is
    # still caught.
    ("bare JWT", rb"eyJ[A-Za-z0-9_-]{10,}\."),
    # The pre-signed-content ``docID`` header carries the OneDrive site-collection
    # GUID as ``...content.com_<site-guid>_<doc-guid>``.
    ("pre-signed docID / site GUID", rb"microsoftpersonalcontent\.com_[0-9a-fA-F-]{36}_"),
    # A business-drive / SharePoint pre-signed content host is tenant-identifying
    # (``<tenant>-my.sharepoint.com``); the placeholder must have replaced it.
    # Consumer recordings never contain ``sharepoint.com``, so any hit is a leak.
    ("tenant SharePoint host", rb"-my\.sharepoint\.com"),
    # The long ``b!…`` drive resource id (the cid's full form).
    ("long b! drive id", rb"b![A-Za-z0-9_-]{20,}"),
    # OAuth credential form fields that escaped ``_GRAPH_REQUEST_BODY_SCRUB`` (e.g.
    # a token exchange against an auth host outside ``_GRAPH_API_HOSTS``).
    ("unredacted client_secret", rb"client_secret=(?!REDACTED)"),
    ("unredacted refresh_token", rb"refresh_token=(?!REDACTED)"),
    ("unredacted assertion", rb"(?:client_)?assertion=(?!REDACTED)"),
    # Identity keys that escaped ``_GRAPH_PII_BODY_SCRUB`` (the one fixed class
    # with no env-independent marker until now).
    ("unredacted identity key", rb'"(?:email|userPrincipalName)"\s*:\s*"(?!REDACTED)'),
    # A bare email address anywhere in the tree (account PII).
    ("bare email address", rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


# ---------------------------------------------------------------------------
# Connection-string helpers
# ---------------------------------------------------------------------------


def parse_account_name(conn_str: str) -> str:
    """Extract the ``AccountName`` value from a connection string."""
    for part in conn_str.split(";"):
        if part.strip().lower().startswith("accountname="):
            return part.split("=", 1)[1].strip()
    raise ValueError(f"connection string has no AccountName= segment: {conn_str!r}")


# Azurite-detection fragments (mirrors ``_live_env.py``).
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")


def live_connection_string() -> str:
    """Return a real ADLS Gen2 connection string for recording mode.

    Fails loud when ``RS_TEST_LIVE_HNS`` is absent, the connection string
    is missing, or it points at Azurite.  Mirrors the fail-loud convention
    in ``tests/backends/fixtures/_live_env.py``.
    """
    import pytest  # noqa: PLC0415 -- lazy: only on the record path
    from dotenv import load_dotenv  # noqa: PLC0415 -- lazy: only on the record path

    load_dotenv(override=False)
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.fail("recording requires RS_TEST_LIVE_HNS=1 (a real ADLS Gen2 account)")
    conn = (os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    if not conn:
        pytest.fail("recording requires AZURE_STORAGE_CONNECTION_STRING (a real ADLS Gen2 account)")
    if any(frag in conn for frag in _AZURITE_FRAGMENTS):
        pytest.fail("AZURE_STORAGE_CONNECTION_STRING points at Azurite; recording needs a real HNS account")
    return conn


# ---------------------------------------------------------------------------
# Scrubbing layer (vcrpy configuration factory)
# ---------------------------------------------------------------------------


def build_vcr_config(real_account: str | None) -> dict[str, Any]:
    """Return a ``vcr_config`` dict for the conformance conftest fixture.

    ``real_account`` is the storage account name extracted from the live
    connection string (record mode) or ``None`` (replay mode).  The
    ``before_record_*`` hooks apply in both modes — vcrpy normalises
    outgoing requests for matching against the cassette even during replay,
    so the ``if real:`` guards below are load-bearing on the replay path.

    Additions over the PoC scrubbing layer:

    * Filesystem-UUID rewrite: ``conformance-<uuid8>`` → ``FAKE_FILESYSTEM``
      so live and replay fixtures share cassette URLs (plan challenge 2).
    * Temp-file UUID normalisation: ``write_atomic`` appends a random 8-char
      hex UUID to temp filenames (``_TMP_UUID_PATTERN``); normalising it out
      keeps the cassette path deterministic across record and replay runs.
    * ``x-ms-rename-source`` / ``x-ms-copy-source`` header scrubbing: the live
      account name and container name leak into these headers during move/copy
      operations; both are replaced with ``FAKE_ACCOUNT`` / ``FAKE_FILESYSTEM``.
    * Body-level ``RequestId:`` / ``Time:`` scrub for error-response XML
      (PoC gap; cosmetic but keeps cassette diffs clean).
    * Binary-safe bytes handling: ``before_record_response`` operates on bytes
      directly (using ``_FILESYSTEM_PATTERN_BYTES``) rather than decoding the
      body as UTF-8, which would crash on raw binary payloads (e.g. ``\\xff``).
    * ``User-Agent`` normalisation to ``azsdk-python-replay`` so recording
      machine Python/OS details don't appear in committed cassettes.
    """

    def before_record_request(request: Any) -> Any:
        if real_account:
            request.uri = request.uri.replace(real_account, FAKE_ACCOUNT)
            request.uri = _FILESYSTEM_PATTERN.sub(FAKE_FILESYSTEM, request.uri)
        # Normalise the 8-char hex UUID in atomic write temp-file paths so the
        # cassette path is deterministic across record and replay runs.
        request.uri = _TMP_UUID_PATTERN.sub(r"\1", request.uri)
        for key in list(request.headers):
            lower = key.lower()
            if lower in _SCRUB_REQUEST_HEADERS:
                del request.headers[key]
            elif lower == "user-agent":
                request.headers[key] = _USER_AGENT_NORMALIZED
            elif lower in ("x-ms-rename-source", "x-ms-copy-source"):
                # These headers carry live account name and container; scrub both.
                # Also normalise write_atomic temp-file UUIDs so re-records don't
                # churn the header value unnecessarily.
                val = request.headers[key]
                if real_account:
                    val = val.replace(real_account, FAKE_ACCOUNT)
                val = _FILESYSTEM_PATTERN.sub(FAKE_FILESYSTEM, val)
                request.headers[key] = _TMP_UUID_PATTERN.sub(r"\1", val)
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            lower = key.lower()
            if lower in _SCRUB_RESPONSE_HEADERS:
                del headers[key]
            elif lower == "x-ms-copy-source":
                # Azure echoes the copy-source URL back in the response;
                # apply the same account/filesystem replacement as on the request.
                val = headers[key]
                if isinstance(val, list):
                    val = [
                        _FILESYSTEM_PATTERN.sub(
                            FAKE_FILESYSTEM,
                            (v.replace(real_account, FAKE_ACCOUNT) if real_account else v),
                        )
                        for v in val
                    ]
                else:
                    if real_account:
                        val = val.replace(real_account, FAKE_ACCOUNT)
                    val = _FILESYSTEM_PATTERN.sub(FAKE_FILESYSTEM, val)
                headers[key] = val
        body = response.get("body", {})
        raw = body.get("string")
        if real_account:
            if isinstance(raw, bytes):
                # Stay in bytes throughout — don't decode() binary bodies.
                raw = raw.replace(real_account.encode(), FAKE_ACCOUNT.encode())
                raw = _FILESYSTEM_PATTERN_BYTES.sub(FAKE_FILESYSTEM.encode(), raw)
            elif isinstance(raw, str):
                raw = raw.replace(real_account, FAKE_ACCOUNT)
                raw = _FILESYSTEM_PATTERN.sub(FAKE_FILESYSTEM, raw)
        # Body-level scrub for error-response XML (both paths).
        if isinstance(raw, bytes):
            for pattern, replacement in _BODY_SCRUB:
                raw = pattern.sub(replacement, raw)
            body["string"] = raw
        elif isinstance(raw, str):
            raw_b = raw.encode()
            for pattern, replacement in _BODY_SCRUB:
                raw_b = pattern.sub(replacement, raw_b)
            body["string"] = raw_b.decode()
        return response

    return {
        # Decoded bodies keep cassettes diff-reviewable (TEST-009) and let
        # the response-body scrub above run against plain text.
        "decode_compressed_response": True,
        "filter_query_parameters": list(_SCRUB_QUERY_PARAMS),
        "before_record_request": before_record_request,
        "before_record_response": before_record_response,
        # Default match_on (method, scheme, host, port, path, query) is
        # sufficient: SharedKey auth keeps signatures in the Authorization
        # header (scrubbed, unmatched); x-ms-client-request-id is a header.
    }


def build_graph_vcr_config(real_drive_id: str | None) -> dict[str, Any]:
    """Return a ``vcr_config`` dict for recording/replaying Microsoft Graph.

    ``real_drive_id`` is the live drive id (record mode) or ``None`` (replay
    mode). The ``before_record_*`` hooks run in both modes because vcrpy
    normalises outgoing requests for matching during replay too, so the
    ``if real_drive_id:`` guards are load-bearing on the replay path.

    What it strips (the GR-FOUNDATION security gate, GR-035 / TEST-007):

    * ``Authorization`` (the bearer token), ``Cookie``, and the
      ``client-request-id`` correlation header from requests;
    * the OAuth credentials (``client_secret`` / ``client_assertion`` /
      ``assertion`` / ``refresh_token``) from the token-exchange **request**
      body — MSAL sends these form-encoded over ``requests``, which vcrpy
      records too (the app-only recording path; the device-code path carries
      none of them);
    * ``request-id`` / ``client-request-id`` / ``x-ms-ags-diagnostic`` /
      ``Set-Cookie`` / ``Date`` from responses;
    * the pre-signed download token from the ``Location`` /
      ``Content-Location`` response header — the ``302`` from ``GET /content``
      redirects to ``@microsoft.graph.downloadUrl`` (GR-015); its **whole
      query** is wiped (value-based, like the body scrub) so no token survives,
      named or not;
    * the ``@microsoft.graph.downloadUrl`` value, the upload-session
      ``uploadUrl`` value (pre-authorised, token in its query), and any
      ``Bearer`` / ``access_token`` / ``refresh_token`` / ``id_token`` /
      ``client_info`` from response bodies (the last two carry the base64-encoded
      account identity in the OAuth token-exchange response);
    * the pre-signed download query parameters;
    * the live ``drive_id`` (rewritten to ``FAKE_DRIVE_ID``) from request
      URIs and response bodies, so a cassette recorded against a real drive
      replays against the fake one — matched **case-insensitively** because
      Graph echoes the id (cid) upper-cased inside item ids / eTags / webUrls
      but lower-cased in URIs; and
    * the account identity and tenant PII Graph embeds in item responses —
      ``email`` / ``displayName`` / ``userPrincipalName`` / ``loginName`` (the
      ``createdBy`` / ``lastModifiedBy`` user objects) and ``siteId`` (the
      personal-OneDrive site GUID) — none of which the backend reads or the
      conformance suite asserts.
    """

    # The drive_id (cid) is rewritten case-insensitively: Graph echoes it
    # lower-cased in URIs / parentReference paths but UPPER-cased inside item
    # ids, eTags, cTags, and webUrls (``4FDE...!s<hex>``). A plain ``.replace``
    # of the lower-cased env value misses the upper-cased copies, leaking the
    # real resource id. One case-insensitive pattern catches every casing and
    # maps them all to the same ``FAKE_DRIVE_ID`` so eTag/id self-comparisons
    # within a cassette still match.
    _drive_id_re_str = re.compile(re.escape(real_drive_id), re.IGNORECASE) if real_drive_id else None
    _drive_id_re_bytes = re.compile(re.escape(real_drive_id.encode()), re.IGNORECASE) if real_drive_id else None

    def _scrub_location(val: str) -> str:
        """Redact a ``Location`` / ``Content-Location`` response-header URL.

        A pre-signed-host Location — the ``302`` from ``GET /content`` pointing
        at ``@microsoft.graph.downloadUrl`` (GR-015), or the ``202`` async
        copy/move monitor URL — collapses to ``GRAPH_PRESIGNED_PLACEHOLDER``,
        the same value its request URI and body twin are rewritten to. This
        removes not only the query token but the drive id (the cid and the long
        ``b!…`` form) Graph embeds in the *path* of a consumer-OneDrive
        pre-signed URL (``/personal/<cid>/_api/v2.0/drives/b!…``) — a path the
        old query-only wipe left intact (BK-262). It stays replay-able because
        ``before_record_request`` rewrites the poll/download request the backend
        issues from this header to the same placeholder, so vcrpy matches.

        A Graph-API-host Location (e.g. a ``201 Created`` item URL the backend
        never re-requests) keeps its host + path for review: the token query is
        wiped value-based and the drive id in the path is id-normalised.
        """
        if _graph_is_presigned_host(val):
            return GRAPH_PRESIGNED_PLACEHOLDER
        val = _GRAPH_URL_QUERY_RE.sub("?REDACTED", val)
        if _drive_id_re_str is not None:
            val = _drive_id_re_str.sub(FAKE_DRIVE_ID, val)
        return _GRAPH_CONFORMANCE_ROOT_RE_STR.sub(GRAPH_CONFORMANCE_BASE_PATH, val)

    def _scrub_request_headers(request: Any) -> None:
        for key in list(request.headers):
            lower = key.lower()
            if lower in _GRAPH_SCRUB_REQUEST_HEADERS:
                del request.headers[key]
            elif lower == "user-agent":
                request.headers[key] = _USER_AGENT_NORMALIZED

    def before_record_request(request: Any) -> Any:
        # A pre-signed content host (downloadUrl / uploadUrl / copy-move monitor
        # URL) carries an access token in its URI, so the whole URI is replaced
        # with the stable placeholder. This runs in both record and replay mode:
        # the request the backend issues on replay — built from the placeholder it
        # read out of the scrubbed response body / Location header — normalises to
        # the same value the recorded request was rewritten to, so vcrpy matches
        # them.
        if _graph_is_presigned_host(request.uri):
            request.uri = GRAPH_PRESIGNED_PLACEHOLDER
            _scrub_request_headers(request)
            # The Host header still names the live pre-signed content host (the
            # placeholder guarantees *nothing* of the live URL survives), so
            # rewrite it to the placeholder host. Generic for consumer OneDrive,
            # but tenant-identifying (``<tenant>-my.sharepoint.com``) on a
            # business drive (BK-262 review).
            for key in list(request.headers):
                if key.lower() == "host":
                    request.headers[key] = _GRAPH_PRESIGNED_PLACEHOLDER_HOST
            # Defense-in-depth on the body: a pre-signed request body is normally
            # opaque content (an upload chunk), but an OAuth token exchange against
            # an auth host *outside* ``_GRAPH_API_HOSTS`` (``login.live.com``, a
            # sovereign-cloud endpoint) lands in this branch too — so run the
            # credential-form scrub before recording. A no-op on an upload chunk
            # (no ``client_secret=`` / ``assertion=`` / ``refresh_token=`` bytes).
            body = getattr(request, "body", None)
            if isinstance(body, (str, bytes)):
                raw = body.encode() if isinstance(body, str) else body
                for pattern, replacement in _GRAPH_REQUEST_BODY_SCRUB:
                    raw = pattern.sub(replacement, raw)
                request.body = raw.decode() if isinstance(body, str) else raw
            return request
        if _drive_id_re_str is not None:
            request.uri = _drive_id_re_str.sub(FAKE_DRIVE_ID, request.uri)
        # Normalise the per-test base_path uuid to the stable replay token so the
        # recorded URI matches graph_replay's fixed base_path (runs in both modes).
        request.uri = _GRAPH_CONFORMANCE_ROOT_RE_STR.sub(GRAPH_CONFORMANCE_BASE_PATH, request.uri)
        _scrub_request_headers(request)
        # Scrub credentials out of the OAuth token-exchange POST body (login host).
        # The bytes-domain sub is a no-op on the device-code flow (no secret present).
        body = getattr(request, "body", None)
        if isinstance(body, (str, bytes)):
            raw = body.encode() if isinstance(body, str) else body
            for pattern, replacement in _GRAPH_REQUEST_BODY_SCRUB:
                raw = pattern.sub(replacement, raw)
            # The move/copy parentReference body carries the live drive_id (driveId
            # field + a /drives/{drive_id}/root: path), so the URI replace above is
            # not enough — rewrite it in the request body too (mirrors the response).
            if _drive_id_re_bytes is not None:
                raw = _drive_id_re_bytes.sub(FAKE_DRIVE_ID.encode(), raw)
            raw = _GRAPH_CONFORMANCE_ROOT_RE_BYTES.sub(GRAPH_CONFORMANCE_BASE_PATH.encode(), raw)
            request.body = raw.decode() if isinstance(body, str) else raw
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            lower = key.lower()
            if lower in _GRAPH_SCRUB_RESPONSE_HEADERS:
                del headers[key]
            elif lower in ("location", "content-location"):
                val = headers[key]
                if isinstance(val, list):
                    headers[key] = [_scrub_location(v) if isinstance(v, str) else v for v in val]
                elif isinstance(val, str):
                    headers[key] = _scrub_location(val)
        body = response.get("body", {})
        raw = body.get("string")
        if isinstance(raw, str):
            raw = raw.encode()
            was_str = True
        else:
            was_str = False
        if isinstance(raw, bytes):
            if _drive_id_re_bytes is not None:
                raw = _drive_id_re_bytes.sub(FAKE_DRIVE_ID.encode(), raw)
            for pattern, replacement in (*_GRAPH_BODY_SCRUB, *_GRAPH_PII_BODY_SCRUB):
                raw = pattern.sub(replacement, raw)
            raw = _GRAPH_CONFORMANCE_ROOT_RE_BYTES.sub(GRAPH_CONFORMANCE_BASE_PATH.encode(), raw)
            body["string"] = raw.decode() if was_str else raw
        return response

    return {
        "decode_compressed_response": True,
        "filter_query_parameters": list(_GRAPH_SCRUB_QUERY_PARAMS),
        "before_record_request": before_record_request,
        "before_record_response": before_record_response,
    }


__all__ = [
    "CASSETTE_DIR_AZURE",
    "CASSETTE_DIR_GRAPH",
    "FAKE_ACCOUNT",
    "FAKE_CONN_STR",
    "FAKE_DRIVE_ID",
    "FAKE_FILESYSTEM",
    "GRAPH_CONFORMANCE_BASE_PATH",
    "GRAPH_FORBIDDEN_CASSETTE_PATTERNS",
    "GRAPH_PRESIGNED_PLACEHOLDER",
    "build_graph_vcr_config",
    "build_vcr_config",
    "live_connection_string",
    "parse_account_name",
]
