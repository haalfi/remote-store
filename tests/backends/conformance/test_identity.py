"""Backend identity, lifecycle, and resolve conformance.

Universal tests that every Backend must satisfy regardless of capability.
No capability filter is applied at the class level; the fixture registry
contributes every Stage <= --stage entry. Spec markers preserved verbatim
from the pre-split conformance suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import CapabilityNotSupported
from tests.backends.fixtures import BackendFixture, all_fixtures, fixture_params

if TYPE_CHECKING:
    from remote_store._backend import Backend


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendIdentity:
    """BE-001 through BE-003: backend identity and capabilities."""

    @pytest.mark.spec("BE-001")
    def test_backend_is_instance(self, backend: Backend) -> None:
        from remote_store._backend import Backend as BackendABC

        assert isinstance(backend, BackendABC)

    @pytest.mark.spec("BE-002")
    @pytest.mark.spec("MEM-002")
    def test_name_is_string(self, backend: Backend) -> None:
        assert isinstance(backend.name, str)
        assert len(backend.name) > 0

    @pytest.mark.spec("BE-003")
    @pytest.mark.spec("MEM-003")
    def test_capabilities_is_capabilityset(self, backend: Backend) -> None:
        assert isinstance(backend.capabilities, CapabilitySet)

    @pytest.mark.spec("BE-003")
    def test_capabilities_subset_of_class_var(self, backend: Backend) -> None:
        """ID-159: instance capabilities must be a subset of the class-level CAPABILITIES."""
        cls = type(backend)
        assert set(backend.capabilities) <= set(cls.CAPABILITIES)

    @pytest.mark.spec("MEM-004")
    def test_repr_returns_string(self, backend: Backend) -> None:
        r = repr(backend)
        assert isinstance(r, str)
        assert backend.name in r.lower() or backend.__class__.__name__ in r

    def test_repr_masks_secrets(self, backend: Backend) -> None:
        """AF-008: sensitive values must not appear in repr output."""
        r = repr(backend)
        for secret in ("testing", "testpass", "Eby8vdM02xNOcqFlqUwJPLlmEtl"):
            assert secret not in r, f"Secret {secret!r} leaked in repr: {r}"


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendLifecycle:
    """BE-020: close is callable."""

    @pytest.mark.spec("BE-020")
    @pytest.mark.spec("MEM-018")
    def test_close_is_callable(self, backend: Backend) -> None:
        result = backend.close()
        assert result is None


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendUnwrap:
    """BE-022: unwrap raises by default."""

    @pytest.mark.spec("BE-022")
    @pytest.mark.spec("MEM-019")
    @pytest.mark.spec("MEM-020")
    def test_unwrap_raises_by_default(self, backend: Backend) -> None:
        with pytest.raises(CapabilityNotSupported):
            backend.unwrap(str)


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendCapabilityGate:
    """CAP-004: require() rejects an undeclared capability, naming it."""

    @pytest.mark.spec("CAP-004")
    def test_require_missing_capability_raises_with_name(self, backend: Backend) -> None:
        """cap not in capabilities => CapabilityNotSupported(CapabilityName(cap), name).

        Mirrors the Dafny ``RequireCapability`` postcondition: the error must
        carry the offending capability's *name* (``cap.value``), not just the
        exception type. Run against every fixture; a backend that happens to
        declare every capability self-skips (no gate to exercise).
        """
        missing = next((c for c in Capability if c not in backend.capabilities), None)
        if missing is None:
            pytest.skip("Backend declares every capability; no gate to exercise")
        with pytest.raises(CapabilityNotSupported) as exc_info:
            backend.capabilities.require(missing, backend=backend.name)
        assert exc_info.value.capability == missing.value


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendNativePath:
    """BE-025: native_path() default is identity."""

    @pytest.mark.spec("BE-025")
    @pytest.mark.spec("NPR-020")
    def test_native_path_round_trip(self, backend: Backend) -> None:
        """native_path is the inverse of to_key (NPR-020)."""
        assert backend.to_key(backend.native_path("some/key")) == "some/key"

    @pytest.mark.spec("BE-025")
    @pytest.mark.spec("NPR-021")
    def test_native_path_empty_returns_root(self, backend: Backend) -> None:
        """native_path('') returns the backend's root (NPR-021)."""
        assert isinstance(backend.native_path(""), str)


