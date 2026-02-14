"""Tests for capabilities — derived from docs/specs/capabilities.md."""

from __future__ import annotations

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported

# -- CAP-001: Enum members --


@pytest.mark.spec("CAP-001")
def test_capability_members() -> None:
    expected = {"READ", "WRITE", "DELETE", "LIST", "MOVE", "COPY", "ATOMIC_WRITE", "GLOB", "RECURSIVE_LIST", "METADATA"}
    actual = {c.name for c in Capability}
    assert actual == expected


# -- CAP-002: Construction --


@pytest.mark.spec("CAP-002")
def test_capabilityset_construction() -> None:
    cs = CapabilitySet({Capability.READ, Capability.WRITE})
    assert len(cs) == 2


# -- CAP-003: supports() --


@pytest.mark.spec("CAP-003")
def test_supports_true() -> None:
    cs = CapabilitySet({Capability.READ})
    assert cs.supports(Capability.READ) is True


@pytest.mark.spec("CAP-003")
def test_supports_false() -> None:
    cs = CapabilitySet({Capability.READ})
    assert cs.supports(Capability.WRITE) is False


# -- CAP-004: require() --


@pytest.mark.spec("CAP-004")
def test_require_passes() -> None:
    cs = CapabilitySet({Capability.READ})
    cs.require(Capability.READ)  # Should not raise


@pytest.mark.spec("CAP-004")
def test_require_raises() -> None:
    cs = CapabilitySet({Capability.READ})
    with pytest.raises(CapabilityNotSupported) as exc_info:
        cs.require(Capability.WRITE, backend="test")
    assert exc_info.value.capability == "write"


# -- CAP-005: Iteration and membership --


@pytest.mark.spec("CAP-005")
def test_contains() -> None:
    cs = CapabilitySet({Capability.READ, Capability.WRITE})
    assert Capability.READ in cs
    assert Capability.DELETE not in cs


@pytest.mark.spec("CAP-005")
def test_iteration() -> None:
    caps = {Capability.READ, Capability.WRITE}
    cs = CapabilitySet(caps)
    assert set(cs) == caps


# -- CAP-006: Immutability --


@pytest.mark.spec("CAP-006")
def test_immutable_setattr() -> None:
    cs = CapabilitySet({Capability.READ})
    with pytest.raises(AttributeError, match="immutable"):
        cs.x = 1  # type: ignore[attr-defined]


@pytest.mark.spec("CAP-006")
def test_immutable_delattr() -> None:
    cs = CapabilitySet({Capability.READ})
    with pytest.raises(AttributeError, match="immutable"):
        del cs._caps  # type: ignore[attr-defined]
