"""Property-based tests for ``WriteResult`` size invariants (ID-151c).

Companion to ``tests/backends/conformance/test_atomic.py::TestWriteResultConformance``,
which exercises fixed-example WR-001a / WR-003 / WR-004 / WR-005 / WR-012 /
WR-013 across the full conformance fixture matrix.  This module adds property
coverage that enumerated inputs cannot: random payloads across the size
regimes that historically broke things (BUG-168 — Python 3.14 raised the
default ``BufferedWriter`` block size to roughly 128 KiB, so a 256 KiB – 1 MiB
streaming payload bypasses the flush that ``getsize``/``stat`` expects).

Backend selection is deliberately narrow, per TESTING.md Rules 5 and 6:

* ``MemoryBackend`` as a fast oracle; ``LocalBackend`` for the BUG-168
  boundary — it is the only v1 backend whose write path flows through a
  real ``BufferedWriter``.

Both backends are allowed at ``tests/`` root (TEST-003 / Rule B permits
``_memory`` and ``_local``), so this file stays at root.

Metadata round-trip PBT (WR-012 / WR-013) was split per-backend in BK-221:
``tests/backends/s3/test_write_result_pbt.py`` (moto) and
``tests/backends/azure/test_write_result_pbt.py`` (Azurite).

Hypothesis profiles are loaded from ``tests/conftest.py``
(``dev=50`` / ``ci=100`` / ``nightly=1000``); no inline ``max_examples`` is
set (TESTING.md Rule 10).  Payload strategies are module-level constants
(TESTING.md Rule 11).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from remote_store._models import WriteResult
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

if TYPE_CHECKING:
    from remote_store._backend import Backend


# ---------------------------------------------------------------------------
# Payload strategies (TESTING.md Rule 11 — module scope)
# ---------------------------------------------------------------------------

# Small regime: 0 B through 4 KiB-1.  Random content stays cheap.
_SMALL_MAX = 4 * 1024 - 1
_small_payload = st.binary(min_size=0, max_size=_SMALL_MAX)

# BUG-168 regime: 256 KiB through 1 MiB.  The Python 3.14 default
# BufferedWriter block size (~128 KiB) is large enough to hold anything
# below 256 KiB unflushed — so a pre-close ``os.path.getsize`` observed 0 on
# LocalBackend.write_atomic before the fix.  Content is deterministic per
# example (``fill * size``) so Hypothesis examples stay cheap and shrink
# cleanly without allocating random 1 MiB blobs.
_BUG168_MIN = 256 * 1024
_BUG168_MAX = 1024 * 1024

_write_op = st.sampled_from(["write", "write_atomic"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _example_path(prefix: str, *parts: object) -> str:
    """Stable filename derived from example inputs (reproducible under shrink)."""
    suffix = "-".join(str(p) for p in parts) or "root"
    return f"{prefix}/{suffix}.bin"


def _do_write(
    backend: Backend,
    path: str,
    content: bytes | io.BytesIO,
    *,
    overwrite: bool,
    op: str,
) -> WriteResult:
    """Dispatch ``write`` / ``write_atomic`` with hygienic pre-state."""
    backend.delete(path, missing_ok=True)
    if overwrite:
        backend.write(path, b"seed", overwrite=False)
    return getattr(backend, op)(path, content, overwrite=overwrite)


# ---------------------------------------------------------------------------
# PBT 1 — WriteResult.size == len(payload)
# ---------------------------------------------------------------------------


class TestWriteResultSizeSmall:
    """WR-001a / WR-003: ``size`` matches payload length across the small regime."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @given(
        payload=_small_payload,
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_memory(self, payload: bytes, overwrite: bool, as_stream: bool, op: str) -> None:
        backend = MemoryBackend()
        path = _example_path("pbt", "mem", len(payload), int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == len(payload)

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @pytest.mark.os_sensitive
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        payload=_small_payload,
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_local(
        self,
        tmp_path: object,
        payload: bytes,
        overwrite: bool,
        as_stream: bool,
        op: str,
    ) -> None:
        backend = LocalBackend(root=str(tmp_path))
        path = _example_path("pbt", "local-s", len(payload), int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == len(payload)


class TestWriteResultSizeBug168Regime:
    """WR-001a / WR-003 at the 256 KiB – 1 MiB buffer boundary (BUG-168 net)."""

    @pytest.mark.pbt
    @pytest.mark.spec("WR-001a")
    @pytest.mark.spec("WR-003")
    @pytest.mark.os_sensitive
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
        deadline=None,
    )
    @given(
        size=st.integers(min_value=_BUG168_MIN, max_value=_BUG168_MAX),
        fill=st.integers(min_value=0, max_value=255),
        overwrite=st.booleans(),
        as_stream=st.booleans(),
        op=_write_op,
    )
    def test_local_buffer_boundary(
        self,
        tmp_path: object,
        size: int,
        fill: int,
        overwrite: bool,
        as_stream: bool,
        op: str,
    ) -> None:
        """BUG-168 regression net.

        Only ``LocalBackend`` exercises a real ``BufferedWriter``; this is the
        regime where a pre-close ``os.path.getsize`` returned ``0`` on
        Python 3.14 (default buffer ~128 KiB, payload ≥ 256 KiB — everything
        stays buffered until ``with`` exit).  Content is deterministic per
        example (``bytes([fill]) * size``) to keep Hypothesis memory flat.
        """
        backend = LocalBackend(root=str(tmp_path))
        payload = bytes([fill]) * size
        path = _example_path("pbt", "local-b", size, fill, int(overwrite), int(as_stream), op)
        content: bytes | io.BytesIO = io.BytesIO(payload) if as_stream else payload
        result = _do_write(backend, path, content, overwrite=overwrite, op=op)
        assert isinstance(result, WriteResult)
        assert result.size == size
