"""Tests for configuration -- derived from sdd/specs/002-registry-config.md (CFG sections)."""

from __future__ import annotations

import copy
import dataclasses
import logging
import pickle
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
    resolve_env,
)

# ---------------------------------------------------------------------------
# CFG-001 / CFG-002: BackendConfig & StoreProfile
# ---------------------------------------------------------------------------

_BC = BackendConfig(type="s3", options={"bucket": "my-bucket"})
_SP = StoreProfile(backend="local", root_path="data", options={"key": "val"})


@pytest.mark.spec("CFG-001")
@pytest.mark.parametrize(
    ("field", "expected"), [("type", "s3"), ("options", {"bucket": "my-bucket"})], ids=["type", "options"]
)
def test_backend_config_fields(field: str, expected: Any) -> None:
    assert getattr(_BC, field) == expected


@pytest.mark.spec("CFG-001")
def test_backend_config_defaults() -> None:
    assert BackendConfig(type="local").options == {}


@pytest.mark.spec("CFG-002")
@pytest.mark.parametrize(
    ("field", "expected"),
    [("backend", "local"), ("root_path", "data"), ("options", {"key": "val"})],
    ids=["backend", "root_path", "options"],
)
def test_store_profile_fields(field: str, expected: Any) -> None:
    assert getattr(_SP, field) == expected


@pytest.mark.spec("CFG-002")
@pytest.mark.parametrize(("field", "expected"), [("root_path", ""), ("options", {})], ids=["root_path", "options"])
def test_store_profile_defaults(field: str, expected: Any) -> None:
    assert getattr(StoreProfile(backend="local"), field) == expected


# ---------------------------------------------------------------------------
# CFG-003 / CFG-004: RegistryConfig + validation
# ---------------------------------------------------------------------------


def _valid_rc() -> RegistryConfig:
    return RegistryConfig(
        backends={"local": BackendConfig(type="local")}, stores={"main": StoreProfile(backend="local")}
    )


@pytest.mark.spec("CFG-003")
def test_registry_config_fields() -> None:
    rc = _valid_rc()
    assert "local" in rc.backends
    assert "main" in rc.stores


@pytest.mark.spec("CFG-004")
def test_registry_config_validate_passes() -> None:
    result = _valid_rc().validate()
    assert result is None


@pytest.mark.spec("CFG-004")
def test_registry_config_validate_fails_missing_backend() -> None:
    rc = RegistryConfig(backends={}, stores={"main": StoreProfile(backend="nonexistent")})
    with pytest.raises(ValueError, match="nonexistent"):
        rc.validate()


# ---------------------------------------------------------------------------
# CFG-005: from_dict() construction
# ---------------------------------------------------------------------------


@pytest.mark.spec("CFG-005")
def test_from_dict() -> None:
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
def test_from_dict_minimal() -> None:
    rc = RegistryConfig.from_dict({"backends": {}, "stores": {}})
    assert rc.backends == {}
    assert rc.stores == {}


# ---------------------------------------------------------------------------
# CFG-006: Immutability
# ---------------------------------------------------------------------------


@pytest.mark.spec("CFG-006")
@pytest.mark.parametrize(
    ("factory", "attr", "value"),
    [
        pytest.param(lambda: BackendConfig(type="local"), "type", "s3", id="BackendConfig"),
        pytest.param(lambda: StoreProfile(backend="local"), "backend", "s3", id="StoreProfile"),
        pytest.param(lambda: RegistryConfig(), "backends", {}, id="RegistryConfig"),
    ],
)
def test_config_immutability(factory: Any, attr: str, value: Any) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(factory(), attr, value)


# ---------------------------------------------------------------------------
# SEC-001 / SEC-002: Secret wrapper
# ---------------------------------------------------------------------------


