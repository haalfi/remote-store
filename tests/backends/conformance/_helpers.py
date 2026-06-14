"""Helpers shared across conformance topic files.

The capability-filter parametrise decorator is the primary gating
mechanism (TEST-005); a fixture lacking a required capability is absent
from the test session entirely. ``_require`` here is retained as a
defensive runtime gate for tests whose finer-grained capability needs
diverge from the class-level filter; it is a no-op whenever the
parametrise filter already excluded the fixture.

``_skip_flat_namespace`` and the self-op gate consult the per-fixture
``BackendFixture`` record attached by the indirect ``backend`` /
``async_backend`` fixtures, not the runtime ``backend.name``. That makes
the gate per-fixture, so the Azurite emulator (flat) and live ADLS Gen2
(HNS) sharing ``backend.name == "azure"`` decide independently
(closes BK-185).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from tests.backends.fixtures.registry import BackendFixture


def _depth(prefix: str, path: RemotePath) -> int:
    """Depth of ``path`` relative to listing root ``prefix``.

    Mirrors the spec 037 reference algorithm and the ``Depth`` ghost
    function in ``sdd/formal/BackendContract.dfy`` (the postcondition
    discharged at lines 705-709, proven by the four lemmas in
    ``sdd/formal/DepthCounting.dfy``):

        depth = len(parent.parts) - len(prefix_parts)

    where ``prefix in {"", "."}`` means root (0 parts) and a one-segment
    ``path`` (no parent) is depth 0 at root. Used by
    ``TestListFilesCompleteness`` to assert the DEPTH-003 boundary
    invariant directly, instead of only the resulting ``.name`` set.
    """
    base_parts = len(RemotePath(prefix).parts) if prefix and prefix != "." else 0
    parent = path.parent
    parent_parts = len(parent.parts) if parent is not None else 0
    return parent_parts - base_parts


def _fixture_record(backend: object) -> BackendFixture:
    """Return the ``BackendFixture`` record attached to ``backend``.

    The record is stamped on by the indirect ``backend`` / ``async_backend``
    fixtures in ``tests/backends/conformance/conftest.py``. Tests that
    bypass those fixtures (e.g. construct a backend directly) will hit
    the ``RuntimeError`` here — that path is never the conformance
    contract, so the failure is intentional and load-bearing.
    """
    rec = getattr(backend, "_fixture_record", None)
    if rec is None:
        raise RuntimeError(
            "backend instance lacks _fixture_record; conformance helpers "
            "require backends produced by the indirect fixture in conftest.py"
        )
    return rec


def _require(backend: object, *caps: Capability) -> None:
    """Skip the test if the backend lacks any of the given capabilities.

    Defensive runtime fallback. Tests should prefer the class-level
    capability filter via ``fixture_params(*caps)``; this helper only
    fires when a test inside a coarsely-filtered class needs a
    stricter capability than its siblings.
    """
    for cap in caps:
        if not backend.capabilities.supports(cap):  # type: ignore[attr-defined]
            pytest.skip(f"Backend does not support {cap.name}")


def _seed(backend: object, files: dict[str, bytes]) -> None:
    """Write multiple files into the backend."""
    for path, data in files.items():
        backend.write(path, data)  # type: ignore[attr-defined]


def _skip_flat_namespace(backend: object, reason: str = "flat-namespace backend") -> None:
    """Skip the test for backends without real directory entries.

    Per-fixture gate: reads ``flat_namespace`` from the attached
    ``BackendFixture`` record so fixtures of the same backend family
    can disagree (Azurite vs live HNS).
    """
    if _fixture_record(backend).flat_namespace:
        pytest.skip(reason)


def _skip_unless_rejects_file_ancestor(
    backend: object,
    reason: str = "fixture does not reject write-under-file-ancestor (ID-211 opt-in off)",
) -> None:
    """Skip when the fixture's backend does not enforce the file-ancestor gate.

    The ID-209 file-ancestor InvalidPath contract is mandatory on
    hierarchical backends and opt-in on flat-NS backends (see ID-211).
    Fixtures advertise the resolved behaviour via
    ``BackendFixture.rejects_write_under_file_ancestor``; tests gated on
    that promise use this helper instead of ``_skip_flat_namespace``.

    Replaces the older "skip everything flat-NS" stance: the new
    ``s3_moto_strict`` / ``azurite_strict`` / ``sqlblob_strict``
    fixtures advertise ``rejects = True`` and run the gate; the
    default-off fixtures continue to skip.
    """
    if not _fixture_record(backend).rejects_write_under_file_ancestor:
        pytest.skip(reason)


def _skip_unless_large_write_distinct(
    backend: object,
    reason: str = "fixture's backend has no distinct large/streamed write path (BK-286 opt-in off)",
) -> None:
    """Skip unless the fixture exercises a distinct large/streamed write path.

    Per-fixture gate (BK-286): reads ``large_write_distinct`` from the
    attached ``BackendFixture`` record. Set only on fixtures whose backend
    switches code path for large/streamed writes (S3 multipart, Azure block
    staging, Graph ``createUploadSession``) AND runs against a real
    emulator or live endpoint — so the large WriteResult↔FileInfo
    consistency test stays off on in-process mocks and cassette replay.
    """
    if not _fixture_record(backend).large_write_distinct:
        pytest.skip(reason)


def _do_op(backend: object, op: str, src: str, dst: str, **kw: Any) -> None:
    """Invoke ``backend.<op>(src, dst, **kw)``."""
    getattr(backend, op)(src, dst, **kw)


_MOVE_COPY_PARAMS = [
    pytest.param("move", Capability.MOVE, id="move"),
    pytest.param("copy", Capability.COPY, id="copy"),
]
