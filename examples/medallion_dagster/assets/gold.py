"""Gold layer — analytics aggregations over the Silver measurements.

All assets read from the Silver layer via the Dagster IO manager and
return Polars DataFrames serialized to Parquet.
"""

from __future__ import annotations

import polars as pl
from dagster import AssetIn, asset


@asset(
    group_name="gold",
    io_manager_key="gold_io_manager",
    ins={"silver_measurements": AssetIn(key_prefix=[], input_manager_key="silver_io_manager")},
)
def gold_daily_summary(silver_measurements: pl.DataFrame) -> pl.DataFrame:
    """Daily aggregates per station: avg/min/max temperature, precipitation sum."""
    # Extract date from timestamp.
    df = silver_measurements.with_columns(pl.col("timestamp").dt.date().alias("date"))

    agg_exprs: list[pl.Expr] = []
    if "tre200d0" in df.columns:
        agg_exprs.append(pl.col("tre200d0").mean().alias("avg_temp"))
    if "tre200dn" in df.columns:
        agg_exprs.append(pl.col("tre200dn").min().alias("min_temp"))
    if "tre200dx" in df.columns:
        agg_exprs.append(pl.col("tre200dx").max().alias("max_temp"))
    if "rre150d0" in df.columns:
        agg_exprs.append(pl.col("rre150d0").sum().alias("total_precip"))

    result = df.group_by(["station", "date"]).agg(agg_exprs).sort(["station", "date"])

    print(f"  Gold daily_summary: {len(result)} rows")
    return result


@asset(
    group_name="gold",
    io_manager_key="gold_io_manager",
    ins={"silver_measurements": AssetIn(key_prefix=[], input_manager_key="silver_io_manager")},
)
def gold_station_stats(silver_measurements: pl.DataFrame) -> pl.DataFrame:
    """Per-station statistics: row count, date range, mean temperature."""
    agg_exprs: list[pl.Expr] = [
        pl.len().alias("row_count"),
        pl.col("timestamp").min().alias("earliest"),
        pl.col("timestamp").max().alias("latest"),
    ]
    if "tre200d0" in silver_measurements.columns:
        agg_exprs.append(pl.col("tre200d0").mean().alias("mean_temp"))
        agg_exprs.append(pl.col("tre200d0").null_count().alias("temp_nulls"))

    result = silver_measurements.group_by("station").agg(agg_exprs).sort("station")

    print(f"  Gold station_stats: {len(result)} rows")
    return result


@asset(
    group_name="gold",
    io_manager_key="gold_io_manager",
    ins={"silver_measurements": AssetIn(key_prefix=[], input_manager_key="silver_io_manager")},
)
def gold_alerts(silver_measurements: pl.DataFrame) -> pl.DataFrame:
    """Flag days where measurements exceed thresholds.

    Thresholds:
    - Frost: min temperature < 0 C
    - Heat: max temperature > 30 C
    """
    df = silver_measurements.with_columns(pl.col("timestamp").dt.date().alias("date"))

    alert_exprs: list[pl.Expr] = []
    if "tre200dn" in df.columns:
        alert_exprs.append((pl.col("tre200dn").min() < 0).alias("frost_alert"))
    if "tre200dx" in df.columns:
        alert_exprs.append((pl.col("tre200dx").max() > 30).alias("heat_alert"))

    if not alert_exprs:
        # No temperature columns available — return empty frame matching normal schema.
        return pl.DataFrame({"station": [], "date": [], "frost_alert": [], "heat_alert": []})

    result = df.group_by(["station", "date"]).agg(alert_exprs).sort(["station", "date"])

    # Keep only rows with at least one alert.
    alert_cols = [c for c in result.columns if c.endswith("_alert")]
    if alert_cols:
        any_alert = pl.any_horizontal(pl.col(c) for c in alert_cols)
        result = result.filter(any_alert)

    print(f"  Gold alerts: {len(result)} alert-days")
    return result
