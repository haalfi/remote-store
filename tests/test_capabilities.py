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
