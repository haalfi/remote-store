"""Session-scoped fixture that publishes infra endpoints into ``INFRA``.

The ``moto_server``, ``minio_server``, ``sftp_server``, ``azurite_server``
and ``http_server`` session fixtures are defined in :mod:`tests.conftest`
and :mod:`tests.backends.conftest`. They start (or detect) the
underlying services and yield URLs / ports / connection strings.

This module re-exposes those values via the ``INFRA`` dataclass so
factory modules in :mod:`tests.backends.fixtures` can read endpoints
without needing pytest's ``request`` machinery. Per TEST-004 the
factory signature is ``Callable[[], AnyBackend]`` (no-arg); reading
from ``INFRA`` is how we honour that.

The autouse fixture below runs at session scope. It depends on every
infrastructure session fixture so they are forced to start before any
test setup runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.backends.fixtures._state import INFRA

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session", autouse=True)
def _populate_infra(
    moto_server: str | None,
    minio_server: str | None,
    sftp_server: tuple[int, str] | None,
    azurite_server: str | None,
    http_server: object | None,
) -> Iterator[None]:
    """Copy session infrastructure endpoints into ``INFRA``.

    ``request.param``-less factories in :mod:`tests.backends.fixtures`
    read ``INFRA`` directly. The yields below leave the values populated
    for the entire session and reset them afterwards so a re-imported
    test session in the same process starts with a clean slate.
    """
    INFRA.moto_url = moto_server
    INFRA.minio_url = minio_server
    if sftp_server is not None:
        INFRA.sftp_inproc_port, INFRA.sftp_inproc_host_key = sftp_server
    INFRA.azurite_conn_str = azurite_server
    INFRA.http_server = http_server
    yield
    INFRA.moto_url = None
    INFRA.minio_url = None
    INFRA.sftp_inproc_port = None
    INFRA.sftp_inproc_host_key = None
    INFRA.sftp_docker_port = None
    INFRA.azurite_conn_str = None
    INFRA.http_server = None
