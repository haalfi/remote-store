"""Which ABC members each kernel inherits unchanged from its ABC, and signature parity between the two kernels."""

from __future__ import annotations

import asyncio
import inspect

from remote_store._backend import Backend
from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend
from remote_store.aio._async_backend import AsyncBackend
from remote_store.aio.backends._memory import AsyncMemoryBackend


def public(cls):
    return {n for n in dir(cls) if not n.startswith("_")}


def owner(cls, name):
    for k in cls.__mro__:
        if name in k.__dict__:
            return k.__name__
    return None


for kern, abc in ((DriverBackend, Backend), (AsyncDriverBackend, AsyncBackend)):
    inherited = sorted(n for n in public(abc) if owner(kern, n) == abc.__name__)
    print(f"{kern.__name__}: members taken from {abc.__name__} unchanged: {inherited}")

sync_names = public(DriverBackend)
async_names = public(AsyncDriverBackend)
print("only sync kernel:", sorted(sync_names - async_names))
print("only async kernel:", sorted(async_names - sync_names))
for n in sorted(sync_names & async_names):
    s, a = getattr(DriverBackend, n), getattr(AsyncDriverBackend, n)
    if callable(s) and callable(a):
        try:
            ss, sa = inspect.signature(s), inspect.signature(a)
        except (TypeError, ValueError):
            continue
        ps = [(p.name, p.kind, p.default) for p in ss.parameters.values()]
        pa = [(p.name, p.kind, p.default) for p in sa.parameters.values()]
        if ps != pa:
            print("SIGNATURE DIFF", n, ss, "|", sa)
        kind_s = (
            "asyncgen"
            if inspect.isasyncgenfunction(s)
            else "coro"
            if inspect.iscoroutinefunction(s)
            else "gen"
            if inspect.isgeneratorfunction(s)
            else "plain"
        )
        kind_a = (
            "asyncgen"
            if inspect.isasyncgenfunction(a)
            else "coro"
            if inspect.iscoroutinefunction(a)
            else "gen"
            if inspect.isgeneratorfunction(a)
            else "plain"
        )
        print(
            f"  {n}: sync={kind_s} async={kind_a} owner_sync={owner(DriverBackend, n)} owner_async={owner(AsyncDriverBackend, n)}"
        )


# Inherited AsyncBackend members on the kernel: do they go through the closed guard / key rule?
async def probe_inherited():
    b = AsyncMemoryBackend()
    out = {}
    for name in ("read_bytes",):
        pass
    try:
        out["iter_children('../x')"] = [x async for x in b.iter_children("../x")]
    except Exception as e:  # noqa: BLE001
        out["iter_children('../x')"] = repr(e)
    return out


print(asyncio.run(probe_inherited()))
