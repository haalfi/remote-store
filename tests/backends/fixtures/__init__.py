"""Backend fixture registry.

Per spec 048 / TEST-004 the registry is the single source of truth for
which backends conformance and backend-specific tests parametrise over.

Public surface:

    from tests.backends.fixtures import BackendFixture, all_fixtures, fixtures

``all_fixtures()`` returns every registered fixture, regardless of stage
or capability gating. ``fixtures(*caps, is_async=...)`` returns the
subset whose ``stage <= current_stage()``, ``is_async`` matches the
requested mode, and whose capabilities cover ``caps``.

Fixture-side state (the active stage, session-scoped infra URLs) lives
in :mod:`tests.backends.fixtures._state`. Per-backend factory modules
(``memory``, ``local``, ``azurite``, ...) each register one or more
:class:`BackendFixture` records by appending to ``_FIXTURES`` in
:mod:`tests.backends.fixtures.registry`.
"""

from __future__ import annotations

from tests.backends.fixtures.registry import (
    AnyBackend,
    BackendFixture,
    all_fixtures,
    fixture_params,
    fixtures,
)


def _load_all() -> None:
    """Import every per-backend factory module to trigger registration.

    Each module appends to the registry at import time, so this is the
    single place that decides which backends are registered. The conftest
    at :mod:`tests.backends` calls this once at session start.
    """
    from tests.backends.fixtures import (  # noqa: F401 -- import-side-effect registration
        azurite,
        dafny_oracle,
        http,
        local,
        local_async,
        memory,
        memory_async,
        s3_moto,
        s3_pyarrow_minio,
        s3_pyarrow_moto,
        sftp_docker,
        sftp_inproc,
        sqlblob,
    )


__all__ = [
    "AnyBackend",
    "BackendFixture",
    "_load_all",
    "all_fixtures",
    "fixture_params",
    "fixtures",
]
