# ADR-0013: Drop Optional-Extension Re-exports from `__init__.py`

## Status

Accepted — supersedes the "Export rules" section of ADR-0008.

## Context

ADR-0008 established two export patterns for extensions:

1. **Pure-Python extensions** are re-exported unconditionally from
   `remote_store.__init__`.
2. **Optional-dependency extensions** are conditionally re-exported via
   `try/except ImportError` blocks so that `from remote_store import
   pyarrow_fs` works when the dependency is installed.

In practice, the conditional re-export for optional-dependency extensions
provides negligible value and introduces real costs:

- **Import-time overhead.** Each `try` block eagerly imports the extension
  module (and its dependency) at `import remote_store` time.  Heavy
  dependencies like Dagster (~2-5 s) penalise every user who happens to
  have the package installed, even when the extension is unused.  The
  dagster extension was deliberately excluded from this pattern (ID-075),
  creating an inconsistency.

- **No internal usage.** A codebase-wide search confirms that no source
  file, test, or example imports an optional-extension symbol from the
  top-level package.  All existing code uses the canonical
  `from remote_store.ext.<name> import ...` path.

- **Maintenance friction.** Every new optional-dependency extension
  requires a `try/except` block in `__init__.py`, an `__all__` append,
  and a docs note explaining the silent-omission behaviour.

- **Inconsistency across extensions.** With dagster excluded, two
  conventions coexist.  Contributors have to check which pattern applies.

Pure-Python extensions (`batch`, `cache`, `glob`, `observe`, `partition`,
`transfer`) remain unconditionally re-exported — they add zero import
cost and are part of the core value proposition.

## Decision

Remove the conditional `try/except ImportError` re-export blocks for all
optional-dependency extensions (`arrow`, `otel`, `pydantic`, `yaml`) from
`remote_store/__init__.py` and `__all__`.

Users import optional extensions from their canonical module path:

```python
from remote_store.ext.arrow import pyarrow_fs
from remote_store.ext.otel import otel_hooks, otel_observe
from remote_store.ext.pydantic import from_pydantic
from remote_store.ext.yaml import from_yaml
from remote_store.ext.dagster import dagster_io_manager
```

This makes all optional-dependency extensions consistent — including
dagster, which was already using this pattern.

The rest of ADR-0008 (public-API-only rule, `__all__`, lifecycle rules,
error propagation, dependency rules, development lifecycle, third-party
conventions) remains in effect.

## Consequences

- **Faster imports.** `import remote_store` no longer eagerly loads
  pyarrow, opentelemetry, pydantic, or ruamel.yaml.
- **One import pattern.** All optional-dependency extensions use the same
  `from remote_store.ext.<name> import ...` path.  No special cases.
- **Simpler `__init__.py`.** Four `try/except` blocks and their `__all__`
  appends are removed.
- **Minor breaking change.** `from remote_store import pyarrow_fs` (and
  similar) no longer works.  Mitigated by: (a) no internal usage exists,
  (b) the canonical import path still works, (c) a CHANGELOG entry
  guides migration.
- **Pure-Python extensions unchanged.** `from remote_store import
  batch_delete, glob_files, observe` etc. continue to work.
- **Future direction.** If top-level convenience imports are ever wanted back
  without the eager-load cost, Python 3.7+ module-level `__getattr__` in
  `__init__.py` enables lazy loading -- the symbol appears in the namespace
  but the heavy dependency only imports on first access.  This avoids
  re-introducing the `try/except ImportError` pattern.
