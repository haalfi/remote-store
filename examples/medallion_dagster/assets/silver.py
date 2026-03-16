"""Silver layer — clean and unify Bronze CSVs into a single Parquet dataset.

Reads raw semicolon-delimited CSVs from the Bronze store, parses timestamps,
adds station metadata, drops rows with missing critical measurements, and
returns a unified Polars DataFrame.
"""

from __future__ import annotations

import io

import polars as pl
from dagster import AssetKey, asset
from stores import bronze

# MeteoSwiss CSV uses semicolon delimiter. Key columns present in daily data:
# - station_abbr: 3-letter station code (uppercase)
# - reference_timestamp: timestamp (DD.MM.YYYY HH:MM)
# - tre200d0: daily mean temperature (C)
# - tre200dn: daily min temperature (C)
# - tre200dx: daily max temperature (C)
# - rre150d0: daily precipitation sum (mm)
# - ure200d0: daily mean relative humidity (%)
# - prestad0: daily mean station pressure (hPa)

# Columns we keep. Not all stations have all columns; we use a safe subset.
_MEASUREMENT_COLS = [
    "tre200d0",  # mean temp
    "tre200dn",  # min temp
    "tre200dx",  # max temp
    "rre150d0",  # precipitation
    "ure200d0",  # humidity
    "prestad0",  # pressure
]

_STATION_CODES = ["ber", "klo", "lug"]


def _read_station_csv(station: str) -> pl.DataFrame:
    """Read a single station CSV from the Bronze store."""
    raw = bronze.read_bytes(f"stations/{station}/daily.csv")
    df = pl.read_csv(
        io.BytesIO(raw),
        separator=";",
        infer_schema_length=10_000,
        try_parse_dates=False,
        null_values=["-"],
    )
    # Rename station_abbr to station and lowercase for consistency.
    df = df.with_columns(pl.col("station_abbr").str.to_lowercase().alias("station"))
    return df


def _parse_timestamp(df: pl.DataFrame) -> pl.DataFrame:
    """Parse the 'reference_timestamp' column to a proper datetime."""
    # MeteoSwiss daily data uses DD.MM.YYYY HH:MM format (e.g., 01.01.2026 00:00).
    return df.with_columns(
        pl.col("reference_timestamp")
        .cast(pl.String)
        .str.strptime(pl.Datetime, "%d.%m.%Y %H:%M", strict=False)
        .alias("timestamp")
    )


def _select_and_cast(df: pl.DataFrame) -> pl.DataFrame:
    """Select relevant columns and cast measurement columns to Float64."""
    # Keep station, timestamp, and available measurement columns.
    available = [c for c in _MEASUREMENT_COLS if c in df.columns]
    keep = ["station", "timestamp", *available]
    df = df.select([c for c in keep if c in df.columns])

    # Cast measurement columns to Float64 (they may arrive as String).
    for col in available:
        if col in df.columns and df[col].dtype != pl.Float64:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))

    return df


@asset(
    group_name="silver",
    io_manager_key="silver_io_manager",
    deps=[
        AssetKey("bronze_bern"),
        AssetKey("bronze_zurich"),
        AssetKey("bronze_lugano"),
        AssetKey("meteo_stations"),
    ],
)
def silver_measurements() -> pl.DataFrame:
    """Clean and unify all station data into a single Parquet dataset.

    - Parses timestamps (UTC)
    - Normalizes semicolon-delimited CSV to columnar format
    - Drops rows missing timestamp or all measurements
    - Adds station code
    - Concatenates all stations
    """
    frames: list[pl.DataFrame] = []

    for station in _STATION_CODES:
        df = _read_station_csv(station)
        df = _parse_timestamp(df)
        df = _select_and_cast(df)
        # Drop rows where timestamp is null (unparseable).
        df = df.filter(pl.col("timestamp").is_not_null())
        frames.append(df)

    combined = pl.concat(frames, how="diagonal_relaxed")

    # Drop rows where ALL measurement columns are null.
    measurement_cols = [c for c in _MEASUREMENT_COLS if c in combined.columns]
    if measurement_cols:
        all_null = pl.all_horizontal(pl.col(c).is_null() for c in measurement_cols)
        combined = combined.filter(~all_null)

    # Sort by station and timestamp for clean output.
    combined = combined.sort(["station", "timestamp"])

    print(
        f"  Silver: {len(combined)} rows, {len(combined.columns)} columns, "
        f"stations: {combined['station'].unique().to_list()}"
    )

    return combined
