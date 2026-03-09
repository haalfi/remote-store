"""Tests for configuration -- derived from sdd/specs/002-registry-config.md (CFG sections)."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store._config import (
    BackendConfig,
    RegistryConfig,
    RetryPolicy,
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
        assert bc.type == "s3" and bc.options == {"bucket": "my-bucket"}

    @pytest.mark.spec("CFG-001")
    def test_defaults(self) -> None:
        assert BackendConfig(type="local").options == {}


class TestStoreProfile:
    """CFG-002: StoreProfile."""

    @pytest.mark.spec("CFG-002")
    def test_fields(self) -> None:
        sp = StoreProfile(backend="local", root_path="data", options={"key": "val"})
        assert sp.backend == "local" and sp.root_path == "data" and sp.options == {"key": "val"}

    @pytest.mark.spec("CFG-002")
    def test_defaults(self) -> None:
        sp = StoreProfile(backend="local")
        assert sp.root_path == "" and sp.options == {}


class TestRegistryConfig:
    """CFG-003: RegistryConfig."""

    @pytest.mark.spec("CFG-003")
    def test_fields(self) -> None:
        rc = RegistryConfig(
            backends={"local": BackendConfig(type="local")},
            stores={"main": StoreProfile(backend="local")},
        )
        assert "local" in rc.backends and "main" in rc.stores


class TestRegistryConfigValidation:
    """CFG-004: validate() checks store references."""

    @pytest.mark.spec("CFG-004")
    def test_validate_passes(self) -> None:
        RegistryConfig(
            backends={"local": BackendConfig(type="local")},
            stores={"main": StoreProfile(backend="local")},
        ).validate()

    @pytest.mark.spec("CFG-004")
    def test_validate_fails_missing_backend(self) -> None:
        rc = RegistryConfig(backends={}, stores={"main": StoreProfile(backend="nonexistent")})
        with pytest.raises(ValueError, match="nonexistent"):
            rc.validate()


class TestRegistryConfigFromDict:
    """CFG-005: from_dict() construction."""

    @pytest.mark.spec("CFG-005")
    def test_from_dict(self) -> None:
        rc = RegistryConfig.from_dict(
            {
                "backends": {"local": {"type": "local", "options": {"root": "/tmp"}}},
                "stores": {"main": {"backend": "local", "root_path": "data"}},
            }
        )
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options == {"root": "/tmp"}
        assert rc.stores["main"].backend == "local"
        assert rc.stores["main"].root_path == "data"

    @pytest.mark.spec("CFG-005")
    def test_from_dict_minimal(self) -> None:
        rc = RegistryConfig.from_dict({"backends": {}, "stores": {}})
        assert rc.backends == {} and rc.stores == {}


# -- CFG-006: Immutability (parametrized) --

_FROZEN_CASES = [
    pytest.param(lambda: BackendConfig(type="local"), "type", "s3", id="BackendConfig"),
    pytest.param(lambda: StoreProfile(backend="local"), "backend", "s3", id="StoreProfile"),
    pytest.param(lambda: RegistryConfig(), "backends", {}, id="RegistryConfig"),
]


@pytest.mark.spec("CFG-006")
@pytest.mark.parametrize("factory,attr,value", _FROZEN_CASES)
def test_config_immutability(factory: Any, attr: str, value: Any) -> None:
    obj = factory()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, attr, value)


# region: Secret wrapper tests (SEC-001, SEC-002)


class TestSecret:
    """SEC-001, SEC-002: Secret class -- reveal, repr, str, eq, hash, bool, immutability."""

    @pytest.mark.spec("SEC-001")
    def test_reveal(self) -> None:
        assert Secret("my-key").reveal() == "my-key"

    @pytest.mark.spec("SEC-001")
    def test_repr_masked(self) -> None:
        s = Secret("super-secret")
        assert repr(s) == "Secret('***')" and "super-secret" not in repr(s)

    @pytest.mark.spec("SEC-001")
    def test_str_masked(self) -> None:
        s = Secret("super-secret")
        assert str(s) == "***" and "super-secret" not in str(s)

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize(
        "a,b,equal",
        [("abc", "abc", True), ("abc", "xyz", False)],
        ids=["same", "different"],
    )
    def test_eq(self, a: str, b: str, equal: bool) -> None:
        assert (Secret(a) == Secret(b)) is equal

    @pytest.mark.spec("SEC-001")
    def test_eq_not_implemented_for_str(self) -> None:
        assert Secret("abc") != "abc"

    @pytest.mark.spec("SEC-001")
    def test_hash(self) -> None:
        a, b = Secret("abc"), Secret("abc")
        assert hash(a) == hash(b) and {a, b} == {a}

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize("val,expected", [("x", True), ("", False)], ids=["truthy", "falsy"])
    def test_bool(self, val: str, expected: bool) -> None:
        assert bool(Secret(val)) is expected

    @pytest.mark.spec("SEC-001")
    def test_type_check_rejects_non_str(self) -> None:
        with pytest.raises(TypeError, match="str"):
            Secret(123)  # type: ignore[arg-type]

    @pytest.mark.spec("SEC-002")
    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: setattr(s, "_value", "new"), id="setattr_existing"),
            pytest.param(lambda s: setattr(s, "foo", "bar"), id="setattr_new"),
            pytest.param(lambda s: delattr(s, "_value"), id="delattr"),
        ],
    )
    def test_immutability(self, action: Any) -> None:
        with pytest.raises(AttributeError):
            action(Secret("abc"))

    @pytest.mark.spec("SEC-002")
    def test_pickle_roundtrip(self) -> None:
        import pickle

        restored = pickle.loads(pickle.dumps(Secret("roundtrip")))
        assert isinstance(restored, Secret) and restored.reveal() == "roundtrip"

    @pytest.mark.spec("SEC-002")
    def test_deepcopy(self) -> None:
        import copy

        cloned = copy.deepcopy(Secret("deep"))
        assert isinstance(cloned, Secret) and cloned.reveal() == "deep"

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize(
        "action",
        [
            pytest.param(lambda s: list(s), id="not_iterable"),
            pytest.param(lambda s: s[0], id="not_subscriptable"),
            pytest.param(lambda s: len(s), id="no_len"),
        ],
    )
    def test_unsupported_operations(self, action: Any) -> None:
        with pytest.raises(TypeError):
            action(Secret("abc"))


# -- _reveal() helper --


@pytest.mark.parametrize(
    "inp,expected",
    [(Secret("x"), "x"), ("plain", "plain"), (None, None)],
    ids=["secret", "str", "none"],
)
def test_reveal_helper(inp: Any, expected: Any) -> None:
    assert _reveal(inp) == expected


# endregion


# region: from_dict() wrapping tests (SEC-003, SEC-006, SEC-008)


class TestFromDictSecretWrapping:
    """SEC-003: from_dict() wraps _SENSITIVE_KEYS in Secret."""

    @pytest.mark.spec("SEC-003")
    @pytest.mark.parametrize(
        "backend_type,options,secret_keys,non_secret_keys",
        [
            ("s3", {"bucket": "b", "key": "AKID", "secret": "SK"}, ["key", "secret"], ["bucket"]),
            (
                "azure",
                {"container": "c", "account_name": "a", "account_key": "k", "sas_token": "t", "connection_string": "c"},
                ["account_key", "sas_token", "connection_string"],
                ["container", "account_name"],
            ),
            ("sftp", {"host": "h", "password": "p"}, ["password"], ["host"]),
        ],
        ids=["s3", "azure", "sftp"],
    )
    def test_keys_wrapped(
        self,
        backend_type: str,
        options: dict[str, str],
        secret_keys: list[str],
        non_secret_keys: list[str],
    ) -> None:
        data = {"backends": {"b": {"type": backend_type, "options": options}}, "stores": {}}
        rc = RegistryConfig.from_dict(data)
        opts = rc.backends["b"].options
        for k in secret_keys:
            assert isinstance(opts[k], Secret)
        for k in non_secret_keys:
            assert not isinstance(opts[k], Secret)

    @pytest.mark.spec("SEC-003")
    def test_non_string_value_not_wrapped(self) -> None:
        sentinel = object()
        data = {"backends": {"b": {"type": "s3", "options": {"key": sentinel, "bucket": "b"}}}, "stores": {}}
        rc = RegistryConfig.from_dict(data)
        assert rc.backends["b"].options["key"] is sentinel

    @pytest.mark.spec("SEC-006")
    @pytest.mark.spec("SEC-008")
    def test_repr_no_leak(self) -> None:
        data = {
            "backends": {"s3": {"type": "s3", "options": {"bucket": "b", "key": "AKID_TEST", "secret": "SK_TEST"}}},
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        r = repr(rc.backends["s3"])
        assert "AKID_TEST" not in r and "SK_TEST" not in r and "Secret('***')" in r


# endregion


# region: SFTP enum coercion (SEC-005) -- parametrized

_SFTP_POLICY_CASES = [
    pytest.param("auto", "AUTO_ADD", id="auto"),
    pytest.param("tofu", "TRUST_ON_FIRST_USE", id="tofu"),
    pytest.param("strict", "STRICT", id="strict"),
]


@pytest.mark.spec("SEC-005")
@pytest.mark.parametrize("policy_str,enum_name", _SFTP_POLICY_CASES)
def test_sftp_enum_coercion(policy_str: str, enum_name: str) -> None:
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(host="h", host_key_policy=policy_str)
    assert backend._host_key_policy is HostKeyPolicy[enum_name]


@pytest.mark.spec("SEC-005")
def test_sftp_invalid_policy_raises() -> None:
    from remote_store.backends._sftp import SFTPBackend

    with pytest.raises(ValueError, match="not_a_policy"):
        SFTPBackend(host="h", host_key_policy="not_a_policy")


@pytest.mark.spec("SEC-005")
def test_sftp_enum_passthrough() -> None:
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend

    backend = SFTPBackend(host="h", host_key_policy=HostKeyPolicy.AUTO_ADD)
    assert backend._host_key_policy is HostKeyPolicy.AUTO_ADD


# endregion


# region: SecretRedactionFilter (SEC-007)


class TestSecretRedactionFilter:
    """SEC-007: SecretRedactionFilter scrubs Secret instances in log record args."""

    def _make_record(self, msg: str, args: Any) -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )

    @pytest.mark.spec("SEC-007")
    @pytest.mark.parametrize(
        "msg,args,expected",
        [
            ("key=%s secret=%s", (Secret("AKID"), Secret("SK")), ("***", "***")),
            ("val=%s", ("plain",), ("plain",)),
        ],
        ids=["tuple_redacted", "tuple_unchanged"],
    )
    def test_tuple_args(self, msg: str, args: tuple[Any, ...], expected: tuple[Any, ...]) -> None:
        filt = SecretRedactionFilter()
        record = self._make_record(msg, args)
        filt.filter(record)
        assert record.args == expected

    @pytest.mark.spec("SEC-007")
    def test_dict_args_redacted(self) -> None:
        filt = SecretRedactionFilter()
        record = self._make_record("key=%(key)s", {"key": Secret("AKID"), "name": "safe"})
        filt.filter(record)
        assert record.args == {"key": "***", "name": "safe"}  # type: ignore[comparison-overlap]

    @pytest.mark.spec("SEC-007")
    def test_filter_returns_true(self) -> None:
        filt = SecretRedactionFilter()
        assert filt.filter(self._make_record("no args", None)) is True


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
        toml_file = tmp_path / "creds.toml"
        toml_file.write_text(
            '[backends.s3]\ntype = "s3"\n\n[backends.s3.options]\nbucket = "b"\nkey = "AKID"\nsecret = "SK"\n'
        )
        rc = RegistryConfig.from_toml(toml_file)
        opts = rc.backends["s3"].options
        assert isinstance(opts["key"], Secret) and isinstance(opts["secret"], Secret)
        assert not isinstance(opts["bucket"], Secret)

    @pytest.mark.spec("CFG-013")
    def test_from_toml_equivalence_with_from_dict(self, tmp_path: Path) -> None:
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
    @pytest.mark.parametrize("use_str", [False, True], ids=["path_obj", "str_path"])
    def test_from_toml_accepts_path_types(self, tmp_path: Path, use_str: bool) -> None:
        toml_file = tmp_path / "p.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        path: Any = str(toml_file) if use_str else toml_file
        rc = RegistryConfig.from_toml(path)
        assert rc.backends["m"].type == "memory"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_invalid_toml(self, tmp_path: Path) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        bad = tmp_path / "bad.toml"
        bad.write_text("[invalid\n")
        with pytest.raises(tomllib.TOMLDecodeError):
            RegistryConfig.from_toml(bad)


class TestUnknownKeyWarning:
    """CFG-012: from_dict() warns on unknown top-level keys."""

    @pytest.mark.spec("CFG-012")
    def test_unknown_key_warns(self) -> None:
        with pytest.warns(UserWarning, match="Unknown top-level config keys"):
            RegistryConfig.from_dict({"backends": {}, "stores": {}, "backend": {"typo": True}})

    @pytest.mark.spec("CFG-012")
    @pytest.mark.parametrize(
        "data",
        [{"backends": {}, "stores": {}}, {}],
        ids=["known_keys", "empty"],
    )
    def test_no_warning(self, data: dict[str, Any]) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            RegistryConfig.from_dict(data)


# endregion


# region: Config loader fallback paths (CFG-008, CFG-009)


class TestFromTomlFallbacks:
    """Tests for optional-dependency fallback paths in from_toml()."""

    @pytest.mark.spec("CFG-009")
    def test_tomli_fallback_when_tomllib_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        try:
            import tomli  # noqa: F401
        except ImportError:
            pytest.skip("tomli not installed")

        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        monkeypatch.setitem(sys.modules, "tomllib", None)
        rc = RegistryConfig.from_toml(toml_file)
        assert rc.backends["m"].type == "memory"

    @pytest.mark.spec("CFG-009")
    def test_no_toml_lib_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        monkeypatch.setitem(sys.modules, "tomllib", None)
        monkeypatch.setitem(sys.modules, "tomli", None)
        with pytest.raises(ModuleNotFoundError, match="tomli"):
            RegistryConfig.from_toml(toml_file)

    @pytest.mark.spec("CFG-008")
    def test_from_toml_non_dict_table_value(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "scalar.toml"
        toml_file.write_text('[tool]\nremote-store = "not a table"\n')
        with pytest.raises(TypeError, match="Expected a TOML table"):
            RegistryConfig.from_toml(toml_file, table=("tool", "remote-store"))


# endregion


# region: RetryPolicy tests (RET-001 through RET-006)


class TestRetryPolicy:
    """RET-001, RET-002, RET-003: RetryPolicy dataclass."""

    @pytest.mark.spec("RET-001")
    def test_defaults(self) -> None:
        rp = RetryPolicy()
        assert rp.max_attempts == 3
        assert rp.backoff_base == 1.0
        assert rp.backoff_max == 60.0
        assert rp.jitter == 1.0
        assert rp.timeout is None

    @pytest.mark.spec("RET-001")
    def test_custom_values(self) -> None:
        rp = RetryPolicy(max_attempts=5, backoff_base=2.0, backoff_max=30.0, jitter=0.5, timeout=120.0)
        assert rp.max_attempts == 5
        assert rp.backoff_base == 2.0
        assert rp.backoff_max == 30.0
        assert rp.jitter == 0.5
        assert rp.timeout == 120.0

    @pytest.mark.spec("RET-001")
    def test_frozen(self) -> None:
        rp = RetryPolicy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            rp.max_attempts = 5  # type: ignore[misc]

    @pytest.mark.spec("RET-002")
    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"max_attempts": 0}, "max_attempts must be >= 1"),
            ({"max_attempts": -1}, "max_attempts must be >= 1"),
            ({"backoff_base": -0.1}, "backoff_base must be >= 0"),
            ({"backoff_max": -1}, "backoff_max must be >= 0"),
            ({"jitter": -0.5}, "jitter must be >= 0"),
            ({"timeout": 0}, "timeout must be > 0"),
            ({"timeout": -1.0}, "timeout must be > 0"),
        ],
        ids=[
            "max_attempts_zero",
            "max_attempts_negative",
            "backoff_base_negative",
            "backoff_max_negative",
            "jitter_negative",
            "timeout_zero",
            "timeout_negative",
        ],
    )
    def test_validation_rejects(self, kwargs: dict[str, Any], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            RetryPolicy(**kwargs)

    @pytest.mark.spec("RET-002")
    def test_validation_accepts_edge_values(self) -> None:
        rp = RetryPolicy(max_attempts=1, backoff_base=0, backoff_max=0, jitter=0, timeout=0.001)
        assert rp.max_attempts == 1
        assert rp.backoff_base == 0

    @pytest.mark.spec("RET-003")
    def test_disabled_factory(self) -> None:
        rp = RetryPolicy.disabled()
        assert rp.max_attempts == 1

    @pytest.mark.spec("RET-021")
    def test_equality(self) -> None:
        a = RetryPolicy(max_attempts=5)
        b = RetryPolicy(max_attempts=5)
        c = RetryPolicy(max_attempts=3)
        assert a == b
        assert a != c

    @pytest.mark.spec("RET-021")
    def test_hash(self) -> None:
        a = RetryPolicy(max_attempts=5)
        b = RetryPolicy(max_attempts=5)
        assert hash(a) == hash(b)
        assert {a, b} == {a}


class TestBackendConfigRetry:
    """RET-004: BackendConfig.retry field."""

    @pytest.mark.spec("RET-004")
    def test_default_none(self) -> None:
        bc = BackendConfig(type="s3")
        assert bc.retry is None

    @pytest.mark.spec("RET-004")
    def test_with_policy(self) -> None:
        rp = RetryPolicy(max_attempts=5)
        bc = BackendConfig(type="sftp", retry=rp)
        assert bc.retry is rp
        assert bc.retry.max_attempts == 5


class TestFromDictRetryParsing:
    """RET-006: from_dict() parses retry config."""

    @pytest.mark.spec("RET-006")
    def test_retry_dict_parsed(self) -> None:
        data = {
            "backends": {
                "sftp": {
                    "type": "sftp",
                    "options": {"host": "h"},
                    "retry": {"max_attempts": 5, "backoff_base": 2.0},
                },
            },
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        assert rc.backends["sftp"].retry is not None
        assert rc.backends["sftp"].retry.max_attempts == 5
        assert rc.backends["sftp"].retry.backoff_base == 2.0

    @pytest.mark.spec("RET-006")
    def test_retry_missing_is_none(self) -> None:
        data = {
            "backends": {"local": {"type": "local", "options": {}}},
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        assert rc.backends["local"].retry is None

    @pytest.mark.spec("RET-006")
    def test_retry_policy_passthrough(self) -> None:
        rp = RetryPolicy(max_attempts=10)
        data = {
            "backends": {"sftp": {"type": "sftp", "options": {"host": "h"}, "retry": rp}},
            "stores": {},
        }
        rc = RegistryConfig.from_dict(data)
        assert rc.backends["sftp"].retry is rp

    @pytest.mark.spec("RET-006")
    def test_retry_invalid_field_raises_type_error(self) -> None:
        data = {
            "backends": {
                "sftp": {
                    "type": "sftp",
                    "options": {"host": "h"},
                    "retry": {"max_attempts": 5, "unknown_field": True},
                },
            },
            "stores": {},
        }
        with pytest.raises(TypeError):
            RegistryConfig.from_dict(data)


# endregion


# region: Registry retry passthrough (RET-005)


class TestRegistryRetryPassthrough:
    """RET-005: Registry passes retry from BackendConfig to backend constructors."""

    @pytest.mark.spec("RET-005")
    def test_retry_passed_to_backend(self) -> None:
        from remote_store._registry import Registry

        rp = RetryPolicy(max_attempts=7)
        config_sftp = RegistryConfig(
            backends={"sftp": BackendConfig(type="sftp", options={"host": "h"}, retry=rp)},
            stores={"s": StoreProfile(backend="sftp")},
        )
        registry = Registry(config_sftp)
        backend = registry._get_backend("sftp")
        assert backend._retry is rp  # type: ignore[union-attr]
        registry.close()

    @pytest.mark.spec("RET-005")
    def test_no_retry_when_none(self) -> None:
        from remote_store._registry import Registry

        config = RegistryConfig(
            backends={"sftp": BackendConfig(type="sftp", options={"host": "h"})},
            stores={"s": StoreProfile(backend="sftp")},
        )
        registry = Registry(config)
        backend = registry._get_backend("sftp")
        assert backend._retry is None  # type: ignore[union-attr]
        registry.close()


# endregion


# region: RetryPolicy backend constructor acceptance (RET-010 through RET-014)


class TestRetryBackendConstructors:
    """RET-010 through RET-014: Backends accept or reject retry parameter."""

    @pytest.mark.spec("RET-010")
    def test_sftp_accepts_retry(self) -> None:
        from remote_store.backends._sftp import SFTPBackend

        rp = RetryPolicy(max_attempts=5)
        backend = SFTPBackend(host="h", retry=rp)
        assert backend._retry is rp

    @pytest.mark.spec("RET-010")
    def test_sftp_default_none(self) -> None:
        from remote_store.backends._sftp import SFTPBackend

        backend = SFTPBackend(host="h")
        assert backend._retry is None

    @pytest.mark.spec("RET-011")
    def test_s3_accepts_retry(self) -> None:
        from remote_store.backends._s3 import S3Backend

        rp = RetryPolicy(max_attempts=10)
        backend = S3Backend(bucket="b", retry=rp)
        assert backend._retry is rp

    @pytest.mark.spec("RET-012")
    def test_azure_accepts_retry(self) -> None:
        from remote_store.backends._azure import AzureBackend

        rp = RetryPolicy(max_attempts=7)
        backend = AzureBackend(
            container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;", retry=rp
        )
        assert backend._retry is rp

    @pytest.mark.spec("RET-013")
    def test_s3_pyarrow_accepts_retry(self) -> None:
        pytest.importorskip("pyarrow")
        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        rp = RetryPolicy(max_attempts=4)
        backend = S3PyArrowBackend(bucket="b", retry=rp)
        assert backend._retry is rp

    @pytest.mark.spec("RET-014")
    def test_local_rejects_retry(self) -> None:
        from remote_store.backends._local import LocalBackend

        with pytest.raises(TypeError):
            LocalBackend(root="/tmp", retry=RetryPolicy())  # type: ignore[call-arg]

    @pytest.mark.spec("RET-014")
    def test_memory_rejects_retry(self) -> None:
        from remote_store.backends._memory import MemoryBackend

        with pytest.raises(TypeError):
            MemoryBackend(retry=RetryPolicy())  # type: ignore[call-arg]


# endregion


# region: RetryPolicy backend mapping (RET-011, RET-012)


class TestRetryBackendMapping:
    """RET-011, RET-012: Backends correctly translate RetryPolicy to native config."""

    @pytest.mark.spec("RET-012")
    def test_azure_build_retry_mapping(self) -> None:
        from remote_store.backends._azure import AzureBackend

        rp = RetryPolicy(max_attempts=5, backoff_base=2.0, jitter=3.0)
        backend = AzureBackend(
            container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;", retry=rp
        )
        azure_retry = backend._build_azure_retry()
        assert azure_retry.total_retries == 4  # max_attempts - 1
        assert azure_retry.initial_backoff == 2
        assert azure_retry.random_jitter_range == 3

    @pytest.mark.spec("RET-012")
    def test_azure_build_retry_rounds_fractional(self) -> None:
        """Fractional backoff_base is rounded, not truncated to zero."""
        from remote_store.backends._azure import AzureBackend

        rp = RetryPolicy(max_attempts=3, backoff_base=0.5, jitter=0.7)
        backend = AzureBackend(
            container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;", retry=rp
        )
        azure_retry = backend._build_azure_retry()
        # 0.5 rounds to 0, but max(1, ...) ensures at least 1
        assert azure_retry.initial_backoff == 1
        # 0.7 rounds to 1
        assert azure_retry.random_jitter_range == 1

    @pytest.mark.spec("RET-012")
    def test_azure_build_retry_none(self) -> None:
        from remote_store.backends._azure import AzureBackend

        backend = AzureBackend(container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;")
        assert backend._build_azure_retry() is None

    @pytest.mark.spec("RET-011")
    def test_s3_retry_botocore_config(self) -> None:
        from remote_store.backends._s3 import S3Backend

        rp = RetryPolicy(max_attempts=7)
        backend = S3Backend(bucket="b", retry=rp)
        # Force lazy init to build the config
        fs = backend._fs
        config = fs.client_kwargs.get("config")
        assert config is not None
        assert config.retries["max_attempts"] == 7
        assert config.retries["mode"] == "standard"
        backend.close()

    @pytest.mark.spec("RET-013")
    def test_s3_pyarrow_retry_strategy(self) -> None:
        pytest.importorskip("pyarrow")
        from unittest.mock import patch

        from remote_store.backends._s3_pyarrow import S3PyArrowBackend

        rp = RetryPolicy(max_attempts=9)
        backend = S3PyArrowBackend(bucket="b", retry=rp)
        with patch("pyarrow.fs.S3FileSystem") as mock_s3fs:
            mock_s3fs.return_value = mock_s3fs
            _ = backend._pa_fs
            call_kwargs = mock_s3fs.call_args[1]
            strategy = call_kwargs["retry_strategy"]
            assert strategy.max_attempts == 9
        backend.close()


# endregion


# region: RetryPolicy top-level export (RET-020)


class TestRetryPolicyExport:
    """RET-020: RetryPolicy is exported from remote_store."""

    @pytest.mark.spec("RET-020")
    def test_importable(self) -> None:
        from remote_store import RetryPolicy as RP

        assert RP is RetryPolicy

    @pytest.mark.spec("RET-020")
    def test_in_all(self) -> None:
        import remote_store

        assert "RetryPolicy" in remote_store.__all__


# endregion
