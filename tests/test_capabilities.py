"""Tests for capabilities — derived from sdd/specs/003-backend-adapter-contract.md (CAP sections)."""

from __future__ import annotations

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported


class TestCapabilityEnum:
    """CAP-001: Capability enum members."""

    @pytest.mark.spec("CAP-001")
    def test_members(self) -> None:
        expected = {
            "READ",
            "WRITE",
            "DELETE",
            "LIST",
            "MOVE",
            "COPY",
            "ATOMIC_WRITE",
            "ATOMIC_MOVE",
            "METADATA",
            "GLOB",
            "SEEKABLE_READ",
            "LAZY_READ",
            "WRITE_RESULT_NATIVE",
            "USER_METADATA",
        }
        actual = {c.name for c in Capability}
        assert actual == expected

    @pytest.mark.spec("CAP-001")
    @pytest.mark.parametrize(
        ("member", "expected_value"),
        [
            pytest.param("READ", "read", id="read"),
            pytest.param("WRITE", "write", id="write"),
            pytest.param("DELETE", "delete", id="delete"),
            pytest.param("LIST", "list", id="list"),
            pytest.param("MOVE", "move", id="move"),
            pytest.param("COPY", "copy", id="copy"),
            pytest.param("ATOMIC_WRITE", "atomic_write", id="atomic_write"),
            pytest.param("ATOMIC_MOVE", "atomic_move", id="atomic_move"),
            pytest.param("METADATA", "metadata", id="metadata"),
            pytest.param("GLOB", "glob", id="glob"),
            pytest.param("SEEKABLE_READ", "seekable_read", id="seekable_read"),
            pytest.param("LAZY_READ", "lazy_read", id="lazy_read"),
            pytest.param("WRITE_RESULT_NATIVE", "write_result_native", id="write_result_native"),
            pytest.param("USER_METADATA", "user_metadata", id="user_metadata"),
        ],
    )
    def test_values(self, member: str, expected_value: str) -> None:
        """Each Capability member has the expected string value."""
        assert Capability[member].value == expected_value


class TestCapabilitySetConstruction:
    """CAP-002: CapabilitySet construction."""

    @pytest.mark.spec("CAP-002")
    def test_construction(self) -> None:
        cs = CapabilitySet({Capability.READ, Capability.WRITE})
        assert len(cs) == 2


class TestCapabilitySetSupports:
    """CAP-003: supports() method."""

    @pytest.mark.spec("CAP-003")
    def test_supports_true(self) -> None:
        cs = CapabilitySet({Capability.READ})
        assert cs.supports(Capability.READ) is True

    @pytest.mark.spec("CAP-003")
    def test_supports_false(self) -> None:
        cs = CapabilitySet({Capability.READ})
        assert cs.supports(Capability.WRITE) is False


class TestCapabilitySetRequire:
    """CAP-004: require() raises CapabilityNotSupported."""

    @pytest.mark.spec("CAP-004")
    def test_require_passes(self) -> None:
        cs = CapabilitySet({Capability.READ})
        result = cs.require(Capability.READ)
        assert result is None

    @pytest.mark.spec("CAP-004")
    def test_require_raises(self) -> None:
        cs = CapabilitySet({Capability.READ})
        with pytest.raises(CapabilityNotSupported) as exc_info:
            cs.require(Capability.WRITE, backend="test")
        assert exc_info.value.capability == "write"

    @pytest.mark.spec("CAP-004")
    def test_require_atomic_move_raises_with_correct_capability_value(self) -> None:
        """require(ATOMIC_MOVE) must raise with capability='atomic_move' when absent."""
        cs = CapabilitySet({Capability.READ, Capability.WRITE})
        with pytest.raises(CapabilityNotSupported, match="atomic_move") as exc_info:
            cs.require(Capability.ATOMIC_MOVE, backend="s3")
        assert exc_info.value.capability == "atomic_move"


class TestCapabilitySetIterationMembership:
    """CAP-005: Iteration and membership."""

    @pytest.mark.spec("CAP-005")
    def test_contains(self) -> None:
        cs = CapabilitySet({Capability.READ, Capability.WRITE})
        assert Capability.READ in cs
        assert Capability.DELETE not in cs

    @pytest.mark.spec("CAP-005")
    def test_iteration(self) -> None:
        caps = {Capability.READ, Capability.WRITE}
        cs = CapabilitySet(caps)
        assert set(cs) == caps


class TestCapabilitySetImmutability:
    """CAP-006: CapabilitySet is immutable."""

    @pytest.mark.spec("CAP-006")
    def test_immutable_setattr(self) -> None:
        cs = CapabilitySet({Capability.READ})
        with pytest.raises(AttributeError, match="immutable"):
            cs.x = 1  # type: ignore[attr-defined]

    @pytest.mark.spec("CAP-006")
    def test_immutable_delattr(self) -> None:
        cs = CapabilitySet({Capability.READ})
        with pytest.raises(AttributeError, match="immutable"):
            del cs._caps  # type: ignore[attr-defined]


class TestWriteResultNative:
    """WR-009: WRITE_RESULT_NATIVE is a quality flag — does not gate any method."""

    @pytest.mark.spec("WR-009")
    def test_is_quality_flag_not_a_gate(self) -> None:
        # The flag advertises rich WriteResult fields, not method availability.
        cs_with = CapabilitySet({Capability.WRITE, Capability.WRITE_RESULT_NATIVE})
        cs_without = CapabilitySet({Capability.WRITE})
        assert cs_with.supports(Capability.WRITE_RESULT_NATIVE)
        assert not cs_without.supports(Capability.WRITE_RESULT_NATIVE)
        # Both declare WRITE — the flag is orthogonal to write access.
        assert cs_with.supports(Capability.WRITE)
        assert cs_without.supports(Capability.WRITE)


class TestUserMetadata:
    """WR-010 (CapabilitySet layer): USER_METADATA membership declared/absent.

    Gate firing (non-empty metadata= raises CapabilityNotSupported) and the
    empty-mapping carve-out (metadata=None / metadata={} are no-ops) are
    Store-layer concerns tested in Step 4.
    """

    @pytest.mark.spec("WR-010")
    def test_declared_and_absent(self) -> None:
        cs_with = CapabilitySet({Capability.WRITE, Capability.USER_METADATA})
        cs_without = CapabilitySet({Capability.WRITE})
        assert cs_with.supports(Capability.USER_METADATA)
        assert not cs_without.supports(Capability.USER_METADATA)

    @pytest.mark.spec("WR-010")
    def test_require_raises_with_correct_value(self) -> None:
        cs = CapabilitySet({Capability.WRITE})
        with pytest.raises(CapabilityNotSupported, match="user_metadata") as exc_info:
            cs.require(Capability.USER_METADATA, backend="sftp")
        assert exc_info.value.capability == "user_metadata"
