"""WR-012 / WR-013 property-based metadata round-trip — S3 backend (BK-221 / BK-191 slice 5/6).

Verifies that ``WriteResult.metadata`` echoes the caller-supplied mapping
verbatim (WR-012) and that ``get_file_info().metadata`` round-trips the same
mapping through the S3 object-tagging / header layer (WR-013), under arbitrary
but WR-011-compliant key/value shapes.

Companion: the fixed-example WR-012 / WR-013 assertions across all conformance
fixtures live in ``tests/backends/conformance/test_atomic.py::TestWriteResultConformance``.
This file adds property coverage that enumerated examples cannot: random
metadata shapes exercised against real SDK serialisation (moto standing in for
the S3 endpoint).

Migrated from ``tests/test_pbt_write_result.py`` (BK-221 / BK-191 slice 5/6).
The size-regime PBT (WR-001a / WR-003) stays at root: ``MemoryBackend`` and
``LocalBackend`` are allowed there, and the BUG-168 boundary is
``LocalBackend``-specific (real ``BufferedWriter`` path).

Hypothesis profiles are loaded from ``tests/conftest.py``
(``dev=50`` / ``ci=100`` / ``nightly=1000``); no inline ``max_examples``
(TESTING.md Rule 10). Metadata strategies are module-level constants
(TESTING.md Rule 11).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

pytest.importorskip("boto3")
pytest.importorskip("s3fs")
pytest.importorskip("aiobotocore")
pytest.importorskip("moto")

from remote_store._capabilities import Capability  # noqa: E402
from remote_store._models import WriteResult  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# Metadata strategies (WR-011-compliant, S3-compatible)
# ---------------------------------------------------------------------------

# Keys are letter-led, lowercase alphanumeric.  Two S3-specific constraints:
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

# Printable ASCII values with no whitespace — safe on S3 (header bytes).
# ``min_size=1``: empty-value metadata (``{"k": ""}``) round-trips to
# ``None`` on moto because ``x-amz-meta-*`` headers with empty bodies are
# not returned by HeadObject (and are commonly stripped by HTTP intermediaries).
_meta_value = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=50,
)


def _meta_payload_bytes(m: dict[str, str]) -> int:
    return sum(len(k.encode("ascii")) + len(v.encode("utf-8")) for k, v in m.items())


# WR-011 caps the total payload at 2048 bytes; ``min_size=1`` excludes the
# empty-dict case (WR-010 routes to the no-metadata branch, making WR-012
# vacuous; fixed-example coverage lives in ``TestWriteResultConformance``).
_metadata = st.dictionaries(keys=_meta_key, values=_meta_value, min_size=1, max_size=6).filter(
    lambda m: _meta_payload_bytes(m) <= 2000
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def s3_backend(moto_server: str | None) -> Iterator[Backend]:
    """Fresh bucket per test function; shared session moto server."""
    if moto_server is None:
        pytest.skip("moto/s3fs not installed")
    import boto3

    from remote_store.backends._s3 import S3Backend

    bucket = f"pbt-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=moto_server,
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
        endpoint_url=moto_server,
    )
    try:
        yield b
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _require_user_metadata(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.USER_METADATA):
        pytest.skip(f"{backend.name} does not declare USER_METADATA")
    if not backend.capabilities.supports(Capability.METADATA):
        pytest.skip(f"{backend.name} does not declare METADATA")


class TestMetadataRoundTripS3:
    """WR-012 / WR-013 under the S3 backend via moto."""

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
