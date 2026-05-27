"""Dafny-compiled MemoryBackend adapter — conformance oracle.

Thin wrapper that bridges Dafny types (``Seq[CodePoint]``, ``Map``,
``Result``) to the Python ``Backend`` ABC.  All behavioral logic lives in
the verified Dafny spec — this module does only type marshaling.

**Principle**: the compiled oracle is correct by construction (verified by
Dafny, 0 errors).  If the oracle fails a conformance test, the *test* has a
bug — not the oracle.  See ``sdd/formal/README.md`` § Compiled Oracle.

Root path translation: the Python Backend ABC uses ``""`` for root, but
Dafny's ``Path`` type requires non-empty strings.  The Dafny spec models
root as ``"."`` (seeded as DirEntry in the constructor).  Translation
happens once in ``_str_to_dafny`` — no per-method root guards needed.
"""

from __future__ import annotations

import contextlib
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store._models import ContentDigest, FileInfo, FolderEntry, FolderInfo, WriteResult
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

# ---------------------------------------------------------------------------
# Import the compiled Dafny module
# ---------------------------------------------------------------------------
_DAFNY_PY_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "sdd" / "formal" / "MemoryBackend-py")
if _DAFNY_PY_DIR not in sys.path:
    sys.path.insert(0, _DAFNY_PY_DIR)

import _dafny  # noqa: E402
import module_ as _dafny_module  # noqa: E402
from module_ import Option_None, Option_Some  # noqa: E402

# ---------------------------------------------------------------------------
# Type marshaling helpers
# ---------------------------------------------------------------------------

_BACKEND_NAME = "dafny-oracle"
_ORACLE_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB, Capability.LAZY_READ})


def _str_to_dafny(s: str) -> _dafny.Seq:
    """Convert Python str to Dafny Seq[CodePoint].  Maps root "" → "."."""
    path = s if (s and s != ".") else "."
    return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, path))


def _dafny_to_str(seq: _dafny.Seq) -> str:
    return "".join(str(cp) for cp in seq)


def _bytes_to_dafny(data: bytes) -> _dafny.Seq:
    return _dafny.Seq(list(data))


def _dafny_to_bytes(seq: _dafny.Seq) -> bytes:
    return bytes(seq)


def _filename(path: str) -> str:
    return path.rsplit("/", 1)[1] if "/" in path else path


_ERR_DISPATCH: dict[str, type[Exception]] = {
    "is_NotFound": NotFound,
    "is_AlreadyExists": AlreadyExists,
    "is_InvalidPath": InvalidPath,
    "is_DirectoryNotEmpty": DirectoryNotEmpty,
}


def _raise_if_err(result: object) -> object:
    """Convert Dafny Result_Err to remote_store exceptions, return Ok value."""
    if result.is_Err:  # type: ignore[union-attr]
        err = result.error  # type: ignore[union-attr]
        path_str = _dafny_to_str(err.path) if hasattr(err, "path") else ""
        for attr, exc_cls in _ERR_DISPATCH.items():
            if getattr(err, attr):
                raise exc_cls(path=path_str, backend=_BACKEND_NAME)
        if err.is_CapabilityNotSupported:
            raise CapabilityNotSupported(capability=_dafny_to_str(err.capability), backend=_BACKEND_NAME)
        if err.is_BackendUnavailable:
            raise NotFound(message="Backend unavailable", backend=_BACKEND_NAME)
    return result.value  # type: ignore[union-attr]


def _dafny_ts_to_dt(opt: object, fallback: datetime) -> datetime:
    """Lift a Dafny ``Option<int>`` timestamp to a Python UTC datetime.

    Falls back to ``fallback`` when the spec returns ``None`` (the
    non-declaring ``MemoryBackendMinimal`` branch) so that ``FileInfo``
    still carries a non-None ``modified_at`` as the Python model requires.
    """
    if opt.is_Some:  # type: ignore[union-attr]
        return datetime.fromtimestamp(int(opt.value), tz=timezone.utc)  # type: ignore[union-attr]
    return fallback


def _to_file_info(dafny_fi: object, fallback_now: datetime) -> FileInfo:
    meta = None
    if dafny_fi.metadata.is_Some:  # type: ignore[union-attr]
        meta = {_dafny_to_str(k): _dafny_to_str(v) for k, v in dict.items(dafny_fi.metadata.value)}  # type: ignore[union-attr]
    return FileInfo(
        path=RemotePath(_dafny_to_str(dafny_fi.path)),  # type: ignore[union-attr]
        name=_filename(_dafny_to_str(dafny_fi.path)),  # type: ignore[union-attr]
        size=int(dafny_fi.size),  # type: ignore[union-attr]
        modified_at=_dafny_ts_to_dt(dafny_fi.last__modified, fallback_now),  # type: ignore[union-attr]
        metadata=meta,
    )


def _to_folder_entry(path_str: str) -> FolderEntry:
    return FolderEntry(path=RemotePath(path_str), name=_filename(path_str))


def _metadata_to_dafny(metadata: dict[str, str] | None) -> object:
    if metadata is None:
        return Option_None()
    return Option_Some(_dafny.Map({_str_to_dafny(k): _str_to_dafny(v) for k, v in metadata.items()}))


def _dafny_write_source(src: object) -> str:
    if src.is_NativeSource:  # type: ignore[union-attr]
        return "native"
    if src.is_SidecarSource:  # type: ignore[union-attr]
        return "sidecar"
    if src.is_BasicSource:  # type: ignore[union-attr]
        return "basic"
    raise AssertionError(f"unknown Dafny WriteSource variant: {src}")


