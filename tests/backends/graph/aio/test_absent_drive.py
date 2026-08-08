"""What ``GraphBackend`` does when its drive is gone — where two specs disagree.

Graph's container is the drive, so BE-021's absent-container rule reaches this
backend: both tolerant deletes MUST return cleanly when the container is not
there. GR-031 says the opposite for one of the two `404` shapes Graph can answer
with — a drive-identity `resourceNotFound` maps to ``BackendUnavailable`` for
every error-raising operation, deliberately, because a deleted drive is a backend
identity failure rather than a per-item condition. Both clauses are this
repository's own, both were written on purpose, and they give opposite answers to
the same call.

**Measured here, so the disagreement is a fact rather than a reading.**

| `error.code`       | tolerant deletes           | `exists` / `is_file` / `is_folder` |
| ------------------ | -------------------------- | ---------------------------------- |
| `itemNotFound`     | tolerated (BE-021 holds)   | `False`                            |
| `resourceNotFound` | raises `BackendUnavailable`| `False`                            |

The probe row is not a divergence from anything: GR-031's probe scope flattens
every `404` before the drive-identity escalation can fire, so BE-004 and BE-005
hold on both codes. Only the deletes split.

**Why no ``xfail``.** The Local sibling (`tests/backends/local/test_absent_root.py`)
marks its contract cells ``xfail(strict=True)`` because there the code is simply
wrong and a fix should break the marker. Here nothing is wrong yet — each side
matches its own spec — and marking either answer as the expected failure would
pre-decide an adjudication that has not happened. These cells pin what ships;
BUG-248 decides which clause survives, and whichever way it lands one of them
changes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable
from remote_store.aio.backends._graph.backend import GraphBackend

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"
# Every drive-addressed URL: with the drive itself gone, no request against it
# can succeed, so a single catch-all route models the condition faithfully.
_ANY_DRIVE_URL = re.compile(re.escape(_BASE) + r"/drives/.*")

_DELETES: list[tuple[str, Callable[[GraphBackend], Coroutine[Any, Any, None]]]] = [
    ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
    ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
]
_PROBES = ["exists", "is_file", "is_folder"]


def _absent_drive(code: str) -> GraphBackend:
    """A backend whose every drive request answers ``404 <code>``."""
    respx.route(url__regex=_ANY_DRIVE_URL).mock(
        return_value=httpx.Response(404, json={"error": {"code": code, "message": "The resource could not be found."}})
    )
    return GraphBackend(_DRIVE, token_provider=lambda: "tok")


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "GR-031")
class TestAnAbsentDriveReportedAsItemNotFound:
    """The shape live consumer OneDrive actually returns. BE-021 holds on it."""

    @respx.mock
    @pytest.mark.parametrize(("op_name", "call"), _DELETES, ids=[name for name, _ in _DELETES])
    async def test_tolerant_delete_returns_cleanly(
        self,
        op_name: str,
        call: Callable[[GraphBackend], Coroutine[Any, Any, None]],
    ) -> None:
        backend = _absent_drive("itemNotFound")
        assert await call(backend) is None, f"{op_name} must tolerate an absent drive under missing_ok"


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "GR-031")
class TestAnAbsentDriveReportedAsResourceNotFound:
    """The shape GR-031 escalates. BE-021 does not hold on it, by design."""

    @respx.mock
    @pytest.mark.parametrize(("op_name", "call"), _DELETES, ids=[name for name, _ in _DELETES])
    async def test_tolerant_delete_raises_backend_unavailable(
        self,
        op_name: str,
        call: Callable[[GraphBackend], Coroutine[Any, Any, None]],
    ) -> None:
        backend = _absent_drive("resourceNotFound")
        with pytest.raises(BackendUnavailable) as exc_info:
            await call(backend)
        assert exc_info.value.backend == "graph", f"{op_name} must attribute the failure to the graph backend"
        # The escalation is what makes this a divergence rather than a bug: the
        # message names the drive, not the path, so the error is legible even
        # while the two clauses disagree about whether it should be raised.
        assert "Drive unavailable" in str(exc_info.value)


@pytest.mark.spec("BE-004", "BE-005", "GR-031")
class TestTheProbesNeverRaiseOnEitherCode:
    """GR-031's probe scope keeps the never-raise rule intact through both shapes.

    This is the half of GR-031 that agrees with the contract: the type probes
    suppress every `404` regardless of ``error.code``, so the drive-identity
    escalation cannot reach a caller through them. Asserting it on both codes is
    what shows the suppression is scope-driven and not an accident of which code
    the stub happens to return.
    """

    @respx.mock
    @pytest.mark.parametrize("code", ["itemNotFound", "resourceNotFound"])
    @pytest.mark.parametrize("probe", _PROBES)
    async def test_probe_answers_false(self, probe: str, code: str) -> None:
        backend = _absent_drive(code)
        assert await getattr(backend, probe)("folder/object.txt") is False
