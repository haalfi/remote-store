"""Shared Toxiproxy helpers and Azurite connection strings for benchmarks."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Connection strings
# ---------------------------------------------------------------------------

AZURITE_HOST = os.environ.get("BENCH_AZURITE_HOST", "127.0.0.1")
AZURITE_PORT = int(os.environ.get("BENCH_AZURITE_PORT", "10000"))
AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw==;"
    f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
)

TOXIPROXY_HOST = os.environ.get("BENCH_TOXIPROXY_HOST", "127.0.0.1")
TOXIPROXY_API_PORT = int(os.environ.get("BENCH_TOXIPROXY_API_PORT", "8474"))
TOXIPROXY_AZURITE_PORT = int(os.environ.get("BENCH_TOXIPROXY_AZURITE_PORT", "10001"))
TOXIPROXY_AZURITE_CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq"
    "/K1SZFPTOtr/KBHBeksoGMGw==;"
    f"BlobEndpoint=http://{TOXIPROXY_HOST}:{TOXIPROXY_AZURITE_PORT}/devstoreaccount1;"
)


# ---------------------------------------------------------------------------
# Latency management
# ---------------------------------------------------------------------------


def set_latency(latency_ms: int) -> None:
    """Add or remove a latency toxic on the 'azurite' proxy via the Toxiproxy HTTP API."""
    api = f"http://{TOXIPROXY_HOST}:{TOXIPROXY_API_PORT}"
    toxic_url = f"{api}/proxies/azurite/toxics"

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


def clear_latency() -> None:
    """Remove the bench_latency toxic (cleanup)."""
    set_latency(0)
