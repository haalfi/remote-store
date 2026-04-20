"""Property-based tests for ``WriteResult`` invariants (ID-151c).

Companion to ``tests/backends/test_conformance.py::TestWriteResultConformance``,
which exercises fixed-example WR-001a / WR-003 / WR-004 / WR-005 / WR-012 /
WR-013 across the full conformance fixture matrix.  This module adds property
coverage that enumerated inputs cannot: random payloads across the size
regimes that historically broke things (BUG-168 — Python 3.14 raised the
default ``BufferedWriter`` block size to roughly 128 KiB, so a 256 KiB – 1 MiB
streaming payload bypasses the flush that ``getsize``/``stat`` expects), and
metadata round-trip under arbitrary-but-WR-011-compliant key/value shapes.

Backend selection is deliberately narrow, per TESTING.md Rules 5 and 6:

* PBT 1 (size): ``MemoryBackend`` as a fast oracle; ``LocalBackend`` for the
  BUG-168 boundary — it is the only v1 backend whose write path flows
  through a real ``BufferedWriter``.
* PBT 2 (metadata round-trip): ``S3Backend`` under ``moto`` and
  ``AzureBackend`` under Azurite — the two v1 backends whose
  ``USER_METADATA`` round-trip crosses a real SDK serialisation boundary.
  Azure is gated on Azurite reachability so the test is a no-op when Docker
  services are not running.

Hypothesis profiles are loaded from ``tests/conftest.py``
(``dev=50`` / ``ci=100`` / ``nightly=1000``); no inline ``max_examples`` is
set (TESTING.md Rule 10).  Payload and metadata strategies are module-level
constants (TESTING.md Rule 11).
"""

from __future__ import annotations

import io
import socket
import uuid
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from remote_store._capabilities import Capability
from remote_store._models import WriteResult
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend
from tests.backends.conftest import _free_port

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# Availability gates
# ---------------------------------------------------------------------------


def _s3_available() -> bool:
    try:
        import moto  # noqa: F401
        import s3fs  # noqa: F401
    except ImportError:
        return False
    return True


def _azure_available() -> bool:
    # The ``azure_backend`` fixture only touches ``azure.storage.blob`` (via
    # ``BlobServiceClient`` and ``AzureBackend``), so probe that package — not
    # ``azure.storage.filedatalake``, which is a separate install extra.
    try:
        import azure.storage.blob  # noqa: F401
    except ImportError:
        return False
    return True


def _azurite_reachable() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 10000), timeout=1)
        s.close()
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# Payload strategies (TESTING.md Rule 11 — module scope)
# ---------------------------------------------------------------------------

# Small regime: 0 B through 4 KiB-1.  Random content stays cheap.
_SMALL_MAX = 4 * 1024 - 1
_small_payload = st.binary(min_size=0, max_size=_SMALL_MAX)

# BUG-168 regime: 256 KiB through 1 MiB.  The Python 3.14 default
# BufferedWriter block size (~128 KiB) is large enough to hold anything
# below 256 KiB unflushed — so a pre-close ``getsize`` observed 0 on
# LocalBackend.write_atomic before the fix.  Content is deterministic per
# example (``fill * size``) so Hypothesis examples stay cheap and shrink
# cleanly without allocating random 1 MiB blobs.
_BUG168_MIN = 256 * 1024
_BUG168_MAX = 1024 * 1024

_write_op = st.sampled_from(["write", "write_atomic"])


# ---------------------------------------------------------------------------
# Metadata strategies (WR-011-compliant, SDK-portable)
# ---------------------------------------------------------------------------

# Keys are letter-led, lowercase alphanumeric.  Three cross-backend
# constraints pin down the shape:
#   * Azure metadata keys must be valid C# identifiers, so letter-led is
#     mandatory (``0a`` is rejected).
#   * S3 lowercases header-derived keys on the wire, so ``get_file_info``
#     returns a lowercase key even when the caller passed mixed case;
#     staying lowercase keeps round-trip exact.
#   * Underscores are excluded.  The WSGI spec translates request headers
#     to ``HTTP_<UPPER>`` with ``-`` → ``_`` — so ``x-amz-meta-foo_bar`` and
#     ``x_amz_meta_foo_bar`` collide on werkzeug's dev server, which is
#     what moto is built on.  Any underscore in the metadata key causes
#     moto to drop the header on the HeadObject response.  Real S3 does
#     not have this limitation; it is purely a test-server artefact, and
#     WR-011 is silent on the matter.
# WR-011 itself forbids leading underscore and empty keys.
_META_KEY_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_meta_key = st.text(alphabet=st.sampled_from(_META_KEY_ALPHABET), min_size=1, max_size=20).filter(
    lambda s: s[0].isalpha()
)

