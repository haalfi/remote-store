"""Direct-boto3 S3 backend.

A third S3 lane that talks to S3 through ``boto3`` only -- no ``s3fs``,
no ``aiobotocore``, no ``pyarrow``. It exists to retire three pains the
``s3``/``s3-pyarrow`` lanes inherit from their dependencies and cannot fix
from our side:

1. the ``aiobotocore``-driven dependency-pin cascade against a user's own
   ``boto3`` (``s3`` pulls ``s3fs`` -> ``aiobotocore`` -> a pinned ``botocore``);
2. the s3fs-fuse >5 GB multipart-restart cliff (handled here by
   ``boto3.s3.transfer.TransferConfig``);
3. the fsspec directory-listing-cache staleness (this lane keeps no listing
   cache -- every ``list_*`` is a fresh ``list_objects_v2``).

Standalone by design: it subclasses ``Backend`` directly rather than
``_S3Base``, because ``_S3Base``'s listing / metadata methods are s3fs-coupled
(``self._s3fs.ls(...)``) and cannot be reused. The genuinely SDK-agnostic
helpers (``_normalize_endpoint_url``, ``_resolve_tls_ca_bundle``,
``_validate_tls_ca_bundle``) are imported from ``_s3_base``; the small
HeadObject -> ``FileInfo`` parsing is reimplemented here.

The data path is boto3-only: ``get_object`` Range reads for a seekable lazy
``read()``, ``put_object`` / ``upload_fileobj`` for writes.

Typed-error mapping reads ``ClientError.response['Error']['Code']`` directly:
the 403 / credential rows map to ``PermissionDenied`` and 404 to ``NotFound``.
A mid-stream content failure leaves **no** object -- unlike the s3fs lane,
``put_object`` never sends a truncated body and ``upload_fileobj`` aborts the
multipart upload on exception.
"""
# PoC for ID-202. Control-path prior art: the boto3 listing/stat/copy/delete
# shape in legacy/sam-services-snapshot/src/app/handler/s3/store.py (the origin
# of remote-store). Error-mapping contract: sdd/research/
# research-s3-error-mapping-fidelity.md (ID-200). Mid-stream-abort contract
# mirrors the s3fs-lane BUG-214 fix without inheriting its truncated-commit
# defect.

from __future__ import annotations

import base64
import copy
import io
import logging
import tempfile
from collections import deque
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeVar, cast

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    BackendUnavailable,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    NotFound,
    RemoteStoreError,
    _classify_by_message,
    _not_found,
    _permission_denied,
)
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath
from remote_store._stream import _ErrorMappingStream, _safe_wrap
from remote_store.backends._fileinfo import _clean_etag, _name_from_path, _normalize_modified
from remote_store.backends._s3_base import (
    _S3_CA_ENV_VARS,
    _normalize_endpoint_url,
    _resolve_tls_ca_bundle,
    _validate_tls_ca_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from remote_store._resolution import ResolutionPlan
    from remote_store._types import WritableContent

T = TypeVar("T")

log = logging.getLogger(__name__)

# Capability parity with S3Backend: everything except ATOMIC_MOVE (move is a
# server-side copy + delete, not crash-safe). SEEKABLE_READ is declared because
# read() returns a Range-backed seekable stream (see _S3RangeReader).
_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.ATOMIC_MOVE})

# read() wraps the per-call Range reader in a BufferedReader of this size so a
# sequential consume issues one GetObject per buffer rather than one per
# RawIOBase.readall() chunk (8 KiB). Random read_at via PyArrow still costs one
# ranged GET per seek+read; bulk sequential reads should prefer read_bytes.
_READ_BUFFER_SIZE = 1024 * 1024

# Error codes that map to PermissionDenied regardless of HTTP status. ExpiredToken
# is HTTP 400 (ID-200 § 3(c)) yet still a credential failure, so we key on the code.
_PERMISSION_CODES = frozenset(
    {
        "AccessDenied",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "ExpiredToken",
        "InvalidToken",
        "TokenRefreshRequired",
        "AccountProblem",
        "AllAccessDisabled",
    }
)
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})


