"""pytest-recording / vcrpy wiring for the BK-181 S3 cassette-replay spike.

Mirrors ``sdd/research/bk-181-poc/conftest.py`` (Azure PoC). Loaded only
when pytest is pointed explicitly at ``sdd/research/bk-181-s3-spike/`` —
the folder sits outside ``testpaths`` in ``pyproject.toml``, so a normal
``hatch run test`` never touches it.

The spike validates whether vcrpy 8.1.1 can record + replay against
``s3fs.S3FileSystem``. The Azure PoC found vcrpy's ``aiohttp_stubs.py``
drops the response body on record and deadlocks on replay for
``AioHttpTransport``; ``s3fs`` rides ``aiobotocore`` which uses aiohttp,
and offers no equivalent transport injection point. See README.md for
the decision gate.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Fixed identifiers
# ---------------------------------------------------------------------------
# Deterministic bucket name. The repo's live registry mints
# ``rs-conformance-<uuid12>`` per call (tests/backends/fixtures/s3_live.py),
# but the spike uses a single fixed bucket so the cassettes don't depend on
# URI rewriting (that complication moves to the production PR 2 wiring).
BUCKET = "rs-conformance-bk181spike"

# Region kept on us-east-1 so the bucket-create call path doesn't carry a
# LocationConstraint, matching what the simplest S3 client setup produces.
FAKE_REGION = "us-east-1"

# Placeholder credentials for replay: real boto3 default chain would probe
# IMDS/SSO and may emit network calls that --block-network rejects.
FAKE_KEY = "AKIAFAKESPIKEKEY"
FAKE_SECRET = "fake-spike-secret-not-real"  # noqa: S105 -- spike placeholder, not a credential

_SCRUB_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "x-amz-date",
        "x-amz-content-sha256",
        "x-amz-security-token",
        "amz-sdk-invocation-id",
        "amz-sdk-request",
        "cookie",
    }
)
_SCRUB_RESPONSE_HEADERS = frozenset(
    {
        "x-amz-request-id",
        "x-amz-id-2",
        "date",
        "set-cookie",
    }
)
_SCRUB_QUERY_PARAMS = (
    "X-Amz-Signature",
    "X-Amz-Credential",
    "X-Amz-Date",
    "X-Amz-Expires",
    "X-Amz-SignedHeaders",
    "X-Amz-Algorithm",
    "X-Amz-Security-Token",
)


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------
def _live_credentials() -> dict[str, str]:
    """Real AWS credentials for record mode. Fails loud."""
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(override=False)
    if os.environ.get("RS_TEST_LIVE_S3") != "1":
        pytest.fail("recording requires RS_TEST_LIVE_S3=1 (a real AWS S3 account)")
    out: dict[str, str] = {}
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
        value = (os.environ.get(var) or "").strip()
        if not value:
            pytest.fail(f"recording requires {var}")
        out[var] = value
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    if endpoint and any(frag in endpoint for frag in ("127.0.0.1", "localhost", ":9000", ":4566")):
        pytest.fail(f"AWS_ENDPOINT_URL={endpoint!r} points at an emulator; recording needs a real account")
    return out


# ---------------------------------------------------------------------------
# vcrpy configuration — the scrubbing layer
# ---------------------------------------------------------------------------
@pytest.fixture
def _real_bucket(record_mode: str) -> str | None:
    """Real (per-run) bucket name in record mode, ``None`` in replay mode.

    The spike uses a fixed bucket name (``BUCKET``), so no URI rewriting is
    needed in either direction — record and replay both target the same
    bucket name. The fixture is here for parity with the Azure PoC pattern
    and so future bucket-rewriting (production PR 2) slots in cleanly.
    """
    if record_mode == "none":
        return None
    return BUCKET


@pytest.fixture
def vcr_config(_real_bucket: str | None) -> dict[str, Any]:  # noqa: ARG001 -- shape-preserving for PR 2 port
    """Scrub credentials and signature query parameters from every cassette."""

    def before_record_request(request: Any) -> Any:
        for key in list(request.headers):
            if key.lower() in _SCRUB_REQUEST_HEADERS:
                del request.headers[key]
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            if key.lower() in _SCRUB_RESPONSE_HEADERS:
                del headers[key]
        return response

    return {
        "decode_compressed_response": True,
        "filter_query_parameters": list(_SCRUB_QUERY_PARAMS),
        "before_record_request": before_record_request,
        "before_record_response": before_record_response,
    }


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------
def _ensure_bucket(creds: dict[str, str]) -> None:
    """Create the spike bucket if absent. Runs in both modes.

    Recording: a real round trip captured in the cassette. Replay: vcrpy
    serves the captured response (200 or 409). Either way, the same code
    path runs unchanged.
    """
    import boto3  # noqa: PLC0415
    from botocore.exceptions import ClientError  # noqa: PLC0415

    client = boto3.client(
        "s3",
        aws_access_key_id=creds["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["AWS_SECRET_ACCESS_KEY"],
        region_name=creds["AWS_DEFAULT_REGION"],
    )
    try:
        kwargs: dict[str, Any] = {"Bucket": BUCKET}
        if creds["AWS_DEFAULT_REGION"] != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": creds["AWS_DEFAULT_REGION"]}
        with contextlib.suppress(ClientError):
            client.create_bucket(**kwargs)
    finally:
        client.close()


@pytest.fixture
def s3_backend(record_mode: str) -> Iterator[Any]:
    """Real ``S3Backend`` against the fixed spike bucket.

    In record mode, uses live credentials from ``.env`` and provisions the
    bucket idempotently. In replay mode, uses fake credentials so boto3
    never probes IMDS/SSO; the backend's traffic is served by vcrpy.
    """
    from remote_store.backends._s3 import S3Backend  # noqa: PLC0415

    if record_mode == "none":
        creds = {
            "AWS_ACCESS_KEY_ID": FAKE_KEY,
            "AWS_SECRET_ACCESS_KEY": FAKE_SECRET,
            "AWS_DEFAULT_REGION": FAKE_REGION,
        }
    else:
        creds = _live_credentials()
        _ensure_bucket(creds)

    backend = S3Backend(
        bucket=BUCKET,
        key=creds["AWS_ACCESS_KEY_ID"],
        secret=creds["AWS_SECRET_ACCESS_KEY"],
        region_name=creds["AWS_DEFAULT_REGION"],
    )
    try:
        yield backend
    finally:
        backend.close()


# ---------------------------------------------------------------------------
# Plugin guard
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Fail fast with a clear message when ``pytest-recording`` is absent."""
    if importlib.util.find_spec("pytest_recording") is None:
        pytest.exit(
            "pytest-recording is required for the BK-181 S3 spike but is not installed; "
            "run: uv pip install --python .venv pytest-recording",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# TEST-007: a missing replay cassette skips, it does not fail
# ---------------------------------------------------------------------------
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip vcr-marked tests whose cassette is absent in replay mode."""
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