class TestSecret:
    """SEC-001, SEC-002: Secret class."""

    @pytest.mark.spec("SEC-001")
    def test_reveal(self) -> None:
        assert Secret("my-key").reveal() == "my-key"

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize(("func", "expected"), [(repr, "Secret('***')"), (str, "***")], ids=["repr", "str"])
    def test_masked_output(self, func: Any, expected: str) -> None:
        assert func(Secret("super-secret")) == expected
        assert "super-secret" not in func(Secret("super-secret"))

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize(
        ("a", "b", "equal"), [("abc", "abc", True), ("abc", "xyz", False)], ids=["same", "different"]
    )
    def test_eq(self, a: str, b: str, equal: bool) -> None:
        assert (Secret(a) == Secret(b)) is equal

    @pytest.mark.spec("SEC-001")
    def test_eq_not_implemented_for_str(self) -> None:
        assert Secret("abc") != "abc"

    @pytest.mark.spec("SEC-001")
    def test_hash(self) -> None:
        a, b = Secret("abc"), Secret("abc")
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    @pytest.mark.spec("SEC-001")
    @pytest.mark.parametrize(("val", "expected"), [("x", True), ("", False)], ids=["truthy", "falsy"])
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
    @pytest.mark.parametrize(
        ("action", "check"),
        [
            pytest.param(
                lambda: pickle.loads(pickle.dumps(Secret("roundtrip"))),
                lambda r: isinstance(r, Secret) and r.reveal() == "roundtrip",
                id="pickle",
            ),
            pytest.param(
                lambda: copy.deepcopy(Secret("deep")),
                lambda r: isinstance(r, Secret) and r.reveal() == "deep",
                id="deepcopy",
            ),
        ],
    )
    def test_serialization_roundtrip(self, action: Any, check: Any) -> None:
        assert check(action())

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
        with pytest.raises(TypeError, match="Secret"):
            action(Secret("abc"))


@pytest.mark.parametrize(
    ("inp", "expected"),
    [(Secret("x"), "x"), ("plain", "plain"), (None, None)],
    ids=["secret", "str", "none"],
)
def test_reveal_helper(inp: Any, expected: Any) -> None:
    assert _reveal(inp) == expected


# ---------------------------------------------------------------------------
# SEC-003 / SEC-006 / SEC-008: from_dict() secret wrapping
# ---------------------------------------------------------------------------


class TestFromDictSecretWrapping:
    """SEC-003: from_dict() wraps _SENSITIVE_KEYS in Secret."""

    @pytest.mark.spec("SEC-003")
    @pytest.mark.parametrize(
        ("backend_type", "options", "secret_keys", "non_secret_keys"),
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
        self, backend_type: str, options: dict[str, str], secret_keys: list[str], non_secret_keys: list[str]
    ) -> None:
        rc = RegistryConfig.from_dict({"backends": {"b": {"type": backend_type, "options": options}}, "stores": {}})
        opts = rc.backends["b"].options
        for k in secret_keys:
            assert isinstance(opts[k], Secret)
        for k in non_secret_keys:
            assert not isinstance(opts[k], Secret)

    @pytest.mark.spec("SEC-003")
    def test_non_string_value_not_wrapped(self) -> None:
        sentinel = object()
        rc = RegistryConfig.from_dict(
            {"backends": {"b": {"type": "s3", "options": {"key": sentinel, "bucket": "b"}}}, "stores": {}}
        )
        assert rc.backends["b"].options["key"] is sentinel

    @pytest.mark.spec("SEC-006")
    @pytest.mark.spec("SEC-008")
    def test_repr_no_leak(self) -> None:
        rc = RegistryConfig.from_dict(
            {
                "backends": {"s3": {"type": "s3", "options": {"bucket": "b", "key": "AKID_TEST", "secret": "SK_TEST"}}},
                "stores": {},
            }
        )
        r = repr(rc.backends["s3"])
        assert "AKID_TEST" not in r
        assert "SK_TEST" not in r
        assert "Secret('***')" in r


# ---------------------------------------------------------------------------
# SEC-005: SFTP enum coercion
# ---------------------------------------------------------------------------


@pytest.mark.spec("SEC-005")
@pytest.mark.parametrize(
    ("policy_str", "enum_name"),
    [
        pytest.param("auto", "AUTO_ADD", id="auto"),
        pytest.param("tofu", "TRUST_ON_FIRST_USE", id="tofu"),
        pytest.param("strict", "STRICT", id="strict"),
    ],
)
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


# ---------------------------------------------------------------------------
# SEC-007: SecretRedactionFilter
# ---------------------------------------------------------------------------


