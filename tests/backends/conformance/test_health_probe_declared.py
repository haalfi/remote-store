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

A class on the contract kernel always owns a ``check_health``, the kernel's, which
runs its driver's ``probe()`` (PING-002). For such a class the decision lives on
the driver, so the rule is asked of the driver class instead: its ``probe`` must
not be the driver protocol's inherited no-op body, unless exempted. Every kernel
class must be mapped to its driver in ``_DRIVERS``; an unmapped one fails, so a
new class on the kernel cannot pass on the kernel's ``check_health`` alone. The
map is checked too: the class must build the mapped driver, and must not
override the kernel's ``check_health`` (``_kernel_decision_defects``).

First instantiated for BUG-231 (Graph had no probe and no exemption).
"""

from __future__ import annotations

import contextlib

import pytest

from remote_store._backend import Backend
from remote_store._kernel._async.driver import AsyncDriver
from remote_store._kernel._async.kernel import _AsyncKernelCore
from remote_store._kernel._sync.driver import Driver
from remote_store._kernel._sync.kernel import _KernelCore
from remote_store.aio._async_backend import AsyncBackend

# Import every production backend module so its class is registered as a
# subclass before discovery runs. Optional-dependency backends are imported
# best-effort: when the extra is absent the class simply is not discovered, so
# the CI-with-all-extras run is the enforcing environment (mirrors the
# ``importorskip`` guard in the per-backend ``test_ping.py`` files).
from remote_store.aio.backends._memory import AsyncMemoryBackend, AsyncMemoryDriver
from remote_store.backends._memory import MemoryBackend, MemoryDriver

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
    # The contract kernel's two classes are concrete Backend subclasses too;
    # imported here so whether they are checked never depends on what else
    # the session imported first.
    "remote_store._kernel.backend",
    "remote_store._kernel.aio_backend",
):
    with contextlib.suppress(ImportError):
        __import__(_mod)

# The two ABC defaults. Resolving the class that *supplies* check_health against
# BOTH is the crux of Rule 13: comparing against a single hardcoded ABC
# (``type(b).check_health is not Backend.check_health``) reports "overrides" for
# an async backend that merely inherits AsyncBackend's no-op — failing open for
# exactly the case the rule exists to catch.
_ABC_DEFAULTS = (Backend, AsyncBackend)

# The driver protocols, whose ``probe`` body is the no-op a driver inherits when
# it subclasses them without declaring its own.
_DRIVER_DEFAULTS = (Driver, AsyncDriver)
_KERNEL_CORES = (_KernelCore, _AsyncKernelCore)

# Each class on the contract kernel and the driver it builds. Discovery finds the
# classes; this map says where each one's probe decision lives.
_DRIVERS: dict[type, type] = {
    MemoryBackend: MemoryDriver,
    AsyncMemoryBackend: AsyncMemoryDriver,
}

# The exemption registry — keyed by class, not by ``name``, so a sync and an async
# twin are two entries. An entry costs a spec ID and a reason.
_NO_PROBE: dict[type, str] = {
    MemoryBackend: "PING-008 — in-memory, always healthy",
    AsyncMemoryBackend: "PING-008 — in-memory, always healthy",
}

# Adapters wrap another backend and delegate check_health; they are not
# standalone backends in the per-backend health-check taxonomy, so they are not
# subject to the probe-or-exempt rule.
_ADAPTER_NAMES = frozenset({"SyncBackendAdapter", "AsyncBackendSyncAdapter"})

# The kernel's two runtimes take any driver, so they have no probe decision of
# their own; each class built on them is checked through its driver instead.
_KERNEL_BASES = frozenset({"DriverBackend", "AsyncDriverBackend"})


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
        if cls.__name__ in _KERNEL_BASES:
            continue
        if getattr(cls, "__abstractmethods__", frozenset()):
            continue
        concrete.append(cls)
    return sorted(concrete, key=lambda c: (c.__module__, c.__name__))


def _on_kernel(cls: type) -> bool:
    return issubclass(cls, _KERNEL_CORES)


def _kernel_decision_defects(cls: type, driver: type) -> list[str]:
    """Why the probe decision of kernel class *cls* is not where ``_DRIVERS`` says it is.

    The map is hand-kept, so it is checked: the driver *cls* builds must be the
    mapped one, and *cls* must not override the kernel's ``check_health``, which
    is what runs the driver's ``probe``. A class that cannot be built without
    arguments fails here until this check learns how to build it.
    """
    defects = []
    owner = next(k for k in cls.__mro__ if "check_health" in k.__dict__)
    if owner not in _KERNEL_CORES:
        defects.append(f"{cls.__name__} overrides check_health in {owner.__name__}, so its driver's probe may not run")
    try:
        built = type(cls()._driver)
    except TypeError as exc:
        defects.append(f"{cls.__name__}() needs arguments ({exc}); teach this check to build it")
    else:
        if built is not driver:
            defects.append(f"{cls.__name__} builds {built.__name__}, but _DRIVERS maps it to {driver.__name__}")
    return defects


def _has_own_probe(cls: type) -> bool:
    """True iff *cls* decides its probe: its own ``check_health``, or on the kernel its driver's ``probe``."""
    if _on_kernel(cls):
        driver = _DRIVERS[cls]
        owner = next(k for k in driver.__mro__ if "probe" in k.__dict__)
        return owner not in _DRIVER_DEFAULTS
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
def test_every_class_on_the_kernel_names_its_driver() -> None:
    # Fails closed: a kernel class missing here would otherwise be judged by the
    # kernel's own check_health, which every such class owns.
    unmapped = [c.__name__ for c in _BACKENDS if _on_kernel(c) and c not in _DRIVERS]
    assert not unmapped, f"add each to _DRIVERS with the driver class it builds: {unmapped}"
    stale = [c.__name__ for c in _DRIVERS if c not in _BACKENDS]
    assert not stale, f"_DRIVERS names classes discovery no longer finds: {stale}"


