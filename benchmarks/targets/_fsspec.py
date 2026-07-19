"""Fsspec-based targets — auto-skip if the relevant library is not installed."""

from __future__ import annotations

import contextlib
import warnings
from typing import TYPE_CHECKING

from benchmarks.targets._protocol import BenchTarget

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextlib.contextmanager
def _quiet_large_raw_body() -> Iterator[None]:
    """Silence aiohttp's >1 MiB raw-body ``ResourceWarning`` for one call.

    aiohttp warns (``payload.py``) when a raw ``bytes``/``memoryview`` body over
    ``TOO_LARGE_BYTES_BODY`` (2**20) is sent, and adlfs's buffered-file write
    stages the whole payload as a single ``memoryview`` block. Under the suite's
    ``filterwarnings = error`` the warning is promoted to an exception, which
    adlfs re-raises as ``RuntimeError: Failed to upload block: ...`` — so 10 MB
    writes error where 1 MB ones (below the threshold) pass. The upload itself is
    fine; the warning is cosmetic (no event loop to lock in a sync benchmark), so
    scope the suppression to this one message and keep the default write path — a
    faithful measurement of what a plain ``fs.open(...).write(bytes)`` user gets.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Sending a large body directly with raw bytes",
            category=ResourceWarning,
        )
        yield


class S3fsTarget(BenchTarget):
    """s3fs filesystem target."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        key: str | None = None,
        secret: str | None = None,
    ) -> None:
        import s3fs

        self._bucket = bucket
        kwargs: dict[str, str] = {}
        if key:
            kwargs["key"] = key
        if secret:
            kwargs["secret"] = secret
        client_kwargs: dict[str, str] = {"region_name": "us-east-1"}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._fs = s3fs.S3FileSystem(**kwargs, client_kwargs=client_kwargs)

    @property
    def label(self) -> str:
        return "s3fs"

    def _full(self, path: str) -> str:
        return f"{self._bucket}/{path}"

    def write(self, path: str, data: bytes) -> None:
        with self._fs.open(self._full(path), "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with self._fs.open(self._full(path), "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._full(path))

    def delete(self, path: str) -> None:
        self._fs.rm(self._full(path))

    def list_files(self, prefix: str) -> list[str]:
        return self._fs.ls(self._full(prefix), detail=False)

    def iter_children(self, prefix: str) -> list[str]:
        # s3fs `ls` already returns immediate files + subdirs in one combined listing.
        return self._fs.ls(self._full(prefix), detail=False)

    def invalidate_cache(self) -> None:
        self._fs.invalidate_cache()

    def close(self) -> None:
        self._fs.clear_instance_cache()


class AdlfsTarget(BenchTarget):
    """adlfs (Azure Blob via fsspec) target."""

    def __init__(self, container: str, connection_string: str) -> None:
        import adlfs

        self._container = container
        self._fs = adlfs.AzureBlobFileSystem(connection_string=connection_string)

    @property
    def label(self) -> str:
        return "adlfs"

    def _full(self, path: str) -> str:
        return f"{self._container}/{path}"

    def write(self, path: str, data: bytes) -> None:
        # adlfs stages the payload as one raw memoryview block; suppress aiohttp's
        # cosmetic >1 MiB ResourceWarning so the suite's error-on-warning does not
        # fail 10 MB writes. See _quiet_large_raw_body for the full rationale.
        with _quiet_large_raw_body(), self._fs.open(self._full(path), "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with self._fs.open(self._full(path), "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._full(path))

    def delete(self, path: str) -> None:
        self._fs.rm(self._full(path))

    def list_files(self, prefix: str) -> list[str]:
        return self._fs.ls(self._full(prefix), detail=False)

    def invalidate_cache(self) -> None:
        self._fs.invalidate_cache()

    def close(self) -> None:
        self._fs.clear_instance_cache()


class SshfsTarget(BenchTarget):
    """sshfs (SFTP via fsspec) target."""

    def __init__(self, host: str, port: int, username: str, password: str, base_path: str) -> None:
        import sshfs as sshfs_mod

        self._base_path = base_path
        self._fs = sshfs_mod.SSHFileSystem(host=host, port=port, username=username, password=password)

    @property
    def label(self) -> str:
        return "sshfs"

    def _full(self, path: str) -> str:
        return f"{self._base_path}/{path}"

    def write(self, path: str, data: bytes) -> None:
        full = self._full(path)
        parent = full.rsplit("/", 1)[0]
        self._fs.makedirs(parent, exist_ok=True)
        with self._fs.open(full, "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with self._fs.open(self._full(path), "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._full(path))

    def delete(self, path: str) -> None:
        self._fs.rm(self._full(path))

    def list_files(self, prefix: str) -> list[str]:
        return self._fs.ls(self._full(prefix), detail=False)

    def invalidate_cache(self) -> None:
        self._fs.invalidate_cache()

    def close(self) -> None:
        self._fs.clear_instance_cache()


class LocalFsspecTarget(BenchTarget):
    """fsspec local filesystem target."""

    def __init__(self, root: str) -> None:
        import fsspec

        self._root = root
        self._fs = fsspec.filesystem("file")

    @property
    def label(self) -> str:
        return "fsspec_local"

    def _full(self, path: str) -> str:
        return f"{self._root}/{path}"

    def write(self, path: str, data: bytes) -> None:
        import os

        full = self._full(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with self._fs.open(full, "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with self._fs.open(self._full(path), "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._full(path))

    def delete(self, path: str) -> None:
        self._fs.rm(self._full(path))

    def list_files(self, prefix: str) -> list[str]:
        return self._fs.ls(self._full(prefix), detail=False)

    def invalidate_cache(self) -> None:
        self._fs.invalidate_cache()