class TestSecretRedactionFilter:
    """SEC-007: SecretRedactionFilter scrubs Secret instances in log record args."""

    @staticmethod
    def _make_record(msg: str, args: Any) -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg=msg, args=args, exc_info=None
        )

    @pytest.mark.spec("SEC-007")
    @pytest.mark.parametrize(
        ("msg", "args", "expected"),
        [
            ("key=%s secret=%s", (Secret("AKID"), Secret("SK")), ("***", "***")),
            ("val=%s", ("plain",), ("plain",)),
            ("key=%(key)s", {"key": Secret("AKID"), "name": "safe"}, {"key": "***", "name": "safe"}),
        ],
        ids=["tuple_redacted", "tuple_unchanged", "dict_redacted"],
    )
    def test_args_redacted(self, msg: str, args: Any, expected: Any) -> None:
        record = self._make_record(msg, args)
        SecretRedactionFilter().filter(record)
        assert record.args == expected

    @pytest.mark.spec("SEC-007")
    def test_filter_returns_true(self) -> None:
        assert SecretRedactionFilter().filter(self._make_record("no args", None)) is True


# ---------------------------------------------------------------------------
# CFG-008 / CFG-009 / CFG-013: from_toml()
# ---------------------------------------------------------------------------


class TestFromToml:
    """CFG-008, CFG-009, CFG-013: from_toml() loads config from TOML files."""

    @pytest.mark.spec("CFG-008")
    def test_from_toml_standalone(self, tmp_path: Path) -> None:
        f = tmp_path / "config.toml"
        f.write_text(
            "[backends.local]\n"
            'type = "local"\n\n'
            "[backends.local.options]\n"
            'root = "/data"\n\n'
            "[stores.main]\n"
            'backend = "local"\nroot_path = "data"\n'
        )
        rc = RegistryConfig.from_toml(f)
        assert rc.backends["local"].type == "local"
        assert rc.backends["local"].options["root"] == "/data"
        assert rc.stores["main"].backend == "local"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_with_table(self, tmp_path: Path) -> None:
        f = tmp_path / "pyproject.toml"
        f.write_text(
            "[tool.remote-store.backends.mem]\n"
            'type = "memory"\n\n'
            "[tool.remote-store.stores.scratch]\n"
            'backend = "mem"\nroot_path = "tmp"\n'
        )
        rc = RegistryConfig.from_toml(f, table=("tool", "remote-store"))
        assert rc.backends["mem"].type == "memory"
        assert rc.stores["scratch"].root_path == "tmp"

    @pytest.mark.spec("CFG-008")
    def test_from_toml_table_key_not_found(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.toml"
        f.write_text("[other]\nfoo = 1\n")
        with pytest.raises(KeyError, match="tool"):
            RegistryConfig.from_toml(f, table=("tool", "remote-store"))

    @pytest.mark.spec("CFG-008")
    def test_from_toml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            RegistryConfig.from_toml("/nonexistent/config.toml")

    @pytest.mark.spec("CFG-008")
    def test_from_toml_secret_wrapping(self, tmp_path: Path) -> None:
        f = tmp_path / "creds.toml"
        f.write_text('[backends.s3]\ntype = "s3"\n\n[backends.s3.options]\nbucket = "b"\nkey = "AKID"\nsecret = "SK"\n')
        opts = RegistryConfig.from_toml(f).backends["s3"].options
        assert isinstance(opts["key"], Secret)
        assert isinstance(opts["secret"], Secret)
        assert not isinstance(opts["bucket"], Secret)

    @pytest.mark.spec("CFG-013")
    def test_from_toml_equivalence_with_from_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "eq.toml"
        f.write_text(
            "[backends.local]\n"
            'type = "local"\n\n'
            "[backends.local.options]\n"
            'root = "/tmp"\n\n'
            "[stores.data]\n"
            'backend = "local"\nroot_path = "d"\n'
        )
        from_toml = RegistryConfig.from_toml(f)
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
        f = tmp_path / "p.toml"
        f.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        path: Any = str(f) if use_str else f
        assert RegistryConfig.from_toml(path).backends["m"].type == "memory"

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


# ---------------------------------------------------------------------------
# CFG-012: Unknown key warning
# ---------------------------------------------------------------------------


@pytest.mark.spec("CFG-012")
def test_unknown_key_warns() -> None:
    with pytest.warns(UserWarning, match="Unknown top-level config keys"):
        result = RegistryConfig.from_dict({"backends": {}, "stores": {}, "backend": {"typo": True}})
    assert result is not None


@pytest.mark.spec("CFG-012")
@pytest.mark.parametrize("data", [{"backends": {}, "stores": {}}, {}], ids=["known_keys", "empty"])
def test_no_unknown_key_warning(data: dict[str, Any]) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = RegistryConfig.from_dict(data)
    assert result is not None


# ---------------------------------------------------------------------------
# CFG-008 / CFG-009: from_toml() fallback paths
# ---------------------------------------------------------------------------


class TestFromTomlFallbacks:
    """Tests for optional-dependency fallback paths in from_toml()."""

    @pytest.mark.spec("CFG-009")
    def test_tomli_fallback_when_tomllib_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        try:
            import tomli  # noqa: F401
        except ImportError:
            pytest.skip("tomli not installed")
        f = tmp_path / "config.toml"
        f.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        monkeypatch.setitem(sys.modules, "tomllib", None)
        assert RegistryConfig.from_toml(f).backends["m"].type == "memory"

    @pytest.mark.spec("CFG-009")
    def test_no_toml_lib_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        f = tmp_path / "config.toml"
        f.write_text('[backends.m]\ntype = "memory"\n\n[stores]\n')
        monkeypatch.setitem(sys.modules, "tomllib", None)
        monkeypatch.setitem(sys.modules, "tomli", None)
        with pytest.raises(ModuleNotFoundError, match="tomli"):
            RegistryConfig.from_toml(f)

    @pytest.mark.spec("CFG-008")
    def test_from_toml_non_dict_table_value(self, tmp_path: Path) -> None:
        f = tmp_path / "scalar.toml"
        f.write_text('[tool]\nremote-store = "not a table"\n')
        with pytest.raises(TypeError, match="Expected a TOML table"):
            RegistryConfig.from_toml(f, table=("tool", "remote-store"))


# ---------------------------------------------------------------------------
# RET-001 through RET-003, RET-021: RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    """RET-001 through RET-003, RET-021: RetryPolicy dataclass."""

    @pytest.mark.spec("RET-001")
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("max_attempts", 3),
            ("backoff_base", 1.0),
            ("backoff_max", 60.0),
            ("jitter", 1.0),
            ("timeout", None),
        ],
        ids=["max_attempts", "backoff_base", "backoff_max", "jitter", "timeout"],
    )
    def test_defaults(self, field: str, expected: Any) -> None:
        assert getattr(RetryPolicy(), field) == expected

    @pytest.mark.spec("RET-001")
    def test_custom_values(self) -> None:
        rp = RetryPolicy(max_attempts=5, backoff_base=2.0, backoff_max=30.0, jitter=0.5, timeout=120.0)
        assert (rp.max_attempts, rp.backoff_base, rp.backoff_max, rp.jitter, rp.timeout) == (5, 2.0, 30.0, 0.5, 120.0)

    @pytest.mark.spec("RET-001")
    def test_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            RetryPolicy().max_attempts = 5  # type: ignore[misc]

    @pytest.mark.spec("RET-002")
    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"max_attempts": 0}, "max_attempts must be >= 1"),
            ({"max_attempts": -1}, "max_attempts must be >= 1"),
            ({"backoff_base": -0.1}, "backoff_base must be >= 0"),
            ({"backoff_max": -1}, "backoff_max must be >= 0"),
            ({"jitter": -0.5}, "jitter must be >= 0"),
            ({"timeout": 0}, "timeout must be > 0"),
            ({"timeout": -1.0}, "timeout must be > 0"),
        ],
        ids=["max_zero", "max_neg", "base_neg", "bmax_neg", "jitter_neg", "timeout_zero", "timeout_neg"],
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
        assert RetryPolicy.disabled().max_attempts == 1

    @pytest.mark.spec("RET-021")
    def test_equality_and_hash(self) -> None:
        a, b, c = RetryPolicy(max_attempts=5), RetryPolicy(max_attempts=5), RetryPolicy(max_attempts=3)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
        assert {a, b} == {a}


