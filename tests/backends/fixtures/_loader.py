"""Pure TOML loader for the fixture / backend registry (spec 048 / TEST-004).

Two TOML files in this package are the single source of truth for the
declarative facts that previously drifted across seven consumer sites:

* ``backends.toml`` — per-backend-family facts (sources, transport, and
  the per-family defaults for ``flat_namespace`` / ``self_op_supported``).
* ``fixtures.toml`` — per-fixture facts (backend, stage, kind, container,
  ``is_async``, optional live-cloud env vars, and per-fixture overrides
  for the two namespace/self-op flags).

The loader has no side effects beyond reading the two files at import
time of the calling module. Closed enums fail loudly with ``ValueError``
at parse time so a typo in TOML cannot silently propagate to a half-broken
fixture; the round-trip test in ``test_registry.py`` exercises the same
path on every run.

Typical use sites:

* ``tests/backends/fixtures/<name>.py`` calls ``load_fixture(name)`` and
  splats the resulting kwargs into its ``BackendFixture(...)`` literal.
* ``tests/backends/fixtures/__init__.py::_load_all`` walks
  ``load_fixtures()`` to import every per-fixture module by name.
* ``tests/conftest.py::pytest_addoption`` reads ``VALID_STAGES`` for the
  ``--stage`` option's ``choices``.

Per house style (``scripts/gen_features.py:20-23``) the ``tomllib``/``tomli``
import pattern follows the repo-wide convention so the loader runs on
Python 3.10 (via ``tomli``) and 3.11+ (stdlib ``tomllib``) alike.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import tomllib
except ImportError:  # pragma: no cover -- python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


_HERE = Path(__file__).resolve().parent
_BACKENDS_TOML = _HERE / "backends.toml"
_FIXTURES_TOML = _HERE / "fixtures.toml"


# ---------------------------------------------------------------------------
# Closed-enum validation sets (public — listed in ``__all__``)
# ---------------------------------------------------------------------------
#
# Single source of truth for every closed-enum dimension on a fixture or
# backend record. ``set_current_stage`` and the ``--stage`` option both
# read from ``VALID_STAGES``; the other three are consumed by the loader
# itself and the spec-marker round-trip tests. Public names so external
# callers (``_state.py``, ``tests/conftest.py``, ``test_registry.py``)
# do not reach into a "private" module surface.

VALID_STAGES: frozenset[int] = frozenset({1, 2, 3})
VALID_KINDS: frozenset[str] = frozenset({"pure", "mocked", "real-local", "real-live", "replay"})
VALID_TRANSPORTS: frozenset[str] = frozenset({"http", "ssh", "fs", "memory", "sql"})
VALID_CONTAINERS: frozenset[str] = frozenset({"minio", "azurite", "sftp", "none"})


Stage = Literal[1, 2, 3]
Kind = Literal["pure", "mocked", "real-local", "real-live", "replay"]
Transport = Literal["http", "ssh", "fs", "memory", "sql"]
Container = Literal["minio", "azurite", "sftp", "none"]


# ---------------------------------------------------------------------------
# Descriptor records (immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendDescriptor:
    """Per-backend-family facts loaded from ``backends.toml``.

    A fixture inherits ``flat_namespace`` / ``self_op_supported`` from
    its backend family unless its TOML block overrides them. Source-file
    lists feed PR 2's mutate-scope generator and a future static-analysis
    cross-check; PR 1 only consumes ``transport`` and the two boolean
    defaults.
    """

    name: str
    sources: tuple[str, ...]
    async_sources: tuple[str, ...]
    transport: Transport
    flat_namespace: bool
    self_op_supported: bool


@dataclass(frozen=True)
class FixtureDescriptor:
    """Per-fixture facts loaded from ``fixtures.toml``.

    Static fields only — the runtime callables (``factory``, ``cleanup``,
    ``aclose``, ``marks``) stay in the per-fixture Python module because
    they reference live objects (functions, ``pytest.mark`` decorators)
    that TOML cannot represent. The fixture module composes both halves
    when it calls ``register(BackendFixture(**desc.to_kwargs(), ...))``.
    """

    name: str
    backend: str
    stage: Stage
    kind: Kind
    container: Container
    is_async: bool
    flat_namespace: bool
    self_op_supported: bool
    transport: Transport
    live_opt_in_env: str | None = None
    live_creds_env: tuple[str, ...] = field(default_factory=tuple)

    def to_kwargs(self) -> dict[str, Any]:
        """Static-field kwargs for ``BackendFixture(...)``.

        Excludes the runtime callables and live-cloud env metadata; the
        per-fixture module passes ``factory``, ``cleanup``, ``aclose``,
        ``capabilities``, and ``marks`` separately. Live-cloud env names
        stay on the descriptor so future PR 2 work (mutate scopes, CI
        plumbing) can read them without round-tripping through pytest.
        """
        return {
            "name": self.name,
            "backend": self.backend,
            "stage": self.stage,
            "kind": self.kind,
            "container": self.container,
            "is_async": self.is_async,
            "flat_namespace": self.flat_namespace,
            "self_op_supported": self.self_op_supported,
            "transport": self.transport,
        }


# ---------------------------------------------------------------------------
# TOML parsing
# ---------------------------------------------------------------------------


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _require_str_list(value: Any, *, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where} must be a list of strings, got {value!r}")
    return tuple(value)


def _parse_backend(name: str, raw: dict[str, Any]) -> BackendDescriptor:
    transport = raw.get("transport")
    if transport not in VALID_TRANSPORTS:
        raise ValueError(f"backend.{name}: transport must be one of {sorted(VALID_TRANSPORTS)}, got {transport!r}")
    flat_ns = raw.get("flat_namespace", False)
    self_op = raw.get("self_op_supported", True)
    if not isinstance(flat_ns, bool):
        raise ValueError(f"backend.{name}: flat_namespace must be bool, got {flat_ns!r}")
    if not isinstance(self_op, bool):
        raise ValueError(f"backend.{name}: self_op_supported must be bool, got {self_op!r}")
    return BackendDescriptor(
        name=name,
        sources=_require_str_list(raw.get("sources", []), where=f"backend.{name}.sources"),
        async_sources=_require_str_list(raw.get("async_sources", []), where=f"backend.{name}.async_sources"),
        transport=transport,  # type: ignore[arg-type]
        flat_namespace=flat_ns,
        self_op_supported=self_op,
    )


def _parse_fixture(name: str, raw: dict[str, Any], backends: dict[str, BackendDescriptor]) -> FixtureDescriptor:
    backend_name = raw.get("backend")
    if not isinstance(backend_name, str):
        raise ValueError(f"fixture.{name}: backend must be a string, got {backend_name!r}")
    if backend_name not in backends:
        raise ValueError(
            f"fixture.{name}: backend {backend_name!r} not declared in backends.toml; "
            f"known backends: {sorted(backends)}"
        )
    backend = backends[backend_name]

    stage = raw.get("stage")
    if stage not in VALID_STAGES:
        raise ValueError(f"fixture.{name}: stage must be one of {sorted(VALID_STAGES)}, got {stage!r}")

    kind = raw.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"fixture.{name}: kind must be one of {sorted(VALID_KINDS)}, got {kind!r}")

    container = raw.get("container", "none")
    if container not in VALID_CONTAINERS:
        raise ValueError(f"fixture.{name}: container must be one of {sorted(VALID_CONTAINERS)}, got {container!r}")

    is_async = raw.get("is_async", False)
    if not isinstance(is_async, bool):
        raise ValueError(f"fixture.{name}: is_async must be bool, got {is_async!r}")

    # Per-fixture overrides merge on top of the backend-family defaults.
    flat_ns = raw.get("flat_namespace", backend.flat_namespace)
    self_op = raw.get("self_op_supported", backend.self_op_supported)
    if not isinstance(flat_ns, bool):
        raise ValueError(f"fixture.{name}: flat_namespace must be bool, got {flat_ns!r}")
    if not isinstance(self_op, bool):
        raise ValueError(f"fixture.{name}: self_op_supported must be bool, got {self_op!r}")

    live_opt_in_env = raw.get("live_opt_in_env")
    if live_opt_in_env is not None and not isinstance(live_opt_in_env, str):
        raise ValueError(f"fixture.{name}: live_opt_in_env must be a string, got {live_opt_in_env!r}")
    live_creds_env = _require_str_list(raw.get("live_creds_env", []), where=f"fixture.{name}.live_creds_env")

    return FixtureDescriptor(
        name=name,
        backend=backend_name,
        stage=stage,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        container=container,  # type: ignore[arg-type]
        is_async=is_async,
        flat_namespace=flat_ns,
        self_op_supported=self_op,
        transport=backend.transport,
        live_opt_in_env=live_opt_in_env,
        live_creds_env=live_creds_env,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@functools.cache
def load_backends() -> dict[str, BackendDescriptor]:
    """Parse ``backends.toml`` and return a name → descriptor map.

    The map preserves the TOML iteration order so downstream consumers
    that walk the registry deterministically (e.g. PR 2's mutate scopes)
    see a stable sequence.

    Cached: ``BackendDescriptor`` is frozen and the consumer set
    (per-fixture modules, ``test_registry.py``) treats the dict as
    read-only, so the result is safe to share across calls. Tests that
    swap the TOML at runtime should call ``load_backends.cache_clear()``.
    """
    raw = _read_toml(_BACKENDS_TOML)
    backends_raw = raw.get("backend", {})
    if not isinstance(backends_raw, dict):
        raise ValueError("backends.toml: top-level [backend] must be a table")
    return {name: _parse_backend(name, body) for name, body in backends_raw.items()}


@functools.cache
def load_fixtures() -> dict[str, FixtureDescriptor]:
    """Parse ``fixtures.toml`` and return a name → descriptor map.

    Cross-references every fixture's ``backend`` against
    ``load_backends()``; an unknown reference is a hard error so a
    fixture cannot silently float free of any family.

    Cached: at session startup every per-fixture module calls
    ``load_fixture`` (which delegates here), so without the cache both
    TOML files are parsed ~15 times. ``FixtureDescriptor`` is frozen and
    the consumer set treats the dict as read-only. Tests that swap the
    TOML at runtime should call ``load_fixtures.cache_clear()``.
    """
    backends = load_backends()
    raw = _read_toml(_FIXTURES_TOML)
    fixtures_raw = raw.get("fixture", {})
    if not isinstance(fixtures_raw, dict):
        raise ValueError("fixtures.toml: top-level [fixture] must be a table")
    return {name: _parse_fixture(name, body, backends) for name, body in fixtures_raw.items()}


def load_fixture(name: str) -> FixtureDescriptor:
    """Return the descriptor for a single named fixture.

    Convenience for per-fixture modules that only need their own block;
    delegates to the cached ``load_fixtures()`` so repeated calls do not
    re-parse the TOML files.
    """
    fixtures = load_fixtures()
    if name not in fixtures:
        raise KeyError(f"fixture {name!r} not declared in fixtures.toml; known fixtures: {sorted(fixtures)}")
    return fixtures[name]


__all__ = [
    "VALID_CONTAINERS",
    "VALID_KINDS",
    "VALID_STAGES",
    "VALID_TRANSPORTS",
    "BackendDescriptor",
    "Container",
    "FixtureDescriptor",
    "Kind",
    "Stage",
    "Transport",
    "load_backends",
    "load_fixture",
    "load_fixtures",
]
