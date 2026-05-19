"""Toxiproxy helpers and proxied connection strings for benchmarks.

Supports latency simulation for all Docker backends (Azurite, MinIO, SFTP)
via named network profiles. Host/port constants come from
``infra._settings`` (single source of truth shared with the test suite
and docker-compose).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from infra._settings import (
    AZURITE_CONN_STR,
    AZURITE_HOST,
    AZURITE_PORT,
    TOXIPROXY_API_PORT,
    TOXIPROXY_AZURITE_CONN_STR,
    TOXIPROXY_AZURITE_PORT,
    TOXIPROXY_HOST,
    TOXIPROXY_MINIO_ENDPOINT,
    TOXIPROXY_MINIO_PORT,
    TOXIPROXY_SFTP_PORT,
)

# Re-exported so existing `from benchmarks._toxiproxy import ...` callers
# (and any third party that grew to depend on this surface) keep working.
__all__ = [
    "AZURITE_CONN_STR",
    "AZURITE_HOST",
    "AZURITE_PORT",
    "NETWORK_PROFILES",
    "PROXY_NAMES",
    "TOXIPROXY_API_PORT",
    "TOXIPROXY_AZURITE_CONN_STR",
    "TOXIPROXY_AZURITE_PORT",
    "TOXIPROXY_HOST",
    "TOXIPROXY_MINIO_ENDPOINT",
    "TOXIPROXY_MINIO_PORT",
    "TOXIPROXY_SFTP_PORT",
    "apply_profile",
    "clear_all_toxics",
    "clear_latency",
    "set_latency",
]

_TOXIPROXY_API = f"http://{TOXIPROXY_HOST}:{TOXIPROXY_API_PORT}"

# Proxy names must match toxiproxy.json entries.
PROXY_NAMES = ("azurite", "minio", "sftp")

NETWORK_PROFILES: dict[str, dict[str, int]] = {
    "clean": {"latency": 0, "jitter": 0},
    "rtt20": {"latency": 20, "jitter": 7},
    "rtt50": {"latency": 50, "jitter": 17},
    "rtt100": {"latency": 100, "jitter": 33},
}

# ---------------------------------------------------------------------------
# Low-level toxic management
# ---------------------------------------------------------------------------


def set_latency(latency_ms: int, proxy_name: str = "azurite", jitter_ms: int | None = None) -> None:
    """Add or remove a latency toxic on the given proxy via the Toxiproxy HTTP API.

    Args:
        latency_ms: Base latency in milliseconds. 0 removes the toxic.
        proxy_name: Toxiproxy proxy name (must match ``toxiproxy.json``).
        jitter_ms: Jitter in milliseconds. Defaults to ``latency_ms // 3``.
    """
    toxic_url = f"{_TOXIPROXY_API}/proxies/{proxy_name}/toxics"

    # Remove existing latency toxic (ignore 404 if absent).
    req = urllib.request.Request(f"{toxic_url}/bench_latency", method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    if latency_ms > 0:
        jitter = jitter_ms if jitter_ms is not None else latency_ms // 3
        payload = json.dumps(
            {
                "name": "bench_latency",
                "type": "latency",
                "stream": "upstream",
                "toxicity": 1.0,
                "attributes": {"latency": latency_ms, "jitter": jitter},
            }
        ).encode()
        req = urllib.request.Request(toxic_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)


def clear_latency(proxy_name: str = "azurite") -> None:
    """Remove the bench_latency toxic from the given proxy."""
    set_latency(0, proxy_name=proxy_name)


# ---------------------------------------------------------------------------
# Profile-level management
# ---------------------------------------------------------------------------


def apply_profile(profile_name: str, proxy_name: str | None = None) -> None:
    """Apply a named network profile to one or all proxies.

    Args:
        profile_name: One of ``clean``, ``rtt20``, ``rtt50``, ``rtt100``.
        proxy_name: Apply to a single proxy. If ``None``, apply to all proxies.
    """
    if profile_name not in NETWORK_PROFILES:
        msg = f"Unknown network profile {profile_name!r}. Choose from: {', '.join(NETWORK_PROFILES)}"
        raise ValueError(msg)

    profile = NETWORK_PROFILES[profile_name]
    targets = (proxy_name,) if proxy_name else PROXY_NAMES
    for name in targets:
        set_latency(profile["latency"], proxy_name=name, jitter_ms=profile["jitter"])


def clear_all_toxics() -> None:
    """Remove latency toxics from all proxies."""
    for name in PROXY_NAMES:
        clear_latency(proxy_name=name)
