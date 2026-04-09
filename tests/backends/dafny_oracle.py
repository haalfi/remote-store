"""Dafny-compiled MemoryBackend adapter — conformance oracle.

Thin wrapper that bridges Dafny types (``Seq[CodePoint]``, ``Map``,
``Result``) to the Python ``Backend`` ABC.  All behavioral logic lives in
the verified Dafny spec — this module does only type marshaling.

**Principle**: the compiled oracle is correct by construction (53 verified
proofs, 0 errors).  If the oracle fails a conformance test, the *test* has a
bug — not the oracle.  See ``sdd/formal/README.md`` § Compiled Oracle.

The only adapter-level special case is root path handling: Dafny's ``Path``
type requires non-empty strings (``type Path = s: string | s != ""``), while
the Python Backend ABC uses ``""`` for root.  Root is always-exists,
always-folder, never-file by convention.
"""

from __future__ import annotations

import contextlib
import io
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from remote_store._backend import Backend
from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import (
    AlreadyExists,
    CapabilityNotSupported,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
)
from remote_store._models import FileInfo, FolderEntry, FolderInfo
from remote_store._path import RemotePath

if TYPE_CHECKING:
    from collections.abc import Iterator

    from remote_store._types import WritableContent

# ---------------------------------------------------------------------------
# Import the compiled Dafny module
# ---------------------------------------------------------------------------
_DAFNY_PY_DIR = str(Path(__file__).resolve().parent.parent.parent / "sdd" / "formal" / "MemoryBackend-py")
if _DAFNY_PY_DIR not in sys.path:
    sys.path.insert(0, _DAFNY_PY_DIR)

import _dafny  # noqa: E402
import module_ as _dafny_module  # noqa: E402

# ---------------------------------------------------------------------------
# Type marshaling helpers
# ---------------------------------------------------------------------------

_BACKEND_NAME = "dafny-oracle"
_ORACLE_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB})


def _str_to_dafny(s: str) -> _dafny.Seq:
    return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, s))


def _dafny_to_str(seq: _dafny.Seq) -> str:
    return "".join(str(cp) for cp in seq)


def _bytes_to_dafny(data: bytes) -> _dafny.Seq:
    return _dafny.Seq(list(data))


def _dafny_to_bytes(seq: _dafny.Seq) -> bytes:
    return bytes(seq)


def _filename(path: str) -> str:
    return path.rsplit("/", 1)[1] if "/" in path else path


def _raise_if_err(result: object) -> object:
    """Convert Dafny Result_Err to remote_store exceptions, return Ok value."""
    if result.is_Err:  # type: ignore[union-attr]
        err = result.error  # type: ignore[union-attr]
        path_str = _dafny_to_str(err.path) if hasattr(err, "path") else ""
        if err.is_NotFound:
            raise NotFound(path=path_str, backend=_BACKEND_NAME)
        if err.is_AlreadyExists:
            raise AlreadyExists(path=path_str, backend=_BACKEND_NAME)
        if err.is_InvalidPath:
            raise InvalidPath(path=path_str, backend=_BACKEND_NAME)
        if err.is_DirectoryNotEmpty:
            raise DirectoryNotEmpty(path=path_str, backend=_BACKEND_NAME)
        if err.is_CapabilityNotSupported:
            raise CapabilityNotSupported(
                capability=_dafny_to_str(err.capability),
                backend=_BACKEND_NAME,
            )
        if err.is_BackendUnavailable:
            msg = "Backend unavailable"
            raise NotFound(message=msg, backend=_BACKEND_NAME)
    return result.value  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# DafnyOracleBackend — pure type-marshaling wrapper
# ---------------------------------------------------------------------------


class DafnyOracleBackend(Backend):
    """Backend wrapping the compiled Dafny MemoryBackend (53 proofs, 0 errors).

    This adapter contains zero behavioral logic — only type conversions
    between Python and Dafny types, and the root-path type-boundary
    special case (Dafny Path requires non-empty strings).
    """

    def __init__(self) -> None:
        self._mb = _dafny_module.MemoryBackend()
        self._mb.ctor__()

    @property
    def name(self) -> str:
        return _BACKEND_NAME

    @property
    def capabilities(self) -> CapabilitySet:
        return _ORACLE_CAPABILITIES

    # -- Root path: Dafny Path type forbids ""; handle at type boundary -------

    def exists(self, path: str) -> bool:
        if not path or path == ".":
            return True
        return bool(_raise_if_err(self._mb.Exists(_str_to_dafny(path))))

    def is_file(self, path: str) -> bool:
        if not path or path == ".":
            return False
        return bool(_raise_if_err(self._mb.IsFileMethod(_str_to_dafny(path))))

    def is_folder(self, path: str) -> bool:
        if not path or path == ".":
            return True
        return bool(_raise_if_err(self._mb.IsFolderMethod(_str_to_dafny(path))))

    # -- Type marshaling: bytes <-> Dafny Seq, str <-> Seq[CodePoint] --------

    def read(self, path: str) -> io.BufferedReader:
        content = _raise_if_err(self._mb.Read(_str_to_dafny(path)))
        return io.BufferedReader(io.BytesIO(_dafny_to_bytes(content)))  # type: ignore[arg-type]

    def read_bytes(self, path: str) -> bytes:
        return _dafny_to_bytes(_raise_if_err(self._mb.Read(_str_to_dafny(path))))

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        data = bytes(content) if isinstance(content, (bytes, bytearray, memoryview)) else content.read()
        _raise_if_err(self._mb.Write(_str_to_dafny(path), _bytes_to_dafny(data), overwrite))

    def write_atomic(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        self.write(path, content, overwrite=overwrite)

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

    # -- Return-type marshaling: Dafny FileInfo/FolderEntry -> Python models --

    def list_files(self, path: str, *, recursive: bool = False, max_depth: int | None = None) -> Iterator[FileInfo]:
        dp = _str_to_dafny(path if path else "")
        result = _raise_if_err(self._mb.ListFiles(dp, recursive, -1 if max_depth is None else max_depth))
        now = datetime.now(tz=timezone.utc)
        for fi in result:
            p = _dafny_to_str(fi.path)
            yield FileInfo(path=RemotePath(p), name=_filename(p), size=int(fi.size), modified_at=now)

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        result = _raise_if_err(self._mb.ListFolders(_str_to_dafny(path if path else "")))
        for fe in result:
            p = _dafny_to_str(fe.path)
            yield FolderEntry(path=RemotePath(p), name=_filename(p))

    def get_file_info(self, path: str) -> FileInfo:
        dafny_fi = _raise_if_err(self._mb.GetFileInfo(_str_to_dafny(path)))
        p = _dafny_to_str(dafny_fi.path)
        return FileInfo(
            path=RemotePath(p), name=_filename(p), size=int(dafny_fi.size), modified_at=datetime.now(tz=timezone.utc)
        )

    def get_folder_info(self, path: str) -> FolderInfo:
        dafny_fi = _raise_if_err(self._mb.GetFolderInfo(_str_to_dafny(path)))
        return FolderInfo(
            path=RemotePath(_dafny_to_str(dafny_fi.path)),
            file_count=int(dafny_fi.file__count),
            total_size=int(dafny_fi.total__size),
        )

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        _raise_if_err(self._mb.Move(_str_to_dafny(src), _str_to_dafny(dst), overwrite))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        _raise_if_err(self._mb.Copy(_str_to_dafny(src), _str_to_dafny(dst), overwrite))

    def __repr__(self) -> str:
        return "DafnyOracleBackend()"
