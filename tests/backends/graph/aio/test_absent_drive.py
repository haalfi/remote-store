"""What ``GraphBackend`` does when its drive is gone — BE-021 vs GR-031, adjudicated.

Graph's container is the drive, so BE-021's absent-container rule reaches this
backend: an absent container answers as absence, on every operation that clause
decides. GR-031 used to say the opposite for one of the two ``404`` shapes Graph
can answer with — a drive-identity ``resourceNotFound`` mapped to
``BackendUnavailable`` for *every* error-raising operation, at any URL scope.

`ADR-0038 <../../../../sdd/adrs/0038-absent-container-outranks-drive-identity.md>`_
adjudicated the collision: **BE-021 wins on every operation it decides; GR-031
keeps ``write``, and — off BE-021's roster entirely — ``check_health`` and
drive-id resolution.** This file's subject is the roster, so ``write`` is the
only one of the three it covers; the other two are pinned in ``test_ping.py`` and
``test_utils.py``. What the roster answers now, on both codes:

| Operation                                            | Answer                |
| ---------------------------------------------------- | --------------------- |
| ``delete``/``delete_folder`` (``missing_ok=True``)   | returns cleanly       |
| ``delete``/``delete_folder`` (``missing_ok=False``)  | ``NotFound``          |
| ``read``, ``read_bytes``, ``get_file_info``,         | ``NotFound``          |
| ``get_folder_info``, ``move``/``copy`` source        |                       |
| ``list_files``, ``list_folders``, ``iter_children``  | empty listing         |
| ``exists`` / ``is_file`` / ``is_folder``             | ``False``             |
| ``write``                                            | see below             |

``write`` is the exception, and it is not a divergence: BE-021 § Reach states in
so many words that ``write`` is the one roster operation no clause of it decides,
so GR-031 keeps it. A drive-identity ``resourceNotFound`` on a write raises
``BackendUnavailable``, which is what still surfaces a misconfigured drive as a
configuration error rather than as "your file isn't there". An ``itemNotFound``
write keeps ``NotFound``, unchanged.

**Both write paths are covered.** The small ``PUT /content`` write and the
large-file ``createUploadSession`` write classify their ``404`` at separate call
sites, so a cell for one says nothing about the other.

**Measured, not read.** The pre-adjudication divergence was recorded as reaching
the two tolerant deletes alone; running every operation against an absent drive
showed it reaching eleven. The parametrisation below is that measurement turned
into a fence — a future narrowing of the mapping shows up as a failing cell on
the operation it narrows, not just on the deletes.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
import respx

from remote_store._errors import BackendUnavailable, NotFound
from remote_store.aio.backends._graph import backend as graph_backend
from remote_store.aio.backends._graph.backend import GraphBackend

_DRIVE = "b!driveid123"
_BASE = "https://graph.microsoft.com/v1.0"
# Every drive-addressed URL: with the drive itself gone, no request against it
# can succeed, so a single catch-all route models the condition faithfully. It
# covers the createUploadSession POST too, which is why the large-write cells
# need no route of their own.
_ANY_DRIVE_URL = re.compile(re.escape(_BASE) + r"/drives/.*")

# Both 404 shapes Graph can answer with. `itemNotFound` is what live consumer
# OneDrive returns for a nonexistent drive on both URL forms (GR-031's
# verification note); `resourceNotFound` is the drive-identity code the
# adjudicated escalation is now confined to. Every cell runs on both, because
# the whole point of the adjudication is that the answer no longer depends on
# which one arrives — except on `write`.
_CODES = ["itemNotFound", "resourceNotFound"]

_FILE = "folder/object.txt"
_FOLDER = "folder"

_Call = Callable[[GraphBackend], Coroutine[Any, Any, object]]

_TOLERANT_DELETES: list[tuple[str, _Call]] = [
    ("delete", lambda b: b.delete(_FILE, missing_ok=True)),
    ("delete_folder", lambda b: b.delete_folder(_FOLDER, recursive=True, missing_ok=True)),
]

_NOT_FOUND_OPS: list[tuple[str, _Call]] = [
    ("delete", lambda b: b.delete(_FILE)),
    ("delete_folder", lambda b: b.delete_folder(_FOLDER, recursive=True)),
    ("read_bytes", lambda b: b.read_bytes(_FILE)),
    ("get_file_info", lambda b: b.get_file_info(_FILE)),
    ("get_folder_info", lambda b: b.get_folder_info(_FOLDER)),
    ("move", lambda b: b.move(_FILE, "folder/moved.txt")),
    ("copy", lambda b: b.copy(_FILE, "folder/copied.txt")),
]

_PROBES = ["exists", "is_file", "is_folder"]


def _absent_drive(code: str) -> GraphBackend:
    """A backend whose every drive request answers ``404 <code>``."""
    respx.route(url__regex=_ANY_DRIVE_URL).mock(
        return_value=httpx.Response(404, json={"error": {"code": code, "message": "The resource could not be found."}})
    )
    return GraphBackend(_DRIVE, token_provider=lambda: "tok")


@pytest.mark.spec("BE-012", "BE-013", "BE-021", "GR-031")
class TestTolerantDeletesReturnCleanly:
    """BE-021's headline clause: ``missing_ok=True`` tolerates an absent container."""

    @respx.mock
    @pytest.mark.parametrize("code", _CODES)
    @pytest.mark.parametrize(("op_name", "call"), _TOLERANT_DELETES, ids=[n for n, _ in _TOLERANT_DELETES])
    async def test_returns_none(self, op_name: str, call: _Call, code: str) -> None:
        backend = _absent_drive(code)
        assert await call(backend) is None, f"{op_name} must tolerate an absent drive under missing_ok ({code})"


