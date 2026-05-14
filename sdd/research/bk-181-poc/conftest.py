"""pytest-recording / vcrpy wiring for the BK-181 cassette-replay PoC.

This conftest is loaded **only** when pytest is pointed explicitly at
``sdd/research/bk-181-poc/`` -- the folder sits outside ``testpaths`` in
``pyproject.toml``, so a normal ``hatch run test`` never touches it.

What it provides:

* ``vcr_config`` -- the scrubbing layer. Drops credential headers, rewrites
  the real storage-account name out of every URL and response body, and
  decodes compressed responses so cassettes are reviewable.
* ``azure_conn_str`` -- the record/replay switch. Recording uses the real
  ADLS Gen2 connection string from ``.env`` (fail-loud); replaying uses a
  fixed *fake* connection string and never touches the network.
* ``azure_backend`` / ``async_azure_backend`` -- a real ``AzureBackend`` /
  ``AsyncAzureBackend`` against the fixed ``bk181poc`` filesystem.
* ``hns_directory`` -- a factory that materialises a real HNS directory
  blob (``hdi_isfolder=true``), the marker Azurite cannot emulate.
* ``pytest_collection_modifyitems`` -- TEST-007: a missing replay cassette
  *skips* the test, it does not fail.

See ``README.md`` for how to record and replay.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

# ---------------------------------------------------------------------------
# Fixed identifiers
# ---------------------------------------------------------------------------
# A *deterministic* filesystem name. The live registry fixtures mint a
# per-call ``conformance-<uuid>`` (tests/backends/fixtures/azure_live.py:77);
# that uuid would land in every request URL and break cassette matching on
# replay. A fixed name is PoC success criterion 5.
CONTAINER = "bk181poc"

# The placeholder account every recorded request/response is rewritten to.
# Replay builds the backend from a connection string naming this same
# account, so the URL host in the live traffic matches the cassette.
FAKE_ACCOUNT = "bk181poc"

# Azurite's well-known emulator key: valid base64 (so ``from_connection_string``
# and the SharedKey signer accept it), publicly documented, not a secret.
_FAKE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
FAKE_CONN_STR = (
    f"DefaultEndpointsProtocol=https;AccountName={FAKE_ACCOUNT};AccountKey={_FAKE_KEY};EndpointSuffix=core.windows.net"
)

# Request headers dropped from every recorded interaction.
_SCRUB_REQUEST_HEADERS = frozenset({"authorization", "x-ms-date", "x-ms-client-request-id", "cookie"})
# Response headers dropped from every recorded interaction.
_SCRUB_RESPONSE_HEADERS = frozenset(
    {"x-ms-request-id", "x-ms-client-request-id", "x-ms-correlation-request-id", "set-cookie", "date"}
)
# SAS-token query parameters. SharedKey auth (connection string) does not put
# a signature in the query, so these never appear in PoC traffic -- listed so
# BK-181 proper inherits the intent when SAS-authenticated fixtures land.
_SCRUB_QUERY_PARAMS = ("sig", "se", "st", "sp", "sv", "sr", "skoid", "sktid", "skt", "ske", "sks", "skv")


# ---------------------------------------------------------------------------
# Connection-string handling
# ---------------------------------------------------------------------------
def _parse_account_name(conn_str: str) -> str:
    for part in conn_str.split(";"):
        if part.strip().lower().startswith("accountname="):
            return part.split("=", 1)[1].strip()
    pytest.fail("connection string has no AccountName=")
    raise AssertionError  # unreachable -- pytest.fail raises


def _live_connection_string() -> str:
    """Real ADLS Gen2 connection string for record mode. Fails loud.

    Mirrors the repo convention in ``tests/backends/fixtures/_live_env.py``:
    once the developer has opted into recording, missing or emulator
    credentials are a configuration bug, not a reason to silent-skip.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 -- lazy, only on the record path

    load_dotenv(override=False)
    if os.environ.get("RS_TEST_LIVE_HNS") != "1":
        pytest.fail("recording requires RS_TEST_LIVE_HNS=1 (a real ADLS Gen2 account)")
    conn = (os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or "").strip()
    if not conn:
        pytest.fail("recording requires AZURE_STORAGE_CONNECTION_STRING (a real ADLS Gen2 account)")
    if "UseDevelopmentStorage=true" in conn or "AccountName=devstoreaccount1" in conn:
        pytest.fail("AZURE_STORAGE_CONNECTION_STRING points at Azurite; recording needs a real HNS account")
    return conn


# ---------------------------------------------------------------------------
# vcrpy configuration -- the scrubbing layer
# ---------------------------------------------------------------------------
@pytest.fixture
def _real_account(record_mode: str) -> str | None:
    """Real storage-account name (record mode) or ``None`` (replay mode)."""
    if record_mode == "none":
        return None
    return _parse_account_name(_live_connection_string())


