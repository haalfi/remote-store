"""Shared pytest wiring for HTTP cassette record/replay (TEST-007 / spec 049).

The generic, registry-driven half of the cassette machinery: cassette
directory routing, live/replay name aliasing, the scrub-config fixture, the
plugin guard, the missing-cassette skip, and the scrub-fire manifest dump.
None of it is conformance-specific — every routing decision derives from a
fixture's ``cassette_profile`` (REC-007) — so it is hosted here and imported by
both conftests that need it:

* ``tests/backends/conformance/conftest.py`` — the ``<backend>_live`` /
  ``<backend>_replay`` conformance pairs.
* ``tests/backends/azure/conftest.py`` — the ``azure_live_hns`` /
  ``azure_replay_hns`` deviation pair (BK-303), a sibling subtree that does not
  inherit the conformance conftest.

The conformance conftest keeps what *is* conformance-specific: the
``pytest_generate_tests`` auto-walk, the ``backend`` / ``async_backend``
indirect fixtures, and the real-Azure xfail roster.

Usage in a conftest::

    from tests.backends.fixtures._cassette_pytest import (
        apply_missing_cassette_skips,
        cassette_plugin_guard,
        default_cassette_name,  # noqa: F401 — re-exported as a pytest fixture
        dump_scrub_manifest,
        vcr_cassette_dir,       # noqa: F401 — re-exported as a pytest fixture
        vcr_config,             # noqa: F401 — re-exported as a pytest fixture
    )

    def pytest_configure(config):
        cassette_plugin_guard(config)

    def pytest_collection_modifyitems(config, items):
        apply_missing_cassette_skips(config, items)

    def pytest_sessionfinish(session, exitstatus):
        dump_scrub_manifest()

Importing the three fixture functions into a conftest namespace is what makes
pytest resolve them; the ``noqa: F401`` is load-bearing.
"""

from __future__ import annotations

import functools
import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest

from tests.backends.fixtures import all_fixtures
from tests.backends.fixtures._cassettes import CassetteProfile, build_profile_vcr_config, dump_scrub_manifest

__all__ = [
    "apply_missing_cassette_skips",
    "cassette_plugin_guard",
    "default_cassette_name",
    "dump_scrub_manifest",
    "vcr_cassette_dir",
    "vcr_config",
]

# Harmless fallback for the non-vcr nodes pytest-recording resolves
# ``vcr_cassette_dir`` for (the value is unused on those nodes). ``__file__``
# is ``tests/backends/fixtures/_cassette_pytest.py``; ``parent.parent`` is
# ``tests/backends``.
_CASSETTES_ROOT: Path = Path(__file__).resolve().parent.parent / "cassettes"


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
    """Return the expected cassette ``Path`` for a vcr-marked test.

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


def cassette_plugin_guard(config: pytest.Config) -> None:
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


# ---------------------------------------------------------------------------
# Missing-cassette skip (TEST-007)
# ---------------------------------------------------------------------------


def apply_missing_cassette_skips(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip vcr-marked tests whose cassette is absent (TEST-007).

    vcrpy's native behaviour in ``record_mode=none`` is to *raise* on an
    unmatched request.  The spec requires a *skip* instead.  This checks at
    collection time and adds ``pytest.mark.skip`` for any vcr-marked test whose
    cassette file does not exist yet.

    Only relevant during replay: in record mode the cassette is being written,
    so its absence is expected. Idempotent — safe to call from more than one
    conftest's ``pytest_collection_modifyitems`` over the same item list.
    """
    record_mode = config.getoption("--record-mode", default=None) or "none"
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
