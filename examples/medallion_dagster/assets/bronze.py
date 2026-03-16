"""Bronze layer — raw ingest from MeteoSwiss HTTP to local store.

Each asset downloads one CSV file via read_bytes + write. Using read_bytes
(not streaming read) ensures ext.cache can cache the HTTP responses.
No transformation, no IO manager — this is file-level copy.
"""

from __future__ import annotations

from dagster import asset
from stores import bronze, meteo_store, print_cache_stats


def _ingest(src_path: str, dst_path: str) -> None:
    """Read from HTTP source and write to local Bronze store."""
    data = meteo_store.read_bytes(src_path)
    bronze.write(dst_path, data, overwrite=True)
    print(f"  Bronze: {src_path} -> {dst_path} ({len(data):,} bytes)")


@asset(group_name="bronze")
def meteo_stations() -> None:
    """Download station metadata CSV from MeteoSwiss."""
    _ingest("ogd-smn_meta_stations.csv", "meta/stations.csv")
    print_cache_stats()


@asset(group_name="bronze")
def bronze_bern() -> None:
    """Ingest Bern daily weather data."""
    _ingest("ber/ogd-smn_ber_d_recent.csv", "stations/ber/daily.csv")
    print_cache_stats()


@asset(group_name="bronze")
def bronze_zurich() -> None:
    """Ingest Zurich-Kloten daily weather data."""
    _ingest("klo/ogd-smn_klo_d_recent.csv", "stations/klo/daily.csv")
    print_cache_stats()


@asset(group_name="bronze")
def bronze_lugano() -> None:
    """Ingest Lugano daily weather data."""
    _ingest("lug/ogd-smn_lug_d_recent.csv", "stations/lug/daily.csv")
    print_cache_stats()
