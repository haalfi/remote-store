"""Azure Storage cassette profile: scrub declarations and replay identifiers.

Declares ``AZURE_PROFILE`` — the ``CassetteProfile`` shared by the
``azure_live*`` (record) and ``azure_replay*`` (playback) fixtures — plus
the fixed identifiers the replay fixtures build their backend from and the
account-name resolution the record-time scrub keys on. Credential
validation for the record path lives in ``_live_env``, not here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tests.backends.fixtures._cassettes import (
    CassetteProfile,
    EnvRedact,
    RedactPattern,
    UriRewrite,
)

CASSETTE_DIR_AZURE: Path = Path(__file__).resolve().parent.parent / "cassettes" / "azure"
"""Absolute path to ``tests/backends/cassettes/azure/`` (TEST-007)."""

# region: fixed replay identifiers

FAKE_ACCOUNT = "azreplay"
"""Placeholder account name written into every recorded cassette URL.

The replay fixtures build the backend from a connection string naming this
same account so that the host in every outgoing request matches the cassette.
Not a secret — just a well-formed DNS label. The value is recorded in every
committed cassette, so changing it is a corpus-wide rewrite.
"""

FAKE_FILESYSTEM = "conformance-azure-replay"
"""Fixed filesystem (container) name used by replay fixtures.

Live fixtures mint a per-call ``conformance-<uuid>``; the scrub layer
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

REPLAY_HNS_DIRPATH_SYNC = "live-hns/REPLAY/dirblob"
"""Fixed HNS directory path the sync replay fixture targets (BK-303).

The live HNS fixture provisions ``live-hns/<uuid8>/dirblob``; the
``azure.uri.hns-prefix`` scrub rewrites the per-session uuid to ``REPLAY``
so the replay fixture (which does no HTTP at setup) replays cassette URLs
that match this fixed path.
"""

REPLAY_HNS_DIRPATH_ASYNC = "live-hns-async/REPLAY/dirblob"
"""Fixed HNS directory path the async replay fixture targets (BK-303)."""

LIVE_HNS_ROOT_FS = "rs-hns-root-probe"
"""Dedicated, persistent, empty HNS filesystem for the root ``get_folder_info("")`` tests (BK-303).

``get_folder_info("")`` enumerates the *whole* container root recursively, so
recording it against the shared ``RS_TEST_LIVE_HNS_CONTAINER`` baked the
container's mutable top-level inventory into the cassette — non-reproducible on
re-record and an unbounded residue surface. The root tests instead target this
dedicated filesystem, which the azure-subtree conftests create empty (and never
write to), so its root listing is a deterministic ``{"paths":[]}``. The name is
not a secret, but it is scrubbed to ``FAKE_FILESYSTEM`` (``azure.uri.root-fs``)
so the replay fixtures — which target ``FAKE_FILESYSTEM`` — match the cassette.
"""

# endregion

# region: account-name resolution (record path)


def parse_account_name(conn_str: str) -> str:
    """Extract the ``AccountName`` value from a connection string."""
    for part in conn_str.split(";"):
        if part.strip().lower().startswith("accountname="):
            return part.split("=", 1)[1].strip()
    raise ValueError(f"connection string has no AccountName= segment: {conn_str!r}")


# Azurite-detection fragments (mirrors ``_live_env.py``).
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")


def _resolve_live_account() -> str | None:
    """``EnvRedact`` resolver: the real account name, or ``None`` (rule disabled).

    ``None`` covers every no-live-account state: an unset or blank
    connection string, or one pointing at Azurite (whose well-known
    ``devstoreaccount1`` is not a secret). Credential presence for a record
    run is enforced fail-loud by the live fixtures via
    ``_live_env.require_azure_live_connection_string``, not here, and the
    recorder's named-rule audit backstops a full record run whose
    required ``azure.account`` rule never fired.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 -- lazy: only on the record path

    load_dotenv(override=False)
    conn = (os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    if not conn or any(frag in conn for frag in _AZURITE_FRAGMENTS):
        return None
    return parse_account_name(conn)


def _resolve_live_hns_container() -> str | None:
    """``EnvRedact`` resolver: the real HNS filesystem name, or ``None`` (rule disabled).

    The live HNS deviation suite targets a persistent, account-specific
    filesystem named by ``RS_TEST_LIVE_HNS_CONTAINER`` (BK-303). Unlike the
    conformance suite's minted ``conformance-<uuid8>`` names — covered by
    ``_FILESYSTEM_PATTERN`` — this fixed name does not match a uuid pattern,
    so it gets its own env-redact to ``FAKE_FILESYSTEM``. ``None`` covers the
    no-live state (env var unset), so a normal offline run is unaffected.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 -- lazy: only on the record path

    load_dotenv(override=False)
    container = (os.environ.get("RS_TEST_LIVE_HNS_CONTAINER") or "").strip()
    return container or None


