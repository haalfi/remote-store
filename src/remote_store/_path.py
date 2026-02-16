"""RemotePath — immutable, validated path value object."""

from __future__ import annotations

from typing import Final

from remote_store._errors import InvalidPath


class RemotePath:
    """An immutable, normalized path within a remote store.

    :param raw: The raw path string to normalize and validate.
    :raises InvalidPath: If the path is malformed or unsafe.
    """

    __slots__ = ("_path",)
    _path: Final[str]  # type: ignore[misc]

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
