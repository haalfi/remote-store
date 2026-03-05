"""Tests for configuration — derived from sdd/specs/002-registry-config.md (CFG sections)."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store._config import (
    BackendConfig,
    RegistryConfig,
    Secret,
    SecretRedactionFilter,
    StoreProfile,
    _reveal,
)


class TestBackendConfig:
    """CFG-001: BackendConfig."""

    @pytest.mark.spec("CFG-001")
    def test_fields(self) -> None:
        bc = BackendConfig(type="s3", options={"bucket": "my-bucket"})
        assert bc.type == "s3"
        assert bc.options == {"bucket": "my-bucket"}

    @pytest.mark.spec("CFG-001")
    def test_defaults(self) -> None:
        bc = BackendConfig(type="local")
        assert bc.options == {}


class TestStoreProfile:
    """CFG-002: StoreProfile."""

    @pytest.mark.spec("CFG-002")
    def test_fields(self) -> None:
        sp = StoreProfile(backend="local", root_path="data", options={"key": "val"})
        assert sp.backend == "local"
        assert sp.root_path == "data"
        assert sp.options == {"key": "val"}

    @pytest.mark.spec("CFG-002")
    def test_defaults(self) -> None:
        sp = StoreProfile(backend="local")
        assert sp.root_path == ""
        assert sp.options == {}


class TestRegistryConfig:
    """CFG-003: RegistryConfig."""

    @pytest.mark.spec("CFG-003")
    def test_fields(self) -> None:
        rc = RegistryConfig(
            backends={"local": BackendConfig(type="local")},
            stores={"main": StoreProfile(backend="local")},
        )
        assert "local" in rc.backends
        assert "main" in rc.stores


class TestRegistryConfigValidation:
    """CFG-004: validate() checks store references."""

    @pytest.mark.spec("CFG-004")
    def test_validate_passes(self) -> None:
        rc = RegistryConfig(
            backends={"local": BackendConfig(type="local")},
            stores={"main": StoreProfile(backend="local")},
        )
        rc.validate()

    @pytest.mark.spec("CFG-004")
    def test_validate_fails_missing_backend(self) -> None:
        rc = RegistryConfig(
            backends={},
            stores={"main": StoreProfile(backend="nonexistent")},
        )
        with pytest.raises(ValueError, match="nonexistent"):
            rc.validate()


class TestRegistryConfigFromDict:
    """CFG-005: from_dict() construction."""

    @pytest.mark.spec("CFG-005")
    def test_from_dict(self) -> None:
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
    def test_from_dict_minimal(self) -> None:
        rc = RegistryConfig.from_dict({"backends": {}, "stores": {}})
        assert rc.backends == {}
        assert rc.stores == {}


class TestConfigImmutability:
    """CFG-006: Config objects are immutable."""

    @pytest.mark.spec("CFG-006")
    def test_backend_config_frozen(self) -> None:
        bc = BackendConfig(type="local")
        with pytest.raises(dataclasses.FrozenInstanceError):
            bc.type = "s3"  # type: ignore[misc]

    @pytest.mark.spec("CFG-006")
    def test_store_profile_frozen(self) -> None:
        sp = StoreProfile(backend="local")
        with pytest.raises(dataclasses.FrozenInstanceError):
            sp.backend = "s3"  # type: ignore[misc]

    @pytest.mark.spec("CFG-006")
    def test_registry_config_frozen(self) -> None:
        rc = RegistryConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            rc.backends = {}  # type: ignore[misc]


# region: Secret wrapper tests (SEC-001, SEC-002)


class TestSecret:
    """SEC-001: Secret class basics — reveal, repr, str, eq, hash, bool."""

    @pytest.mark.spec("SEC-001")
    def test_reveal(self) -> None:
        s = Secret("my-key")
        assert s.reveal() == "my-key"

    @pytest.mark.spec("SEC-001")
    def test_repr_masked(self) -> None:
        s = Secret("super-secret")
        assert repr(s) == "Secret('***')"
        assert "super-secret" not in repr(s)

    @pytest.mark.spec("SEC-001")
    def test_str_masked(self) -> None:
        s = Secret("super-secret")
        assert str(s) == "***"
        assert "super-secret" not in str(s)

    @pytest.mark.spec("SEC-001")
    def test_eq_same_value(self) -> None:
        assert Secret("abc") == Secret("abc")

    @pytest.mark.spec("SEC-001")
    def test_eq_different_value(self) -> None:
        assert Secret("abc") != Secret("xyz")

    @pytest.mark.spec("SEC-001")
    def test_eq_not_implemented_for_str(self) -> None:
        assert Secret("abc") != "abc"

    @pytest.mark.spec("SEC-001")
    def test_hash(self) -> None:
        a = Secret("abc")
        b = Secret("abc")
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    @pytest.mark.spec("SEC-001")
    def test_bool_truthy(self) -> None:
        assert Secret("x")

    @pytest.mark.spec("SEC-001")
    def test_bool_falsy(self) -> None:
        assert not Secret("")

    @pytest.mark.spec("SEC-001")
    def test_type_check_rejects_non_str(self) -> None:
        with pytest.raises(TypeError, match="str"):
            Secret(123)  # type: ignore[arg-type]

    @pytest.mark.spec("SEC-002")
    def test_immutability(self) -> None:
        s = Secret("abc")
        with pytest.raises(AttributeError):
            s._value = "new"  # type: ignore[misc]

    @pytest.mark.spec("SEC-002")
    def test_immutability_new_attr(self) -> None:
        s = Secret("abc")
        with pytest.raises(AttributeError):
            s.foo = "bar"  # type: ignore[attr-defined]

    @pytest.mark.spec("SEC-002")
    def test_immutability_delattr(self) -> None:
        s = Secret("abc")
        with pytest.raises(AttributeError):
            del s._value  # type: ignore[misc]

    @pytest.mark.spec("SEC-002")
    def test_pickle_roundtrip(self) -> None:
        import pickle

        s = Secret("roundtrip")
        restored = pickle.loads(pickle.dumps(s))
        assert isinstance(restored, Secret)
        assert restored.reveal() == "roundtrip"

    @pytest.mark.spec("SEC-002")
    def test_deepcopy(self) -> None:
        import copy

        s = Secret("deep")
        cloned = copy.deepcopy(s)
        assert isinstance(cloned, Secret)
        assert cloned.reveal() == "deep"

    @pytest.mark.spec("SEC-001")
    def test_not_iterable(self) -> None:
        s = Secret("abc")
        with pytest.raises(TypeError):
            list(s)  # type: ignore[call-overload]

    @pytest.mark.spec("SEC-001")
    def test_not_subscriptable(self) -> None:
        s = Secret("abc")
        with pytest.raises(TypeError):
            s[0]  # type: ignore[index]

    @pytest.mark.spec("SEC-001")
    def test_no_len(self) -> None:
        s = Secret("abc")
        with pytest.raises(TypeError):
            len(s)  # type: ignore[arg-type]


class TestRevealHelper:
    """_reveal() helper function."""

    def test_reveal_secret(self) -> None:
        assert _reveal(Secret("x")) == "x"

    def test_reveal_str(self) -> None:
        assert _reveal("plain") == "plain"

    def test_reveal_none(self) -> None:
        assert _reveal(None) is None


# endregion


# region: from_dict() wrapping tests (SEC-003, SEC-006, SEC-008)


class TestFromDictSecretWrapping:
    """SEC-003: from_dict() wraps _SENSITIVE_KEYS in Secret."""

    @pytest.mark.spec("SEC-003")
    def test_s3_keys_wrapped(self) -> None:
        data = {
            "backends": {
                "s3": {
                    "type": "s3",
                    "options": {
                        "bucket": "my-bucket",
                        "key": "AKID123",
                        "secret": "SK456",
                    },
                }
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret)
        assert isinstance(opts["secret"], Secret)
        assert opts["key"].reveal() == "AKID123"  # type: ignore[union-attr]
        assert opts["secret"].reveal() == "SK456"  # type: ignore[union-attr]
        # Non-sensitive keys are NOT wrapped
        assert opts["bucket"] == "my-bucket"
        assert not isinstance(opts["bucket"], Secret)

    @pytest.mark.spec("SEC-003")
    def test_azure_keys_wrapped(self) -> None:
        data = {
            "backends": {
                "az": {
                    "type": "azure",
                    "options": {
                        "container": "c",
                        "account_name": "acct",
                        "account_key": "mykey",
                        "sas_token": "tok",
                        "connection_string": "conn=str",
                    },
                }
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        opts = rc.backends["az"].options
        assert isinstance(opts["account_key"], Secret)
        assert isinstance(opts["sas_token"], Secret)
        assert isinstance(opts["connection_string"], Secret)
        assert not isinstance(opts["container"], Secret)
        assert not isinstance(opts["account_name"], Secret)

    @pytest.mark.spec("SEC-003")
    def test_sftp_password_wrapped(self) -> None:
        data = {
            "backends": {
                "sftp": {
                    "type": "sftp",
                    "options": {
                        "host": "h",
                        "password": "secret123",
                    },
                }
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        opts = rc.backends["sftp"].options
        assert isinstance(opts["password"], Secret)
        assert opts["password"].reveal() == "secret123"  # type: ignore[union-attr]

    @pytest.mark.spec("SEC-003")
    def test_non_string_value_not_wrapped(self) -> None:
        """Non-string values (e.g. int, None, object) for sensitive keys are left as-is."""
        sentinel = object()
        data = {
            "backends": {
                "b": {
                    "type": "s3",
                    "options": {"key": sentinel, "bucket": "b"},
                }
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        assert rc.backends["b"].options["key"] is sentinel

    @pytest.mark.spec("SEC-006")
    @pytest.mark.spec("SEC-008")
    def test_repr_no_leak(self) -> None:
        """repr(BackendConfig) must not leak secret values."""
        data = {
            "backends": {
                "s3": {
                    "type": "s3",
                    "options": {"bucket": "b", "key": "AKID_TEST", "secret": "SK_TEST"},
                }
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        r = repr(rc.backends["s3"])
        assert "AKID_TEST" not in r
        assert "SK_TEST" not in r
        assert "Secret('***')" in r


# endregion


# region: SFTP enum coercion (SEC-005)


class TestSFTPEnumCoercion:
    """SEC-005: SFTP coerces host_key_policy string to HostKeyPolicy enum."""

    @pytest.mark.spec("SEC-005")
    def test_string_to_enum(self) -> None:
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        backend = SFTPBackend(host="h", host_key_policy="auto")
        assert backend._host_key_policy is HostKeyPolicy.AUTO_ADD

    @pytest.mark.spec("SEC-005")
    def test_string_tofu(self) -> None:
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        backend = SFTPBackend(host="h", host_key_policy="tofu")
        assert backend._host_key_policy is HostKeyPolicy.TRUST_ON_FIRST_USE

    @pytest.mark.spec("SEC-005")
    def test_string_strict(self) -> None:
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        backend = SFTPBackend(host="h", host_key_policy="strict")
        assert backend._host_key_policy is HostKeyPolicy.STRICT

    @pytest.mark.spec("SEC-005")
    def test_invalid_string_raises(self) -> None:
        from remote_store.backends._sftp import SFTPBackend

        with pytest.raises(ValueError, match="not_a_policy"):
            SFTPBackend(host="h", host_key_policy="not_a_policy")

    @pytest.mark.spec("SEC-005")
    def test_enum_passthrough(self) -> None:
        from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

        backend = SFTPBackend(host="h", host_key_policy=HostKeyPolicy.AUTO_ADD)
        assert backend._host_key_policy is HostKeyPolicy.AUTO_ADD


# endregion


# region: SecretRedactionFilter (SEC-007)


class TestSecretRedactionFilter:
    """SEC-007: SecretRedactionFilter scrubs Secret instances in log record args."""

    @pytest.mark.spec("SEC-007")
    def test_tuple_args_redacted(self) -> None:
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="key=%s secret=%s",
            args=(Secret("AKID"), Secret("SK")),
            exc_info=None,
        )
        filt.filter(record)
        assert record.args == ("***", "***")

    @pytest.mark.spec("SEC-007")
    def test_dict_args_redacted(self) -> None:
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="key=%(key)s",
            args={"key": Secret("AKID"), "name": "safe"},
            exc_info=None,
        )
        filt.filter(record)
        assert record.args == {"key": "***", "name": "safe"}  # type: ignore[comparison-overlap]

    @pytest.mark.spec("SEC-007")
    def test_non_secret_args_unchanged(self) -> None:
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="val=%s",
            args=("plain",),
            exc_info=None,
        )
        filt.filter(record)
        assert record.args == ("plain",)

    @pytest.mark.spec("SEC-007")
    def test_filter_returns_true(self) -> None:
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="no args",
            args=None,
            exc_info=None,
        )
        assert filt.filter(record) is True


# endregion


# region: Config loaders (CFG-008 through CFG-014)


class TestFromToml:
    """CFG-008, CFG-009: from_toml() loads config from TOML files."""

    @pytest.mark.spec("CFG-008")
    def test_from_toml_standalone(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            '[backends.local]\ntype = "local"\n\n'
            "[backends.local.options]\n"
            'root = "/data"\n\n'
            "[stores.main]\n"
            'backend = "local"\n'
            'root_path = "data"\n'
        )
        rc = RegistryConfig.from_toml(toml_file)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"
        assert rc.stores["main"].root_path == "data"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_with_table(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "pyproject.toml"
        toml_file.write_text(
            "[tool.remote-store.backends.mem]\n"
            'type = "memory"\n\n'
            "[tool.remote-store.stores.scratch]\n"
            'backend = "mem"\n'
            'root_path = "tmp"\n'
        )
        rc = RegistryConfig.from_toml(toml_file, table=("tool", "remote-store"))
        assert rc.backends["mem"].type == "memory"
        assert rc.stores["scratch"].root_path == "tmp"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_table_key_not_found(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("[other]\nfoo = 1\n")
        with pytest.raises(KeyError, match="tool"):
            RegistryConfig.from_toml(toml_file, table=("tool", "remote-store"))

    @pytest.mark.spec("CFG-008")
    def test_from_toml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            RegistryConfig.from_toml("/nonexistent/config.toml")

    @pytest.mark.spec("CFG-008")
    def test_from_toml_secret_wrapping(self, tmp_path: Path) -> None:
        """Secrets in TOML are auto-wrapped via from_dict() delegation."""
        toml_file = tmp_path / "creds.toml"
        toml_file.write_text(
            '[backends.s3]\ntype = "s3"\n\n[backends.s3.options]\nbucket = "b"\nkey = "AKID"\nsecret = "SK"\n'
        )
        rc = RegistryConfig.from_toml(toml_file)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret)
        assert isinstance(opts["secret"], Secret)
        assert not isinstance(opts["bucket"], Secret)

    @pytest.mark.spec("CFG-013")
    def test_from_toml_equivalence_with_from_dict(self, tmp_path: Path) -> None:
        """from_toml() produces identical config to from_dict() for same data."""
        toml_file = tmp_path / "eq.toml"
        toml_file.write_text(
            '[backends.local]\ntype = "local"\n\n'
            "[backends.local.options]\n"
            'root = "/tmp"\n\n'
            "[stores.data]\n"
            'backend = "local"\n'
            'root_path = "d"\n'
        )
        from_toml = RegistryConfig.from_toml(toml_file)
        from_dict = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"data": {"backend": "local", "root_path": "d"}},
            }
        )
        assert from_toml.backends["local"].type == from_dict.backends["local"].type
        assert from_toml.stores["data"].root_path == from_dict.stores["data"].root_path

    @pytest.mark.spec("CFG-008")
    def test_from_toml_accepts_path_object(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "p.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        rc = RegistryConfig.from_toml(toml_file)
        assert rc.backends["m"].type == "memory"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_accepts_str_path(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "s.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        rc = RegistryConfig.from_toml(str(toml_file))
        assert rc.backends["m"].type == "memory"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_invalid_toml(self, tmp_path: Path) -> None:
        """Malformed TOML raises TOMLDecodeError."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        bad = tmp_path / "bad.toml"
        bad.write_text("[invalid\n")
        with pytest.raises(tomllib.TOMLDecodeError):
            RegistryConfig.from_toml(bad)


