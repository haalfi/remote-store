"""Tests for configuration — derived from docs/specs/config.md."""

from __future__ import annotations

import dataclasses

import pytest

from remote_store._config import BackendConfig, RegistryConfig, StoreProfile

# -- CFG-001: BackendConfig --


@pytest.mark.spec("CFG-001")
def test_backend_config_fields() -> None:
    bc = BackendConfig(type="s3", options={"bucket": "my-bucket"})
    assert bc.type == "s3"
    assert bc.options == {"bucket": "my-bucket"}


@pytest.mark.spec("CFG-001")
def test_backend_config_defaults() -> None:
    bc = BackendConfig(type="local")
    assert bc.options == {}


# -- CFG-002: StoreProfile --


@pytest.mark.spec("CFG-002")
def test_store_profile_fields() -> None:
    sp = StoreProfile(backend="local", root_path="data", options={"key": "val"})
    assert sp.backend == "local"
    assert sp.root_path == "data"
    assert sp.options == {"key": "val"}


@pytest.mark.spec("CFG-002")
def test_store_profile_defaults() -> None:
    sp = StoreProfile(backend="local")
    assert sp.root_path == ""
    assert sp.options == {}


# -- CFG-003: RegistryConfig --


@pytest.mark.spec("CFG-003")
def test_registry_config_fields() -> None:
    rc = RegistryConfig(
        backends={"local": BackendConfig(type="local")},
        stores={"main": StoreProfile(backend="local")},
    )
    assert "local" in rc.backends
    assert "main" in rc.stores


# -- CFG-004: Validation --


@pytest.mark.spec("CFG-004")
def test_validate_passes() -> None:
    rc = RegistryConfig(
        backends={"local": BackendConfig(type="local")},
        stores={"main": StoreProfile(backend="local")},
    )
    rc.validate()  # Should not raise


@pytest.mark.spec("CFG-004")
def test_validate_fails_missing_backend() -> None:
    rc = RegistryConfig(
        backends={},
        stores={"main": StoreProfile(backend="nonexistent")},
    )
    with pytest.raises(ValueError, match="nonexistent"):
        rc.validate()


# -- CFG-005: from_dict --


@pytest.mark.spec("CFG-005")
def test_from_dict() -> None:
    data = {
        "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
        "stores": {"main": {"backend": "local", "root_path": "data"}},
    }
    rc = RegistryConfig.from_dict(data)
    assert rc.backends["local"].type == "local"
    assert rc.backends["local"].options == {"root": "/tmp"}
    assert rc.stores["main"].backend == "local"
    assert rc.stores["main"].root_path == "data"


@pytest.mark.spec("CFG-005")
def test_from_dict_minimal() -> None:
    rc = RegistryConfig.from_dict({"backends": {}, "stores": {}})
    assert rc.backends == {}
    assert rc.stores == {}


# -- CFG-006: Immutability --


@pytest.mark.spec("CFG-006")
def test_backend_config_frozen() -> None:
    bc = BackendConfig(type="local")
    with pytest.raises(dataclasses.FrozenInstanceError):
        bc.type = "s3"  # type: ignore[misc]


@pytest.mark.spec("CFG-006")
def test_store_profile_frozen() -> None:
    sp = StoreProfile(backend="local")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sp.backend = "s3"  # type: ignore[misc]


@pytest.mark.spec("CFG-006")
def test_registry_config_frozen() -> None:
    rc = RegistryConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rc.backends = {}  # type: ignore[misc]