def _dafny_wr_to_python(path_str: str, dwr: object) -> WriteResult:
    meta = None
    if dwr.metadata.is_Some:  # type: ignore[union-attr]
        meta = {_dafny_to_str(k): _dafny_to_str(v) for k, v in dict.items(dwr.metadata.value)}  # type: ignore[union-attr]
    digest = None
    if dwr.digest.is_Some:  # type: ignore[union-attr]
        cd = dwr.digest.value  # type: ignore[union-attr]
        digest = ContentDigest(algorithm=_dafny_to_str(cd.kind), value=_dafny_to_str(cd.value))
    etag = _dafny_to_str(dwr.etag.value) if dwr.etag.is_Some else None  # type: ignore[union-attr]
    version_id = _dafny_to_str(dwr.version__id.value) if dwr.version__id.is_Some else None  # type: ignore[union-attr]
    last_modified = (
        datetime.fromtimestamp(int(dwr.last__modified.value), tz=timezone.utc)  # type: ignore[union-attr]
        if dwr.last__modified.is_Some  # type: ignore[union-attr]
        else None
    )
    return WriteResult(
        path=RemotePath(path_str),
        size=int(dwr.size),  # type: ignore[union-attr]
        source=_dafny_write_source(dwr.source),  # type: ignore[union-attr]
        digest=digest,
        etag=etag,
        version_id=version_id,
        last_modified=last_modified,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# DafnyOracleBackend — pure type-marshaling wrapper
# ---------------------------------------------------------------------------


class DafnyOracleBackend(Backend):
    """Backend wrapping the compiled Dafny MemoryBackend (Dafny-verified, 0 errors).

    This adapter contains zero behavioral logic — only type conversions
    between Python and Dafny types.  Root is modeled as "." in Dafny
    (seeded in the constructor); ``_str_to_dafny`` translates "" → "."
    at the single entry point.
    """

    CAPABILITIES: ClassVar[CapabilitySet] = _ORACLE_CAPABILITIES

    def __init__(self) -> None:
        self._mb = _dafny_module.MemoryBackend()
        self._mb.ctor__()

    @property
    def name(self) -> str:
        return _BACKEND_NAME

    @property
    def capabilities(self) -> CapabilitySet:
        return _ORACLE_CAPABILITIES

    # -- Predicates (bool results, no model conversion) -------------------------

    def exists(self, path: str) -> bool:
        return bool(_raise_if_err(self._mb.Exists(_str_to_dafny(path))))

    def is_file(self, path: str) -> bool:
        return bool(_raise_if_err(self._mb.IsFileMethod(_str_to_dafny(path))))

    def is_folder(self, path: str) -> bool:
        return bool(_raise_if_err(self._mb.IsFolderMethod(_str_to_dafny(path))))

    # -- Type marshaling: bytes <-> Dafny Seq, str <-> Seq[CodePoint] ----------

    def read(self, path: str) -> io.BytesIO:
        content = _raise_if_err(self._mb.Read(_str_to_dafny(path)))
        return io.BytesIO(_dafny_to_bytes(content))

    def read_bytes(self, path: str) -> bytes:
        return _dafny_to_bytes(_raise_if_err(self._mb.Read(_str_to_dafny(path))))

    def write(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> WriteResult:
        data = bytes(content) if isinstance(content, (bytes, bytearray, memoryview)) else content.read()
        dwr = _raise_if_err(
            self._mb.Write(_str_to_dafny(path), _bytes_to_dafny(data), overwrite, _metadata_to_dafny(metadata))
        )
        return _dafny_wr_to_python(path, dwr)

    def write_atomic(
        self,
        path: str,
        content: WritableContent,
        *,
        overwrite: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> WriteResult:
        return self.write(path, content, overwrite=overwrite, metadata=metadata)

    def open_atomic(self, path: str, *, overwrite: bool = False) -> contextlib.AbstractContextManager[io.BytesIO]:
        @contextlib.contextmanager
        def _ctx() -> Iterator[io.BytesIO]:
            buf = io.BytesIO()
            yield buf
            buf.seek(0)
            self.write(path, buf.read(), overwrite=overwrite)

        return _ctx()

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        _raise_if_err(self._mb.Delete(_str_to_dafny(path), missing_ok))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        _raise_if_err(self._mb.DeleteFolder(_str_to_dafny(path), recursive, missing_ok))

    # -- Return-type marshaling: Dafny FileInfo/FolderEntry -> Python models ----

    def list_files(self, path: str, *, recursive: bool = False, max_depth: int | None = None) -> Iterator[FileInfo]:
        result = _raise_if_err(
            self._mb.ListFiles(_str_to_dafny(path), recursive, -1 if max_depth is None else max_depth)
        )
        fallback = datetime.now(tz=timezone.utc)
        for fi in result:
            yield _to_file_info(fi, fallback)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        for fe in _raise_if_err(self._mb.ListFolders(_str_to_dafny(path))):
            yield _to_folder_entry(_dafny_to_str(fe.path))

    def get_file_info(self, path: str) -> FileInfo:
        dafny_fi = _raise_if_err(self._mb.GetFileInfo(_str_to_dafny(path)))
        return _to_file_info(dafny_fi, datetime.now(tz=timezone.utc))

    def get_folder_info(self, path: str) -> FolderInfo:
        dafny_fi = _raise_if_err(self._mb.GetFolderInfo(_str_to_dafny(path)))
        return FolderInfo(
            path=RemotePath.from_backend_path(path),
            file_count=int(dafny_fi.file__count),
            total_size=int(dafny_fi.total__size),
        )

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        _raise_if_err(self._mb.Move(_str_to_dafny(src), _str_to_dafny(dst), overwrite))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        _raise_if_err(self._mb.Copy(_str_to_dafny(src), _str_to_dafny(dst), overwrite))

    def __repr__(self) -> str:
        return "DafnyOracleBackend()"