# ---------------------------------------------------------------------------
# RET-004: BackendConfig.retry field
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-004")
@pytest.mark.parametrize(
    ("retry_arg", "check"),
    [
        pytest.param(None, lambda bc: bc.retry is None, id="default_none"),
        pytest.param(
            RetryPolicy(max_attempts=5),
            lambda bc: bc.retry is not None and bc.retry.max_attempts == 5,
            id="with_policy",
        ),
    ],
)
def test_backend_config_retry(retry_arg: Any, check: Any) -> None:
    bc = BackendConfig(type="sftp") if retry_arg is None else BackendConfig(type="sftp", retry=retry_arg)
    assert check(bc)


# ---------------------------------------------------------------------------
# RET-006: from_dict() retry parsing
# ---------------------------------------------------------------------------


class TestFromDictRetryParsing:
    """RET-006: from_dict() parses retry config."""

    @pytest.mark.spec("RET-006")
    def test_retry_dict_parsed(self) -> None:
        rc = RegistryConfig.from_dict(
            {
                "backends": {
                    "sftp": {
                        "type": "sftp",
                        "options": {"host": "h"},
                        "retry": {"max_attempts": 5, "backoff_base": 2.0},
                    }
                },
                "stores": {},
            }
        )
        assert rc.backends["sftp"].retry is not None
        assert rc.backends["sftp"].retry.max_attempts == 5
        assert rc.backends["sftp"].retry.backoff_base == 2.0

    @pytest.mark.spec("RET-006")
    def test_retry_missing_is_none(self) -> None:
        rc = RegistryConfig.from_dict({"backends": {"local": {"type": "local", "options": {}}}, "stores": {}})
        assert rc.backends["local"].retry is None

    @pytest.mark.spec("RET-006")
    def test_retry_policy_passthrough(self) -> None:
        rp = RetryPolicy(max_attempts=10)
        rc = RegistryConfig.from_dict(
            {"backends": {"sftp": {"type": "sftp", "options": {"host": "h"}, "retry": rp}}, "stores": {}}
        )
        assert rc.backends["sftp"].retry is rp

    @pytest.mark.spec("RET-006")
    def test_retry_invalid_field_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            RegistryConfig.from_dict(
                {
                    "backends": {
                        "sftp": {
                            "type": "sftp",
                            "options": {"host": "h"},
                            "retry": {"max_attempts": 5, "unknown_field": True},
                        }
                    },
                    "stores": {},
                }
            )


