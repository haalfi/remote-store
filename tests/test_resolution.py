"""Tests for ResolutionPlan and Store/ProxyStore.resolve() -- RES-010 through RES-040."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from remote_store._resolution import ResolutionPlan
from remote_store._store import Store
from remote_store.backends._memory import MemoryBackend

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


@pytest.fixture
def store(backend: MemoryBackend) -> Store:
    return Store(backend=backend, root_path="data")


@pytest.fixture
def store_no_root(backend: MemoryBackend) -> Store:
    return Store(backend=backend)


# ---------------------------------------------------------------------------
# RES-010: ResolutionPlan dataclass
# ---------------------------------------------------------------------------


class TestResolutionPlanDataclass:
    """RES-010: ResolutionPlan is a frozen, unhashable dataclass with immutable details."""

    @pytest.mark.spec("RES-010")
    def test_fields_populated(self) -> None:
        plan = ResolutionPlan(
            kind="memory",
            backend="memory",
            key="file.txt",
            native_path="file.txt",
            details={},
        )
        assert plan.kind == "memory"
        assert plan.backend == "memory"
        assert plan.key == "file.txt"
        assert plan.native_path == "file.txt"

    @pytest.mark.spec("RES-010")
    def test_frozen_rejects_attribute_assignment(self) -> None:
        plan = ResolutionPlan(
            kind="memory",
            backend="memory",
            key="file.txt",
            native_path="file.txt",
            details={},
        )
        with pytest.raises(AttributeError, match="cannot assign|has no setter"):
            plan.kind = "other"  # type: ignore[misc]

    @pytest.mark.spec("RES-010")
    def test_unhashable(self) -> None:
        plan = ResolutionPlan(
            kind="memory",
            backend="memory",
            key="file.txt",
            native_path="file.txt",
            details={},
        )
        with pytest.raises(TypeError, match="unhashable"):
            hash(plan)

    @pytest.mark.spec("RES-010")
    def test_details_immutable_at_runtime(self) -> None:
        plan = ResolutionPlan(
            kind="local",
            backend="local",
            key="file.txt",
            native_path="/root/file.txt",
            details={"root": "/root"},
        )
        with pytest.raises(TypeError, match="does not support item assignment"):
            plan.details["new_key"] = "value"  # type: ignore[index]

    @pytest.mark.spec("RES-010")
    def test_details_is_mapping_proxy(self) -> None:
        plan = ResolutionPlan(
            kind="memory",
            backend="memory",
            key="file.txt",
            native_path="file.txt",
            details={"a": 1},
        )
        assert isinstance(plan.details, MappingProxyType)
        assert isinstance(plan.details, Mapping)

    @pytest.mark.spec("RES-010")
    def test_repr_readable(self) -> None:
        plan = ResolutionPlan(
            kind="memory",
            backend="memory",
            key="file.txt",
            native_path="file.txt",
            details={},
        )
        r = repr(plan)
        assert "ResolutionPlan" in r
        assert "memory" in r
        assert "file.txt" in r

    @pytest.mark.spec("RES-010")
    @pytest.mark.parametrize(
        ("kind", "backend_name", "key", "native_path", "details"),
        [
            pytest.param("s3", "s3", "data/f.csv", "s3://bucket/data/f.csv", {"bucket": "b"}, id="s3"),
            pytest.param("local", "local", "f.txt", "/tmp/f.txt", {"root": "/tmp"}, id="local"),
            pytest.param("memory", "memory", "", "", {}, id="empty_key"),
        ],
    )
    def test_various_field_combinations(
        self, kind: str, backend_name: str, key: str, native_path: str, details: dict[str, str]
    ) -> None:
        plan = ResolutionPlan(kind=kind, backend=backend_name, key=key, native_path=native_path, details=details)
        assert plan.kind == kind
        assert plan.backend == backend_name
        assert plan.key == key
        assert plan.native_path == native_path
        # details accessible as Mapping
        for k, v in details.items():
            assert plan.details[k] == v


# ---------------------------------------------------------------------------
# RES-030: Store.resolve() key rebasing
# ---------------------------------------------------------------------------


class TestStoreResolveKeyRebasing:
    """RES-030: Store.resolve() rebases key to store-relative."""

    @pytest.mark.spec("RES-030")
    def test_with_root_path_key_is_store_relative(self, store: Store) -> None:
        plan = store.resolve("sub/file.txt")
        assert plan.key == "sub/file.txt"

    @pytest.mark.spec("RES-030")
    def test_without_root_path_key_equals_input(self, store_no_root: Store) -> None:
        plan = store_no_root.resolve("file.txt")
        assert plan.key == "file.txt"

    @pytest.mark.spec("RES-030")
    def test_resolve_empty_string_resolves_root(self, store: Store) -> None:
        plan = store.resolve("")
        assert plan.key == ""

    @pytest.mark.spec("RES-030")
    def test_native_path_includes_root_prefix(self, store: Store) -> None:
        plan = store.resolve("file.txt")
        # With root_path="data", native_path should include the root
        assert "data" in plan.native_path


# ---------------------------------------------------------------------------
# RES-035: Store.resolve() invariant
# ---------------------------------------------------------------------------


class TestStoreResolveInvariant:
    """RES-035: store.native_path(key) == store.resolve(key).native_path."""

    @pytest.mark.spec("RES-035")
    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("simple.txt", id="simple"),
            pytest.param("dir/sub/file.txt", id="nested"),
            pytest.param("", id="root"),
        ],
    )
    def test_invariant_with_root_path(self, store: Store, key: str) -> None:
        assert store.native_path(key) == store.resolve(key).native_path

    @pytest.mark.spec("RES-035")
    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("simple.txt", id="simple"),
            pytest.param("dir/sub/file.txt", id="nested"),
            pytest.param("", id="root"),
        ],
    )
    def test_invariant_without_root_path(self, store_no_root: Store, key: str) -> None:
        assert store_no_root.native_path(key) == store_no_root.resolve(key).native_path


# ---------------------------------------------------------------------------
# RES-040: ProxyStore.resolve() delegation
# ---------------------------------------------------------------------------


class TestProxyStoreResolveDelegation:
    """RES-040: ProxyStore.resolve() delegates to inner store unchanged."""

    @pytest.mark.spec("RES-040")
    def test_plan_matches_inner_store(self) -> None:
        from remote_store._proxy import ProxyStore

        class _TestProxy(ProxyStore):
            def _wrap_child(self, inner_child: Store) -> _TestProxy:
                return _TestProxy(inner_child)

        inner = Store(backend=MemoryBackend(), root_path="data")
        proxy = _TestProxy(inner)

        inner_plan = inner.resolve("file.txt")
        proxy_plan = proxy.resolve("file.txt")

        assert proxy_plan.kind == inner_plan.kind
        assert proxy_plan.backend == inner_plan.backend
        assert proxy_plan.key == inner_plan.key
        assert proxy_plan.native_path == inner_plan.native_path
        assert dict(proxy_plan.details) == dict(inner_plan.details)

    @pytest.mark.spec("RES-040")
    def test_proxy_resolve_empty_key(self) -> None:
        from remote_store._proxy import ProxyStore

        class _TestProxy(ProxyStore):
            def _wrap_child(self, inner_child: Store) -> _TestProxy:
                return _TestProxy(inner_child)

        inner = Store(backend=MemoryBackend(), root_path="root")
        proxy = _TestProxy(inner)

        inner_plan = inner.resolve("")
        proxy_plan = proxy.resolve("")
        assert proxy_plan.key == inner_plan.key
        assert proxy_plan.native_path == inner_plan.native_path


# ---------------------------------------------------------------------------
# child().resolve() interaction
# ---------------------------------------------------------------------------


class TestChildResolve:
    """child().resolve() returns plan with child-relative key."""

    @pytest.mark.spec("RES-030")
    def test_child_resolve_key_is_child_relative(self) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        child = store.child("sub")
        plan = child.resolve("file.txt")
        assert plan.key == "file.txt"

    @pytest.mark.spec("RES-035")
    def test_child_resolve_invariant(self) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        child = store.child("sub")
        assert child.native_path("file.txt") == child.resolve("file.txt").native_path

    @pytest.mark.spec("RES-030")
    def test_child_resolve_native_path_includes_full_prefix(self) -> None:
        store = Store(backend=MemoryBackend(), root_path="data")
        child = store.child("sub")
        plan = child.resolve("file.txt")
        # native_path should contain both root and child prefix
        assert "data" in plan.native_path
        assert "sub" in plan.native_path
