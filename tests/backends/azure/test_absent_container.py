"""What every operation does when the Azure *container* itself is gone.

BE-012 / BE-013 / BE-021 § Reach. A container that does not exist holds no path
either, so each operation answers as it would for a missing path: the two deletes
return silently under ``missing_ok=True`` and raise ``NotFound`` without it, the
probes answer ``False``, and the listings come back empty.

The deletes came first and their history explains the shape of the rest. The pair
disagreed: ``delete_blob`` surfaces ``ContainerNotFound`` as a plain
``ResourceNotFoundError`` that the existing ``missing_ok`` branch already
swallowed, while ``delete_folder``'s prefix listing raised the same 404 out of
its determinant and past the tolerance check. The probes and the listings were
the same omission one method further out — and in the listings' case the HNS
branch already answered correctly while the flat branch beside it did not.

Sync half. The async twin carries its own copy of each of these bodies and so
gets its own file, ``aio/test_absent_container.py`` (TEST-003); the wire stubs
both use live in ``.._helpers``, which also explains why this runs on a stub
rather than the Docker-gated ``azurite`` fixture.

Both axes are asserted, not just tolerance: a backend that simply stopped
raising on the listing's 404 would pass the tolerant cells and silently turn a
strict ``delete_folder`` into a no-op. The ``missing_ok=False`` cells forbid
that, and ``TestDeniedListingIsNotAnAbsentContainer`` forbids the other
overshoot — widening the catch past the container's own 404.

**Coverage bound: the two deletes on HNS, and nothing else.** The listings'
HNS branches are executed here — see ``TestTheHnsListingsAnswerTheSameWay`` —
because ADLS Gen2's ``List Path`` is an ordinary JSON REST call and the same
stub technique reaches it. What is still argued rather than executed is the
*deletes* on HNS: that an absent container surfaces from ``delete_blob`` /
``get_directory_properties`` as ``ResourceNotFoundError`` → ``NotFound`` → the
pre-existing ``missing_ok`` branch, with none of this work's changes involved.

That bound used to cover the listings too, on the stated grounds that the HNS
branches were reachable only through the Docker-gated fixtures. It was false,
and it hid the one guard in this change that nothing ran. The lesson is the
repo's own and it has now cost this change twice: a reading of a body is not a
run of it, and "cannot be tested" is a claim that must itself be measured.
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

    The flat lane reached the caller with ``NotFound`` where the contract wants an
    empty listing, and the HNS branch of the *same* methods already returned early
    on a mapped ``NotFound`` — so the two namespaces answered the identical
    question differently inside one method body.

    ``glob`` is here because it reaches the wire only through ``list_files``: it
    inherits whatever that method does, and pinning it is what stops a later
    change fixing the listing while leaving the glob path behind.
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

    ``exists`` and ``is_folder`` reached the strict prefix listing once the
    tolerant blob HEAD came back empty, so a ``ContainerNotFound`` escaped as
    ``NotFound`` from two methods the contract says never raise it. ``is_file``
    is HEAD-only and already answered ``False``; it is parametrised in anyway, as
    the control that says what the other two owe.
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

    The control case for the tolerance above, and the failure mode worth
    guarding — widening the catch to every ``AzureError`` would make this pass
    silently as a clean return, reporting "nothing to delete" for a folder the
    caller merely cannot see. It goes through ``delete_folder``, whose
    determinant is the listing this rule touched, in its tolerant form: that is
    the one that would swallow the denial.

    The probe cells carry the same guard for the same reason: those probes now
    read the container's own 404 as an answer, and one narrowing away is reading
    every error as one.
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

    Once a listing has yielded, the container demonstrably existed, so a
    ``ContainerNotFound`` on a later page means it was deleted underneath the
    scan. Swallowing that returns a short listing that looks complete, and the
    caller most hurt is the one diffing a listing against local state and
    deleting the difference.

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

        The cell above pins ``list_files`` against a page carrying a blob — the
        one pairing where the page's contents survive to the caller. Every
        listing here meets the page shape that yields *it* nothing, and the two
        reasons a page can yield nothing are both represented:

        * ``list_folders`` and non-recursive ``list_files`` go through
          ``walk_blobs`` and **discard** half of what it returns — keys and
          prefixes respectively — so the blob page and the prefix page empty
          them by filtering.
        * ``list_files(recursive=True)`` and ``glob`` go through ``list_blobs``,
          which has no delimiter and parses only ``segment.blob_items``. A
          ``BlobPrefix`` is never surfaced to the backend at all, so the prefix
          page reaches them as a page carrying **no items**, which is the other
          residue the bound has to cover.

        Keyed on a yielded item rather than on the page, every one of these
        swallowed the second page's 404 and returned a short listing as a
        complete one.
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

    These branches carry their own copy of both rules — the empty listing and
    the first-page bound — because they never reach ``_listing_errors``: each
    catches its own exception so it can tell an absent container from a listing
    under a file ancestor (BE-014). A copy is a place the two namespaces can
    drift, and for the whole of this change the HNS copy was the one nothing
    ran, on the stated grounds that only Docker could reach it.

    It is reached here by a ``pytest-httpserver`` stub speaking ADLS Gen2's
    ``List Path``, the same way the flat lane is reached — Stage 1, in process,
    no Docker. Both axes and the narrowness control are asserted, because a
    branch that stopped raising altogether would pass the tolerance cells alone.
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
