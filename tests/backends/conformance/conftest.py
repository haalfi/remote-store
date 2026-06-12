"""Conformance-only registry-driven parametrize (spec 048 / TEST-005).

This conftest is scoped to ``tests/backends/conformance/``. It hosts the
``backend`` and ``async_backend`` indirect fixtures and the
``pytest_generate_tests`` hook that auto-parametrises any conformance
test taking those arguments over ``fixture_params``.

The hook lives here, not in ``tests/backends/conftest.py``, because
per-backend tests under ``tests/backends/<backend>/`` use a ``backend``
parameter typed to their own concrete backend class for their own local
fixtures. A repository-wide auto-walk would multiply each per-backend
test by every registered backend.

Tests can still opt in to capability filtering at the class level::

    @pytest.mark.parametrize(
        "backend",
        fixture_params(Capability.WRITE),
        indirect=True,
    )

The hook detects an explicit ``parametrize`` and skips its own walk in
that case, so explicit markers and the auto-walk cohabit cleanly.

HTTP cassette / replay (TEST-007 / spec 049)
--------------------------------------------
This conftest also hosts the pytest-recording wiring that bridges each
``<backend>_live`` (record source) and ``<backend>_replay`` (playback
consumer) fixture pair. Everything routes through the fixture registry:
a fixture registered with a ``cassette_profile`` opts into all of it
(REC-007); there is no per-backend table here.

* ``pytest_configure`` — plugin guard: fails fast when pytest-recording is
  not installed so the ``record_mode`` fixture is never missing.
* ``vcr_cassette_dir`` — routes each cassette to its profile's per-backend
  directory (``tests/backends/cassettes/<backend>/``).
* ``default_cassette_name`` — normalises live/replay fixture ids to the
  profile's canonical suffix so both share one cassette file.
* ``vcr_config`` — the scrubbing layer, built from the node's profile.
* ``pytest_collection_modifyitems`` — missing-cassette → skip hook (TEST-007:
  if the cassette is absent, skip rather than raise).
* ``pytest_sessionfinish`` — dumps the scrub-fire manifest for the
  recorder's named-pattern audit (REC-006).
"""

from __future__ import annotations

import functools
import importlib.util
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.backends.fixtures import BackendFixture, all_fixtures, fixture_params
from tests.backends.fixtures._cassettes import CassetteProfile, build_profile_vcr_config, dump_scrub_manifest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from remote_store._backend import Backend

# Harmless fallback for the non-vcr nodes pytest-recording resolves
# ``vcr_cassette_dir`` for (the value is unused on those nodes).
_CASSETTES_ROOT: Path = Path(__file__).resolve().parent.parent / "cassettes"


_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cassette routing (TEST-007 / spec 049 REC-007)
# ---------------------------------------------------------------------------

# All cassette routing derives from the fixture registry: a fixture
# registered with ``cassette_profile=<PROFILE>`` opts into directory routing,
# name aliasing, the missing-cassette skip, and the scrub config in that one
# act. A node id carrying no profile-bearing fixture has no cassette.


@functools.cache
def _cassette_routing() -> dict[str, CassetteProfile]:
    """fixture id → cassette profile, from the registry.

    Cached on first use (collection time), after the ``tests.backends``
    conftest has imported every per-fixture module for side-effectful
    registration. Fails loud on a profile-bearing fixture missing from its
    profile's ``fixture_aliases`` — the one declaration the profile owner
    must extend per fixture.
    """
    routing: dict[str, CassetteProfile] = {}
    for fixture in all_fixtures():
        profile = fixture.cassette_profile
        if profile is None:
            continue
        if fixture.name not in profile.fixture_aliases:
            raise RuntimeError(
                f"fixture {fixture.name!r} carries the {profile.backend!r} cassette profile "
                "but has no fixture_aliases entry; add it to the profile declaration"
            )
        routing[fixture.name] = profile
    return routing


def _contains_fixture_token(name: str, fid: str) -> bool:
    """True when *fid* appears as a whole parametrize-bracket component.

    Bounded by ``[``, ``]``, or ``-`` so no partial-name collision can occur.
    """
    return f"[{fid}]" in name or f"[{fid}-" in name or f"-{fid}]" in name or f"-{fid}-" in name


def _profile_for_node_name(name: str) -> CassetteProfile | None:
    """Return the cassette profile for the fixture id in *name*, or ``None``."""
    for fid, profile in _cassette_routing().items():
        if _contains_fixture_token(name, fid):
            return profile
    return None


