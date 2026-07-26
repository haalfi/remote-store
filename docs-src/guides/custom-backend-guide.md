# Build Your Own Backend

Write file storage code once. Run it against local files, S3, SFTP, Azure,
OneDrive — or your own custom storage system.

This guide walks you through implementing a custom [`Backend`](../reference/api/backend.md) for remote-store.
By the end, you'll have a working backend that plugs into [`Store`](../reference/api/store.md),
[`Registry`](../reference/api/registry.md), and every extension in the ecosystem.

---

## What you'll build

A **Redis backend** that stores files as Redis keys. It's simple enough to fit
in one module, yet exercises every part of the Backend contract: reads, writes,
listing, metadata, error mapping, and capability declarations.

**Prerequisites:** `pip install remote-store redis`

---

## The Backend contract

Every backend is a subclass of [`Backend`](../reference/api/backend.md). The contract is
straightforward:

1. **Declare capabilities** — which operations does your backend support?
2. **Implement abstract members** — methods and properties covering CRUD, listing, and metadata. See [Abstract methods](#abstract-methods-must-implement) for the full list.
3. **Map all exceptions** — native errors must become `remote_store` errors. No leaks.

The [`Store`](../reference/api/store.md) class wraps your backend, adds path validation, capability gating,
and scoping. You implement the raw operations; `Store` handles the policy.

---

## Step 1: Scaffold the class

```python
--8<-- "examples/snippets/custom_backend_guide.py:step1-imports"
```

Every backend starts with these imports. The key types:

| Import | Purpose |
|---|---|
| [`Backend`](../reference/api/backend.md) | Abstract base class you subclass |
| [`Capability`](../reference/api/capabilities.md), [`CapabilitySet`](../reference/api/capabilities.md) | Declare supported operations |
| [`NotFound`](../reference/api/errors.md), [`AlreadyExists`](../reference/api/errors.md), ... | Normalized error types |
| [`FileInfo`](../reference/api/models.md), [`FolderEntry`](../reference/api/models.md), [`FolderInfo`](../reference/api/models.md) | Return types for listing and metadata |
| [`RemotePath`](../reference/api/models.md) | Immutable, validated path type |
| [`WriteResult`](../reference/api/models.md) | Return type for `write()` and `write_atomic()`; carries the written path, size, and optional backend-native digest/etag |
| `WritableContent` | Type alias: `bytes \| BinaryIO` |

---

## Step 2: Declare capabilities

```python
--8<-- "examples/snippets/custom_backend_guide.py:step2-capabilities"
```

**Capabilities gate Store methods.** If you don't declare `ATOMIC_WRITE`, calls
to `store.write_atomic()` raise `CapabilityNotSupported` automatically — you
don't need to handle it.

`_REDIS_CAPABILITIES` is assigned to the class-level `CAPABILITIES` attribute in Step 3.
Tooling and conformance tests read `YourBackend.CAPABILITIES` without instantiating the class,
so the constant must be a class attribute — not computed in `__init__`.

Three further capabilities are worth declaring when they apply:

- **`USER_METADATA`** — declare this when your backend stores the `metadata=` mapping passed to `write()` and `write_atomic()`. Without it, `Store` raises `CapabilityNotSupported` if the caller passes non-empty metadata.
- **`WRITE_RESULT_NATIVE`** — declare this when your `write*()` methods fill the rich `WriteResult` fields directly from the backend's own write response (`source == "native"`). The criterion is provenance, not field count — which fields land depends on what the response carries, and a native backend may fill none (SFTP declares the flag yet its write response has no metadata). Without the flag, results carry `path`, `size`, and `source == "basic"`. See the [WriteResult reference](../reference/api/models.md) for the full field list.
- **`LAZY_READ`** — declare this when `read()` fetches data lazily from the remote source. A `BytesIO` return does not qualify — data is already materialized.

The Redis example declares neither `USER_METADATA` nor `WRITE_RESULT_NATIVE` (it stores raw bytes without a metadata column and returns only `path` and `size` at write time).

Each capability gates specific Store methods. See the
[Capability reference](../reference/api/capabilities.md) for the full list.

---

## Step 3: Constructor and properties

```python
--8<-- "examples/snippets/custom_backend_guide.py:step3-constructor"
```

**Rules:**

- `name` must be a unique string. Used in error messages and the registry.
- `CAPABILITIES: ClassVar[CapabilitySet]` exposes the capability set at class level — no instantiation required. The `capabilities` property delegates to `self.CAPABILITIES` so both the class view and the instance view always agree.
- Constructor parameters become `options:` in YAML config (more on this later).

---

## Step 4: Internal helpers

Before implementing the abstract methods, add helpers for key management
and error mapping.

```python
--8<-- "examples/snippets/custom_backend_guide.py:step4-helpers"
```

Redis has no concept of folders, so we use key prefixes to simulate a
hierarchical namespace. Files live under `rs:file:<path>`, and folder markers
(optional) under `rs:dir:<path>`.

```python
--8<-- "examples/snippets/custom_backend_guide.py:step4-error-mapping"
```

**The cardinal rule:** backend-native exceptions must never leak. Every Redis
error becomes a `remote_store` error. The `from exc` preserves the original
traceback for debugging.

---

## Step 5: Existence checks

```python
--8<-- "examples/snippets/custom_backend_guide.py:step5-existence"
```

**Key invariants:**

- `exists()` **never raises `NotFound`** — always returns `bool`.
- `""` and `"."` are root aliases. Root always exists and is always a folder.
- `is_file("")` is always `False`. `is_folder("")` is always `True`.

A layer note on the alias rules: `Store` normalizes `"."` to `""` before
your backend runs, so your backend never sees `"."` through `Store` — an
unscoped store's root arrives as `""`, and a scoped store prepends its
`root_path`, so root arrives as that prefix instead. The rule to follow:
implement the root invariants in terms of `""`, and treat `"."` handling
as optional defense for direct backend callers — the tutorial guards
both, which is the safe shape. The precise backend-layer obligations live
in the
[Backend Adapter Contract](../../sdd/specs/003-backend-adapter-contract.md).

---

## Step 6: Reading

```python
--8<-- "examples/snippets/custom_backend_guide.py:step6-reading"
```

**Notes:**

- `read()` returns a `BinaryIO`. Since we return `BytesIO`, streams are
  seekable — that's why we declared `SEEKABLE_READ`.
- `read_bytes()` can be more efficient than `read().read()` because it avoids
  wrapping in a stream object.
- Both raise `NotFound` for missing files.

Since our `read()` returns seekable streams, we don't need to override
`read_seekable()` — the default implementation detects seekability and
returns the stream as-is.

---

## Step 7: Writing

```python
--8<-- "examples/snippets/custom_backend_guide.py:step7-writing"
```

**Key patterns:**

- `content` is `bytes | BinaryIO`. Normalize with `content if isinstance(content, bytes) else content.read()`.
- **Both `write()` and `write_atomic()` accept `metadata: Mapping[str, str] | None = None`.** If your backend declares `USER_METADATA`, persist the mapping alongside the file. If it doesn't, ignore the argument — `Store` rejects non-empty metadata before reaching your implementation.
- **Both methods must return [`WriteResult`](../reference/api/models.md).** Construct it with at minimum `path=RemotePath(path)` and `size=len(raw)`. If your backend can populate richer fields, declare `WRITE_RESULT_NATIVE` and include them. The Redis example constructs just the two required fields.
- **Write creates parent folders implicitly** — in Redis, there's nothing to create, but filesystem-based backends must `mkdir -p`.
- Re-raise your own errors (`AlreadyExists`, `InvalidPath`) before the catch-all `RedisError` handler.
- Even though Store gates `write_atomic()` via capabilities, implement the methods anyway (they're abstract). Raise `CapabilityNotSupported` as a safety net.

---

## Step 8: Deletion

```python
--8<-- "examples/snippets/custom_backend_guide.py:step8-deletion"
```

**Invariants:**

- `delete()` targets files. `delete_folder()` targets folders.
- `missing_ok=True` suppresses `NotFound`.
- `delete_folder(recursive=False)` raises `DirectoryNotEmpty` if the folder has contents.
- You cannot delete root (`""` or `"."`) — `Store` rejects it before your
  backend runs, so users never reach you with a root delete; the tutorial
  backend also guards it locally, which is the safer shape.

---

## Step 9: Listing

```python
--8<-- "examples/snippets/custom_backend_guide.py:step9-listing"
```

**Key rules:**

- `list_files(path="")` lists from root.
- `recursive=False` (default) yields only immediate children.
- **Honor `max_depth`.** `Store` always passes it, and the conformance
  suite calls your backend directly and asserts the depth boundary on what
  *you* return — a backend that ignores the value fails those tests, even
  though `Store` additionally applies client-side depth filtering for its
  own callers. Treat `recursive` and `max_depth` as independent filters,
  exactly as the code above does: at the backend layer `recursive=False`
  wins (immediate children only, whatever `max_depth` says), and
  `max_depth` prunes recursive listings to the requested depth. `Store`
  never sends you a *conflicting* combination — when callers set
  `max_depth`, its facade derives `recursive` from it, and `max_depth=0`
  arrives as `recursive=False`, where both rules agree — so the
  backend-layer precedence is observable only in direct calls, which is
  how the conformance suite calls you. The tutorial follows the formal
  backend contract here; where older spec prose differs, the
  [Backend Adapter Contract](../../sdd/specs/003-backend-adapter-contract.md)
  and the conformance suite are the operative authorities.
- `list_folders()` is always non-recursive — only immediate subfolders.
- Non-existent paths yield nothing (no exception).
- [`FileInfo`](../reference/api/models.md)`.path` must be a [`RemotePath`](../reference/api/models.md).

---

## Step 10: Metadata

```python
--8<-- "examples/snippets/custom_backend_guide.py:step10-metadata"
```

**Contrast with existence checks:**

- `get_file_info()` raises `NotFound` if missing.
- `get_folder_info()` raises `NotFound` if the folder doesn't exist.
- `exists()` never raises — returns `bool`.

---

## Step 11: Move and copy

```python
--8<-- "examples/snippets/custom_backend_guide.py:step11-move-copy"
```

**Rules the code above implements:**

- **`src == dst` is a data-preserving no-op** — never a delete-after-write on
  the same key. Place the no-op return *after* the source check so a missing
  source still raises `NotFound`. (Contract rule.)
- **Precondition order matters:** a missing source raises `NotFound` before
  the destination is checked for `AlreadyExists`. (Contract rule.)
- Empty source or destination paths raise `InvalidPath` — today a
  `Store`-enforced convention that shipped backends (and this tutorial)
  also guard defensively; promoting it to a formal backend-contract clause
  is tracked spec work.

The conformance suite verifies the no-op rule for backends that declare
`self_op_supported` (a registration fact covered later in this guide).

---

## Step 12: Lifecycle methods

```python
--8<-- "examples/snippets/custom_backend_guide.py:step12-lifecycle"
```

`check_health()` should be the **cheapest possible read-only operation**.
Redis `PING` is ideal. For S3 it's a `HEAD` on the bucket. For a database
it's `SELECT 1`.

One declarative flag rides along with `close()`: the
`close_is_terminal: ClassVar[bool]` class attribute (default `False`,
meaning the backend stays usable after `close()`). Declare `True` when
use-after-close must fail — the close-posture conformance lane tests
whichever posture you declare, so an undeclared terminal backend fails it.

---

## Step 13: Register and use

### Direct instantiation

```python
--8<-- "examples/snippets/custom_backend_guide.py:step13-direct"
```

### Via Registry (YAML config)

Register your backend type before creating a [`Registry`](../reference/api/registry.md).
YAML loading lives in the `remote_store.ext.yaml` extension and requires the
`yaml` extra (`pip install "remote-store[yaml]"`):

```python
--8<-- "examples/snippets/custom_backend_guide.py:step13-registry"
```

```yaml
# stores.yaml
backends:
  redis-main:
    type: redis
    options:
      url: "redis://localhost:6379/0"
      prefix: "app:"

stores:
  cache:
    backend: redis-main
    root_path: "cache/v2"
```

The `options` dict is unpacked as `**kwargs` to your constructor. Parameter
names in YAML must match your `__init__` signature exactly.

One ownership note: stores from `registry.get_store()` do not own their
backend, so `store.close()` is a no-op on them — the registry closes the
backends it instantiated. Call `registry.close()` when done, or use
`Registry` as a context manager (`with Registry(config) as registry:`).

---

## Step 14: Extensions work automatically

Because your backend implements the `Backend` contract, every remote-store
extension works out of the box:

```python
--8<-- "examples/snippets/custom_backend_guide.py:step14-extensions"
```

Extensions that require specific capabilities will check at runtime. For
example, `ext.glob.glob_files()` works with any `LIST`-capable backend —
it doesn't need the `GLOB` capability.

---

## Partial-capability backends

Not every backend supports every operation. The HTTP backend, for example,
is read-only — this is the shipped `ReadOnlyHttpBackend`'s actual capability
set (note there is no `LIST`: plain HTTP has no directory listing):

```python
--8<-- "examples/snippets/custom_backend_guide.py:partial-capabilities"
```

When a user calls `store.write()` on an HTTP-backed store, the `Store` layer
raises `CapabilityNotSupported` before your backend code runs. You still need
to implement the abstract methods (Python requires it), but they can raise
`CapabilityNotSupported`:

```python
--8<-- "examples/snippets/custom_backend_guide.py:partial-write"
```

---

## Error mapping checklist

Every backend-native exception must map to one of these:

| remote-store error | When to raise |
|---|---|
| [`NotFound`](../reference/api/errors.md) | File/folder doesn't exist (for operations that require it) |
| [`AlreadyExists`](../reference/api/errors.md) | Target exists and `overwrite=False` |
| [`PermissionDenied`](../reference/api/errors.md) | Auth failure, insufficient permissions |
| [`InvalidPath`](../reference/api/errors.md) | Malformed path, null bytes, `..` traversal |
| [`DirectoryNotEmpty`](../reference/api/errors.md) | Non-empty folder and `recursive=False` |
| [`BackendUnavailable`](../reference/api/errors.md) | Network error, service down |
| [`CapabilityNotSupported`](../reference/api/errors.md) | Operation not supported by this backend |

**Pattern:** catch the SDK's base exception class, classify by error
code/type, and raise the appropriate remote-store error with `from exc`.

---

## Testing your backend

remote-store ships a per-topic conformance suite under
`tests/backends/conformance/` that validates any backend against the formal
`BackendContract` specification. Backends contributed to the repo plug into
this infrastructure and run through the full suite automatically. Standalone
backends can either reuse this suite or write focused tests against the same
categories.

---

### Conformance suite overview

The suite lives in
[`tests/backends/conformance/`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance),
split into per-topic files that share the same parameterized `backend`
fixture — every registered backend runs the full suite automatically.

| Topic file | Coverage | Run with |
|---|---|---|
| [`test_identity.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_identity.py) | Identity, capabilities, lifecycle, `resolve`, native path round-trip | `pytest tests/backends/conformance/test_identity.py` |
| [`test_io.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_io.py) | `exists`, `is_file`/`is_folder`, read, write, delete, `to_key` round-trip | `pytest tests/backends/conformance/test_io.py` |
| [`test_listing.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_listing.py) | `list_files`/`list_folders`, `iter_children`, glob, completeness | `pytest tests/backends/conformance/test_listing.py` |
| [`test_atomic.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_atomic.py) | `write_atomic`, `open_atomic` (SAW-*), `WriteResult` (WR-*), move/copy semantics | `pytest tests/backends/conformance/test_atomic.py` |
| [`test_metadata.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_metadata.py) | `get_file_info`/`get_folder_info`, `size`, `modified_at`, aggregates | `pytest tests/backends/conformance/test_metadata.py` |
| [`test_streaming.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_streaming.py) | Streaming reads, `LAZY_READ` laziness, resource cleanup | `pytest tests/backends/conformance/test_streaming.py` |
| [`test_errors.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_errors.py) | Typed-error fidelity across read/write/delete/move/copy paths | `pytest tests/backends/conformance/test_errors.py` |
| [`test_check_health.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_check_health.py) | `check_health()` contract — error mapping never leaks native SDK exceptions | `pytest tests/backends/conformance/test_check_health.py` |
| [`test_health_probe_declared.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_health_probe_declared.py) | Structural: every backend overrides `check_health()` or declares an exemption (presence only; probe behavior is verified per-backend) | `pytest tests/backends/conformance/test_health_probe_declared.py` |
| [`test_concurrency.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_concurrency.py) | Posture-gated concurrency lane — each fixture tested against its declared `concurrency` posture | `pytest tests/backends/conformance/test_concurrency.py` |
| [`test_close_posture.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_close_posture.py) | Posture-gated `close()` lane — reusable vs. terminal after close | `pytest tests/backends/conformance/test_close_posture.py` |

The directory also carries infrastructure lanes (sync-adapter conformance,
large-payload guard, xfail guard, replayed examples) and the async suite
under `aio/` — browse
[the directory](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance)
for the full inventory.

Run the whole suite at once with `pytest tests/backends/conformance/`.

**Extended (Dafny-derived) cases** — error fidelity, precondition ordering,
depth filtering, move/copy edge semantics, resource cleanup — are not a
separate file. They are individual tests marked
[`@pytest.mark.extended_conformance`](https://github.com/haalfi/remote-store/tree/master/tests/backends/conformance)
spread across the topic files above, so they run with the rest of the suite
by default and can be selected on their own:

```bash
pytest -m extended_conformance
```

Async backends have their own extended sibling,
[`test_async_extended.py`](https://github.com/haalfi/remote-store/blob/master/tests/backends/conformance/test_async_extended.py),
which exercises the `AsyncBackend` contract (ASYNC-* mirroring BE-*).

The conformance suite itself is validated by running it against a
mathematically verified oracle compiled from the formal Dafny specification
(`sdd/formal/MemoryBackend.dfy`).  If the oracle passes a test, the test
is known-correct.  This means passing the
conformance suite is a strong guarantee of correctness — not just "matches
what existing backends happen to do."  See [`sdd/formal/README.md`](https://github.com/haalfi/remote-store/blob/master/sdd/formal/README.md)
§ Compiled Oracle for details.

---

### Registering in the conformance fixture (contributing backends)

If you are contributing a backend to remote-store, this is step 3 of
[CONTRIBUTING.md § Adding a New Backend](../../CONTRIBUTING.md#adding-a-new-backend).
The test infrastructure is registry-driven. Four steps: declare facts in
two TOML files, add one small factory module under
[`tests/backends/fixtures/`](https://github.com/haalfi/remote-store/tree/master/tests/backends/fixtures),
and classify your family in the by-name conformance lanes (step 4). The
conformance suite then parametrizes every test over your fixture
automatically — registration itself needs no conftest edits, though a
backend that needs an external service still adds a server fixture (see
the end of this section).

The TOML and Python blocks below show test-infrastructure files, so they
are hand-written fences rather than executable snippet regions (the CI
drift gate validates the TOML values against the fixture loader instead).

**1. Declare the backend family in `tests/backends/fixtures/backends.toml`:**

```toml
# tests/backends/fixtures/backends.toml
[backend.redis]
sources           = ["src/remote_store/backends/_redis.py"]
transport         = "fs"
concurrency       = "thread_safe"
flat_namespace    = true          # true when the backend has no real directory entries
self_op_supported = true          # move(p, p) / copy(p, p) is a safe no-op
```

`transport`, `concurrency`, and the fixture's `stage` / `kind` /
`container` fields below are closed vocabularies; their members and
semantics are documented authoritatively in the two TOML files' header
comments, and the loader rejects unknown values. Three things to know
here: `concurrency` is deliberately defaultless — a new family must state
its thread-safety posture or the loader refuses to start; the values are
declarations of fact, so establish them (is your client library actually
thread-safe?) rather than copying the example's; and some backends have
no exact member — Redis fits neither `transport` nor `container`
precisely, so pick the nearest transport (`fs` here is that
approximation, not a statement that Redis is a filesystem).

**2. Declare the fixture in `tests/backends/fixtures/fixtures.toml`:**

```toml
# tests/backends/fixtures/fixtures.toml
[fixture.redis]
backend   = "redis"
stage     = 2
kind      = "real-local"
container = "none"
is_async  = false
```

Per-fixture overrides of `flat_namespace` / `self_op_supported` merge on top
of the family defaults — that is how the Azurite emulator (flat) and live
ADLS Gen2 (HNS) share one `azure` family yet disagree.

Three of these fields deserve extra care — `stage` and `kind` drive
collection, `container` is about CI provisioning:

- **`stage` decides when your fixture participates.** Stage 1 fixtures run
  everywhere; stage 2–3 fixtures are dropped from parametrization unless
  the session's stage is high enough. The active stage is auto-detected
  (stage 2 when a Docker daemon is reachable, stage 1 otherwise) and can be
  forced with `--stage=N` or the `RS_TEST_STAGE` env var. A service-backed
  fixture like this one belongs in stage 2.
- **`kind = "real-live"`** (live cloud) fixtures must also carry
  `pytest.mark.live` via the registration's `marks=` — the registry
  rejects a live fixture without it.
- If CI cannot start your service via `container` (the enum has no member
  for it, as with Redis here), provision the service yourself and have the
  factory skip when it is absent — that is step 3's first obligation.

**3. Add a factory module `tests/backends/fixtures/redis.py`:**

The module name matches the fixture name by default (that is how it gets
imported); a differently-named or shared module needs a `_MODULE_FOR`
entry — see below. The factory is called fresh for **every test**, and
the suite runs no cleanup unless you provide one. That gives it four
obligations beyond constructing the backend:

- **Skip when infrastructure is absent** — the optional dependency AND the
  service itself. Factories run at test setup, so `pytest.skip` there is
  how a fixture self-excludes; a missing reachability check turns every
  test into a `BackendUnavailable` failure on machines without the daemon.
- **Provision the namespace it hands out** — create the bucket/database/
  container the backend points at; the suite assumes writable storage.
- **Isolate per call** — a unique prefix or bucket per invocation, or
  earlier tests' leftovers show up as baffling `AlreadyExists` /
  orphan-artifact failures that look like backend bugs.
- **Provide `cleanup=`** to close the backend after each test.

Keep backend/SDK imports *inside* the factory functions: `_load_all()`
imports every factory module at conftest import time, so a module-level
`import` of an optional dependency would break collection for the whole
`tests/backends/` tree on machines without it.

```python
import uuid

import pytest

from tests.backends.fixtures._loader import load_fixture
from tests.backends.fixtures.registry import BackendFixture, register

_meta = load_fixture("redis")
_URL = "redis://localhost:6379/0"


def _factory():
    redis = pytest.importorskip("redis", reason="redis-py not installed")
    try:
        redis.Redis.from_url(_URL).ping()
    except redis.RedisError:
        pytest.skip("Redis server not reachable")

    from remote_store.backends._redis import RedisBackend

    # Unique prefix per call = per-test isolation. Redis needs no
    # provisioning (keys spring into existence); a bucket-based backend
    # would create its bucket here.
    return RedisBackend(url=_URL, prefix=f"test-{uuid.uuid4().hex[:8]}:")


def _capabilities() -> frozenset:
    try:
        from remote_store.backends._redis import RedisBackend

        return frozenset(RedisBackend.CAPABILITIES)
    except ImportError:
        return frozenset()


def _cleanup(backend) -> None:
    backend.close()


register(
    BackendFixture(
        factory=_factory,
        capabilities=_capabilities(),
        cleanup=_cleanup,
        **_meta.to_kwargs(),
    )
)
```

`_load_all()` walks `fixtures.toml` and imports the factory module with
the same name as each fixture — so a fixture whose module is named
differently (or a second fixture sharing one module) needs an entry in the
`_MODULE_FOR` map in `tests/backends/fixtures/__init__.py`, or collection
dies with `ModuleNotFoundError`. The conformance conftest's
`pytest_generate_tests` hook then parametrizes every test that takes a
`backend` argument (or `async_backend` for async fixtures) over the
registered fixtures:

```bash
pytest tests/backends/conformance/ -k redis --stage=2
```

Expect this first run to fail in the two `test_identity.py`
classification lanes until step 4 below is done.

**4. Classify your family in the by-name conformance lanes.** Two
`test_identity.py` declaration sets (atomic-move and seekable) fail loudly
for any unclassified family — the failure message names the exact edit.
One lane does NOT prompt: `test_health_probe_declared.py` discovers
backends from a hardcoded module import list, and a module missing from it
is silently not checked — add your backend module there yourself.

If your backend requires an external service (like S3, SFTP, or Azurite),
add a session-scoped server fixture in `tests/conftest.py` (where
`moto_server` / `sftp_server` / `azurite_server` live), publish its endpoint
via `_populate_infra` in `tests/backends/conftest.py` plus a field on
`InfraState` in `tests/backends/fixtures/_state.py`, and read `INFRA` from
your factory at call time.

---

### Capability gating

Backends may declare a subset of capabilities, and the suite skips what a
backend cannot do — a read-only backend cleanly skips all write, move, copy,
and delete tests without failures. Two mechanisms, in order of preference:

**Class-level filtering** is the primary mechanism: test classes parametrize
via `fixture_params(*caps)`, so a backend missing a capability never
enters those tests at all.

**Runtime fallback** is the `_require()` helper, for a single test inside a
coarsely-filtered class that needs a stricter capability than its siblings:

```python
def _require(backend: Backend, *caps: Capability) -> None:
    for cap in caps:
        if not backend.capabilities.supports(cap):
            pytest.skip(f"Backend does not support {cap.name}")
```

Use the same runtime pattern in your own tests:

```python
from remote_store import Capability
import pytest

def test_move_preserves_content(backend):
    _require(backend, Capability.MOVE)
    backend.write("src.txt", b"hello")
    backend.move("src.txt", "dst.txt")
    assert backend.read_bytes("dst.txt") == b"hello"
```

A backend declaring only `READ` and `LIST` never enters the `WRITE`,
`MOVE`, `COPY`, and `DELETE` lanes at all — class-filtered tests are not
generated for it — and any stricter test inside a coarser class
self-skips. The suite still passes: absences and skips are not failures.

---

### Flat-namespace vs. hierarchical backends

Backends fall into two models that affect a handful of conformance tests.

**Hierarchical** backends (Local, SFTP, Memory) have real directory objects.
Writing a file creates its parent directories; a path can be either a file
*or* a directory, never both.

**Flat-namespace** backends (S3, Azure, HTTP) have no real directory entries.
Folders are virtual — inferred from key prefixes. A path `a/b/c` implies a
prefix `a/b/` but no actual directory object exists.

The conformance suite reads this from the per-backend `flat_namespace` flag
declared in `tests/backends/fixtures/backends.toml`, with per-fixture
overrides in `fixtures.toml` taking precedence (see the registration
steps above for both files and the Azurite-vs-ADLS example).
Tests that rely on real directory semantics call `_skip_flat_namespace()`,
which reads the resolved flag from the per-fixture record attached by the
conformance indirect fixture; no identity-set lookup is needed.

Key behavioral differences that the conformance tests check:

| Behavior | Hierarchical (Local, SFTP, Memory) | Flat-namespace (S3, Azure, HTTP) |
|---|---|---|
| Write to a path that is an existing directory | Raises `InvalidPath` | Typically allowed (no real directory) |
| `delete_folder(recursive=False)` on non-empty folder | Raises `DirectoryNotEmpty` | Behaviour varies; some tests are skipped |
| Explicit directory creation | Required (mkdir semantics) | Not needed; folders emerge from key prefixes |
| `is_folder(path)` for a prefix with no keys | `False` | `False` |

If your backend is hierarchical (the common case), no action is needed — the
full extended suite applies.

---

### Conformance checklist

Before a backend is considered conformant, verify:

| Level | What | Command |
|---|---|---|
| **Conformance** | All `tests/backends/conformance/` tests pass or self-skip (declared capability missing) | `pytest tests/backends/conformance/ -k <fixture-name>` |
| **Extended** | All `@pytest.mark.extended_conformance` cases pass or self-skip | `pytest -m extended_conformance -k <fixture-name>` |
| **Error mapping** | Every native exception maps to a `remote_store` error — nothing leaks | Error mapping checklist above |
| **Repr safety** | `repr(backend)` does not expose secrets | `pytest tests/backends/conformance/test_identity.py -k test_repr_masks_secrets` |

Three pitfalls in reading these results:

- **Check stage participation first.** A stage-2/3 fixture is silently
  dropped from parametrization when the session's stage is lower — and the
  default stage is 1 on machines without a reachable Docker daemon. Pass
  `--stage=2` (or set `RS_TEST_STAGE`) before suspecting your registration.
- **The `-k` token is the fixture/family name** (underscores, e.g.
  `s3_boto3`), not the backend's `name` property — a hyphenated `name` like
  `"s3-boto3"` never matches any test id, so `-k` with it silently selects
  nothing.
- **Green is only meaningful if your fixture actually ran.** Confirm your
  fixture id appears in the parametrized test ids (`pytest --collect-only -q
  ... | grep <fixture-name>`). A handful of passes with thousands
  deselected, or exit code 5 ("no tests ran"), means the fixture never
  participated — stage gating or a failed registration, not universal
  self-skipping.

Skips are expected and acceptable when a backend doesn't declare the relevant
capability. Failures (not skips) in either suite are blocking.

---

### Standalone backend testing

> **Not contributing to the repo?** Skip the fixture registration above and
> write focused tests directly. The categories below mirror what the
> conformance suite verifies.

If you are building a backend outside the remote-store repository, write
focused tests covering the same categories the conformance suite verifies:

#### Happy paths

- Read/write round-trip
- Overwrite behavior (`overwrite=True` and `overwrite=False`)
- List files and folders (recursive and non-recursive)
- Move and copy
- Metadata accuracy (`size`, `modified_at`)

#### Error paths

- `read()` on missing file raises `NotFound`
- `write()` on existing file with `overwrite=False` raises `AlreadyExists`
- `delete(missing_ok=False)` on missing file raises `NotFound`
- `delete_folder(recursive=False)` on non-empty folder raises `DirectoryNotEmpty`
- Path naming a wrong type (file path to `get_folder_info`, directory path to
  `read`) raises `InvalidPath`
- Backend unavailable raises `BackendUnavailable`

#### Edge cases

- Empty path (`""`) and root alias (`"."`) — root always exists and is always a folder
- `is_file("")` always returns `False`; `exists("")` never raises
  (test these through `Store` — see the layer note in Step 5)
- Deeply nested paths (`"a/b/c/d/e/file.txt"`)
- Non-existent paths to `list_files` / `list_folders` yield nothing (no exception)
- `repr(backend)` does not expose credentials or secrets
- Concurrent access (if thread-safety matters)

#### Example test structure

```python
--8<-- "examples/snippets/custom_backend_guide.py:test-examples"
```

---

## Design decisions

### When to declare `SEEKABLE_READ`

Declare it only if `read()` **always** returns a seekable stream with zero
overhead. `BytesIO` qualifies. Streams backed by network iterators don't.

If your `read()` returns a non-seekable stream, don't worry — `Store` handles
it. `read_seekable()` will spool to a temp file automatically. You can also
override `read_seekable()` for an optimized path (like Azure's HTTP Range
reader).

### When to support `ATOMIC_WRITE`

Support it if your backend can guarantee that readers never see partial content.
Filesystem backends use temp-file-and-rename. Databases can use transactions.
If your backend's writes are inherently atomic (single Redis `HSET`), you could
declare it — but be honest about the guarantee. "Atomic at the key level"
isn't the same as "atomic rename of a visible path."

### Thread safety

Backends may be called from multiple threads (e.g., `batch_copy` with
concurrency). Use locking if your internal state is mutable. Redis clients
are generally thread-safe, so our example doesn't need explicit locking.

---

## Quick reference

### Abstract methods (must implement)

| Member | Type | Raises on error |
|---|---|---|
| `CAPABILITIES` (class attribute) | [`ClassVar[CapabilitySet]`](../reference/api/capabilities.md) | — |
| `name` (property) | `str` | — |
| `capabilities` (property) | [`CapabilitySet`](../reference/api/capabilities.md) | — |
| `exists(path)` | `bool` | Never raises [`NotFound`](../reference/api/errors.md) |
| `is_file(path)` | `bool` | — |
| `is_folder(path)` | `bool` | — |
| `read(path)` | `BinaryIO` | [`NotFound`](../reference/api/errors.md) |
| `read_bytes(path)` | `bytes` | [`NotFound`](../reference/api/errors.md) |
| `write(path, content, overwrite, metadata=None)` | [`WriteResult`](../reference/api/models.md) | [`AlreadyExists`](../reference/api/errors.md) |
| `write_atomic(path, content, overwrite, metadata=None)` | [`WriteResult`](../reference/api/models.md) | [`AlreadyExists`](../reference/api/errors.md), [`CapabilityNotSupported`](../reference/api/errors.md) |
| `open_atomic(path, overwrite)` | `ContextManager[BinaryIO]` | [`AlreadyExists`](../reference/api/errors.md), [`CapabilityNotSupported`](../reference/api/errors.md) |
| `delete(path, missing_ok)` | `None` | [`NotFound`](../reference/api/errors.md) |
| `delete_folder(path, recursive, missing_ok)` | `None` | [`NotFound`](../reference/api/errors.md), [`DirectoryNotEmpty`](../reference/api/errors.md) |
| `list_files(path, recursive, max_depth)` | `Iterator[`[`FileInfo`](../reference/api/models.md)`]` | — |
| `list_folders(path)` | `Iterator[`[`FolderEntry`](../reference/api/models.md)`]` | — |
| `get_file_info(path)` | [`FileInfo`](../reference/api/models.md) | [`NotFound`](../reference/api/errors.md) |
| `get_folder_info(path)` | [`FolderInfo`](../reference/api/models.md) | [`NotFound`](../reference/api/errors.md) |
| `move(src, dst, overwrite)` | `None` | [`NotFound`](../reference/api/errors.md), [`AlreadyExists`](../reference/api/errors.md) |
| `copy(src, dst, overwrite)` | `None` | [`NotFound`](../reference/api/errors.md), [`AlreadyExists`](../reference/api/errors.md) |

### Optional overrides

| Method | Default behavior |
|---|---|
| `read_seekable(path)` | Spools non-seekable streams to temp file |
| `iter_children(path)` | Chains `list_files()` + `list_folders()` |
| `glob(pattern)` | Raises `CapabilityNotSupported` |
| `to_key(native_path)` | Identity function |
| `native_path(path)` | Identity function |
| `resolve(path)` | Builds a `ResolutionPlan` from `name` and `native_path()`; no I/O. Override to add backend-specific `details` |
| `check_health()` | No-op |
| `close()` | No-op |
| `unwrap(type_hint)` | Raises `CapabilityNotSupported` |

---

## See also

- [Backend API reference](../reference/api/backend.md) — full method documentation
- [Error types API reference](../reference/api/errors.md) — all error classes
- [Backend Adapter Contract](../../sdd/specs/003-backend-adapter-contract.md) — formal spec
- [Capabilities Matrix](../reference/capabilities-matrix.md) — all backends and their capabilities
- [Choosing a Backend](choosing-a-backend.md) — decision guide for built-in backends
- [Architecture Overview](../explanation/architecture.md) — how Store, Backend, and extensions fit together