class TestFromYaml:
    """CFG-010, CFG-011: from_yaml() loads config from YAML files."""

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_basic(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "backends:\n"
            "  local:\n"
            '    type: "local"\n'
            "    options:\n"
            '      root: "/data"\n'
            "stores:\n"
            "  main:\n"
            '    backend: "local"\n'
            '    root_path: "data"\n'
        )
        rc = RegistryConfig.from_yaml(yaml_file)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            RegistryConfig.from_yaml("/nonexistent/config.yaml")

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_not_a_mapping(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(TypeError, match="mapping"):
            RegistryConfig.from_yaml(yaml_file)

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_invalid_yaml(self, tmp_path: Path) -> None:
        """Malformed YAML raises yaml.YAMLError."""
        from yaml import YAMLError

        bad = tmp_path / "bad.yaml"
        bad.write_text(":\n  - [unterminated\n")
        with pytest.raises(YAMLError):
            RegistryConfig.from_yaml(bad)

    @pytest.mark.spec("CFG-010")
    def test_from_yaml_secret_wrapping(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "creds.yaml"
        yaml_file.write_text(
            "backends:\n"
            "  s3:\n"
            "    type: s3\n"
            "    options:\n"
            "      bucket: b\n"
            "      key: AKID\n"
            "      secret: SK\n"
            "stores: {}\n"
        )
        rc = RegistryConfig.from_yaml(yaml_file)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret)
        assert isinstance(opts["secret"], Secret)

    @pytest.mark.spec("CFG-013")
    def test_from_yaml_equivalence_with_from_dict(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "eq.yaml"
        yaml_file.write_text(
            "backends:\n"
            "  local:\n"
            "    type: local\n"
            "    options:\n"
            "      root: /tmp\n"
            "stores:\n"
            "  data:\n"
            "    backend: local\n"
            "    root_path: d\n"
        )
        from_yaml = RegistryConfig.from_yaml(yaml_file)
        from_dict = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"data": {"backend": "local", "root_path": "d"}},
            }
        )
        assert from_yaml.backends["local"].type == from_dict.backends["local"].type
        assert from_yaml.stores["data"].root_path == from_dict.stores["data"].root_path


