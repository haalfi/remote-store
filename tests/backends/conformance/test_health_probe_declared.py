"""Rule 13 structural conformance: every backend probes, or declares an exemption.

``check_health()`` is concrete-with-a-default (PING-002): a backend that never
overrides it inherits ``AsyncBackend`` / ``Backend``'s no-op and reports healthy
unconditionally. The outcome-based conformance test
(``test_check_health.py``) cannot see that absence — "returns ``None`` or raises
a mapped error" is satisfied by a no-op. This test closes that gap by asserting
on the *presence of a decision* (TESTING.md Rule 13, BK-312), in both directions:

- **Direction 1** — a backend not in ``_NO_PROBE`` must supply its own probe;
  silence (an inherited no-op) fails. This is what stops a *future* backend from
  reaching green by omission — the defect BUG-231 fixed for Graph.
- **Direction 2** — a backend in ``_NO_PROBE`` must NOT override; an exemption
  that grew a real probe is stale and must be dropped from the list.

Rule 13 is presence-of-decision only: it passes the moment an override exists and
cannot see whether that override contacts the backend. The per-backend behavioural
tests (``tests/backends/<x>/**/test_ping.py``) prove the probe *works*; this proves
it is *there*. The two are complementary, not interchangeable.

First instantiated for BUG-231 (Graph had no probe and no exemption).
"""

from __future__ import annotations

import contextlib

import pytest

from remote_store._backend import Backend
from remote_store.aio._async_backend import AsyncBackend

# Import every production backend module so its class is registered as a
# subclass before discovery runs. Optional-dependency backends are imported
# best-effort: when the extra is absent the class simply is not discovered, so
# the CI-with-all-extras run is the enforcing environment (mirrors the
# ``importorskip`` guard in the per-backend ``test_ping.py`` files).
from remote_store.aio.backends._memory import AsyncMemoryBackend
from remote_store.backends._memory import MemoryBackend

for _mod in (
    "remote_store.backends._local",
    "remote_store.backends._http",
    "remote_store.backends._azure",
    "remote_store.backends._s3",
    "remote_store.backends._s3_pyarrow",
    "remote_store.backends._s3_boto3",
    "remote_store.backends._sftp",
    "remote_store.backends._sqlalchemy",
    "remote_store.aio.backends._azure",
    "remote_store.aio.backends._graph.backend",
):
    with contextlib.suppress(ImportError):
        __import__(_mod)

# The two ABC defaults. Resolving the class that *supplies* check_health against
# BOTH is the crux of Rule 13: comparing against a single hardcoded ABC
# (``type(b).check_health is not Backend.check_health``) reports "overrides" for
# an async backend that merely inherits AsyncBackend's no-op — failing open for
# exactly the case the rule exists to catch.
_ABC_DEFAULTS = (Backend, AsyncBackend)

# The exemption registry — keyed by class, not by ``name``: sync ``MemoryBackend``
# and ``AsyncMemoryBackend`` both report ``name == "memory"`` and both legitimately
# inherit the no-op, so a name-keyed dict would collide. An entry costs a spec ID
# and a reason.
_NO_PROBE: dict[type, str] = {
    MemoryBackend: "PING-008 — in-memory, always healthy",
    AsyncMemoryBackend: "PING-008 — in-memory, always healthy",
}

# Adapters wrap another backend and delegate check_health; they are not
# standalone backends in the per-backend health-check taxonomy, so they are not
# subject to the probe-or-exempt rule.
_ADAPTER_NAMES = frozenset({"SyncBackendAdapter", "AsyncBackendSyncAdapter"})


def _all_subclasses(root: type) -> set[type]:
    out: set[type] = set()
    for sub in root.__subclasses__():
        out.add(sub)
        out |= _all_subclasses(sub)
    return out


def _concrete_backends() -> list[type]:
    """Every concrete production backend class across both ABCs.

    Filtered to ``remote_store.`` modules so test doubles defined under
    ``tests.`` never leak in (which would make the set import-order dependent);
    abstract bases (``__abstractmethods__``) and private ``_``-prefixed base
    classes (e.g. ``_S3Base``) are excluded, as are the wrapping adapters.
    """
    discovered = _all_subclasses(Backend) | _all_subclasses(AsyncBackend)
    concrete: list[type] = []
    for cls in discovered:
        if not cls.__module__.startswith("remote_store"):
            continue
        if cls.__name__.startswith("_") or cls.__name__ in _ADAPTER_NAMES:
            continue
        if getattr(cls, "__abstractmethods__", frozenset()):
            continue
        concrete.append(cls)
    return sorted(concrete, key=lambda c: (c.__module__, c.__name__))


def _has_own_probe(cls: type) -> bool:
    """True iff *cls* supplies its own ``check_health`` (not an inherited ABC no-op)."""
    owner = next(k for k in cls.__mro__ if "check_health" in k.__dict__)
    return owner not in _ABC_DEFAULTS


_BACKENDS = _concrete_backends()


def test_discovery_found_the_backends() -> None:
    # Guard against the discovery silently degrading to an empty set (e.g. a
    # refactor that stops importing the backend modules), which would make the
    # per-backend assertions below vacuously pass.
    names = {c.__name__ for c in _BACKENDS}
    assert {"LocalBackend", "MemoryBackend", "AsyncMemoryBackend"} <= names


@pytest.mark.spec("PING-002")
@pytest.mark.parametrize("cls", _BACKENDS, ids=lambda c: f"{c.__module__.split('.')[-1]}.{c.__name__}")
def test_health_probe_is_declared(cls: type) -> None:
    overrides = _has_own_probe(cls)
    if cls in _NO_PROBE:
        # Direction 2: an exemption that grew a real probe is stale.
        assert not overrides, f"{cls.__name__} now probes; drop it from _NO_PROBE"
    else:
        # Direction 1: silence is not consent — the bug BUG-231 fixed for Graph.
        assert overrides, f"{cls.__name__} inherits the no-op check_health default; probe it or add it to _NO_PROBE"
