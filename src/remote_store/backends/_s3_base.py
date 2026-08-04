"""Shared base class for S3 backends that use s3fs for control-path operations."""

from __future__ import annotations

import abc
import base64
import logging
import os
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from remote_store._backend import Backend
from remote_store._errors import (
    BackendUnavailable,
    NotFound,
    RemoteStoreError,
    _classify_by_message,
    _not_found,
    _permission_denied,
)
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath, is_root
from remote_store.backends._fileinfo import _clean_etag, _name_from_path, _normalize_modified

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._config import RetryPolicy
    from remote_store._resolution import ResolutionPlan

log = logging.getLogger(__name__)

# S3-027: the s3fs directory-listing cache is left off by default. Its DirCache
# never expires (``listings_expiry_time=None``), so a cached listing is
# permanently blind to a cross-writer write; callers opt in explicitly via
# ``client_options['use_listings_cache']``. Named (not inlined) so the FEATURES.md
# read-after-write consistency matrix can drift-guard its "strong listing by
# default" footnote against this value (ID-227).
_DEFAULT_USE_LISTINGS_CACHE = False


def _normalize_endpoint_url(url: str | None) -> str | None:
    """Normalize endpoint URL: bare ``host:port`` becomes ``https://host:port``.

    URLs with an existing ``http://`` or ``https://`` scheme are returned
    unchanged (after stripping whitespace).  Bare hostnames or ``host:port``
    strings are prefixed with ``https://``.
    """
    if url is None:
        return None
    url = url.strip()
    if not url:
        return None
    # Case-insensitive scheme check per RFC 3986 § 3.1
    lower = url[:8].lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return url
    return f"https://{url}"


_S3_CA_ENV_VARS: tuple[str, ...] = ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")


def _resolve_tls_ca_bundle(
    explicit: str | None,
    env_vars: tuple[str, ...] = _S3_CA_ENV_VARS,
) -> str | None:
    """Resolve CA bundle: explicit param > env vars (in order) > None."""
    if explicit is not None:
        return explicit
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            return val
    return None


def _validate_tls_ca_bundle(resolved: str | None) -> None:
    """Validate that the resolved CA bundle path is an existing file."""
    if resolved is not None and not Path(resolved).is_file():
        raise ValueError(f"tls_ca_bundle path does not exist or is not a file: {resolved}")


