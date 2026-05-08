"""Fixture-registry runtime state.

This module holds two pieces of process-global state that the registry
consults at parametrize time:

* ``_CURRENT_STAGE``: the active ``--stage=N`` value, set once by
  ``pytest_configure`` in ``tests/conftest.py``. ``current_stage()``
  is read by ``tests.backends.fixtures.fixtures`` to filter the
  registry.

* ``INFRA``: a mutable dataclass holding session-scoped infrastructure
  endpoints (moto URL, Azurite connection string, SFTP ports, ...).
  Populated by the autouse ``_populate_infra`` session fixture in
  ``tests.backends.conftest``. Per-backend factory modules read
  ``INFRA`` at call time.

Both are module-level singletons. Pytest is single-process per worker;
``pytest-xdist`` is not currently used. If it ever is, both pieces of
state need to be lifted into a config plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.backends.fixtures._loader import VALID_STAGES

# ---------------------------------------------------------------------------
# Stage selection
# ---------------------------------------------------------------------------

_CURRENT_STAGE: int = 1


def current_stage() -> int:
    """Return the active stage tier (1, 2, or 3).

    Defaults to 1 until ``pytest_configure`` calls
    ``set_current_stage``. The default keeps ``fixtures()`` safe to
    call before pytest configuration has finished (e.g. from doctest
    runners or ad-hoc imports).
    """
    return _CURRENT_STAGE


def set_current_stage(stage: int) -> None:
    """Set the active stage tier. Called once by ``pytest_configure``.

    Valid stages come from ``_loader.VALID_STAGES``, the same set the
    ``--stage`` CLI option's ``choices`` reads.
    """
    global _CURRENT_STAGE
    if stage not in VALID_STAGES:
        raise ValueError(f"stage must be one of {sorted(VALID_STAGES)} (got {stage!r})")
    _CURRENT_STAGE = stage


# ---------------------------------------------------------------------------
# Session infrastructure
# ---------------------------------------------------------------------------


@dataclass
class InfraState:
    """Session-scoped service endpoints, populated once per pytest run.

    The fields default to ``None``; the autouse ``_populate_infra``
    session fixture in ``tests.backends.conftest`` writes the live
    values after the underlying service fixtures (``moto_server``,
    ``azurite_server``, ...) have started. Factories observe the
    populated fields when they are called from a test setup, never
    before.

    A factory whose required field is still ``None`` should call
    ``pytest.skip(...)`` rather than fail. This is the
    "explicit-stage-with-missing-infrastructure" path described in
    TEST-006: collection succeeds and the affected fixture skips
    visibly.
    """

    moto_url: str | None = None
    minio_url: str | None = None
    sftp_inproc_port: int | None = None
    sftp_inproc_host_key: str | None = None
    sftp_docker_port: int | None = None
    azurite_conn_str: str | None = None
    http_server: object | None = None

    extras: dict[str, object] = field(default_factory=dict)


INFRA = InfraState()
