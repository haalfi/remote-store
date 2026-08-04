"""RemotePath — immutable, validated path value object."""

from __future__ import annotations

from typing import ClassVar, Final

from remote_store._errors import InvalidPath


class RemotePath:
    """An immutable, normalized path within a remote store.

    Args:
        raw: The raw path string to normalize and validate.

    Raises:
        InvalidPath: If the path is malformed or unsafe.
    """

    __slots__ = ("_path",)
    _path: Final[str]  # type: ignore[misc]
    ROOT: ClassVar[RemotePath]

    def __init__(self, raw: str) -> None:
        normalized = self._normalize(raw)
        object.__setattr__(self, "_path", normalized)

    @staticmethod
    def _normalize(raw: str) -> str:
        if "\0" in raw:
            raise InvalidPath("Path contains null byte", path=raw)
        # Backslash → forward slash
        p = raw.replace("\\", "/")
        # Split, filter empty and dot segments, reject double-dot
        parts: list[str] = []
        for segment in p.split("/"):
            if segment == "" or segment == ".":
                continue
            if segment == "..":
                raise InvalidPath("Path contains '..' segment", path=raw)
            parts.append(segment)
        if not parts:
            raise InvalidPath("Path is empty after normalization", path=raw)
        return "/".join(parts)

    @property
    def name(self) -> str:
        """Final component of the path."""
        return self._path.rsplit("/", 1)[-1]

    @property
    def parent(self) -> RemotePath | None:
        """Parent path, or ``None`` if the path has only one component.

        Example: ``RemotePath("a/b").parent`` returns ``RemotePath("a")``,
        but ``RemotePath("a").parent`` returns ``None``.
        """
        if "/" not in self._path:
            return None
        parent_str = self._path.rsplit("/", 1)[0]
        p = object.__new__(RemotePath)
        object.__setattr__(p, "_path", parent_str)
        return p

    @property
    def parts(self) -> tuple[str, ...]:
        """Tuple of path components."""
        return tuple(self._path.split("/"))

    @property
    def suffix(self) -> str:
        """File extension including the dot, or empty string."""
        name = self.name
        dot = name.rfind(".")
        if dot <= 0:
            return ""
        return name[dot:]

    def as_posix(self) -> str:
        """Return the path as a forward-slash string.

        Mirrors ``pathlib.PurePath.as_posix``. The path is always stored
        with forward slashes, so the result is identical to ``str(self)`` on
        every platform. ``RemotePath.ROOT.as_posix()`` returns ``"."``.
        """
        return self._path

    def __truediv__(self, other: str) -> RemotePath:
        return RemotePath(f"{self._path}/{other}")

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"RemotePath({self._path!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RemotePath):
            return self._path == other._path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._path)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"RemotePath is immutable: cannot set '{name}'")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"RemotePath is immutable: cannot delete '{name}'")

    @classmethod
    def from_backend_path(cls, path: str) -> RemotePath:
        """Create a RemotePath, using ROOT for the root spellings.

        Backends use this in ``get_folder_info`` to avoid duplicating
        the ``RemotePath(path) if path else RemotePath.ROOT`` pattern.
        Both root spellings map to ``ROOT``; ``_normalize`` would otherwise
        reject ``"."`` for normalising to nothing, which is the right answer
        for a *file* path and the wrong one for the root folder.
        """
        return cls.ROOT if is_root(path) else cls(path)


# Class-level root sentinel (bypasses __init__ validation).
_root = object.__new__(RemotePath)
object.__setattr__(_root, "_path", ".")
RemotePath.ROOT = _root


_ROOT_SPELLINGS: Final = frozenset({"", "."})


def is_root(path: str) -> bool:
    """Return ``True`` if *path* is one of the two spellings of the store root.

    ``""`` is how a backend key names the root; ``"."`` is how ``RemotePath``
    renders it. Both reach backends — ``Store`` normalises its own inputs, but
    a caller holding a ``Backend`` directly, or one round-tripping a
    ``FolderInfo.path`` back into a query, does not. Backends that build a
    listing prefix by string concatenation must consult this first: ``"./"``
    is a real, and permanently empty, prefix on a flat namespace, so treating
    ``"."`` as an ordinary key silently answers for nothing.
    """
    return path in _ROOT_SPELLINGS


def strip_root(path: str) -> str:
    """Collapse either root spelling to ``""``, leaving other paths untouched."""
    return "" if is_root(path) else path
