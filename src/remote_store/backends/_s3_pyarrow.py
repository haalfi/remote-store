"""Hybrid S3 backend using PyArrow (data path) and s3fs (control path)."""

from __future__ import annotations

import io
import logging
import tempfile
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar, cast

from remote_store._backend import _COPY_BUFSIZE
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    RemoteStoreError,
    _not_found,
    _permission_denied,
)
from remote_store._models import WriteResult
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream, _safe_wrap
from remote_store.backends._s3_base import (
    _S3_CA_ENV_VARS,
    _normalize_endpoint_url,
    _resolve_tls_ca_bundle,
    _S3Base,
    _validate_tls_ca_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._models import FileInfo
    from remote_store._types import WritableContent

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(
    set(Capability) - {Capability.ATOMIC_MOVE, Capability.WRITE_RESULT_NATIVE, Capability.USER_METADATA}
)

log = logging.getLogger(__name__)


class _PyArrowBinaryIO(io.RawIOBase):
    """Adapt a PyArrow RandomAccessFile to Python BinaryIO."""

    def __init__(self, pa_file: Any) -> None:
        self._pa = pa_file

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return bool(self._pa.seekable())

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._pa.read()  # type: ignore[no-any-return]
        return self._pa.read(size)  # type: ignore[no-any-return]

    _READLINE_CHUNK = 8192

    def readline(self, size: int | None = -1) -> bytes:
        """Read a single line, scanning in _READLINE_CHUNK-sized blocks.

        Requires a seekable underlying stream (open_input_file) because
        over-read bytes are rewound via seek().  Less efficient than
        BufferedReader for line-heavy workloads (separate read+seek per
        line vs batched internal buffer), but avoids the double-copy on
        the dominant chunk-read path.  See RFC-0003.
        """
        buf = bytearray()
        while size is None or size < 0 or len(buf) < size:
            remaining = size - len(buf) if size is not None and size >= 0 else self._READLINE_CHUNK
            chunk = self._pa.read(min(remaining, self._READLINE_CHUNK))
            if not chunk:
                break
            idx = chunk.find(b"\n")
            if idx >= 0:
                buf.extend(chunk[: idx + 1])
                over_read = len(chunk) - idx - 1
                if over_read > 0:
                    self._pa.seek(-over_read, 1)
                break
            buf.extend(chunk)
        return bytes(buf)

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        data = self._pa.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        self._pa.seek(offset, whence)
        return int(self._pa.tell())

    def tell(self) -> int:
        return int(self._pa.tell())

    def close(self) -> None:
        if not self.closed:
            self._pa.close()
            super().close()


class S3PyArrowBackend(_S3Base):
    """Hybrid S3 backend: PyArrow for reads/writes/copies, s3fs for listing/metadata.

    Drop-in alternative to ``S3Backend`` with the same constructor signature.
    Uses PyArrow's C++ S3 filesystem for data-path operations (higher throughput
    for large files) and s3fs for control-path operations (listing, metadata,
    deletion).

    ``move()`` is implemented as a PyArrow copy followed by an s3fs delete.
    This is non-atomic: a crash or network error between the two steps may
    leave both source and destination present.  ``ATOMIC_MOVE`` is not
    declared.

    Args:
        bucket: S3 bucket name (required, non-empty).
        endpoint_url: Custom endpoint URL (e.g. for MinIO).
        key: AWS access key ID.
        secret: AWS secret access key.
        region_name: AWS region name.
        tls_ca_bundle: Path to a PEM CA bundle file.  Falls back to
            ``AWS_CA_BUNDLE`` / ``REQUESTS_CA_BUNDLE`` / ``SSL_CERT_FILE``.
        client_options: Additional options passed to s3fs.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        key: str | Secret | None = None,
        secret: str | Secret | None = None,
        region_name: str | None = None,
        tls_ca_bundle: str | None = None,
        client_options: dict[str, Any] | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        if not bucket or not bucket.strip():
            raise ValueError("bucket must be a non-empty string")
        self._bucket = bucket
        self._endpoint_url = _normalize_endpoint_url(endpoint_url)
        self._key = _reveal(key)
        self._secret = _reveal(secret)
        self._region_name = region_name
        resolved_tls = _resolve_tls_ca_bundle(tls_ca_bundle, _S3_CA_ENV_VARS)
        _validate_tls_ca_bundle(resolved_tls)
        self._tls_ca_bundle = resolved_tls
        self._client_options = client_options or {}
        self._retry = retry
        self._pa_fs_instance: Any = None
        self._s3fs_instance: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "s3-pyarrow"

    @property
    def capabilities(self) -> CapabilitySet:
        return _ALL_CAPABILITIES

    # endregion

    # region: public methods

    def check_health(self) -> None:
        with self._pyarrow_errors():
            self._pa_fs.get_file_info(self._bucket)

    def native_path(self, path: str) -> str:
        return self._pa_path(path)

    def exists(self, path: str) -> bool:
        with self._s3fs_errors(path):
            return bool(self._s3fs.exists(self._s3_path(path)))

    def is_file(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._s3fs.info(self._s3_path(path))
                return bool(info.get("type") == "file")
            except FileNotFoundError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._s3fs.info(self._s3_path(path))
                return bool(info.get("type") == "directory")
            except FileNotFoundError:
                return False

    def read(self, path: str) -> BinaryIO:
        with self._pyarrow_errors(path):
            pa_file = self._pa_fs.open_input_file(self._pa_path(path))
            stream = _safe_wrap(pa_file, _PyArrowBinaryIO, lambda s: _ErrorMappingStream(s, self._classify_error, path))
            return cast(BinaryIO, stream)  # noqa: TC006

    def read_bytes(self, path: str) -> bytes:
        with self._pyarrow_errors(path):
            stream = self._pa_fs.open_input_stream(self._pa_path(path))
            return bytes(stream.read())

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        with self._s3fs_errors(path):
            if not overwrite and self._s3fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        with self._pyarrow_errors(path):
            out = self._pa_fs.open_output_stream(self._pa_path(path), buffer_size=_COPY_BUFSIZE)
            try:
                if isinstance(content, bytes):
                    out.write(content)
                    size = len(content)
                else:
                    size = 0
                    while True:
                        chunk = content.read(_COPY_BUFSIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                        size += len(chunk)
            finally:
                out.close()
        return WriteResult(path=RemotePath(path), size=size, source="basic")

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        # S3 PUT is inherently atomic (S3PA-013)
        return self.write(path, content, overwrite=overwrite)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        # S3 PUT is inherently atomic -- buffer then upload (SAW-010)
        with self._s3fs_errors(path):
            if not overwrite and self._s3fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
        buf: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
            max_size=8 * 1024 * 1024,
        )
        try:
            yield cast(BinaryIO, buf)  # noqa: TC006
            buf.seek(0)
            self.write(path, cast(BinaryIO, buf), overwrite=overwrite)  # noqa: TC006
        finally:
            buf.close()

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._s3fs_errors(path):
            if not self._s3fs.exists(self._s3_path(path)):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name)
                return
            self._s3fs.rm(self._s3_path(path))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not self._s3fs.exists(s3_path):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return
            if recursive:
                self._s3fs.rm(s3_path, recursive=True)
            else:
                # Non-recursive: fail if folder has contents
                contents = self._s3fs.ls(s3_path, detail=True)
                if contents:
                    raise DirectoryNotEmpty(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )

    def get_file_info(self, path: str) -> FileInfo:
        with self._s3fs_errors(path):
            raw = self._s3fs.call_s3(
                "head_object",
                Bucket=self._bucket,
                Key=path,
                ChecksumMode="ENABLED",
            )
            return self._head_to_fileinfo(raw, path)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        # Existence checks via s3fs, copy via pyarrow, delete via s3fs
        with self._s3fs_errors(src):
            if not self._s3fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if self._s3_path(src) == self._s3_path(dst):
                return  # self-move is a no-op
            if not overwrite and self._s3fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        with self._pyarrow_errors(src):
            self._pa_fs.copy_file(self._pa_path(src), self._pa_path(dst))
        with self._s3fs_errors(src):
            self._s3fs.rm(self._s3_path(src))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._s3fs_errors(src):
            if not self._s3fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if self._s3_path(src) == self._s3_path(dst):
                return  # self-copy is a no-op
            if not overwrite and self._s3fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
        with self._pyarrow_errors(src):
            self._pa_fs.copy_file(self._pa_path(src), self._pa_path(dst))

    def close(self) -> None:
        if self._s3fs_instance is not None:
            self._s3fs_instance = None
        self._pa_fs_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        import s3fs  # type: ignore[import-untyped]
        from pyarrow.fs import FileSystem as PyArrowFS  # type: ignore[import-untyped]
        from pyarrow.fs import S3FileSystem as PyArrowS3

        if type_hint is PyArrowS3 or type_hint is PyArrowFS:
            return self._pa_fs  # type: ignore[no-any-return]
        if type_hint is s3fs.S3FileSystem:
            return self._s3fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3-pyarrow' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: pyarrow.fs.FileSystem, pyarrow.fs.S3FileSystem, s3fs.S3FileSystem.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return (
            f"S3PyArrowBackend(bucket={self._bucket!r}, "
            f"endpoint_url={self._endpoint_url!r}, "
            f"key={'***' if self._key is not None else None!r}, "
            f"secret={'***' if self._secret is not None else None!r}, "
            f"region_name={self._region_name!r}, "
            f"tls_ca_bundle={self._tls_ca_bundle!r})"
        )

    # endregion

    # region: private helpers

    @property
    def _pa_fs(self) -> Any:
        """Lazy PyArrow S3FileSystem."""
        if self._pa_fs_instance is None:
            from pyarrow.fs import S3FileSystem as PyArrowS3

            kwargs: dict[str, Any] = {}
            if self._key is not None:
                kwargs["access_key"] = self._key
            if self._secret is not None:
                kwargs["secret_key"] = self._secret
            if self._region_name is not None:
                kwargs["region"] = self._region_name
            if self._endpoint_url is not None:
                endpoint = self._endpoint_url
                # PyArrow uses endpoint_override (host:port) and scheme separately
                if endpoint.startswith("http://"):
                    kwargs["scheme"] = "http"
                    kwargs["endpoint_override"] = endpoint[len("http://") :]
                elif endpoint.startswith("https://"):  # pragma: no cover -- tests use http
                    kwargs["scheme"] = "https"
                    kwargs["endpoint_override"] = endpoint[len("https://") :]
                else:  # pragma: no cover -- tests always have scheme prefix
                    kwargs["endpoint_override"] = endpoint
            if self._tls_ca_bundle is not None:
                kwargs.setdefault("tls_ca_file_path", self._tls_ca_bundle)
            kwargs.setdefault("anonymous", False)
            if self._retry is not None:
                from pyarrow.fs import AwsStandardS3RetryStrategy

                rp = self._retry
                if rp.backoff_base != 1.0 or rp.backoff_max != 60.0 or rp.jitter != 1.0 or rp.timeout is not None:
                    log.debug(
                        "S3-PyArrow retry: backoff_base, backoff_max, jitter, timeout "
                        "are not mappable to AwsStandardS3RetryStrategy; "
                        "only max_attempts is used",
                    )
                kwargs["retry_strategy"] = AwsStandardS3RetryStrategy(
                    max_attempts=rp.max_attempts,
                )
            self._pa_fs_instance = PyArrowS3(**kwargs)
        return self._pa_fs_instance

    @property
    def _s3fs(self) -> Any:
        """Lazy s3fs S3FileSystem."""
        if self._s3fs_instance is None:
            import copy

            import s3fs

            opts: dict[str, Any] = copy.deepcopy(self._client_options)
            if self._endpoint_url is not None:
                opts["endpoint_url"] = self._endpoint_url
            if self._key is not None:
                opts["key"] = self._key
            if self._secret is not None:
                opts["secret"] = self._secret
            if self._region_name is not None:
                client_kwargs: dict[str, Any] = opts.setdefault("client_kwargs", {})
                client_kwargs["region_name"] = self._region_name
            if self._retry is not None:
                import botocore.config  # type: ignore[import-untyped]

                rp = self._retry
                if rp.backoff_base != 1.0 or rp.backoff_max != 60.0 or rp.jitter != 1.0 or rp.timeout is not None:
                    log.debug(
                        "S3-PyArrow s3fs retry: backoff_base, backoff_max, jitter, timeout "
                        "are not mappable to botocore; only max_attempts is used",
                    )
                client_kwargs = opts.setdefault("client_kwargs", {})
                existing_config = client_kwargs.get("config")
                retry_config = botocore.config.Config(
                    retries={"max_attempts": rp.max_attempts, "mode": "standard"},
                )
                if existing_config is not None:
                    client_kwargs["config"] = existing_config.merge(retry_config)
                else:
                    client_kwargs["config"] = retry_config
            if self._tls_ca_bundle is not None:
                client_kwargs = opts.setdefault("client_kwargs", {})
                client_kwargs.setdefault("verify", self._tls_ca_bundle)
            opts.setdefault("anon", False)
            self._s3fs_instance = s3fs.S3FileSystem(**opts)
        return self._s3fs_instance

    def _pa_path(self, path: str) -> str:
        """Build bucket/key path for PyArrow."""
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

    @contextmanager
    def _pyarrow_errors(self, path: str = "") -> Iterator[None]:
        """Map PyArrow exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:  # pragma: no cover -- passthrough
            raise
        except FileNotFoundError:
            raise _not_found(path, self.name) from None
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except OSError as exc:  # pragma: no cover -- moto raises FileNotFoundError directly
            msg = str(exc).lower()
            if "404" in msg or "not found" in msg or "no such" in msg or "path does not exist" in msg:
                raise _not_found(path, self.name) from None
            if "403" in msg or "access denied" in msg:
                raise _permission_denied(path, self.name) from None
            if any(kw in msg for kw in ("endpoint", "connect", "timeout", "dns", "name or service")):
                raise BackendUnavailable(str(exc), path=path, backend=self.name) from None
            raise RemoteStoreError(str(exc), path=path, backend=self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def _extract_etag(self, info: dict[str, Any]) -> str | None:
        """Suppress ETag for listing paths (``list_files``, ``iter_children``).

        ``get_file_info`` bypasses this via ``_head_to_fileinfo`` which
        extracts ETag directly from the HeadObject response.
        """
        return None

    # endregion