def _profile_for_vcr_node(node: Any) -> CassetteProfile | None:
    """Profile for *node*, failing loud when a vcr-marked node has none.

    pytest-recording resolves the cassette fixtures for every async
    conformance test, not only vcr-marked ones (a non-cassette param shares
    the parametrized class with the cassette params) — so a missing profile
    is an error only when the node actually carries ``pytest.mark.vcr``.
    """
    profile = _profile_for_node_name(node.name)
    if profile is None and node.get_closest_marker("vcr") is not None:
        raise RuntimeError(
            f"vcr-marked test {node.name!r} has no cassette profile; "
            "register its fixture with cassette_profile=<PROFILE> (REC-007)"
        )
    return profile


# Forbidden characters replaced by pytest-recording's get_default_cassette_name.
_FORBIDDEN_CASSETTE_CHARS = r"""<>?%*:|"'/\\"""


def _normalise_cassette_name(node_name: str, cls: type | None) -> str:
    """Return a cassette name with backend-fixture suffixes normalised.

    Applies the same class-prefix and forbidden-char replacement logic as
    ``pytest_recording.plugin.get_default_cassette_name`` so the skip hook
    and the ``default_cassette_name`` fixture compute the same path.

    Handles ids where the backend fixture appears at any position within the
    parametrize bracket group — first (``[azure_replay-write-no-overwrite]``),
    last (``[write-azure_replay]``), or sole (``[azure_replay]``).  Each
    fixture name is matched as a whole component bounded by ``[``, ``]``, or
    ``-`` so no partial-name collisions can occur.
    """
    name = node_name
    for fixture_name, profile in _cassette_routing().items():
        canonical = profile.fixture_aliases[fixture_name]
        name = name.replace(f"[{fixture_name}]", f"[{canonical}]")
        name = name.replace(f"[{fixture_name}-", f"[{canonical}-")
        name = name.replace(f"-{fixture_name}]", f"-{canonical}]")
        name = name.replace(f"-{fixture_name}-", f"-{canonical}-")
    cassette_name = f"{cls.__name__}.{name}" if cls is not None else name
    for ch in _FORBIDDEN_CASSETTE_CHARS:
        cassette_name = cassette_name.replace(ch, "-")
    return cassette_name


def _cassette_path_for_item(item: pytest.Item) -> None | Any:
    """Return the expected cassette ``Path`` for a vcr-marked conformance test.

    Returns ``None`` when the item's parametrize id carries no cassette-bearing
    fixture (and therefore has no cassette path to check). The directory is the
    fixture's per-backend cassette dir (``azure`` / ``graph``), per TEST-007.
    """
    profile = _profile_for_node_name(item.name)
    if profile is None:
        return None
    cls = getattr(item, "cls", None)
    cassette_name = _normalise_cassette_name(item.name, cls)
    return profile.cassette_dir / f"{cassette_name}.yaml"


