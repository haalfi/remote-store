"""Dagster Definitions — wires assets, IO managers, and resources.

Run with:  dagster dev -f definitions.py
"""

from __future__ import annotations

from assets.bronze import bronze_bern, bronze_lugano, bronze_zurich, meteo_stations
from assets.gold import gold_alerts, gold_daily_summary, gold_station_stats
from assets.silver import silver_measurements
from dagster import Definitions
from stores import gold, silver

from remote_store.ext.dagster import remote_store_io_manager

defs = Definitions(
    assets=[
        # Bronze (raw ingest via ext.transfer)
        meteo_stations,
        bronze_bern,
        bronze_zurich,
        bronze_lugano,
        # Silver (clean + unify)
        silver_measurements,
        # Gold (analytics)
        gold_daily_summary,
        gold_station_stats,
        gold_alerts,
    ],
    resources={
        "silver_io_manager": remote_store_io_manager(silver, serializer="parquet"),
        "gold_io_manager": remote_store_io_manager(gold, serializer="parquet"),
    },
)