# ---------------------------------------------------------------------------
# RET-005: Registry retry passthrough
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-005")
@pytest.mark.parametrize(
    ("retry_arg", "expect_none"),
    [
        pytest.param(RetryPolicy(max_attempts=7), False, id="with_retry"),
        pytest.param(None, True, id="no_retry"),
    ],
)
def test_registry_retry_passthrough(retry_arg: Any, expect_none: bool) -> None:
    from remote_store._registry import Registry

    bc_kwargs: dict[str, Any] = {"type": "sftp", "options": {"host": "h"}}
    if retry_arg is not None:
        bc_kwargs["retry"] = retry_arg
    config = RegistryConfig(backends={"sftp": BackendConfig(**bc_kwargs)}, stores={"s": StoreProfile(backend="sftp")})
    registry = Registry(config)
    backend = registry._get_backend("sftp")
    assert (backend._retry is None) is expect_none  # type: ignore[union-attr]
    if not expect_none:
        assert backend._retry is retry_arg  # type: ignore[union-attr]
    registry.close()


# ---------------------------------------------------------------------------
# RET-010 through RET-014: Backend constructor retry acceptance
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-010")
@pytest.mark.parametrize(
    ("retry_arg", "expect_none"),
    [
        pytest.param(RetryPolicy(max_attempts=5), False, id="with_retry"),
        pytest.param(None, True, id="default_none"),
    ],
)
def test_sftp_retry(retry_arg: Any, expect_none: bool) -> None:
    from remote_store.backends._sftp import SFTPBackend

    backend = SFTPBackend(host="h") if retry_arg is None else SFTPBackend(host="h", retry=retry_arg)
    assert (backend._retry is None) is expect_none


@pytest.mark.spec("RET-011")
def test_s3_accepts_retry() -> None:
    from remote_store.backends._s3 import S3Backend

    rp = RetryPolicy(max_attempts=10)
    assert S3Backend(bucket="b", retry=rp)._retry is rp


