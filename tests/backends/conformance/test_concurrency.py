"""Posture-gated concurrency conformance lane — sync (BK-289).

This is the single cross-backend home for concurrency conformance. It does
**not** assert one uniform "every backend is thread-safe" property — that claim
is false for SFTP and HTTP. Instead it follows the same gating discipline the
``Capability`` system uses everywhere else: each fixture declares a
``concurrency`` posture (``thread_safe`` / ``single_connection``, sourced from
``backends.toml`` like ``transport``), and the lane tests each backend against
*its own* declaration. ``fixture_params_concurrent(posture=...)`` is the selector.

**Every assertion here is an invariant** — no error, correct final state, no
lost writes on distinct keys. There is no assertion about interleaving,
ordering, or timing, and no ``sleep``-based synchronisation. Concurrency tests
are the historical #1 source of CI flake and this repo has paid for that lesson
(CLAUDE.md *Parallel tests*); the lane is deterministic by construction.

Tiers
-----
* **Tier 1 (Stage 1, CI):** in-process ``ThreadPoolExecutor`` stress over the
  ``thread_safe`` set — concurrent reads, distinct-key writes, read-after-write.
  At Stage 1 this is Memory + Local; at Stage 2 it pulls in the in-process
  S3/Azure emulators; at Stage 3 the live fixtures' params carry
  ``pytest.mark.live`` (excluded by the default ``-m 'not live'``), so the same
  invariant tests double as the **Tier 3** live concurrent-op probes when run
  with ``--stage=3 -m live``.
* **Tier 2 (Stage 1, CI):** the ``single_connection`` carve-out — assert the
  *documented* posture (one instance per thread works) and deliberately do
  **not** thread-stress a shared instance (that races the paramiko socket — the
  exact reason ``live_adapted_backend_concurrent`` excludes SFTP).
* **Tier 3 (Stage 2/3):** ``test_concurrent_large_streamed_uploads`` runs the
  N-parallel large-upload probe only where a real staged/multipart write path
  exists (``large_write_distinct``). Graph-specific Tier-3 probes
  (create-once-race, token-call counting) live in
  ``tests/backends/graph/aio/test_concurrency.py`` because they construct a
  concrete backend with mocked transport (TEST-010 keeps concrete backend
  classes out of this subtree).

Consolidation (research §4.4 — reuse, don't duplicate)
------------------------------------------------------
This lane generalises the share-across-threads property that was previously
asserted on Memory only:

* STORE-007 — ``test_store.py::TestStoreThreadSafety`` (Store-layer immutability
  note retained there); generalised here over the ``thread_safe`` set.
* CHILD-010 — ``test_store_child.py::TestChildThreadSafety`` inherits STORE-007.
* ASYNC-055 — ``memory/aio/.../TestAsyncMemoryConcurrency`` is generalised in
  the ``aio/`` sibling of this file.
* The ``test_sync_adapter_conformance.py`` SFTP carve-out is the precedent for
  Tier 2; its ``single_connection`` exclusion is now registry-driven.

Spec binding
------------
The backend-level posture clause is **BK-287**: ``BE-028`` (sync, spec 003),
``ASYNC-094`` (async, spec 029), and the per-backend clauses ``S3-028`` /
``AZ-037`` / ``SFTP-029``. The lane carries those marks plus STORE-007 (the
Store-layer share-across-threads property it generalises). The registry
``concurrency`` field is the machine-readable shadow of that taxonomy.
"""

from __future__ import annotations

import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability
from tests.backends.conformance._helpers import (
    _fixture_record,
    _require,
    _skip_unless_large_write_distinct,
)
from tests.backends.fixtures import fixture_params_concurrent

if TYPE_CHECKING:
    from collections.abc import Callable

    from remote_store._backend import Backend

# Fixed, modest fan-out so that under ``pytest -n auto`` the product
# ``xdist_workers × threads`` does not saturate the host (research §4.3).
_WORKERS = 8
_N_ITEMS = 16
# Single-connection carve-out opens one fresh transport per thread; keep the
# count gentle on the in-process SSH server.
_SC_WORKERS = 4
# Parallel large-upload probe: few but large, so total bytes stay modest on a
# live account (4 × 8 MiB = 32 MiB) while still tripping the staged/multipart path.
_LARGE_N = 4
_LARGE_SIZE = 8 * 1024 * 1024


