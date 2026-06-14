"""Fixture registry per spec 048 / TEST-004.

The registry is a flat list of ``BackendFixture`` records. Each record
names a fixture, ties it to a backend family, and declares the stage
tier, kind, capabilities, and async/sync mode the fixture operates in.

Conformance tests parametrise via ``fixtures``, which filters the
registry by stage (TEST-006), async mode, and capability set
(TEST-005). Backend-specific tests typically filter by a single
``backend == "<x>"`` predicate; do that with a list comprehension
over ``all_fixtures``. There is no per-backend helper because that
would invite re-implementing the filter in every site.

Per-backend factory modules append ``BackendFixture`` entries to
``_FIXTURES`` at import time. The conftest at ``tests.backends``
imports each module so that import-side effects run before any test
collection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import pytest

from remote_store._backend import Backend
from remote_store.aio import AsyncBackend
from tests.backends.fixtures._state import current_stage

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from remote_store._capabilities import Capability
    from tests.backends.fixtures._cassettes import CassetteProfile


AnyBackend = Backend | AsyncBackend
"""Type alias spanning sync ``Backend`` and ``AsyncBackend``.

The ``is_async`` flag on ``BackendFixture`` disambiguates the union
for parametrize callers; per-test indirect fixtures cast to the
concrete type they need.
"""


@dataclass(frozen=True)
class BackendFixture:
    """Single entry in the fixture registry.

    Per TEST-004 the shape is fixed: name, backend family, no-arg
    factory, stage, kind, capability set, async flag, optional
    cleanup. Records are frozen so a misbehaving test cannot mutate
    a registry entry shared across the session.

    The ``flat_namespace``, ``self_op_supported``, ``transport`` and
    ``container`` fields are populated from ``backends.toml`` /
    ``fixtures.toml`` via ``_loader.load_fixture``. They replace the
    ``_FLAT_NAMESPACE_BACKENDS`` / ``_NO_SELF_OP_BACKENDS`` identity
    sets that previously lived in conformance helpers and could not
    distinguish the Azurite emulator (flat) from real ADLS Gen2
    (HNS) — see BK-185.
    """

    name: str
    backend: str
    factory: Callable[[], AnyBackend]
    stage: int
    kind: Literal["pure", "mocked", "real-local", "real-live", "replay"]
    capabilities: frozenset[Capability]
    is_async: bool
    flat_namespace: bool = False
    """True when the backend has no real directory entries.

    Replaces the old ``_FLAT_NAMESPACE_BACKENDS`` identity set. Per-fixture
    so the Azurite emulator (flat) and live ADLS Gen2 (HNS) sharing the
    same backend family can disagree.
    """
    self_op_supported: bool = True
    """True when ``move(p, p)`` / ``copy(p, p)`` is a safe no-op.

    Replaces the old ``_NO_SELF_OP_BACKENDS`` identity set.
    """
    rejects_write_under_file_ancestor: bool = False
    """True when the fixture's backend rejects write-under-file-ancestor (ID-211).

    Hierarchical backends (Local, SFTP, Memory) always reject (set to True
    via the per-family default in ``backends.toml``).  Flat-NS backends
    (S3, Azure non-HNS, SQLBlob) only reject when the per-fixture
    ``reject_write_under_file_ancestor`` opt-in is wired into the factory.
    The conformance gate for the file-ancestor InvalidPath promise reads
    this flag instead of ``flat_namespace`` so the new strict fixture
    variants (e.g. ``s3_moto_strict``) run the gate while the default
    fixtures continue to skip it.
    """
    strict_only: bool = False
    """True when this fixture exists only to exercise a narrow contract.

    A ``strict_only`` fixture is excluded from the default
    ``fixture_params()`` enumeration, so it does NOT participate in the
    auto-parametrized conformance surface (atomic / io / listing /
    metadata / streaming / identity). Tests that genuinely need the
    strict variant opt in by passing ``include_strict_only=True`` to
    ``fixture_params()`` (or by adding an explicit parametrize).

    Set on the ID-211 ``*_strict`` fixtures so they exercise only the
    three file-ancestor tests (write / open_atomic / move+copy under
    file ancestor, plus the missing-src precondition-order test), not
    the full conformance suite. Without this guard a strict fixture
    would run the entire applicable surface twice on flat-NS backends.
    """
    large_write_distinct: bool = False
    """True when this fixture's backend takes a distinct code path for large
    or streamed writes (S3 multipart, Azure block staging, Graph
    ``createUploadSession``) AND runs against a real endpoint — emulator or
    live cloud — where that path is faithfully exercised.

    Gates the large/streamed WriteResult↔FileInfo consistency test (WR-001a):
    only fixtures with this flag run it, so the multipart / upload-session
    write path is checked for ``size``/``etag``/``digest`` agreement with a
    subsequent ``get_file_info()``. Per-fixture opt-in (no backend-family
    default, like ``strict_only``): deliberately ``False`` on the in-process
    moto mocks (multipart fidelity not trusted) and on ``graph_replay`` (a
    >4 MiB committed cassette is the cost GRAPH_PROFILE avoids — Graph's
    upload-session consistency is a live-lane concern).
    """
    transport: Literal["http", "ssh", "fs", "memory", "sql"] = "fs"
    """Transport family of the backend.

    Sourced from ``[backend.<x>].transport`` in ``backends.toml`` and copied
    onto every fixture of that family.
    """
    container: Literal["minio", "azurite", "sftp", "none"] = "none"
    """External container the fixture talks to, or ``"none"`` for in-process.

    Used by PR 2's mutate-scope generator to derive ``needs=[...]`` and
    by CI plumbing to decide which services to start.
    """
    cleanup: Callable[[AnyBackend], None] | None = None
    aclose: Callable[[AnyBackend], Awaitable[None]] | None = None
    """Awaitable teardown for async fixtures that own a real network pool.

    Set on async live fixtures so the conformance ``async_backend``
    indirect fixture can ``await`` it after a test. Sync fixtures and
    async fixtures whose teardown is purely synchronous (e.g.
    ``memory_async``) leave it as ``None``. Sync ``cleanup`` and async
    ``aclose`` are independent: a fixture may set both when it has both
    sync resources to release and an async pool to close.
    """
    marks: tuple[pytest.MarkDecorator, ...] = field(default_factory=tuple)
    """Pytest marks applied to this fixture's parametrize entry.

    Carries CI-runtime selectors that should ride along with the fixture
    name. For example, ``pytest.mark.os_sensitive`` on the ``local``
    fixture so that LocalBackend conformance is included in the
    macOS/Windows CI matrix that selects ``-m "os_sensitive"``.
    """
    cassette_profile: CassetteProfile | None = None
    """The cassette profile of this fixture's backend family, or ``None``.

    Set on HTTP record/replay fixtures only (spec 049, REC-007): carrying a
    profile is the single registration act that opts the fixture into
    cassette-directory routing, name aliasing, the missing-cassette skip,
    the scrub config, and the leak audit. Non-HTTP fixtures (and HTTP
    fixtures without a cassette tier, e.g. Azurite) leave it ``None`` and
    are invisible to cassette routing.
    """


_FIXTURES: list[BackendFixture] = []


def register(fixture: BackendFixture) -> None:
    """Append ``fixture`` to the registry. Called from per-backend modules.

    Duplicate names raise ``ValueError`` to surface accidental
    double-registration of the same fixture.
    """
    for existing in _FIXTURES:
        if existing.name == fixture.name:
            raise ValueError(f"duplicate fixture name: {fixture.name!r}")
    _FIXTURES.append(fixture)


def all_fixtures() -> list[BackendFixture]:
    """Return every registered fixture, unfiltered.

    Useful for tests that walk the full registry (e.g. layout
    invariant checks). Most call sites want ``fixtures`` instead.
    """
    return list(_FIXTURES)


def fixtures(*caps: Capability, is_async: bool = False, include_strict_only: bool = False) -> list[BackendFixture]:
    """Return registry entries matching ``caps`` for the active stage.

    Filters applied (in order):

    1. ``stage <= current_stage()`` for TEST-006 stage selection. Each
       stage includes all lower stages.
    2. ``is_async == is_async``: sync and async parametrize callers
       see disjoint subsets.
    3. ``caps <= fixture.capabilities`` for TEST-005 capability
       id-filtering. A fixture lacking any requested capability is
       absent from the returned list (no ``SKIPPED`` entry is emitted
       at runtime because the test was never parametrised over it).
    4. ``strict_only`` fixtures are excluded unless
       ``include_strict_only=True``. Strict variants exist to exercise
       narrow contracts (e.g. ID-211 file-ancestor), not the full
       conformance surface.

    Pass no ``caps`` to get every fixture in the requested mode and
    stage band.
    """
    stage_cap = current_stage()
    cap_set = frozenset(caps)
    return [
        f
        for f in _FIXTURES
        if f.stage <= stage_cap
        and f.is_async is is_async
        and cap_set.issubset(f.capabilities)
        and (include_strict_only or not f.strict_only)
    ]


def fixture_params(*caps: Capability, is_async: bool = False, include_strict_only: bool = False) -> list[Any]:
    """Wrap ``fixtures`` results as ``pytest.param`` entries.

    Each entry carries the fixture's ``name`` as the parametrize id and
    its ``marks`` (e.g. ``os_sensitive`` on local). Pass directly to
    ``@pytest.mark.parametrize("backend", fixture_params(Cap.X),
    indirect=True)``.

    ``include_strict_only`` opts the result into the strict-variant
    fixtures (see ``BackendFixture.strict_only``). Default-off so the
    default conformance surface stays narrow; tests that need the
    strict variants (e.g. the three ID-211 file-ancestor tests) pass
    ``include_strict_only=True`` explicitly.

    SFTP-Docker exclusion under xdist: the atmoz/sftp OpenSSH daemon is
    unreliable under concurrent connections from multiple xdist workers
    (banner drops, transient EOF). Rather than papering over this with
    MaxStartups tuning, banner pre-checks, and retry loops, we drop the
    ``sftp_docker`` fixture from parametrize entirely when running under
    an xdist worker. The CI workflow runs a second serial pytest
    invocation (``-k sftp_docker``) that picks them up.
    """
    is_xdist_worker = "PYTEST_XDIST_WORKER" in os.environ
    return [
        pytest.param(f, id=f.name, marks=list(f.marks))
        for f in fixtures(*caps, is_async=is_async, include_strict_only=include_strict_only)
        if not (is_xdist_worker and f.container == "sftp")
    ]


__all__ = [
    "AnyBackend",
    "BackendFixture",
    "all_fixtures",
    "fixture_params",
    "fixtures",
    "register",
]