# endregion

# region: scrub patterns

# Matches both ``conformance-12ab34cd`` (sync live) and
# ``conformance-async-12ab34cd`` (async live); replaced with FAKE_FILESYSTEM
# so live and replay fixtures share cassette URLs.
_FILESYSTEM_PATTERN: re.Pattern[str] = re.compile(r"conformance(?:-async)?-[0-9a-f]{8}")

# Matches the 8-char hex UUID suffix that write_atomic appends to temp files
# (``.~tmp.{basename}.{uuid8}``). The suffix differs between record and
# replay runs, so it is normalised out for a deterministic cassette path.
_TMP_UUID_PATTERN: re.Pattern[str] = re.compile(r"(\.~tmp\.[^?/]*)\.[0-9a-f]{8}(?=[?/]|$)")

# Matches the per-session prefix the live HNS suite provisions:
# ``live-hns/<uuid8>`` (sync) and ``live-hns-async/<uuid8>`` (async). The uuid
# differs between record and replay runs, so it is normalised to ``REPLAY``
# (the fixed segment the replay fixtures' dirpath uses) for a deterministic
# cassette path (BK-303).
_HNS_PREFIX_PATTERN: re.Pattern[str] = re.compile(r"(live-hns(?:-async)?)/[0-9a-f]{8}")

# endregion