def _run_concurrently(
    fn: Callable[[int, Any], Any],
    items: list[Any],
    *,
    workers: int,
) -> tuple[dict[int, Any], list[BaseException]]:
    """Run ``fn(idx, item)`` for each item on a thread pool; collect outcomes.

    Returns ``(results_by_index, errors)``. Exceptions are captured rather than
    re-raised so the caller asserts the *invariant* (``errors == []``) directly
    and reports the offending exceptions, instead of the pool surfacing only the
    first failure. No ordering or timing is asserted anywhere.
    """
    results: dict[int, Any] = {}
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, idx, item): idx for idx, item in enumerate(items)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except BaseException as exc:  # noqa: BLE001 -- invariant captures every failure mode
                errors.append(exc)
    return results, errors


def _xfail_local_dir_race_on_windows(backend: Backend, request: pytest.FixtureRequest) -> None:
    """xfail the ``local`` write-stress on Windows for BUG-220.

    ``LocalBackend._resolve`` canonicalises with ``Path.resolve()``; on Windows
    a directory a sibling thread is concurrently creating transiently
    canonicalises outside the init-time root, so a legitimate concurrent write
    to a nested key raises a spurious ``InvalidPath`` (reproduced 20/20). The
    posture itself is sound — concurrent *reads* and pre-created-dir writes pass
    — so the mark is ``strict=False`` and Windows-only: when BUG-220 is fixed the
    xpass on Windows prompts its removal, and POSIX runs the test for real.
    """
    if sys.platform == "win32" and _fixture_record(backend).name == "local":
        # No ``raises=``: the spurious InvalidPath is captured by
        # ``_run_concurrently`` and surfaces as the ``assert not errors``
        # AssertionError, so the xfail keys on failure alone (strict=False).
        request.applymarker(
            pytest.mark.xfail(
                reason="BUG-220: LocalBackend._resolve races on concurrent intermediate-dir creation (Windows)",
                strict=False,
            )
        )


@pytest.mark.concurrency
@pytest.mark.spec("BE-028")
@pytest.mark.spec("S3-028")
@pytest.mark.spec("AZ-037")
@pytest.mark.parametrize(
    "backend",
    fixture_params_concurrent(Capability.WRITE, posture="thread_safe"),
    indirect=True,
)
class TestThreadSafeConcurrency:
    """Tier 1 — concurrent threads on ONE shared instance are safe (BE-028 thread_safe).

    Runs only on fixtures that declare ``concurrency = "thread_safe"``, asserting
    BE-028's per-instance thread-safety: a shared instance under concurrent load
    produces no error and a correct final state, and concurrent writes to
    *distinct* keys never lose a write. The cross-backend class carries the
    per-backend posture marks for the fixtures it exercises — ``S3-028`` (s3_moto
    at Stage 2) and ``AZ-037`` (azurite) — plus STORE-007, the Store-layer
    share-across-threads property this generalises.
    """

    @pytest.mark.spec("STORE-007")
    def test_concurrent_reads_consistent(self, backend: Backend) -> None:
        """N threads reading a shared instance each see the correct content."""
        keys = {f"cc/read/{i}.txt": f"payload-{i}".encode() for i in range(_N_ITEMS)}
        for key, data in keys.items():
            backend.write(key, data)
        items = list(keys.items())

        def _read(idx: int, item: tuple[str, bytes]) -> tuple[bytes, bytes]:
            key, expected = item
            return backend.read_bytes(key), expected

        results, errors = _run_concurrently(_read, items, workers=_WORKERS)
        assert not errors, errors
        assert len(results) == len(items)
        assert all(got == expected for got, expected in results.values())

    @pytest.mark.spec("STORE-007")
    def test_concurrent_distinct_key_writes_all_land(self, backend: Backend, request: pytest.FixtureRequest) -> None:
        """N threads writing distinct keys: every write is durable (no lost writes)."""
        _xfail_local_dir_race_on_windows(backend, request)
        items = [(f"cc/write/{i}.bin", f"w{i}".encode()) for i in range(_N_ITEMS)]

        def _write(idx: int, item: tuple[str, bytes]) -> None:
            key, data = item
            backend.write(key, data)

        _, errors = _run_concurrently(_write, items, workers=_WORKERS)
        assert not errors, errors
        for key, data in items:
            assert backend.read_bytes(key) == data

    @pytest.mark.spec("STORE-007")
    def test_concurrent_read_after_write_consistent(self, backend: Backend, request: pytest.FixtureRequest) -> None:
        """Each thread reads back exactly what it just wrote to its own key."""
        _xfail_local_dir_race_on_windows(backend, request)
        items = [(f"cc/raw/{i}.txt", f"raw-{i}".encode()) for i in range(_N_ITEMS)]

        def _raw(idx: int, item: tuple[str, bytes]) -> tuple[bytes, bytes]:
            key, data = item
            backend.write(key, data)
            return backend.read_bytes(key), data

        results, errors = _run_concurrently(_raw, items, workers=_WORKERS)
        assert not errors, errors
        assert len(results) == len(items)
        assert all(got == expected for got, expected in results.values())


