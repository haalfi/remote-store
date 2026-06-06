"""GraphBackend public surface (GR-001..005, GR-009/010, GR-036/036a, GR-037, GR-051).

Construction/validation, capability declaration, path addressing and encoding,
the unwrap escape hatch, the close baseline, and credential-safe repr. The
data-plane operations themselves are exercised in the read / write / mutate
test modules; this module covers the construction-time and addressing surface.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from remote_store._capabilities import Capability
from remote_store._errors import CapabilityNotSupported
from remote_store.aio.backends._graph.backend import GraphBackend, _encode_segment

_DRIVE = "b!driveid123"


def _make(**kwargs: Any) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok", **kwargs)


class TestConstruction:
    """GR-001 / GR-005 construction and validation."""

    @pytest.mark.spec("GR-001")
    def test_valid_construction_does_no_io(self) -> None:
        backend = _make()
        assert backend.drive_id == _DRIVE
        assert backend._owned_client is None  # GR-004: no client until first use

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_drive_id_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="drive_id"):
            GraphBackend(bad, token_provider=lambda: "t")

    @pytest.mark.spec("GR-005")
    def test_non_callable_token_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="token_provider"):
            GraphBackend(_DRIVE, token_provider="not-callable")  # type: ignore[arg-type]

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [0, -320 * 1024, 320 * 1024 + 1, 500_000])
    def test_misaligned_upload_chunk_size_rejected(self, bad: int) -> None:
        with pytest.raises(ValueError, match="320 KiB"):
            _make(upload_chunk_size=bad)

    @pytest.mark.spec("GR-005")
    def test_aligned_upload_chunk_size_accepted(self) -> None:
        backend = _make(upload_chunk_size=320 * 1024 * 3)
        assert backend._upload_chunk_size == 320 * 1024 * 3

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [60 * 1024 * 1024, 200 * 320 * 1024])
    def test_oversized_upload_chunk_size_rejected(self, bad: int) -> None:
        # Aligned 320 KiB multiples at/above Graph's 60 MiB per-request ceiling
        # (60 MiB == 192 x 320 KiB exactly; 200 x 320 KiB == 62.5 MiB).
        with pytest.raises(ValueError, match="60 MiB"):
            _make(upload_chunk_size=bad)

    @pytest.mark.spec("GR-005")
    def test_upload_chunk_size_just_below_ceiling_accepted(self) -> None:
        size = 191 * 320 * 1024  # largest aligned multiple strictly below 60 MiB
        backend = _make(upload_chunk_size=size)
        assert backend._upload_chunk_size == size

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [0, -1.0])
    def test_non_positive_copy_timeout_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="copy_timeout"):
            _make(copy_timeout=bad)

    @pytest.mark.spec("GR-026")
    def test_copy_timeout_none_is_allowed(self) -> None:
        assert _make(copy_timeout=None)._copy_timeout is None


class TestIdentity:
    """GR-002 name, GR-003 capabilities."""

    @pytest.mark.spec("GR-002")
    def test_name(self) -> None:
        assert _make().name == "graph"

    @pytest.mark.spec("GR-003")
    def test_capability_set_is_exact(self) -> None:
        expected = {
            Capability.READ,
            Capability.WRITE,
            Capability.DELETE,
            Capability.LIST,
            Capability.MOVE,
            Capability.COPY,
            Capability.METADATA,
            Capability.ATOMIC_WRITE,
            Capability.LAZY_READ,
            Capability.WRITE_RESULT_NATIVE,
        }
        assert set(_make().capabilities) == expected

    @pytest.mark.spec("GR-003")
    @pytest.mark.parametrize(
        "withheld",
        [Capability.GLOB, Capability.ATOMIC_MOVE, Capability.SEEKABLE_READ, Capability.USER_METADATA],
    )
    def test_withheld_capabilities(self, withheld: Capability) -> None:
        assert not _make().capabilities.supports(withheld)


class TestAddressing:
    """GR-009/010 path resolution and segment encoding; GR-036/036a round-trip."""

    @pytest.mark.spec("GR-036a")
    def test_native_path_empty_key_is_drive_root(self) -> None:
        assert _make().native_path("") == f"/drives/{_DRIVE}/root:"

    @pytest.mark.spec("GR-009")
    def test_native_path_simple(self) -> None:
        assert _make().native_path("a/b.txt") == f"/drives/{_DRIVE}/root:/a/b.txt:"

    @pytest.mark.spec("GR-010")
    def test_native_path_encodes_special_chars(self) -> None:
        # Spaces and ``#`` per the GR-010 example.
        assert _make().native_path("My Folder/file #1.txt") == f"/drives/{_DRIVE}/root:/My%20Folder/file%20%231.txt:"

    @pytest.mark.spec("GR-010")
    @pytest.mark.parametrize(
        ("raw", "encoded"),
        [(" ", "%20"), ("#", "%23"), ("?", "%3F"), ("+", "%2B")],
    )
    def test_encode_segment_special(self, raw: str, encoded: str) -> None:
        assert _encode_segment(f"x{raw}y") == f"x{encoded}y"

    @pytest.mark.spec("GR-010")
    def test_encode_segment_trailing_dot(self) -> None:
        assert _encode_segment("name.") == "name%2E"
        assert _encode_segment("a.b.") == "a.b%2E"  # only the trailing dot

    @pytest.mark.spec("GR-036")
    def test_to_key_strips_prefix_and_decodes(self) -> None:
        backend = _make()
        native = f"/drives/{_DRIVE}/root:/My%20Folder/file%20%231.txt:"
        assert backend.to_key(native) == "My Folder/file #1.txt"

    @pytest.mark.spec("GR-036")
    def test_to_key_passthrough_without_prefix(self) -> None:
        assert _make().to_key("/some/other/path") == "/some/other/path"

    @pytest.mark.spec("GR-036")
    def test_to_key_root_is_empty(self) -> None:
        assert _make().to_key(f"/drives/{_DRIVE}/root:") == ""

    @pytest.mark.spec("GR-036")
    @pytest.mark.parametrize("key", ["", "a", "a/b/c", "My Folder/file #1.txt", "weird+name", "trail."])
    def test_round_trip_identity(self, key: str) -> None:
        backend = _make()
        assert backend.to_key(backend.native_path(key)) == key

    @pytest.mark.spec("GR-009")
    def test_resolve_carries_drive_id(self) -> None:
        plan = _make().resolve("a.txt")
        assert plan.backend == "graph"
        assert plan.details["drive_id"] == _DRIVE
        assert plan.details["base_url"] == "https://graph.microsoft.com/v1.0"


class TestUnwrapAndClose:
    """GR-037 escape hatch and GR-051 close baseline."""

    @pytest.mark.spec("GR-037")
    def test_unwrap_returns_httpx_client(self) -> None:
        backend = _make()
        assert isinstance(backend.unwrap(httpx.AsyncClient), httpx.AsyncClient)

    @pytest.mark.spec("GR-037")
    def test_unwrap_wrong_type_raises(self) -> None:
        with pytest.raises(CapabilityNotSupported):
            _make().unwrap(str)

    @pytest.mark.spec("GR-051")
    async def test_aclose_closes_owned_client(self) -> None:
        backend = _make()
        client = backend._client  # force lazy creation
        await backend.aclose()
        assert client.is_closed
        assert backend._owned_client is None

    @pytest.mark.spec("GR-051")
    async def test_aclose_is_idempotent(self) -> None:
        backend = _make()
        _ = backend._client
        await backend.aclose()
        await backend.aclose()  # second call must not raise
        assert backend._owned_client is None

    @pytest.mark.spec("GR-051")
    async def test_aclose_leaves_user_supplied_client_open(self) -> None:
        async with httpx.AsyncClient() as user_client:
            backend = _make(http_client=user_client)
            assert backend.unwrap(httpx.AsyncClient) is user_client
            await backend.aclose()
            assert not user_client.is_closed  # caller owns it

    @pytest.mark.spec("GR-051")
    async def test_aclose_flushes_auth_cache(self) -> None:
        class _AuthProvider:
            def __init__(self) -> None:
                self.flushed = False

            def __call__(self) -> str:
                return "tok"

            def flush_cache(self) -> None:
                self.flushed = True

        provider = _AuthProvider()
        backend = GraphBackend(_DRIVE, token_provider=provider)
        await backend.aclose()
        assert provider.flushed

    @pytest.mark.spec("GR-052")
    def test_client_options_passed_through(self) -> None:
        backend = _make(client_options={"timeout": 5.0})
        assert backend._client.timeout.read == 5.0

    @pytest.mark.spec("GR-035")
    def test_repr_has_no_token(self) -> None:
        r = repr(_make())
        assert _DRIVE in r
        assert "tok" not in r
