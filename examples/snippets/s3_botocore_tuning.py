"""S3 botocore-tuning snippets — sourced by guides/backends/s3.md.

Named regions are included via pymdownx.snippets ``--8<--`` syntax. Each
snippet constructs an ``S3Backend`` with the relevant ``client_options``
and then triggers the lazy ``_s3fs`` property: this exercises
``_build_s3fs_kwargs()`` end to end (no ``config`` in ``client_kwargs``,
documented option present in ``config_kwargs``) without performing any
network I/O. So ``hatch run examples`` proves each documented use case
actually wires through to s3fs, not just that the constructor accepts the
keyword shape.

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


def _assert_wired(backend: S3Backend) -> dict:
    """Trigger lazy init and return the dict s3fs received as config_kwargs.

    Asserts the never-clobber invariant (S3-026): ``client_kwargs['config']``
    is unset on the s3fs.S3FileSystem instance.
    """
    fs = backend._s3fs
    assert "config" not in fs.client_kwargs, (
        "client_kwargs['config'] must never be set — it duplicates s3fs's "
        "own config=AioConfig(...) argument to aiobotocore.create_client"
    )
    return dict(fs.config_kwargs)


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
    cfg = _assert_wired(backend)
    assert cfg["proxies"] == {"http": None, "https": None}
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
    cfg = _assert_wired(backend)
    assert cfg["proxies"] == {
        "http": "http://proxy.corp:3128",
        "https": "http://proxy.corp:3128",
    }
    backend.close()


def _retries_policy() -> None:
    # --8<-- [start:retries-policy]
    backend = S3Backend(
        bucket="my-bucket",
        retry=RetryPolicy(max_attempts=5),
    )
    # --8<-- [end:retries-policy]
    cfg = _assert_wired(backend)
    assert cfg["retries"] == {"max_attempts": 5, "mode": "standard"}
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
    cfg = _assert_wired(backend)
    # No retry= here, so caller's adaptive mode survives.
    assert cfg["retries"] == {"max_attempts": 5, "mode": "adaptive"}
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
    cfg = _assert_wired(backend)
    assert cfg["connect_timeout"] == 3.0
    assert cfg["read_timeout"] == 10.0
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
    cfg = _assert_wired(backend)
    assert cfg["s3"] == {"addressing_style": "path"}
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
    cfg = _assert_wired(backend)
    assert cfg["connect_timeout"] == 3.0
    assert cfg["read_timeout"] == 10.0
    assert cfg["s3"] == {"addressing_style": "path"}
    assert cfg["proxies"] == {"http": None, "https": None}
    # RetryPolicy wins on retries (replaces the dict wholesale).
    assert cfg["retries"] == {"max_attempts": 5, "mode": "standard"}
    backend.close()


if __name__ == "__main__":
    demo()
