"""Async twin of the absent-container deviation suite.

BE-012 / BE-013, ASYNC-012 / ASYNC-013. ``AsyncAzureBackend`` carries its own
copy of the non-HNS ``delete_folder`` body rather than delegating to the sync
one, so the rule needs its own copy of the assertions — a sync-only suite would
have passed while the async twin still raised. It did, on the first run.

See the sync sibling (``../test_absent_container.py``) for the rule and why it
is decided this way round, and ``.._helpers`` for the wire stubs both use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

pytest.importorskip("azure.storage.blob", reason="azure-storage-blob not installed")
pytest.importorskip("pytest_httpserver", reason="pytest-httpserver not installed")
pytest.importorskip("werkzeug", reason="werkzeug not installed")

from remote_store._errors import NotFound, PermissionDenied  # noqa: E402
from tests.backends.azure._helpers import (  # noqa: E402
    CONTAINER,
    FOLDER,
    KEY,
    MID_SCAN_BLIND_PAGES,
    connection_string,
    serve_absent_container,
    serve_container_vanishing_mid_listing,
    serve_denied,
)

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer


def _backend_at(endpoint: str) -> Any:
    from remote_store.aio.backends._azure import AsyncAzureBackend

    return AsyncAzureBackend(container=CONTAINER, hns=False, connection_string=connection_string(endpoint))


@pytest.fixture
async def backend(httpserver: HTTPServer) -> Any:
    """An ``AsyncAzureBackend`` (non-HNS) bound to a container that does not exist."""
    instance = _backend_at(serve_absent_container(httpserver))
    try:
        yield instance
    finally:
        await instance.aclose()


@pytest.fixture
async def denied_backend(httpserver: HTTPServer) -> Any:
    """An ``AsyncAzureBackend`` (non-HNS) whose every request is refused with a 403."""
    instance = _backend_at(serve_denied(httpserver))
    try:
        yield instance
    finally:
        await instance.aclose()


class TestAbsentContainerReadsAsAbsentPath:
    """An absent container is an absent path, for both deletes."""

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-012", "AZ-025")
    async def test_delete_tolerates_absent_container(self, backend: Any) -> None:
        assert await backend.delete(KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013", "AZ-015")
    async def test_delete_folder_tolerates_absent_container(self, backend: Any) -> None:
        assert await backend.delete_folder(FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "ASYNC-012", "AZ-025", "AZ-026")
    async def test_delete_raises_not_found_when_strict(self, backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            await backend.delete(KEY)
        assert exc_info.value.backend == "async-azure"

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013", "AZ-015", "AZ-026")
    async def test_delete_folder_raises_not_found_when_strict(self, backend: Any) -> None:
        """The tolerance belongs to ``missing_ok``, not to the container 404."""
        with pytest.raises(NotFound) as exc_info:
            await backend.delete_folder(FOLDER, recursive=True)
        assert exc_info.value.backend == "async-azure"


_PROBES = [
    ("exists-file", lambda b: b.exists(KEY)),
    ("exists-folder", lambda b: b.exists(FOLDER)),
    ("is_file", lambda b: b.is_file(KEY)),
    ("is_folder", lambda b: b.is_folder(FOLDER)),
]

_LISTINGS = [
    ("list_files", lambda b: b.list_files("")),
    ("list_files-recursive", lambda b: b.list_files(FOLDER, recursive=True)),
    ("list_folders", lambda b: b.list_folders("")),
    ("iter_children", lambda b: b.iter_children("")),
    ("glob", lambda b: b.glob("**/*.txt")),
]


class TestTheListingsComeBackEmpty:
    """An absent container holds nothing, async half.

    Same reasoning as the sync sibling. ``AsyncAzureBackend`` carries its own copy
    of each listing body, so a sync-only suite proves nothing here.
    """

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    async def test_absent_container_yields_nothing(
        self,
        backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        got = [item async for item in call(backend)]
        assert got == [], f"{op_name} must yield nothing against an absent container"

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    async def test_denied_listing_still_raises(
        self,
        denied_backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The narrowness guard: an empty listing must not be how a denial is reported."""
        with pytest.raises(PermissionDenied) as exc_info:
            [item async for item in call(denied_backend)]
        assert exc_info.value.backend == "async-azure", op_name


class TestTheProbesAnswerFalse:
    """BE-004 / BE-005, async half.

    Same reasoning as the sync sibling, and the same reason for a separate file:
    ``AsyncAzureBackend`` carries its own copy of each probe body, so a sync-only
    suite proves nothing about this one.
    """

    @pytest.mark.spec("BE-004", "BE-005", "BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _PROBES, ids=[n for n, _ in _PROBES])
    async def test_absent_container_answers_false(
        self,
        backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert await call(backend) is False, f"{op_name} must answer False against an absent container"


class TestDeniedListingIsNotAnAbsentContainer:
    """The determinant's catch stays narrow: a 403 is not an answer about the folder.

    Async half of the control case. The async determinant has its own
    ``_achildren_or_absent_container`` re-raise branch, so this is the cell that
    executes it — without this test that branch is unreached code.
    """

    @pytest.mark.spec("BE-013", "BE-021", "ASYNC-013", "AZ-025", "AZ-026")
    async def test_denied_listing_raises_permission_denied(self, denied_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            await denied_backend.delete_folder(FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "async-azure"

    @pytest.mark.spec("BE-004", "BE-005", "BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _PROBES, ids=[n for n, _ in _PROBES])
    async def test_denied_probe_raises_permission_denied(
        self,
        denied_backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """ "You may not look" must not be reported as "there is nothing there"."""
        with pytest.raises(PermissionDenied) as exc_info:
            await call(denied_backend)
        assert exc_info.value.backend == "async-azure", op_name


class TestTheToleranceIsBoundedToTheFirstPage:
    """Async half of the first-page bound; this adapter carries its own listing bodies."""

    @pytest.mark.spec("BE-021", "AZ-026")
    async def test_absent_from_the_start_still_yields_nothing(self, backend: Any) -> None:
        assert [i async for i in backend.list_files("", recursive=True)] == []

    @pytest.mark.spec("BE-021", "AZ-026")
    async def test_a_container_deleted_mid_listing_raises(self, httpserver: HTTPServer) -> None:
        instance = _backend_at(serve_container_vanishing_mid_listing(httpserver))
        try:
            seen: list[Any] = []

            async def _drain() -> None:
                async for info in instance.list_files("", recursive=True):
                    seen.append(info)

            with pytest.raises(NotFound):
                await _drain()
            assert seen, "the stub must yield before the container vanishes, or this cell proves nothing"
        finally:
            await instance.aclose()

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    async def test_every_listing_raises_on_its_own_blind_page_shape(
        self,
        httpserver: HTTPServer,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The bound must key on the page, not on what this operation made of it.

        Same reasoning as the sync sibling, and the same reason for a separate
        file: this adapter carries its own copy of each listing body, and its own
        copy of the re-raise. Coverage said so — before this cell, five of the six
        ``raise`` statements the mid-scan bound added here never executed, because
        the only mid-scan cell drove ``list_files`` alone.
        """
        endpoint = serve_container_vanishing_mid_listing(httpserver, page_one=MID_SCAN_BLIND_PAGES[op_name])
        instance = _backend_at(endpoint)
        try:

            async def _drain() -> None:
                async for _ in call(instance):
                    pass

            with pytest.raises(NotFound):
                await _drain()
        finally:
            await instance.aclose()