# Printable ASCII values with no whitespace — safe on both S3 (header bytes)
# and Azure.  Two domain restrictions:
#   * ``min_size=1``: empty-value metadata (``{"k": ""}``) round-trips to
#     ``None`` on S3 because ``x-amz-meta-*`` headers with empty bodies are
#     not returned by HeadObject on moto (and are commonly stripped by HTTP
#     intermediaries).
#   * codepoint ``0x21`` (``!``) upward excludes space and tab: Azurite / the
#     Azure REST layer trims leading and trailing HTTP header whitespace per
#     RFC 7230, so ``{"k": " "}`` round-trips to ``{"k": ""}``.
# Both are HTTP-header artefacts outside WR-011's scope; the conformance
# suite's fixed examples sit in the same narrower domain.
_meta_value = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=50,
)


def _meta_payload_bytes(m: dict[str, str]) -> int:
    return sum(len(k.encode("ascii")) + len(v.encode("utf-8")) for k, v in m.items())


# WR-011 caps the total payload at 2048 bytes; leave headroom so the
# ``filter`` does not reject too many generated examples.  ``min_size=1``
# excludes the empty-dict case from PBT 2: when ``metadata={}`` is passed,
# WR-010 routes to the no-metadata branch and WR-012 does not apply, so the
# property being tested here is vacuous.  The empty-dict / ``None``
# equivalence is already covered by
# ``TestWriteResultConformance.test_metadata_is_none_when_not_passed``.
_metadata = st.dictionaries(keys=_meta_key, values=_meta_value, min_size=1, max_size=6).filter(
    lambda m: _meta_payload_bytes(m) <= 2000
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _example_path(prefix: str, *parts: object) -> str:
    """Stable filename derived from example inputs (reproducible under shrink)."""
    suffix = "-".join(str(p) for p in parts) or "root"
    return f"{prefix}/{suffix}.bin"


def _do_write(
    backend: Backend,
    path: str,
    content: bytes | io.BytesIO,
    *,
    overwrite: bool,
    op: str,
    metadata: dict[str, str] | None = None,
) -> WriteResult:
    """Dispatch ``write`` / ``write_atomic`` with hygienic pre-state."""
    backend.delete(path, missing_ok=True)
    if overwrite:
        backend.write(path, b"seed", overwrite=False)
    kwargs: dict[str, object] = {"overwrite": overwrite}
    if metadata is not None:
        kwargs["metadata"] = metadata
    return getattr(backend, op)(path, content, **kwargs)


# ---------------------------------------------------------------------------
# PBT 1 — WriteResult.size == len(payload)
# ---------------------------------------------------------------------------


class TestWriteResultSizeSmall:
    """WR-001a / WR-003: ``size`` matches payload length across the small regime."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @given(
        payload=_small_payload,
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_memory(self, payload: bytes, overwrite: bool, as_stream: bool, op: str) -> None:
        backend = MemoryBackend()
        path = _example_path("pbt", "mem", len(payload), int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == len(payload)

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @pytest.mark.os_sensitive
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        payload=_small_payload,
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_local(
        self,
        tmp_path: object,
        payload: bytes,
        overwrite: bool,
        as_stream: bool,
        op: str,
    ) -> None:
        backend = LocalBackend(root=str(tmp_path))
        path = _example_path("pbt", "local-s", len(payload), int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == len(payload)


class TestWriteResultSizeBug168Regime:
    """WR-001a / WR-003 at the 256 KiB – 1 MiB buffer boundary (BUG-168 net)."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @pytest.mark.os_sensitive
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
        deadline=None,
    )
    @given(
        size=st.integers(min_value=_BUG168_MIN, max_value=_BUG168_MAX),
        fill=st.integers(min_value=0, max_value=255),
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_local_buffer_boundary(
        self,
        tmp_path: object,
        size: int,
        fill: int,
        overwrite: bool,
        as_stream: bool,
        op: str,
    ) -> None:
        """BUG-168 regression net.

        Only ``LocalBackend`` exercises a real ``BufferedWriter``; this is the
        regime where a pre-close ``os.path.getsize`` returned ``0`` on
        Python 3.14 (default buffer ~128 KiB, payload ≥ 256 KiB — everything
        stays buffered until ``with`` exit).  Content is deterministic per
        example (``bytes([fill]) * size``) to keep Hypothesis memory flat.
        """
        backend = LocalBackend(root=str(tmp_path))
        payload = bytes([fill]) * size
        path = _example_path("pbt", "local-b", size, fill, int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == size


# ---------------------------------------------------------------------------
# PBT 2 — Metadata round-trip (WR-012 echo + WR-013 get_file_info round-trip)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _moto_endpoint() -> Iterator[str | None]:
    """Module-scoped moto HTTP server — amortise startup across examples."""
    if not _s3_available():
        yield None
        return
    from moto.moto_server.threaded_moto_server import ThreadedMotoServer

    port = _free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@pytest.fixture
def s3_backend(_moto_endpoint: str | None) -> Iterator[Backend]:
    """Fresh bucket per test function; shared moto server."""
    if _moto_endpoint is None:
        pytest.skip("moto/s3fs not installed")
    import boto3

    from remote_store.backends._s3 import S3Backend

    bucket = f"pbt-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=_moto_endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    b = S3Backend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name="us-east-1",
        endpoint_url=_moto_endpoint,
    )
    try:
        yield b
    finally:
        b.close()


@pytest.fixture
def azure_backend() -> Iterator[Backend]:
    """Azurite-backed AzureBackend; skips when Azurite is not reachable."""
    if not _azure_available() or not _azurite_reachable():
        pytest.skip("azure SDK not installed or Azurite not reachable")

    from azure.storage.blob import BlobServiceClient

    from remote_store.backends._azure import AzureBackend
    from tests.backends.conftest import _AZURITE_CONN_STR

    container = f"pbt-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(_AZURITE_CONN_STR)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise

    b = AzureBackend(container=container, connection_string=_AZURITE_CONN_STR)
    try:
        yield b
    finally:
        b.close()
        service.delete_container(container)
        service.close()


def _require_user_metadata(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.USER_METADATA):
        pytest.skip(f"{backend.name} does not declare USER_METADATA")
    if not backend.capabilities.supports(Capability.METADATA):
        pytest.skip(f"{backend.name} does not declare METADATA")


@pytest.mark.skipif(not _s3_available(), reason="moto/s3fs not installed")
class TestMetadataRoundTripS3:
    """WR-012 / WR-013 under ``S3Backend`` via moto."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-012")
    @pytest.mark.spec("WR-013")
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
        deadline=None,
    )
    @given(metadata=_metadata)
    def test_round_trip(self, s3_backend: Backend, metadata: dict[str, str]) -> None:
        _require_user_metadata(s3_backend)
        path = f"pbt/s3-meta-{uuid.uuid4().hex[:8]}.bin"
        result = s3_backend.write(path, b"pbt", overwrite=True, metadata=metadata)
        assert isinstance(result, WriteResult)
        assert result.metadata == metadata  # WR-012
        info = s3_backend.get_file_info(path)
        assert info.metadata == metadata  # WR-013


@pytest.mark.requires_docker
@pytest.mark.skipif(
    not _azure_available() or not _azurite_reachable(),
    reason="azure SDK not installed or Azurite not reachable",
)
class TestMetadataRoundTripAzure:
    """WR-012 / WR-013 under ``AzureBackend`` via Azurite."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-012")
    @pytest.mark.spec("WR-013")
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
        deadline=None,
    )
    @given(metadata=_metadata)
    def test_round_trip(self, azure_backend: Backend, metadata: dict[str, str]) -> None:
        _require_user_metadata(azure_backend)
        path = f"pbt/az-meta-{uuid.uuid4().hex[:8]}.bin"
        result = azure_backend.write(path, b"pbt", overwrite=True, metadata=metadata)
        assert isinstance(result, WriteResult)
        assert result.metadata == metadata  # WR-012
        info = azure_backend.get_file_info(path)
        assert info.metadata == metadata  # WR-013