@pytest.mark.concurrency
@pytest.mark.spec("BE-028")
@pytest.mark.parametrize(
    "backend",
    fixture_params_concurrent(Capability.WRITE, posture="thread_safe"),
    indirect=True,
)
class TestConcurrentLargeUploads:
    """Tier 3 — N parallel large/streamed uploads on a real staged write path.

    Gated on ``large_write_distinct`` so it runs only where the multipart /
    block-staging / upload-session path is faithfully exercised (the in-process
    emulators at Stage 2 and the live fixtures at Stage 3, whose params carry
    ``pytest.mark.live``). On the default Stage-1 lane there is no such fixture,
    so the test is simply not parametrised onto Memory/Local.
    """

    @pytest.mark.spec("STORE-007")
    def test_concurrent_large_streamed_uploads(self, backend: Backend) -> None:
        _require(backend, Capability.ATOMIC_WRITE)
        _skip_unless_large_write_distinct(backend)
        payload = b"\xab" * _LARGE_SIZE

        def _upload(idx: int, item: int) -> int:
            key = f"cc/large/{item}.bin"
            # Fresh BytesIO per thread: a shared reader would race on its cursor.
            backend.write_atomic(key, io.BytesIO(payload))
            return backend.get_file_info(key).size

        results, errors = _run_concurrently(_upload, list(range(_LARGE_N)), workers=_LARGE_N)
        assert not errors, errors
        assert len(results) == _LARGE_N
        assert all(size == _LARGE_SIZE for size in results.values())


@pytest.mark.concurrency
@pytest.mark.spec("BE-028")
@pytest.mark.spec("SFTP-029")
@pytest.mark.parametrize(
    "backend",
    fixture_params_concurrent(Capability.WRITE, posture="single_connection"),
    indirect=True,
)
class TestSingleConnectionCarveOut:
    """Tier 2 — the ``single_connection`` posture carve-out.

    SFTP (shared paramiko socket), HTTP (shared redirect-counter opener), and the
    ``sqlite:///:memory:`` SQLBlob fixture (SingletonThreadPool → one isolated DB
    per thread) are declared ``single_connection``: concurrent ops on ONE instance
    race or fail. The documented, supported pattern is **one instance per
    thread**, and this test asserts exactly that — each thread builds its own
    backend via the registry ``factory`` and operates on it independently.

    The lane deliberately never subjects a *shared* single-connection instance
    to the thread-stress: ``fixture_params_concurrent(posture="thread_safe")``
    excludes these fixtures structurally, so the unsafe pattern is never run.
    A backend that silently became thread-safe — or a thread-safe backend that
    silently regressed to single-connection — would diverge from its declared
    posture and be caught by the registry posture guard
    (``test_registry.py::test_bk289_concurrency_posture_is_declared_and_split``).

    This carve-out runs over the WRITE-capable ``single_connection`` set —
    ``sftp_inproc`` (Stage 1, ``sftp_docker`` in the serial lane) and ``sqlblob``
    (each thread owns its own engine + isolated ``:memory:`` DB). HTTP carries no
    ``WRITE`` capability and its in-process fixture mutates a shared test server
    on construct, so it is not a clean per-thread-instance write substrate; its
    ``single_connection`` posture is pinned at the registry level instead.
    """

    @pytest.mark.spec("STORE-007")
    def test_one_instance_per_thread_works(self, backend: Backend) -> None:
        record = _fixture_record(backend)
        factory = record.factory
        cleanup = record.cleanup

        def _own_instance(idx: int, item: int) -> tuple[bytes, bytes]:
            instance = factory()
            try:
                key = f"sc/{idx}.txt"
                data = f"sc-{idx}".encode()
                instance.write(key, data)  # type: ignore[attr-defined]
                return instance.read_bytes(key), data  # type: ignore[attr-defined]
            finally:
                if cleanup is not None:
                    cleanup(instance)

        results, errors = _run_concurrently(_own_instance, list(range(_SC_WORKERS)), workers=_SC_WORKERS)
        assert not errors, errors
        assert len(results) == _SC_WORKERS
        assert all(got == expected for got, expected in results.values())
