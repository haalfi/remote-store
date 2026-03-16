"""Dagster Definitions — wires assets, IO managers, and resources.

Run with:  dagster dev -f definitions.py
"""

from __future__ import annotations

import io
from typing import Any

import pyarrow.parquet as pq
from assets.bronze import bronze_bern, bronze_lugano, bronze_zurich, meteo_stations
from assets.gold import gold_alerts, gold_daily_summary, gold_station_stats
from assets.silver import silver_measurements
from dagster import Definitions
from stores import gold, silver

from remote_store.ext.dagster import ParquetSerializer, remote_store_io_manager


class PolarsParquetSerializer(ParquetSerializer):
    """Parquet serializer that deserializes to Polars (no pandas needed)."""

    def deserialize(self, data: bytes) -> Any:
        import polars as pl

        table = pq.read_table(io.BytesIO(data))
        return pl.from_arrow(table)


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
        "silver_io_manager": remote_store_io_manager(silver, serializer=PolarsParquetSerializer()),
        "gold_io_manager": remote_store_io_manager(gold, serializer=PolarsParquetSerializer()),
    },
)
