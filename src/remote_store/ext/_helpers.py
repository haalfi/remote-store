"""Shared helpers for extension modules."""

from __future__ import annotations

import functools
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _deprecated_alias(old_name: str, new_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a deprecated wrapper that delegates to *new_fn*.

    The returned function emits a ``DeprecationWarning`` on every call,
    then forwards all arguments to *new_fn*.
    """

    @functools.wraps(new_fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        warnings.warn(
            f"{old_name}() is deprecated, use {new_fn.__name__}() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return new_fn(*args, **kwargs)

    wrapper.__name__ = old_name
    wrapper.__qualname__ = old_name
    return wrapper