class TestUnknownKeyWarning:
    """CFG-012: from_dict() warns on unknown top-level keys."""

    @pytest.mark.spec("CFG-012")
    def test_unknown_key_warns(self) -> None:
        with pytest.warns(UserWarning, match="Unknown top-level config keys"):
            RegistryConfig.from_dict({"backends": {}, "stores": {}, "backend": {"typo": True}})

    @pytest.mark.spec("CFG-012")
    def test_known_keys_no_warning(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            RegistryConfig.from_dict({"backends": {}, "stores": {}})

    @pytest.mark.spec("CFG-012")
    def test_empty_dict_no_warning(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            RegistryConfig.from_dict({})


# endregion


# region: Config loader fallback paths (CFG-008, CFG-009, CFG-010, CFG-011)


class TestFromTomlFallbacks:
    """Tests for optional-dependency fallback paths in from_toml()."""

    @pytest.mark.spec("CFG-009")
    def test_tomli_fallback_when_tomllib_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When tomllib is unavailable, from_toml() falls back to tomli."""
        import sys

        try:
            import tomli  # noqa: F401
        except ImportError:
            pytest.skip("tomli not installed — fallback path cannot be exercised")

        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')

        # Hide tomllib so the fallback branch runs
        monkeypatch.setitem(sys.modules, "tomllib", None)
        rc = RegistryConfig.from_toml(toml_file)
        assert rc.backends["m"].type == "memory"

    @pytest.mark.spec("CFG-009")
    def test_no_toml_lib_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When neither tomllib nor tomli is available, from_toml() raises."""
        import sys

        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')

        monkeypatch.setitem(sys.modules, "tomllib", None)
        monkeypatch.setitem(sys.modules, "tomli", None)
        with pytest.raises(ModuleNotFoundError, match="tomli"):
            RegistryConfig.from_toml(toml_file)

    @pytest.mark.spec("CFG-008")
    def test_from_toml_non_dict_table_value(self, tmp_path: Path) -> None:
        """TypeError when table path resolves to a non-dict value."""
        toml_file = tmp_path / "scalar.toml"
        toml_file.write_text('[tool]\nremote-store = "not a table"\n')
        with pytest.raises(TypeError, match="Expected a TOML table"):
            RegistryConfig.from_toml(toml_file, table=("tool", "remote-store"))


class TestFromYamlFallbacks:
    """Tests for optional-dependency fallback paths in from_yaml() / _get_yaml_loader()."""

    @pytest.mark.spec("CFG-011")
    def test_ruamel_fallback_when_pyyaml_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When pyyaml is unavailable, from_yaml() falls back to ruamel.yaml."""
        import sys

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("backends:\n  m:\n    type: memory\nstores: {}\n")

        # Block pyyaml so _get_yaml_loader tries ruamel
        monkeypatch.setitem(sys.modules, "yaml", None)

        try:
            from ruamel.yaml import YAML  # noqa: F401

            ruamel_available = True
        except ImportError:
            ruamel_available = False

        if not ruamel_available:
            pytest.skip("ruamel.yaml not installed")

        from remote_store._config import _get_yaml_loader

        loader = _get_yaml_loader()
        with open(yaml_file, encoding="utf-8") as f:
            data = loader(f)
        assert isinstance(data, dict)
        assert data["backends"]["m"]["type"] == "memory"

    @pytest.mark.spec("CFG-011")
    def test_no_yaml_lib_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When neither pyyaml nor ruamel.yaml is available, raises ModuleNotFoundError."""
        import sys

        monkeypatch.setitem(sys.modules, "yaml", None)
        monkeypatch.setitem(sys.modules, "ruamel", None)
        monkeypatch.setitem(sys.modules, "ruamel.yaml", None)

        from remote_store._config import _get_yaml_loader

        with pytest.raises(ModuleNotFoundError, match="pyyaml or ruamel"):
            _get_yaml_loader()


# endregion
