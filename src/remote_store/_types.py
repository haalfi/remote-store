"""Type aliases used throughout remote_store."""

from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO, Union

if TYPE_CHECKING:
    import os

PathLike = Union[str, "os.PathLike[str]"]  # noqa: UP007
WritableContent = BinaryIO | bytes
Extras = dict[str, object]
