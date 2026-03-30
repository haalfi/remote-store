"""Tests for ext.pydantic — derived from sdd/specs/021-config-loaders.md (CFG-015 through CFG-017)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from remote_store._config import RegistryConfig, Secret
from remote_store.ext.pydantic import from_pydantic


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
    """CFG-015: from_pydantic() converts BaseModel to RegistryConfig."""

    @pytest.mark.spec("CFG-015")
    def test_basic_conversion(self) -> None:
        model = SimpleConfig(
            backends={"local": BackendEntry(type="local", options={"root": "/data"})},
            stores={"main": StoreEntry(backend="local", root_path="data")},
        )
        rc = from_pydantic(model)
        assert isinstance(rc, RegistryConfig)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"
        assert rc.stores["main"].root_path == "data"

    @pytest.mark.spec("CFG-015")
    def test_empty_config(self) -> None:
        rc = from_pydantic(SimpleConfig())
        assert rc.backends == {}
        assert rc.stores == {}

    @pytest.mark.spec("CFG-015")
    @pytest.mark.parametrize(
        "use_secretstr",
        [
            pytest.param(False, id="plain_string"),
            pytest.param(True, id="pydantic_SecretStr"),
        ],
    )
    def test_secret_wrapping(self, use_secretstr: bool) -> None:
        """Sensitive keys in options are wrapped in Secret by from_dict(), with or without SecretStr."""
        if use_secretstr:
            from pydantic import SecretStr

            key_val: Any = SecretStr("AKID")
            secret_val: Any = SecretStr("SK")
        else:
            key_val = "AKID"
            secret_val = "SK"

        model = SimpleConfig(
            backends={"s3": BackendEntry(type="s3", options={"bucket": "b", "key": key_val, "secret": secret_val})},
            stores={},
        )
        rc = from_pydantic(model)
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
        rc = from_pydantic(model)
        assert len(rc.backends) == 2
        assert len(rc.stores) == 2
        assert rc.backends["local"].type == "local"
        assert rc.backends["s3"].type == "s3"

    @pytest.mark.spec("CFG-013")
    def test_equivalence_with_from_dict(self) -> None:
        model = SimpleConfig(
            backends={"local": BackendEntry(type="local", options={"root": "/tmp"})},
            stores={"data": StoreEntry(backend="local", root_path="d")},
        )
        rc_pydantic = from_pydantic(model)
        rc_dict = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"data": {"backend": "local", "root_path": "d"}},
            }
        )
        assert rc_pydantic.backends["local"].type == rc_dict.backends["local"].type
        assert rc_pydantic.backends["local"].options == rc_dict.backends["local"].options
        assert rc_pydantic.stores["data"].root_path == rc_dict.stores["data"].root_path

    @pytest.mark.spec("CFG-015")
    def test_unknown_keys_warn(self) -> None:
        class ExtraConfig(BaseModel):
            backends: dict[str, BackendEntry] = {}
            stores: dict[str, StoreEntry] = {}
            extra_key: str = "unexpected"

        with pytest.warns(UserWarning, match="Unknown top-level config keys"):
            result = from_pydantic(ExtraConfig())
        assert result is not None

    @pytest.mark.spec("CFG-015")
    def test_store_options_preserved(self) -> None:
        model = SimpleConfig(
            backends={"mem": BackendEntry(type="memory")},
            stores={"main": StoreEntry(backend="mem", root_path="data", options={"custom": "value"})},
        )
        rc = from_pydantic(model)
        assert rc.stores["main"].options == {"custom": "value"}


class TestPydanticBaseSettingsAndContract:
    """CFG-016 / CFG-017: BaseSettings integration and extension contract."""

    @pytest.mark.spec("CFG-016")
    def test_base_settings_conversion(self) -> None:
        from pydantic_settings import BaseSettings, SettingsConfigDict

        class MySettings(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="RS_TEST_")
            backends: dict[str, BackendEntry] = {"mem": BackendEntry(type="memory")}
            stores: dict[str, StoreEntry] = {"data": StoreEntry(backend="mem", root_path="test")}

        rc = from_pydantic(MySettings())
        assert rc.backends["mem"].type == "memory"
        assert rc.stores["data"].root_path == "test"

    @pytest.mark.spec("CFG-017")
    def test_all_defined(self) -> None:
        from remote_store.ext import pydantic

        assert hasattr(pydantic, "__all__")
        assert "from_pydantic" in pydantic.__all__

    @pytest.mark.spec("CFG-017")
    def test_no_top_level_reexport(self) -> None:
        import remote_store

        assert not hasattr(remote_store, "from_pydantic")