# ---------------------------------------------------------------------------
# Plugin guard (TEST-007)
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast if pytest-recording is not installed.

    The ``record_mode`` fixture (session-scoped, provided by pytest-recording)
    is a dependency of both ``vcr_config`` and the ``vcr`` autouse fixture.
    A missing plugin would surface as an opaque ``fixture 'record_mode' not
    found`` deep in a session that otherwise looks healthy.  This guard
    converts that into a clear up-front message.
    """
    if importlib.util.find_spec("pytest_recording") is None:
        pytest.exit(
            "pytest-recording is required for HTTP cassette replay (TEST-007); "
            "run: uv pip install --python .venv pytest-recording",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# Cassette directory and name overrides (TEST-007 / plan challenges 1 & 2)
# ---------------------------------------------------------------------------


@pytest.fixture
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    """Override: route each cassette to its per-backend directory (TEST-007).

    Spec TEST-007 mandates ``tests/backends/cassettes/<backend>/`` for all
    HTTP replay cassettes.  The directory is selected from the test's
    parametrize id — ``cassettes/azure/`` for an azure fixture,
    ``cassettes/graph/`` for a graph fixture — so the corpus stays reviewable
    as a single per-backend PR diff (TEST-009).

    Function-scoped (not module-scoped) because one conformance module
    parametrises over both backend families; the cassette dir is per-test, not
    per-module.

    pytest-recording resolves this fixture for *every* async conformance test,
    not only vcr-marked ones (a non-cassette param like ``memory_async_native``
    shares the parametrized class with the cassette params). So a missing
    profile only fails loudly when the node actually carries
    ``pytest.mark.vcr`` — a genuinely-vcr-marked id with no registered
    profile. For non-vcr nodes the returned value is unused, so an arbitrary
    valid directory is harmless.
    """
    profile = _profile_for_vcr_node(request.node)
    if profile is not None:
        return str(profile.cassette_dir)
    return str(_CASSETTES_ROOT)  # unused: this node has no vcr marker


@pytest.fixture
def default_cassette_name(request: pytest.FixtureRequest) -> str:
    """Override: normalise backend-fixture suffixes so live and replay share a cassette.

    ``test_foo[azure_live]`` and ``test_foo[azure_replay]`` must read and write
    the same cassette file.  pytest-recording's default uses the raw node name,
    which would produce two different files.  This fixture applies the
    profiles' ``fixture_aliases`` to collapse them to a shared canonical
    suffix (``[azure]`` / ``[azure_async]``).
    """
    return _normalise_cassette_name(request.node.name, request.cls)


# ---------------------------------------------------------------------------
# Scrubbing layer — vcr_config fixture (TEST-007 / spec 049)
# ---------------------------------------------------------------------------


@pytest.fixture
def vcr_config(request: pytest.FixtureRequest, record_mode: str) -> dict[str, Any]:
    """Scrubbing layer for vcrpy: the node's profile builds its config.

    The profile is the single source of truth for what gets stripped out of
    its cassettes. Its ``EnvRedact`` resolvers run only in record mode and
    only for the test's own backend family, so neither family's live config
    is required to record the other's cassettes.

    As with ``vcr_cassette_dir``, pytest-recording resolves this for every
    async conformance test; an unregistered id only fails loudly when the
    node is actually ``pytest.mark.vcr``. For a non-vcr node the value is
    unused, so the empty dict is harmless.
    """
    profile = _profile_for_vcr_node(request.node)
    if profile is None:
        return {}
    live_values = profile.resolve_live_values() if record_mode != "none" else None
    return build_profile_vcr_config(profile, live_values)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Dump the per-rule scrub-fire manifest for the recorder's Step-4 audit.

    No-op unless ``record_cassettes.py`` exported ``_RS_SCRUB_MANIFEST``.
    """
    dump_scrub_manifest()


# ---------------------------------------------------------------------------
# Missing-cassette skip hook (TEST-007) + HNS known-failures xfail
# ---------------------------------------------------------------------------

# Test function names that expose a real-ADLS-Gen2 conformance gap not yet
# fixed in the backend.  Applied as xfail(strict=False) for real-Azure
# fixture IDs so CI does not treat them as unexpected failures; once the
# underlying bug is fixed and cassettes are re-recorded, the xpass signals
# the entry can be removed.  Currently empty: BUG-202 + BUG-203 fixes landed
# in PR #650; cassettes were refreshed (BK-224) so both names xpass and were
# removed from the roster.  Guard: ``test_xfail_guard.py`` asserts every
# entry matches a live test function.
_AZURE_HNS_KNOWN_FAILURE_FN_NAMES: frozenset[str] = frozenset()

# Fixture IDs that represent real ADLS Gen2 (live or replay) — not Azurite.
_AZURE_REAL_FIXTURE_IDS: frozenset[str] = frozenset(
    {
        "azure_live",
        "azure_live_async",
        "azure_replay",
        "azure_replay_async",
    }
)