class _ProbingDriver(MemoryDriver):
    def probe(self) -> None:
        """A probe of its own, so a class mapped to this driver reads as probing."""


@pytest.mark.spec("PING-002")
def test_a_class_mapped_to_a_driver_it_does_not_build_is_refused() -> None:
    # The map said a probing driver; the class builds Memory's no-op one.
    class Remapped(MemoryBackend):
        pass

    assert _kernel_decision_defects(Remapped, _ProbingDriver) == [
        "Remapped builds MemoryDriver, but _DRIVERS maps it to _ProbingDriver"
    ]


@pytest.mark.spec("PING-002")
def test_a_kernel_class_overriding_check_health_is_refused() -> None:
    # An override that never runs the driver's probe is no probe decision.
    class Silenced(MemoryBackend):
        def check_health(self) -> None:
            return None

    defects = _kernel_decision_defects(Silenced, MemoryDriver)
    assert defects == ["Silenced overrides check_health in Silenced, so its driver's probe may not run"]


@pytest.mark.spec("PING-002")
def test_a_kernel_class_built_as_mapped_has_no_defect() -> None:
    assert _kernel_decision_defects(MemoryBackend, MemoryDriver) == []
    assert _kernel_decision_defects(AsyncMemoryBackend, AsyncMemoryDriver) == []


@pytest.mark.spec("PING-002")
@pytest.mark.parametrize("cls", _BACKENDS, ids=lambda c: f"{c.__module__.split('.')[-1]}.{c.__name__}")
def test_health_probe_is_declared(cls: type) -> None:
    if _on_kernel(cls):
        if cls not in _DRIVERS:
            pytest.fail(f"{cls.__name__} is on the kernel but not in _DRIVERS")
        defects = _kernel_decision_defects(cls, _DRIVERS[cls])
        assert not defects, "; ".join(defects)
    overrides = _has_own_probe(cls)
    if cls in _NO_PROBE:
        # Direction 2: an exemption that grew a real probe is stale.
        assert not overrides, f"{cls.__name__} now probes; drop it from _NO_PROBE"
    else:
        # Direction 1: silence is not consent — the bug BUG-231 fixed for Graph.
        assert overrides, f"{cls.__name__} inherits the no-op check_health default; probe it or add it to _NO_PROBE"
