"""S3-compatible object storage backend using s3fs."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeVar, cast

from remote_store._backend import _COPY_BUFSIZE
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
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

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.ATOMIC_MOVE})


class S3Backend(_S3Base):
    """S3-compatible object storage backend using s3fs.

    ``move()`` is implemented as a server-side copy followed by a delete.
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
        reject_write_under_file_ancestor: If ``True``, ``write`` /
            ``write_atomic`` / ``open_atomic`` / ``move`` / ``copy`` HEAD
            each slash-aligned ancestor of the target path and raise
            ``InvalidPath`` on the first regular-file hit, matching the
            cross-backend contract that hierarchical filesystems enforce
            natively. Default ``False``: each nested-path write otherwise
            pays one HEAD per ancestor; paths without slashes
            short-circuit.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ALL_CAPABILITIES

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
        reject_write_under_file_ancestor: bool = False,
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
        self._reject_write_under_file_ancestor = reject_write_under_file_ancestor
        self._fs_instance: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "s3"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    @property
    def _s3fs(self) -> Any:
        """Alias for the s3fs filesystem (satisfies ``_S3Base`` contract)."""
        return self._fs

    # endregion

    # region: public methods

    def check_health(self) -> None:
        with self._s3fs_errors():
            # Not self._fs.s3.head_bucket(...): raw aiobotocore returns a coroutine. See PING-004.
            self._fs.call_s3("head_bucket", Bucket=self._bucket)

    def native_path(self, path: str) -> str:
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

    def exists(self, path: str) -> bool:
        with self._s3fs_errors(path):
            return bool(self._fs.exists(self._s3_path(path)))

    def is_file(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._fs.info(self._s3_path(path))
                return bool(info.get("type") == "file")
            except FileNotFoundError:
                return False

    def is_folder(self, path: str) -> bool:
        with self._s3fs_errors(path):
            try:
                info = self._fs.info(self._s3_path(path))
                return bool(info.get("type") == "directory")
            except FileNotFoundError:
                return False

    def read(self, path: str) -> BinaryIO:
        with self._s3fs_errors(path):
            f: BinaryIO = self._fs.open(self._s3_path(path), "rb")
            stream = _safe_wrap(f, lambda s: _ErrorMappingStream(s, self._classify_error, path))
            return cast(BinaryIO, stream)  # noqa: TC006

    def read_bytes(self, path: str) -> bytes:
        with self._s3fs_errors(path):
            return bytes(self._fs.cat_file(self._s3_path(path)))

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        self._maybe_check_no_file_ancestor(path)
        sdk_metadata = dict(metadata) if metadata else None
        meta_kw = {"Metadata": sdk_metadata} if sdk_metadata is not None else {}
        with self._s3fs_errors(path):
            if not overwrite and self._fs.exists(self._s3_path(path)):
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            if isinstance(content, bytes):
                self._fs.pipe_file(self._s3_path(path), content, **meta_kw)
                size = len(content)
            else:
                size = 0
                f = self._fs.open(self._s3_path(path), "wb", **meta_kw)
                try:
                    while True:
                        chunk = content.read(_COPY_BUFSIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        size += len(chunk)
                except BaseException:
                    # BUG-214: the content source failed mid-stream. Letting
                    # s3fs's ``S3File.__exit__`` -> ``close()`` run would flush
                    # the buffer / complete the in-flight multipart upload,
                    # committing a truncated but complete-looking object and
                    # breaking the S3-010 / AW-001 atomicity contract.
                    # ``discard()`` aborts any multipart upload and drops the
                    # buffer; setting ``closed`` stops ``__del__`` from
                    # re-initiating an upload through a force-flush.
                    #
                    # ``discard()`` makes a live ``AbortMultipartUpload`` call,
                    # so it can itself fail (network blip, server error). Swallow
                    # that so the ORIGINAL content failure propagates -- and set
                    # ``closed`` regardless, so a failed abort still cannot leave
                    # ``__del__`` free to re-commit a truncated object.
                    with suppress(Exception):
                        f.discard()
                    f.closed = True
                    raise
                else:
                    f.close()
            # WriteResult.etag/digest are sourced from this head_object call --
            # the SAME call get_file_info() reads (S3-024) -- so the two agree by
            # construction and need no consistency xfail. (Contrast Azure, whose
            # write-response digest can diverge from the stored blob's: BUG-216.)
            # s3fs uploads normal-sized objects in a single PUT (no multipart
            # WriteResult path here even at ~10 MiB); the always-multipart S3 lane
            # is S3PyArrowBackend.
            raw = self._fs.call_s3("head_object", Bucket=self._bucket, Key=path, ChecksumMode="ENABLED")
        etag_raw: str | None = raw.get("ETag")
        etag = etag_raw.strip('"').lower() if etag_raw else None
        last_modified = raw.get("LastModified")
        version_id: str | None = raw.get("VersionId") or None
        digest = self._digest_from_head_response(raw)
        return WriteResult(
            path=RemotePath(path),
            size=size,
            source="native",
            etag=etag,
            last_modified=last_modified,
            version_id=version_id,
            digest=digest,
            metadata=metadata,
        )

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        # S3 PUT is inherently atomic (S3-010)
        return self.write(path, content, overwrite=overwrite, metadata=metadata)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        # S3 PUT is inherently atomic -- buffer then upload (SAW-010)
        self._maybe_check_no_file_ancestor(path)
        with self._s3fs_errors(path):
            if not overwrite and self._fs.exists(self._s3_path(path)):
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
            if not self._fs.exists(self._s3_path(path)):
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name)
                return
            self._fs.rm(self._s3_path(path))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not self._fs.exists(s3_path):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return
            if recursive:
                self._fs.rm(s3_path, recursive=True)
            else:
                # Non-recursive: fail if folder has contents
                contents = self._fs.ls(s3_path, detail=True)
                if contents:
                    raise DirectoryNotEmpty(
                        f"Folder not empty: {path}",
                        path=path,
                        backend=self.name,
                    )

    def get_file_info(self, path: str) -> FileInfo:
        with self._s3fs_errors(path):
            raw = self._fs.call_s3(
                "head_object",
                Bucket=self._bucket,
                Key=path,
                ChecksumMode="ENABLED",
            )
            return self._head_to_fileinfo(raw, path)

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._s3fs_errors(src):
            if not self._fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if self._s3_path(src) == self._s3_path(dst):
                return  # self-move is a no-op
            if not overwrite and self._fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            # BE-018 precondition order: src-NotFound takes priority over
            # dst-file-ancestor (matches LocalBackend.move's mkdir-parent
            # placement; ID-211 review).
            self._maybe_check_no_file_ancestor(dst)
            self._fs.copy(self._s3_path(src), self._s3_path(dst))
            self._fs.rm(self._s3_path(src))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._s3fs_errors(src):
            if not self._fs.exists(self._s3_path(src)):
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if self._s3_path(src) == self._s3_path(dst):
                return  # self-copy is a no-op
            if not overwrite and self._fs.exists(self._s3_path(dst)):
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            # BE-019 precondition order: src-NotFound before dst-file-ancestor (ID-211 review).
            self._maybe_check_no_file_ancestor(dst)
            self._fs.copy(self._s3_path(src), self._s3_path(dst))

    def close(self) -> None:
        if self._fs_instance is not None:
            self._fs_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        import s3fs  # type: ignore[import-untyped]

        if type_hint is s3fs.S3FileSystem:
            return self._fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3' does not expose native handle of type {type_hint.__name__}. "
            f"Override unwrap() in your backend to provide native access.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion

    # region: dunder methods

    def __repr__(self) -> str:
        return (
            f"S3Backend(bucket={self._bucket!r}, "
            f"endpoint_url={self._endpoint_url!r}, "
            f"key={'***' if self._key is not None else None!r}, "
            f"secret={'***' if self._secret is not None else None!r}, "
            f"region_name={self._region_name!r}, "
            f"tls_ca_bundle={self._tls_ca_bundle!r})"
        )

    # endregion

    # region: private helpers

    @property
    def _fs(self) -> Any:
        if self._fs_instance is None:
            import s3fs

            self._fs_instance = s3fs.S3FileSystem(**self._build_s3fs_kwargs())
        return self._fs_instance

    # endregion
