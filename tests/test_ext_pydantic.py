"""Tests for ext.pydantic — derived from sdd/specs/021-config-loaders.md (CFG-015 through CFG-017)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from remote_store._config import RegistryConfig, Secret
from remote_store.ext.pydantic import pydantic_to_registry_config


class BackendEntry(BaseModel):
    type: str
    options: dict[str, Any] = {}


class StoreEntry(BaseModel):
    backend: str
    root_path: str = ""
    options: dict[str, Any] = {}


class SimpleConfig(BaseModel):
    backends: dict[str, BackendEntry] = {}
    stores: dict[str, StoreEntry] = {}


class TestPydanticToRegistryConfig:
    """CFG-015: pydantic_to_registry_config() converts BaseModel to RegistryConfig."""

    @pytest.mark.spec("CFG-015")
    def test_basic_conversion(self) -> None:
        model = SimpleConfig(
            backends={"local": BackendEntry(type="local", options={"root": "/data"})},
            stores={"main": StoreEntry(backend="local", root_path="data")},
        )
        rc = pydantic_to_registry_config(model)
        assert isinstance(rc, RegistryConfig)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"
        assert rc.stores["main"].root_path == "data"

    @pytest.mark.spec("CFG-015")
    def test_empty_config(self) -> None:
        model = SimpleConfig()
        rc = pydantic_to_registry_config(model)
        assert rc.backends == {}
        assert rc.stores == {}

    @pytest.mark.spec("CFG-015")
    def test_secret_wrapping(self) -> None:
        """Sensitive keys in options are wrapped in Secret by from_dict()."""
        model = SimpleConfig(
            backends={
                "s3": BackendEntry(
                    type="s3",
                    options={"bucket": "b", "key": "AKID", "secret": "SK"},
                )
            },
            stores={},
        )
        rc = pydantic_to_registry_config(model)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret)
        assert isinstance(opts["secret"], Secret)
        assert opts["key"].reveal() == "AKID"  # type: ignore[union-attr]
        assert opts["secret"].reveal() == "SK"  # type: ignore[union-attr]
        assert not isinstance(opts["bucket"], Secret)

    @pytest.mark.spec("CFG-015")
    def test_multiple_backends_and_stores(self) -> None:
        model = SimpleConfig(
            backends={
                "local": BackendEntry(type="local", options={"root": "/data"}),
                "s3": BackendEntry(type="s3", options={"bucket": "prod"}),
            },
            stores={
                "data": StoreEntry(backend="local", root_path="data"),
                "archive": StoreEntry(backend="s3", root_path="archive"),
            },
        )
        rc = pydantic_to_registry_config(model)
        assert len(rc.backends) == 2
        assert len(rc.stores) == 2
        assert rc.backends["local"].type == "local"
        assert rc.backends["s3"].type == "s3"

    @pytest.mark.spec("CFG-013")
    def test_equivalence_with_from_dict(self) -> None:
        """pydantic_to_registry_config() produces identical config to from_dict()."""
        model = SimpleConfig(
            backends={"local": BackendEntry(type="local", options={"root": "/tmp"})},
            stores={"data": StoreEntry(backend="local", root_path="d")},
        )
        from_pydantic = pydantic_to_registry_config(model)
        from_dict = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"data": {"backend": "local", "root_path": "d"}},
            }
        )
        assert from_pydantic.backends["local"].type == from_dict.backends["local"].type
        assert from_pydantic.backends["local"].options == from_dict.backends["local"].options
        assert from_pydantic.stores["data"].root_path == from_dict.stores["data"].root_path

    @pytest.mark.spec("CFG-015")
    def test_unknown_keys_warn(self) -> None:
        """Unknown top-level keys from the model trigger a warning via from_dict()."""

        class ExtraConfig(BaseModel):
            backends: dict[str, BackendEntry] = {}
            stores: dict[str, StoreEntry] = {}
            extra_key: str = "unexpected"

        model = ExtraConfig()
        with pytest.warns(UserWarning, match="Unknown top-level config keys"):
            pydantic_to_registry_config(model)

    @pytest.mark.spec("CFG-015")
    def test_store_options_preserved(self) -> None:
        model = SimpleConfig(
            backends={"mem": BackendEntry(type="memory")},
            stores={
                "main": StoreEntry(
                    backend="mem",
                    root_path="data",
                    options={"custom": "value"},
                )
            },
        )
        rc = pydantic_to_registry_config(model)
        assert rc.stores["main"].options == {"custom": "value"}


class TestPydanticWithBaseSettings:
    """CFG-016: Pydantic BaseSettings integration with env var merging."""

    @pytest.mark.spec("CFG-016")
    def test_base_settings_conversion(self) -> None:
        """BaseSettings model works through pydantic_to_registry_config()."""
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class MySettings(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="RS_TEST_")

            backends: dict[str, BackendEntry] = {
                "mem": BackendEntry(type="memory"),
            }
            stores: dict[str, StoreEntry] = {
                "data": StoreEntry(backend="mem", root_path="test"),
            }

        settings = MySettings()
        rc = pydantic_to_registry_config(settings)
        assert rc.backends["mem"].type == "memory"
        assert rc.stores["data"].root_path == "test"


class TestPydanticExtensionContract:
    """CFG-017: Extension contract — __all__, conditional re-export."""

    @pytest.mark.spec("CFG-017")
    def test_all_defined(self) -> None:
        from remote_store.ext import pydantic

        assert hasattr(pydantic, "__all__")
        assert "pydantic_to_registry_config" in pydantic.__all__

    @pytest.mark.spec("CFG-017")
    def test_top_level_reexport(self) -> None:
        """pydantic_to_registry_config is available from remote_store top level."""
        import remote_store

        assert hasattr(remote_store, "pydantic_to_registry_config")
        assert remote_store.pydantic_to_registry_config is pydantic_to_registry_config
