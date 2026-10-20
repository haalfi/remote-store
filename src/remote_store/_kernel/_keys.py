"""The key rule: refusals, normalisation and the root, decided once.

Pure functions over strings, so both runtimes share them unchanged.
"""

# Spec 053 BE-030.

from __future__ import annotations


def _segments(key: str) -> list[str]:
    # The segment drop of `backends._flat_ns._addressable_segments`, stated here
    # rather than imported: importing it runs `remote_store.backends.__init__`,
    # which imports every backend, and the backends will subclass this kernel.
    return [s for s in key.split("/") if s and s != "."]


def refusal(key: str) -> str | None:
    """Why the key rule refuses *key*, or ``None`` when it does not.

    The refusal step of the pipeline: a leading ``/``, a ``..`` segment, a null
    byte, a backslash. A backslash is refused as a key, not as the root.
    """
    if key.startswith("/"):
        return "Path must not start with '/'"
    if "\0" in key:
        return "Path contains null byte"
    if "\\" in key:
        return "Path contains a backslash"
    if ".." in key.split("/"):
        return "Path contains '..' segment"
    return None


def canonical(key: str) -> str:
    """Step 3: drop empty and ``.`` segments; every root spelling becomes ``""``.

    Only meaningful for a key ``refusal`` accepts.
    """
    return "/".join(_segments(key))


def listable(key: str) -> bool:
    """Whether a key a driver listed may be presented to a caller.

    A stored key the rule would refuse or rewrite, written by another tool, is
    omitted rather than folded onto the node it would name.
    """
    return bool(key) and refusal(key) is None and canonical(key) == key


def pattern_refusal(pattern: str) -> str | None:
    """Step 2 over a whole ``glob`` pattern, wildcards included."""
    return refusal(pattern)


def canonical_pattern(pattern: str) -> str:
    """Step 3 over a pattern, keeping a trailing ``/`` when anything remains.

    In a pattern a trailing ``/`` selects directories only, so it is the one
    piece of a pattern normalisation does not drop.
    """
    body = canonical(pattern)
    if body and pattern.endswith("/"):
        return body + "/"
    return body


def ancestors(key: str) -> list[str]:
    """The slash-aligned ancestors of a canonical key, shallowest first."""
    parts = key.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def parent(key: str) -> str:
    """The parent of a canonical key; ``""`` for a top-level key."""
    return key.rsplit("/", 1)[0] if "/" in key else ""


def name(key: str) -> str:
    """The final segment of a canonical key."""
    return key.rsplit("/", 1)[-1]
