# BK-008: Medallion + Dagster Showcase — Implementation Plan

## Overview

Self-contained runnable showcase in `examples/showcase_medallion_dagster/` demonstrating a medallion architecture (Bronze/Silver/Gold) orchestrated by Dagster, composing 6 extensions over live MeteoSwiss weather data.

All prerequisites are shipped (ID-075 ext.dagster, ID-082 HTTP backend, ext.cache, ext.observe, ext.otel, ext.transfer, ext.arrow).

## File Structure

```
examples/showcase_medallion_dagster/
├── README.md
├── pyproject.toml
├── otel_setup.py
├── stores.py
├── definitions.py
└── assets/
    ├── __init__.py
    ├── bronze.py
    ├── silver.py
    └── gold.py
```

## Implementation Steps

### Step 1: `pyproject.toml` — Showcase-specific dependencies
- Minimal project config referencing `remote-store[dagster,arrow,otel,requests]`, `polars>=0.20`, `dagster-webserver>=1.9`, `opentelemetry-sdk>=1.20`
- Not a publishable package — just dependency pinning for `pip install`

### Step 2: `otel_setup.py` — Console OTel exporter
- `configure_otel()` function setting up `TracerProvider` + `MeterProvider` with console exporters
- Zero external infrastructure (no Jaeger/Grafana)
- Copied from research doc §8 with minor adjustments

### Step 3: `stores.py` — Store construction with full composition chain
- `meteo_store`: `ReadOnlyHttpBackend` → `cached_store(ttl=3600)` → `otel_observe()`
- `lake`: `LocalBackend("./data/showcase")` with `bronze`, `silver`, `gold` children
- Expose `cached` reference for stats access
- Call `configure_otel()` at module level so traces are active when Dagster imports

### Step 4: `assets/__init__.py` — Package marker
- Empty or minimal `__init__.py`

### Step 5: `assets/bronze.py` — Raw ingest via ext.transfer
- 4 assets: `meteo_stations`, `bronze_bern`, `bronze_zurich`, `bronze_lugano`
- Each uses `transfer(meteo_store, src, bronze, dst, overwrite=True)`
- Bronze assets return `None` (file-level transfer, no IO manager)
- Log cache stats after transfers
- Group: `"bronze"`

### Step 6: `assets/silver.py` — CSV → cleaned Parquet
- `silver_measurements` asset depending on all 4 bronze assets
- Reads CSV files from `bronze` store using `store.read_bytes()`
- Polars for CSV parsing (semicolon delimiter) and cleaning:
  - Parse timestamps to datetime
  - Add station code column
  - Drop rows with all-null measurements
  - Concatenate all stations into one DataFrame
- Returns `pl.DataFrame` (serialized by Dagster IO manager via `silver_io_manager`)
- Group: `"silver"`, `io_manager_key="silver_io_manager"`

### Step 7: `assets/gold.py` — Analytics aggregations
- 3 assets, all depending on `silver_measurements`:
  1. `gold_daily_summary`: daily avg/min/max temperature, precipitation sum per station
  2. `gold_station_stats`: per-station coverage stats, mean temperature
  3. `gold_alerts`: flag days exceeding thresholds (frost <0°C, heat >30°C)
- Each returns `pl.DataFrame`, serialized by `gold_io_manager`
- Group: `"gold"`, `io_manager_key="gold_io_manager"`

### Step 8: `definitions.py` — Dagster wiring
- Import all assets from `assets/` subpackage
- Wire IO managers: `silver_io_manager` and `gold_io_manager` using `remote_store_io_manager(store, serializer="parquet")`
- Single `Definitions(assets=[...], resources={...})` object

### Step 9: `README.md` — Setup instructions and walkthrough
- What the showcase demonstrates (6 extensions, medallion pattern)
- Prerequisites and installation
- How to run (`dagster dev -f definitions.py`)
- What each layer does
- What to observe in the Dagster UI and terminal OTel output
- How to swap backends (one-line change story)

### Step 10: Backlog update
- Mark BK-008 as `[~]` in `sdd/BACKLOG.md`
- Add CHANGELOG entry

## Key Design Decisions

1. **Polars over pandas** — lighter, faster, no C extension compile. Research doc uses `pl.DataFrame`.
2. **Bronze = transfer (no IO manager)** — raw file copy, not DataFrame serialization. Shows both patterns.
3. **Silver/Gold = IO manager** — DataFrame → Parquet via `ParquetSerializer`. Note: `ParquetSerializer.deserialize()` returns pandas DataFrame, so Silver→Gold reads will get pandas. Gold assets will convert if needed.
4. **OTel console exporter** — zero infrastructure requirement. Users see spans in terminal.
5. **No `__init__.py` re-exports** — assets are imported directly in `definitions.py`.
6. **Module-level OTel init in `stores.py`** — ensures tracing is active before any store operation.

## What Won't Be Done

- No tests for the showcase (it's an example, not library code; runs against live HTTP)
- No CI integration (requires network access to MeteoSwiss)
- No cloud deployment docs
- No Dagster sensors/schedules
- No DuckDB integration (mentioned as optional in research doc)

## Verification

After implementation, verify the showcase files are syntactically correct by importing them. Full end-to-end verification (`dagster dev`) requires network access + dagster installed, which may not be available in this environment.
