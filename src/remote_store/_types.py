"""Type aliases used throughout remote_store."""

from __future__ import annotations

import os  # noqa: TC003
from typing import BinaryIO, Union

PathLike = Union[str, "os.PathLike[str]"]  # noqa: UP007
WritableContent = BinaryIO | bytes
Extras = dict[str, object]