class _S3RangeReader(io.RawIOBase):
    """Seekable lazy reader backed by ``get_object`` Range requests.

    Each ``readinto()`` issues a single ranged ``GetObject``; nothing is
    fetched until the caller reads. Mirrors ``_AzureRangeReader`` so the
    backend can declare ``SEEKABLE_READ`` and ``LAZY_READ`` at parity with
    ``S3Backend`` without buffering the whole object. Non-``OSError``
    botocore exceptions are re-raised as ``OSError`` so the surrounding
    ``_ErrorMappingStream`` classifies them via ``_classify_error``.
    """

    def __init__(self, client: Any, bucket: str, key: str, size: int) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key
        self._size = size
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:  # SEEK_SET
            self._pos = offset
        elif whence == 1:  # SEEK_CUR
            self._pos += offset
        elif whence == 2:  # SEEK_END
            self._pos = self._size + offset
        self._pos = max(0, min(self._pos, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        remaining = self._size - self._pos
        if remaining <= 0:
            return 0
        length = min(len(b), remaining)
        end = self._pos + length - 1
        try:
            resp = self._client.get_object(
                Bucket=self._bucket,
                Key=self._key,
                Range=f"bytes={self._pos}-{end}",
            )
            data = resp["Body"].read()
        except OSError:
            raise
        except Exception as exc:  # noqa: BLE001 -- botocore ClientError is not OSError
            raise OSError(str(exc)) from exc
        n = len(data)
        b[:n] = data
        self._pos += n
        return n

    def close(self) -> None:
        if not self.closed:
            self._client = None
            super().close()


class _CountingReader:
    """Wrap a read()-able so the streaming upload can report bytes written.

    ``upload_fileobj`` returns ``None``; the backend needs the byte count for
    ``WriteResult.size`` without a second HEAD round trip. A ``read()`` that
    raises propagates unchanged so ``upload_fileobj`` aborts the upload and no
    truncated object is committed.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._inner.read(size)
        if chunk:
            self.bytes_read += len(chunk)
        return cast(bytes, chunk)  # noqa: TC006


class S3Boto3Backend(Backend):
    """S3-compatible backend using boto3 directly (no s3fs / pyarrow).

    Drop-in alternative to ``S3Backend`` with the same constructor signature.
    ``move()`` is a server-side ``copy_object`` followed by ``delete_object``
    and is non-atomic, so ``ATOMIC_MOVE`` is not declared.

    Args:
        bucket: S3 bucket name (required, non-empty).
        endpoint_url: Custom endpoint URL (e.g. for MinIO). When set, the
            client uses path-style addressing for emulator compatibility.
        key: AWS access key ID.
        secret: AWS secret access key.
        region_name: AWS region name.
        tls_ca_bundle: Path to a PEM CA bundle file. Falls back to
            ``AWS_CA_BUNDLE`` / ``REQUESTS_CA_BUNDLE`` / ``SSL_CERT_FILE``.
        client_options: Optional dict; a ``config_kwargs`` entry is merged
            into the ``botocore.config.Config`` (PoC-minimal passthrough).
        retry: Retry policy; only ``max_attempts`` maps to botocore.
        reject_write_under_file_ancestor: If ``True``, ``write`` /
            ``write_atomic`` / ``open_atomic`` / ``move`` / ``copy`` HEAD each
            slash-aligned ancestor of the target and raise ``InvalidPath`` on
            the first regular-file hit (flat-namespace opt-in, default off).
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
        self._client_instance: Any = None
        self._transfer_config_instance: Any = None

    # region: properties

    @property
    def name(self) -> str:
        return "s3-boto3"

    @property
    def capabilities(self) -> CapabilitySet:
        return self.CAPABILITIES

    # endregion

    # region: path helpers

    def native_path(self, path: str) -> str:
        if path:
            return f"{self._bucket}/{path}"
        return self._bucket

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._bucket}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    def resolve(self, path: str) -> ResolutionPlan:
        from remote_store._resolution import ResolutionPlan as _RP
        from remote_store._resolution import _strip_userinfo

        return _RP(
            kind=self.name,
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "bucket": self._bucket,
                "object_key": path,
                "endpoint_url": _strip_userinfo(self._endpoint_url),
            },
        )

    @staticmethod
    def _prefix_of(path: str) -> str:
        """Folder listing prefix for ``path`` (``""`` for the bucket root)."""
        return f"{path.rstrip('/')}/" if path else ""

    # endregion

    # region: existence / type checks

    def exists(self, path: str) -> bool:
        with self._boto_errors(path):
            if path == "":
                return True
            if self._head_or_none(path) is not None:
                return True
            return self._prefix_has_children(path)

    def is_file(self, path: str) -> bool:
        with self._boto_errors(path):
            return self._head_or_none(path) is not None

    def is_folder(self, path: str) -> bool:
        with self._boto_errors(path):
            if path == "":
                return True
            if self._head_or_none(path) is not None:
                return False  # a file shadows a same-named prefix (flat-NS)
            return self._prefix_has_children(path)

    # endregion

    # region: read

    def _open_range_stream(self, path: str) -> Any:
        """HEAD for size, then a Range reader wrapped in error mapping.

        The returned ``_ErrorMappingStream`` is seekable and unbuffered: each
        ``readinto`` is exactly one ranged ``GetObject``. ``read`` adds a
        ``BufferedReader`` on top for sequential efficiency; ``read_seekable``
        returns this bare stream (see its docstring).
        """
        head = self._client.head_object(Bucket=self._bucket, Key=path)
        size = int(head.get("ContentLength", 0) or 0)
        reader = _S3RangeReader(self._client, self._bucket, path, size)
        return _safe_wrap(reader, lambda s: _ErrorMappingStream(s, self._classify_error, path))

    def read(self, path: str) -> BinaryIO:
        # BufferedReader batches a sequential consume into ~1 GET per
        # _READ_BUFFER_SIZE rather than one per RawIOBase.readall() chunk.
        with self._boto_errors(path):
            inner = self._open_range_stream(path)
            buffered = _safe_wrap(inner, lambda s: io.BufferedReader(s, buffer_size=_READ_BUFFER_SIZE))
            return cast(BinaryIO, buffered)  # noqa: TC006

    def read_seekable(self, path: str) -> BinaryIO:
        # No BufferedReader (unlike read()): PyArrow's random read_at seeks
        # before each read, and BufferedReader invalidates its buffer on seek --
        # turning each small read_at into a full _READ_BUFFER_SIZE GetObject and
        # refetching overlapping ranges. Returning the bare Range reader keeps
        # each read_at to one ranged GET. Matches the Azure / S3PyArrow "no
        # BufferedReader on the seekable path" contract.
        with self._boto_errors(path):
            return cast(BinaryIO, self._open_range_stream(path))  # noqa: TC006

    def read_bytes(self, path: str) -> bytes:
        with self._boto_errors(path):
            resp = self._client.get_object(Bucket=self._bucket, Key=path)
            return bytes(resp["Body"].read())

    # endregion

    # region: write

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
        extra: dict[str, Any] = {"Metadata": sdk_metadata} if sdk_metadata is not None else {}
        with self._boto_errors(path):
            if not overwrite and self._head_or_none(path) is not None:
                raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            if isinstance(content, bytes):
                self._client.put_object(Bucket=self._bucket, Key=path, Body=content, **extra)
                size = len(content)
            else:
                # Multipart via TransferConfig. A mid-stream read() failure
                # propagates and upload_fileobj aborts the upload -- no
                # truncated object is committed (BUG-214 guarantee).
                counting = _CountingReader(content)
                self._client.upload_fileobj(
                    counting,
                    self._bucket,
                    path,
                    ExtraArgs=extra or None,
                    Config=self._transfer_config,
                )
                size = counting.bytes_read
            raw = self._client.head_object(Bucket=self._bucket, Key=path, ChecksumMode="ENABLED")
        return WriteResult(
            path=RemotePath(path),
            size=size,
            source="native",
            etag=_clean_etag(raw.get("ETag")),
            last_modified=raw.get("LastModified"),
            version_id=raw.get("VersionId") or None,
            digest=self._digest_from_head_response(raw),
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
        # A single PUT is atomic, and a multipart upload only becomes visible on
        # CompleteMultipartUpload -- partial parts are never readable as the
        # object. upload_fileobj aborts on failure, so write is already
        # atomic-safe; no buffering needed (unlike the pyarrow lane).
        return self.write(path, content, overwrite=overwrite, metadata=metadata)

    @contextmanager
    def open_atomic(self, path: str, *, overwrite: bool = False) -> Iterator[BinaryIO]:
        self._maybe_check_no_file_ancestor(path)
        with self._boto_errors(path):
            if not overwrite and self._head_or_none(path) is not None:
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

    # endregion

    # region: delete

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        with self._boto_errors(path):
            if self._head_or_none(path) is None:
                if not missing_ok:
                    raise NotFound(f"File not found: {path}", path=path, backend=self.name)
                return
            self._client.delete_object(Bucket=self._bucket, Key=path)

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        with self._boto_errors(path):
            prefix = self._prefix_of(path)
            if not self._prefix_has_children(path):
                if not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
                return
            if not recursive:
                raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
            self._delete_prefix(prefix)

    # endregion

    # region: metadata

    def get_file_info(self, path: str) -> FileInfo:
        with self._boto_errors(path):
            raw = self._client.head_object(Bucket=self._bucket, Key=path, ChecksumMode="ENABLED")
            return self._head_to_fileinfo(raw, path)

    def get_folder_info(self, path: str) -> FolderInfo:
        with self._boto_errors(path):
            prefix = self._prefix_of(path)
            if path and not self._prefix_has_children(path):
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            file_count = 0
            total_size = 0
            latest: Any = None
            for page in self._paginate(prefix, delimiter=None):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith("/"):
                        continue
                    file_count += 1
                    total_size += int(obj.get("Size", 0) or 0)
                    modified = obj.get("LastModified")
                    if modified is not None and (latest is None or modified > latest):
                        latest = modified
            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=_normalize_modified(latest) if latest is not None else None,
            )

    # endregion

    # region: listing

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        prefix = self._prefix_of(path)
        # Unified delimiter BFS: non-recursive == depth limit 0; recursive with
        # max_depth=None == unlimited. Mirrors _S3Base.list_files structure.
        depth_limit = 0 if not recursive else max_depth
        queue: deque[tuple[str, int]] = deque([(prefix, 0)])
        while queue:
            current, depth = queue.popleft()
            for page in self._paginate(current, delimiter="/"):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("/") or key == current:
                        continue
                    yield self._obj_to_fileinfo(obj)
                if depth_limit is None or depth < depth_limit:
                    for cp in page.get("CommonPrefixes", []):
                        queue.append((cp["Prefix"], depth + 1))

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        prefix = self._prefix_of(path)
        for page in self._paginate(prefix, delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                rel = cp["Prefix"].rstrip("/")
                yield FolderEntry(path=RemotePath(rel), name=rel.rsplit("/", 1)[-1])

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        prefix = self._prefix_of(path)
        for page in self._paginate(prefix, delimiter="/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/") or key == prefix:
                    continue
                yield self._obj_to_fileinfo(obj)
            for cp in page.get("CommonPrefixes", []):
                rel = cp["Prefix"].rstrip("/")
                yield FolderEntry(path=RemotePath(rel), name=rel.rsplit("/", 1)[-1])

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        from remote_store._glob import extract_prefix, needs_recursive, pattern_to_regex

        prefix = extract_prefix(pattern)
        recursive = needs_recursive(pattern)
        compiled = pattern_to_regex(pattern)
        for info in self.list_files(prefix, recursive=recursive):
            if compiled.match(str(info.path)):
                yield info

    # endregion

    # region: move / copy

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._boto_errors(src):
            if self._head_or_none(src) is None:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if src == dst:
                return  # self-move is a no-op
            if not overwrite and self._head_or_none(dst) is not None:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            # Precondition order: src-NotFound before dst-file-ancestor (ID-211).
            self._maybe_check_no_file_ancestor(dst)
            self._client.copy_object(
                Bucket=self._bucket,
                Key=dst,
                CopySource={"Bucket": self._bucket, "Key": src},
            )
            self._client.delete_object(Bucket=self._bucket, Key=src)

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        with self._boto_errors(src):
            if self._head_or_none(src) is None:
                raise NotFound(f"Source not found: {src}", path=src, backend=self.name)
            if src == dst:
                return  # self-copy is a no-op
            if not overwrite and self._head_or_none(dst) is not None:
                raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
            self._maybe_check_no_file_ancestor(dst)
            self._client.copy_object(
                Bucket=self._bucket,
                Key=dst,
                CopySource={"Bucket": self._bucket, "Key": src},
            )

    # endregion

    # region: lifecycle / introspection

    def check_health(self) -> None:
        with self._boto_errors():
            self._client.head_bucket(Bucket=self._bucket)

    def close(self) -> None:
        self._client_instance = None
        self._transfer_config_instance = None

    def unwrap(self, type_hint: type[T]) -> T:
        from botocore.client import BaseClient  # type: ignore[import-untyped]

        if type_hint is BaseClient:
            return self._client  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 's3-boto3' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: botocore.client.BaseClient (the boto3 S3 client).",
            capability="unwrap",
            backend=self.name,
        )

    def __repr__(self) -> str:
        return (
            f"S3Boto3Backend(bucket={self._bucket!r}, "
            f"endpoint_url={self._endpoint_url!r}, "
            f"key={'***' if self._key is not None else None!r}, "
            f"secret={'***' if self._secret is not None else None!r}, "
            f"region_name={self._region_name!r}, "
            f"tls_ca_bundle={self._tls_ca_bundle!r})"
        )

    # endregion

    # region: error handling

    @contextmanager
    def _boto_errors(self, path: str = "") -> Iterator[None]:
        """Map botocore exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def _classify_error(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify a botocore exception by its ``Error.Code``, then HTTP status."""
        # ID-200 mapping contract (see module-level note): Error.Code first.
        from botocore.exceptions import (  # type: ignore[import-untyped]
            BotoCoreError,
            ClientError,
        )

        if isinstance(exc, ClientError):
            err = exc.response.get("Error", {})
            code = err.get("Code", "")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if code in _NOT_FOUND_CODES or status == 404:
                return _not_found(path, self.name)
            if code in _PERMISSION_CODES or status in (401, 403):
                return _permission_denied(path, self.name)
            if status in (408, 500, 502, 503, 504) or code in {
                "RequestTimeout",
                "SlowDown",
                "InternalError",
                "ServiceUnavailable",
            }:
                return BackendUnavailable(str(exc), path=path, backend=self.name)
            return RemoteStoreError(str(exc), path=path, backend=self.name)
        if isinstance(exc, BotoCoreError):
            # EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError, etc.
            return BackendUnavailable(str(exc), path=path, backend=self.name)
        return _classify_by_message(exc, path, self.name)

    # endregion

    # region: private helpers

    @property
    def _client(self) -> Any:
        if self._client_instance is None:
            import boto3  # type: ignore[import-untyped]

            kwargs: dict[str, Any] = {"service_name": "s3", "config": self._build_boto_config()}
            if self._endpoint_url is not None:
                kwargs["endpoint_url"] = self._endpoint_url
            if self._key is not None:
                kwargs["aws_access_key_id"] = self._key
            if self._secret is not None:
                kwargs["aws_secret_access_key"] = self._secret
            if self._region_name is not None:
                kwargs["region_name"] = self._region_name
            if self._tls_ca_bundle is not None:
                kwargs["verify"] = self._tls_ca_bundle
            self._client_instance = boto3.client(**kwargs)
        return self._client_instance

    def _build_boto_config(self) -> Any:
        from botocore.config import Config  # type: ignore[import-untyped]

        cfg_kwargs: dict[str, Any] = dict(copy.deepcopy(self._client_options).get("config_kwargs") or {})
        # Custom endpoints (MinIO, moto) require path-style addressing.
        if self._endpoint_url is not None:
            cfg_kwargs.setdefault("s3", {"addressing_style": "path"})
        if self._retry is not None:
            rp = self._retry
            if rp.backoff_base != 1.0 or rp.backoff_max != 60.0 or rp.jitter != 1.0 or rp.timeout is not None:
                log.debug(
                    "%s retry: only max_attempts maps to botocore; backoff/jitter/timeout ignored",
                    self.name,
                )
            cfg_kwargs["retries"] = {"max_attempts": rp.max_attempts, "mode": "standard"}
        return Config(**cfg_kwargs)

    @property
    def _transfer_config(self) -> Any:
        if self._transfer_config_instance is None:
            from boto3.s3.transfer import TransferConfig  # type: ignore[import-untyped]

            self._transfer_config_instance = TransferConfig()
        return self._transfer_config_instance

    def _paginate(self, prefix: str, *, delimiter: str | None) -> Iterator[dict[str, Any]]:
        """Yield ``list_objects_v2`` pages for ``prefix``."""
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "PaginationConfig": {"PageSize": 1000}}
        if prefix:
            kwargs["Prefix"] = prefix
        if delimiter is not None:
            kwargs["Delimiter"] = delimiter
        paginator = self._client.get_paginator("list_objects_v2")
        yield from paginator.paginate(**kwargs)

    def _head_or_none(self, key: str) -> dict[str, Any] | None:
        """Return the HeadObject response, or ``None`` on a 404."""
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        try:
            return cast("dict[str, Any]", self._client.head_object(Bucket=self._bucket, Key=key))
        except ClientError as exc:
            if self._is_404(exc):
                return None
            raise

    @staticmethod
    def _is_404(exc: Any) -> bool:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        return code in _NOT_FOUND_CODES or status == 404

    def _prefix_has_children(self, path: str) -> bool:
        resp = self._client.list_objects_v2(
            Bucket=self._bucket,
            Prefix=self._prefix_of(path),
            MaxKeys=1,
        )
        return bool(resp.get("KeyCount", 0)) or bool(resp.get("CommonPrefixes"))

    def _delete_prefix(self, prefix: str) -> None:
        batch: list[dict[str, str]] = []
        for page in self._paginate(prefix, delimiter=None):
            for obj in page.get("Contents", []):
                batch.append({"Key": obj["Key"]})
                if len(batch) == 1000:  # S3 DeleteObjects limit
                    self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch, "Quiet": True})
                    batch = []
        if batch:
            self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch, "Quiet": True})

    def _maybe_check_no_file_ancestor(self, path: str) -> None:
        if not self._reject_write_under_file_ancestor:
            return
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

        from remote_store.backends._flat_ns import _check_no_file_ancestor

        def _head_one(key: str) -> bool:
            # Fail-open on probe failures (404, network, botocore-internal); see
            # _flat_ns.py "Fail-open head_one". Programmer errors propagate.
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
            except (ClientError, BotoCoreError, OSError):
                return False
            return True

        _check_no_file_ancestor(path, head_one=_head_one, backend=self.name)

    def _obj_to_fileinfo(self, obj: dict[str, Any]) -> FileInfo:
        key = obj["Key"]
        return FileInfo(
            path=RemotePath(key),
            name=_name_from_path(key),
            size=int(obj.get("Size", 0) or 0),
            modified_at=_normalize_modified(obj.get("LastModified")),
            etag=_clean_etag(obj.get("ETag")),
        )

    # S3-024: algorithm name -> HeadObject response key for checksums.
    _CHECKSUM_ALGO_TO_RESPONSE_KEY: ClassVar[dict[str, str]] = {
        "sha256": "ChecksumSHA256",
        "sha1": "ChecksumSHA1",
        "crc32": "ChecksumCRC32",
        "crc32c": "ChecksumCRC32C",
    }

    def _head_to_fileinfo(self, raw: dict[str, Any], path: str) -> FileInfo:
        raw_meta = raw.get("Metadata") or {}
        return FileInfo(
            path=RemotePath(path),
            name=_name_from_path(path),
            size=int(raw.get("ContentLength", 0) or 0),
            modified_at=_normalize_modified(raw.get("LastModified")),
            etag=_clean_etag(raw.get("ETag")),
            digest=self._digest_from_head_response(raw),
            metadata=dict(raw_meta) if raw_meta else None,
        )

    def _digest_from_head_response(self, raw: dict[str, Any]) -> ContentDigest | None:
        for algo_lower, response_key in self._CHECKSUM_ALGO_TO_RESPONSE_KEY.items():
            b64_value = raw.get(response_key)
            if not b64_value:
                continue
            try:
                return ContentDigest(algo_lower, base64.b64decode(b64_value).hex())
            except Exception:  # noqa: BLE001
                continue
        return None

    # endregion
