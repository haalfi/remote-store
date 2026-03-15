"""Official extensions for remote-store.

Extensions live in ``remote_store.ext.<name>`` and follow a documented
contract (see ADR-0008):

- **Public API only** -- extensions use only the public Store / Backend
  API.  ``Store.unwrap()`` is the escape hatch for native access.
- **No lifecycle ownership** -- extensions never call ``store.close()``
  or enter the Store as a context manager.
- **Error propagation** -- ``CapabilityNotSupported`` always propagates
  to the caller; extensions must not suppress it.
- **``__all__``** -- every extension module defines ``__all__``.
- **Export rules** -- pure-Python extensions are re-exported from
  ``remote_store.__init__`` unconditionally.  Optional-dependency
  extensions are imported from their module directly
  (``from remote_store.ext.<name> import ...``); they are *not*
  re-exported from the top-level package (ADR-0013).

See ``guides/extensions.md`` for the list of available extensions.
"""
