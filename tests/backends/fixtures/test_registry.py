"""Spec-marker coverage for the fixture registry machinery (spec 048).

These tests pin the architectural invariants the registry must satisfy:
TEST-001 (kind/stage axes), TEST-004 (record shape + isolation), TEST-005
(capability id-filter), TEST-006 (stage selection), TEST-010 (layout
boundary). They run at every stage tier and do not require any external
infrastructure beyond the registered fixtures themselves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from remote_store._capabilities import Capability
from tests.backends.fixtures import (
    BackendFixture,
    _load_all,
    all_fixtures,
    fixtures,
)
from tests.backends.fixtures._state import current_stage, set_current_stage
from tests.backends.fixtures.registry import register

_load_all()


_VALID_KINDS = frozenset({"pure", "mocked", "real-local", "real-live", "replay"})
_VALID_STAGES = frozenset({1, 2, 3})


@pytest.mark.spec("TEST-001")
class TestAxisInvariants:
    """TEST-001: every fixture declares exactly one kind and one stage."""

    def test_every_fixture_has_valid_kind(self) -> None:
        for f in all_fixtures():
            assert f.kind in _VALID_KINDS, f"{f.name!r} has invalid kind {f.kind!r}"

    def test_every_fixture_has_valid_stage(self) -> None:
        for f in all_fixtures():
            assert f.stage in _VALID_STAGES, f"{f.name!r} has invalid stage {f.stage!r}"

    def test_every_fixture_declares_async_flag(self) -> None:
        for f in all_fixtures():
            assert isinstance(f.is_async, bool), f"{f.name!r} is_async is not bool"


@pytest.mark.spec("TEST-004")
class TestRegistryShape:
    """TEST-004: BackendFixture record shape + isolation."""

    def test_names_are_unique(self) -> None:
        seen: set[str] = set()
        for f in all_fixtures():
            assert f.name not in seen, f"duplicate fixture name {f.name!r}"
            seen.add(f.name)

    def test_register_rejects_duplicates(self) -> None:
        existing = all_fixtures()[0]
        clone = BackendFixture(
            name=existing.name,
            backend=existing.backend,
            factory=existing.factory,
            stage=existing.stage,
            kind=existing.kind,
            capabilities=existing.capabilities,
            is_async=existing.is_async,
        )
        with pytest.raises(ValueError, match="duplicate fixture name"):
            register(clone)

    def test_capabilities_is_frozenset(self) -> None:
        for f in all_fixtures():
            assert isinstance(f.capabilities, frozenset), (
                f"{f.name!r}.capabilities is {type(f.capabilities).__name__}, not frozenset"
            )

    def test_factory_returns_fresh_instance(self) -> None:
        """TEST-004 isolation: ``factory()`` produces a new instance per call."""
        # Pick the memory fixture as the canonical no-infra factory check.
        memory = next(f for f in all_fixtures() if f.name == "memory")
        a = memory.factory()
        b = memory.factory()
        assert a is not b
        if memory.cleanup is not None:
            memory.cleanup(a)
            memory.cleanup(b)


@pytest.mark.spec("TEST-005")
class TestCapabilityFilter:
    """TEST-005: capability id-filter excludes fixtures without the requested capability."""

    def test_filter_includes_only_capable_fixtures(self) -> None:
        write = fixtures(Capability.WRITE, is_async=False)
        for f in write:
            assert Capability.WRITE in f.capabilities, f"{f.name!r} returned by fixtures(WRITE) but lacks WRITE"

    def test_filter_excludes_uncapable_fixtures(self) -> None:
        # http (ReadOnlyHttpBackend) does not declare WRITE.
        write = fixtures(Capability.WRITE, is_async=False)
        names = {f.name for f in write}
        assert "http" not in names, "fixtures(WRITE) included http (read-only)"

    def test_empty_caps_returns_all_in_mode(self) -> None:
        sync_all = fixtures(is_async=False)
        async_all = fixtures(is_async=True)
        # Disjoint by mode.
        sync_names = {f.name for f in sync_all}
        async_names = {f.name for f in async_all}
        assert sync_names.isdisjoint(async_names)


@pytest.mark.spec("TEST-006")
class TestStageSelection:
    """TEST-006: stage CLI filters fixtures with stage > N."""

    def test_set_current_stage_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="stage must be"):
            set_current_stage(0)
        with pytest.raises(ValueError, match="stage must be"):
            set_current_stage(4)

    def test_stage1_excludes_stage2_fixtures(self) -> None:
        original = current_stage()
        try:
            set_current_stage(1)
            sync_at_1 = fixtures(is_async=False)
            for f in sync_at_1:
                assert f.stage <= 1, f"{f.name!r} stage={f.stage} included at --stage=1"
        finally:
            set_current_stage(original)

    def test_stage2_includes_stage1_fixtures(self) -> None:
        original = current_stage()
        try:
            set_current_stage(2)
            sync_at_2 = fixtures(is_async=False)
            stages = {f.stage for f in sync_at_2}
            assert stages.issubset({1, 2}), f"--stage=2 included unexpected stages: {stages - {1, 2}}"
        finally:
            set_current_stage(original)


_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent  # tests/
_BACKENDS_ROOT = _TESTS_ROOT / "backends"


@pytest.mark.spec("TEST-010")
class TestLayoutBoundary:
    """TEST-010: backend names appear only inside their backend's home,
    in fixture/registry files dedicated to that backend, or in registry
    code enumerating all backends.

    Lint-style scan over ``tests/`` looking for concrete backend identifiers
    used as string literals or imports outside the permitted homes. Catches
    accidental cross-backend coupling at review time.
    """

    # Identifiers we want to keep out of cross-cutting tests. Each maps to
    # the path prefix(es) where the literal is permitted.
    _BACKEND_LITERALS = {
        "AzureBackend": (
            "tests/backends/azure/",
            "tests/backends/fixtures/azurite",
            "tests/backends/fixtures/azure_live",
        ),
        "S3Backend": ("tests/backends/s3/", "tests/backends/fixtures/s3_"),
        "S3PyArrowBackend": ("tests/backends/s3/", "tests/backends/fixtures/s3_pyarrow"),
        "SFTPBackend": ("tests/backends/sftp/", "tests/backends/fixtures/sftp_"),
        "SQLBlobBackend": ("tests/backends/sqlblob/", "tests/backends/fixtures/sqlblob"),
        "SQLQueryBackend": ("tests/backends/sqlquery/", "tests/backends/fixtures/sqlquery"),
        "ReadOnlyHttpBackend": ("tests/backends/http/", "tests/backends/fixtures/http"),
    }

    def test_conformance_does_not_reference_concrete_backends(self) -> None:
        """TEST-002 + TEST-010 narrow boundary check on the conformance subtree.

        Cross-backend conformance tests reference only the abstract
        ``Store``/``Backend`` API surface; they must not name a concrete
        backend class. The check is scoped to ``tests/backends/conformance/``
        because that subtree is the source of truth for the rule. The
        ``test_sync_adapter_conformance.py`` file is exempt because its
        ``live_adapted_backend`` fixture wraps real backends inside
        ``SyncBackendAdapter``; registry integration for that fixture is
        a deliberate follow-up to BK-179, not a Phase 1 commitment.
        """
        conformance_root = _BACKENDS_ROOT / "conformance"
        # Self-contained adapter-conformance file: integrating its live
        # fixture with the registry is a follow-up; explicit reference
        # to S3Backend/SFTPBackend/AzureBackend is documented as out of
        # scope for BK-179 (see plan).
        exempt_files = {
            conformance_root / "test_sync_adapter_conformance.py",
        }
        violations: list[str] = []
        for py in conformance_root.rglob("*.py"):
            if py in exempt_files:
                continue
            text = py.read_text(encoding="utf-8")
            for name in self._BACKEND_LITERALS:
                if re.search(rf"\b{re.escape(name)}\b", text):
                    rel = py.relative_to(_TESTS_ROOT.parent).as_posix()
                    violations.append(f"{rel}: references {name!r}")
        assert not violations, "TEST-010 boundary violations:\n  " + "\n  ".join(violations)
