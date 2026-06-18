"""WR-012 / WR-013 property-based metadata round-trip — Azure backend (BK-221 / BK-191 slice 5/6).

Verifies that ``WriteResult.metadata`` echoes the caller-supplied mapping
verbatim (WR-012) and that ``get_file_info().metadata`` round-trips the same
mapping through the Azure Blob Storage REST layer (WR-013), under arbitrary
but WR-011-compliant key/value shapes.  Azurite stands in for the real
endpoint; the test is a no-op when Docker services are not running.

Companion: the fixed-example WR-012 / WR-013 assertions across all conformance
fixtures live in ``tests/backends/conformance/test_atomic.py::TestWriteResultConformance``.
This file adds property coverage that enumerated examples cannot: random
metadata shapes exercised against real SDK serialisation.

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

pytest.importorskip("azure.storage.blob")

from remote_store._capabilities import Capability  # noqa: E402
from remote_store._models import WriteResult  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# Metadata strategies (WR-011-compliant, Azure-compatible)
# ---------------------------------------------------------------------------

# Keys are letter-led, lowercase alphanumeric.  Three cross-backend
# constraints apply here:
#   * Azure metadata keys must be valid C# identifiers, so letter-led is
#     mandatory (``0a`` is rejected by the SDK).
#   * Underscores are excluded to stay consistent with the S3 regime and
#     avoid any WSGI header-translation collisions in shared test infra.
#   * codepoint ``0x21`` (``!``) upward in values excludes space and tab:
#     Azurite / the Azure REST layer trims leading and trailing HTTP header
#     whitespace per RFC 7230, so ``{"k": " "}`` round-trips to ``{"k": ""}``.
# WR-011 itself forbids leading underscore and empty keys.
_META_KEY_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_meta_key = st.text(alphabet=st.sampled_from(_META_KEY_ALPHABET), min_size=1, max_size=20).filter(
    lambda s: s[0].isalpha()
)

# Printable ASCII values with no whitespace — safe on Azure.
# ``min_size=1``: empty-value metadata round-trips to ``None`` on Azurite
# (HTTP intermediaries strip empty-body headers; both empty-value and
# ``None`` collapse to the same wire form on Azure).
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
def azure_backend(azurite_server: str | None) -> Iterator[Backend]:
    """Azurite-backed backend; skips when Azurite is not reachable."""
    if azurite_server is None:
        pytest.skip("azure SDK not installed or Azurite not reachable")

    from azure.storage.blob import BlobServiceClient

    from remote_store.backends._azure import AzureBackend

    container = f"pbt-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(azurite_server)
    try:
        service.create_container(container)
    except Exception:
        service.close()
        raise

    b = AzureBackend(container=container, hns=False, connection_string=azurite_server)
    try:
        yield b
    finally:
        b.close()
        service.delete_container(container)
        service.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _require_user_metadata(backend: Backend) -> None:
    if not backend.capabilities.supports(Capability.USER_METADATA):
        pytest.skip(f"{backend.name} does not declare USER_METADATA")
    if not backend.capabilities.supports(Capability.METADATA):
        pytest.skip(f"{backend.name} does not declare METADATA")


@pytest.mark.requires_docker
class TestMetadataRoundTripAzure:
    """WR-012 / WR-013 under the Azure backend via Azurite."""

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
