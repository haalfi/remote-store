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
  extensions guard their import with ``try/except ModuleNotFoundError``
  and are imported directly from their module.

Available extensions:

- ``ext.batch``    -- bulk delete, copy, exists (pure Python)
- ``ext.transfer`` -- upload, download, cross-store transfer (pure Python)
- ``ext.arrow``    -- PyArrow FileSystem adapter (requires ``pyarrow``)
"""
