# ADR-0008: Extension Namespace Contract (`ext.*`)

## Status

| Field         | Value    |
| ------------- | -------- |
| Status        | Accepted |
| Supersedes    | —        |
| Superseded by | —        |
| Amends        | —        |

## Context

The project has three extensions (`ext.arrow`, `ext.batch`, `ext.transfer`)
that emerged organically but follow consistent patterns:

- Each lives in `src/remote_store/ext/<name>.py`.
- Each uses only the public `Store` / `Backend` API (never `_backend`).
- Each defines `__all__`.
- None owns or closes a Store.
- `CapabilityNotSupported` always propagates to the caller.
- Pure-Python extensions (`batch`, `transfer`) are exported unconditionally
  from `remote_store.__init__`.  Optional-dependency extensions (`arrow`)
  use a conditional `try/except` import with a helpful `ModuleNotFoundError`.

Future extensions (`ext.notify`, `ext.cache`, streaming atomic writes) and
potential third-party extensions need these rules written down.  Without a
documented contract, contributors would have to reverse-engineer the
conventions from existing code.

### Scope

This ADR covers the **namespace convention and module contract** for
stateless utility extensions — functions that accept a Store and operate
on it.  It does not define an extension framework with interfaces,
hooks, lifecycle management, or plugin discovery.  Those patterns will
be designed when needed (see "Future patterns" below).

## Decision

The `ext.*` namespace contract for stateless utility extensions — standalone
functions that accept a `Store` and operate on it. Framework concerns
(interfaces, hooks, lifecycle management, plugin discovery) are out of scope and
get their own ADRs when built.

- **Location** — extensions live in `src/remote_store/ext/<name>.py` (single
  module) or `src/remote_store/ext/<name>/` (sub-package for complex ones);
  `ext/__init__.py` re-exports nothing — each extension is imported directly.
  *Reverse if* a plugin-discovery mechanism (deferred) requires a registry in
  `__init__`.
- **Public API only** — extensions use only the public `Store` / `Backend` API;
  private-attribute access (`store._backend`) is forbidden. `Store.unwrap(type_hint)`
  is the sanctioned escape hatch for native backend handles. *Reverse if* a
  required capability becomes impossible to express through the public API.
- **Module exports** — every extension module defines `__all__`. *Reverse if*
  the project drops explicit export lists project-wide.
- **Lifecycle** — extensions never own the `Store`: they must not close it or
  use it as a context manager. The caller owns lifecycle. *Reverse if* an
  extension legitimately needs to own a Store it constructs (a different
  pattern — new ADR).
- **Error propagation** — `CapabilityNotSupported` must propagate to the caller,
  never be suppressed, so callers see an honest capability boundary rather than
  a silent wrong result. *Reverse if* the capability model stops using
  exceptions to signal unsupported operations.
- **Zero-dependency core** — core `remote-store` takes no third-party
  dependencies; optional deps are declared as extras in `pyproject.toml`.
  Extension code must guard optional-dependency imports (including inside
  `TYPE_CHECKING` blocks, which mypy still evaluates) rather than importing them
  unconditionally. This constraint is why the optional-dependency extension
  category exists at all. *Reverse if* the zero-dependency-core promise is
  abandoned.

### Capability-probe exception pattern

`CapabilityNotSupported` MAY be caught in exactly one case: an extension
**probing for an optional native backend at initialization**, where a graceful
fallback exists (e.g. `ext.arrow` Tier 1 native fast-path falling through to
Tier 2/3 I/O). The catch must be narrowly scoped to the expected exceptions and
commented. This is the sole sanctioned exception to "must propagate," and it is
bounded to *optional* features with a fallback — a probe for a *required*
operation must still propagate. *Reverse if* capability probing moves to an
explicit `supports()`-style API that removes the need to catch.

The exact exception tuple, the `# noqa: BLE001` marker, and the concrete probe
live in the code (`ext/arrow.py`) and in spec `014-pyarrow-filesystem-adapter`
§ PA-001, which points here for rationale.

### Deferred and relocated

- **Optional-extension re-exports** — removed; superseded by **ADR-0013**.
  Optional-dependency extensions are imported from `remote_store.ext.<name>`,
  never re-exported from `remote_store.__init__`. Pure-Python extensions remain
  unconditionally exported.
- **Stateful patterns** — hook/interceptor (`ext.notify`), proxy/wrapping
  (`ext.cache`), and context-manager streaming writes are not covered here; each
  is designed in its own ADR when the extension is built. The rules above
  (public API only, `__all__`, dependency guarding, error propagation) apply to
  all extension types.
- **Authoring pipeline, test location, third-party naming (`remote-store-<name>`),
  and plugin discovery** live in CONTRIBUTING § "Adding an Extension" — the
  operational checklist. Entry-point discovery stays deferred until real
  third-party extensions exist.

## Consequences

- **Documented contract.** Contributors and third-party authors have a
  single reference for extension rules.
- **Consistent patterns.** New extensions follow the same structure,
  reducing review friction.
- **Zero breaking changes.** This ADR codifies existing practice; no
  existing code needs to change.
- **CONTRIBUTING.md checklist.** An "Adding an Extension" checklist
  ensures nothing is missed.
- **Deferred complexity.** Entry-point discovery, namespace packages,
  and extension registries are explicitly deferred until real need
  emerges.
