"""S3 botocore-tuning snippets — sourced by guides/backends/s3.md.

Named regions are included via pymdownx.snippets ``--8<--`` syntax. Each
snippet constructs an ``S3Backend`` with the relevant ``client_options``;
no I/O is performed (s3fs is created lazily on first operation), so the
snippets execute under ``hatch run examples`` without network access.

The shared invariant is documented in spec S3-026: every botocore ``Config``
source flows to s3fs as ``opts["config_kwargs"]`` (a dict). Callers should
not set ``client_kwargs["config"]`` directly (BUG-178, BUG-185).
"""

from __future__ import annotations

from remote_store import RetryPolicy
from remote_store.backends import S3Backend


def demo() -> None:
    """Execute all S3 botocore-tuning snippets."""
    _proxies_disable()
    _proxies_explicit()
    _retries_policy()
    _retries_config_kwargs()
    _timeouts()
    _minio_addressing()
    _everything()


def _proxies_disable() -> None:
    # --8<-- [start:proxies-disable]
    backend = S3Backend(
        bucket="my-bucket",
        endpoint_url="https://s3.internal:9000",
        client_options={
            "config_kwargs": {
                "proxies": {"http": None, "https": None},
            },
        },
    )
    # --8<-- [end:proxies-disable]
    backend.close()


def _proxies_explicit() -> None:
    # --8<-- [start:proxies-explicit]
    backend = S3Backend(
        bucket="my-bucket",
        client_options={
            "config_kwargs": {
                "proxies": {
                    "http": "http://proxy.corp:3128",
                    "https": "http://proxy.corp:3128",
                },
            },
        },
    )
    # --8<-- [end:proxies-explicit]
    backend.close()


def _retries_policy() -> None:
    # --8<-- [start:retries-policy]
    backend = S3Backend(
        bucket="my-bucket",
        retry=RetryPolicy(max_attempts=5),
    )
    # --8<-- [end:retries-policy]
    backend.close()


def _retries_config_kwargs() -> None:
    # --8<-- [start:retries-config-kwargs]
    backend = S3Backend(
        bucket="my-bucket",
        client_options={
            "config_kwargs": {
                "retries": {"max_attempts": 5, "mode": "adaptive"},
            },
        },
    )
    # --8<-- [end:retries-config-kwargs]
    backend.close()


def _timeouts() -> None:
    # --8<-- [start:timeouts]
    backend = S3Backend(
        bucket="my-bucket",
        client_options={
            "config_kwargs": {
                "connect_timeout": 3.0,
                "read_timeout": 10.0,
            },
        },
    )
    # --8<-- [end:timeouts]
    backend.close()


def _minio_addressing() -> None:
    # --8<-- [start:minio-addressing]
    backend = S3Backend(
        bucket="my-bucket",
        endpoint_url="https://minio.internal:9000",
        key="AKIA...",
        secret="...",
        client_options={
            "config_kwargs": {
                "s3": {"addressing_style": "path"},
            },
        },
    )
    # --8<-- [end:minio-addressing]
    backend.close()


def _everything() -> None:
    # --8<-- [start:everything]
    backend = S3Backend(
        bucket="my-bucket",
        endpoint_url="https://s3.internal:9000",
        key="AKIA...",
        secret="...",
        retry=RetryPolicy(max_attempts=5),
        client_options={
            "config_kwargs": {
                "connect_timeout": 3.0,
                "read_timeout": 10.0,
                "s3": {"addressing_style": "path"},
                "proxies": {"http": None, "https": None},
            },
        },
    )
    # --8<-- [end:everything]
    backend.close()


if __name__ == "__main__":
    demo()
