"""Store construction — HTTP source + local medallion lake.

Extension composition chain (innermost → outermost):
  ReadOnlyHttpBackend → ext.cache (1h TTL) → ext.otel (spans + metrics)

The local lake uses Store.child() for Bronze / Silver / Gold isolation.
"""

from __future__ import annotations

import os

from otel_setup import configure_otel

# Activate OTel *before* any Store operations so traces are captured.
configure_otel()

from remote_store import Store  # noqa: E402
from remote_store.backends import LocalBackend, ReadOnlyHttpBackend  # noqa: E402
from remote_store.ext.cache import cache  # noqa: E402
from remote_store.ext.otel import otel_observe  # noqa: E402

# ---------------------------------------------------------------------------
# Source: MeteoSwiss open data (read-only, zero credentials)
# ---------------------------------------------------------------------------

# RS_SHOWCASE_SOURCE_URL overrides the upstream base URL — point it at a mirror,
# a cache, or (in tests) a local HTTP server serving fixture CSVs.
_SOURCE_URL = os.environ.get("RS_SHOWCASE_SOURCE_URL", "https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/")

_http = Store(
    ReadOnlyHttpBackend(
        base_url=_SOURCE_URL,
        timeout=60.0,
    )
)
_cached = cache(_http, ttl=3600)
meteo_store = otel_observe(_cached)

# ---------------------------------------------------------------------------
# Sink: local medallion lake
# ---------------------------------------------------------------------------

# The lake is observed too: swap LocalBackend for S3Backend / AzureBackend (see
# the README "Swapping Backends" section) and every Bronze write, Silver/Gold IO
# round-trip, and read keeps emitting OTel spans — observability is not tied to
# the HTTP source. RS_SHOWCASE_LAKE_ROOT relocates the local lake (used by tests).
_LAKE_ROOT = os.environ.get("RS_SHOWCASE_LAKE_ROOT", "./data/showcase")

lake = otel_observe(Store(LocalBackend(root=_LAKE_ROOT)))
bronze = lake.child("bronze")
silver = lake.child("silver")
gold = lake.child("gold")


def print_cache_stats() -> None:
    """Print cache hit/miss statistics (call after Bronze ingestion)."""
    stats = _cached.stats
    total = stats.hits + stats.misses
    ratio = f"{stats.hits / total:.0%}" if total else "n/a"
    print(f"  Cache stats: {stats.hits} hits, {stats.misses} misses, hit ratio {ratio}, {stats.size} entries cached")
