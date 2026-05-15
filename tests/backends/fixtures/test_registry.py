"""Spec-marker coverage for the fixture registry machinery (spec 048).

These tests pin the architectural invariants the registry must satisfy:
TEST-001 (kind/stage axes), TEST-004 (record shape + isolation), TEST-005
(capability id-filter), TEST-006 (stage selection), TEST-010 (layout
boundary). They run at every stage tier and do not require any external
infrastructure beyond the registered fixtures themselves.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

import pytest

from remote_store._backend import Backend
from remote_store._capabilities import Capability
from tests.backends.fixtures import (
    BackendFixture,
    _load_all,
    all_fixtures,
    fixture_params,
    fixtures,
)

# ``_parse_backend`` and ``_parse_fixture`` are deliberate private-reach
# imports: the ``TestClosedEnumValidation`` class needs direct access to
# the loader's validation internals to round-trip synthetic raw dicts
# without mutating the on-disk TOML. They stay out of ``_loader.__all__``
# because they are not part of the runtime calling contract — only tests
# pinning the closed-enum branches consume them.
from tests.backends.fixtures._loader import (
    VALID_CONTAINERS,
    VALID_KINDS,
    VALID_STAGES,
    VALID_TRANSPORTS,
    _parse_backend,
    _parse_fixture,
    load_backends,
    load_fixtures,
)
from tests.backends.fixtures._state import current_stage, set_current_stage
from tests.backends.fixtures.registry import register

_load_all()


@pytest.mark.spec("TEST-001")
class TestAxisInvariants:
    """TEST-001: every fixture declares exactly one kind and one stage."""

    def test_every_fixture_has_valid_kind(self) -> None:
        for f in all_fixtures():
            assert f.kind in VALID_KINDS, f"{f.name!r} has invalid kind {f.kind!r}"

    def test_every_fixture_has_valid_stage(self) -> None:
        for f in all_fixtures():
            assert f.stage in VALID_STAGES, f"{f.name!r} has invalid stage {f.stage!r}"

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

    def test_toml_round_trips_to_records(self) -> None:
        """TOML loader populates every field on the registered ``BackendFixture``.

        Reads ``fixtures.toml`` directly and compares the loader's view of
        each entry against the registered record. Pins the contract that
        ``transport`` / ``container`` / ``flat_namespace`` /
        ``self_op_supported`` survive the round-trip without manual
        per-field copying — adding a new TOML field requires one update
        to ``FixtureDescriptor.to_kwargs`` and one matching field on
        ``BackendFixture``; this test catches drift.
        """
        descriptors = load_fixtures()
        for f in all_fixtures():
            desc = descriptors[f.name]
            # Pin the TOML key → ``BackendFixture.name`` link explicitly:
            # a mismatch between ``[fixture.<key>]`` and the registered
            # ``name`` would slip through every other field-level assert.
            assert f.name == desc.name, f"{f.name!r} name drift"
            assert f.backend == desc.backend
            assert f.stage == desc.stage
            assert f.kind == desc.kind
            assert f.is_async == desc.is_async
            assert f.flat_namespace == desc.flat_namespace
            assert f.self_op_supported == desc.self_op_supported
            assert f.transport == desc.transport, f"{f.name!r} transport drift"
            assert f.container == desc.container, f"{f.name!r} container drift"
            assert f.transport in VALID_TRANSPORTS
            assert f.container in VALID_CONTAINERS

    def test_live_env_fields_parse_on_descriptor(self) -> None:
        """``FixtureDescriptor`` carries the live-cloud env metadata that
        ``BackendFixture.to_kwargs`` deliberately omits.

        The fields are static-but-out-of-band: they are read by future
        PR 2 work (mutate scopes, CI plumbing) rather than by the
        ``BackendFixture`` runtime contract, so they sit on the
        descriptor and not on the registered record. This test pins
        the parsing path so a typo in ``live_creds_env`` would fail
        in CI immediately, not when PR 2 first reads it.
        """
        fixtures_by_name = load_fixtures()

        live = fixtures_by_name["azure_live"]
        assert live.live_opt_in_env == "RS_TEST_LIVE_HNS"
        # tuple, not list — ``_require_str_list`` froze the sequence so
        # ``FixtureDescriptor`` stays hashable / immutable.
        assert isinstance(live.live_creds_env, tuple)
        assert live.live_creds_env == ("AZURE_STORAGE_CONNECTION_STRING",)

        live_async = fixtures_by_name["azure_live_async"]
        assert live_async.live_opt_in_env == "RS_TEST_LIVE_HNS"
        assert isinstance(live_async.live_creds_env, tuple)
        assert live_async.live_creds_env == ("AZURE_STORAGE_CONNECTION_STRING",)

        s3_live = fixtures_by_name["s3_live"]
        assert s3_live.live_opt_in_env == "RS_TEST_LIVE_S3"
        assert isinstance(s3_live.live_creds_env, tuple)
        assert s3_live.live_creds_env == (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_DEFAULT_REGION",
        )

        # Non-live fixtures default to ``None`` / empty tuple — the
        # absence of a TOML key is meaningful.
        non_live = fixtures_by_name["memory"]
        assert non_live.live_opt_in_env is None
        assert non_live.live_creds_env == ()

    def test_bk185_azurite_flat_azure_live_hns(self) -> None:
        """BK-185 regression: same backend family can disagree on flat_namespace.

        ``azurite`` (emulator) and ``azure_live`` (real ADLS Gen2) both
        carry ``backend == "azure"`` but their namespaces differ — the
        emulator is flat, real ADLS Gen2 has HNS. The old
        ``_FLAT_NAMESPACE_BACKENDS`` set keyed by ``backend.name`` could
        not represent the split; this test pins the per-fixture override
        and would have failed before BK-186 PR 1.
        """
        by_name = {f.name: f for f in all_fixtures()}
        assert by_name["azurite"].flat_namespace is True, "azurite emulator is flat-namespace"
        assert by_name["azure_live"].flat_namespace is False, "live HNS has real directories"
        assert by_name["azure_live_async"].flat_namespace is False, "async live HNS has real directories"
        # Both fixtures still share the same backend family.
        assert by_name["azurite"].backend == by_name["azure_live"].backend == "azure"


def _valid_backend_raw() -> dict[str, object]:
    """Return a minimal valid raw dict for ``_parse_backend``.

    The negative-path tests below mutate one field at a time off this
    baseline so each test exercises a single branch.
    """
    return {"transport": "fs", "sources": [], "async_sources": []}


def _valid_fixture_raw() -> dict[str, object]:
    """Return a minimal valid raw dict for ``_parse_fixture``."""
    return {
        "backend": "memory",
        "stage": 1,
        "kind": "real-local",
        "container": "none",
        "is_async": False,
    }


def _backends_for_fixture_tests() -> dict[str, object]:
    """Return the parsed backends.toml view, used as the cross-reference
    map for ``_parse_fixture`` negative-path tests.

    Cached at the module level by ``functools.cache`` on
    ``load_backends``; calling it here is effectively free.
    """
    return load_backends()  # type: ignore[return-value]


@pytest.mark.spec("TEST-004")
class TestClosedEnumValidation:
    """Every ``ValueError`` branch in the loader's closed-enum validation
    has explicit regression coverage. Fail-loud parsing is the load-bearing
    contract introduced by BK-186 PR 1; without these tests, a regression
    that loosens validation would land silently — exactly the failure mode
    the loader was designed to prevent.

    The tests round-trip synthetic raw dicts through ``_parse_backend`` /
    ``_parse_fixture`` directly so they do not need to mutate the on-disk
    TOML files.
    """

    # region: _parse_backend negative paths

    @pytest.mark.parametrize("transport", ["", "tcp", "ftp", "FS", None, 1, 1.5])
    def test_parse_backend_rejects_invalid_transport(self, transport: object) -> None:
        raw = _valid_backend_raw()
        raw["transport"] = transport
        with pytest.raises(ValueError, match="transport must be one of"):
            _parse_backend("x", raw)

    @pytest.mark.parametrize("flat_ns", [0, 1, "yes", None, "true"])
    def test_parse_backend_rejects_non_bool_flat_namespace(self, flat_ns: object) -> None:
        raw = _valid_backend_raw()
        raw["flat_namespace"] = flat_ns
        with pytest.raises(ValueError, match="flat_namespace must be bool"):
            _parse_backend("x", raw)

    @pytest.mark.parametrize("self_op", [0, 1, "yes", None])
    def test_parse_backend_rejects_non_bool_self_op_supported(self, self_op: object) -> None:
        raw = _valid_backend_raw()
        raw["self_op_supported"] = self_op
        with pytest.raises(ValueError, match="self_op_supported must be bool"):
            _parse_backend("x", raw)

    @pytest.mark.parametrize(
        "sources",
        [
            "src/path.py",  # bare string, not a list
            ["ok.py", 1],  # list with non-string member
            [None],  # list of None
            {"a": "b"},  # dict
        ],
    )
    def test_parse_backend_rejects_non_string_list_sources(self, sources: object) -> None:
        raw = _valid_backend_raw()
        raw["sources"] = sources
        with pytest.raises(ValueError, match="must be a list of strings"):
            _parse_backend("x", raw)

    @pytest.mark.parametrize("async_sources", ["solo.py", ["ok.py", 2]])
    def test_parse_backend_rejects_non_string_list_async_sources(self, async_sources: object) -> None:
        raw = _valid_backend_raw()
        raw["async_sources"] = async_sources
        with pytest.raises(ValueError, match="must be a list of strings"):
            _parse_backend("x", raw)

    # endregion

    # region: _parse_fixture negative paths

    @pytest.mark.parametrize("backend", [None, 1, ["memory"], {"name": "memory"}])
    def test_parse_fixture_rejects_non_string_backend(self, backend: object) -> None:
        raw = _valid_fixture_raw()
        raw["backend"] = backend
        with pytest.raises(ValueError, match="backend must be a string"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    def test_parse_fixture_rejects_unknown_backend(self) -> None:
        raw = _valid_fixture_raw()
        raw["backend"] = "no-such-backend"
        with pytest.raises(ValueError, match="not declared in backends.toml"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("stage", [0, 4, 5, "1", None])
    def test_parse_fixture_rejects_invalid_stage(self, stage: object) -> None:
        raw = _valid_fixture_raw()
        raw["stage"] = stage
        with pytest.raises(ValueError, match="stage must be one of"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("kind", ["", "real", "wrong", None, 1])
    def test_parse_fixture_rejects_invalid_kind(self, kind: object) -> None:
        raw = _valid_fixture_raw()
        raw["kind"] = kind
        with pytest.raises(ValueError, match="kind must be one of"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("container", ["", "broken", "MINIO", None, 1])
    def test_parse_fixture_rejects_invalid_container(self, container: object) -> None:
        raw = _valid_fixture_raw()
        raw["container"] = container
        with pytest.raises(ValueError, match="container must be one of"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("is_async", [0, 1, "no", None])
    def test_parse_fixture_rejects_non_bool_is_async(self, is_async: object) -> None:
        raw = _valid_fixture_raw()
        raw["is_async"] = is_async
        with pytest.raises(ValueError, match="is_async must be bool"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("flat_ns", [0, 1, "yes", None])
    def test_parse_fixture_rejects_non_bool_flat_namespace(self, flat_ns: object) -> None:
        raw = _valid_fixture_raw()
        raw["flat_namespace"] = flat_ns
        with pytest.raises(ValueError, match="flat_namespace must be bool"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("self_op", [0, 1, "yes", None])
    def test_parse_fixture_rejects_non_bool_self_op_supported(self, self_op: object) -> None:
        raw = _valid_fixture_raw()
        raw["self_op_supported"] = self_op
        with pytest.raises(ValueError, match="self_op_supported must be bool"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize("opt_in", [1, ["RS_X"], {"name": "RS_X"}])
    def test_parse_fixture_rejects_non_string_live_opt_in_env(self, opt_in: object) -> None:
        raw = _valid_fixture_raw()
        raw["live_opt_in_env"] = opt_in
        with pytest.raises(ValueError, match="live_opt_in_env must be a string"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    @pytest.mark.parametrize(
        "creds_env",
        [
            "RS_X",  # bare string, not a list
            ["RS_OK", 1],  # list with non-string
            [None],
        ],
    )
    def test_parse_fixture_rejects_non_string_list_live_creds_env(self, creds_env: object) -> None:
        raw = _valid_fixture_raw()
        raw["live_creds_env"] = creds_env
        with pytest.raises(ValueError, match="live_creds_env.*must be a list of strings"):
            _parse_fixture("x", raw, _backends_for_fixture_tests())

    # endregion

    # region: positive baseline (guards against vacuous negative-path tests)

    def test_valid_backend_baseline_parses(self) -> None:
        """Pin the positive path: every negative-path test mutates one field off
        this baseline. If the baseline itself stopped parsing, the rest of the
        class would become vacuous passes.
        """
        result = _parse_backend("x", _valid_backend_raw())
        assert result.transport == "fs"
        assert result.flat_namespace is False
        assert result.self_op_supported is True

    def test_valid_fixture_baseline_parses(self) -> None:
        """Pin the positive path for ``_parse_fixture``."""
        result = _parse_fixture("x", _valid_fixture_raw(), _backends_for_fixture_tests())
        assert result.backend == "memory"
        assert result.stage == 1

    # endregion


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


# Concrete backend class names whose presence in cross-backend
# conformance code is a TEST-010 boundary violation. Class names aren't
# in the TOML registry (TOML keys are family identifiers like "azure"),
# so this list is hand-maintained. The current
# ``test_conformance_does_not_reference_concrete_backends`` consumes only
# these names; per-backend permitted-path prefixes are not enforced.
_BACKEND_CLASS_NAMES: tuple[str, ...] = (
    "AzureBackend",
    "S3Backend",
    "S3PyArrowBackend",
    "SFTPBackend",
    "SQLBlobBackend",
    "SQLQueryBackend",
    "ReadOnlyHttpBackend",
)


@pytest.mark.spec("TEST-010")
class TestLayoutBoundary:
    """TEST-010: backend names appear only inside their backend's home,
    in fixture/registry files dedicated to that backend, or in registry
    code enumerating all backends.

    Lint-style scan over ``tests/backends/conformance/`` for concrete
    backend class names. Catches accidental cross-backend coupling at
    review time.
    """

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
            for name in _BACKEND_CLASS_NAMES:
                if re.search(rf"\b{re.escape(name)}\b", text):
                    rel = py.relative_to(_TESTS_ROOT.parent).as_posix()
                    violations.append(f"{rel}: references {name!r}")
        assert not violations, "TEST-010 boundary violations:\n  " + "\n  ".join(violations)


class TestFixtureParamsXdistWorkerFilter:
    """``fixture_params`` drops ``container == "sftp"`` entries under xdist.

    Pins the carve-out contract: when ``PYTEST_XDIST_WORKER`` is set
    (i.e. inside an xdist worker subprocess), ``sftp_docker`` is filtered
    out of the parametrize set so the atmoz/sftp daemon never sees
    concurrent connections from multiple workers. The CI workflow's
    second serial pytest pass picks up the carved-out variants.

    A future change that flips the predicate sense or generalises the
    container test would otherwise only surface as silent re-introduction
    of the concurrent-SFTP failure mode the carve-out exists to prevent.
    """

    @staticmethod
    def _with_stage_2(monkeypatch: pytest.MonkeyPatch) -> None:
        """Force Stage 2 for the test so sftp_docker is in scope regardless
        of whether the host Docker daemon is reachable. The stage is a
        module-level global, so monkeypatch.setattr restores it on teardown.
        """
        from tests.backends.fixtures import _state

        monkeypatch.setattr(_state, "_CURRENT_STAGE", 2)

    def test_no_sftp_under_xdist_worker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._with_stage_2(monkeypatch)
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
        params = fixture_params()
        assert all(p.values[0].container != "sftp" for p in params), (
            "fixture_params() under PYTEST_XDIST_WORKER must exclude sftp_docker"
        )

    def test_sftp_present_without_xdist_worker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._with_stage_2(monkeypatch)
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        params = fixture_params()
        sftp_ids = [p.id for p in params if p.values[0].container == "sftp"]
        assert sftp_ids, "fixture_params() outside xdist must include the sftp_docker fixture"


@pytest.mark.spec("TEST-004")
class TestFixtureCleanupContract:
    """Sync backends that override ``Backend.close`` must register ``cleanup=``.

    BUG-210 surfaced the failure mode: ``azure_replay`` registered without
    ``cleanup=``, so the conformance ``backend`` fixture skipped
    ``backend.close()`` for every replay-fixture instance. The unclosed
    clients fired ``ResourceWarning`` at GC, which ``filterwarnings=error``
    promoted to unraisable exceptions that bit unrelated
    ``pytest.warns(ResourceWarning, ...)`` tests under 20-worker Windows
    xdist. In-memory backends (``memory`` / ``local`` / ``dafny``)
    legitimately inherit the no-op default ``close`` and need no teardown,
    so the guard is conditional on actually overriding the method —
    false-positiving them would force boilerplate.

    Scope is deliberately narrow:

    * Sync fixtures only. ``asyncio.run(f.aclose(instance))`` on Linux
      leaves the ``UnixSelectorEventLoop``'s self-pipe sockets unclosed
      long enough to fire ``PytestUnraisableExceptionWarning`` on a
      later test on the same xdist worker. The session-level
      ``_close_leaked_event_loops`` fixture in ``tests/conftest.py``
      only sweeps at session teardown. The mirror-side bug for async
      (``azure_replay_async`` forgetting ``aclose=``) would surface
      through the conformance suite the same way BUG-210 originally
      did.

    * Only fixtures whose ``factory()`` does not open a real network
      transport (``transport in {"fs", "memory", "sql"}``, or
      ``kind == "replay"`` which uses a fake connection string and lazy
      clients). Real-network fixtures (s3_moto, sftp_docker, azurite,
      live cloud) are covered by the conformance suite itself.
    """

    _SAFE_TRANSPORTS: frozenset[str] = frozenset({"fs", "memory", "sql"})

    def _is_safe_to_instantiate(self, f: BackendFixture) -> bool:
        """Whether ``f.factory()`` is guaranteed not to open a real network transport.

        ``replay`` fixtures use fake connection strings and lazy clients
        that never reach a real server; the remaining safe set is the
        non-network transports (fs / memory / sql).
        """
        return f.kind == "replay" or f.transport in self._SAFE_TRANSPORTS

    def test_sync_overriding_close_requires_cleanup(self) -> None:
        offenders: list[str] = []
        for f in all_fixtures():
            if f.is_async or not self._is_safe_to_instantiate(f):
                continue
            try:
                instance = f.factory()
            except pytest.skip.Exception:
                # Optional SDK not installed (e.g. azure-storage-file-datalake
                # absent on a minimal env). Skip silently — the invariant is
                # checked wherever the fixture actually constructs.
                continue
            try:
                if type(instance).close is not Backend.close and f.cleanup is None:
                    offenders.append(
                        f"{f.name!r}: {type(instance).__name__} overrides "
                        f"close() but the fixture has no cleanup= registered"
                    )
            finally:
                if f.cleanup is not None:
                    with contextlib.suppress(Exception):
                        f.cleanup(instance)
        assert not offenders, "BackendFixture missing teardown channel:\n  " + "\n  ".join(offenders)
