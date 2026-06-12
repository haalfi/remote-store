"""Tests for registry-driven cassette routing (spec 049, REC-007).

Registering a fixture with ``cassette_profile=<PROFILE>`` is the single act
that opts it into directory routing, cassette-name aliasing, the
missing-cassette skip, and the scrub config. These tests pin that contract
from both sides: the registry invariants every profile-bearing fixture must
satisfy, and the conformance conftest's fail-loud guards for fixtures that
break it.
"""

from __future__ import annotations

import types

import pytest

from tests.backends.conformance import conftest as routing
from tests.backends.fixtures import all_fixtures, registry
from tests.backends.fixtures._cassettes_azure import AZURE_PROFILE
from tests.backends.fixtures.registry import BackendFixture


@pytest.fixture
def fresh_routing_cache():
    """Clear the cached routing map around a test that fakes the registry."""
    routing._cassette_routing.cache_clear()
    yield
    routing._cassette_routing.cache_clear()


@pytest.mark.spec("REC-007")
class TestCassetteRouting:
    """One registration act: profile on the fixture, everything else derives."""

    def test_every_profile_bearing_fixture_has_an_alias(self) -> None:
        """The one declaration a profile owner must extend per fixture."""
        for fixture in all_fixtures():
            profile = fixture.cassette_profile
            if profile is None:
                continue
            assert fixture.name in profile.fixture_aliases, (
                f"fixture {fixture.name!r} carries the {profile.backend!r} profile "
                "but its fixture_aliases entry is missing"
            )

    def test_replay_fixtures_carry_a_profile(self) -> None:
        """A replay fixture without a profile would silently lose routing,
        scrubbing, and the missing-cassette skip."""
        for fixture in all_fixtures():
            if fixture.kind == "replay":
                assert fixture.cassette_profile is not None, fixture.name

    def test_live_fixtures_of_cassette_families_carry_a_profile(self) -> None:
        """The record-side twin of the replay guard — the higher blast
        radius: a live fixture that lost its profile would still record,
        just with no scrub config, silently writing live secrets into a
        fresh cassette. Scoped to families that have a cassette tier at all
        (``s3_live`` is HTTP + real-live but records no cassettes)."""
        cassette_families = {f.backend for f in all_fixtures() if f.cassette_profile is not None}
        assert cassette_families, "no cassette families registered"
        for fixture in all_fixtures():
            if fixture.backend in cassette_families and fixture.kind == "real-live" and fixture.transport == "http":
                assert fixture.cassette_profile is not None, fixture.name

    def test_non_http_fixtures_are_invisible_to_routing(self) -> None:
        """Fixtures without a profile (non-HTTP transports, emulator tiers)
        never appear in the routing map."""
        names_with_profile = {f.name for f in all_fixtures() if f.cassette_profile is not None}
        for fixture in all_fixtures():
            if fixture.transport != "http" or fixture.kind in ("pure", "mocked", "real-local"):
                assert fixture.name not in names_with_profile, (
                    f"{fixture.name!r} ({fixture.kind}, {fixture.transport}) should not carry a cassette profile"
                )

    def test_backend_family_shares_one_profile_object(self) -> None:
        """All fixtures of a family carry the same frozen profile by reference
        — one declaration, no per-fixture copies to drift."""
        by_backend: dict[str, set[int]] = {}
        for fixture in all_fixtures():
            if fixture.cassette_profile is not None:
                by_backend.setdefault(fixture.cassette_profile.backend, set()).add(id(fixture.cassette_profile))
        assert by_backend, "no profile-bearing fixtures registered"
        for backend, ids in by_backend.items():
            assert len(ids) == 1, f"{backend!r} fixtures carry {len(ids)} distinct profile objects"

    def test_missing_alias_fails_loud_at_routing_build(
        self, fresh_routing_cache: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fixture registered with a profile but absent from its
        ``fixture_aliases`` is a half-registration; the routing map refuses to
        build rather than silently mis-rout the cassette."""
        bogus = BackendFixture(
            name="bogus_replay",
            backend="azure",
            factory=lambda: None,  # type: ignore[arg-type,return-value]
            stage=1,
            kind="replay",
            capabilities=frozenset(),
            is_async=False,
            cassette_profile=AZURE_PROFILE,  # "bogus_replay" not in its aliases
        )
        monkeypatch.setattr(registry, "_FIXTURES", [bogus])
        with pytest.raises(RuntimeError, match="fixture_aliases"):
            routing._cassette_routing()

    def test_normalise_cassette_name_handles_every_token_position(self) -> None:
        """Live/replay ids collapse to the canonical suffix wherever the
        fixture token sits in the parametrize bracket — first, last, or sole —
        so both fixtures read and write one cassette file."""
        cases = {
            "test_foo[azure_replay]": "test_foo[azure]",
            "test_foo[azure_live]": "test_foo[azure]",
            "test_foo[azure_replay-write-no-overwrite]": "test_foo[azure-write-no-overwrite]",
            "test_foo[write-azure_replay_async]": "test_foo[write-azure_async]",
            "test_foo[a-graph_replay-b]": "test_foo[a-graph-b]",
            "test_foo[memory_async_native]": "test_foo[memory_async_native]",  # no cassette fixture: untouched
        }
        for node_name, expected in cases.items():
            assert routing._normalise_cassette_name(node_name, None) == expected

    def test_vcr_marked_node_without_profile_raises(self) -> None:
        """The fail-loud guard: a genuinely vcr-marked node whose fixture id
        has no profile is a registration bug, not a silent fallback."""
        node = types.SimpleNamespace(
            name="test_foo[unregistered_replay]",
            get_closest_marker=lambda name: object() if name == "vcr" else None,
        )
        with pytest.raises(RuntimeError, match="no cassette profile"):
            routing._profile_for_vcr_node(node)

    def test_non_vcr_node_without_profile_is_harmless(self) -> None:
        """pytest-recording resolves the cassette fixtures for non-vcr nodes
        too; those must pass through without a profile and without an error."""
        node = types.SimpleNamespace(
            name="test_foo[memory_async_native]",
            get_closest_marker=lambda name: None,
        )
        assert routing._profile_for_vcr_node(node) is None

    def test_profile_dir_routes_by_node_name(self) -> None:
        assert routing._profile_for_node_name("test_foo[azure_replay]") is AZURE_PROFILE
        graph = routing._profile_for_node_name("test_foo[graph_replay]")
        assert graph is not None
        assert graph.cassette_dir.name == "graph"
        assert routing._profile_for_node_name("test_foo[local]") is None
