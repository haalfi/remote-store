"""What every operation does when the Azure *container* itself is gone.

BE-012 / BE-013 / BE-021 § Reach. A container that does not exist holds no path
either, so each operation answers as it would for a missing path: the two deletes
return silently under ``missing_ok=True`` and raise ``NotFound`` without it, the
probes answer ``False``, and the listings come back empty.

Sync half; the async adapter carries its own copy of every body and gets its own
file (TEST-003). Wire stubs live in ``.._helpers``, which is also why this runs
on a stub rather than the Docker-gated ``azurite`` fixture.

Both axes are asserted, not just tolerance. A backend that simply stopped
raising would pass the tolerant cells while turning a strict ``delete_folder``
into a no-op; the ``missing_ok=False`` cells forbid that, and the denied-listing
classes forbid the opposite overshoot — widening the catch past the container's
own 404.

**Coverage bound: the two deletes on HNS.** Their rule is argued from the code
(``ResourceNotFoundError`` → ``NotFound`` → the pre-existing ``missing_ok``
branch) rather than run. The HNS *listings* are executed — see
``TestTheHnsListingsAnswerTheSameWay``.
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
    HNS_MID_SCAN_BLIND_PAGES,
    KEY,
    MID_SCAN_BLIND_PAGES,
    connection_string,
    serve_absent_container,
    serve_container_vanishing_mid_listing,
    serve_denied,
    serve_hns_absent_filesystem,
    serve_hns_denied,
    serve_hns_filesystem_vanishing_mid_listing,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_httpserver import HTTPServer


def _backend_at(endpoint: str, *, hns: bool = False) -> Any:
    from remote_store.backends._azure import AzureBackend

    return AzureBackend(container=CONTAINER, hns=hns, connection_string=connection_string(endpoint))


@pytest.fixture
def backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) bound to a container that does not exist."""
    instance = _backend_at(serve_absent_container(httpserver))
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def denied_backend(httpserver: HTTPServer) -> Iterator[Any]:
    """An ``AzureBackend`` (non-HNS) whose every request is refused with a 403."""
    instance = _backend_at(serve_denied(httpserver))
    try:
        yield instance
    finally:
        instance.close()


class TestAbsentContainerReadsAsAbsentPath:
    """An absent container is an absent path, for both deletes."""

    @pytest.mark.spec("BE-012", "BE-021", "AZ-025")
    def test_delete_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete(KEY, missing_ok=True) is None

    @pytest.mark.spec("BE-013", "BE-021", "AZ-015")
    def test_delete_folder_tolerates_absent_container(self, backend: Any) -> None:
        assert backend.delete_folder(FOLDER, recursive=True, missing_ok=True) is None

    @pytest.mark.spec("BE-012", "BE-021", "AZ-025", "AZ-026")
    def test_delete_raises_not_found_when_strict(self, backend: Any) -> None:
        with pytest.raises(NotFound) as exc_info:
            backend.delete(KEY)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-013", "BE-021", "AZ-015", "AZ-026")
    def test_delete_folder_raises_not_found_when_strict(self, backend: Any) -> None:
        """The tolerance belongs to ``missing_ok``, not to the container 404."""
        with pytest.raises(NotFound) as exc_info:
            backend.delete_folder(FOLDER, recursive=True)
        assert exc_info.value.backend == "azure"


_PROBES = [
    ("exists-file", lambda b: b.exists(KEY)),
    ("exists-folder", lambda b: b.exists(FOLDER)),
    ("is_file", lambda b: b.is_file(KEY)),
    ("is_folder", lambda b: b.is_folder(FOLDER)),
]

_LISTINGS = [
    ("list_files", lambda b: list(b.list_files(""))),
    ("list_files-recursive", lambda b: list(b.list_files(FOLDER, recursive=True))),
    ("list_folders", lambda b: list(b.list_folders(""))),
    ("iter_children", lambda b: list(b.iter_children(""))),
    ("glob", lambda b: list(b.glob("**/*.txt"))),
]


