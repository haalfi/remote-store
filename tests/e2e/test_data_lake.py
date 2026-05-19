"""End-to-end data lake medallion test.

Runs the full Bronze / Silver / Gold pipeline against real Docker backends,
exercising extension interplay: ext.arrow, ext.partition, ext.batch,
ext.cache, and ext.observe working together.

Requires: ``docker compose -f infra/docker-compose.yml up -d``

This is the integration counterpart of ``examples/notebooks/04_data_lake_medallion.ipynb``
which runs only on MemoryBackend.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

pyarrow = pytest.importorskip("pyarrow")
polars = pytest.importorskip("polars")

import polars as pl  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from remote_store import Store  # noqa: E402, TC001
from remote_store.ext.arrow import pyarrow_fs  # noqa: E402
from remote_store.ext.batch import batch_delete, batch_exists  # noqa: E402
from remote_store.ext.cache import cache  # noqa: E402
from remote_store.ext.observe import observe  # noqa: E402
from remote_store.ext.partition import parse_partition, partition_path  # noqa: E402
from tests.e2e.conftest import azurite_skip, minio_skip, s3_pyarrow_skip  # noqa: E402

# ---------------------------------------------------------------------------
# Shared test data generator
# ---------------------------------------------------------------------------

SENSORS = [
    "sensor-01",
    "sensor-02",
    "sensor-03",
    "sensor-04",
    "sensor-05",
    "sensor-06",
    "sensor-07",
    "sensor-08",
]
MACHINES = [
    "press-A",
    "press-B",
    "lathe-1",
    "lathe-2",
    "welder-1",
    "welder-2",
    "oven-1",
    "oven-2",
]
START = datetime(2026, 3, 1)
DAYS = 2
READINGS_PER_HOUR = 3  # fewer than notebook for speed


def _generate_raw_rows() -> list[dict[str, object]]:
    """Generate raw sensor rows with intentional quality issues."""
    rng = random.Random(42)
    rows: list[dict[str, object]] = []

    for day_offset in range(DAYS):
        for hour in range(24):
            for reading in range(READINGS_PER_HOUR):
                for i, sensor_id in enumerate(SENSORS):
                    ts = START + timedelta(
                        days=day_offset,
                        hours=hour,
                        minutes=reading * 20,
                    )
                    base_temp = 35 + i * 6
                    temp: float | None = round(base_temp + rng.gauss(0, 3), 1)
                    vibration = round(rng.uniform(0.1, 5.0), 2)

                    # ~5% null readings
                    if rng.random() < 0.05:
                        temp = None
                    # ~2% out-of-range spikes
                    elif rng.random() < 0.02:
                        temp = round(rng.uniform(200, 500), 1)

                    # ~2% type drift: sensor ID as integer string
                    sid = str(i + 1) if rng.random() < 0.02 else sensor_id

                    rows.append(
                        {
                            "timestamp": ts.isoformat(),
                            "sensor_id": sid,
                            "machine": MACHINES[i],
                            "temperature_c": temp,
                            "vibration_mm_s": vibration,
                        }
                    )

    # ~3% duplicate rows
    n_dupes = int(len(rows) * 0.03)
    dupes = rng.choices(rows, k=n_dupes)
    rows.extend(dupes)
    rng.shuffle(rows)
    return rows


# ---------------------------------------------------------------------------
# Medallion pipeline logic (backend-agnostic)
# ---------------------------------------------------------------------------


def _write_bronze(bronze: Store, raw_rows: list[dict[str, object]]) -> int:
    """Ingest raw data into Bronze layer as daily Parquet files.

    Returns total row count written.
    """
    bronze_fs = pyarrow_fs(bronze)
    raw_table = pa.table(
        {
            "timestamp": [r["timestamp"] for r in raw_rows],
            "sensor_id": [r["sensor_id"] for r in raw_rows],
            "machine": [r["machine"] for r in raw_rows],
            "temperature_c": [r["temperature_c"] for r in raw_rows],
            "vibration_mm_s": [r["vibration_mm_s"] for r in raw_rows],
        }
    )

    total = 0
    for day_offset in range(DAYS):
        date_str = (START + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        mask = pc.starts_with(raw_table["timestamp"], date_str)
        day_table = raw_table.filter(mask)
        path = f"readings/{date_str}.parquet"
        pq.write_table(day_table, path, filesystem=bronze_fs)
        total += day_table.num_rows

    return total


def _clean_to_silver(bronze: Store, silver: Store) -> pl.DataFrame:
    """Read Bronze, clean, deduplicate, write partitioned Silver.

    Returns cleaned DataFrame.
    """
    bronze_fs = pyarrow_fs(bronze)
    silver_fs = pyarrow_fs(silver)

    bronze_dataset = pq.read_table("readings", filesystem=bronze_fs)
    df = pl.from_arrow(bronze_dataset)

    silver_df = (
        df.with_columns(
            pl.col("timestamp").str.to_datetime().alias("timestamp"),
        )
        .with_columns(
            pl.when(pl.col("sensor_id").str.len_chars() <= 2)
            .then(
                pl.col("sensor_id").str.zfill(2).str.replace(r"^", "sensor-"),
            )
            .otherwise(pl.col("sensor_id"))
            .alias("sensor_id"),
        )
        .unique()
        .filter(pl.col("temperature_c").is_not_null())
        .filter(pl.col("temperature_c").is_between(0, 150))
        .sort("timestamp", "sensor_id")
    )

    silver_with_date = silver_df.with_columns(
        pl.col("timestamp").dt.date().cast(pl.String).alias("date"),
    )

    ds.write_dataset(
        silver_with_date.to_arrow(),
        "readings",
        filesystem=silver_fs,
        format="parquet",
        partitioning=ds.partitioning(pa.schema([("date", pa.string())])),
        existing_data_behavior="overwrite_or_ignore",
    )

    return silver_df


def _aggregate_to_gold(silver_df: pl.DataFrame, gold: Store) -> tuple[int, int]:
    """Compute Gold aggregates from Silver DataFrame.

    Returns (hourly_count, daily_count).
    """
    gold_fs = pyarrow_fs(gold)

    # Hourly machine stats
    hourly_stats = (
        silver_df.with_columns(
            pl.col("timestamp").dt.truncate("1h").alias("hour"),
        )
        .group_by("hour", "machine", "sensor_id")
        .agg(
            pl.col("temperature_c").mean().round(1).alias("avg_temp_c"),
            pl.col("temperature_c").min().alias("min_temp_c"),
            pl.col("temperature_c").max().alias("max_temp_c"),
            pl.col("vibration_mm_s").mean().round(2).alias("avg_vibration"),
            pl.col("vibration_mm_s").max().alias("max_vibration"),
            pl.len().alias("reading_count"),
        )
        .with_columns(
            (pl.col("max_temp_c") > 75).alias("temp_alert"),
            (pl.col("max_vibration") > 4.5).alias("vibration_alert"),
        )
        .sort("hour", "machine")
    )

    pq.write_table(
        hourly_stats.to_arrow(),
        "hourly_machine_stats.parquet",
        filesystem=gold_fs,
    )

    # Daily sensor health
    daily_health = (
        silver_df.with_columns(
            pl.col("timestamp").dt.date().alias("date"),
        )
        .group_by("date", "sensor_id", "machine")
        .agg(
            pl.len().alias("total_readings"),
            pl.col("temperature_c").mean().round(1).alias("avg_temp_c"),
            pl.col("temperature_c").std().round(2).alias("temp_std_dev"),
            (pl.col("temperature_c") > 75).sum().alias("temp_alerts"),
            (pl.col("vibration_mm_s") > 4.5).sum().alias("vibration_alerts"),
        )
        .sort("date", "sensor_id")
    )

    pq.write_table(
        daily_health.to_arrow(),
        "daily_sensor_health.parquet",
        filesystem=gold_fs,
    )

    return len(hourly_stats), len(daily_health)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _assert_bronze(bronze: Store, total_rows: int) -> None:
    """Verify Bronze layer contents."""
    files = list(bronze.list_files("readings", recursive=True))
    assert len(files) == DAYS, f"Expected {DAYS} daily files, got {len(files)}"

    for f in files:
        assert str(f.path).endswith(".parquet")
        assert f.size > 0

    # Round-trip: read back and verify row count
    bronze_fs = pyarrow_fs(bronze)
    table = pq.read_table("readings", filesystem=bronze_fs)
    assert table.num_rows == total_rows


def _assert_silver(silver: Store, silver_df: pl.DataFrame) -> None:
    """Verify Silver layer contents."""
    files = list(silver.list_files("readings", recursive=True))
    assert len(files) == DAYS, f"Expected {DAYS} partition files, got {len(files)}"

    # All sensor IDs should be normalized
    sensor_ids = silver_df["sensor_id"].unique().to_list()
    for sid in sensor_ids:
        assert sid.startswith("sensor-"), f"Unnormalized sensor ID: {sid}"

    # No nulls in temperature
    assert silver_df["temperature_c"].null_count() == 0

    # No out-of-range temperatures
    assert silver_df["temperature_c"].min() >= 0  # type: ignore[operator]
    assert silver_df["temperature_c"].max() <= 150  # type: ignore[operator]

    # Fewer rows than raw (duplicates, nulls, out-of-range removed)
    # Silver should have strictly fewer rows -- quality issues were injected

    # Verify Hive partitions are readable
    silver_fs = pyarrow_fs(silver)
    roundtrip = pq.read_table("readings", filesystem=silver_fs)
    assert roundtrip.num_rows == len(silver_df)


def _assert_gold(gold: Store, hourly_count: int, daily_count: int) -> None:
    """Verify Gold layer contents."""
    gold_fs = pyarrow_fs(gold)

    hourly = pq.read_table("hourly_machine_stats.parquet", filesystem=gold_fs)
    assert hourly.num_rows == hourly_count

    health = pq.read_table("daily_sensor_health.parquet", filesystem=gold_fs)
    assert health.num_rows == daily_count

    # Hourly stats should have expected columns
    assert "avg_temp_c" in hourly.column_names
    assert "temp_alert" in hourly.column_names
    assert "reading_count" in hourly.column_names

    # Daily health should cover all days and sensors
    dates = health.column("date").to_pylist()
    assert len(set(dates)) == DAYS
    sensors = health.column("sensor_id").to_pylist()
    assert len(set(sensors)) == len(SENSORS)


# ---------------------------------------------------------------------------
# Extension integration helpers
# ---------------------------------------------------------------------------


def _test_partition_helpers(silver: Store) -> None:
    """Verify ext.partition round-trips through real object keys."""
    # Build a partition path and write through it
    path = partition_path("data.parquet", year="2026", month="03")
    assert path == "year=2026/month=03/data.parquet"

    silver.write(path, b"partition-test")
    assert silver.exists(path)

    parsed = parse_partition(path)
    assert parsed.partitions == {"year": "2026", "month": "03"}
    assert parsed.filename == "data.parquet"

    # Clean up
    silver.delete(path)


def _test_batch_operations(gold: Store) -> None:
    """Verify ext.batch against real backend."""
    # Write test files
    paths = [f"batch-test/file-{i}.txt" for i in range(5)]
    for p in paths:
        gold.write(p, f"content-{p}".encode())

    # batch_exists
    existence = batch_exists(gold, paths)
    assert all(existence.values())

    # batch_delete with concurrent=True (real network parallelism)
    result = batch_delete(gold, paths, concurrent=True, max_workers=3)
    assert len(result.succeeded) == len(paths)
    assert len(result.failed) == 0

    # Verify deletion
    existence = batch_exists(gold, paths)
    assert not any(existence.values())


def _test_cache_layer(gold: Store) -> None:
    """Verify ext.cache caching and invalidation against real backend."""
    gold.write("cache-test.txt", b"original")

    cstore = cache(gold, ttl=60)

    # First read populates cache
    content1 = cstore.read_bytes("cache-test.txt")
    assert content1 == b"original"

    stats = cstore.stats
    assert stats.misses >= 1

    # Second read should hit cache
    content2 = cstore.read_bytes("cache-test.txt")
    assert content2 == b"original"
    stats2 = cstore.stats
    assert stats2.hits >= 1

    # Write through cached store should invalidate
    cstore.write("cache-test.txt", b"updated", overwrite=True)
    content3 = cstore.read_bytes("cache-test.txt")
    assert content3 == b"updated"

    # Clean up
    cstore.delete("cache-test.txt")


def _test_observe_hooks(lake: Store) -> None:
    """Verify ext.observe fires hooks against real backend."""
    events: list[str] = []

    def on_write(event: object) -> None:
        events.append(f"write:{event.path}")  # type: ignore[attr-defined]

    def on_delete(event: object) -> None:
        events.append(f"delete:{event.path}")  # type: ignore[attr-defined]

    observed = observe(lake, on_write=on_write, on_delete=on_delete)
    observed.write("observe-test.txt", b"hello")
    observed.delete("observe-test.txt")

    assert "write:observe-test.txt" in events
    assert "delete:observe-test.txt" in events


def _test_atomic_writes(lake: Store) -> None:
    """Verify open_atomic() against real backend."""
    with lake.open_atomic("atomic-test.txt") as f:
        f.write(b"atomic content")

    assert lake.exists("atomic-test.txt")
    assert lake.read_bytes("atomic-test.txt") == b"atomic content"

    lake.delete("atomic-test.txt")


# ---------------------------------------------------------------------------
# Full pipeline test (parametrized by backend)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.spec("ID-050")
class TestDataLakeMedallion:
    """Full medallion pipeline against each backend."""

    def _run_pipeline(self, lake: Store) -> None:
        """Execute the complete pipeline and verify all layers."""
        bronze = lake.child("bronze")
        silver = lake.child("silver")
        gold = lake.child("gold")

        raw_rows = _generate_raw_rows()

        # --- Bronze: ingest ---
        total_rows = _write_bronze(bronze, raw_rows)
        _assert_bronze(bronze, total_rows)

        # --- Silver: clean ---
        silver_df = _clean_to_silver(bronze, silver)
        _assert_silver(silver, silver_df)
        assert len(silver_df) < len(raw_rows), "Silver should have fewer rows than raw"

        # --- Gold: aggregate ---
        hourly_count, daily_count = _aggregate_to_gold(silver_df, gold)
        _assert_gold(gold, hourly_count, daily_count)

        # --- Extension integration ---
        _test_partition_helpers(silver)
        _test_batch_operations(gold)
        _test_cache_layer(gold)
        _test_observe_hooks(lake)
        _test_atomic_writes(lake)

        # --- Cross-layer verification ---
        # Gold aggregation reduces rows (group-by), even if wider columns
        # make file sizes larger.  Verify row count reduction instead of
        # byte size, which depends on schema width.
        gold_total_rows = hourly_count + daily_count
        assert gold_total_rows < len(silver_df), (
            f"Gold rows ({gold_total_rows}) should be fewer than Silver rows ({len(silver_df)}) after aggregation"
        )

        # Lake should see all three layers
        top_folder_names = {f.name for f in lake.list_folders("")}
        assert {"bronze", "silver", "gold"} <= top_folder_names

    def test_memory_baseline(self, memory_lake: Store) -> None:
        """Baseline: full pipeline on MemoryBackend (always runs)."""
        self._run_pipeline(memory_lake)
        assert {"bronze", "silver", "gold"} <= {f.name for f in memory_lake.list_folders("")}

    @minio_skip
    def test_s3_minio(self, s3_lake: Store) -> None:
        """Full pipeline on S3Backend via MinIO Docker."""
        self._run_pipeline(s3_lake)
        assert {"bronze", "silver", "gold"} <= {f.name for f in s3_lake.list_folders("")}

    @s3_pyarrow_skip
    def test_s3_pyarrow_minio(self, s3_pyarrow_lake: Store) -> None:
        """Full pipeline on S3PyArrowBackend via MinIO Docker."""
        self._run_pipeline(s3_pyarrow_lake)
        assert {"bronze", "silver", "gold"} <= {f.name for f in s3_pyarrow_lake.list_folders("")}

    @azurite_skip
    def test_azurite(self, azurite_lake: Store) -> None:
        """Full pipeline on AzureBackend via Azurite Docker."""
        self._run_pipeline(azurite_lake)
        assert {"bronze", "silver", "gold"} <= {f.name for f in azurite_lake.list_folders("")}