class _S3Base(Backend):
    """Internal base for S3 backends that share an s3fs control path.

    Subclasses must implement the ``_s3fs`` abstract property plus all
    remaining ``Backend`` abstract methods (read, write, etc.).
    """

    # Set by subclass __init__
    _bucket: str
    _endpoint_url: str | None
    _key: str | None
    _secret: str | None
    _region_name: str | None
    _tls_ca_bundle: str | None
    _client_options: dict[str, Any]
    _retry: RetryPolicy | None
    _reject_write_under_file_ancestor: bool

    # M1 (BK-298): close() is terminal — a use-after-close raises
    # BackendUnavailable rather than silently re-creating the s3fs client.
    close_is_terminal: ClassVar[bool] = True
    # Default until a subclass close() flips it; set as a class attr because
    # _S3Base has no __init__ (subclasses set their own instance state).
    _closed: bool = False

    def _raise_if_closed(self) -> None:
        """Raise ``BackendUnavailable`` if the backend has been closed.

        After ``close()`` every data-plane op reaches s3fs through a lazy
        property; this guard turns a use-after-close into a typed error instead
        of silently re-creating the client.
        """
        if self._closed:
            raise BackendUnavailable(f"{self.name} backend is closed", backend=self.name)

    # region: abstract property

    @property
    @abc.abstractmethod
    def _s3fs(self) -> Any:
        """Return the s3fs ``S3FileSystem`` instance."""

    # endregion

    # region: shared — file-ancestor pre-check (opt-in)

    def _maybe_check_no_file_ancestor(self, path: str) -> None:
        """Run the file-ancestor walk when the opt-in is set.

        Default-off: only callers that constructed the backend with
        ``reject_write_under_file_ancestor=True`` pay the per-write
        HEAD walk. No-slash paths short-circuit in
        ``_check_no_file_ancestor`` itself.

        Shared on ``_S3Base`` rather than duplicated on each subclass
        because the s3fs ``head_object`` closure is identical for
        ``S3Backend`` and ``S3PyArrowBackend`` — the only difference
        was the attribute name used to reach the underlying s3fs
        instance, which the abstract ``_s3fs`` property now unifies.
        """
        if not self._reject_write_under_file_ancestor:
            return
        from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

        from remote_store.backends._flat_ns import _check_no_file_ancestor

        def _head_one(key: str) -> bool:
            # Fail-open on probe failures (404 ClientError, network OSError,
            # botocore-internal BotoCoreError). Programmer errors (TypeError,
            # AttributeError) propagate — they signal an integration bug, not
            # a probe outcome. See ``_flat_ns.py`` module docstring §
            # "Fail-open ``head_one``" for the cross-backend contract.
            try:
                self._s3fs.call_s3("head_object", Bucket=self._bucket, Key=key)
            except (ClientError, BotoCoreError, OSError):
                return False
            return True

        _check_no_file_ancestor(path, head_one=_head_one, backend=self.name)

    # endregion

    # region: shared — wrong-type reclassification (BE-021, BK-324 facet 2)

    def _s3_is_object(self, path: str) -> bool:
        """One ``HeadObject``: ``True`` iff an object exists at exactly *path*.

        Narrower than ``s3fs.exists``, which also answers ``True`` for a bare
        common prefix. The file-shaped operations need the narrow answer so
        that a prefix falls through to the type-mismatch branch instead of
        being mistaken for a file.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        if is_root(path):
            return False  # the root is a folder, never an object
        try:
            self._s3fs.call_s3("head_object", Bucket=self._bucket, Key=path)
        except (FileNotFoundError, ClientError, BotoCoreError, OSError):
            return False
        return True

    def _s3_has_children(self, path: str) -> bool:
        """One ``MaxKeys=1`` listing: ``True`` iff any key lives under ``path/``.

        Goes through ``call_s3`` rather than ``s3fs.ls`` so the answer is never
        served from the fsspec directory cache — a stale ``True`` here would
        turn a legitimate ``NotFound`` into a spurious ``InvalidPath``.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            resp = self._s3fs.call_s3(
                "list_objects_v2",
                Bucket=self._bucket,
                Prefix="" if is_root(path) else f"{path.rstrip('/')}/",
                MaxKeys=1,
            )
        except (FileNotFoundError, ClientError, BotoCoreError, OSError):
            return False
        return bool(resp.get("KeyCount", 0)) or bool(resp.get("CommonPrefixes"))

    def _reject_root_as_file(self, path: str) -> None:
        """Pre-check: the store root is a folder, so a file op on it is a type error.

        Costs no round trip (root-ness is decidable from the string) and keeps
        the root out of the SDK, where a zero-length ``Key`` is rejected at
        parameter validation and surfaces as a transport-shaped error.

        The closed-backend guard outranks this check and so runs first: a
        closed backend refuses before it classifies the path. Otherwise the
        answer would depend on which guard happens to be written first.
        """
        from remote_store.backends._flat_ns import _reject_root_as_file

        self._raise_if_closed()
        _reject_root_as_file(path, self.name)

    def _reject_folder(self, path: str) -> None:
        """Error path: raise ``InvalidPath`` if *path* is a virtual folder.

        Fail-open on probe failures (the closures above swallow their own SDK
        error shapes), so a transient listing failure leaves the operation's
        original error standing rather than replacing it with a transport one.
        """
        from remote_store.backends._flat_ns import _wrong_type_if_folder

        _wrong_type_if_folder(path, has_children=self._s3_has_children, backend=self.name)

    def _reject_file(self, path: str) -> None:
        """Error path: raise ``InvalidPath`` if *path* is an object."""
        from remote_store.backends._flat_ns import _wrong_type_if_file

        _wrong_type_if_file(path, is_object=self._s3_is_object, backend=self.name)

    @contextmanager
    def _s3fs_file_errors(self, path: str) -> Iterator[None]:
        """``_s3fs_errors`` plus wrong-type reclassification of a miss.

        For file-shaped operations whose miss surfaces as a ``NotFound`` from
        the SDK rather than from an explicit pre-check. The prefix probe runs
        only once the mapped error is already ``NotFound``.
        """
        try:
            with self._s3fs_errors(path):
                yield
        except NotFound:
            self._reject_folder(path)
            raise

    # endregion

    # region: path helpers

    def _s3_path(self, path: str) -> str:
        """Build ``bucket/key`` path for s3fs.

        Both spellings of the store root resolve to the bare bucket: S3 names
        the root by the empty key, and passing ``"."`` through would address a
        literal ``./`` prefix that no write ever creates.
        """
        if is_root(path):
            return self._bucket
        return f"{self._bucket}/{path}"

    def to_key(self, native_path: str) -> str:
        prefix = f"{self._bucket}/"
        if native_path.startswith(prefix):
            return native_path[len(prefix) :]
        if native_path == self._bucket:
            # Bare bucket is the root; its key is "" (NPR-005, BK-234).
            return ""
        return native_path

    def resolve(self, path: str) -> ResolutionPlan:
        """Return a ``ResolutionPlan`` with S3-specific details.

        Args:
            path: Backend-relative key.

        Returns:
            Plan with ``kind=self.name`` and ``details`` containing
            ``bucket``, ``object_key``, and ``endpoint_url``.
        """
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

    # endregion

    # region: shared s3fs builder

    def _build_s3fs_kwargs(self) -> dict[str, Any]:
        """Build kwargs for ``s3fs.S3FileSystem(**kwargs)``.

        Routes every botocore ``Config`` option through ``opts['config_kwargs']``
        (a dict) — never through ``client_kwargs['config']``.
        ``s3fs.S3FileSystem.set_session`` already calls
        ``aiobotocore.create_client(..., config=AioConfig(**self.config_kwargs),
        **client_kwargs)``; a parallel ``client_kwargs['config']`` would
        duplicate the ``config=`` keyword and raise ``TypeError`` at first
        I/O.  Caller-supplied ``client_kwargs['config']`` is therefore
        rejected with a clear ``ValueError`` that points to the supported
        channel — silent rewriting hid the underlying defect twice in
        prior releases.

        Retry-policy precedence: when ``retry=RetryPolicy(...)`` is passed,
        the ``retries`` entry in ``config_kwargs`` is replaced wholesale
        with ``{"max_attempts": rp.max_attempts, "mode": "standard"}``
        (plain dict assignment, not a field-level merge).  Caller-supplied
        non-``max_attempts`` keys (e.g. ``mode="adaptive"``) are dropped;
        a ``log.warning`` fires when this happens.  Pass
        ``client_options={'config_kwargs': {'retries': {...}}}`` alone to
        keep caller-supplied retry knobs.
        """
        import copy

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

        if "config" in (opts.get("client_kwargs") or {}):
            raise ValueError(
                "client_options['client_kwargs']['config'] is not supported: "
                "s3fs.S3FileSystem.set_session always passes "
                "config=AioConfig(**self.config_kwargs) to "
                "aiobotocore.create_client(), so a parallel "
                "client_kwargs['config'] duplicates the keyword and raises "
                "TypeError. Pass the same options as a dict via "
                "client_options['config_kwargs'] (see spec S3-026). "
                "If you need a botocore Config setting that does not map "
                "to a config_kwargs key, please open an issue."
            )

        config_kwargs: dict[str, Any] = dict(opts.pop("config_kwargs", None) or {})

        if self._retry is not None:
            rp = self._retry
            if rp.backoff_base != 1.0 or rp.backoff_max != 60.0 or rp.jitter != 1.0 or rp.timeout is not None:
                log.debug(
                    "%s retry: backoff_base, backoff_max, jitter, timeout are not "
                    "mappable to botocore; only max_attempts is used",
                    self.name,
                )
            caller_retries = config_kwargs.get("retries")
            if caller_retries:
                dropped = {k: v for k, v in caller_retries.items() if k != "max_attempts"}
                if dropped:
                    log.warning(
                        "%s: retry=RetryPolicy(...) replaced caller-supplied "
                        "config_kwargs['retries'] entirely; dropped keys: %s. "
                        "Pass only one of retry=/config_kwargs['retries'] to keep both.",
                        self.name,
                        sorted(dropped.keys()),
                    )
            config_kwargs["retries"] = {"max_attempts": rp.max_attempts, "mode": "standard"}

        if config_kwargs:
            opts["config_kwargs"] = config_kwargs

        if self._tls_ca_bundle is not None:
            client_kwargs = opts.setdefault("client_kwargs", {})
            client_kwargs.setdefault("verify", self._tls_ca_bundle)
        opts.setdefault("anon", False)
        # S3-027: default the s3fs directory-listing cache off (see
        # _DEFAULT_USE_LISTINGS_CACHE); setdefault keeps any caller-supplied
        # client_options['use_listings_cache'] (opt-in caching).
        opts.setdefault("use_listings_cache", _DEFAULT_USE_LISTINGS_CACHE)
        # BK-306: opt out of fsspec's process-global instance cache so each
        # backend owns its own S3FileSystem. Without this, close() cannot
        # deterministically release the aiobotocore session — the cached
        # instance survives in fsspec's registry and a new backend with the
        # same args silently reuses the (closed) session. setdefault keeps a
        # caller's explicit client_options['skip_instance_cache'] choice.
        opts.setdefault("skip_instance_cache", True)
        return opts

    # endregion

    # region: shared listing methods

    def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[FileInfo]:
        """Yield files under *path*, one ``FileInfo`` at a time.

        Lazily pages the bucket listing (``ListObjectsV2`` via s3fs); a missing
        prefix yields nothing. ``recursive`` walks the virtual tree one prefix
        listing at a time (``max_depth`` bounds the descent). Listings are
        strongly consistent by default — the s3fs directory cache is left off
        (``use_listings_cache=False``), so a listing reflects a just-completed
        write; opting into the cache via ``client_options`` trades this for a
        never-expiring cache that can stay blind to a cross-writer change.

        Raises:
            PermissionDenied: If the credentials lack access, surfaced during
                iteration.
            BackendUnavailable: On a transport or service failure, surfaced during
                iteration.
        """
        try:
            s3_path = self._s3_path(path)
            if recursive:
                queue: deque[tuple[str, int]] = deque([(s3_path, 0)])
                while queue:
                    current, depth = queue.popleft()
                    try:
                        dir_entries: list[dict[str, Any]] = self._s3fs.ls(current, detail=True)
                    except FileNotFoundError:
                        continue  # directory deleted mid-traversal
                    for info in dir_entries:
                        if info.get("type") == "file":
                            rel = self.to_key(info["name"])
                            yield self._info_to_fileinfo(info, rel)
                        elif info.get("type") == "directory":
                            if max_depth is None or depth < max_depth:
                                queue.append((info["name"], depth + 1))
            else:
                entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
                for info in entries:
                    if info.get("type") == "file":
                        rel = self.to_key(info["name"])
                        yield self._info_to_fileinfo(info, rel)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        """Yield immediate subfolders of *path* as ``FolderEntry`` records.

        One delimiter-scoped ``ListObjectsV2`` (via s3fs); a missing prefix
        yields nothing. Listing consistency matches ``list_files`` — strong by
        default, opt-in cache can serve stale.

        Raises:
            PermissionDenied: If the credentials lack access, surfaced during
                iteration.
            BackendUnavailable: On a transport or service failure, surfaced during
                iteration.
        """
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
            for info in entries:
                if info.get("type") == "directory":
                    rel = self.to_key(info["name"].rstrip("/"))
                    folder_name = rel.rsplit("/", 1)[-1]
                    yield FolderEntry(path=RemotePath(rel), name=folder_name)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def iter_children(self, path: str) -> Iterator[FileInfo | FolderEntry]:
        """Yield the immediate files and folders under *path* in one listing.

        Overrides the base two-pass default with a single delimiter-scoped
        ``ListObjectsV2``, yielding ``FileInfo`` for files and ``FolderEntry``
        for common prefixes. A missing prefix yields nothing.

        Raises:
            PermissionDenied: If the credentials lack access, surfaced during
                iteration.
            BackendUnavailable: On a transport or service failure, surfaced during
                iteration.
        """
        try:
            s3_path = self._s3_path(path)
            entries: list[dict[str, Any]] = self._s3fs.ls(s3_path, detail=True)
            for info in entries:
                if info.get("type") == "file":
                    rel = self.to_key(info["name"])
                    yield self._info_to_fileinfo(info, rel)
                elif info.get("type") == "directory":
                    rel = self.to_key(info["name"].rstrip("/"))
                    folder_name = rel.rsplit("/", 1)[-1]
                    yield FolderEntry(path=RemotePath(rel), name=folder_name)
        except RemoteStoreError:  # pragma: no cover -- defensive
            raise
        except FileNotFoundError:  # pragma: no cover -- s3fs returns empty for missing prefixes
            return
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # pragma: no cover -- defensive  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def glob(self, pattern: str) -> Iterator[FileInfo]:
        """Yield files whose key matches the glob *pattern*.

        Narrows to the pattern's literal prefix, lists that subtree (recursively
        when the pattern needs it), and applies the full glob regex to each key.
        Cost tracks the size of the narrowed listing.

        Raises:
            PermissionDenied: If the credentials lack access, surfaced during
                iteration.
            BackendUnavailable: On a transport or service failure, surfaced during
                iteration.
        """
        from remote_store._glob import extract_prefix, needs_recursive, pattern_to_regex

        prefix = extract_prefix(pattern)
        recursive = needs_recursive(pattern)
        compiled = pattern_to_regex(pattern)
        for info in self.list_files(prefix, recursive=recursive):
            if compiled.match(str(info.path)):
                yield info

    # endregion

    # region: shared metadata methods

    def get_folder_info(self, path: str) -> FolderInfo:
        """Return aggregate metadata for the virtual folder *path*.

        S3 folders are prefixes, not stored objects, so file count, total size,
        and latest modification time are gathered by walking the whole subtree
        listing — cost scales with the number of descendants.

        Raises:
            NotFound: If no object exists under *path*.
            PermissionDenied: If the credentials lack access.
            BackendUnavailable: On a transport or service failure.
        """
        # S3 folders are virtual (prefix-based).  An empty folder is simply a
        # prefix with no objects, so exists() already returns False for truly
        # non-existent prefixes.
        with self._s3fs_errors(path):
            s3_path = self._s3_path(path)
            if not is_root(path) and not self._s3_has_children(path):
                # BE-017/BE-021: an object at *path* is a type mismatch, not a
                # missing folder. The root has no object form, so it skips both
                # checks and always aggregates (BE-029).
                self._reject_file(path)
                raise NotFound(f"Folder not found: {path}", path=path, backend=self.name)
            file_count = 0
            total_size = 0
            latest_modified: datetime | None = None
            queue: deque[str] = deque([s3_path])
            while queue:
                current = queue.popleft()
                try:
                    entries: list[dict[str, Any]] = self._s3fs.ls(current, detail=True)
                except FileNotFoundError:
                    continue  # directory deleted mid-traversal
                for info in entries:
                    if info.get("type") == "directory":
                        queue.append(info["name"])
                    elif info.get("type") == "file":
                        file_count += 1
                        total_size += info.get("size", 0) or 0
                        modified = info.get("LastModified", info.get("last_modified"))
                        if isinstance(modified, str):  # pragma: no cover -- moto returns datetime
                            modified = datetime.fromisoformat(modified)
                        if modified is not None:
                            if modified.tzinfo is None:  # pragma: no cover -- moto includes tzinfo
                                modified = modified.replace(tzinfo=timezone.utc)
                            if latest_modified is None or modified > latest_modified:
                                latest_modified = modified
            return FolderInfo(
                path=RemotePath.from_backend_path(path),
                file_count=file_count,
                total_size=total_size,
                modified_at=latest_modified,
            )

    # endregion

    # region: shared error handling

    @contextmanager
    def _s3fs_errors(self, path: str = "") -> Iterator[None]:
        """Map s3fs/botocore exceptions to remote_store errors."""
        try:
            yield
        except RemoteStoreError:
            raise
        except FileNotFoundError:
            raise _not_found(path, self.name) from None
        except PermissionError:  # pragma: no cover -- moto doesn't raise PermissionError
            raise _permission_denied(path, self.name) from None
        except Exception as exc:  # noqa: BLE001
            raise self._classify_error(exc, path) from None

    def _classify_error(self, exc: Exception, path: str) -> RemoteStoreError:
        """Classify an unknown exception into a remote_store error type.

        Uses the shared heuristic fallback.  Subclasses may override to
        check SDK-specific exception types first.
        """
        return _classify_by_message(exc, path, self.name)

    # endregion

    # region: shared FileInfo construction

    def _info_to_fileinfo(self, info: dict[str, Any], path: str) -> FileInfo:
        """Convert an s3fs info dict to a ``FileInfo``.

        ETag extraction is delegated to ``_extract_etag()`` so subclasses
        can suppress or customise it.
        """
        name = _name_from_path(path)
        size = info.get("size", info.get("Size", 0)) or 0
        modified = _normalize_modified(info.get("LastModified", info.get("last_modified")))
        etag = self._extract_etag(info)
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
            etag=etag,
        )

    def _extract_etag(self, info: dict[str, Any]) -> str | None:
        """Extract and clean the ETag from an s3fs info dict.

        The base class defaults to extracting ETag because that is the
        common case (``S3Backend`` and any future s3fs-based backend).
        ``S3PyArrowBackend`` overrides to return ``None`` because its
        read path does not use s3fs metadata.
        """
        raw = info.get("ETag") or info.get("etag")
        return _clean_etag(raw)

    # endregion

    # region: shared HeadObject helpers

    # S3-024: algorithm name → HeadObject response key for checksums
    _CHECKSUM_ALGO_TO_RESPONSE_KEY: dict[str, str] = {
        "sha256": "ChecksumSHA256",
        "sha1": "ChecksumSHA1",
        "crc32": "ChecksumCRC32",
        "crc32c": "ChecksumCRC32C",
    }

    def _head_to_fileinfo(self, raw: dict[str, Any], path: str) -> FileInfo:
        """Convert a raw boto3 HeadObject response to a FileInfo.

        Expects a response obtained with ``ChecksumMode="ENABLED"`` so that
        checksum fields (``ChecksumSHA256``, etc.) are included when present.
        """
        name = _name_from_path(path)
        size = raw.get("ContentLength", 0) or 0
        modified = _normalize_modified(raw.get("LastModified"))
        etag = _clean_etag(raw.get("ETag"))
        digest = self._digest_from_head_response(raw)
        raw_meta = raw.get("Metadata") or {}
        user_meta: dict[str, str] | None = dict(raw_meta) if raw_meta else None
        return FileInfo(
            path=RemotePath(path),
            name=name,
            size=int(size),
            modified_at=modified,
            etag=etag,
            digest=digest,
            metadata=user_meta,
        )

    def _digest_from_head_response(self, raw: dict[str, Any]) -> ContentDigest | None:
        """Extract a ContentDigest from a HeadObject response with ChecksumMode=ENABLED.

        Iterates the known checksum response keys and returns the first one found.
        Returns None when no checksum key is present in the response.

        Note: Amazon S3 automatically computes and stores CRC32 checksums for objects
        created since late 2022, so ``ContentDigest`` may be returned even for objects
        uploaded without an explicit checksum algorithm.
        """
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