class TestTheListingsComeBackEmpty:
    """An absent container holds nothing, so a listing is empty rather than an error.

    ``glob`` is included because it reaches the wire only through ``list_files``:
    pinning it stops a later change fixing the listing and leaving glob behind.
    """

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_absent_container_yields_nothing(
        self,
        backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert call(backend) == [], f"{op_name} must yield nothing against an absent container"

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_denied_listing_still_raises(
        self,
        denied_backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The narrowness guard: an empty listing must not be how a denial is reported."""
        with pytest.raises(PermissionDenied) as exc_info:
            call(denied_backend)
        assert exc_info.value.backend == "azure", op_name


class TestTheProbesAnswerFalse:
    """BE-004 and BE-005 forbid these from raising, and an absent container is no exception.

    ``is_file`` was already correct — its HEAD absorbs the 404 — and is
    parametrised in as the control that says what the other two owe.
    """

    @pytest.mark.spec("BE-004", "BE-005", "BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _PROBES, ids=[n for n, _ in _PROBES])
    def test_absent_container_answers_false(
        self,
        backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert call(backend) is False, f"{op_name} must answer False against an absent container"


class TestDeniedListingIsNotAnAbsentContainer:
    """The determinant's catch stays narrow: a 403 is not an answer about the folder.

    Widening the catch to every ``AzureError`` would report "nothing to delete"
    for a folder the caller merely cannot see. Driven through the tolerant
    ``delete_folder``, which is the form that would swallow the denial; the probe
    cells carry the same guard because they now read a 404 as an answer too.
    """

    @pytest.mark.spec("BE-013", "BE-021", "AZ-025", "AZ-026")
    def test_denied_listing_raises_permission_denied(self, denied_backend: Any) -> None:
        with pytest.raises(PermissionDenied) as exc_info:
            denied_backend.delete_folder(FOLDER, recursive=True, missing_ok=True)
        assert exc_info.value.backend == "azure"

    @pytest.mark.spec("BE-004", "BE-005", "BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _PROBES, ids=[n for n, _ in _PROBES])
    def test_denied_probe_raises_permission_denied(
        self,
        denied_backend: Any,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """ "You may not look" must not be reported as "there is nothing there"."""
        with pytest.raises(PermissionDenied) as exc_info:
            call(denied_backend)
        assert exc_info.value.backend == "azure", op_name


class TestTheToleranceIsBoundedToTheFirstPage:
    """ "An absent container holds nothing" is only sound while nothing was handed over.

    Both halves are pinned because a fix for either alone is wrong: unbounded, a
    mid-scan deletion is silent; bounded too tightly, an absent container raises
    where the contract wants an empty listing.
    """

    @pytest.mark.spec("BE-021", "AZ-026")
    def test_absent_from_the_start_still_yields_nothing(self, backend: Any) -> None:
        assert list(backend.list_files("", recursive=True)) == []

    @pytest.mark.spec("BE-021", "AZ-026")
    def test_a_container_deleted_mid_listing_raises(self, httpserver: HTTPServer) -> None:
        instance = _backend_at(serve_container_vanishing_mid_listing(httpserver))
        try:
            seen: list[Any] = []
            with pytest.raises(NotFound):
                # ``extend`` appends as it consumes, so the partial listing
                # survives the raise and the assertion below can check it.
                seen.extend(instance.list_files("", recursive=True))
            assert seen, "the stub must yield before the container vanishes, or this cell proves nothing"
        finally:
            instance.close()

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_every_listing_raises_on_its_own_blind_page_shape(
        self,
        httpserver: HTTPServer,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The bound must key on the page, not on what this operation made of it.

        Each listing meets the page shape that yields *it* nothing, covering both
        reasons a page can yield nothing: ``walk_blobs`` callers
        (``list_folders``, non-recursive ``list_files``) discard half of what
        comes back, while ``list_blobs`` callers (``list_files(recursive=True)``,
        ``glob``) never see a ``BlobPrefix`` at all, so the prefix page reaches
        them carrying no items. Keyed on a yielded item, every one of these
        swallowed the second page's 404.
        """
        endpoint = serve_container_vanishing_mid_listing(httpserver, page_one=MID_SCAN_BLIND_PAGES[op_name])
        instance = _backend_at(endpoint)
        try:
            with pytest.raises(NotFound):
                call(instance)
        finally:
            instance.close()


class TestTheHnsListingsAnswerTheSameWay:
    """The ADLS Gen2 branches, executed rather than argued.

    These carry their own copy of both rules because they never reach
    ``_listing_errors``: each catches its own exception so it can tell an absent
    container from a listing under a file ancestor (BE-014). A copy is a place
    the two namespaces can drift, so it needs its own cells — driven by a
    ``pytest-httpserver`` stub speaking ``List Path``, Stage 1, no Docker.
    """

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_absent_filesystem_yields_nothing(
        self,
        httpserver: HTTPServer,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        instance = _backend_at(serve_hns_absent_filesystem(httpserver), hns=True)
        try:
            assert call(instance) == [], f"{op_name} must yield nothing against an absent filesystem"
        finally:
            instance.close()

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_a_filesystem_deleted_mid_listing_raises(
        self,
        httpserver: HTTPServer,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The bound, on the branch that had it argued and unexecuted.

        Each listing meets the ``List Path`` page it makes nothing of:
        ``list_folders`` a page of one file, ``list_files`` and ``glob`` a page
        of one directory. Before the page-keyed bound these returned a truncated
        listing cleanly.
        """
        endpoint = serve_hns_filesystem_vanishing_mid_listing(httpserver, page_one=HNS_MID_SCAN_BLIND_PAGES[op_name])
        instance = _backend_at(endpoint, hns=True)
        try:
            with pytest.raises(NotFound):
                call(instance)
        finally:
            instance.close()

    @pytest.mark.spec("BE-021", "AZ-026")
    @pytest.mark.parametrize(("op_name", "call"), _LISTINGS, ids=[n for n, _ in _LISTINGS])
    def test_denied_listing_still_raises(
        self,
        httpserver: HTTPServer,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        """The narrowness guard: an empty listing must not be how a denial is reported."""
        instance = _backend_at(serve_hns_denied(httpserver), hns=True)
        try:
            with pytest.raises(PermissionDenied):
                call(instance)
        finally:
            instance.close()
