"""Dafny-compiled MemoryBackend adapter — conformance oracle.

Wraps the mathematically verified Dafny MemoryBackend (compiled to Python)
behind the ``Backend`` ABC so it can be run through the conformance test suite.

**Principle**: the compiled oracle is correct by construction (51 verified
proofs, 0 errors).  If the oracle fails a conformance test, the *test* has a
bug — not the oracle.  See ``sdd/formal/README.md`` § Compiled Oracle.
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


def _str_to_dafny(s: str) -> _dafny.Seq:
    """Convert Python str to Dafny Seq[CodePoint]."""
    return _dafny.SeqWithoutIsStrInference(map(_dafny.CodePoint, s))


def _dafny_to_str(seq: _dafny.Seq) -> str:
    """Convert Dafny Seq[CodePoint] to Python str."""
    return "".join(str(cp) for cp in seq)


def _bytes_to_dafny(data: bytes) -> _dafny.Seq:
    """Convert Python bytes to Dafny seq<nat>."""
    return _dafny.Seq(list(data))


def _dafny_to_bytes(seq: _dafny.Seq) -> bytes:
    """Convert Dafny seq<nat> to Python bytes."""
    return bytes(seq)


def _filename(path: str) -> str:
    """Extract the last segment of a path."""
    if "/" in path:
        return path.rsplit("/", 1)[1]
    return path


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
# Capabilities — mirror the Dafny spec (all except GLOB)
# ---------------------------------------------------------------------------
_ORACLE_CAPABILITIES = CapabilitySet(set(Capability) - {Capability.GLOB})


# ---------------------------------------------------------------------------
# DafnyOracleBackend
# ---------------------------------------------------------------------------


class DafnyOracleBackend(Backend):
    """Backend adapter wrapping the compiled Dafny MemoryBackend.

    Bridges Dafny types (``_dafny.Seq``, ``_dafny.Map``, ``_dafny.CodePoint``)
    to the Python ``Backend`` interface.  The underlying Dafny implementation
    is mathematically verified — 51 proofs, 0 errors.
    """

    def __init__(self) -> None:
        self._mb = _dafny_module.MemoryBackend()
        self._mb.ctor__()
        # Root ("") is handled at the adapter level — NOT inserted into the
        # Dafny fs map because Dafny's Path type requires non-empty strings.

    # -- properties -----------------------------------------------------------

    @property
    def name(self) -> str:
        return _BACKEND_NAME

    @property
    def capabilities(self) -> CapabilitySet:
        return _ORACLE_CAPABILITIES

    # -- existence checks -----------------------------------------------------

    def exists(self, path: str) -> bool:
        if not path or path == ".":
            return True
        dp = _str_to_dafny(path)
        return bool(_raise_if_err(self._mb.Exists(dp)))

    def is_file(self, path: str) -> bool:
        if not path or path == ".":
            return False
        dp = _str_to_dafny(path)
        return bool(_raise_if_err(self._mb.IsFileMethod(dp)))

    def is_folder(self, path: str) -> bool:
        if not path or path == ".":
            return True
        dp = _str_to_dafny(path)
        return bool(_raise_if_err(self._mb.IsFolderMethod(dp)))

    # -- read -----------------------------------------------------------------

    def read(self, path: str) -> io.BufferedReader:
        dp = _str_to_dafny(path)
        content = _raise_if_err(self._mb.Read(dp))
        raw = _dafny_to_bytes(content)
        return io.BufferedReader(io.BytesIO(raw))  # type: ignore[arg-type]

    def read_bytes(self, path: str) -> bytes:
        dp = _str_to_dafny(path)
        content = _raise_if_err(self._mb.Read(dp))
        return _dafny_to_bytes(content)

    # -- write ----------------------------------------------------------------

    def write(self, path: str, content: WritableContent, *, overwrite: bool = False) -> None:
        data = bytes(content) if isinstance(content, (bytes, bytearray, memoryview)) else content.read()
        dp = _str_to_dafny(path)
        dc = _bytes_to_dafny(data)
        self._ensure_parents(path)
        _raise_if_err(self._mb.Write(dp, dc, overwrite))

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

    # -- delete ---------------------------------------------------------------

    def delete(self, path: str, *, missing_ok: bool = False) -> None:
        dp = _str_to_dafny(path)
        _raise_if_err(self._mb.Delete(dp, missing_ok))

    def delete_folder(self, path: str, *, recursive: bool = False, missing_ok: bool = False) -> None:
        dp = _str_to_dafny(path)
        _raise_if_err(self._mb.DeleteFolder(dp, recursive, missing_ok))

    # -- listing --------------------------------------------------------------

    def list_files(self, path: str, *, recursive: bool = False, max_depth: int | None = None) -> Iterator[FileInfo]:
        dp = _str_to_dafny(path if path else "")
        dafny_max_depth = -1 if max_depth is None else max_depth
        result = _raise_if_err(self._mb.ListFiles(dp, recursive, dafny_max_depth))
        now = datetime.now(tz=timezone.utc)
        for fi in result:
            p = _dafny_to_str(fi.path)
            yield FileInfo(
                path=RemotePath(p),
                name=_filename(p),
                size=int(fi.size),
                modified_at=now,
            )

    def list_folders(self, path: str) -> Iterator[FolderEntry]:
        dp = _str_to_dafny(path if path else "")
        result = _raise_if_err(self._mb.ListFolders(dp))
        for fe in result:
            p = _dafny_to_str(fe.path)
            yield FolderEntry(
                path=RemotePath(p),
                name=_filename(p),
            )

    # -- metadata -------------------------------------------------------------

    def get_file_info(self, path: str) -> FileInfo:
        dp = _str_to_dafny(path)
        dafny_fi = _raise_if_err(self._mb.GetFileInfo(dp))
        p = _dafny_to_str(dafny_fi.path)
        return FileInfo(
            path=RemotePath(p),
            name=_filename(p),
            size=int(dafny_fi.size),
            modified_at=datetime.now(tz=timezone.utc),
        )

    def get_folder_info(self, path: str) -> FolderInfo:
        dp = _str_to_dafny(path)
        _raise_if_err(self._mb.GetFolderInfo(dp))
        # Dafny returns minimal FolderInfo(path, name).
        # Compute file_count and total_size by scanning the fs map.
        file_count = 0
        total_size = 0
        for k in self._mb.fs.keys.Elements:
            entry = self._mb.fs[k]
            if entry.is_FileEntry and _dafny_module.default__.IsChildOf(k, dp):
                file_count += 1
                total_size += int(entry.info.size)
        return FolderInfo(
            path=RemotePath(path),
            file_count=file_count,
            total_size=total_size,
        )

    # -- move / copy ----------------------------------------------------------

    def move(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        ds = _str_to_dafny(src)
        dd = _str_to_dafny(dst)
        self._ensure_parents(dst)
        _raise_if_err(self._mb.Move(ds, dd, overwrite))

    def copy(self, src: str, dst: str, *, overwrite: bool = False) -> None:
        ds = _str_to_dafny(src)
        dd = _str_to_dafny(dst)
        self._ensure_parents(dst)
        _raise_if_err(self._mb.Copy(ds, dd, overwrite))

    # -- repr -----------------------------------------------------------------

    def __repr__(self) -> str:
        return "DafnyOracleBackend()"

    # -- internal helpers -----------------------------------------------------

    def _ensure_parents(self, path: str) -> None:
        """Insert DirEntry nodes for every ancestor of *path*.

        The Dafny spec uses an explicit ``fs`` map with ``DirEntry`` nodes.
        Conformance tests expect ``write("a/b/c.txt", ...)`` to implicitly
        create directories ``a`` and ``a/b``.
        """
        parts = path.split("/")
        for i in range(1, len(parts)):
            ancestor = "/".join(parts[:i])
            dp = _str_to_dafny(ancestor)
            if dp not in self._mb.fs:
                self._mb.fs = self._mb.fs.set(dp, _dafny_module.Entry_DirEntry())
