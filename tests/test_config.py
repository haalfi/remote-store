"""Tests for configuration — derived from sdd/specs/002-registry-config.md (CFG sections)."""

from __future__ import annotations

import dataclasses
import logging

import pytest

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
