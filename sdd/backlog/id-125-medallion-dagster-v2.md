# ID-125 — Update medallion showcase to Dagster v2 resource pattern
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Replace `dagster_io_manager(store)` calls in `examples/medallion_dagster/`
with `RemoteStoreIOManager`. Demonstrates the config-driven pattern.
Examples get copied verbatim, so a stale one teaches a superseded pattern
from a first-contact surface.

## Correction, 2026-09-27

"A superseded pattern" is not what the published guide says.
`docs-src/guides/dagster.md:167-170` recommends v1 (`dagster_io_manager`)
"when you already have a Store" and v2 (`RemoteStoreIOManager`) "when Dagster
should construct the Store from config"; `dagster_io_manager`
(`src/remote_store/ext/dagster.py:365`) carries no deprecation. The example
already has its Stores: `examples/medallion_dagster/stores.py:50-53` builds
`lake = otel_observe(Store(LocalBackend(...)))` and derives `silver` and
`gold` with `.child()`, which `definitions.py:35-36` pass to the two
`dagster_io_manager` calls. `RemoteStoreIOManager` builds its own Store from
`backend_type`/`backend_options` (`dagster.py:508-532`), so a straight swap
would drop the `otel_observe` wrapping; its `serializer: str` field accepts
`"parquet"` (`dagster.py:205`), so the serializer is not a loss. Whether the
item is still wanted is the open decision the index names. Found by the
ADR-0040 § 3 conversion, which re-derived the item before writing its index
diagnosis.
