"""Toxiproxy helpers and proxied connection strings for benchmarks.

Supports latency simulation for all Docker backends (Azurite, MinIO, SFTP)
via named network profiles.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Toxiproxy API
# ---------------------------------------------------------------------------

TOXIPROXY_HOST = os.environ.get("BENCH_TOXIPROXY_HOST", "127.0.0.1")
TOXIPROXY_API_PORT = int(os.environ.get("BENCH_TOXIPROXY_API_PORT", "8474"))
_TOXIPROXY_API = f"http://{TOXIPROXY_HOST}:{TOXIPROXY_API_PORT}"

# Proxy names must match toxiproxy.json entries.
PROXY_NAMES = ("azurite", "minio", "sftp")

# ---------------------------------------------------------------------------
# Named network profiles
# ---------------------------------------------------------------------------

NETWORK_PROFILES: dict[str, dict[str, int]] = {
    "clean": {"latency": 0, "jitter": 0},
    "rtt20": {"latency": 20, "jitter": 7},
    "rtt50": {"latency": 50, "jitter": 17},
    "rtt100": {"latency": 100, "jitter": 33},
}

# ---------------------------------------------------------------------------
# Azurite connection strings (direct + proxied)
# ---------------------------------------------------------------------------

AZURITE_HOST = os.environ.get("BENCH_AZURITE_HOST", "127.0.0.1")
AZURITE_PORT = int(os.environ.get("BENCH_AZURITE_PORT", "10000"))
TOXIPROXY_AZURITE_PORT = int(os.environ.get("BENCH_TOXIPROXY_AZURITE_PORT", "10001"))

_AZURITE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    f"AccountKey={_AZURITE_KEY};"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
)

TOXIPROXY_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    f"AccountKey={_AZURITE_KEY};"
    f"BlobEndpoint=http://{TOXIPROXY_HOST}:{TOXIPROXY_AZURITE_PORT}/devstoreaccount1;"
)

# ---------------------------------------------------------------------------
# MinIO connection constants (proxied)
# ---------------------------------------------------------------------------

TOXIPROXY_MINIO_PORT = int(os.environ.get("BENCH_MINIO_PROXY_PORT", "19000"))
TOXIPROXY_MINIO_ENDPOINT = f"http://{TOXIPROXY_HOST}:{TOXIPROXY_MINIO_PORT}"

# ---------------------------------------------------------------------------
# SFTP connection constants (proxied)
# ---------------------------------------------------------------------------

TOXIPROXY_SFTP_PORT = int(os.environ.get("BENCH_SFTP_PROXY_PORT", "12222"))

# ---------------------------------------------------------------------------
# Low-level toxic management
# ---------------------------------------------------------------------------


def set_latency(latency_ms: int, proxy_name: str = "azurite") -> None:
    """Add or remove a latency toxic on the given proxy via the Toxiproxy HTTP API."""
    toxic_url = f"{_TOXIPROXY_API}/proxies/{proxy_name}/toxics"

    # Remove existing latency toxic (ignore 404 if absent).
    req = urllib.request.Request(f"{toxic_url}/bench_latency", method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    if latency_ms > 0:
        payload = json.dumps(
            {
                "name": "bench_latency",
                "type": "latency",
                "stream": "upstream",
                "toxicity": 1.0,
                "attributes": {"latency": latency_ms, "jitter": latency_ms // 3},
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
        set_latency(profile["latency"], proxy_name=name)


def clear_all_toxics() -> None:
    """Remove latency toxics from all proxies."""
    for name in PROXY_NAMES:
        clear_latency(proxy_name=name)
