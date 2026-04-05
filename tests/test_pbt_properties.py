"""Property-based tests for partition, config, and path modules (BK-139 P1-P3)."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from remote_store._config import RegistryConfig, Secret
from remote_store._errors import InvalidPath
from remote_store._path import RemotePath
from remote_store.ext.partition import parse_partition, partition_path

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Partition key: non-empty, no '=' or '/'
_partition_key = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_0123456789"),
    min_size=1,
    max_size=20,
)

# Partition value: non-empty, no '=' or '/'
_partition_value = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_-."),
    min_size=1,
    max_size=30,
)

# Filename: non-empty, no '/', must NOT look like a partition segment (no '=')
_filename = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_."),
    min_size=1,
    max_size=30,
).filter(lambda s: "=" not in s)

# Path segment: non-empty, no '/', no null, no '..'
_path_segment = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_-."),
    min_size=1,
    max_size=20,
).filter(lambda s: s not in (".", ".."))

# Backend type for config tests
_backend_type = st.sampled_from(["local", "s3", "sftp", "azure", "memory"])

# Non-sensitive option values (strings, ints, bools)
_option_value = st.one_of(
    st.text(min_size=0, max_size=30),
    st.integers(min_value=0, max_value=10000),
    st.booleans(),
)

# ---------------------------------------------------------------------------
# P1: Partition roundtrip
# ---------------------------------------------------------------------------


class TestPartitionRoundtrip:
    """partition_path -> parse_partition roundtrips correctly."""

    @pytest.mark.pbt
    @given(
        keys=st.lists(_partition_key, min_size=1, max_size=4, unique=True),
        values=st.lists(_partition_value, min_size=1, max_size=4),
        filename=_filename,
    )
    def test_roundtrip(self, keys: list[str], values: list[str], filename: str) -> None:
        pairs = dict(zip(keys, values[: len(keys)], strict=False))
        path = partition_path(filename, **pairs)
        parsed = parse_partition(path)
        assert parsed.partitions == pairs
        assert parsed.filename == filename

    @pytest.mark.pbt
    @given(filename=_filename)
    def test_no_partitions_roundtrip(self, filename: str) -> None:
        path = partition_path(filename)
        parsed = parse_partition(path)
        assert parsed.partitions == {}
        assert parsed.filename == filename


# ---------------------------------------------------------------------------
# P2: Config from_dict — no silent corruption
# ---------------------------------------------------------------------------

_config_strategy = st.fixed_dictionaries(
    {},
    optional={
        "backends": st.dictionaries(
            keys=st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
                min_size=1,
                max_size=10,
            ),
            values=st.fixed_dictionaries(
                {"type": _backend_type},
                optional={
                    "options": st.dictionaries(
                        keys=st.text(
                            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
                            min_size=1,
                            max_size=15,
                        ),
                        values=_option_value,
                        max_size=5,
                    ),
                },
            ),
            max_size=3,
        ),
        "stores": st.just({}),
    },
)


class TestConfigFromDict:
    """RegistryConfig.from_dict never silently corrupts data."""

    @pytest.mark.pbt
    @settings(suppress_health_check=[HealthCheck.too_slow])
    @given(data=_config_strategy)
    def test_no_silent_corruption(self, data: dict[str, object]) -> None:
        try:
            rc = RegistryConfig.from_dict(data)
        except (TypeError, ValueError, KeyError):
            return  # valid rejection

        for name, bc in rc.backends.items():
            # BUG-140 regression: type must never be the string "None"
            assert bc.type != "None", f"Backend '{name}' type is string 'None'"
            assert bc.type in {"local", "s3", "sftp", "azure", "memory"}
            # BUG-139 regression: options must support dict operations
            assert bc.options is not None, f"Backend '{name}' options is None"
            _ = bc.options.keys()  # behavioral: must quack like a dict

    @pytest.mark.pbt
    @given(data=_config_strategy)
    def test_backend_types_preserved(self, data: dict[str, object]) -> None:
        try:
            rc = RegistryConfig.from_dict(data)
        except (TypeError, ValueError, KeyError):
            return

        input_backends = data.get("backends", {})
        assert isinstance(input_backends, dict)
        for name, bc in rc.backends.items():
            original = input_backends[name]
            assert isinstance(original, dict)
            assert bc.type == original["type"]

    @pytest.mark.pbt
    @given(data=_config_strategy)
    def test_non_sensitive_options_preserved(self, data: dict[str, object]) -> None:
        """Non-sensitive option values round-trip exactly."""
        from remote_store._config import _SENSITIVE_KEYS

        try:
            rc = RegistryConfig.from_dict(data)
        except (TypeError, ValueError, KeyError):
            return

        input_backends = data.get("backends", {})
        assert isinstance(input_backends, dict)
        for name, bc in rc.backends.items():
            original = input_backends[name]
            assert isinstance(original, dict)
            orig_opts = original.get("options") or {}
            assert isinstance(orig_opts, dict)
            for k, v in bc.options.items():
                if k in _SENSITIVE_KEYS and isinstance(v, Secret):
                    assert v.reveal() == str(orig_opts[k])
                else:
                    assert v == orig_opts[k], f"Option '{k}' mutated: {orig_opts[k]!r} -> {v!r}"


# ---------------------------------------------------------------------------
# P3: Path normalization — idempotent; hostile input normalizes or raises
# ---------------------------------------------------------------------------


class TestPathNormalization:
    """RemotePath normalization is idempotent and rejects hostile input."""

    @pytest.mark.pbt
    @given(segments=st.lists(_path_segment, min_size=1, max_size=5))
    def test_idempotent(self, segments: list[str]) -> None:
        raw = "/".join(segments)
        p1 = RemotePath(raw)
        p2 = RemotePath(str(p1))
        assert str(p1) == str(p2)

    @pytest.mark.pbt
    @given(segments=st.lists(_path_segment, min_size=1, max_size=5))
    def test_no_empty_or_dot_segments(self, segments: list[str]) -> None:
        raw = "/".join(segments)
        p = RemotePath(raw)
        for part in p.parts:
            assert part != ""
            assert part != "."
            assert part != ".."

    @pytest.mark.pbt
    @given(segments=st.lists(_path_segment, min_size=1, max_size=5))
    def test_backslash_normalized(self, segments: list[str]) -> None:
        raw = "\\".join(segments)
        p = RemotePath(raw)
        assert "\\" not in str(p)
        # Should be the same as forward-slash version
        p2 = RemotePath("/".join(segments))
        assert str(p) == str(p2)

    @pytest.mark.pbt
    @given(
        segments=st.lists(_path_segment, min_size=1, max_size=5),
        extra_slashes=st.lists(st.just("/"), min_size=1, max_size=3),
    )
    def test_redundant_slashes_collapsed(self, segments: list[str], extra_slashes: list[str]) -> None:
        # Insert extra slashes between segments
        raw = ("".join(extra_slashes)).join(segments)
        p = RemotePath(raw)
        assert "//" not in str(p)

    @pytest.mark.pbt
    @given(raw=st.text(min_size=0, max_size=50))
    def test_normalizes_or_raises(self, raw: str) -> None:
        """Any input either normalizes successfully or raises InvalidPath."""
        try:
            p = RemotePath(raw)
        except InvalidPath:
            return  # valid rejection
        result = str(p)
        assert result  # non-empty
        assert "\0" not in result
        assert ".." not in result.split("/")