AZURE_PROFILE = CassetteProfile(
    backend="azure",
    cassette_dir=CASSETTE_DIR_AZURE,
    fixture_aliases={
        "azure_live": "azure",
        "azure_replay": "azure",
        "azure_live_async": "azure_async",
        "azure_replay_async": "azure_async",
        # BK-303: the live HNS deviation suite and its replay tier share a
        # cassette file under the same cassettes/azure/ directory; a distinct
        # alias group keeps their filenames separate from conformance.
        "azure_live_hns": "azure_hns",
        "azure_replay_hns": "azure_hns",
        "azure_live_hns_async": "azure_hns_async",
        "azure_replay_hns_async": "azure_hns_async",
    },
    # SharedKey auth keeps its signature in the deleted headers; the
    # ``User-Agent`` tuple rewrites the recording machine's SDK/Python/OS
    # string to a stable value (capitalised key: the case cassettes record).
    filter_headers=(
        "authorization",
        "x-ms-date",
        "x-ms-client-request-id",
        "cookie",
        ("User-Agent", "azsdk-python-replay"),
    ),
    # SAS-token parameters. SharedKey auth keeps its signature in headers, so
    # these are zero-hit on today's recordings; listed so any future
    # SAS-authenticated fixture inherits the scrub.
    filter_query_parameters=("sig", "se", "st", "sp", "sv", "sr", "skoid", "sktid", "skt", "ske", "sks", "skv"),
    env_redacts=(
        EnvRedact(name="azure.account", resolve=_resolve_live_account, fake=FAKE_ACCOUNT),
        # BK-303: the live HNS suite targets a fixed RS_TEST_LIVE_HNS_CONTAINER
        # filesystem whose name is not a conformance-<uuid8> form; redact it to
        # FAKE_FILESYSTEM so HNS replay runs against container=FAKE_FILESYSTEM.
        # required-to-fire: it fires on every HNS recording (folded into the
        # azure record run), so a zero-fire is a wiring defect.
        EnvRedact(name="azure.hns-container", resolve=_resolve_live_hns_container, fake=FAKE_FILESYSTEM),
    ),
    uri_rewrites=(
        UriRewrite(
            name="azure.uri.filesystem-uuid",
            pattern=_FILESYSTEM_PATTERN,
            replacement=FAKE_FILESYSTEM,
            expectation="required-to-fire",
        ),
        UriRewrite(name="azure.uri.tmp-uuid", pattern=_TMP_UUID_PATTERN, replacement=r"\1"),
        # BK-303: normalise the live HNS per-session prefix uuid to REPLAY.
        UriRewrite(
            name="azure.uri.hns-prefix",
            pattern=_HNS_PREFIX_PATTERN,
            replacement=r"\1/REPLAY",
            expectation="required-to-fire",
        ),
        # BK-303: the root get_folder_info tests target a dedicated empty
        # filesystem (LIVE_HNS_ROOT_FS) so the recorded root listing is
        # residue-free; rewrite its name to FAKE_FILESYSTEM so replay (which
        # targets FAKE_FILESYSTEM) matches. required-to-fire: the root tests
        # always record on a full run, so a zero-fire means the rule drifted
        # from the probe filesystem name.
        UriRewrite(
            name="azure.uri.root-fs",
            pattern=re.compile(re.escape(LIVE_HNS_ROOT_FS)),
            replacement=FAKE_FILESYSTEM,
            expectation="required-to-fire",
        ),
    ),
    response_body_redactions=(
        # Opportunistic: the recorded corpus shows response bodies never carry
        # the filesystem name (URIs do — that is the required uri rule above).
        RedactPattern(
            name="azure.body.filesystem-uuid",
            pattern=re.compile(_FILESYSTEM_PATTERN.pattern.encode()),
            replacement=FAKE_FILESYSTEM.encode(),
        ),
        # BK-303: bytes twin of azure.uri.hns-prefix — get_paths listing
        # responses echo child paths carrying the per-session prefix uuid.
        # Opportunistic: not every HNS cassette lists the directory.
        RedactPattern(
            name="azure.body.hns-prefix",
            pattern=re.compile(rb"(live-hns(?:-async)?)/[0-9a-f]{8}"),
            replacement=rb"\1/REPLAY",
        ),
        # BK-303: bytes twin of azure.uri.root-fs. Opportunistic: the empty
        # probe filesystem's root listing is {"paths":[]} (no name), but an
        # error response could echo the filesystem name in its body.
        RedactPattern(
            name="azure.body.root-fs",
            pattern=re.compile(re.escape(LIVE_HNS_ROOT_FS.encode())),
            replacement=FAKE_FILESYSTEM.encode(),
        ),
        # Error-response XML fragments carrying per-run identifiers.
        RedactPattern(
            name="azure.body.request-id",
            pattern=re.compile(rb"RequestId:[0-9a-f-]+"),
            replacement=b"RequestId:SCRUBBED",
        ),
        RedactPattern(
            name="azure.body.time",
            pattern=re.compile(rb"Time:\d{4}-\d{2}-\d{2}T[^<\"&\r\n]+"),
            replacement=b"Time:SCRUBBED",
        ),
    ),
    response_header_deletes=frozenset(
        {"x-ms-request-id", "x-ms-client-request-id", "x-ms-correlation-request-id", "set-cookie", "date"}
    ),
    # Azure echoes the copy-source URL (live account + container) back in the
    # response; same env-redact + rewrite chain as the request side.
    rewrite_response_headers=("x-ms-copy-source",),
)
"""The Azure Storage scrub profile (spec 049).

What it strips: the SharedKey ``Authorization`` / ``x-ms-date`` /
correlation / ``Cookie`` request headers and SAS query parameters (native
filters); the live account name, the per-call ``conformance-<uuid>``
filesystem name, and the live HNS suite's ``RS_TEST_LIVE_HNS_CONTAINER``
filesystem name (and the dedicated ``LIVE_HNS_ROOT_FS`` probe filesystem)
from URIs, header values (``x-ms-rename-source`` / ``x-ms-copy-source``),
and bodies; the random ``write_atomic`` temp-file UUID and the live HNS
per-session ``live-hns/<uuid>`` prefix; per-request response headers; and
``RequestId:`` / ``Time:`` fragments in error-response XML.
"""

__all__ = [
    "AZURE_PROFILE",
    "CASSETTE_DIR_AZURE",
    "FAKE_ACCOUNT",
    "FAKE_CONN_STR",
    "FAKE_FILESYSTEM",
    "LIVE_HNS_ROOT_FS",
    "REPLAY_HNS_DIRPATH_ASYNC",
    "REPLAY_HNS_DIRPATH_SYNC",
    "parse_account_name",
]