@pytest.mark.spec("RET-012")
def test_azure_accepts_retry() -> None:
    from remote_store.backends._azure import AzureBackend

    rp = RetryPolicy(max_attempts=7)
    assert (
        AzureBackend(container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;", retry=rp)._retry
        is rp
    )


@pytest.mark.spec("RET-013")
def test_s3_pyarrow_accepts_retry() -> None:
    pytest.importorskip("pyarrow")
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    rp = RetryPolicy(max_attempts=4)
    assert S3PyArrowBackend(bucket="b", retry=rp)._retry is rp


def _make_local_backend(**kwargs: Any) -> Any:
    from remote_store.backends._local import LocalBackend

    return LocalBackend(**kwargs)


def _make_memory_backend(**kwargs: Any) -> Any:
    from remote_store.backends._memory import MemoryBackend

    return MemoryBackend(**kwargs)


def _remote_store_module() -> Any:
    import remote_store

    return remote_store


@pytest.mark.spec("RET-014")
@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda rp: _make_local_backend(root="/tmp", retry=rp), id="local"),
        pytest.param(lambda rp: _make_memory_backend(retry=rp), id="memory"),
    ],
)
def test_backend_rejects_retry(factory: Any) -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        factory(RetryPolicy())


# ---------------------------------------------------------------------------
# RET-011 / RET-012 / RET-013: Backend retry mapping
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-012")
@pytest.mark.parametrize(
    ("rp_kwargs", "expected_backoff", "expected_jitter"),
    [
        pytest.param({"max_attempts": 5, "backoff_base": 2.0, "jitter": 3.0}, 2, 3, id="integer_values"),
        pytest.param({"max_attempts": 3, "backoff_base": 0.5, "jitter": 0.7}, 1, 1, id="fractional_rounds_up"),
    ],
)
def test_azure_build_retry_mapping(rp_kwargs: dict[str, Any], expected_backoff: int, expected_jitter: int) -> None:
    from remote_store.backends._azure import AzureBackend

    rp = RetryPolicy(**rp_kwargs)
    azure_retry = AzureBackend(
        container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;", retry=rp
    )._build_azure_retry()
    assert azure_retry.total_retries == rp_kwargs["max_attempts"] - 1
    assert azure_retry.initial_backoff == expected_backoff
    assert azure_retry.random_jitter_range == expected_jitter


@pytest.mark.spec("RET-012")
def test_azure_build_retry_none() -> None:
    from remote_store.backends._azure import AzureBackend

    assert (
        AzureBackend(
            container="c", connection_string="DefaultEndpointsProtocol=http;AccountName=a;"
        )._build_azure_retry()
        is None
    )


@pytest.mark.spec("RET-011")
def test_s3_retry_botocore_config() -> None:
    from remote_store.backends._s3 import S3Backend

    backend = S3Backend(bucket="b", retry=RetryPolicy(max_attempts=7))
    config = backend._fs.client_kwargs.get("config")
    assert config is not None
    assert config.retries["max_attempts"] == 7
    assert config.retries["mode"] == "standard"
    backend.close()


@pytest.mark.spec("RET-013")
def test_s3_pyarrow_retry_strategy() -> None:
    pytest.importorskip("pyarrow")
    from unittest.mock import patch

    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    backend = S3PyArrowBackend(bucket="b", retry=RetryPolicy(max_attempts=9))
    with patch("pyarrow.fs.S3FileSystem") as mock_s3fs:
        mock_s3fs.return_value = mock_s3fs
        _ = backend._pa_fs
        assert mock_s3fs.call_args[1]["retry_strategy"].max_attempts == 9
    backend.close()


# ---------------------------------------------------------------------------
# RET-020: RetryPolicy top-level export
# ---------------------------------------------------------------------------


@pytest.mark.spec("RET-020")
@pytest.mark.parametrize(
    "check",
    [
        pytest.param(lambda: _remote_store_module().RetryPolicy is RetryPolicy, id="importable"),
        pytest.param(lambda: "RetryPolicy" in _remote_store_module().__all__, id="in___all__"),
    ],
)
def test_retry_policy_export(check: Any) -> None:
    assert check()


