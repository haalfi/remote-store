"""Async Azure Storage backend -- Blob SDK for non-HNS, DataLake SDK for HNS."""

from __future__ import annotations

import contextlib
import inspect
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._config import RetryPolicy, Secret, _reveal
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    RemoteStoreError,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath
from remote_store.aio._async_backend import AsyncBackend
from remote_store.backends._azure import _AZURE_BLOCK_SIZE, AzureBackend
from remote_store.backends._azure_common import (
    _build_azure_write_result,
    build_azure_retry,
    classify_azure_error,
    props_to_fileinfo,
    validate_azure_params,
)
from remote_store.backends._azure_common import (
    azure_path as _azure_path_fn,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from remote_store._models import WriteResult
    from remote_store._resolution import ResolutionPlan
    from remote_store.aio._types import AsyncWritableContent

T = TypeVar("T")

_ALL_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.SEEKABLE_READ, Capability.ATOMIC_MOVE})

log = logging.getLogger(__name__)


class AsyncAzureBackend(AsyncBackend):
    """Async Azure Storage backend.

    Uses the async Blob SDK for non-HNS accounts (plain Blob Storage, Azurite)
    and the async DataLake SDK for HNS accounts (ADLS Gen2) to get atomic
    rename and real directory support.

    Args:
        container: Azure Storage container name (required, non-empty).
        account_name: Storage account name.
        account_url: Full account URL (e.g. ``https://myaccount.dfs.core.windows.net``).
        account_key: Storage account key.
        sas_token: Shared Access Signature token.
        connection_string: Azure Storage connection string.
        credential: Any credential object (e.g. ``DefaultAzureCredential()``).
        client_options: Additional options passed to service clients.
            The library sets ``max_single_put_size``, ``max_block_size``,
            and ``min_large_block_upload_threshold`` defaults for streaming
            memory discipline; user-supplied values take precedence.
        retry: Retry policy for transient failures.
        max_concurrency: Maximum number of parallel connections for
            uploads and downloads (default ``1`` -- sequential).
        reject_write_under_file_ancestor: If ``True``, ``write`` /
            ``write_atomic`` / ``move`` / ``copy`` HEAD each
            slash-aligned ancestor of the target path on non-HNS
            accounts and raise ``InvalidPath`` on the first regular-file
            hit. On HNS accounts the kwarg short-circuits: ``hdi_isfolder``
            rejects the operation natively, **but** until ID-213 / BK-235
            lands that native rejection surfaces as ``NotFound`` or
            ``AlreadyExists`` rather than ``InvalidPath``. The
            cross-backend ``InvalidPath`` contract the kwarg promises is
            therefore *deferred* on HNS, not delivered — even when set.
            Default ``False``. See spec 003 § BE-008 / spec 029 §
            ASYNC-008 and ID-211.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ALL_CAPABILITIES
    __mirror__: ClassVar[type[AzureBackend]] = AzureBackend

    def __init__(
        self,
        container: str,
        *,
        account_name: str | None = None,
        account_url: str | None = None,
        account_key: str | Secret | None = None,
        sas_token: str | Secret | None = None,
        connection_string: str | Secret | None = None,
        credential: Any | None = None,
        client_options: dict[str, Any] | None = None,
        retry: RetryPolicy | None = None,
        max_concurrency: int = 1,
        reject_write_under_file_ancestor: bool = False,
    ) -> None:
        validate_azure_params(container, account_name, account_url, connection_string, max_concurrency)
        self._container = container
        self._account_name = account_name
        self._account_url = account_url
        self._account_key = _reveal(account_key)
        self._sas_token = _reveal(sas_token)
        self._connection_string = _reveal(connection_string)
        self._credential = credential
        self._client_options = client_options or {}
        self._retry = retry
        self._max_concurrency = max_concurrency
        self._reject_write_under_file_ancestor = reject_write_under_file_ancestor
        # Lazy instances
        self._blob_service_instance: Any = None
        self._cc_instance: Any = None
        self._datalake_service_instance: Any = None
        self._fs_instance: Any = None
        self._hns_enabled: bool | None = None
        self._resolved_credential: Any = None

    # region: properties

    @property
    def name(self) -> str:
        """Unique identifier for this backend type."""
        return "async-azure"

    @property
    def capabilities(self) -> CapabilitySet:
        """Declared capabilities of this backend."""
        return self.CAPABILITIES

    # endregion

    # region: private — file-ancestor pre-check (ID-211 opt-in)

    async def _maybe_check_no_file_ancestor(self, path: str) -> None:
        """Async sibling of ``AzureBackend._maybe_check_no_file_ancestor`` (ID-211)."""
        if not self._reject_write_under_file_ancestor:
            return
        if await self._ensure_hns():
            return
        from remote_store.backends._flat_ns import _acheck_no_file_ancestor

        async def _head_one(key: str) -> bool:
            bc = self._blob_client(key)
            try:
                await bc.get_blob_properties()
            except ResourceNotFoundError:
                return False
            except Exception:  # noqa: BLE001
                return False
            return True

        await _acheck_no_file_ancestor(path, head_one=_head_one, backend=self.name)

    # endregion

    # region: lazy client properties

    @property
    def _blob_service(self) -> Any:
        """Lazy async BlobServiceClient."""
        if self._blob_service_instance is None:
            from azure.storage.blob.aio import BlobServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            # BUG-161/BUG-162: force staged-block upload, keep memory bounded.
            _blk = _AZURE_BLOCK_SIZE
            opts.setdefault("max_single_put_size", _blk)
            opts.setdefault("max_block_size", _blk)
            opts.setdefault("min_large_block_upload_threshold", 1)  # 1 byte = always stage
            azure_retry = build_azure_retry(self._retry)
            if azure_retry is not None and "retry_policy" not in opts:
                opts["retry_policy"] = azure_retry
            if self._connection_string:
                self._blob_service_instance = BlobServiceClient.from_connection_string(self._connection_string, **opts)
            else:  # pragma: no cover -- only reached without connection_string
                url = self._account_url
                if url is None and self._account_name is not None:
                    url = f"https://{self._account_name}.blob.core.windows.net"
                assert url is not None  # guaranteed by __init__ validation
                cred = self._get_credential()
                self._blob_service_instance = BlobServiceClient(account_url=url, credential=cred, **opts)
        return self._blob_service_instance

    @property
    def _cc(self) -> Any:
        """Lazy async ContainerClient (Blob SDK)."""
        if self._cc_instance is None:
            self._cc_instance = self._blob_service.get_container_client(self._container)
        return self._cc_instance

    @property
    def _datalake_service(self) -> Any:  # pragma: no cover -- HNS only, requires ADLS Gen2
        """Lazy async DataLakeServiceClient (only used for HNS accounts)."""
        if self._datalake_service_instance is None:
            from azure.storage.filedatalake.aio import DataLakeServiceClient

            opts: dict[str, Any] = dict(self._client_options)
            # BUG-161/BUG-162: same block-size defaults as Blob SDK.
            _blk = _AZURE_BLOCK_SIZE
            opts.setdefault("max_single_put_size", _blk)
            opts.setdefault("max_block_size", _blk)
            opts.setdefault("min_large_block_upload_threshold", 1)  # 1 byte = always stage
            azure_retry = build_azure_retry(self._retry)
            if azure_retry is not None and "retry_policy" not in opts:
                opts["retry_policy"] = azure_retry
            if self._connection_string:
                self._datalake_service_instance = DataLakeServiceClient.from_connection_string(
                    self._connection_string, **opts
                )
            else:
                url = self._account_url
                if url is None and self._account_name is not None:
                    url = f"https://{self._account_name}.dfs.core.windows.net"
                assert url is not None
                cred = self._get_credential()
                self._datalake_service_instance = DataLakeServiceClient(account_url=url, credential=cred, **opts)
        return self._datalake_service_instance

    @property
    def _fs(self) -> Any:  # pragma: no cover -- HNS only, requires ADLS Gen2
        """Lazy async FileSystemClient (DataLake SDK, HNS only)."""
        if self._fs_instance is None:
            self._fs_instance = self._datalake_service.get_file_system_client(self._container)
        return self._fs_instance

    # endregion

    # region: HNS detection

    async def _ensure_hns(self) -> bool:
        """Detect whether the storage account has Hierarchical Namespace enabled.

        Returns:
            ``True`` if HNS is enabled, ``False`` otherwise.
        """
        if self._hns_enabled is None:
            try:
                info = await self._blob_service.get_account_information()
                self._hns_enabled = bool(info.get("is_hns_enabled", False))
            except Exception:  # noqa: BLE001
                log.warning(
                    "Failed to detect HNS status, falling back to non-HNS behavior",
                    exc_info=True,
                )
                self._hns_enabled = False
        return self._hns_enabled

    # endregion

    # region: public methods

    async def check_health(self) -> None:
        """Verify the backend is reachable and credentials are valid.

        Raises:
            PermissionDenied: If credentials are invalid.
            NotFound: If the container does not exist.
            BackendUnavailable: If the backend cannot be reached.
        """
        async with self._errors():
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                await self._fs.get_file_system_properties()
            else:
                await self._cc.get_container_properties()

    def to_key(self, native_path: str) -> str:
        """Convert a backend-native path to a backend-relative key.

        Args:
            native_path: Absolute or backend-native path string.

        Returns:
            Path relative to the backend's root.
        """
        prefix = f"{self._container}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        return native_path

    def native_path(self, path: str) -> str:
        """Convert a backend-relative key to the backend-native path.

        Args:
            path: Backend-relative key.

        Returns:
            Backend-native path (``container/path``).
        """
        if path:
            return f"{self._container}/{path}"
        return self._container

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with Azure-specific details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind="async-azure"`` and ``details`` containing
            ``container`` and ``account_url``.
        """
        from remote_store._resolution import ResolutionPlan as _RP
        from remote_store._resolution import _strip_userinfo

        return _RP(
            kind="async-azure",
            backend=self.name,
            key=path,
            native_path=self.native_path(path),
            details={
                "container": self._container,
                "account_url": _strip_userinfo(self._account_url),
            },
        )

    async def exists(self, path: str) -> bool:
        """Check if a file or folder exists.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if a file or folder exists at *path*.
        """
        async with self._errors(path):
            ap = _azure_path_fn(path)
            if not ap:
                return True
            # Check as blob
            bc = self._cc.get_blob_client(ap)
            try:
                await bc.get_blob_properties()
                return True
            except ResourceNotFoundError:
                pass
            # Check as folder
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    await self._fs.get_directory_client(ap).get_directory_properties()
                    return True
                except Exception:  # noqa: BLE001
                    return False
            else:
                prefix = ap.rstrip("/") + "/"
                blobs = self._cc.list_blobs(name_starts_with=prefix, results_per_page=1)
                return bool([b async for b in blobs][:1])

    async def is_file(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing file.

        Args:
            path: Backend-relative key.

        Returns:
            ``True`` if *path* exists and is a file.
        """
        async with self._errors(path):
            bc = self._blob_client(path)
            try:
                props = await bc.get_blob_properties()
                meta = getattr(props, "metadata", None) or {}
                return not meta.get("hdi_isfolder")
            except ResourceNotFoundError:
                return False

    async def is_folder(self, path: str) -> bool:
        """Return ``True`` if ``path`` is an existing folder.

        Args:
            path: Backend-relative key, or ``""`` for the root.

        Returns:
            ``True`` if *path* exists and is a folder.
        """
        async with self._errors(path):
            ap = _azure_path_fn(path)
            if not ap:
                return True
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    props = await self._fs.get_directory_client(ap).get_directory_properties()
                    # On HNS, get_directory_properties() succeeds for both files and
                    # directories.  A real HNS directory has hdi_isfolder=true in its
                    # metadata; a regular file does not (BUG-203).
                    meta = getattr(props, "metadata", None) or {}
                    return bool(meta.get("hdi_isfolder"))
                except Exception:  # noqa: BLE001
                    return False
            else:
                prefix = ap.rstrip("/") + "/"
                blobs = self._cc.list_blobs(name_starts_with=prefix, results_per_page=1)
                return bool([b async for b in blobs][:1])

    async def read(self, path: str) -> AsyncIterator[bytes]:
        """Open a file for reading and return an async iterator of byte chunks.

        Args:
            path: Backend-relative key.

        Returns:
            An async iterator yielding byte chunks.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If ``path`` names a directory (HNS accounts only).
        """
        try:
            bc = self._blob_client(path)
            downloader = await bc.download_blob(max_concurrency=self._max_concurrency)
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                # BE-021: await download_blob() makes the initial HTTP request,
                # so downloader.properties is populated before streaming starts.
                # Check hdi_isfolder before yielding any bytes.
                blob_meta = getattr(getattr(downloader, "properties", None), "metadata", None) or {}
                if blob_meta.get("hdi_isfolder"):
                    # Close the response before raising; the chunks() iterator
                    # never runs so the underlying HTTP body would otherwise
                    # leak the connection back to the pool unclosed.
                    with contextlib.suppress(Exception):
                        close = getattr(downloader, "close", None)
                        if close is not None:
                            res = close()
                            if inspect.isawaitable(res):
                                await res
                    raise InvalidPath(f"Cannot read — '{path}' is a directory", path=path, backend=self.name)
            async for chunk in downloader.chunks():
                yield chunk
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, path, self.name) from None

    async def read_bytes(self, path: str) -> bytes:
        """Read the full content of a file as bytes.

        Args:
            path: Backend-relative key.

        Returns:
            The file content.

        Raises:
            NotFound: If the file does not exist.
            InvalidPath: If ``path`` names a directory (HNS accounts only).
        """
        async with self._errors(path):
            bc = self._blob_client(path)
            downloader = await bc.download_blob(max_concurrency=self._max_concurrency)
            data = bytes(await downloader.readall())
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                # BE-021: file-API operations on an HNS directory path must
                # raise InvalidPath. download_blob() succeeds (directory marker
                # is a 0-byte blob), so inspect response metadata post-download.
                blob_meta = getattr(getattr(downloader, "properties", None), "metadata", None) or {}
                if blob_meta.get("hdi_isfolder"):
                    raise InvalidPath(f"Cannot read — '{path}' is a directory", path=path, backend=self.name)
            return data

    async def write(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content to a file.

        Args:
            path: Backend-relative key.
            content: Data to write (bytes or async iterator of bytes).
            overwrite: If ``False``, raise if file already exists.
            metadata: Optional user-defined string metadata.

        Returns:
            ``WriteResult`` with native Azure fields (``etag``, ``last_modified``,
            etc.) populated from the SDK upload response.

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
            InvalidPath: If ``path`` names a directory.
        """
        await self._maybe_check_no_file_ancestor(path)
        async with self._errors(path):
            bc = self._blob_client(path)
            if await self._ensure_hns():
                try:
                    props = await bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(
                            f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name
                        )
                    if not overwrite:
                        raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except (InvalidPath, AlreadyExists):
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist, proceed
            elif not overwrite:
                try:
                    await bc.get_blob_properties()
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
                except AlreadyExists:
                    raise
                except ResourceNotFoundError:
                    pass  # Blob doesn't exist, proceed
            # BUG-165: pass async iter straight to upload_blob — the SDK streams
            # AsyncIterable[bytes] in bounded memory; materializing would break
            # the streaming promise (SIO-003/ASYNC-021) for large payloads.
            # Size is tracked via a counting passthrough generator for async iter.
            if isinstance(content, bytes):
                size = len(content)
                resp = await bc.upload_blob(
                    content, overwrite=True, max_concurrency=self._max_concurrency, metadata=metadata or None
                )
            else:
                size_ref = [0]

                async def _count_and_pass(src: AsyncWritableContent) -> AsyncIterator[bytes]:
                    async for chunk in src:  # type: ignore[union-attr]
                        size_ref[0] += len(chunk)
                        yield chunk

                resp = await bc.upload_blob(
                    _count_and_pass(content),
                    overwrite=True,
                    max_concurrency=self._max_concurrency,
                    metadata=metadata or None,
                )
                size = size_ref[0]
            return _build_azure_write_result(path, size, resp if isinstance(resp, dict) else {}, metadata)

    async def write_atomic(
        self,
        path: str,
        content: AsyncWritableContent,
        *,
        overwrite: bool = False,
        metadata: Mapping[str, str] | None = None,
    ) -> WriteResult:
        """Write content atomically via temp file + rename.

        For non-HNS accounts, direct upload is atomic (PUT semantics).
        For HNS accounts, write to temp file via DFS then atomic rename.

        Args:
            path: Backend-relative key.
            content: Data to write.
            overwrite: If ``False``, raise if file already exists.
            metadata: Optional user-defined string metadata.

        Returns:
            ``WriteResult`` with native Azure fields populated from the SDK
            response (non-HNS) or from ``get_file_properties()`` after rename
            (HNS).

        Raises:
            AlreadyExists: If the file exists and ``overwrite`` is ``False``.
            InvalidPath: If ``path`` names a directory.
        """
        if not await self._ensure_hns():
            # non-HNS: direct upload is atomic (PUT semantics)
            return await self.write(path, content, overwrite=overwrite, metadata=metadata)

        # HNS: write to temp file via DFS, then atomic rename
        async with self._errors(path):
            bc = self._blob_client(path)
            try:
                props = await bc.get_blob_properties()
                blob_meta = getattr(props, "metadata", None) or {}
                if blob_meta.get("hdi_isfolder"):
                    raise InvalidPath(f"Cannot write — '{path}' exists as a directory", path=path, backend=self.name)
                if not overwrite:
                    raise AlreadyExists(f"File already exists: {path}", path=path, backend=self.name)
            except (InvalidPath, AlreadyExists):
                raise
            except ResourceNotFoundError:
                pass  # Blob doesn't exist yet; proceed to temp upload + atomic rename

            ap = _azure_path_fn(path)
            basename = ap.rsplit("/", 1)[-1] if "/" in ap else ap
            parent = ap.rsplit("/", 1)[0] if "/" in ap else ""
            tmp_name = f".~tmp.{basename}.{uuid.uuid4().hex[:8]}"
            tmp_path = f"{parent}/{tmp_name}" if parent else tmp_name

            # DFS flush_data requires position=<total bytes> (BUG-194).
            # upload_data passes length=None for async generators, so the SDK
            # omits the required query parameter on real ADLS Gen2
            # (MissingRequiredQueryParameter).
            #
            # Bytes: upload_data resolves length via len(); no extra protocol.
            # AsyncIterator: drive the DFS append protocol directly —
            # create_file, then append_data per chunk (tracking cumulative
            # position), then flush_data with the final byte count.  One chunk
            # at a time; memory is bounded to a single chunk (SIO-003,
            # ASYNC-021).
            tmp_fc = self._fs.get_file_client(tmp_path)
            new_name = f"{self._container}/{ap}"
            size: int

            if isinstance(content, bytes):
                size = len(content)
                try:
                    await tmp_fc.upload_data(
                        content,
                        overwrite=True,
                        max_concurrency=self._max_concurrency,
                        metadata=metadata or None,
                    )
                    final_fc = await tmp_fc.rename_file(new_name)
                except Exception:
                    with contextlib.suppress(Exception):
                        await tmp_fc.delete_file()
                    raise
            else:
                try:
                    # No per-chunk _AZURE_BLOCK_SIZE cap here (unlike sync
                    # write_atomic): the caller already emits the chunk
                    # boundaries via AsyncIterable[bytes]. Sync wraps a
                    # synchronous BinaryIO so it owns the .read(N) call;
                    # async hands that responsibility to the producer.
                    await tmp_fc.create_file(metadata=metadata or None)
                    position = 0
                    async for chunk in content:
                        chunk_len = len(chunk)
                        await tmp_fc.append_data(chunk, offset=position, length=chunk_len)
                        position += chunk_len
                    await tmp_fc.flush_data(position)
                    size = position
                    final_fc = await tmp_fc.rename_file(new_name)
                except Exception:
                    with contextlib.suppress(Exception):
                        await tmp_fc.delete_file()
                    raise

            # BUG-173 / BUG-196: the rename above has already committed the write.
            # A post-commit read failure (network blip, eventual consistency,
            # permissions) must not surface as a write failure -- retrying would
            # raise AlreadyExists (overwrite=False) or silently double-write.
            # Fall back to a WriteResult without rich fields (mirrors sync sibling).
            props_dict: dict[str, Any] = {}
            try:
                props = await final_fc.get_file_properties()
                props_dict = {
                    "etag": getattr(props, "etag", None),
                    "last_modified": getattr(props, "last_modified", None),
                }
            except Exception as exc:  # noqa: BLE001 -- post-commit read fallback
                log.warning(
                    "HNS write_atomic committed to %s but post-rename get_file_properties failed: %s",
                    path,
                    exc,
                )
            return _build_azure_write_result(path, size, props_dict, metadata)

    async def delete(self, path: str, *, missing_ok: bool = False) -> None:
        """Delete a file.

        Args:
            path: Backend-relative key.
            missing_ok: If ``True``, do not raise when the file is absent.

        Raises:
            NotFound: If the file is missing and ``missing_ok`` is ``False``.
            InvalidPath: If ``path`` names a directory (HNS accounts only).
        """
        async with self._errors(path):
            bc = self._blob_client(path)
            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    props = await bc.get_blob_properties()
                    blob_meta = getattr(props, "metadata", None) or {}
                    if blob_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Cannot delete — '{path}' is a directory", path=path, backend=self.name)
                except InvalidPath:
                    raise
                except Exception:  # noqa: BLE001
                    # Probe failure (ResourceNotFoundError, network blip, etc.)
                    # is non-fatal here — let delete_blob() surface the real
                    # error so the missing_ok=True path stays intact.
                    pass
            try:
                await bc.delete_blob()
            except Exception as exc:  # noqa: BLE001
                mapped = classify_azure_error(exc, path, self.name)
                if isinstance(mapped, NotFound):
                    if not missing_ok:
                        raise mapped from None
                    return
                # BE-021: HNS non-empty directory yields DirectoryIsNotEmpty (409).
                # The file-API delete() must raise InvalidPath, not AlreadyExists.
                if isinstance(exc, HttpResponseError) and getattr(exc, "error_code", None) == "DirectoryIsNotEmpty":
                    raise InvalidPath(
                        f"Cannot delete — '{path}' is a directory", path=path, backend=self.name
                    ) from None
                raise mapped from None  # pragma: no cover

    async def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        """Delete a folder.

        Args:
            path: Backend-relative key.
            recursive: If ``True``, delete all contents first.
            missing_ok: If ``True``, do not raise when absent.

        Raises:
            NotFound: If the folder is missing and ``missing_ok`` is ``False``.
            InvalidPath: If ``path`` names a file (use ``delete`` instead).
            DirectoryNotEmpty: If non-empty and ``recursive`` is ``False``.
        """
        async with self._errors(path):
            ap = _azure_path_fn(path)

            if await self._ensure_hns():  # pragma: no cover -- HNS only
                dc = self._fs.get_directory_client(ap)
                try:
                    props = await dc.get_directory_properties()
                except Exception as exc:  # noqa: BLE001
                    mapped = classify_azure_error(exc, path, self.name)
                    if isinstance(mapped, NotFound):
                        if not missing_ok:
                            raise mapped from None
                        return
                    raise mapped from None

                # BUG-198: on real ADLS Gen2, get_directory_properties() succeeds
                # for file paths too (resource_type=file, no hdi_isfolder in metadata).
                # Detect the type mismatch early and raise InvalidPath.
                props_meta = getattr(props, "metadata", None) or {}
                if not props_meta.get("hdi_isfolder"):
                    raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)

                if not recursive:
                    children = []
                    async for p in self._fs.get_paths(path=ap, recursive=False, max_results=1):
                        children.append(p)
                    if children:
                        raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
                await dc.delete_directory()
            else:
                # non-HNS: virtual folders via blob prefix
                prefix = ap.rstrip("/") + "/"
                first = []
                async for blob in self._cc.list_blobs(name_starts_with=prefix, results_per_page=1):
                    first.append(blob)
                    break
                if first:
                    if not recursive:
                        raise DirectoryNotEmpty(f"Folder not empty: {path}", path=path, backend=self.name)
                    async for blob in self._cc.list_blobs(name_starts_with=prefix):
                        await self._cc.get_blob_client(blob.name).delete_blob()
                elif not missing_ok:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> AsyncIterator[FileInfo]:
        """List files under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.
            recursive: If ``True``, include files in all subdirectories.
            max_depth: Optional maximum folder depth to traverse.

        Returns:
            An async iterator of ``FileInfo`` objects.
        """
        try:
            ap = _azure_path_fn(path)
            prefix = (ap.rstrip("/") + "/") if ap else ""

            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=ap or "/", recursive=recursive)
                    async for p in paths:
                        if not getattr(p, "is_directory", False):
                            if recursive and max_depth is not None:
                                rel = str(p.name)[len(prefix) :]
                                depth = rel.count("/")
                                if depth > max_depth:
                                    continue
                            yield props_to_fileinfo(p, str(p.name))
                except Exception as exc:  # noqa: BLE001
                    mapped = classify_azure_error(exc, path, self.name)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            elif recursive:
                async for blob in self._cc.list_blobs(name_starts_with=prefix):
                    if max_depth is not None:
                        rel = blob.name[len(prefix) :]
                        depth = rel.count("/")
                        if depth > max_depth:
                            continue
                    yield props_to_fileinfo(blob, blob.name)
            else:
                async for item in self._cc.walk_blobs(name_starts_with=prefix):
                    if not getattr(item, "prefix", None):
                        yield props_to_fileinfo(item, item.name)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, path, self.name) from None

    async def list_folders(self, path: str) -> AsyncIterator[FolderEntry]:
        """List immediate subfolders under ``path``.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FolderEntry`` objects.
        """
        try:
            ap = _azure_path_fn(path)
            prefix = (ap.rstrip("/") + "/") if ap else ""

            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=ap or "/", recursive=False)
                    async for p in paths:
                        if getattr(p, "is_directory", False):
                            rel = str(p.name).rstrip("/")
                            folder_name = rel.rsplit("/", 1)[-1]
                            yield FolderEntry(path=RemotePath(rel), name=folder_name)
                except Exception as exc:  # noqa: BLE001
                    mapped = classify_azure_error(exc, path, self.name)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            else:
                async for item in self._cc.walk_blobs(name_starts_with=prefix):
                    if getattr(item, "prefix", None):
                        rel = self.to_key(item.prefix.rstrip("/"))
                        folder_name = rel.rsplit("/", 1)[-1]
                        yield FolderEntry(path=RemotePath(rel), name=folder_name)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, path, self.name) from None

    async def iter_children(self, path: str) -> AsyncIterator[FileInfo | FolderEntry]:
        """Yield both files and folders under ``path`` in a single pass.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            An async iterator of ``FileInfo`` (files) and ``FolderEntry`` (folders).
        """
        try:
            ap = _azure_path_fn(path)
            prefix = (ap.rstrip("/") + "/") if ap else ""

            if await self._ensure_hns():  # pragma: no cover -- HNS only
                try:
                    paths = self._fs.get_paths(path=ap or "/", recursive=False)
                    async for p in paths:
                        if getattr(p, "is_directory", False):
                            rel = str(p.name).rstrip("/")
                            folder_name = rel.rsplit("/", 1)[-1]
                            yield FolderEntry(path=RemotePath(rel), name=folder_name)
                        else:
                            yield props_to_fileinfo(p, str(p.name))
                except Exception as exc:  # noqa: BLE001
                    mapped = classify_azure_error(exc, path, self.name)
                    if isinstance(mapped, NotFound):
                        return
                    raise mapped from None
            else:
                async for item in self._cc.walk_blobs(name_starts_with=prefix):
                    if getattr(item, "prefix", None):
                        rel = self.to_key(item.prefix.rstrip("/"))
                        folder_name = rel.rsplit("/", 1)[-1]
                        yield FolderEntry(path=RemotePath(rel), name=folder_name)
                    else:
                        yield props_to_fileinfo(item, item.name)
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, path, self.name) from None

    async def glob(self, pattern: str) -> AsyncIterator[FileInfo]:
        """Match files against a glob pattern.

        Args:
            pattern: Glob pattern (e.g., ``"data/*.csv"``, ``"**/*.txt"``).

        Returns:
            An async iterator of matching ``FileInfo`` objects.
        """
        from remote_store._glob import extract_prefix, needs_recursive, pattern_to_regex

        try:
            prefix = extract_prefix(pattern)
            recursive = needs_recursive(pattern)
            compiled = pattern_to_regex(pattern)
            async for info in self.list_files(prefix, recursive=recursive):
                if compiled.match(str(info.path)):
                    yield info
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, pattern, self.name) from None

    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a file.

        Args:
            path: Backend-relative key.

        Returns:
            A ``FileInfo`` with size, modification time, etc.

        Raises:
            InvalidPath: If ``path`` names a directory (HNS: ``hdi_isfolder=true``).
            NotFound: If the file does not exist.
        """
        async with self._errors(path):
            bc = self._blob_client(path)
            props = await bc.get_blob_properties()
            meta = getattr(props, "metadata", None) or {}
            if meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                raise InvalidPath(
                    f"Cannot get file info — '{path}' exists as a directory",
                    path=path,
                    backend=self.name,
                )
            return props_to_fileinfo(props, path)

    async def get_folder_info(self, path: str) -> FolderInfo:
        """Get metadata for a folder.

        Args:
            path: Backend-relative folder key, or ``""`` for the root.

        Returns:
            A ``FolderInfo`` with file count, total size, etc.

        Raises:
            NotFound: If the folder does not exist.
            InvalidPath: If ``path`` names a file (use ``get_file_info`` instead).
        """
        async with self._errors(path):
            ap = _azure_path_fn(path)
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None

            if await self._ensure_hns():  # pragma: no cover -- HNS only
                # DFS get_paths exposes is_directory inline; list_blobs would
                # silently count hdi_isfolder marker blobs as files (BUG-199).
                # BUG-213: skip the per-path probe for the filesystem root —
                # ``get_directory_client("")`` fails on real ADLS Gen2 with
                # "Please specify a file system name and file path", and the
                # root is always a folder (no hdi_isfolder probe needed).
                if ap:
                    dc = self._fs.get_directory_client(ap)
                    dir_props = await dc.get_directory_properties()  # raises if not found
                    # BUG-198: on real ADLS Gen2, get_directory_properties() succeeds
                    # for file paths too.  Detect the type mismatch and raise InvalidPath.
                    dir_meta = getattr(dir_props, "metadata", None) or {}
                    if not dir_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Not a folder: {path}", path=path, backend=self.name)
                async for p in self._fs.get_paths(path=ap or "/", recursive=True):
                    if getattr(p, "is_directory", False):
                        continue
                    file_count += 1
                    # Mirror props_to_fileinfo (_azure_common.py:127) attribute order so
                    # FolderInfo.total_size and FileInfo.size agree for the same path.
                    size = getattr(p, "size", None) or getattr(p, "content_length", 0) or 0
                    total_size += int(size)
                    modified = getattr(p, "last_modified", None)
                    if modified is not None:
                        if modified.tzinfo is None:
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
            else:
                prefix = (ap.rstrip("/") + "/") if ap else ""
                async for blob in self._cc.list_blobs(name_starts_with=prefix):
                    file_count += 1
                    total_size += blob.size or 0
                    modified = blob.last_modified
                    if modified is not None:
                        if modified.tzinfo is None:  # pragma: no cover
                            modified = modified.replace(tzinfo=timezone.utc)
                        if latest_modified is None or modified > latest_modified:
                            latest_modified = modified
                if file_count == 0:
                    raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)

            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    async def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Move or rename a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` or ``dst`` names a directory (HNS only).
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """
        # BE-018 / ASYNC-018: self-move is a no-op (src == dst → Ok), but only
        # for files.  Directory-path inputs must still raise InvalidPath per
        # BE-021 — same contract as the non-self-op path below (line 942-943).
        if src == dst:
            async with self._errors(src):
                src_bc = self._blob_client(src)
                src_props = await src_bc.get_blob_properties()  # raises NotFound if missing
                src_meta = getattr(src_props, "metadata", None) or {}
                if src_meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                    raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)
            return

        async with self._errors(src):
            src_bc = self._blob_client(src)
            src_props = await src_bc.get_blob_properties()  # raises NotFound if missing
            src_meta = getattr(src_props, "metadata", None) or {}
            if src_meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)

            dst_bc = self._blob_client(dst)
            is_hns = await self._ensure_hns()
            if not overwrite:
                try:
                    dst_props = await dst_bc.get_blob_properties()
                    if is_hns:  # pragma: no cover -- HNS only
                        dst_meta = getattr(dst_props, "metadata", None) or {}
                        if dst_meta.get("hdi_isfolder"):
                            raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except (AlreadyExists, InvalidPath):
                    raise
                except ResourceNotFoundError:
                    pass
            elif is_hns:  # pragma: no cover -- HNS only
                # Overwrite=True on HNS still needs a dst probe to reject directory
                # destinations per BE-021. Non-HNS skips this entirely — flat
                # namespace has no `hdi_isfolder` concept, so the extra HEAD
                # round-trip would be pure overhead.
                try:
                    dst_props = await dst_bc.get_blob_properties()
                    dst_meta = getattr(dst_props, "metadata", None) or {}
                    if dst_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                except ResourceNotFoundError:
                    # Destination does not exist yet; this is valid when overwrite=True.
                    pass

            # ASYNC-018 precondition order: src-NotFound (raised above by
            # get_blob_properties) takes priority over dst-file-ancestor
            # (matches LocalBackend.move; ID-211 review).
            await self._maybe_check_no_file_ancestor(dst)
            if is_hns:  # pragma: no cover -- HNS only
                src_fc = self._fs.get_file_client(_azure_path_fn(src))
                new_name = f"{self._container}/{_azure_path_fn(dst)}"
                await src_fc.rename_file(new_name)
            else:
                # Server-side copy + delete.  Same-account copies complete
                # inline; cross-account may be async (matches sync backend).
                await dst_bc.start_copy_from_url(src_bc.url)
                await src_bc.delete_blob()

    async def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        """Copy a file.

        Args:
            src: Backend-relative source key.
            dst: Backend-relative destination key.
            overwrite: If ``True``, replace any existing file at *dst*.

        Raises:
            NotFound: If ``src`` does not exist.
            InvalidPath: If ``src`` or ``dst`` names a directory (HNS only).
            AlreadyExists: If ``dst`` exists and ``overwrite`` is ``False``.
        """
        # BE-019 / ASYNC-019: self-copy is a no-op (src == dst → Ok), but only
        # for files.  Directory-path inputs must still raise InvalidPath per
        # BE-021 — same contract as the non-self-op path below.
        if src == dst:
            async with self._errors(src):
                src_bc = self._blob_client(src)
                src_props = await src_bc.get_blob_properties()  # raises NotFound if missing
                src_meta = getattr(src_props, "metadata", None) or {}
                if src_meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                    raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)
            return

        async with self._errors(src):
            src_bc = self._blob_client(src)
            src_props = await src_bc.get_blob_properties()  # raises NotFound if missing
            src_meta = getattr(src_props, "metadata", None) or {}
            if src_meta.get("hdi_isfolder"):  # pragma: no cover -- HNS only
                raise InvalidPath(f"Source is a directory: {src}", path=src, backend=self.name)

            dst_bc = self._blob_client(dst)
            is_hns = await self._ensure_hns()
            if not overwrite:
                try:
                    dst_props = await dst_bc.get_blob_properties()
                    if is_hns:  # pragma: no cover -- HNS only
                        dst_meta = getattr(dst_props, "metadata", None) or {}
                        if dst_meta.get("hdi_isfolder"):
                            raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                    raise AlreadyExists(f"Destination already exists: {dst}", path=dst, backend=self.name)
                except (AlreadyExists, InvalidPath):
                    raise
                except ResourceNotFoundError:
                    pass
            elif is_hns:  # pragma: no cover -- HNS only
                # Overwrite=True on HNS still needs a dst probe to reject directory
                # destinations per BE-021. Non-HNS skips this entirely — flat
                # namespace has no `hdi_isfolder` concept, so the extra HEAD
                # round-trip would be pure overhead.
                try:
                    dst_props = await dst_bc.get_blob_properties()
                    dst_meta = getattr(dst_props, "metadata", None) or {}
                    if dst_meta.get("hdi_isfolder"):
                        raise InvalidPath(f"Destination is a directory: {dst}", path=dst, backend=self.name)
                except ResourceNotFoundError:
                    # Destination does not exist yet; this is valid when overwrite=True.
                    pass

            # ASYNC-019 precondition order: src-NotFound before dst-file-ancestor (ID-211 review).
            await self._maybe_check_no_file_ancestor(dst)
            await dst_bc.start_copy_from_url(src_bc.url)

    async def aclose(self) -> None:
        """Release all Azure SDK client resources."""
        clients = (self._cc_instance, self._blob_service_instance, self._fs_instance, self._datalake_service_instance)
        for client in clients:
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.close()
        self._cc_instance = None
        self._blob_service_instance = None
        self._fs_instance = None
        self._datalake_service_instance = None
        self._hns_enabled = None
        # Close auto-created async credential (holds aiohttp sessions).
        if self._resolved_credential is not None:
            close = getattr(self._resolved_credential, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()
            self._resolved_credential = None

    def unwrap(self, type_hint: type[T]) -> T:
        """Return the native async FileSystemClient if it matches the requested type.

        Args:
            type_hint: The expected type.

        Returns:
            The native async client instance matching *type_hint*.

        Raises:
            CapabilityNotSupported: If backend cannot provide the requested type.
        """
        from azure.storage.filedatalake.aio import FileSystemClient

        if type_hint is FileSystemClient:
            return self._fs  # type: ignore[no-any-return]
        raise CapabilityNotSupported(
            f"Backend 'async-azure' does not expose native handle of type {type_hint.__name__}. "
            f"Supported: azure.storage.filedatalake.aio.FileSystemClient.",
            capability="unwrap",
            backend=self.name,
        )

    # endregion

    # region: dunder methods

    def _has_open_clients(self) -> bool:
        return any(
            (
                getattr(self, "_cc_instance", None),
                getattr(self, "_blob_service_instance", None),
                getattr(self, "_fs_instance", None),
                getattr(self, "_datalake_service_instance", None),
            )
        )

    def __del__(self) -> None:
        # Guard against interpreter shutdown: module globals may be None.
        # Cannot call async aclose() from __del__, so warn only.
        try:
            if not self._has_open_clients():
                return
        except Exception:  # noqa: BLE001
            return
        try:  # noqa: SIM105 — cannot use contextlib.suppress during shutdown
            self._del_cleanup()
        except Exception:  # noqa: BLE001
            pass

    def _del_cleanup(self) -> None:
        """Emit ResourceWarning; called by __del__ without contextlib."""
        try:
            import warnings

            warnings.warn(
                f"Unclosed {type(self).__name__}. Call .aclose() or use an async context manager.",
                ResourceWarning,
                stacklevel=2,
            )
        except Exception:  # noqa: BLE001
            pass

    def __repr__(self) -> str:
        return (
            f"AsyncAzureBackend(container={self._container!r}, "
            f"account_name={self._account_name!r}, "
            f"account_key={'***' if self._account_key is not None else None!r}, "
            f"sas_token={'***' if self._sas_token is not None else None!r}, "
            f"connection_string={'***' if self._connection_string is not None else None!r}, "
            f"credential={'***' if self._credential is not None else None!r})"
        )

    # endregion

    # region: private helpers

    def _get_credential(self) -> Any:
        """Return cached async credential, creating it on first call."""
        if self._resolved_credential is None:
            from remote_store.backends._azure_common import resolve_credential

            self._resolved_credential = resolve_credential(
                self._credential,
                self._account_key,
                self._sas_token,
                is_async=True,
                backend_name=self.name,
            )
        return self._resolved_credential

    def _blob_client(self, path: str) -> Any:
        """Get an async BlobClient for the given path."""
        return self._cc.get_blob_client(_azure_path_fn(path))

    @asynccontextmanager
    async def _errors(self, path: str = "") -> AsyncIterator[None]:
        """Map Azure SDK exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise classify_azure_error(exc, path, self.name) from None

    # endregion
