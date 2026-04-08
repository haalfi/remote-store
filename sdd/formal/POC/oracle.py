"""
Dafny Oracle: Reference implementation of MemoryBackend.dfy in Python.

This module provides a faithful Python implementation of the MemoryBackend.dfy
formal specification. It is used as a ground-truth oracle for conformance tests,
allowing us to verify that production backends behave consistently with the
formally-verified contract.

Every method directly mirrors the Dafny postconditions and error semantics.
The oracle is deterministic and can be compared against real backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

# ============================================================================
# Error Model (mirrors BackendContract.dfy § Error model)
# ============================================================================


class ErrorKind(Enum):
    """Error types matching the Dafny Error datatype."""

    NOT_FOUND = auto()
    ALREADY_EXISTS = auto()
    PERMISSION_DENIED = auto()
    INVALID_PATH = auto()
    CAPABILITY_NOT_SUPPORTED = auto()
    DIRECTORY_NOT_EMPTY = auto()
    BACKEND_UNAVAILABLE = auto()


@dataclass(frozen=True)
class OracleError:
    """Represents an error result in the oracle."""

    kind: ErrorKind
    path: str | None = None
    backend: str = "oracle"


@dataclass(frozen=True)
class OracleOk:
    """Represents a successful result in the oracle."""

    value: Any


OracleResult = OracleOk | OracleError


# ============================================================================
# Data Models (mirrors BackendContract.dfy § Data models)
# ============================================================================


@dataclass(frozen=True)
class FileInfo:
    """File metadata: path, name, size."""

    path: str
    name: str
    size: int


@dataclass(frozen=True)
class FolderEntry:
    """Folder entry: path and name."""

    path: str
    name: str


# ============================================================================
# Filesystem Entry Types
# ============================================================================


@dataclass(frozen=True)
class FileEntry:
    """File entry with content and metadata."""

    content: bytes
    info: FileInfo


class DirEntry:
    """Marker for directory entries."""

    pass


# ============================================================================
# Path Utilities (mirrors BackendContract.dfy § Path utilities)
# ============================================================================


def slash_count(p: str) -> int:
    """Count forward slashes in a path string."""
    return p.count("/")


def filename(path: str) -> str:
    """Extract final path component (filename from path)."""
    if "/" not in path:
        return path
    return path.rsplit("/", 1)[1]


def depth(root: str, child: str) -> int:
    """
    Compute depth of child relative to root.

    Returns:
        >= 0: depth is the number of slashes in the relative suffix
        -1: child is not a child of root (precondition violation)

    Special case: when root is "", depth is the number of slashes in child.
    Mirrors BackendContract.dfy:
    ```
    function Depth(root: string, child: string): int
    {
      if |child| <= |root| + 1 then -1
      else if child[..|root|] != root then -1
      else if child[|root|] != '/' then -1
      else
        var suffix := child[|root| + 1..];
        SlashCount(suffix)
    }
    ```
    """
    if root == "":
        # Special case: empty root means depth is just the slash count
        return slash_count(child)
    if len(child) <= len(root) + 1:
        return -1
    if child[: len(root)] != root:
        return -1
    if child[len(root)] != "/":
        return -1
    suffix = child[len(root) + 1 :]
    return slash_count(suffix)


def is_child_of(child: str, parent: str) -> bool:
    """
    Check if child is a direct or indirect child of parent.

    Mirrors the Dafny spec (with special case for empty parent):
    ```
    predicate IsChildOf(child: string, parent: string)
    {
      |child| > |parent| + 1 &&
      child[..|parent|] == parent &&
      child[|parent|] == '/'
    }
    ```
    For empty parent "", apply semantic: non-empty path without leading slash.
    """
    if parent == "":
        # Special case: root directory. Child is a child if non-empty & no leading /
        return len(child) > 0 and not child.startswith("/")
    return len(child) > len(parent) + 1 and child[: len(parent)] == parent and child[len(parent)] == "/"


# ============================================================================
# Filesystem Predicates (mirrors BackendContract.dfy § Filesystem model)
# ============================================================================


def is_file(fs: dict[str, FileEntry | DirEntry], p: str) -> bool:
    """True if p exists in fs and is a FileEntry."""
    return p in fs and isinstance(fs[p], FileEntry)


def is_dir(fs: dict[str, FileEntry | DirEntry], p: str) -> bool:
    """True if p exists in fs and is a DirEntry."""
    return p in fs and isinstance(fs[p], DirEntry)


def path_exists(fs: dict[str, FileEntry | DirEntry], p: str) -> bool:
    """True if p exists in fs (file or directory)."""
    return p in fs


def has_children(fs: dict[str, FileEntry | DirEntry], dir_path: str) -> bool:
    """True if any path in fs is a child of dir_path."""
    return any(is_child_of(p, dir_path) for p in fs)


# ============================================================================
# Dafny Oracle: MemoryBackend Reference Implementation
# ============================================================================


class DafnyOracle:
    """
    Reference implementation of the Backend contract.

    Faithfully mirrors MemoryBackend.dfy, implementing every method with
    postconditions and error-ordering guarantees from the formal spec.
    """

    def __init__(self) -> None:
        """Initialize the oracle (empty filesystem, no capabilities restrictions)."""
        self.name = "oracle"
        self.fs: dict[str, FileEntry | DirEntry] = {}
        self.capabilities = {
            "read",
            "write",
            "delete",
            "list",
            "move",
            "copy",
            "atomic_write",
            "atomic_move",
            "metadata",
            "seekable_read",
        }

    def _ensure_parent_dirs(self, path: str) -> None:
        """Create all parent directories for a path (implicit directory creation)."""
        # Find all parent paths by splitting on /
        parts = path.split("/")
        for i in range(1, len(parts)):  # Skip the first (empty) part
            parent = "/".join(parts[:i])
            if parent and parent not in self.fs:
                self.fs[parent] = DirEntry()

    def exists(self, path: str) -> OracleResult:
        """
        Check if a path exists.

        Mirrors:
        ```
        method Exists(path: Path) returns (r: Result<bool>)
          ensures r.Ok?
          ensures r.value == PathExists(fs, path)
        ```

        Always succeeds; returns whether path exists.
        """
        return OracleOk(path_exists(self.fs, path))

    def read(self, path: str) -> OracleResult:
        """
        Read file content.

        Mirrors:
        ```
        method Read(path: Path) returns (r: Result<seq<nat>>)
          ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
          ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
          ensures IsFile(fs, path)      ==> r == Ok(fs[path].content)
        ```

        Error order (by postcondition):
        1. IsDir → InvalidPath
        2. !PathExists → NotFound
        3. IsFile → Ok
        """
        if is_dir(self.fs, path):
            return OracleError(ErrorKind.INVALID_PATH, path, self.name)
        if not path_exists(self.fs, path):
            return OracleError(ErrorKind.NOT_FOUND, path, self.name)
        if is_file(self.fs, path):
            entry = self.fs[path]
            assert isinstance(entry, FileEntry), "is_file check ensures FileEntry"
            return OracleOk(entry.content)
        # Unreachable (contradicts is_dir and path_exists checks)
        raise AssertionError(f"Path {path} state contradicts fs model")

    def write(self, path: str, content: bytes, overwrite: bool = False) -> OracleResult:
        """
        Write file content.

        Mirrors:
        ```
        method Write(path: Path, content: seq<nat>, overwrite: bool)
          returns (r: Result<()>)
          modifies this
          ensures IsDir(old(fs), path)
            ==> r == Err(InvalidPath(path, name))
          ensures !IsDir(old(fs), path) && IsFile(old(fs), path) && !overwrite
            ==> r == Err(AlreadyExists(path, name))
          ensures !IsDir(old(fs), path) && (!IsFile(old(fs), path) || overwrite)
            ==> r.Ok?
          ensures r.Ok? ==>
            IsFile(fs, path) && fs[path].content == content
        ```

        Error order:
        1. IsDir(old(fs), path) → InvalidPath
        2. !IsDir ∧ IsFile(old(fs), path) ∧ !overwrite → AlreadyExists
        3. Otherwise → Ok (create/overwrite file)
        """
        # Snapshot old state for error-path checking
        old_fs_is_dir = is_dir(self.fs, path)

        # 1. IsDir → InvalidPath
        if old_fs_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, path, self.name)

        # 2. IsFile ∧ !overwrite → AlreadyExists
        old_fs_is_file = is_file(self.fs, path)
        if old_fs_is_file and not overwrite:
            return OracleError(ErrorKind.ALREADY_EXISTS, path, self.name)

        # 3. Success: create or overwrite (ensure parent dirs exist)
        self._ensure_parent_dirs(path)
        info = FileInfo(path, filename(path), len(content))
        self.fs[path] = FileEntry(content, info)
        return OracleOk(None)

    def delete(self, path: str, missing_ok: bool = False) -> OracleResult:
        """
        Delete a file.

        Mirrors:
        ```
        method Delete(path: Path, missing_ok: bool) returns (r: Result<()>)
          modifies this
          ensures IsDir(old(fs), path)
            ==> r == Err(InvalidPath(path, name))
          ensures !PathExists(old(fs), path) && !missing_ok
            ==> r == Err(NotFound(path, name))
          ensures !PathExists(old(fs), path) && missing_ok
            ==> r.Ok?
          ensures IsFile(old(fs), path) ==> r.Ok?
          ensures IsFile(old(fs), path) && r.Ok?
            ==> !PathExists(fs, path)
        ```

        Error order:
        1. IsDir → InvalidPath
        2. !PathExists ∧ !missing_ok → NotFound
        3. Otherwise → Ok
        """
        old_is_dir = is_dir(self.fs, path)
        old_exists = path_exists(self.fs, path)

        # 1. IsDir → InvalidPath
        if old_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, path, self.name)

        # 2. !PathExists ∧ !missing_ok → NotFound
        if not old_exists and not missing_ok:
            return OracleError(ErrorKind.NOT_FOUND, path, self.name)

        # 3. Success: delete if it exists
        if path in self.fs:
            del self.fs[path]
        return OracleOk(None)

    def delete_folder(self, path: str, recursive: bool = False, missing_ok: bool = False) -> OracleResult:
        """
        Delete a directory (and optionally its contents).

        Mirrors:
        ```
        method DeleteFolder(path: Path, recursive: bool, missing_ok: bool)
          returns (r: Result<()>)
          modifies this
          ensures IsFile(old(fs), path)
            ==> r == Err(InvalidPath(path, name))
          ensures !PathExists(old(fs), path) && !missing_ok
            ==> r == Err(NotFound(path, name))
          ensures !PathExists(old(fs), path) && missing_ok
            ==> r.Ok?
          ensures IsDir(old(fs), path) && !recursive && HasChildren(old(fs), path)
            ==> r == Err(DirectoryNotEmpty(path, name))
          ensures IsDir(old(fs), path) && (recursive || !HasChildren(old(fs), path))
            ==> r.Ok?
          ensures IsDir(old(fs), path) && r.Ok?
            ==> !IsDir(fs, path)
          ensures IsDir(old(fs), path) && recursive && r.Ok? ==>
            forall p: Path | IsChildOf(p, path) :: !PathExists(fs, p)
        ```

        Error order:
        1. IsFile → InvalidPath (wrong type)
        2. !PathExists ∧ !missing_ok → NotFound
        3. IsDir ∧ !recursive ∧ HasChildren → DirectoryNotEmpty
        4. Otherwise → Ok
        """
        old_is_file = is_file(self.fs, path)
        old_is_dir = is_dir(self.fs, path)
        old_exists = path_exists(self.fs, path)
        old_has_children = has_children(self.fs, path)

        # 1. IsFile → InvalidPath
        if old_is_file:
            return OracleError(ErrorKind.INVALID_PATH, path, self.name)

        # 2. !PathExists ∧ !missing_ok → NotFound
        if not old_exists:
            if not missing_ok:
                return OracleError(ErrorKind.NOT_FOUND, path, self.name)
            # missing_ok and path doesn't exist → succeed
            return OracleOk(None)

        # Now path exists and is not a file, so it must be a directory (or nothing)
        if not old_is_dir:
            # Path exists but is neither file nor dir — impossible in model
            raise AssertionError(f"Path {path} exists but is neither file nor dir")

        # 3. IsDir ∧ !recursive ∧ HasChildren → DirectoryNotEmpty
        if not recursive and old_has_children:
            return OracleError(ErrorKind.DIRECTORY_NOT_EMPTY, path, self.name)

        # 4. Success: delete directory and (if recursive) all children
        if recursive:
            # Remove dir and all children
            self.fs = {k: v for k, v in self.fs.items() if k != path and not is_child_of(k, path)}
        else:
            # Remove empty directory only
            self.fs = {k: v for k, v in self.fs.items() if k != path}

        return OracleOk(None)

    def list_files(self, path: str, recursive: bool = False, max_depth: int = -1) -> OracleResult:
        """
        List files under a path (with optional depth filtering).

        Mirrors:
        ```
        method ListFiles(path: Path, recursive: bool, max_depth: int)
          returns (r: Result<seq<FileInfo>>)
          ensures r.Ok?
          ensures !PathExists(fs, path) ==> r.value == []
          ensures r.Ok? ==>
            forall fi | fi in r.value :: IsFile(fs, fi.path) && IsChildOf(fi.path, path)
          ensures r.Ok? ==>
            forall fi | fi in r.value :: Depth(path, fi.path) >= 0
          ensures !recursive && r.Ok? ==>
            forall fi | fi in r.value :: Depth(path, fi.path) == 0
          ensures recursive && max_depth >= 0 && r.Ok? ==>
            forall fi | fi in r.value :: Depth(path, fi.path) <= max_depth
          ensures r.Ok? && PathExists(fs, path) ==>
            forall p: Path | IsFile(fs, p) && IsChildOf(p, path) &&
              (if !recursive then Depth(path, p) == 0
               else if max_depth >= 0 then Depth(path, p) <= max_depth
               else true) ::
              exists fi | fi in r.value :: fi.path == p
        ```

        Always succeeds; returns empty list if path doesn't exist.
        Completeness: every matching file appears in result.
        """
        # Special case: empty path is the root, which always exists
        if path != "" and not path_exists(self.fs, path):
            return OracleOk([])

        result: list[FileInfo] = []

        for p, _entry in self.fs.items():
            if not is_file(self.fs, p):
                continue
            if not is_child_of(p, path):
                continue

            d = depth(path, p)
            # Precondition: is_child_of implies d >= 0
            if d < 0:
                raise AssertionError(f"is_child_of({p}, {path}) but depth is {d} (should be >= 0)")

            # Depth filter
            if not recursive and d != 0:
                continue
            if recursive and max_depth >= 0 and d > max_depth:
                continue

            # Add to result
            file_entry = self.fs[p]
            if not isinstance(file_entry, FileEntry):
                raise AssertionError(f"Expected FileEntry for {p}, got {type(file_entry)}")
            result.append(file_entry.info)

        return OracleOk(result)

    def list_folders(self, path: str) -> OracleResult:
        """
        List direct child directories of a path.

        Mirrors:
        ```
        method ListFolders(path: Path) returns (r: Result<seq<FolderEntry>>)
          ensures r.Ok?
          ensures !PathExists(fs, path) ==> r.value == []
          ensures r.Ok? ==>
            forall fe | fe in r.value :: IsDir(fs, fe.path) && IsChildOf(fe.path, path)
          ensures r.Ok? && PathExists(fs, path) ==>
            forall p: Path | IsDir(fs, p) && IsChildOf(p, path) ::
              exists fe | fe in r.value :: fe.path == p
        ```

        Always succeeds; returns empty list if path doesn't exist.
        Completeness: every child directory appears in result.
        """
        # Special case: empty path is the root, which always exists
        if path != "" and not path_exists(self.fs, path):
            return OracleOk([])

        result: list[FolderEntry] = []

        for p in self.fs:
            if not is_dir(self.fs, p):
                continue
            if not is_child_of(p, path):
                continue
            result.append(FolderEntry(p, filename(p)))

        return OracleOk(result)

    def get_file_info(self, path: str) -> OracleResult:
        """
        Get file metadata.

        Mirrors:
        ```
        method GetFileInfo(path: Path) returns (r: Result<FileInfo>)
          ensures IsDir(fs, path)       ==> r == Err(InvalidPath(path, name))
          ensures !PathExists(fs, path) ==> r == Err(NotFound(path, name))
          ensures IsFile(fs, path)      ==> r.Ok? && r.value == fs[path].info
        ```

        Error order:
        1. IsDir → InvalidPath
        2. !PathExists → NotFound
        3. IsFile → Ok
        """
        if is_dir(self.fs, path):
            return OracleError(ErrorKind.INVALID_PATH, path, self.name)
        if not path_exists(self.fs, path):
            return OracleError(ErrorKind.NOT_FOUND, path, self.name)
        if is_file(self.fs, path):
            entry = self.fs[path]
            assert isinstance(entry, FileEntry), "is_file check ensures FileEntry"
            return OracleOk(entry.info)
        raise AssertionError(f"Path {path} contradicts is_dir and path_exists checks")

    def move(self, src: str, dst: str, overwrite: bool = False) -> OracleResult:
        """
        Move a file from src to dst.

        Mirrors:
        ```
        method Move(src: Path, dst: Path, overwrite: bool)
          returns (r: Result<()>)
          modifies this
          ensures IsDir(old(fs), src)
            ==> r == Err(InvalidPath(src, name))
          ensures !PathExists(old(fs), src)
            ==> r == Err(NotFound(src, name))
          ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
            ==> r == Err(InvalidPath(dst, name))
          ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
            ==> r == Err(AlreadyExists(dst, name))
          ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
                  (!IsFile(old(fs), dst) || overwrite || src == dst)
            ==> r.Ok?
          ensures r.Ok? && IsFile(old(fs), src) ==>
            IsFile(fs, dst) &&
            fs[dst].content == old(fs)[src].content &&
            (src != dst ==> !PathExists(fs, src))
        ```

        Error order:
        1. IsDir(src) → InvalidPath
        2. !PathExists(src) → NotFound
        3. IsDir(dst) → InvalidPath
        4. IsFile(dst) ∧ !overwrite ∧ src ≠ dst → AlreadyExists
        5. Otherwise → Ok
        """
        old_src_is_dir = is_dir(self.fs, src)
        old_src_exists = path_exists(self.fs, src)
        old_src_is_file = is_file(self.fs, src)
        old_dst_is_dir = is_dir(self.fs, dst)
        old_dst_is_file = is_file(self.fs, dst)

        # 1. IsDir(src) → InvalidPath
        if old_src_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, src, self.name)

        # 2. !PathExists(src) → NotFound
        if not old_src_exists:
            return OracleError(ErrorKind.NOT_FOUND, src, self.name)

        assert old_src_is_file, "After checks, src must be a file"

        # 3. IsDir(dst) → InvalidPath
        if old_dst_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, dst, self.name)

        # Self-move is a no-op success
        if src == dst:
            return OracleOk(None)

        # 4. IsFile(dst) ∧ !overwrite → AlreadyExists
        if old_dst_is_file and not overwrite:
            return OracleError(ErrorKind.ALREADY_EXISTS, dst, self.name)

        # 5. Success: move src to dst (ensure parent dirs exist)
        self._ensure_parent_dirs(dst)
        src_entry = self.fs[src]
        assert isinstance(src_entry, FileEntry), "src must be a FileEntry"
        new_info = FileInfo(dst, filename(dst), src_entry.info.size)
        new_entry = FileEntry(src_entry.content, new_info)
        del self.fs[src]
        self.fs[dst] = new_entry
        return OracleOk(None)

    def copy(self, src: str, dst: str, overwrite: bool = False) -> OracleResult:
        """
        Copy a file from src to dst.

        Mirrors:
        ```
        method Copy(src: Path, dst: Path, overwrite: bool)
          returns (r: Result<()>)
          modifies this
          ensures IsDir(old(fs), src)
            ==> r == Err(InvalidPath(src, name))
          ensures !PathExists(old(fs), src)
            ==> r == Err(NotFound(src, name))
          ensures IsFile(old(fs), src) && IsDir(old(fs), dst)
            ==> r == Err(InvalidPath(dst, name))
          ensures IsFile(old(fs), src) && IsFile(old(fs), dst) && !overwrite && src != dst
            ==> r == Err(AlreadyExists(dst, name))
          ensures IsFile(old(fs), src) && !IsDir(old(fs), dst) &&
                  (!IsFile(old(fs), dst) || overwrite || src == dst)
            ==> r.Ok?
          ensures r.Ok? && IsFile(old(fs), src) ==>
            IsFile(fs, src) && IsFile(fs, dst) &&
            fs[dst].content == old(fs)[src].content
        ```

        Error order: same as Move, except self-copy also succeeds.
        Success preserves src (unlike Move).
        """
        old_src_is_dir = is_dir(self.fs, src)
        old_src_exists = path_exists(self.fs, src)
        old_src_is_file = is_file(self.fs, src)
        old_dst_is_dir = is_dir(self.fs, dst)
        old_dst_is_file = is_file(self.fs, dst)

        # 1. IsDir(src) → InvalidPath
        if old_src_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, src, self.name)

        # 2. !PathExists(src) → NotFound
        if not old_src_exists:
            return OracleError(ErrorKind.NOT_FOUND, src, self.name)

        assert old_src_is_file, "After checks, src must be a file"

        # 3. IsDir(dst) → InvalidPath
        if old_dst_is_dir:
            return OracleError(ErrorKind.INVALID_PATH, dst, self.name)

        # Self-copy is a no-op success
        if src == dst:
            return OracleOk(None)

        # 4. IsFile(dst) ∧ !overwrite → AlreadyExists
        if old_dst_is_file and not overwrite:
            return OracleError(ErrorKind.ALREADY_EXISTS, dst, self.name)

        # 5. Success: copy src to dst, preserving src (ensure parent dirs exist)
        self._ensure_parent_dirs(dst)
        src_entry = self.fs[src]
        assert isinstance(src_entry, FileEntry), "src must be a FileEntry"
        new_info = FileInfo(dst, filename(dst), src_entry.info.size)
        new_entry = FileEntry(src_entry.content, new_info)
        self.fs[dst] = new_entry
        return OracleOk(None)

    def require_capability(self, cap: str) -> OracleResult:
        """
        Check if a capability is supported.

        Mirrors:
        ```
        method RequireCapability(cap: Capability) returns (r: Result<()>)
          ensures cap in capabilities ==> r.Ok?
          ensures cap !in capabilities ==>
            r == Err(CapabilityNotSupported(CapabilityName(cap), name))
        ```

        Always succeeds for the oracle (it supports all capabilities).
        """
        if cap in self.capabilities:
            return OracleOk(None)
        return OracleError(ErrorKind.CAPABILITY_NOT_SUPPORTED, None, self.name)
