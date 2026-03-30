"""Dagster Definitions — wires assets, IO managers, and resources.

Run with:  dagster dev -f definitions.py
"""

from __future__ import annotations

from assets.bronze import bronze_bern, bronze_lugano, bronze_zurich, meteo_stations
from assets.gold import gold_alerts, gold_daily_summary, gold_station_stats
from assets.silver import silver_measurements
from dagster import Definitions
from stores import gold, silver

from remote_store.ext.dagster import ParquetSerializer, dagster_io_manager

# ParquetSerializer.deserialize() returns a PyArrow Table by default.
# Assets convert to their preferred framework (e.g. pl.from_arrow(table)
# or table.to_pandas()) as needed.

defs = Definitions(
    assets=[
        # Bronze (raw ingest via read_bytes + write)
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
        "silver_io_manager": dagster_io_manager(silver, serializer=ParquetSerializer()),
        "gold_io_manager": dagster_io_manager(gold, serializer=ParquetSerializer()),
    },
)