@pytest.fixture
def vcr_config(_real_account: str | None) -> dict[str, Any]:
    """Scrub credentials and the real account name out of every cassette.

    ``before_record_request`` runs in *both* modes -- vcrpy also applies it
    to the live request during replay so it can be matched against the
    cassette. ``_real_account`` is ``None`` on the replay path, so the
    ``if real:`` guards below are required, not optional.
    """
    real = _real_account

    def before_record_request(request: Any) -> Any:
        if real:
            request.uri = request.uri.replace(real, FAKE_ACCOUNT)
        for key in list(request.headers):
            if key.lower() in _SCRUB_REQUEST_HEADERS:
                del request.headers[key]
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            if key.lower() in _SCRUB_RESPONSE_HEADERS:
                del headers[key]
        if real:
            body = response.get("body", {})
            raw = body.get("string")
            if isinstance(raw, bytes):
                body["string"] = raw.replace(real.encode(), FAKE_ACCOUNT.encode())
            elif isinstance(raw, str):
                body["string"] = raw.replace(real, FAKE_ACCOUNT)
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
        # header (scrubbed, unmatched), not the query, and the per-run
        # x-ms-client-request-id is a header too.
    }


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def azure_conn_str(record_mode: str) -> str:
    """Real connection string when recording, fixed fake one when replaying."""
    return FAKE_CONN_STR if record_mode == "none" else _live_connection_string()


def _ensure_filesystem(conn_str: str, name: str) -> None:
    """Create the HNS filesystem if absent. Runs in both modes.

    Recording: a real round trip against ADLS Gen2 (captured in the cassette).
    Replay: vcrpy serves the captured response -- whichever status was
    recorded (``201 Created`` or ``409 ResourceExists``), the try/except
    below absorbs the difference so the same code path runs unchanged.
    """
    from azure.core.exceptions import ResourceExistsError  # noqa: PLC0415
    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    service = DataLakeServiceClient.from_connection_string(conn_str)
    try:
        service.create_file_system(name)
    except ResourceExistsError:
        pass
    finally:
        service.close()


def _ensure_hns_directory(conn_str: str, container: str, path: str) -> str:
    """Materialise a real HNS directory blob (``hdi_isfolder=true``).

    This is the marker Azurite cannot emulate and the reason BK-181 is the
    foundation for the HNS bug family. Idempotent so re-records are clean.
    """
    from azure.core.exceptions import ResourceExistsError  # noqa: PLC0415
    from azure.storage.filedatalake import DataLakeServiceClient  # noqa: PLC0415

    service = DataLakeServiceClient.from_connection_string(conn_str)
    try:
        fs_client = service.get_file_system_client(container)
        with contextlib.suppress(ResourceExistsError):
            fs_client.get_directory_client(path).create_directory()
    finally:
        service.close()
    return path


@pytest.fixture
def azure_backend(azure_conn_str: str) -> Iterator[Any]:
    """A real ``AzureBackend`` against the fixed ``bk181poc`` filesystem."""
    from remote_store.backends._azure import AzureBackend  # noqa: PLC0415

    _ensure_filesystem(azure_conn_str, CONTAINER)
    backend = AzureBackend(container=CONTAINER, connection_string=azure_conn_str)
    try:
        yield backend
    finally:
        backend.close()


@pytest.fixture
async def async_azure_backend(azure_conn_str: str) -> AsyncIterator[Any]:
    """A real ``AsyncAzureBackend`` against the fixed ``bk181poc`` filesystem.

    Filesystem setup uses the *sync* DataLake SDK (same choice the live
    registry fixture ``azure_live_async.py`` makes); the test body exercises
    the async backend code path.

    **Transport shim.** The async Azure SDK defaults to ``AioHttpTransport``
    (aiohttp), and vcrpy 8.1.1's aiohttp stub cannot stream a response body:
    it deadlocks ``AioHttpTransport.__anext__`` on replay and drops the body
    on record (see the finding doc). The PoC works around that by injecting
    ``AsyncioRequestsTransport`` -- an async transport that rides ``requests``
    in a thread pool -- so the proven urllib3 stub handles the traffic. The
    backend's own async code path is unchanged; only the bottom transport
    layer differs. Injection is via the existing ``client_options`` kwarg,
    so production code is untouched.
    """
    from azure.core.pipeline.transport import AsyncioRequestsTransport  # noqa: PLC0415

    from remote_store.aio.backends._azure import AsyncAzureBackend  # noqa: PLC0415

    _ensure_filesystem(azure_conn_str, CONTAINER)
    backend = AsyncAzureBackend(
        container=CONTAINER,
        connection_string=azure_conn_str,
        client_options={"transport": AsyncioRequestsTransport()},
    )
    try:
        yield backend
    finally:
        await backend.aclose()


@pytest.fixture
def hns_directory(azure_conn_str: str) -> Callable[[str], str]:
    """Factory: materialise a real HNS directory blob at the given path."""

    def _make(path: str) -> str:
        return _ensure_hns_directory(azure_conn_str, CONTAINER, path)

    return _make


# ---------------------------------------------------------------------------
# TEST-007: a missing replay cassette skips, it does not fail
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``vcr``-marked tests whose cassette is absent in replay mode.

    vcrpy's native behaviour is to *raise* when ``record_mode=none`` meets an
    unmatched request. TEST-007 wants a *skip*. The cassette path mirrors
    ``pytest_recording.plugin.vcr_cassette_dir`` (``<test_dir>/cassettes/
    <test_file_stem>/``) and ``get_default_cassette_name`` (``<node_name>``);
    PoC tests are module-level functions, so the node name is the file name.
    """
    record_mode = config.getoption("--record-mode") or "none"
    if record_mode != "none":
        return
    for item in items:
        if item.get_closest_marker("vcr") is None:
            continue
        cassette = item.path.parent / "cassettes" / item.path.stem / f"{item.name}.yaml"
        if not cassette.exists():
            rel = os.path.relpath(cassette, config.rootpath)
            item.add_marker(
                pytest.mark.skip(reason=f"replay cassette missing ({rel}); record with --record-mode=rewrite")
            )
