"""Bronze layer — raw ingest from MeteoSwiss HTTP to local store via ext.transfer.

Each asset downloads one CSV file. No transformation, no IO manager —
this is file-level transfer, not DataFrame serialization.
"""

from __future__ import annotations

import logging

from dagster import asset
from stores import bronze, meteo_store, print_cache_stats

from remote_store.ext.transfer import transfer

log = logging.getLogger(__name__)

# Station codes and their MeteoSwiss URL paths (daily granularity).
STATIONS: dict[str, str] = {
    "ber": "Bern-Zollikofen",
    "klo": "Zurich-Kloten",
    "lug": "Lugano",
}


def _bytes_transferred(n: int) -> None:
    """Progress callback for transfer — logs chunk sizes."""
    log.debug("Transferred %d bytes", n)


@asset(group_name="bronze")
def meteo_stations() -> None:
    """Download station metadata CSV from MeteoSwiss."""
    transfer(
        meteo_store,
        "ogd-smn_meta_stations.csv",
        bronze,
        "meta/stations.csv",
        overwrite=True,
        on_progress=_bytes_transferred,
    )
    print_cache_stats()


@asset(group_name="bronze")
def bronze_bern() -> None:
    """Ingest Bern daily weather data."""
    transfer(
        meteo_store,
        "ber/ogd-smn_ber_d.csv",
        bronze,
        "stations/ber/daily.csv",
        overwrite=True,
        on_progress=_bytes_transferred,
    )
    print_cache_stats()


@asset(group_name="bronze")
def bronze_zurich() -> None:
    """Ingest Zurich-Kloten daily weather data."""
    transfer(
        meteo_store,
        "klo/ogd-smn_klo_d.csv",
        bronze,
        "stations/klo/daily.csv",
        overwrite=True,
        on_progress=_bytes_transferred,
    )
    print_cache_stats()


@asset(group_name="bronze")
def bronze_lugano() -> None:
    """Ingest Lugano daily weather data."""
    transfer(
        meteo_store,
        "lug/ogd-smn_lug_d.csv",
        bronze,
        "stations/lug/daily.csv",
        overwrite=True,
        on_progress=_bytes_transferred,
    )
    print_cache_stats()