_RESOLVE_PATHS = [
    pytest.param("simple.txt", id="simple"),
    pytest.param("dir/sub/file.txt", id="nested"),
    pytest.param("", id="empty"),
]


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendResolveDefault:
    """RES-020: Backend.resolve() default implementation returns a ResolutionPlan."""

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_returns_resolution_plan(self, backend: Backend, path: str) -> None:
        from remote_store._resolution import ResolutionPlan

        plan = backend.resolve(path)
        assert isinstance(plan, ResolutionPlan)
        assert plan.key == path

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_kind_is_non_empty_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.kind == backend.name

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_backend_is_non_empty_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.backend == backend.name

    @pytest.mark.spec("RES-020")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_native_path_is_string(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.native_path == backend.native_path(path)


def _atomic_move_canonical_fixtures() -> list[Any]:
    """Pick one sync registry entry per backend family.

    Several families register more than one fixture (``sftp_inproc`` +
    ``sftp_docker``, ``s3_pyarrow_moto`` + ``s3_pyarrow_minio``); the
    ATOMIC_MOVE classification is family-level, so iterating over the
    full registry would assert the same fact twice. Dedup by
    ``BackendFixture.backend`` and keep the first entry seen per family.
    """
    seen: set[str] = set()
    out: list[Any] = []
    for f in all_fixtures():
        if f.is_async or f.backend in seen:
            continue
        seen.add(f.backend)
        out.append(pytest.param(f, id=f.backend))
    return out


class TestAtomicMoveCapability:
    """CAP-001: ATOMIC_MOVE capability declared by backends with atomic move semantics.

    Classification is by ``BackendFixture.backend`` (registry family
    name), not by the live ``backend.name`` property; the registry's
    family field is what's stable across same-backend fixture pairs.
    sql-query is not parametrised here; it has its own test module.
    """

    _DECLARES = {"local", "memory", "dafny", "sqlblob"}
    _DOES_NOT_DECLARE = {"s3", "s3_pyarrow", "s3_boto3", "azure", "sftp", "http"}

    @pytest.mark.spec("CAP-001")
    @pytest.mark.parametrize("fixture", _atomic_move_canonical_fixtures())
    def test_atomic_move_capability_declaration(self, fixture: BackendFixture) -> None:
        family = fixture.backend
        supports = Capability.ATOMIC_MOVE in fixture.capabilities
        if family in self._DECLARES:
            assert supports, f"{family} should declare ATOMIC_MOVE"
        elif family in self._DOES_NOT_DECLARE:
            assert not supports, f"{family} should not declare ATOMIC_MOVE"
        else:
            pytest.fail(
                f"Backend family {family!r} is not listed in _DECLARES or _DOES_NOT_DECLARE. "
                "Update TestAtomicMoveCapability to classify this family."
            )


def _seekable_canonical_fixtures() -> list[Any]:
    """One sync fixture per backend family for SEEKABLE_READ declaration check.

    Several families register more than one fixture; the declaration is
    family-level, so dedup by ``BackendFixture.backend`` keeps one entry each.
    """
    seen: set[str] = set()
    out: list[Any] = []
    for f in all_fixtures():
        if f.is_async or f.backend in seen:
            continue
        seen.add(f.backend)
        out.append(pytest.param(f, id=f.backend))
    return out


class TestSeekableCapability:
    """SEEK-001: backends that always return seekable streams declare SEEKABLE_READ."""

    _DECLARES = {"local", "memory", "s3", "s3_pyarrow", "s3_boto3", "sftp", "sqlblob", "dafny"}
    _DOES_NOT_DECLARE = {"azure", "http"}

    @pytest.mark.spec("SEEK-001")
    @pytest.mark.parametrize("fixture", _seekable_canonical_fixtures())
    def test_seekable_read_capability_declaration(self, fixture: BackendFixture) -> None:
        family = fixture.backend
        supports = Capability.SEEKABLE_READ in fixture.capabilities
        if family in self._DECLARES:
            assert supports, f"{family} should declare SEEKABLE_READ"
        elif family in self._DOES_NOT_DECLARE:
            assert not supports, f"{family} should not declare SEEKABLE_READ"
        else:
            pytest.fail(
                f"Backend family {family!r} is not listed in _DECLARES or _DOES_NOT_DECLARE. "
                "Update TestSeekableCapability to classify this family."
            )


@pytest.mark.parametrize("backend", fixture_params(), indirect=True)
class TestBackendResolveUniversalContract:
    """RES-025: Universal contract for Backend.resolve()."""

    @pytest.mark.spec("RES-025")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_native_path_matches_backend(self, backend: Backend, path: str) -> None:
        plan = backend.resolve(path)
        assert plan.native_path == backend.native_path(path)

    @pytest.mark.spec("RES-025")
    @pytest.mark.parametrize("path", _RESOLVE_PATHS)
    def test_details_is_mapping(self, backend: Backend, path: str) -> None:
        from collections.abc import Mapping

        plan = backend.resolve(path)
        assert isinstance(plan.details, Mapping)
        assert plan.kind == backend.name