# ---------------------------------------------------------------------------
# CFG-018 .. CFG-021: resolve_env() — env-var interpolation
# ---------------------------------------------------------------------------


class TestResolveEnv:
    """CFG-018/CFG-019: resolve_env() placeholder resolution."""

    @pytest.mark.spec("CFG-018")
    @pytest.mark.spec("CFG-019")
    @pytest.mark.parametrize(
        ("template", "environ", "expected"),
        [
            pytest.param("${MY_VAR}", {"MY_VAR": "hello"}, "hello", id="simple"),
            pytest.param("${X}", {"X": "custom"}, "custom", id="custom-environ"),
            pytest.param("${MISSING:-fallback}", {}, "fallback", id="default-used"),
            pytest.param("${MISSING:-}", {}, "", id="default-empty"),
            pytest.param("${VAR:-fallback}", {"VAR": "actual"}, "actual", id="default-ignored"),
            pytest.param("$${NOT_A_VAR}", {}, "${NOT_A_VAR}", id="escape"),
            pytest.param(
                "https://${HOST}:${PORT}/path",
                {"HOST": "example.com", "PORT": "8080"},
                "https://example.com:8080/path",
                id="embedded-multiple",
            ),
        ],
    )
    def test_placeholder_resolution(self, template: str, environ: dict[str, str], expected: str) -> None:
        result = resolve_env({"key": template}, environ=environ)
        assert result["key"] == expected

    @pytest.mark.spec("CFG-018")
    def test_missing_var_raises(self) -> None:
        data: dict[str, object] = {"backends": {"s3": {"secret": "${MISSING}"}}}
        with pytest.raises(KeyError, match="MISSING"):
            resolve_env(data, environ={})

    @pytest.mark.spec("CFG-018")
    def test_nested_dict_list(self) -> None:
        data: dict[str, object] = {
            "backends": {"s3": {"options": {"key": "${K}"}}},
            "tags": ["${T1}", "${T2}"],
        }
        result = resolve_env(data, environ={"K": "secret", "T1": "a", "T2": "b"})
        assert result["backends"]["s3"]["options"]["key"] == "secret"  # type: ignore[index]
        assert result["tags"] == ["a", "b"]

    @pytest.mark.spec("CFG-018")
    def test_non_string_passthrough(self) -> None:
        data: dict[str, object] = {"port": 8080, "debug": True, "empty": None}
        result = resolve_env(data, environ={})
        assert result == {"port": 8080, "debug": True, "empty": None}

    @pytest.mark.spec("CFG-018")
    def test_keys_not_interpolated(self) -> None:
        data: dict[str, object] = {"${KEY}": "value"}
        result = resolve_env(data, environ={"KEY": "replaced"})
        assert "${KEY}" in result
        assert "replaced" not in result

    @pytest.mark.spec("CFG-018")
    def test_original_not_mutated(self) -> None:
        data: dict[str, object] = {"nested": {"key": "${VAR}"}}
        resolve_env(data, environ={"VAR": "new"})
        assert data == {"nested": {"key": "${VAR}"}}


class TestResolveEnvLoaderIntegration:
    """CFG-020: resolve_env_vars parameter on from_toml()."""

    @pytest.mark.spec("CFG-020")
    def test_from_toml_resolve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        f = tmp_path / "config.toml"
        f.write_text('[backends.s3]\ntype = "s3"\n\n[backends.s3.options]\nkey = "${AWS_KEY}"\n\n[stores]\n')
        monkeypatch.setenv("AWS_KEY", "my-secret")
        rc = RegistryConfig.from_toml(f, resolve_env_vars=True)
        assert rc.backends["s3"].options["key"].reveal() == "my-secret"  # type: ignore[union-attr]

    @pytest.mark.spec("CFG-020")
    def test_from_toml_default_off(self, tmp_path: Path) -> None:
        f = tmp_path / "config.toml"
        f.write_text('[backends.s3]\ntype = "s3"\n\n[backends.s3.options]\nkey = "${AWS_KEY}"\n\n[stores]\n')
        rc = RegistryConfig.from_toml(f)
        # Placeholder is NOT resolved — stored as-is, then wrapped in Secret
        assert rc.backends["s3"].options["key"].reveal() == "${AWS_KEY}"  # type: ignore[union-attr]
