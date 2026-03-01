"""BenchTarget ABC — minimal interface for comparative benchmarks."""

from __future__ import annotations

import abc


class BenchTarget(abc.ABC):
    """Minimal interface covering operations where comparison is meaningful.

    Only basic byte-level operations are included — streaming, atomic writes,
    copy/move, and metadata queries are remote-store-specific and stay as
    ``bench_backend``-only tests.
    """

    @property
    @abc.abstractmethod
    def label(self) -> str:
        """Short human-readable label for benchmark IDs (e.g. ``'boto3_raw'``)."""

    @abc.abstractmethod
    def write(self, path: str, data: bytes) -> None:
        """Write ``data`` to ``path``, creating or overwriting."""

    @abc.abstractmethod
    def read(self, path: str) -> bytes:
        """Read the full content of ``path`` as bytes."""

    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        """Return ``True`` if ``path`` exists."""

    @abc.abstractmethod
    def delete(self, path: str) -> None:
        """Delete the file at ``path``."""

    @abc.abstractmethod
    def list_files(self, prefix: str) -> list[str]:
        """List file paths under ``prefix``."""

    def invalidate_cache(self) -> None:  # noqa: B027
        """Invalidate any client-side directory cache.

        Called after fixture setup and before benchmark measurement to ensure
        listing benchmarks reflect real I/O, not cached results from the
        population phase.  Default is a no-op.
        """

    def close(self) -> None:  # noqa: B027
        """Release resources. Default is a no-op."""
