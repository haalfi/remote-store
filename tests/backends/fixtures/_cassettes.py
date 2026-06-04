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

_GRAPH_SCRUB_REQUEST_HEADERS: frozenset[str] = frozenset({"authorization", "cookie", "client-request-id"})
_GRAPH_SCRUB_RESPONSE_HEADERS: frozenset[str] = frozenset(
    {"request-id", "client-request-id", "x-ms-ags-diagnostic", "set-cookie", "date"}
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

# Body-level redactions, applied in the bytes domain so binary payloads are
# safe. Each preserves surrounding JSON structure and replaces only the
# secret-bearing value.
_GRAPH_BODY_SCRUB: list[tuple[re.Pattern[bytes], bytes]] = [
    (re.compile(rb'("@microsoft\.graph\.downloadUrl"\s*:\s*")[^"]*(")'), rb"\1REDACTED\2"),
    (re.compile(rb'("(?:access_token|refresh_token)"\s*:\s*")[^"]*(")'), rb"\1REDACTED\2"),
    (re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=\-]+"), b"Bearer REDACTED"),
]

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
    * the ``@microsoft.graph.downloadUrl`` value and any
      ``Bearer`` / ``access_token`` / ``refresh_token`` from response bodies;
    * the pre-signed download query parameters; and
    * the live ``drive_id`` (rewritten to ``FAKE_DRIVE_ID``) from request
      URIs and response bodies, so a cassette recorded against a real drive
      replays against the fake one.
    """

    def before_record_request(request: Any) -> Any:
        if real_drive_id:
            request.uri = request.uri.replace(real_drive_id, FAKE_DRIVE_ID)
        for key in list(request.headers):
            lower = key.lower()
            if lower in _GRAPH_SCRUB_REQUEST_HEADERS:
                del request.headers[key]
            elif lower == "user-agent":
                request.headers[key] = _USER_AGENT_NORMALIZED
        # Scrub credentials out of the OAuth token-exchange POST body. The
        # bytes-domain sub is a no-op on binary upload payloads (no form keys
        # match) and on the device-code flow (no secret present).
        body = getattr(request, "body", None)
        if isinstance(body, (str, bytes)):
            raw = body.encode() if isinstance(body, str) else body
            for pattern, replacement in _GRAPH_REQUEST_BODY_SCRUB:
                raw = pattern.sub(replacement, raw)
            request.body = raw.decode() if isinstance(body, str) else raw
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            lower = key.lower()
            if lower in _GRAPH_SCRUB_RESPONSE_HEADERS:
                del headers[key]
            elif lower in ("location", "content-location"):
                # The 302 from GET /content carries the pre-signed download
                # token in the Location query (GR-015); wipe the whole query,
                # keeping host/path so the cassette stays reviewable.
                val = headers[key]
                if isinstance(val, list):
                    headers[key] = [_GRAPH_URL_QUERY_RE.sub("?REDACTED", v) if isinstance(v, str) else v for v in val]
                elif isinstance(val, str):
                    headers[key] = _GRAPH_URL_QUERY_RE.sub("?REDACTED", val)
        body = response.get("body", {})
        raw = body.get("string")
        if isinstance(raw, str):
            raw = raw.encode()
            was_str = True
        else:
            was_str = False
        if isinstance(raw, bytes):
            if real_drive_id:
                raw = raw.replace(real_drive_id.encode(), FAKE_DRIVE_ID.encode())
            for pattern, replacement in _GRAPH_BODY_SCRUB:
                raw = pattern.sub(replacement, raw)
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
    "build_graph_vcr_config",
    "build_vcr_config",
    "live_connection_string",
    "parse_account_name",
]