@pytest.mark.spec("BE-006", "BE-007", "BE-012", "BE-013", "BE-016", "BE-017", "BE-018", "BE-019", "BE-021", "GR-031")
class TestErrorRaisingOperationsReportAbsence:
    """The canonical table's ``NotFound`` row, which BE-021 § Reach applies here.

    A container that is not there holds no path either, so every operation for
    which a missing path is an error answers ``NotFound`` — not
    ``BackendUnavailable``, which would make a caller's absent-store handling
    depend on which backend it is talking to.
    """

    @respx.mock
    @pytest.mark.parametrize("code", _CODES)
    @pytest.mark.parametrize(("op_name", "call"), _NOT_FOUND_OPS, ids=[n for n, _ in _NOT_FOUND_OPS])
    async def test_raises_not_found(self, op_name: str, call: _Call, code: str) -> None:
        backend = _absent_drive(code)
        with pytest.raises(NotFound) as exc_info:
            await call(backend)
        assert exc_info.value.backend == "graph", f"{op_name} must attribute the failure to the graph backend"

    @respx.mock
    @pytest.mark.parametrize("code", _CODES)
    async def test_read_raises_not_found(self, code: str) -> None:
        # `read` is an async generator, so the error surfaces on first iteration
        # rather than on the call: awaiting the coroutine would never run the body.
        backend = _absent_drive(code)
        with pytest.raises(NotFound):
            [chunk async for chunk in backend.read(_FILE)]


@pytest.mark.spec("BE-014", "BE-015", "BE-021", "GR-031")
class TestListingsAreEmpty:
    """An absent container holds nothing, so a listing is empty rather than an error."""

    @respx.mock
    @pytest.mark.parametrize("code", _CODES)
    @pytest.mark.parametrize("op_name", ["list_files", "list_folders", "iter_children"])
    async def test_yields_nothing(self, op_name: str, code: str) -> None:
        backend = _absent_drive(code)
        assert [entry async for entry in getattr(backend, op_name)(_FOLDER)] == [], (
            f"{op_name} must read an absent drive as no children ({code})"
        )


@pytest.mark.spec("BE-004", "BE-005", "GR-031")
class TestTheProbesNeverRaiseOnEitherCode:
    """The never-raise rule, which held on both codes before the adjudication too.

    GR-031's probe scope suppresses every ``404`` regardless of ``error.code``.
    That scope now coincides with the ordinary path scope, but it is kept as a
    distinct value because it pins BE-004 / BE-005 independently of what the rest
    of the mapping table does — these cells are what would catch a future
    re-narrowing that let an escalation reach a probe.
    """

    @respx.mock
    @pytest.mark.parametrize("code", _CODES)
    @pytest.mark.parametrize("probe", _PROBES)
    async def test_probe_answers_false(self, probe: str, code: str) -> None:
        backend = _absent_drive(code)
        assert await getattr(backend, probe)(_FILE) is False


@pytest.mark.spec("BE-021", "GR-031")
class TestWriteKeepsTheDriveIdentityEscalation:
    """The one operation BE-021 § Reach leaves undecided, so GR-031 keeps it.

    A write against a drive that is not there is the call most likely to be a
    misconfiguration rather than a missing file, and it is the one operation no
    clause of BE-021 decides — so ``resourceNotFound`` still escalates here.
    ``itemNotFound`` keeps ``NotFound``, which is what the live tier returns and
    what shipped before the adjudication.
    """

    @respx.mock
    async def test_small_write_escalates_resource_not_found(self) -> None:
        backend = _absent_drive("resourceNotFound")
        with pytest.raises(BackendUnavailable, match="Drive unavailable"):
            await backend.write(_FILE, b"payload")

    @respx.mock
    async def test_small_write_reports_item_not_found_as_absence(self) -> None:
        backend = _absent_drive("itemNotFound")
        with pytest.raises(NotFound):
            await backend.write(_FILE, b"payload")

    @respx.mock
    async def test_upload_session_write_escalates_resource_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The large-file path classifies its 404 at createUploadSession, a
        # different call site from the small PUT /content write above.
        monkeypatch.setattr(graph_backend, "_SMALL_FILE_MAX_SIZE", 4)
        backend = _absent_drive("resourceNotFound")
        with pytest.raises(BackendUnavailable, match="Drive unavailable"):
            await backend.write("big.bin", b"payload longer than the small-write threshold")

    @respx.mock
    async def test_upload_session_write_reports_item_not_found_as_absence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(graph_backend, "_SMALL_FILE_MAX_SIZE", 4)
        backend = _absent_drive("itemNotFound")
        with pytest.raises(NotFound):
            await backend.write("big.bin", b"payload longer than the small-write threshold")