def _has_real_azure_fixture(node_id: str) -> bool:
    """Return True if the node ID contains a real-Azure fixture ID as a whole token."""
    for fid in _AZURE_REAL_FIXTURE_IDS:
        if f"[{fid}]" in node_id or f"[{fid}-" in node_id or f"-{fid}]" in node_id or f"-{fid}-" in node_id:
            return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip vcr-marked conformance tests whose cassette is absent (TEST-007).

    Also marks known HNS-bug test functions as xfail for real-Azure fixture IDs
    so that CI does not treat them as unexpected failures.

    vcrpy's native behaviour in ``record_mode=none`` is to *raise* on an
    unmatched request.  The spec requires a *skip* instead.  This hook checks
    at collection time and adds ``pytest.mark.skip`` for any vcr-marked test
    whose cassette file does not exist yet.

    The xfail marks are applied in **all** modes, including ``--record``.
    During recording, xfail still lets the HTTP call complete (so the cassette
    is written) and then gracefully handles the subsequent assertion failure
    — without this, ``record_cassettes.py`` aborts at step 2 when the known-
    failing tests return non-zero.  Only the missing-cassette skip is gated on
    replay mode.
    """
    record_mode = config.getoption("--record-mode", default=None) or "none"

    # HNS known-failures: applied unconditionally (record + replay).
    for item in items:
        fn_name = getattr(item, "originalname", item.name.split("[")[0])
        if fn_name in _AZURE_HNS_KNOWN_FAILURE_FN_NAMES and _has_real_azure_fixture(item.nodeid):
            item.add_marker(
                pytest.mark.xfail(
                    strict=False,
                    reason="Known real-ADLS-Gen2 conformance gap (see _AZURE_HNS_KNOWN_FAILURE_FN_NAMES)",
                )
            )

    # Missing-cassette skip: only relevant during replay (cassette is being
    # written during recording, so its absence is expected).
    if record_mode != "none":
        return
    for item in items:
        if item.get_closest_marker("vcr") is None:
            continue
        cassette = _cassette_path_for_item(item)
        if cassette is None or cassette.exists():
            continue
        rel = os.path.relpath(cassette, config.rootpath)
        item.add_marker(
            pytest.mark.skip(reason=f"replay cassette missing ({rel}); record with pytest --stage=3 --record")
        )


# ---------------------------------------------------------------------------
# Conformance parametrize hooks
# ---------------------------------------------------------------------------


def _is_already_parametrized(metafunc: pytest.Metafunc, argname: str) -> bool:
    """Return True if ``argname`` is already parametrized via a marker."""
    for marker in metafunc.definition.iter_markers("parametrize"):
        if not marker.args:
            continue
        argnames = marker.args[0]
        names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)
        if argname in names:
            return True
    return False


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrise conformance tests requesting ``backend`` / ``async_backend``."""
    if "backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "backend"):
        metafunc.parametrize("backend", fixture_params(is_async=False), indirect=True)
    if "async_backend" in metafunc.fixturenames and not _is_already_parametrized(metafunc, "async_backend"):
        metafunc.parametrize("async_backend", fixture_params(is_async=True), indirect=True)


@pytest.fixture
def backend(request: pytest.FixtureRequest) -> Iterator[Backend]:
    """Indirect fixture: build a Backend from a ``BackendFixture`` record.

    Attaches the ``BackendFixture`` record onto the produced instance as
    ``_fixture_record`` so conformance helpers (``_skip_flat_namespace``,
    self-op skips) can consult per-fixture flags without re-deriving them
    from ``backend.name``. Reading the record is what closes BK-185 — the
    Azurite emulator and live ADLS Gen2 share ``backend.name == "azure"``
    but disagree on ``flat_namespace``.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    # Constraint: backend classes must not define ``__slots__`` (and must
    # not override ``__setattr__`` to reject unknown attributes). The
    # current backend set is plain dataclasses / classes with no slots,
    # so the assignment is safe; if a future backend adds slots, surface
    # the failure here rather than silently in a downstream
    # ``_fixture_record`` access.
    instance._fixture_record = fixture  # type: ignore[attr-defined]
    try:
        yield instance  # type: ignore[misc]
    finally:
        if fixture.cleanup is not None:
            fixture.cleanup(instance)


@pytest.fixture
async def async_backend(request: pytest.FixtureRequest) -> AsyncIterator[object]:
    """Indirect async fixture: build an AsyncBackend from a ``BackendFixture`` record.

    Sync ``cleanup`` and async ``aclose`` are both honoured. Async fixtures
    that own a real network pool (live cloud backends) set ``aclose`` so
    the connection pool is awaited before the next test starts. Sync
    teardown (e.g. tempdir removal) goes through ``cleanup`` as for sync
    fixtures. ``asyncio_mode = "auto"`` in ``pyproject.toml`` makes the
    ``async def`` fixture a first-class pytest-asyncio fixture without
    additional decorators.

    Both teardown channels are guarded so a transient failure in
    ``aclose`` (e.g. SDK pool-flush error) cannot strand the resource
    that ``cleanup`` is responsible for releasing — mirrors the same
    threat model that motivates the per-fixture ``_cleanup`` guards in
    ``azure_live`` / ``azurite``.
    """
    fixture: BackendFixture = request.param
    instance = fixture.factory()
    # Same ``__slots__`` constraint as the sync ``backend`` fixture above.
    instance._fixture_record = fixture  # type: ignore[attr-defined]
    try:
        yield instance
    finally:
        if fixture.aclose is not None:
            try:
                await fixture.aclose(instance)
            except Exception:  # noqa: BLE001 -- teardown is best-effort
                _LOG.warning("fixture.aclose() failed; continuing to cleanup", exc_info=True)
        if fixture.cleanup is not None:
            fixture.cleanup(instance)
