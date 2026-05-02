# Medallion + Dagster Showcase
<!-- doc: dual dest=examples/medallion-dagster.md -->

A self-contained Dagster project demonstrating remote-store's value proposition
through a real-world **medallion architecture** (Bronze → Silver → Gold) over
live [MeteoSwiss](https://www.meteoswiss.admin.ch/) weather station data.

## What This Demonstrates

Four remote-store extensions composing without conflict:

| Extension | Role |
|-----------|------|
| `ReadOnlyHttpBackend` | Read-only backend fetching live CSV data via HTTP |
| `ext.cache` | TTL-based caching — avoids redundant HTTP downloads |
| `ext.otel` | OpenTelemetry spans + metrics on every storage operation |
| `ext.dagster` | 3-line IO manager wrapping any Store for Dagster |

## Prerequisites

- Python 3.10+
- Network access to `data.geo.admin.ch` (Swiss open government data, no credentials)

## Setup

```bash
cd examples/medallion_dagster

# Install remote-store with required extras + showcase dependencies
pip install -e "../../[dagster,arrow,otel,requests]" polars dagster-webserver opentelemetry-sdk
```

## Running

```bash
dagster dev -f definitions.py
```

Open the Dagster UI (typically http://localhost:3000) and materialize all assets.

## Architecture

```
MeteoSwiss HTTP ──→ ext.cache (1h TTL) ──→ ext.otel (traces)
       │
       └──→ read_bytes + write ──→ Bronze (raw CSV)
                                      │
                                      ├──→ Silver (cleaned Parquet)
                                      │
                                      └──→ Gold (aggregated Parquet)
```

### Bronze Layer (raw ingest)
- **`meteo_stations`** — station metadata CSV
- **`bronze_bern`**, **`bronze_zurich`**, **`bronze_lugano`** — daily weather CSVs
- Uses `read_bytes` + `write` directly (file-level copy, no IO manager)

### Silver Layer (clean + unify)
- **`silver_measurements`** — all stations cleaned, unified, stored as Parquet
- Parses semicolon-delimited CSV, normalizes timestamps, drops null rows
- Uses Dagster IO manager with `ParquetSerializer`

### Gold Layer (analytics)
- **`gold_daily_summary`** — daily avg/min/max temperature, precipitation per station
- **`gold_station_stats`** — per-station row counts, date ranges, mean temperature
- **`gold_alerts`** — frost (< 0°C) and heat (> 30°C) alert days

## What to Observe

### Dagster UI
- Asset graph showing Bronze → Silver → Gold dependencies
- Materialization metadata (path, size) on Silver/Gold assets

### Terminal Output
- OTel spans (JSON lines) for every `read_bytes()`, `exists()`, `get_file_info()` call
- Cache hit/miss stats after each Bronze ingest
- Row counts from Silver and Gold transforms

### Cache Benefit
Run materialization twice within one hour. The second run hits the cache for
all Bronze `read_bytes()` calls — visible in cache stats (4 hits, 0 misses)
and shorter OTel span durations.

## Swapping Backends

The core value proposition: change one line in `stores.py` to swap the lake
backend from local filesystem to S3 or Azure:

```python
# Before (local)
lake = Store(LocalBackend(root="./data/showcase"))

# After (S3)
lake = Store(S3Backend(bucket="my-bucket", prefix="showcase"))
```

Everything else — caching, observability, Dagster integration —
works unchanged.

## Data Source

[MeteoSwiss Automatic Weather Stations (SMN)](https://data.geo.admin.ch/ch.meteoschweiz.ogd-smn/)
— Swiss Federal Office of Meteorology and Climatology. Public domain data,
no API keys required.

Stations used: Bern-Zollikofen (`ber`), Zurich-Kloten (`klo`), Lugano (`lug`).
Granularity: daily measurements.

## See also

- [Dagster](../../docs-src/how-to/dagster.md) — Dagster integration guide
- [Data Lake Patterns](../../docs-src/how-to/data-lake-patterns.md) — medallion architecture patterns
- [Architecture: Medallion + Dagster Showcase](../../sdd/research/research-medallion-dagster-showcase.md) — detailed design rationale, store topology, and Dagster asset graph
- [Source: `examples/medallion_dagster/`](https://github.com/haalfi/remote-store/tree/master/examples/medallion_dagster/)
